data "aws_caller_identity" "current" {}

# Latest Amazon Linux 2023 arm64 AMI, through the public SSM parameter documented by AWS.
# The instance ignores later AMI changes (below) so a new AMI never replaces a running server.
data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

# Default VPC: no NAT gateway, no extra network cost. A new account has one in every region.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

# ---------------------------------------------------------------------------------------------------
# Network: 80/443 from anywhere, nothing else. No SSH: access is AWS Systems Manager Session Manager.
# ---------------------------------------------------------------------------------------------------
resource "aws_security_group" "web" {
  name_prefix = "${var.project}-web-"
  description = "Veedor: HTTP/HTTPS in, everything out. No SSH."
  vpc_id      = data.aws_vpc.default.id

  tags = { Name = "${var.project}-web" }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.web.id
  description       = "HTTP (redirect to HTTPS, ACME challenge)"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.web.id
  description       = "HTTPS"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

# Egress is open: Session Manager, S3, package repositories, ACME and an LLM provider (optional).
resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.web.id
  description       = "All outbound"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# ---------------------------------------------------------------------------------------------------
# IAM: instance profile for Session Manager (AWS managed core policy) + read/write on the release bucket.
# ---------------------------------------------------------------------------------------------------
data "aws_iam_policy_document" "ec2_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name_prefix        = "${var.project}-ec2-"
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "release_bucket_access" {
  count = var.create_release_bucket ? 1 : 0

  statement {
    sid       = "ListReleaseBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.releases[0].arn]
  }
  statement {
    sid       = "ReadReleases"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.releases[0].arn}/releases/*"]
  }
  statement {
    sid       = "WriteBackups"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.releases[0].arn}/backups/*"]
  }
}

resource "aws_iam_role_policy" "release_bucket_access" {
  count  = var.create_release_bucket ? 1 : 0
  name   = "release-bucket"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.release_bucket_access[0].json
}

resource "aws_iam_instance_profile" "instance" {
  name_prefix = "${var.project}-"
  role        = aws_iam_role.instance.name
}

# ---------------------------------------------------------------------------------------------------
# The server
# ---------------------------------------------------------------------------------------------------
resource "aws_instance" "server" {
  ami                    = data.aws_ssm_parameter.al2023_arm64.value
  instance_type          = var.instance_type
  subnet_id              = sort(data.aws_subnets.default.ids)[0]
  vpc_security_group_ids = [aws_security_group.web.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name

  # Public address comes from the Elastic IP below; do not also pay for an auto-assigned one.
  associate_public_ip_address = false

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 1          # containers cannot reach the metadata service
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    encrypted             = true
    delete_on_termination = true
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    swap_gb = var.swap_gb
  })
  user_data_replace_on_change = false

  tags = { Name = "${var.project}-server" }

  lifecycle {
    ignore_changes = [ami, user_data]
  }
}

resource "aws_eip" "server" {
  domain = "vpc"
  tags   = { Name = "${var.project}-server" }
}

resource "aws_eip_association" "server" {
  instance_id   = aws_instance.server.id
  allocation_id = aws_eip.server.id
}

# ---------------------------------------------------------------------------------------------------
# Optional DNS record in an existing Route 53 zone.
# ---------------------------------------------------------------------------------------------------
resource "aws_route53_record" "site" {
  count   = var.route53_zone_id != "" && var.domain_name != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"
  ttl     = 300
  records = [aws_eip.server.public_ip]
}

# ---------------------------------------------------------------------------------------------------
# Cost guard: monthly cost budget with e-mail alerts at 50 / 80 / 100 percent.
# ---------------------------------------------------------------------------------------------------
resource "aws_budgets_budget" "monthly" {
  name         = "${var.project}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_amount_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_types {
    include_credit = var.budget_include_credits
  }

  dynamic "notification" {
    for_each = [50, 80, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = var.budget_alert_emails
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.budget_alert_emails
  }
}
