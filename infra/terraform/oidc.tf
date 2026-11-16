# GitHub Actions -> AWS without long-lived keys (OIDC). Created only when github_repository is set.
# The role can: upload releases/gh-* to the release bucket and run the update on THIS instance through
# Systems Manager Run Command. It cannot create or change infrastructure.
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
    # Exactly this repository and this branch (workflow_dispatch run from that branch).
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/${var.github_branch}"]
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
    sid     = "RunUpdateOnTheServer"
    actions = ["ssm:SendCommand"]
    resources = [
      "arn:aws:ssm:${var.region}::document/AWS-RunShellScript",
      aws_instance.server.arn,
    ]
  }
  statement {
    sid       = "ReadCommandResult"
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
