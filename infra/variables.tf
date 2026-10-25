variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "us-central1"
}
variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "gitlab_project_path" {
  type        = string
  description = "Defuse project full path, e.g. defuse-sandbox/defuse, for the WIF attribute condition."
}
variable "gitlab_project_id" {
  type        = number
  description = "Numeric GitLab project id, pinned in the WIF attribute condition."
}

variable "db_tier" {
  type    = string
  default = "db-f1-micro"
}
