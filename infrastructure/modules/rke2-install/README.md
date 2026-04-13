# rke2-install

Blocks `tofu apply` until the Kubernetes API becomes reachable through the Hetzner **API** LB.

## Why this exists

Without a readiness barrier, the environment layer finishes `tofu apply` as soon as the last Hetzner resource is created — which may be minutes before `rke2-server` on the first master finishes installing, Cilium comes up, and the API answers. Downstream automation (e.g. `make kubeconfig`, smoke tests) then hits a cluster that is not there yet.

This module solves that with a single `data "http"` resource pointing at `https://<lb_ip>:6443/livez`, using OpenTofu 1.6+ native retry. A successful status code (`200`) or `401` (auth required = API up) means the cluster is ready.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `lb_ip` | string | — | Hetzner **API** LB public IPv4 (6443) — the probe target |
| `max_attempts` | number | `180` | Retry attempts before failing — at 10 s each that is ~30 min total |
| `max_delay_ms` | number | `10000` | Max delay between retries in ms |

## Outputs

| Name | Purpose |
|---|---|
| `cluster_ready` | `true` once the API answered with 200 or 401 |
| `probe_status_code` | raw status code, useful for debugging |

## Example

```hcl
module "rke2_install" {
  source = "../../modules/rke2-install"

  lb_ip = module.hetzner_infra.load_balancer_api_ipv4

  depends_on = [
    hcloud_server.master,
    hcloud_load_balancer_target.api_master,
  ]
}
```

## Why no `helm_release` or `kubernetes_manifest`?

Everything that would traditionally be installed via `helm_release` is installed by RKE2's in-cluster Helm Controller (see `rke2-cluster` module). By the time this probe succeeds, ArgoCD already exists and the GitOps root Application is reconciling the rest of the platform. Tofu's only remaining job is to block until the API is reachable so that downstream automation can proceed.
