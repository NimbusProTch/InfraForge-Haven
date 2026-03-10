rke2-cilium:
  k8sServiceHost: "127.0.0.1"
  k8sServicePort: "6443"
  kubeProxyReplacement: true
  operator:
    replicas: ${operator_replicas}
    tolerations:
      - operator: "Exists"
  tolerations:
    - operator: "Exists"
  hubble:
    enabled: ${hubble_enabled}
    relay:
      enabled: ${hubble_enabled}
    ui:
      enabled: ${hubble_enabled}
