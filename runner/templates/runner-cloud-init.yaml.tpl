#cloud-config
# =============================================================================
#  iyziops CI runner — cloud-init
# =============================================================================
#  Installs Docker, Node.js 20, crane (for Harbor image push), then N
#  parallel GitHub Actions runner systemd units sharing a single VM.
# =============================================================================

package_update: true
package_upgrade: false
packages:
  - curl
  - git
  - jq
  - unzip
  - docker.io
  - python3
  - python3-pip
  - python3-venv
  - build-essential

runcmd:
  - systemctl enable --now docker

  # crane for Harbor image push (docker save → crane push)
  - |
    curl -sL https://github.com/google/go-containerregistry/releases/download/v0.20.3/go-containerregistry_Linux_x86_64.tar.gz \
      | tar xz -C /usr/local/bin crane

  # Node.js 20 LTS
  - curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  - apt-get install -y -qq nodejs

  # Dedicated runner user with docker group access
  - useradd -m -s /bin/bash -G docker runner

  # Download the GitHub Actions runner release tarball once
  - |
    RUNNER_VERSION="${runner_version}"
    RUNNER_TAR="actions-runner-linux-x64-$${RUNNER_VERSION}.tar.gz"
    su - runner -c "curl -sL https://github.com/actions/runner/releases/download/v$${RUNNER_VERSION}/$${RUNNER_TAR} -o /tmp/$${RUNNER_TAR}"

  # Configure ${runner_count} parallel runners, each with its own systemd unit
  - |
    set -eu
    RUNNER_VERSION="${runner_version}"
    RUNNER_TAR="actions-runner-linux-x64-$${RUNNER_VERSION}.tar.gz"
    for i in $(seq 1 ${runner_count}); do
      su - runner -c "
        mkdir -p actions-runner-$$i && cd actions-runner-$$i
        tar xz -f /tmp/$${RUNNER_TAR}
        ./config.sh --unattended \
          --url https://github.com/${github_repo} \
          --token ${github_runner_token} \
          --name ${name}-$$i \
          --labels ${runner_labels} \
          --work _work \
          --replace
      "
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
