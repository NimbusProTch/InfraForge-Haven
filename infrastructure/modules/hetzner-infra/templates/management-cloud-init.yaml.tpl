#cloud-config
# Production-grade Rancher management node
# K3s + Helm + cert-manager + Rancher (not Docker)
package_update: true
packages:
  - curl
  - jq

runcmd:
  # Detect public IP (Hetzner metadata API)
  - |
    echo "[cloud-init] Detecting public IP..."
    PUBLIC_IP=$(curl -s http://169.254.169.254/hetzner/v1/metadata/public-ipv4)
    if [ -z "$$PUBLIC_IP" ]; then
      PUBLIC_IP=$(curl -s ifconfig.me)
    fi
    echo "$$PUBLIC_IP" > /root/.management_ip
    echo "[cloud-init] Public IP: $$PUBLIC_IP"
  # Install K3s (lightweight K8s for management plane)
  - |
    PUBLIC_IP=$(cat /root/.management_ip)
    echo "[cloud-init] Installing K3s ${k3s_version}..."
    curl -sfL https://get.k3s.io | \
      INSTALL_K3S_VERSION="${k3s_version}" \
      sh -s - server \
        --tls-san="$$PUBLIC_IP" \
        --write-kubeconfig-mode=644
  # Wait for K3s to be ready
  - |
    echo "[cloud-init] Waiting for K3s..."
    export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
    for i in $(seq 1 60); do
      if kubectl get nodes 2>/dev/null | grep -q " Ready"; then
        echo "[cloud-init] K3s is ready after $$((i * 5)) seconds."
        break
      fi
      if [ "$$i" -eq 60 ]; then
        echo "[cloud-init] ERROR: K3s not ready after 5 minutes"
        exit 1
      fi
      sleep 5
    done
  # Install Helm
  - |
    echo "[cloud-init] Installing Helm..."
    curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
  # Add Helm repos
  - |
    export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
    helm repo add jetstack https://charts.jetstack.io
    helm repo add rancher-stable https://releases.rancher.com/server-charts/stable
    helm repo update
  # Install cert-manager (Rancher dependency)
  - |
    echo "[cloud-init] Installing cert-manager ${cert_manager_version}..."
    export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
    kubectl create namespace cert-manager 2>/dev/null || true
    helm install cert-manager jetstack/cert-manager \
      --namespace cert-manager \
      --version ${cert_manager_version} \
      --set crds.enabled=true \
      --wait --timeout=5m
  # Wait for cert-manager webhook
  - |
    export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
    echo "[cloud-init] Waiting for cert-manager webhook..."
    kubectl wait --for=condition=Available deployment/cert-manager-webhook \
      -n cert-manager --timeout=120s
  # Install Rancher via Helm
  - |
    PUBLIC_IP=$(cat /root/.management_ip)
    echo "[cloud-init] Installing Rancher ${rancher_version} (chart ${rancher_chart_version})..."
    export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
    kubectl create namespace cattle-system 2>/dev/null || true
    helm install rancher rancher-stable/rancher \
      --namespace cattle-system \
      --version ${rancher_chart_version} \
      --set hostname="$$PUBLIC_IP" \
      --set bootstrapPassword=${bootstrap_password} \
      --set replicas=1 \
      --set ingress.tls.source=rancher \
      --wait --timeout=10m
    echo "[cloud-init] Rancher installation complete!"
