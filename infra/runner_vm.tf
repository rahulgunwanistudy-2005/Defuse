# The persistent sandbox runner: a GCE e2-small running gitlab-runner (shell executor, tag
# sandbox-persistent) with network tag runner-live. Isolation is a tag swap to "quarantined",
# which a deny-all-egress firewall rule catches. The Defuse engine performs the swap via API.

resource "google_compute_network" "sandbox" {
  name                    = "defuse-sandbox"
  auto_create_subnetwork  = true
}

resource "google_compute_firewall" "quarantine_deny_egress" {
  name      = "defuse-quarantine-deny-egress"
  network   = google_compute_network.sandbox.name
  direction = "EGRESS"
  priority  = 100
  deny { protocol = "all" }
  destination_ranges = ["0.0.0.0/0"]
  target_tags        = ["quarantined"]
}

resource "google_compute_instance" "runner" {
  name         = "defuse-runner-1"
  machine_type = "e2-small"
  zone         = var.zone
  tags         = ["runner-live"]

  boot_disk {
    initialize_params { image = "debian-cloud/debian-12" }
  }
  network_interface {
    network = google_compute_network.sandbox.name
    access_config {}
  }
  metadata = {
    enable-oslogin = "TRUE"
  }
  metadata_startup_script = <<-EOT
    #!/bin/bash
    curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh | bash
    apt-get install -y gitlab-runner nodejs
    mkdir -p /srv/defuse-sentinel && for i in $(seq 1 9); do echo "sentinel $i" > /srv/defuse-sentinel/file-$i.txt; done
  EOT
}
