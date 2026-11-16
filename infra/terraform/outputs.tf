output "public_ip" {
  description = "Elastic IP of the server. Use it as http://<ip> until a domain points here."
  value       = aws_eip.server.public_ip
}

output "instance_id" {
  value = aws_instance.server.id
}

output "region" {
  value = var.region
}

output "session_manager_command" {
  description = "Open a shell on the server (needs the AWS CLI and the Session Manager plugin on your machine)."
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.server.id}"
}

output "release_bucket" {
  description = "Bucket for releases and backups (empty when create_release_bucket = false)."
  value       = var.create_release_bucket ? aws_s3_bucket.releases[0].bucket : ""
}

output "upload_release_command" {
  value = var.create_release_bucket ? "aws s3 sync dist/release-<stamp> s3://${aws_s3_bucket.releases[0].bucket}/releases/<stamp>/ --region ${var.region}" : ""
}

output "site_url_hint" {
  description = "Value for build-release.sh --site-url and PUBLIC_ORIGIN."
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "http://${aws_eip.server.public_ip}"
}

output "github_deploy_role_arn" {
  description = "Set as the repository variable AWS_DEPLOY_ROLE_ARN (empty when OIDC is not enabled)."
  value       = local.oidc_enabled ? aws_iam_role.github_deploy[0].arn : ""
}
