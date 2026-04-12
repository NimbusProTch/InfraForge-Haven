# dns

Cloudflare DNS for an iyziops cluster — apex + wildcard A records pointing at the Hetzner LB.

## Records created

| Record | Type | Target | Proxied | Purpose |
|---|---|---|---|---|
| `iyziops.com` | A | `lb_ip` | no | UI + apex catchall |
| `*.iyziops.com` | A | `lb_ip` | no | every platform + tenant subdomain |

Proxy mode is deliberately off so Let's Encrypt HTTP-01 challenges work and so TLS terminates in Cilium Envoy (not Cloudflare).

## Inputs

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `zone_name` | string | yes | — | Cloudflare zone apex (e.g. `iyziops.com`) |
| `lb_ip` | string | yes | — | Hetzner LB public IPv4 |
| `ttl` | number | no | `1` | `1` means Cloudflare auto |
| `comment` | string | no | `"Managed by OpenTofu — iyziops platform"` | per-record comment |

## Outputs

| Name | Purpose |
|---|---|
| `zone_id` | used by cert-manager DNS-01 solver |
| `apex_record_id`, `wildcard_record_id` | stable references for import/drift |
| `apex_fqdn`, `wildcard_fqdn` | FQDN strings for logging/outputs |

## Example

```hcl
module "dns" {
  source = "../../modules/dns"

  zone_name = "iyziops.com"
  lb_ip     = module.hetzner_infra.load_balancer_ipv4
}
```

## Notes

- The Cloudflare API token must have `Zone:Read` + `DNS:Edit` scoped to the target zone. It is loaded from Keychain via `TF_VAR_cloudflare_api_token`.
- The same token is also reused by cert-manager inside the cluster for DNS-01 challenges (wildcard cert for `*.iyziops.com`).
