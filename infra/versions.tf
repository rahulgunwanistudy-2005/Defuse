terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  # GitLab-managed Terraform state (HTTP backend). Configured via `terraform init` with the
  # project's state address and a CI job token; no credentials in the repo.
  backend "http" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}
