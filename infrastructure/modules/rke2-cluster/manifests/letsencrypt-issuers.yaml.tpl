---
# =============================================================================
#  iyziops — Let's Encrypt ClusterIssuers
# =============================================================================
#  DNS-01 via Cloudflare only. HTTP-01 is intentionally NOT provisioned
#  because Cilium 1.16+ ships no classic Ingress controller under class
#  "cilium" — certificate challenges would stall. Platform subdomains are
#  covered by the wildcard certificate against *.iyziops.com. Tenant custom
#  domains will get their own HTTP-01 issuer wired through a Gateway API
#  HTTPRoute in a later sprint.
# =============================================================================

apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-staging
spec:
  acme:
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    email: ${letsencrypt_email}
    privateKeySecretRef:
      name: letsencrypt-staging-key
    solvers:
      - dns01:
          cloudflare:
            apiTokenSecretRef:
              name: cloudflare-api-token
              key: api-token
---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ${letsencrypt_email}
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
      - dns01:
          cloudflare:
            apiTokenSecretRef:
              name: cloudflare-api-token
              key: api-token
