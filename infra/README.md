# infra

Terraform for the Google Cloud deployment, using GitLab-managed Terraform state (HTTP backend).

Resources: Artifact Registry; Cloud Run `engine`, `web`, `sinkhole`; Cloud SQL Postgres (smallest
tier); Secret Manager; a Workload Identity Pool + provider trusting gitlab.com with attribute
conditions pinned to the Defuse project path and protected refs; a GCE `e2-small` runner with
network tag `runner-live`; a deny-all-egress firewall rule for tag `quarantined` (isolation = tag
swap via API). No static GCP keys anywhere.

```
terraform init -backend-config="address=$GL_STATE_ADDRESS" ...
terraform apply -var project_id=... -var gitlab_project_path=defuse-sandbox/defuse -var gitlab_project_id=...
terraform output web_url   # the live console URL (a submission field; must stay up)
```
