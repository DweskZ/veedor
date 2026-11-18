# GitHub Actions -> AWS without long-lived keys (OIDC). Created only when github_repository is set.
# The role can: upload releases/gh-* to the release bucket and run ONE custom Systems Manager document
# (below) on THIS instance. That document takes a single validated release id and runs only
# server-update.sh: the role cannot run arbitrary shell (it has no right to AWS-RunShellScript) and
# cannot create or change infrastructure. Trust is limited to one repository AND one GitHub environment
# (so the owner can require manual approval there).
locals {
  oidc_enabled = var.github_repository != "" && var.create_release_bucket
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = local.oidc_enabled && var.create_github_oidc_provider ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = local.oidc_enabled && !var.create_github_oidc_provider ? 1 : 0
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  github_provider_arn = local.oidc_enabled ? (
    var.create_github_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
  ) : ""
}

data "aws_iam_policy_document" "github_trust" {
  count = local.oidc_enabled ? 1 : 0
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.github_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Exactly this repository AND this GitHub environment: the job's `sub` claim is
    # repo:<owner>/<repo>:environment:<name> only when the job declares `environment: <name>`, and GitHub
    # evaluates the environment's protection rules (required reviewers, deployment branches) first.
    # A branch-only subject would let any workflow on that branch assume the role.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${var.github_environment}"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  count                = local.oidc_enabled ? 1 : 0
  name_prefix          = "${var.project}-gh-deploy-"
  assume_role_policy   = data.aws_iam_policy_document.github_trust[0].json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "github_deploy" {
  count = local.oidc_enabled ? 1 : 0

  statement {
    sid       = "UploadRelease"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.releases[0].arn}/releases/gh-*"]
  }
  statement {
    sid     = "RunTheDeployDocumentOnTheServer"
    actions = ["ssm:SendCommand"]
    # Only our own document and only this instance. AWS-RunShellScript is deliberately NOT listed.
    resources = [
      aws_ssm_document.deploy[0].arn,
      aws_instance.server.arn,
    ]
  }
  statement {
    sid = "ReadCommandResult"
    # AWS Service Authorization Reference: these two actions support no resource types and no condition
    # keys, so "*" is the only possible resource. They only read command results.
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  count  = local.oidc_enabled ? 1 : 0
  name   = "deploy"
  role   = aws_iam_role.github_deploy[0].id
  policy = data.aws_iam_policy_document.github_deploy[0].json
}

# ---------------------------------------------------------------------------------------------------
# The ONLY thing the deploy role may run on the server. One parameter, validated twice by SSM
# (allowedPattern at the API and again in the agent), handed to the shell as an environment variable
# (interpolationType = ENV_VAR: a literal string, never spliced into the command line), and validated a
# third time by server-update.sh. The bucket is fixed here, not a parameter.
# ---------------------------------------------------------------------------------------------------
resource "aws_ssm_document" "deploy" {
  count           = local.oidc_enabled ? 1 : 0
  name            = "${var.project}-deploy-release"
  document_type   = "Command"
  document_format = "JSON"
  target_type     = "/AWS::EC2::Instance"

  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Veedor: download release releases/<releaseId>/ from the release bucket and run server-update.sh. Nothing else."
    parameters = {
      releaseId = {
        type              = "String"
        description       = "(Required) Release id produced by the deploy workflow, gh-<run id>-<attempt>."
        allowedPattern    = "^gh-[0-9]{1,20}-[0-9]{1,3}$"
        minChars          = 6
        maxChars          = 30
        interpolationType = "ENV_VAR"
      }
    }
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "updateServer"
      inputs = {
        timeoutSeconds = "1800"
        runCommand = [
          "VEEDOR_RELEASE_BUCKET=${aws_s3_bucket.releases[0].bucket} /srv/veedor/deploy/scripts/server-update.sh --release-id \"$SSM_releaseId\"",
        ]
      }
    }]
  })
}
