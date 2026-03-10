# Cert-Manager Helm values (Haven Check #12: Auto HTTPS)
installCRDs: true
tolerations:
  - operator: "Exists"
webhook:
  tolerations:
    - operator: "Exists"
cainjector:
  tolerations:
    - operator: "Exists"
