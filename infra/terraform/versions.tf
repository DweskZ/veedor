terraform {
  required_version = ">= 1.6.0" # Terraform or OpenTofu

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0" # 6.73.0 was the latest release on 2026-11-16
    }
  }

  # Remote state is optional. The default is a local terraform.tfstate next to these files (it contains
  # resource ids, no secrets; keep it, you need it for `destroy`). To keep state in S3 instead, create a
  # private versioned bucket by hand and uncomment (see docs/DEPLOYMENT_AWS.md):
  #
  # backend "s3" {
  #   bucket       = "your-state-bucket"
  #   key          = "veedor/terraform.tfstate"
  #   region       = "us-east-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
    }
  }
}
