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

variable "github_runner_token" {
  type        = string
  sensitive   = true
  description = "GitHub Actions runner registration token"
}

variable "github_repo" {
  type    = string
  default = "NimbusProTch/InfraForge-Haven"
}

variable "runner_count" {
  type    = number
  default = 3
}

resource "hcloud_ssh_key" "runner" {
  name       = "haven-ci-runner"
  public_key = var.ssh_public_key
}

resource "hcloud_server" "runner" {
  name        = "haven-ci-runner"
  server_type = "cx23"
  image       = "ubuntu-22.04"
  location    = "fsn1"
  ssh_keys    = [hcloud_ssh_key.runner.id]

  user_data = <<-CLOUD_INIT
    #!/bin/bash
    set -euo pipefail

    # System packages
    apt-get update -qq
    apt-get install -y -qq curl git jq unzip docker.io python3 python3-pip python3-venv build-essential

    # Docker: insecure registries for Harbor (HTTP-only)
    mkdir -p /etc/docker
    cat > /etc/docker/daemon.json <<'DOCKER_JSON'
    {
      "insecure-registries": ["harbor.46.225.42.2.sslip.io"]
    }
    DOCKER_JSON
    systemctl enable --now docker
    systemctl restart docker

    # Node.js 20 LTS
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs

    # Runner user
    useradd -m -s /bin/bash -G docker runner

    # GitHub Actions Runner
    RUNNER_VERSION="2.321.0"
    RUNNER_TAR="actions-runner-linux-x64-$${RUNNER_VERSION}.tar.gz"

    su - runner -c "
      curl -sL https://github.com/actions/runner/releases/download/v$${RUNNER_VERSION}/$${RUNNER_TAR} -o /tmp/$${RUNNER_TAR}
    "

    # Install N runner instances
    for i in $(seq 1 ${var.runner_count}); do
      su - runner -c "
        mkdir -p actions-runner-$$i && cd actions-runner-$$i
        tar xz -f /tmp/$${RUNNER_TAR}
        ./config.sh --unattended \
          --url https://github.com/${var.github_repo} \
          --token ${var.github_runner_token} \
          --name haven-runner-$$i \
          --labels self-hosted,haven \
          --work _work \
          --replace
      "

      # Systemd service for each runner
      cat > /etc/systemd/system/github-runner-$$i.service <<SYSTEMD
    [Unit]
    Description=GitHub Actions Runner $$i
    After=network.target docker.service

    [Service]
    Type=simple
    User=runner
    WorkingDirectory=/home/runner/actions-runner-$$i
    ExecStart=/home/runner/actions-runner-$$i/run.sh
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    SYSTEMD

      systemctl daemon-reload
      systemctl enable --now github-runner-$$i
    done

    rm -f /tmp/$${RUNNER_TAR}
  CLOUD_INIT

  labels = {
    role    = "ci-runner"
    project = "haven"
  }
}

output "runner_ip" {
  value = hcloud_server.runner.ipv4_address
}
