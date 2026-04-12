# =============================================================================
#  iyziops CI runner — main
# =============================================================================
#  Single Hetzner VM hosting var.runner_count parallel GitHub Actions runner
#  systemd units. The VM has its own SSH key (separate blast radius from
#  the platform cluster) and its own state bucket (iyziops-tfstate-runner).
#
#  The cloud-init template lives under templates/ so the main.tf stays free
#  of inline shell.
# =============================================================================

# ----- SSH key (generated, written to logs/ for SCP) ------------------------
#  Persistent, NOT scratch: operator needs this to SSH into the runner for
#  debugging. Lives under logs/ which is gitignored.

resource "tls_private_key" "runner" {
  algorithm = "ED25519"
}

resource "local_sensitive_file" "ssh_private_key" {
  filename        = "${path.root}/../logs/iyziops-runner-ssh.pem"
  content         = tls_private_key.runner.private_key_openssh
  file_permission = "0600"
}

resource "hcloud_ssh_key" "runner" {
  name       = var.name
  public_key = tls_private_key.runner.public_key_openssh
}

# ----- Cloud-init template render ------------------------------------------

locals {
  runner_cloud_init = templatefile("${path.module}/templates/runner-cloud-init.yaml.tpl", {
    name                = var.name
    github_repo         = var.github_repo
    github_runner_token = var.github_runner_token
    runner_count        = var.runner_count
    runner_labels       = join(",", var.runner_labels)
    runner_version      = var.runner_version
  })
}

# ----- Runner VM ------------------------------------------------------------

resource "hcloud_server" "runner" {
  name        = var.name
  server_type = var.server_type
  image       = var.os_image
  location    = var.location

  ssh_keys  = [hcloud_ssh_key.runner.id]
  user_data = local.runner_cloud_init

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  labels = {
    role    = "ci-runner"
    project = "iyziops"
  }
}
