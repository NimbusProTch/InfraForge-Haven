---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: iyziops-wildcard
  namespace: cert-manager
spec:
  secretName: iyziops-wildcard-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  commonName: "*.${platform_apex_domain}"
  dnsNames:
    - "${platform_apex_domain}"
    - "*.${platform_apex_domain}"
  duration: 2160h
  renewBefore: 360h
  privateKey:
    algorithm: ECDSA
    size: 256
    rotationPolicy: Always
