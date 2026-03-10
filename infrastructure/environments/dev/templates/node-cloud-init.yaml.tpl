#cloud-config
package_update: true
packages:
  - curl

runcmd:
  - |
    echo "[cloud-init] Waiting for Rancher at https://${rancher_ip}..."
    for i in $(seq 1 120); do
      if curl -sk "https://${rancher_ip}/ping" 2>/dev/null | grep -q pong; then
        echo "[cloud-init] Rancher is reachable after $((i * 5)) seconds."
        break
      fi
      if [ "$i" -eq 120 ]; then
        echo "[cloud-init] ERROR: Rancher not reachable after 10 minutes"
        exit 1
      fi
      sleep 5
    done
  - |
    export CATTLE_CA_CHECKSUM=$(curl -sk "https://${rancher_ip}/cacerts" | sha256sum | awk '{print $1}')
    echo "[cloud-init] CA checksum: $${CATTLE_CA_CHECKSUM:0:16}..."
    curl --insecure -fL "https://${rancher_ip}/system-agent-install.sh" | \
      CATTLE_CA_CHECKSUM="$$CATTLE_CA_CHECKSUM" sh -s - \
        --server "https://${rancher_ip}" \
        --label 'cattle.io/os=linux' \
        --token "${registration_token}" \
        ${node_roles}
    echo "[cloud-init] Node registration initiated with roles: ${node_roles}"
