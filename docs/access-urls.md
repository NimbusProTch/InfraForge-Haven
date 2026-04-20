# iyziops — Access URLs & Credential Fetch Guide

> Public URLs for the live iyziops cluster + the exact commands to
> retrieve each credential from the cluster. **Never commit plaintext
> passwords** — the repo is public. For a local cheat-sheet filled
> with real values, use `docs/credentials-local.md` (gitignored).

---

## 🌐 Ingress URLs (prod)

All behind `*.iyziops.com` (Let's Encrypt wildcard, auto-renewed by
cert-manager v1.20.x). HTTPRoutes attached to the `iyziops-gateway`
Gateway API resource.

| Service | URL | Purpose |
|---|---|---|
| **iyziops UI** | https://iyziops.com | Main platform UI (Next.js) |
| **iyziops API** | https://api.iyziops.com | FastAPI backend |
| **Keycloak** | https://keycloak.iyziops.com | OIDC / SSO |
| **ArgoCD** | https://argocd.iyziops.com | GitOps sync dashboard |
| **Gitea** | https://gitea.iyziops.com | Self-hosted git server |
| **Harbor** | https://harbor.iyziops.com | Container registry |
| **Grafana** | https://grafana.iyziops.com | Observability |
| **MinIO Console** | https://minio.iyziops.com | Object store UI (port 9001) |
| **MinIO S3 API** | https://s3.iyziops.com | Object store S3 endpoint (port 9000) |

Per-tenant app URLs follow `{app-slug}.{tenant-slug}.apps.46.225.42.2.sslip.io` or a custom domain if the tenant configured one.

---

## 🔑 Credential fetch (one-liners)

Prefix every command with:
```bash
KC=infrastructure/environments/prod/kubeconfig
```

### Keycloak (realm: `haven`)
User `admin` — password is a plain env var on the Keycloak Deployment:
```bash
kubectl --kubeconfig=$KC -n keycloak get deployment keycloak \
  -o jsonpath='{.spec.template.spec.containers[0].env}' \
  | python3 -c 'import sys,json; [print(f"{e[\"name\"]}={e.get(\"value\",\"<ref>\")}") for e in json.load(sys.stdin) if "ADMIN" in e.get("name","")]'
```

### ArgoCD
After bootstrap the `argocd-initial-admin-secret` is deleted. The
`argocd-secret` stores a bcrypt hash, not the plaintext. To set a
known password:
```bash
NEW='admin-iyziops-2026'   # or your own
HASH=$(kubectl --kubeconfig=$KC -n argocd exec deploy/argocd-server \
  -- argocd account bcrypt --password "$NEW")
kubectl --kubeconfig=$KC -n argocd patch secret argocd-secret \
  -p "{\"stringData\":{\"admin.password\":\"$HASH\",\"admin.passwordMtime\":\"$(date -u +%FT%TZ)\"}}"
kubectl --kubeconfig=$KC -n argocd rollout restart deploy argocd-server
```
Log in with `admin` + `$NEW`.

### Gitea
User `haven-admin` — plain env var on the Deployment:
```bash
kubectl --kubeconfig=$KC -n gitea-system get deployment gitea -o yaml \
  | grep -E 'GITEA_ADMIN_(USERNAME|PASSWORD)' -A1 | head
```

### Harbor
User `admin`:
```bash
kubectl --kubeconfig=$KC -n harbor-system get secret harbor-core \
  -o jsonpath='{.data.HARBOR_ADMIN_PASSWORD}' | base64 -d; echo
```

### Grafana
```bash
kubectl --kubeconfig=$KC -n monitoring get secret kube-prometheus-stack-grafana \
  -o jsonpath='{.data.admin-password}' | base64 -d; echo
# user = admin
```

### MinIO
```bash
kubectl --kubeconfig=$KC -n minio-system get secret minio-credentials \
  -o json | python3 -c 'import sys,json,base64; d=json.load(sys.stdin)["data"]; print("\n".join(f"{k} = {base64.b64decode(v).decode()}" for k,v in d.items()))'
```

### Postgres (platform DB — shared by API + Keycloak)
```bash
kubectl --kubeconfig=$KC -n haven-system get secret haven-platform-superuser \
  -o jsonpath='{.data.password}' 2>/dev/null | base64 -d; echo
# Fallback: read iyziops-api-secrets DATABASE_URL
kubectl --kubeconfig=$KC -n haven-system get secret iyziops-api-secrets \
  -o jsonpath='{.data.DATABASE_URL}' | base64 -d; echo
```

### iyziops-api service account + external integrations
```bash
kubectl --kubeconfig=$KC -n haven-system get secret iyziops-api-secrets \
  -o json | python3 -c 'import sys,json,base64; d=json.load(sys.stdin)["data"]; [print(f"{k} = {base64.b64decode(v).decode()[:80]}") for k in d for k in [k]]'
```

---

## 🔐 testuser (primary Keycloak login)

Realm: `haven`, username `testuser`, password `test123456`.
After the ET4 pivot the user must carry the `platform-admin` realm
role to see the admin console and `POST /tenants`:

```bash
kubectl --kubeconfig=$KC -n keycloak exec deploy/keycloak -- bash -c '
  /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080 --realm master \
    --user admin --password keycloak-admin-dev-2026
  /opt/keycloak/bin/kcadm.sh add-roles -r haven \
    --uusername=testuser --rolename platform-admin
'
```
Users must re-login so the new role lands in their JWT.

---

## 🧰 Cluster access (operator shell)

```bash
export KUBECONFIG=$(pwd)/infrastructure/environments/prod/kubeconfig
kubectl get nodes
```
Kubeconfig is gitignored — obtain it via `make kubeconfig` (SCPs
from the first master) or copy it from a fellow operator.

---

## ⚠️ Security notes

- All current passwords except Keycloak testuser are **dev defaults**
  (`Harbor12345`, `prom-operator`, `gitea-admin-dev-2026`, etc.).
  Rotate before any real-customer cutover.
- `docs/credentials-local.md` is gitignored — never commit.
- If a credential is ever accidentally committed:
  1. Rotate it immediately in Keycloak / kubectl.
  2. `git filter-repo` or `git filter-branch` the plaintext out.
  3. Force-push (coordinate with the team).
