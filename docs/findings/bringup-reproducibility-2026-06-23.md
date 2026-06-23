# Bring-up reproducibility findings — 2026-06-23

Live bring-up + bootstrap session. Goal was "demo-ready in one command". This
documents, honestly, what is PROVEN working and what blocks the goal. No fake-OK:
demo-ready is NOT reached — the app layer is not yet reproducible from a fresh
`tofu apply`.

## PROVEN working live this session
- **`tofu apply` → 6 nodes Ready** (rc=0, ~3 min), Cilium/CCM up, cert/gateway/ArgoCD converge to ~15/21 apps. C14 destroy-safety + cloud-init 32KB fixes held.
- **Vault bootstrap end-to-end** (`scripts/bootstrap.sh` `bootstrap_vault`):
  init → unseal → kv-v2 → kubernetes auth + `platform-eso-read` policy + `external-secrets` role (audience `vault`) → seed `kv/platform/iyziops-api/*` → pre-seed K8s Secret → **ClusterSecretStore Valid/Ready**, **ExternalSecret SecretSynced**, **K8s Secret = 9 keys**, **external-secrets-config Healthy**.
- **Clean destroy** (C14): single run, 0 orphans.

## Blockers to demo-ready (the real remaining work — app-layer reproducibility)
The app layer was hand-recovered in past overnight sprints and is NOT reproducible
on a fresh cluster. Each item is a code/GitOps task (do it cluster-DOWN, free; then
verify with one clean bring-up):

1. **Vault crashloop + no auto-unseal (PROVEN bug).** Helm liveness probe lacks
   `sealedcode` → a sealed pod (state after every restart) is killed → CrashLoopBackOff.
   Fix in git: `platform-helm.yaml` vault values → liveness `path` +=
   `&sealedcode=204&uninitcode=204`. AND add real auto-unseal (a sidecar/CronJob that
   runs `vault operator unseal` from the `vault-init` Secret on restart) — without it,
   ESO breaks after any Vault restart. (Hetzner has no KMS → K8s-secret unseal loop.)
2. **No platform Postgres in GitOps.** iyziops-api needs a DB; the manifest references
   a dev `iyziops-db` Deployment (emptyDir, on worker-0) that is NOT in the ArgoCD apps.
   Add a reproducible Postgres (CNPG cluster or a clean Deployment) + wire `DATABASE_URL`.
3. **Images not reproducible.** `iyziops-api`/`ui` deployments pin
   `harbor.iyziops.com/library/...@sha256:4a8af68b...` with `imagePullPolicy: IfNotPresent`
   — that digest lived in the OLD (destroyed) Harbor; the fresh Harbor is empty →
   ImagePullBackOff. Need: a build+push pipeline that pushes to the fresh cluster's
   Harbor + reconciles the manifest digest/tag on bring-up (CI dispatch, or a bootstrap
   build step). Depends on Harbor being up + reachable + authed.
4. **Deployment recovery-hacks.** `iyziops-api` deployment is pinned to `worker-0`
   (`nodeSelector`), references a temp in-cluster registry, and assumes pre-pulled
   images via `ctr`. De-hack to a portable form once images are reproducible.
5. **Keycloak realm import not automated.** `keycloak/haven-realm.json` must be imported
   (a Job) for UI login. (Keycloak IS deployed via platform-helm.)
6. **Deploy GitOps seam broken** (see `memory/project_deploy_seam_broken_20260623.md`).
   Demo-ready workaround: set `GITOPS_REPO_URL=""` in the iyziops-api ConfigMap →
   pipeline uses direct-K8s deploy (`pipeline.py:214`). GitOps redesign is post-demo.
7. **LB_IP hardcoded** (old `46.225.42.2`) in iyziops-api/ui ConfigMaps; on a fresh
   cluster it must be `tofu output load_balancer_ingress_ipv4`. Patch via bootstrap +
   ArgoCD `ignoreDifferences` (selfHeal would revert a bare kubectl patch).

## Honest assessment
"`tofu apply` → 30 min → demo-ready" is NOT close. The infra lifecycle (apply/destroy)
and the Vault data-plane are solid. The gap is **making the app layer reproducible in
git** (items 1–7) — that is a real, multi-day project, not a single bootstrap script.
Recommended: do items 1–7 as code (cluster-down, free), each its own PR, then verify
with ONE clean bring-up. Stub'd in `scripts/bootstrap.sh`.
