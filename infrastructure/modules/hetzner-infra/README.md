# hetzner-infra

Base Hetzner Cloud resources for an iyziops cluster: SSH key, private network + subnet, public firewall, and a single load balancer that fronts the Kubernetes API plus the Cilium Gateway.

## What it does not do

- **Does not create servers** (masters and workers live in the environment layer so cloud-init can be rendered with per-node context).
- **Does not attach LB targets** (same reason — targets need `hcloud_server` IDs).
- **Does not open private-network ports** — Hetzner firewalls only filter public ingress, so kubelet, VXLAN, etcd, and the RKE2 supervisor on 9345 all work freely over the private network without firewall rules.

## Inputs

| Name | Type | Required | Description |
|---|---|---|---|
| `cluster_name` | string | yes | Resource name prefix, e.g. `iyziops` |
| `environment` | string | yes | Must be `prod` (single-env model) |
| `ssh_public_key` | string | yes | OpenSSH public key installed on every node |
| `location_primary` | string | yes | Hetzner datacenter code (e.g. `fsn1`, `nbg1`) |
| `network_zone` | string | yes | Hetzner network zone (e.g. `eu-central`) |
| `network_cidr` | string | yes | Private network CIDR |
| `subnet_cidr` | string | yes | Subnet CIDR inside `network_cidr` |
| `lb_type` | string | yes | `lb11`, `lb21`, or `lb31` |
| `operator_cidrs` | list(string) | yes | Public allow-list for SSH + kubectl — must not contain `0.0.0.0/0` |
| `gateway_http_nodeport` | number | no (30080) | NodePort the Cilium Gateway exposes for HTTP |
| `gateway_https_nodeport` | number | no (30443) | NodePort the Cilium Gateway exposes for HTTPS |

## Outputs

| Name | Purpose |
|---|---|
| `load_balancer_id` | attach master + worker targets in the env layer |
| `load_balancer_ipv4` | DNS A-record target + RKE2 tls-san |
| `load_balancer_private_ipv4` | in-cluster tls-san and kubectl fallback |
| `network_id`, `subnet_id` | attach server networks |
| `network_cidr`, `subnet_cidr` | Cilium `ipv4NativeRoutingCIDR` |
| `ssh_key_id`, `firewall_id` | reference on `hcloud_server` |

## Example

```hcl
module "hetzner_infra" {
  source = "../../modules/hetzner-infra"

  cluster_name     = "iyziops"
  environment      = "prod"
  ssh_public_key   = tls_private_key.cluster.public_key_openssh
  location_primary = "fsn1"
  network_zone     = "eu-central"
  network_cidr     = "10.10.0.0/16"
  subnet_cidr      = "10.10.1.0/24"
  lb_type          = "lb11"
  operator_cidrs   = ["203.0.113.0/24"]
}
```
