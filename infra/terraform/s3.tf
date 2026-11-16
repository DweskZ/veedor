# Private bucket that carries releases to the server (and, optionally, backups from it).
# Layout: releases/<name>/... (uploaded by the owner or by the GitHub workflow), backups/ (from the server).
resource "aws_s3_bucket" "releases" {
  count         = var.create_release_bucket ? 1 : 0
  bucket        = "${var.project}-releases-${data.aws_caller_identity.current.account_id}-${var.region}"
  force_destroy = true # `terraform destroy` must be able to remove it even when it holds releases
}

resource "aws_s3_bucket_public_access_block" "releases" {
  count                   = var.create_release_bucket ? 1 : 0
  bucket                  = aws_s3_bucket.releases[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "releases" {
  count  = var.create_release_bucket ? 1 : 0
  bucket = aws_s3_bucket.releases[0].id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "releases" {
  count  = var.create_release_bucket ? 1 : 0
  bucket = aws_s3_bucket.releases[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "releases" {
  count  = var.create_release_bucket ? 1 : 0
  bucket = aws_s3_bucket.releases[0].id

  rule {
    id     = "expire-releases"
    status = "Enabled"
    filter {
      prefix = "releases/"
    }
    expiration {
      days = var.release_expiry_days
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  rule {
    id     = "expire-backups"
    status = "Enabled"
    filter {
      prefix = "backups/"
    }
    expiration {
      days = 90
    }
  }
}

data "aws_iam_policy_document" "releases_tls_only" {
  count = var.create_release_bucket ? 1 : 0
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.releases[0].arn, "${aws_s3_bucket.releases[0].arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "releases" {
  count  = var.create_release_bucket ? 1 : 0
  bucket = aws_s3_bucket.releases[0].id
  policy = data.aws_iam_policy_document.releases_tls_only[0].json

  depends_on = [aws_s3_bucket_public_access_block.releases]
}
