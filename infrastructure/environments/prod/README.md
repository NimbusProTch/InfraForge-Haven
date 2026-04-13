# prod environment

Single iyziops cluster on Hetzner Cloud in `fsn1`. Six nodes (3 masters + 3 workers), Cilium CNI with Gateway API, Longhorn storage, cert-manager with Cloudflare DNS-01 wildcard, ArgoCD HA bootstrapped via RKE2 Helm Controller.

## Files

| File | Purpose |
|---|---|
| `backend.tf` | Hetzner Object Storage S3-compatible remote state (`iyziops-tfstate-prod`) |
| `providers.tf` | `hcloud` + `cloudflare` only |
| `versions.tf` | Provider pins — no `helm` / `kubernetes` / `ssh` |
| `variables.tf` | All inputs (no defaults for env-specific values, validations everywhere) |
| `hetzner.tf` | SSH key, cluster token, base infra module, master/worker servers, LB targets |
| `rke2.tf` | `module.rke2_cluster` (renders cloud-init) + `module.rke2_install` (readiness probe) |
| `dns.tf` | `module.dns` — Cloudflare apex + wildcard A records |
| `outputs.tf` | LB IP, master/worker IPs, ArgoCD URL, cluster readiness signal |
| `prod.auto.tfvars` | **Non-sensitive values — git-tracked.** Node counts, Helm versions, Hetzner region, CIDRs |
| `README.md` | This file |

Sensitive values (`hcloud_token`, `cloudflare_api_token`, `letsencrypt_email`, `github_ssh_deploy_key_private`, `argocd_admin_password_bcrypt`, `etcd_s3_*`) come from the macOS Keychain via the `iyziops-env` shell function in `~/.zshrc` — they are **never** written to disk or committed.

## Bootstrap

```bash
# 1. Keychain credentials (run once per machine)
./scripts/bootstrap-iyziops.sh

# 2. Load env vars into the current shell
iyziops-env

# 3. Replace the placeholder operator_cidrs in prod.auto.tfvars
#    with your real VPN / office egress CIDR before proceeding.
$EDITOR infrastructure/environments/prod/prod.auto.tfvars

# 4. Initialise remote backend
cd infrastructure/environments/prod
tofu init

# 5. Plan — review what will be created
tofu plan -out=../../../logs/tofu-plan-prod-$(date +%Y%m%d%H%M).tfplan

# 6. Apply — DO NOT skip user review between plan and apply
tofu apply ../../../logs/tofu-plan-prod-$(date +%Y%m%d%H%M).tfplan
```

## Post-apply verification

```bash
# Kubeconfig (SCP from first master)
make kubeconfig
export KUBECONFIG=/tmp/iyziops-prod-kubeconfig

# Cluster
kubectl get nodes                                   # 6 Ready
kubectl get pods -A | grep -v Running | grep -v Completed   # empty
kubectl get helmchart -A                             # longhorn, cert-manager, argocd, rke2-cilium (HelmChartConfig)
kubectl get clusterissuer                            # letsencrypt-staging, letsencrypt-prod
kubectl get certificate -n cert-manager iyziops-wildcard   # Ready=True

# ArgoCD
kubectl get application -n argocd iyziops-root       # Synced, Healthy

# HTTPS
curl -sI https://argocd.iyziops.com/                 # 200 with Let's Encrypt cert
```

## Destroy

```bash
tofu destroy -auto-approve
```

Expected: single run, zero orphans. The destroy order is linear because no provider chains through the Kubernetes API — when the VMs die, the in-cluster Helm Controller dies with them and nothing in tofu state still expects the cluster to exist.

## Gotchas

- **Remote state lock**: `use_lockfile = true` in `backend.tf` is commented out. Enable after upgrading to OpenTofu 1.10+.
- **Replace operator_cidrs**: The placeholder `203.0.113.0/24` is RFC 5737 TEST-NET-3; it will reject every SSH attempt until you replace it.
- **First apply takes ~30-45 min**: VM create (5 min) + cloud-init (10-15 min) + Helm Controller applies (10-15 min) + ArgoCD root sync (5 min).
- **Cloudflare rate limit on first apply**: The wildcard cert issuance uses Let's Encrypt prod. If the CN already has a staging cert, delete it first, or issuance may block on rate limits.
- **logs/ is gitignored**: Plan files go to `logs/`, deleted after task completion per `.claude/rules/logs-directory.md`.
