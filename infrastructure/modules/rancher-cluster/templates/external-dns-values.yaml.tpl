# External-DNS Helm values (Cloudflare provider)
provider: cloudflare
env:
  - name: CF_API_TOKEN
    value: ${cloudflare_api_token}
domainFilters:
%{ for domain in domain_filters ~}
  - ${domain}
%{ endfor ~}
policy: sync
txtOwnerId: haven-dev
sources:
  - service
  - ingress
  - gateway-httproute
tolerations:
  - operator: "Exists"
resources:
  requests:
    cpu: "50m"
    memory: "64Mi"
  limits:
    memory: "128Mi"
