resource "google_artifact_registry_repository" "defuse" {
  location      = var.region
  repository_id = "defuse"
  format        = "DOCKER"
  description   = "Defuse container images"
}
