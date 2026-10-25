resource "google_sql_database_instance" "defuse" {
  name             = "defuse-pg"
  database_version = "POSTGRES_16"
  region           = var.region
  settings {
    tier = var.db_tier
    ip_configuration { ipv4_enabled = true }
    backup_configuration { enabled = true }
  }
  deletion_protection = false
}

resource "google_sql_database" "defuse" {
  name     = "defuse"
  instance = google_sql_database_instance.defuse.name
}

resource "google_secret_manager_secret" "db_url" {
  secret_id = "defuse-database-url"
  replication { auto {} }
}
