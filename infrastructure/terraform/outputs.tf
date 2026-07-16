output "environment" {
  value       = var.environment
  description = "Active environment"
}

output "common_tags" {
  value       = local.common_tags
  description = "Tags applied to [NOW] resources for cost attribution"
}
