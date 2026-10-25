output "engine_url" { value = google_cloud_run_v2_service.engine.uri }
output "web_url" { value = google_cloud_run_v2_service.web.uri }
output "sinkhole_url" { value = google_cloud_run_v2_service.sinkhole.uri }
output "wif_provider" {
  value = google_iam_workload_identity_pool_provider.gitlab.name
}
output "wif_audience" {
  value = "//iam.googleapis.com/${google_iam_workload_identity_pool_provider.gitlab.name}"
}
output "containment_service_account" { value = google_service_account.containment.email }
