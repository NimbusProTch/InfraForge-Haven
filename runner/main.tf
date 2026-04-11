terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.49"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

variable "hcloud_token" {
  type      = string
  sensitive = true
}

variable "ssh_public_key" {
  type        = string
  description = "SSH public key for runner access"
}

resource "hcloud_ssh_key" "runner" {
  name       = "haven-ci-runner"
  public_key = var.ssh_public_key
}

resource "hcloud_server" "runner" {
  name        = "haven-ci-runner"
  server_type = "cx22"
  image       = "ubuntu-22.04"
  location    = "fsn1"
  ssh_keys    = [hcloud_ssh_key.runner.id]

  user_data = <<-CLOUD_INIT
    #!/bin/bash
    set -euo pipefail
    apt-get update -qq
    apt-get install -y -qq curl git jq unzip docker.io python3 python3-pip python3-venv nodejs npm build-essential
    systemctl enable --now docker
    useradd -m -s /bin/bash -G docker runner
    RUNNER_VERSION="2.321.0"
    su - runner -c "
      mkdir -p actions-runner && cd actions-runner
      curl -sL https://github.com/actions/runner/releases/download/v\$RUNNER_VERSION/actions-runner-linux-x64-\$RUNNER_VERSION.tar.gz | tar xz
    "
  CLOUD_INIT

  labels = {
    role    = "ci-runner"
    project = "haven"
  }
}

output "runner_ip" {
  value = hcloud_server.runner.ipv4_address
}
