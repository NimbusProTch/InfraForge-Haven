# dns

Cloudflare DNS for an iyziops cluster. Creates three records pointing at the two Hetzner LBs — apex (`iyziops.com`) and wildcard (`*.iyziops.com`) both point at the **ingress LB** (adopted by Hetzner CCM via annotation), and the `k8s.iyziops.com` record points at the **API LB** (tofu-managed, for direct kubectl access).

## Records created

| Record | Type | Target | Proxied | Purpose |
|---|---|---|---|---|
| `iyziops.com` | A | `ingress_lb_ip` | no | UI + apex catchall |
| `*.iyziops.com` | A | `ingress_lb_ip` | no | every platform + tenant subdomain |
| `k8s.iyziops.com` | A | `api_lb_ip` | no | direct kubectl access (bypasses ingress) |

Proxy mode is deliberately off so Let's Encrypt DNS-01 challenges work and so TLS terminates in Cilium Envoy (not Cloudflare).

## Inputs

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `zone_name` | string | yes | — | Cloudflare zone apex (e.g. `iyziops.com`) |
| `ingress_lb_ip` | string | yes | — | Hetzner ingress LB public IPv4 — CCM-adopted, carries 80/443 |
| `api_lb_ip` | string | yes | — | Hetzner API LB public IPv4 — 6443, kubectl |
| `ttl` | number | no | `1` | `1` means Cloudflare auto |
| `comment` | string | no | `"Managed by OpenTofu — iyziops platform"` | per-record comment |

## Outputs

| Name | Purpose |
|---|---|
| `zone_id` | used by cert-manager DNS-01 solver |
| `apex_record_id`, `wildcard_record_id`, `k8s_record_id` | stable references for import/drift |
| `apex_fqdn`, `wildcard_fqdn`, `k8s_fqdn` | FQDN strings for logging/outputs |

## Example

```hcl
module "dns" {
  source = "../../modules/dns"

  zone_name     = "iyziops.com"
  ingress_lb_ip = module.hetzner_infra.load_balancer_ingress_ipv4
  api_lb_ip     = module.hetzner_infra.load_balancer_api_ipv4
}
```

## Notes

- The Cloudflare API token must have `Zone:Read` + `DNS:Edit` scoped to the target zone. It is loaded from the macOS Keychain via `TF_VAR_cloudflare_api_token`.
- The same token is reused by cert-manager inside the cluster for DNS-01 challenges (wildcard cert for `*.iyziops.com`).
- **Historical note**: cert-manager v1.17.0 had a Cloudflare DNS-01 cleanup bug (empty zone ID in DELETE calls, error 7003) caused by a Cloudflare API change in Feb 2025. Fixed in cert-manager v1.17.1+ via [PR #7549](https://github.com/cert-manager/cert-manager/pull/7549). Token permissions are NOT related to this bug — the fix is purely in cert-manager code. We run v1.20.2+ which contains the fix.
