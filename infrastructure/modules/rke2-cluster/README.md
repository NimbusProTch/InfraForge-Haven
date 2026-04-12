# rke2-cluster

Renders the cloud-init strings for RKE2 master and worker nodes. Does **not** create any Hetzner resource — it only produces three strings that the environment layer attaches to `hcloud_server.user_data`.

## What it does

- Renders every Helm Controller manifest from `templates/manifests/` as a local.
- Base64-encodes each manifest and drops it into the first master's cloud-init `write_files` block.
- Installs: Cilium (HelmChartConfig override), Longhorn, cert-manager, Cloudflare API token Secret, two Let's Encrypt ClusterIssuers (DNS-01 only), wildcard `*.iyziops.com` Certificate, ArgoCD, two AppProjects, repo Secret with SSH deploy key, and the root GitOps Application.
- **Does not install Hetzner CCM** in this phase — we run the tofu-managed LB for the Kubernetes API plus the Cilium Gateway NodePort, so CCM's LoadBalancer reconciler would conflict. Nodes do not carry the `cloud-provider.kubernetes.io/uninitialized` taint because RKE2 is configured without `--cloud-provider=external`. CCM can be added later as a separate ArgoCD Application once tenant-scoped `Service` type LoadBalancers are required.
- Builds three cloud-init outputs:
  1. **first_master_cloud_init** — `cluster-init: true`, writes all manifests under `/var/lib/rancher/rke2/server/manifests/`. When `rke2-server` starts, the in-cluster Helm Controller applies them in order.
  2. **joining_master_cloud_init** — joins via `server: https://<first-master-private-ip>:9345`, no manifests (etcd replicates).
  3. **worker_cloud_init** — agent join, no manifests, no apiserver flags.

## What it does NOT do

- Create `hcloud_server` / `hcloud_load_balancer` / networks — that's the environment layer's job.
- Talk to the Kubernetes API (no `kubernetes`, `helm`, `ssh_resource` providers).
- Manage kubeconfig files (operators use `make kubeconfig`).

## The Helm Controller pattern

RKE2 ships a built-in Helm Controller that watches `helm.cattle.io/v1` `HelmChart` and `HelmChartConfig` CRs. If a manifest is placed under `/var/lib/rancher/rke2/server/manifests/*.yaml` **before** `rke2-server` starts, it is picked up and applied automatically once the API is up. That is why this module only produces cloud-init — no tofu-side provider is needed to install operators, CRDs, or cluster-scoped bootstrap objects.

Install order is controlled by the Helm Controller itself (it just keeps retrying until every dependency resolves), so we do not need explicit dependency ordering beyond what Kubernetes' CRD/namespace/finalizer machinery provides.

## Inputs (abridged — see `variables.tf` for the full list)

| File | Variables |
|---|---|
| `variables.tf` | `cluster_name`, `kubernetes_version`, `cluster_token`, `first_master_private_ip`, `lb_ip`, `lb_private_ip`, `ipv4_native_routing_cidr`, `enable_hubble`, `cilium_operator_replicas`, `disable_kube_proxy`, `enable_cis_profile`, `keycloak_oidc_issuer_url`, `keycloak_oidc_client_id` |
| `variables-etcd.tf` | `etcd_snapshot_schedule`, `etcd_snapshot_retention`, `etcd_s3_enabled`, `etcd_s3_endpoint`, `etcd_s3_bucket`, `etcd_s3_region`, `etcd_s3_access_key`, `etcd_s3_secret_key` |
| `variables-platform.tf` | `platform_apex_domain`, `letsencrypt_email`, `cloudflare_api_token`, `cert_manager_version`, `longhorn_version`, `longhorn_replica_count`, `argocd_version`, `argocd_server_replicas`, `argocd_ha_enabled`, `argocd_admin_password_bcrypt`, `gitops_repo_url`, `gitops_target_revision`, `github_ssh_deploy_key_private` |

## Outputs

| Name | Sensitive | Purpose |
|---|---|---|
| `first_master_cloud_init` | yes | attach to the bootstrap master `hcloud_server.user_data` |
| `joining_master_cloud_init` | yes | attach to every other master |
| `worker_cloud_init` | yes | attach to every worker |

## Files

```
main.tf                                    # local renders + three cloud-init assemblies
variables.tf                               # identity, network, Cilium, OIDC
variables-etcd.tf                          # etcd snapshot + S3 upload
variables-platform.tf                      # Helm chart versions + ArgoCD + GitOps
outputs.tf                                 # three cloud-init strings
versions.tf                                # required_version
README.md                                  # this file

templates/                                 # cloud-init (VM user_data)
├── master-cloud-init.yaml.tpl             # first master: RKE2 config + all manifests
├── joining-master-cloud-init.yaml.tpl     # other masters: join + no manifests
└── worker-cloud-init.yaml.tpl             # agents

manifests/                                 # Helm Controller Kubernetes manifests
├── rke2-cilium-config.yaml.tpl            # HelmChartConfig (Cilium feature toggles)
├── longhorn.yaml.tpl                      # Longhorn storage
├── cert-manager.yaml.tpl                  # cert-manager + Gateway API integration
├── cloudflare-token-secret.yaml.tpl       # Cloudflare API token secret for DNS-01
├── letsencrypt-issuers.yaml.tpl           # 2 ClusterIssuers (DNS-01 only: staging + prod)
├── iyziops-wildcard-cert.yaml.tpl         # Certificate for apex + *.iyziops.com
├── argocd.yaml.tpl                        # ArgoCD Helm chart
├── argocd-projects.yaml.tpl               # iyziops-platform + iyziops-tenants AppProjects
├── argocd-repo-secret.yaml.tpl            # GitHub SSH deploy key (private repo auth)
└── argocd-root-app.yaml.tpl               # Application pointing at platform/argocd/appsets/
```
