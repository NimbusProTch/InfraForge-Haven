# hetzner-infra

Base Hetzner Cloud resources for an iyziops cluster: SSH key, private network + subnet, **two** load balancers (API LB tofu-managed, ingress LB shell adopted by Hetzner CCM at runtime via annotation), a **NAT box** providing egress for public-IP-less cluster nodes, and a **default `hcloud_network_route`** that pins `0.0.0.0/0` through the NAT box.

## Topology (post Haven 15/15 sprint)

Cluster masters and workers run with `public_net { ipv4_enabled = false; ipv6_enabled = false }` so Haven's `privatenetworking` check passes (Hetzner CCM cannot report an `ExternalIP` that does not exist). They reach the internet via the NAT box. Workers run in `var.worker_location` (distinct from `var.location_primary`) so Hetzner CCM emits two `topology.kubernetes.io/zone` labels and Haven's `infraMultiAZ` check passes.

## What it does not do

- **Does not create cluster servers** — masters and workers live in the environment layer so cloud-init can be rendered with per-node context.
- **Does not attach LB targets** to the API LB — targets need `hcloud_server` IDs and are attached in the environment layer.
- **Does not manage ingress LB services** — the ingress LB is a shell that Hetzner CCM adopts via `load-balancer.hetzner.cloud/name` annotation on the Cilium-generated `cilium-gateway-*` Service. Its `target` and CCM-written labels are in `lifecycle { ignore_changes = ... }`.
- **Does not install a shared public firewall on cluster nodes** — cluster nodes have no public IPv4 so there is nothing to filter. The only public surface is `hcloud_firewall.nat`, which allows operator SSH (22) and ICMP echo on the NAT box alone.

## Inputs

| Name | Type | Required | Description |
|---|---|---|---|
| `cluster_name` | string | yes | Resource name prefix, e.g. `iyziops` |
| `environment` | string | yes | Must be `prod` (single-env model) |
| `ssh_public_key` | string | yes | OpenSSH public key installed on every node |
| `location_primary` | string | yes | Hetzner datacenter for masters + LBs + NAT box (e.g. `fsn1`) |
| `worker_location` | string | yes | Hetzner datacenter for worker nodes, must differ from `location_primary` so CCM emits two distinct `topology.kubernetes.io/zone` labels (Haven `infraMultiAZ`). One of `fsn1` / `nbg1` / `hel1`. |
| `network_zone` | string | yes | Hetzner network zone for the private subnet (e.g. `eu-central`) |
| `network_cidr` | string | yes | Private network CIDR (e.g. `10.10.0.0/16`) |
| `subnet_cidr` | string | yes | Subnet CIDR inside `network_cidr` (e.g. `10.10.1.0/24`) |
| `api_lb_type` | string | yes | Hetzner LB type for API LB (6443). `lb11` / `lb21` / `lb31` |
| `ingress_lb_type` | string | yes | Hetzner LB type for ingress LB (80/443). `lb11` / `lb21` / `lb31` |
| `ingress_lb_location` | string | yes | Ingress LB datacenter location — usually matches `location_primary` |
| `operator_cidrs` | list(string) | yes | Public allow-list for SSH (22) on the NAT bastion. Must not contain `0.0.0.0/0` or `::/0`; validator blocks the literal. Because the NAT box is now the **only** public SSH surface for the cluster, tighten this to operator IPs / VPN CIDRs before production. |

## Outputs

| Name | Purpose |
|---|---|
| `load_balancer_api_id` | API LB ID — used to attach master targets in the env layer |
| `load_balancer_api_ipv4` | API LB public IPv4 — `api.iyziops.com` A record + RKE2 tls-san |
| `load_balancer_api_private_ipv4` | API LB private IPv4 — tls-san for in-cluster kubectl |
| `load_balancer_ingress_id` | Ingress LB ID — CCM adopts this shell LB by name annotation |
| `load_balancer_ingress_name` | Ingress LB literal name — must match `load-balancer.hetzner.cloud/name` annotation on Cilium Gateway Service |
| `load_balancer_ingress_ipv4` | Ingress LB public IPv4 — apex + wildcard DNS A records |
| `network_id` | Private network ID — referenced by inline `network { }` blocks on cluster servers |
| `network_name` | Private network literal name — passed to Hetzner CCM via `HCLOUD_NETWORK` env |
| `network_cidr` | Private network CIDR |
| `subnet_id` | Private subnet ID |
| `subnet_cidr` | Private subnet CIDR — used as Cilium `ipv4NativeRoutingCIDR` if native routing is ever enabled |
| `ssh_key_id` | SSH key ID — referenced by `hcloud_server.ssh_keys` |
| `nat_public_ipv4` | NAT box public IPv4 — the only operator-accessible bastion, used by `make kubeconfig` and `scripts/fetch-kubeconfig.sh` as ProxyJump target |
| `nat_private_ipv4` | NAT box private IPv4 (pinned to last usable host in the subnet) — gateway of the `0.0.0.0/0` network route |
| `network_route_id` | Default network route ID — cluster servers depend on the module so they boot after egress is available |
| `worker_zone` | Hetzner datacenter where worker nodes run — informational; Hetzner CCM auto-applies the matching `topology.kubernetes.io/zone` label |

## Example

```hcl
module "hetzner_infra" {
  source = "../../modules/hetzner-infra"

  cluster_name        = "iyziops"
  environment         = "prod"
  ssh_public_key      = tls_private_key.cluster.public_key_openssh
  location_primary    = "fsn1"
  worker_location     = "nbg1"
  network_zone        = "eu-central"
  network_cidr        = "10.10.0.0/16"
  subnet_cidr         = "10.10.1.0/24"
  api_lb_type         = "lb11"
  ingress_lb_type     = "lb11"
  ingress_lb_location = "fsn1"
  operator_cidrs      = ["203.0.113.7/32"]
}
```
