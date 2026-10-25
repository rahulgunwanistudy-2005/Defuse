# Workload Identity Federation trusting gitlab.com, pinned to the Defuse project path and
# protected refs. No static GCP service-account keys anywhere; CI authenticates with id_tokens.

resource "google_iam_workload_identity_pool" "gitlab" {
  workload_identity_pool_id = "defuse-gitlab"
  display_name              = "Defuse GitLab pool"
}

resource "google_iam_workload_identity_pool_provider" "gitlab" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.gitlab.workload_identity_pool_id
  workload_identity_pool_provider_id = "gitlab-com"
  display_name                       = "gitlab.com OIDC"

  attribute_mapping = {
    "google.subject"           = "assertion.sub"
    "attribute.project_path"   = "assertion.project_path"
    "attribute.ref"            = "assertion.ref"
    "attribute.ref_protected"  = "assertion.ref_protected"
    "attribute.pipeline_source" = "assertion.pipeline_source"
  }

  # Only the Defuse project, and only protected refs, may mint tokens.
  attribute_condition = "attribute.project_path == \"${var.gitlab_project_path}\" && attribute.ref_protected == \"true\""

  oidc {
    issuer_uri = "https://gitlab.com"
  }
}

resource "google_service_account" "containment" {
  account_id   = "defuse-containment"
  display_name = "Defuse containment executor"
}

resource "google_service_account" "deployer" {
  account_id   = "defuse-deployer"
  display_name = "Defuse Cloud Run deployer"
}

# Bind the WIF identities (scoped to the Defuse project path) to the service accounts.
resource "google_service_account_iam_member" "containment_wif" {
  service_account_id = google_service_account.containment.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.gitlab.name}/attribute.project_path/${var.gitlab_project_path}"
}

resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.gitlab.name}/attribute.project_path/${var.gitlab_project_path}"
}

# Least privilege: containment may swap instance tags, snapshot disks and run IAP commands.
resource "google_project_iam_member" "containment_compute" {
  project = var.project_id
  role    = "roles/compute.instanceAdmin.v1"
  member  = "serviceAccount:${google_service_account.containment.email}"
}

resource "google_project_iam_member" "deployer_run" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}
