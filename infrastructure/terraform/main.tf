# [NOW] skeleton — model ONLY what we provision (ADR 0007).
# Real modules land in PLAT-01: app-service, database (Postgres+pgvector),
# redis, storage (R2), edge (Cloudflare). No k8s / VPC / sandbox yet.
#
# Example shape (commented until PLAT-01 wires real providers):
# module "database" {
#   source      = "./modules/database"
#   environment = var.environment
# }

locals {
  common_tags = {
    project     = "keel"
    environment = var.environment
    managed_by  = "terraform"
  }
}
