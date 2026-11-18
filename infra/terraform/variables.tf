variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "veedor"
}

variable "region" {
  description = "AWS region. us-east-1 has the lowest list price; sa-east-1 (Sao Paulo) is the closest region to Ecuador but costs more (see docs/DEPLOYMENT_AWS.md)."
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "Graviton instance. t4g.small (2 GiB) without the observability stack, t4g.medium (4 GiB) with it."
  type        = string
  default     = "t4g.small"

  validation {
    condition     = can(regex("^[a-z0-9]+g[a-z0-9]*\\.", var.instance_type))
    error_message = "Use an arm64 (Graviton) instance type such as t4g.small: the images are built for linux/arm64."
  }
}

variable "root_volume_gb" {
  description = "Encrypted gp3 root volume size (GiB). Holds the OS, the Docker images, the data and the database."
  type        = number
  default     = 30
}

variable "swap_gb" {
  description = "Swap file created at first boot (GiB). A safety net for a 2 GiB instance; 0 disables it."
  type        = number
  default     = 2
}

variable "domain_name" {
  description = "Optional public host name (for example veedor.example.org). Only used for the optional Route 53 record and the outputs."
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Optional ID of an EXISTING Route 53 hosted zone. When set together with domain_name, an A record to the Elastic IP is created. A hosted zone itself costs money; see docs."
  type        = string
  default     = ""
}

variable "budget_amount_usd" {
  description = "Monthly cost budget in USD. Alerts go out at 50, 80 and 100 percent of it."
  type        = number
  default     = 20
}

variable "budget_alert_emails" {
  description = "E-mail addresses that receive the budget alerts (1 to 10, the AWS Budgets limit per notification). No default on purpose. AWS sends a confirmation message you may need to accept."
  type        = list(string)

  validation {
    condition     = length(var.budget_alert_emails) >= 1 && length(var.budget_alert_emails) <= 10
    error_message = "Give between 1 and 10 e-mail addresses."
  }
}

variable "budget_include_credits" {
  description = "Whether the budget nets credits against cost. false = budget the gross usage, so alerts fire even while credits pay the bill. (Effect on the console figures not verified; check the budget page after creating it.)"
  type        = bool
  default     = false
}

variable "create_release_bucket" {
  description = "Create a private, encrypted S3 bucket used to move releases (and optionally backups) to the server without SSH."
  type        = bool
  default     = true
}

variable "release_expiry_days" {
  description = "Objects in the release bucket are deleted after this many days."
  type        = number
  default     = 14
}

variable "github_repository" {
  description = "owner/name of the GitHub repository allowed to deploy through OIDC. Empty = no OIDC role is created."
  type        = string
  default     = ""
}

variable "github_environment" {
  description = "Name of the GitHub environment the deploy job runs in. Only jobs of github_repository that declare this environment can assume the deploy role. In GitHub (Settings > Environments) add required reviewers and restrict deployment branches to main."
  type        = string
  default     = "production"

  validation {
    condition     = can(regex("^[A-Za-z0-9._-]{1,40}$", var.github_environment))
    error_message = "Use a plain environment name (letters, digits, . _ -)."
  }
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub OIDC identity provider. Set false if the account already has one (only one per URL is allowed)."
  type        = bool
  default     = true
}
