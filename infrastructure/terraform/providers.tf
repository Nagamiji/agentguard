# [NOW] providers. Real backends/credentials are injected via CI, never committed.
# Governed by ../../../keel/os/standards/infrastructure.md (ADR 0007).
terraform {
  required_version = ">= 1.6"
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
    # aws/gcp provider added when the app-service module lands (PLAT-01).
  }
  # backend "s3"/"gcs" (remote, locked state) configured per-env at PLAT-01.
}
