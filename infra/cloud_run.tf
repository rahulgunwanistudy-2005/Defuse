locals {
  image_base = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.defuse.repository_id}"
}

resource "google_cloud_run_v2_service" "engine" {
  name     = "engine"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  template {
    service_account = google_service_account.deployer.email
    containers {
      image = "${local.image_base}/engine:latest"
      ports { container_port = 8000 }
      env {
        name = "DEFUSE_DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_url.secret_id
            version = "latest"
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service" "web" {
  name     = "web"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  template {
    containers {
      image = "${local.image_base}/web:latest"
      ports { container_port = 3000 }
      env {
        name  = "DEFUSE_API_BASE"
        value = google_cloud_run_v2_service.engine.uri
      }
    }
  }
}

resource "google_cloud_run_v2_service" "sinkhole" {
  name     = "sinkhole"
  location = var.region
  template {
    containers {
      image = "${local.image_base}/sinkhole:latest"
      ports { container_port = 8080 }
    }
  }
}

# The live console must be reachable without login (a submission field).
resource "google_cloud_run_v2_service_iam_member" "web_public" {
  name     = google_cloud_run_v2_service.web.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "engine_public" {
  name     = google_cloud_run_v2_service.engine.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
