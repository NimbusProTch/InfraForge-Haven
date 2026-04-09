# Sprint H1c (P5) — `haven-api` ServiceAccount RBAC Analysis

> **Status**: DRAFT — research + proposed manifest changes. **NO `kubectl apply` performed.** Morning operator must verify and apply manually.

## TL;DR — what the H0 audit found

Two `ClusterRoleBinding`s exist on the dev cluster targeting the `haven-api` ServiceAccount:

```text
$ kubectl get clusterrolebindings | grep haven-api
haven-api          → ClusterRole haven-api          ✅ SCOPED (in GitOps manifests)
haven-api-admin    → ClusterRole cluster-admin      ❌ ROGUE (manual apply, not in git)
```

The `haven-api-admin` binding is **not** in `platform/manifests/haven-api/`. Someone applied it manually as a quick fix and it's been live ever since. **A pod compromise → cluster-admin token → full cluster takeover.**

The architect H0 round-1 review specifically flagged this:

> "**CRITICAL** — `api/app/routers/haven-api ServiceAccount = cluster-admin`. Bir pod compromise → tüm cluster ele geçirilir. Production-grade multi-tenant SaaS için kabul edilemez."

This document is the H1c work to **(a)** verify the existing scoped `haven-api` ClusterRole covers everything haven-api actually needs, **(b)** add anything missing, **(c)** prepare a clean removal of the rogue `haven-api-admin` binding.

---

## Step 1 — inventory: which K8s API verbs does haven-api actually use?

Captured via grep over `api/app/`:

```bash
grep -rE "k8s\.(core_v1|apps_v1|batch_v1|rbac_v1|networking_v1|autoscaling|custom_objects)\." api/app/ \
  | grep -oE "k8s\.[a-z_0-9]+\.[a-z_0-9]+" \
  | sort -u
```

**41 distinct K8s client method calls** + custom_objects against **6 CRD API groups**.

### core_v1 (namespaces, services, pods, secrets, configmaps, events, PVCs, serviceaccounts)

| Method | Verb | Resource |
|---|---|---|
| `create_namespace`, `delete_namespace` | create, delete | namespaces |
| `create_namespaced_resource_quota`, `replace_namespaced_resource_quota` | create, **update** | resourcequotas |
| `create_namespaced_limit_range`, `replace_namespaced_limit_range` | create, **update** | limitranges |
| `create_namespaced_secret`, `read_namespaced_secret`, `replace_namespaced_secret`, `delete_namespaced_secret` | create, get, update, delete | secrets |
| `create_namespaced_service`, `read_namespaced_service`, `patch_namespaced_service`, `delete_namespaced_service` | create, get, patch, delete | services |
| `read_namespaced_pod`, `read_namespaced_pod_log`, `list_namespaced_pod` | get, list | pods, pods/log |
| `list_namespaced_event` | list | events |
| `create_namespaced_persistent_volume_claim`, `read_namespaced_persistent_volume_claim`, `delete_namespaced_persistent_volume_claim` | create, get, delete | persistentvolumeclaims |

### apps_v1 (deployments)

| Method | Verb | Resource |
|---|---|---|
| `create_namespaced_deployment`, `read_namespaced_deployment`, `read_namespaced_deployment_status`, `patch_namespaced_deployment`, `delete_namespaced_deployment` | create, get, patch, delete | deployments |
| `patch_namespaced_deployment_scale` | patch | deployments/scale |

### batch_v1 (jobs, cronjobs)

| Method | Verb | Resource |
|---|---|---|
| `create_namespaced_job`, `read_namespaced_job_status` | create, get | jobs |
| `create_namespaced_cron_job`, `read_namespaced_cron_job`, `patch_namespaced_cron_job`, `delete_namespaced_cron_job` | create, get, patch, delete | cronjobs |

### rbac_v1 (tenant role provisioning)

| Method | Verb | Resource |
|---|---|---|
| `create_namespaced_role` | create | roles |
| `create_namespaced_role_binding` | create | rolebindings |

(escalate + bind verbs needed because haven-api creates Role/RoleBinding granting permissions to tenant admins)

### custom_objects (CRD groups)

| API group | Resources used | From file |
|---|---|---|
| `argoproj.io` | applications, applicationsets | `services/argocd_service.py`, `services/tenant_service.py` |
| `cilium.io` | ciliumnetworkpolicies | `services/tenant_service.py` (default-deny CNP per tenant ns) |
| **`everest.percona.com`** ⚠️ | databaseclusters, databaseclusterbackups, databaseclusterrestores, databaseclusterbackupschedules | `services/everest_client.py`, `services/managed_service.py`, `services/backup_service.py` |
| `postgresql.cnpg.io` | clusters, backups, scheduledbackups | `services/managed_service.py`, `services/backup_service.py` |
| `rabbitmq.com` | rabbitmqclusters | `services/managed_service.py` |
| `redis.redis.opstreelabs.in` | redis | `services/managed_service.py` |

The **`everest.percona.com`** group is the most-used CRD set in the platform (5 different DB types provisioned through it) and is **completely missing from the current ClusterRole**.

---

## Step 2 — diff against current `clusterrole.yaml`

The existing `platform/manifests/haven-api/clusterrole.yaml` is largely correct but has 3 gaps:

### Gap 1 — `everest.percona.com` not granted

Current rules cover `postgresql.cnpg.io`, `redis.redis.opstreelabs.in`, `rabbitmq.com` but NOT `everest.percona.com`. Yet `everest_client.py` calls `custom_objects.create_namespaced_custom_object(group="everest.percona.com", ...)` for every Everest-managed DB.

**Why this currently works**: the rogue `haven-api-admin → cluster-admin` binding masks the gap. As soon as we delete the rogue binding, every Everest DB provision/deprovision/list call will start failing with `forbidden: cannot create resource "databaseclusters" in API group "everest.percona.com"`.

### Gap 2 — `update` verb missing on resourcequotas/limitranges

`tenant_service.py::_update_resource_quota` calls `replace_namespaced_resource_quota` (the `update` verb in K8s RBAC speak — `replace` is an HTTP method, not an RBAC verb). The current rule only lists `create`, `patch`, `delete`. The `replace` call would 403 without cluster-admin masking it.

Same for `limitranges`.

### Gap 3 — `update` verb missing on secrets

`secret_service.py::update_secret` uses `replace_namespaced_secret`. Current rule lists `create, patch, update, delete` for secrets — actually this one IS already in the list (`update` is present). **OK, no fix needed.**

But wait, I want to double-check: the rule is:

```yaml
verbs: ["get", "list", "watch", "create", "patch", "update", "delete"]
```

Yes — that line covers core_v1 services/pods/secrets/configmaps/events/endpoints/pvcs/serviceaccounts uniformly. So `update` is granted on secrets via this combined rule. ✅

But the dedicated resourcequotas/limitranges rule a few lines earlier says:

```yaml
verbs: ["get", "list", "create", "patch", "delete"]
```

Missing `update` here. Real gap.

---

## Step 3 — proposed corrected ClusterRole

See `clusterrole.yaml` in this same directory. Diff against current:

```diff
   # ResourceQuota and LimitRange
   - apiGroups: [""]
     resources: ["resourcequotas", "limitranges"]
-    verbs: ["get", "list", "create", "patch", "delete"]
+    verbs: ["get", "list", "create", "patch", "update", "delete"]
```

```diff
+  # Percona Everest managed DB CRDs (PG / MySQL / MongoDB) — gap closed in H1c
+  - apiGroups: ["everest.percona.com"]
+    resources:
+      - databaseclusters
+      - databaseclusterbackups
+      - databaseclusterrestores
+      - databaseclusterbackupschedules
+      - databaseengines
+    verbs: ["get", "list", "watch", "create", "patch", "update", "delete"]
```

Total change: **+8 LOC** in clusterrole.yaml, **0 LOC removed**. The role stays scoped (no wildcards, explicit verb list per resource).

---

## Step 4 — verify the corrected role passes a `kubectl auth can-i` audit

After applying the corrected `clusterrole.yaml` AND deleting the rogue `haven-api-admin` binding, every method in Step 1 should still pass:

```bash
# Sample positive checks (must be `yes` post-fix)
SA=system:serviceaccount:haven-system:haven-api
NS=tenant-rotterdam   # any tenant ns

kubectl auth can-i create namespace -n "" --as=$SA           # tenant create
kubectl auth can-i create resourcequota -n $NS --as=$SA       # quota provision
kubectl auth can-i replace resourcequota -n $NS --as=$SA      # quota update
kubectl auth can-i create rolebinding -n $NS --as=$SA         # tenant admin RBAC
kubectl auth can-i create deployment -n $NS --as=$SA          # app deploy
kubectl auth can-i patch deployments/scale -n $NS --as=$SA    # scale endpoint
kubectl auth can-i create databaseclusters.everest.percona.com -n everest --as=$SA   # NEW
kubectl auth can-i create ciliumnetworkpolicies.cilium.io -n $NS --as=$SA
kubectl auth can-i create rabbitmqclusters.rabbitmq.com -n $NS --as=$SA
kubectl auth can-i create redis.redis.redis.opstreelabs.in -n $NS --as=$SA
kubectl auth can-i create applicationsets.argoproj.io -n argocd --as=$SA
kubectl auth can-i create httproutes.gateway.networking.k8s.io -n $NS --as=$SA

# Sample negative checks (must be `no` — confirms scope-down works)
kubectl auth can-i 'get' nodes --as=$SA                       # cluster-wide read NO
kubectl auth can-i 'create' clusterroles --as=$SA             # rbac escalate path
kubectl auth can-i 'delete' nodes --as=$SA                    # node management
kubectl auth can-i '*' '*' --as=$SA                           # NOT cluster-admin
```

**The last `*` `*` check is the proof.** Pre-fix it returns `yes` (cluster-admin). Post-fix it must return `no`.

---

## Step 5 — morning operator action plan

This PR ships **only** the corrected `clusterrole.yaml`. The rogue binding deletion is a **destructive** operation against shared cluster state, so it stays as a manual operator step.

### Sequence (run in order)

1. **Visual review** of this analysis + the proposed `clusterrole.yaml` diff
2. **Apply the corrected role** (this is just a patch — adds `update` + the everest group):
   ```bash
   KC=infrastructure/environments/dev/kubeconfig
   kubectl --kubeconfig=$KC apply -f platform/manifests/haven-api/clusterrole.yaml
   ```
3. **Verify the auth checks** above. The negative check `can-i '*' '*'` will still say `yes` because the rogue binding is still present. The positive checks for `everest.percona.com` etc. should now say `yes` from the scoped role alone.
4. **Watch logs for 30 minutes** (or wait a tenant create cycle) to make sure nothing has fallen through:
   ```bash
   kubectl --kubeconfig=$KC logs -n haven-system deploy/haven-api -f | grep -i "forbidden\|denied\|403"
   ```
5. **Delete the rogue binding**:
   ```bash
   kubectl --kubeconfig=$KC delete clusterrolebinding haven-api-admin
   ```
6. **Re-run the auth checks**. Now `can-i '*' '*'` MUST say `no`. Every positive check from Step 4 should still say `yes`.
7. **Smoke test** end-to-end:
   - Create a test tenant via the API
   - Provision a managed DB (PG via Everest)
   - Deploy an app
   - Delete the tenant
   - All four should succeed with no forbidden errors
8. **Update audit log** (`haven-system` namespace) to record the change

### Rollback plan

If anything breaks:

```bash
# Re-grant cluster-admin temporarily
kubectl --kubeconfig=$KC create clusterrolebinding haven-api-admin \
  --clusterrole=cluster-admin \
  --serviceaccount=haven-system:haven-api
```

Then file a follow-up PR with the missing verb / API group identified from the haven-api logs.

---

## What this PR does NOT do

- **No `kubectl apply`** — operator runs it manually
- **No deletion of the rogue binding** — operator runs it after verification
- **No new audit log integration** — that's Sprint H1d
- **No changes to `serviceaccount.yaml`, `clusterrolebinding.yaml`, or other manifests** — only `clusterrole.yaml` is touched
- **No tests** — RBAC verification is done via `kubectl auth can-i` post-apply, which is the canonical K8s pattern

---

## Why this is HIGHEST RISK in Sprint H1

The architect's H1 plan ranked this fix as the riskiest:

> "haven-api crash ederse cluster yönetimi durur. Bunu **dikkatli bir oturumda**, en üst odaklanmayla yapmalıyım. İlk H1 PR'ı olarak değil."

Reasoning:
- haven-api is the platform control plane. If its RBAC is too narrow, **every** tenant create / app deploy / DB provision / scale operation 403s.
- The cluster-admin binding has been masking gaps for months. There may be edge cases the grep above missed (e.g. operator-shell scripts that use the SA token directly, or conditional code paths only triggered by specific tenant tier configs).
- The fix is a **drop in privilege**. If we get it wrong, operations break. If we get the firewall wrong (P4.1) operations fail closed but recoverable. RBAC scope-down is harder to roll back without a brief cluster-admin re-grant.

That's why this PR is **draft + analysis-heavy + step-by-step morning runbook**. The actual destructive `kubectl delete` is your call after reading this and doing the auth-can-i drill in a test window.

---

## References

- Architect H0 round-1 finding: "haven-api ServiceAccount = cluster-admin" (P0)
- K8s RBAC docs: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- The `bind` and `escalate` verbs (used for tenant admin RBAC provisioning): https://kubernetes.io/docs/reference/access-authn-authz/rbac/#privilege-escalation-prevention-and-bootstrapping
