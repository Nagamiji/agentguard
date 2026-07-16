variable "environment" {
  type        = string
  description = "Deployment environment: dev | staging | production"
  default     = "dev"
}

variable "region" {
  type        = string
  description = "Cloud region for [NOW] resources"
  default     = "us-east-1"
}
