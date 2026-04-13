# hetzner-infra

Base Hetzner Cloud resources for an iyziops cluster: SSH key, private network + subnet, public firewall, and **two** load balancers — one for the Kubernetes API (tofu-managed) and one shell LB for the Cilium Gateway (adopted by Hetzner CCM at runtime via annotation).

## What it does not do

- **Does not create servers** — masters and workers live in the environment layer so cloud-init can be rendered with per-node context.
- **Does not attach LB targets** to the API LB — targets need `hcloud_server` IDs and are attached in the environment layer.
- **Does not manage ingress LB services** — the ingress LB is a shell that Hetzner CCM adopts via `load-balancer.hetzner.cloud/name` annotation on the Cilium-generated `cilium-gateway-*` Service. Its `target` and CCM-written labels are in `lifecycle { ignore_changes = ... }`.
- **Does not open private-network ports** — Hetzner firewalls only filter public ingress, so kubelet, VXLAN, etcd, and the RKE2 supervisor on 9345 all work freely over the private network without firewall rules.

## Inputs

| Name | Type | Required | Description |
|---|---|---|---|
| `cluster_name` | string | yes | Resource name prefix, e.g. `iyziops` |
| `environment` | string | yes | Must be `prod` (single-env model) |
| `ssh_public_key` | string | yes | OpenSSH public key installed on every node |
| `location_primary` | string | yes | Hetzner datacenter code for masters/workers (e.g. `fsn1`, `nbg1`, `hel1`) |
| `network_zone` | string | yes | Hetzner network zone for the private subnet (e.g. `eu-central`) |
| `network_cidr` | string | yes | Private network CIDR (e.g. `10.10.0.0/16`) |
| `subnet_cidr` | string | yes | Subnet CIDR inside `network_cidr` (e.g. `10.10.1.0/24`) |
| `api_lb_type` | string | yes | Hetzner LB type for API LB (6443). `lb11` / `lb21` / `lb31` |
| `ingress_lb_type` | string | yes | Hetzner LB type for ingress LB (80/443). `lb11` / `lb21` / `lb31` |
| `ingress_lb_location` | string | yes | Ingress LB datacenter location — usually matches `location_primary` |
| `operator_cidrs` | list(string) | yes | Public allow-list for SSH (22) and direct kubectl (6443). Must not contain `0.0.0.0/0` or `::/0` |

## Outputs

| Name | Purpose |
|---|---|
| `load_balancer_api_id` | API LB ID — used to attach master targets in the env layer |
| `load_balancer_api_ipv4` | API LB public IPv4 — `api.iyziops.com` A record + RKE2 tls-san |
| `load_balancer_api_private_ipv4` | API LB private IPv4 — tls-san for in-cluster kubectl |
| `load_balancer_ingress_id` | Ingress LB ID — CCM adopts this shell LB by name annotation |
| `load_balancer_ingress_name` | Ingress LB literal name — must match `load-balancer.hetzner.cloud/name` annotation on Cilium Gateway Service |
| `load_balancer_ingress_ipv4` | Ingress LB public IPv4 — apex + wildcard DNS A records |
| `network_id` | Private network ID — referenced by `hcloud_server_network` |
| `network_name` | Private network literal name — passed to Hetzner CCM via `HCLOUD_NETWORK` env |
| `network_cidr` | Private network CIDR |
| `subnet_id` | Private subnet ID |
| `subnet_cidr` | Private subnet CIDR — used as Cilium `ipv4NativeRoutingCIDR` if native routing is ever enabled |
| `ssh_key_id` | SSH key ID — referenced by `hcloud_server.ssh_keys` |
| `firewall_id` | Firewall ID — referenced by `hcloud_server.firewall_ids` |

## Example

```hcl
module "hetzner_infra" {
  source = "../../modules/hetzner-infra"

  cluster_name        = "iyziops"
  environment         = "prod"
  ssh_public_key      = tls_private_key.cluster.public_key_openssh
  location_primary    = "fsn1"
  network_zone        = "eu-central"
  network_cidr        = "10.10.0.0/16"
  subnet_cidr         = "10.10.1.0/24"
  api_lb_type         = "lb11"
  ingress_lb_type     = "lb11"
  ingress_lb_location = "fsn1"
  operator_cidrs      = ["203.0.113.0/24"]
}
```
