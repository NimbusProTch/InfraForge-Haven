#cloud-config
package_update: true
packages:
  - curl
  - jq

runcmd:
  - curl -fsSL https://get.docker.com | sh
  - |
    docker run -d \
      --name rancher \
      --privileged \
      --restart=unless-stopped \
      -p 80:80 \
      -p 443:443 \
      -e CATTLE_BOOTSTRAP_PASSWORD=${bootstrap_password} \
      rancher/rancher:${rancher_version}
