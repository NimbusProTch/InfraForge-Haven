# Sprint R — ArgoCD Hierarchy Restructure + haven → iyziops Partial Rename

> **Durum**: 🟡 PLAN (onay bekliyor)
> **Branch**: TBD (`refactor/argocd-hierarchy` önerisi)
> **Bağımlılıklar**: main HEAD 7557403 (Haven compliance gate just landed)
> **Süre tahmini**: 2-3 saat (R1 restructure), +1-2 saat (R2 rename)

---

## 1. Problem Tanımı

Kullanıcının gönderdiği ArgoCD UI screenshot'ında **`iyziops-root` Application altında karışık yapı** görünüyordu:

```
iyziops-root (Application)
├── iyziops-apps             (Application, recurse → apps/iyziops/)
│     ├── haven-api          (Application, nested)
│     └── haven-ui           (Application, nested)
├── platform-ingress         (Application, recurse → apps/ingress/)
├── platform-operators       (Application, recurse → apps/operators/)
├── platform-services        (ApplicationSet, list generator)
│     ├── longhorn
│     └── cert-manager
├── platform-services-config (ApplicationSet, list generator)
│     └── cert-manager-config
└── tenants                  (ApplicationSet, git directories generator)
```

**İstenen**: `iyziops-root → ApplicationSet(only) → Application` — root altında DIREKT Application olmasın, hepsi bir ApplicationSet tarafından generate edilmiş olsun.

Ek problemler:
- **ORPHAN**: `platform/argocd/apps/services/kyverno-policies.yaml` — definition var ama hiçbir appset'e bağlı değil, 5 Kyverno policy file'ı boşa bekliyor
- **Naming inconsistency**: haven-api/haven-ui isimleri + `haven-system` namespace korunmuş, iyziops rename yapılmamış
- **Tenant isolation**: tenants ApplicationSet'i var ama progressive sync yok; bir tenant bozulursa diğerleri etkilenebilir

---

## 2. Canlı Durum (Audit sonucu)

### 2.1 Root Application

**Nerede tanımlı**: `infrastructure/modules/rke2-cluster/manifests/argocd-root-app.yaml.tpl` (cloud-init ile first master'a yazılıyor)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: iyziops-root
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: ${gitops_repo_url}
    targetRevision: ${gitops_target_revision}   # main
    path: platform/argocd/appsets
    directory:
      recurse: false     # <-- sadece appsets/ içindeki YAML'ları görür
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated: {prune: true, selfHeal: true}
```

### 2.2 platform/argocd/appsets/ — Şu Anki İçerik

| Dosya | Kind | Name | Generator / Source |
|---|---|---|---|
| `gateway-api-crds.yaml` | ApplicationSet | gateway-api-crds | List (sync-wave -10) |
| `iyziops-apps.yaml` | **Application** | iyziops-apps | Git path: `apps/iyziops/` (recurse) |
| `platform-ingress.yaml` | **Application** | platform-ingress | Git path: `apps/ingress/` (recurse) |
| `platform-operators.yaml` | **Application** | platform-operators | Git path: `apps/operators/` (recurse) |
| `platform-services.yaml` | ApplicationSet | platform-services | List: longhorn, cert-manager |
| `platform-services-config.yaml` | ApplicationSet | platform-services-config | List: cert-manager-config |
| `tenants.yaml` | ApplicationSet | tenants | Git directories: `gitops/tenants/*` |

→ **3 tane direct Application** root altında = problem kaynağı.

### 2.3 platform/argocd/apps/ — Şu Anki İçerik

```
apps/
├── ingress/                  (raw YAML: cilium-gatewayclass, iyziops-gateway, argocd-httproute)
├── iyziops/                  (haven-api.yaml + haven-ui.yaml Applications)
├── operators/                (kyverno.yaml Application)
└── services/
    ├── cert-manager-config/  (raw YAML: letsencrypt-issuers, iyziops-wildcard-cert)
    └── kyverno-policies.yaml (ORPHAN — not wired to any appset!)
```

### 2.4 Orphan + Legacy Tespit

| Öğe | Durum | Aksiyon |
|---|---|---|
| `platform/argocd/apps/services/kyverno-policies.yaml` | Orphan Application | Wire et veya sil |
| `platform/kyverno-policies/*.yaml` (5 file) | Ready ama deploy edilmemiş | Appset'e bağla |
| `platform/manifests/haven-api/` + `haven-ui/` | Aktif deploy, replicas=0 | Rename hedefi |
| `haven-system` namespace (cluster) | Aktif | iyziops-system'a taşı |
| MinIO/Keycloak/Vault/Harbor/External-Secrets | Code'da var, cluster'da YOK | Future sprint'lerde kurulacak, kod dokunulmaz |
| Prometheus/Grafana/Loki/Alloy | Code'da yok, cluster'da yok | Ayrı sprint (M1, M2) |

### 2.5 Live Cluster (7557403 sonrası)

```
ArgoCD Apps (10): cert-manager, cert-manager-config, haven-api, haven-ui,
                  iyziops-apps, iyziops-root, kyverno, longhorn,
                  platform-ingress, platform-operators
All Synced+Healthy
Namespaces: argocd, cert-manager, cilium-secrets, default, haven-system,
            iyziops-gateway, kube-*, kyverno-system, longhorn-system
CRDs for old deployments: NONE (clean)
Stale resources: NONE
```

Temiz bir baseline.

---

## 3. Target Structure

### 3.1 ASCII Tree

```
iyziops-root (Application, cloud-init)
  │
  │ watches: platform/argocd/appsets/ (recurse: false)
  │
  ├─[-10] gateway-api-crds              (ApplicationSet, List)
  │         └─ gateway-api-crds (Application)
  │
  ├─[-5]  platform-ingress              (ApplicationSet, List — 1 element)
  │         └─ platform-ingress (Application → apps/ingress/)
  │
  ├─[ 0]  platform-operators            (ApplicationSet, List)
  │         ├─ cert-manager (Helm)
  │         ├─ longhorn (Helm)
  │         └─ kyverno (Helm)
  │
  ├─[ 1]  platform-config               (ApplicationSet, List)
  │         ├─ cert-manager-config (raw YAML → apps/platform-config/cert-manager-config/)
  │         └─ kyverno-policies (raw YAML → apps/platform-config/kyverno-policies/)
  │
  ├─[ 3]  platform-observability        (ApplicationSet, List — FUTURE, empty now)
  │         ├─ kube-prometheus-stack    (future sprint M1)
  │         ├─ loki                     (future sprint M2)
  │         └─ alloy                    (future sprint M2)
  │
  ├─[ 4]  data-services                 (ApplicationSet, List — FUTURE, empty now)
  │         ├─ everest                  (future)
  │         ├─ redis-operator           (future)
  │         └─ rabbitmq-operator        (future)
  │
  ├─[ 5]  iyziops-platform              (ApplicationSet, List — 2 elements, replaces iyziops-apps)
  │         ├─ iyziops-api (raw YAML → apps/iyziops-platform/iyziops-api/)
  │         └─ iyziops-ui  (raw YAML → apps/iyziops-platform/iyziops-ui/)
  │
  └─[10]  tenants                       (ApplicationSet, Git directories + progressive sync)
            └─ tenant-{slug} per gitops/tenants/{slug}/
```

Önemli: Root'un **tek çocuğu ApplicationSet**'ler. Her ApplicationSet'in generate ettiği Application'lar root'un "grandchildren"'i oluyor, UI'da 2 katmanlı temiz hiyerarşi görünüyor.

### 3.2 File Layout (Target)

```
platform/argocd/
├── appsets/                                # Root bunları watch ediyor
│   ├── README.md                           # (yeni, layer anlatımı)
│   ├── gateway-api-crds.yaml               # KEEP
│   ├── platform-ingress.yaml               # REWRITE as ApplicationSet
│   ├── platform-operators.yaml             # REWRITE as ApplicationSet
│   ├── platform-config.yaml                # NEW
│   ├── platform-observability.yaml         # NEW (empty list for now)
│   ├── data-services.yaml                  # NEW (empty list for now)
│   ├── iyziops-platform.yaml               # NEW (renames iyziops-apps)
│   └── tenants.yaml                        # UPDATE (progressive sync)
│
└── apps/
    ├── ingress/                            # KEEP (raw K8s manifests)
    │   ├── cilium-gatewayclass.yaml
    │   ├── iyziops-gateway.yaml
    │   └── argocd-httproute.yaml
    │
    ├── platform-config/                    # NEW directory
    │   ├── cert-manager-config/            # MOVED from apps/services/cert-manager-config/
    │   │   ├── letsencrypt-issuers.yaml
    │   │   └── iyziops-wildcard-cert.yaml
    │   └── kyverno-policies/               # MOVED from platform/kyverno-policies/
    │       ├── disallow-privileged.yaml
    │       ├── require-health-probes.yaml
    │       ├── require-resource-limits.yaml
    │       ├── require-tenant-labels.yaml
    │       └── restrict-registries.yaml
    │
    └── iyziops-platform/                   # RENAMED from apps/iyziops/
        ├── iyziops-api/                    # RENAMED from haven-api/
        │   └── (raw K8s manifests)
        └── iyziops-ui/                     # RENAMED from haven-ui/
            └── (raw K8s manifests)

platform/manifests/
├── iyziops-api/                            # RENAMED from haven-api/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap.yaml
│   ├── rbac.yaml
│   └── httproute.yaml
└── iyziops-ui/                             # RENAMED from haven-ui/
    └── ...

platform/kyverno-policies/                  # DELETE (moved to apps/platform-config/kyverno-policies/)

platform/argocd/apps/iyziops/               # DELETE (renamed to iyziops-platform/)
platform/argocd/apps/operators/             # DELETE (inlined into platform-operators ApplicationSet)
platform/argocd/apps/services/              # DELETE (split to apps/platform-config/)
```

**Kullanıcının hedefi**: "başka yerde applications appset kalsın istemiyorum" — bu layout'ta **sadece** `platform/argocd/appsets/` + `platform/argocd/apps/` var, başka hiçbir yerde ArgoCD resource'u yok.

---

## 4. Sync-Wave Ordering

| Wave | AppSet | Neden |
|---|---|---|
| -10 | gateway-api-crds | CRD'ler her şeyden önce |
| -5 | platform-ingress | Gateway + HTTPRoute, CRD'ler sonrası, servisler öncesi |
| 0 | platform-operators | cert-manager, longhorn, kyverno (controller only) |
| 1 | platform-config | ClusterIssuers (cert-manager webhook ready) + ClusterPolicy (kyverno controller ready) |
| 3 | platform-observability | Prometheus, Loki (future sprint M1/M2) — cert-manager-config sonrası (wildcard cert hazır) |
| 4 | data-services | DB operators (future) |
| 5 | iyziops-platform | iyziops-api + iyziops-ui (observability + data-services sonrası) |
| 10 | tenants | Per-tenant Applications (platform tamamen sağlıklı olduktan sonra) |

Wave 2 boş (rezerve, cert-manager ready delay için).

---

## 5. Tenant Isolation — Progressive Sync

Current `tenants.yaml` basic Git directories generator. Target: progressive sync + finalizers + explicit RBAC project.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: tenants
  namespace: argocd
spec:
  generators:
    - git:
        repoURL: https://github.com/NimbusProTch/InfraForge-Haven.git
        revision: main
        directories:
          - path: gitops/tenants/*
  # Progressive sync — 20% of tenants at a time, halt on failure
  strategy:
    type: RollingSync
    rollingSync:
      steps:
        - matchExpressions:
            - key: sync-group
              operator: In
              values: ["tenants"]
          maxUpdate: "20%"
  template:
    metadata:
      name: "tenant-{{path.basename}}"
      namespace: argocd
      labels:
        tenant-slug: "{{path.basename}}"
        sync-group: "tenants"
      annotations:
        argocd.argoproj.io/sync-wave: "10"
      finalizers:
        - resources-finalizer.argocd.argoproj.io
    spec:
      project: iyziops-tenants
      source:
        repoURL: https://github.com/NimbusProTch/InfraForge-Haven.git
        targetRevision: main
        path: "{{path}}"
      destination:
        server: https://kubernetes.default.svc
        namespace: "tenant-{{path.basename}}"
      syncPolicy:
        automated: {prune: true, selfHeal: true}
        syncOptions:
          - CreateNamespace=true
          - ServerSideApply=true
```

**Not**: Progressive Sync (RollingSync strategy) ArgoCD 2.10+ Beta. Mevcut versiyonumuz 7.7.3 (helm chart) → ArgoCD binary 2.14.x civarı olmalı. **Doğrulanmalı**: `kubectl exec -n argocd argocd-application-controller-0 -- argocd version --short` çalıştırılıp progressive sync destekleniyor mu bakılır. Desteklenmiyorsa basit ApplicationSet ile kalırız.

---

## 6. AppProjects (yeni)

Mevcut: `default` project (her şey default'ta).

Target: 2 adet ayrı AppProject.

### 6.1 `iyziops-platform` Project

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: iyziops-platform
  namespace: argocd
spec:
  description: Platform services (operators, ingress, observability, config, iyziops-api/ui)
  sourceRepos:
    - https://github.com/NimbusProTch/InfraForge-Haven.git
    - https://charts.jetstack.io
    - https://charts.longhorn.io
    - https://kyverno.github.io/kyverno/
    - https://prometheus-community.github.io/helm-charts
    - https://grafana-community.github.io/helm-charts
  destinations:
    - namespace: "*"  # Platform cluster-wide access
      server: https://kubernetes.default.svc
  clusterResourceWhitelist:
    - group: "*"
      kind: "*"
  namespaceResourceWhitelist:
    - group: "*"
      kind: "*"
```

### 6.2 `iyziops-tenants` Project

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: iyziops-tenants
  namespace: argocd
spec:
  description: Per-tenant isolated namespaces (restricted)
  sourceRepos:
    - https://github.com/NimbusProTch/InfraForge-Haven.git
  destinations:
    - namespace: "tenant-*"    # Only tenant-* namespaces
      server: https://kubernetes.default.svc
  clusterResourceBlacklist:
    - group: "*"
      kind: ClusterRole
    - group: "*"
      kind: ClusterRoleBinding
    - group: "*"
      kind: CustomResourceDefinition
    - group: ""
      kind: Namespace  # Don't allow tenants to create namespaces
  namespaceResourceBlacklist:
    - group: ""
      kind: ResourceQuota  # Only platform sets quotas
    - group: ""
      kind: LimitRange
    - group: networking.k8s.io
      kind: NetworkPolicy  # Only platform Kyverno sets NPs
```

Bu AppProjects `platform/argocd/apps/platform-config/argocd-projects/` altında olacak (cert-manager-config yanında, platform-config appset tarafından apply edilecek).

---

## 7. Rename Stratejisi — KARAR GEREKİYOR

Kullanıcı dedi: "haven-api ler öyle mesela ve onlarında izimlerini değiştreilm lütfen iyziops-api ve iyziops-ui olarak deploy olsunlar"

3 rename seviyesi var:

### 7.1 Option A — **Surface rename (önerilen, en küçük)**

**Scope**: Sadece ArgoCD visibility + deploy isimleri. API runtime code dokunulmaz.

- `platform/argocd/apps/iyziops/haven-api.yaml` → `platform/argocd/apps/iyziops-platform/iyziops-api/` dizinine taşı
- ArgoCD Application `metadata.name: haven-api` → `iyziops-api`
- `spec.source.path`: `platform/manifests/haven-api` → `platform/manifests/iyziops-api`
- `platform/manifests/haven-api/` dizinini `platform/manifests/iyziops-api/` olarak rename et
- Deployment içinde `metadata.name: haven-api` → `iyziops-api`
- Deployment label `app: haven-api` → `app: iyziops-api` (HPA/Service selector'ları da güncelle)
- Service `metadata.name: haven-api` → `iyziops-api` (ClusterIP DNS değişir: `iyziops-api.haven-system.svc`)
- ConfigMap `metadata.name: haven-api-config` → `iyziops-api-config`
- HTTPRoute target: Service adı yeni, hostname `api.iyziops.com` aynı kalır
- **Namespace**: `haven-system` **DOKUNMA** — Python code + env vars + test code + Keycloak realm + Harbor robot paths hep `haven-system` kullanıyor

**Net çıktı**: 
- ArgoCD UI `iyziops-api`, `iyziops-ui` görür
- K8s Deployment/Service/ConfigMap adları `iyziops-*`
- Namespace hala `haven-system` (gelecek sprint'te rename)
- API code runtime: sıfır değişiklik, test suite etkilenmez

**Risk**: Düşük. Declarative değişiklik, ArgoCD prune eder.  
**Effort**: ~1 saat  
**Backward compat**: Image pin'leri eski (harbor.46.225.42.2.sslip.io/library/haven-api) → Harbor iyziops'ta kurulmamış, zaten image pull fail. Image path bu sprint'te değiştirilebilir veya değil — fark etmez (replicas=0).

### 7.2 Option B — **Namespace rename (orta)**

Option A + namespace rename:

- Her yerde `haven-system` → `iyziops-system` (manifests + API env vars + test fixtures + Keycloak realm URL'i + Harbor robot account destination path + kyverno exclusion list + docs)
- ~20+ dosya değişir
- **Risk**: Orta. API code integration test'leri `haven-system` hardcoded olabilir (muhtemelen)
- **Effort**: ~3-4 saat
- Dikkat: API runtime pod `iyziops-system`'e taşınacak, eski `haven-system`'deki Deployment pruning sırasında arge condition olabilir

### 7.3 Option C — **Full rename (RENAME_IYZIOPS_PLAN.md)**

`docs/sprints/RENAME_IYZIOPS_PLAN.md`'deki tam plan — tüm dosyalar, tüm docs, tüm code, ns, secret, image, CI, Makefile.

- **Risk**: Yüksek (whitelist pattern'ler dikkatli kurulmazsa VNG Haven Standard referansları da rename edilir → compliance claim bozulur)
- **Effort**: 1-2 gün
- Kendi ayrı sprint'i olmalı, bu restructure sprint'inin içinde değil

### Önerim

**Option A**. Sebepler:
1. Kullanıcının istediği şey netti: "iyziops-api ve iyziops-ui olarak deploy olsunlar" — sadece deploy ismi
2. Option B'nin namespace rename riski bu sprint'in kapsamını bozuyor (API code + test suite etkileniyor)
3. Option C zaten ayrı sprint planlanmış (`RENAME_IYZIOPS_PLAN.md`)
4. Option A'dan sonra Option C gelecek sprint'te yapılabilir, engel değil

**Namespace `haven-system` bu sprint'te kalır**, sonra rename sprint'inde tamamen `iyziops-system`'a geçilir.

---

## 8. Migration Plan (Adım Adım)

### Phase 0 — Preparation (5 dk)

1. Backup tag: `git tag -a backup/main-pre-argocd-restructure-YYYYMMDD-HHMMSS main && git push --tags`
2. Feature branch: `git checkout -b refactor/argocd-hierarchy`
3. ArgoCD version doğrula: progressive sync support var mı?
   ```bash
   KUBECONFIG=/tmp/iyziops-kubeconfig kubectl -n argocd exec statefulset/argocd-application-controller -- argocd version --short --client
   ```
4. Mevcut state yedek: `make haven-json > haven/reports/pre-restructure-baseline.json`

### Phase 1 — New ApplicationSets (code, no cluster touch yet) — 30 dk

5. `platform/argocd/apps/platform-config/cert-manager-config/` dizini oluştur, `apps/services/cert-manager-config/*` dosyalarını buraya taşı
6. `platform/argocd/apps/platform-config/kyverno-policies/` dizini oluştur, `platform/kyverno-policies/*` dosyalarını buraya taşı
7. `platform/argocd/apps/platform-config/argocd-projects/` dizini oluştur, `iyziops-platform.yaml` + `iyziops-tenants.yaml` AppProject manifestlerini yaz
8. `platform/argocd/apps/iyziops-platform/iyziops-api/` dizini oluştur, `apps/iyziops/haven-api.yaml` içeriği + `manifests/haven-api/` dosyaları rename edilerek kopyala (Option A)
9. `platform/argocd/apps/iyziops-platform/iyziops-ui/` aynı şekilde
10. `platform/manifests/iyziops-api/` dizinini oluştur, `haven-api/` içeriğini kopyala + rename (Deployment/Service/ConfigMap metadata.name)
11. `platform/manifests/iyziops-ui/` aynı
12. Yeni `platform/argocd/appsets/platform-operators.yaml` yaz (ApplicationSet List: cert-manager, longhorn, kyverno — inline Helm values)
13. Yeni `platform/argocd/appsets/platform-config.yaml` yaz (ApplicationSet List: cert-manager-config path, kyverno-policies path, argocd-projects path)
14. Yeni `platform/argocd/appsets/platform-ingress.yaml` yaz (ApplicationSet List: 1 element → apps/ingress/ path)
15. Yeni `platform/argocd/appsets/platform-observability.yaml` yaz (ApplicationSet List, elements: [] — boş placeholder)
16. Yeni `platform/argocd/appsets/data-services.yaml` yaz (ApplicationSet List, elements: [] — boş placeholder)
17. Yeni `platform/argocd/appsets/iyziops-platform.yaml` yaz (ApplicationSet List: iyziops-api, iyziops-ui → apps/iyziops-platform/*)
18. `platform/argocd/appsets/tenants.yaml` güncelle (progressive sync + iyziops-tenants project + finalizers)

### Phase 2 — Eski Dosyaları Sil — 10 dk

19. `git rm platform/argocd/appsets/iyziops-apps.yaml`
20. `git rm platform/argocd/appsets/platform-services.yaml` (replaced by platform-operators)
21. `git rm platform/argocd/appsets/platform-services-config.yaml` (replaced by platform-config)
22. `git rm -r platform/argocd/apps/iyziops/` (renamed to iyziops-platform)
23. `git rm -r platform/argocd/apps/operators/` (inlined into platform-operators)
24. `git rm -r platform/argocd/apps/services/` (split to platform-config)
25. `git rm -r platform/kyverno-policies/` (moved to apps/platform-config/kyverno-policies)
26. `git rm -r platform/manifests/haven-api/` (renamed)
27. `git rm -r platform/manifests/haven-ui/` (renamed)

### Phase 3 — Doğrulama (local) — 10 dk

28. `tree platform/argocd/ platform/manifests/` → target layout'a uyduğu doğrula
29. `grep -r "haven-api\|haven-ui\|platform/manifests/haven" platform/ charts/` → artık match etmemeli (namespace hariç)
30. `grep -r "platform/argocd/apps/iyziops\|platform/kyverno-policies" .` → hiçbir referans kalmamalı

### Phase 4 — Commit + Push — 5 dk

31. Atomic commit: `feat(argocd): restructure hierarchy + rename haven-api/ui → iyziops-api/ui`
32. Push: `git push origin refactor/argocd-hierarchy`

### Phase 5 — PR + Merge to main — 10 dk

33. PR aç (kullanıcı review ediyorsa), yoksa direkt merge
34. Fast-forward merge to main
35. Push main

### Phase 6 — ArgoCD Auto-Sync + Manual Verify — 20 dk

36. iyziops-root ArgoCD refresh: `kubectl annotate app iyziops-root -n argocd argocd.argoproj.io/refresh=hard --overwrite`
37. 3 dk bekle, durum kontrol:
    ```bash
    kubectl get applicationsets -n argocd
    kubectl get applications -n argocd
    ```
38. Beklenen durum:
    - Eski Application'lar (iyziops-apps, platform-ingress, platform-operators, haven-api, haven-ui) pruned
    - Yeni ApplicationSets (platform-operators, platform-config, platform-ingress, platform-observability, data-services, iyziops-platform) oluşturulmuş
    - Yeni Application'lar (cert-manager, longhorn, kyverno, cert-manager-config, kyverno-policies, platform-ingress, iyziops-api, iyziops-ui) Synced+Healthy
39. `make haven` → 12/15 PASS (baseline değişmemeli)

### Phase 7 — Post-verification Namespace Cleanup — 5 dk

40. Eğer `haven-system` namespace'i boş kaldıysa (iyziops-api/ui Deployment'ları haven-system'da kaldı çünkü Option A namespace değiştirmiyor):
    - Beklenen: haven-system namespace'i hala aktif, Deployment adı iyziops-api olarak değişti
41. Kyverno ClusterPolicies aktif mi: `kubectl get clusterpolicy` → 5 policy görülmeli (daha önce 0 idi)

---

## 9. Risk + Mitigation

| Risk | Olasılık | Impact | Mitigation |
|---|---|---|---|
| iyziops-root cascade delete (appsets dir silinir) | Düşük | Kritik | Backup tag + dikkatli `git rm` + PR review |
| Eski haven-api Deployment orphan kalır | Orta | Düşük | ArgoCD prune=true, selfHeal=true zaten set, otomatik temizler |
| Kyverno policies Enforce mode ile existing workload bozar | Orta | Orta | Policies'i önce `validationFailureAction: Audit` ile deploy et, 24h gözlem, sonra Enforce |
| Progressive sync ArgoCD 7.7.3'te çalışmaz | Düşük | Düşük | Pre-check yap, desteklenmiyorsa basit ApplicationSet |
| AppProject restriction iyziops-api'yi reddeder (cluster-scoped kaynak deny edilir) | Düşük | Orta | iyziops-platform project'i permissive, iyziops-tenants project'i restricted |
| Rename sonrası Harbor image pull hala haven-api/haven-ui arıyor | Zaten | Düşük | replicas=0 → pod oluşturulmuyor, sorun yok. Harbor deploy sprint'inde image path düzeltilecek |
| Cloud-init root app template değişirse sonraki tofu apply'da root resync yapamaz | Düşük | Kritik | Root app template DEĞİŞTİRİLMİYOR — sadece watch ettiği dizinin içeriği değişiyor |
| ArgoCD controller restart gerekir | Düşük | Düşük | Hard refresh yeter, restart normalde gerekmez |

---

## 10. Kullanıcı Kararları — ONAY GEREKEN YERLER

**Q1. Rename scope**: Option A (surface, bu plan) / B (ns rename dahil) / C (full, ayrı sprint)?
- **Benim önerim: A**

**Q2. Single commit mi 2 commit mi?**
- **Option X**: Tek atomic commit (restructure + rename beraber) — temiz git log, tek rollback
- **Option Y**: 2 commit (önce restructure, sonra rename) — incremental, ayrı review
- **Benim önerim: X** (tek atomic commit, rollback istenirse tek `git revert`)

**Q3. Progressive sync bu sprint'te aktif mi?**
- **Pros**: Tenant isolation güçlenir, gelecek tenant rollout'ları güvenli
- **Cons**: Beta feature, şu an 0 tenant var, test edilemez
- **Benim önerim: Implement ama default `elements: []` ile test et**, ileride tenant eklenince doğrula

**Q4. Observability (Prometheus + Loki) bu sprint içinde mi?**
- **Option Z1**: Sadece restructure + rename (bu plan) — 2-3 saat
- **Option Z2**: Restructure + rename + Prometheus stack (sprint M1) — +3-4 saat
- **Option Z3**: Z2 + Loki + Alloy (sprint M1 + M2) — +7-8 saat toplam
- **Benim önerim: Z1** — restructure büyük değişim, observability sonraki sprint'te temiz baseline üzerinde

**Q5. haven-system namespace'i ne olacak?**
- Option A rename'de haven-system kalır. Bu sprint'te haven-system'de artık eski haven-api/ui yerine iyziops-api/ui Deployment'ları olacak. İsim inconsistency ama API code bozulmaz.
- **Alternatif**: haven-system'i `iyziops-system`'e rename et → Option B'ye yaklaşır → risk artar
- **Benim önerim**: Kalsın, rename sprint'ine bırak

---

## 11. Cloud-init Root App — Değiştirmek Gerekir mi?

**Hayır.** Mevcut `argocd-root-app.yaml.tpl`:

```yaml
spec:
  source:
    path: platform/argocd/appsets   # Bu path aynı kalıyor
    directory:
      recurse: false
```

Sadece `appsets/` içindeki dosyalar değişiyor. Root app template aynen kalabilir. Next `tofu apply`'da da aynı root oluşacak, sadece içeriği güncel main'den çekilecek.

**Dokunulacak infra**: YOK. Bu sprint 100% repo-only değişim. Cluster'a ArgoCD sync kendi başına uygulayacak.

---

## 12. Test Plan (merge sonrası)

1. `KUBECONFIG=/tmp/iyziops-kubeconfig kubectl get applicationsets -n argocd` → 7 ApplicationSet beklenir:
   - gateway-api-crds
   - platform-ingress
   - platform-operators
   - platform-config
   - platform-observability (empty)
   - data-services (empty)
   - iyziops-platform
   - tenants (= 8 aslında)

2. `kubectl get applications -n argocd` → mimaride root + generated apps:
   - iyziops-root
   - gateway-api-crds (from appset)
   - platform-ingress (from appset)
   - cert-manager, longhorn, kyverno (from platform-operators)
   - cert-manager-config, kyverno-policies (from platform-config)
   - iyziops-api, iyziops-ui (from iyziops-platform)

3. `kubectl get clusterpolicy` → **5 Kyverno policy** aktif (önceden 0 idi)

4. `kubectl get deploy -n haven-system` → `iyziops-api` + `iyziops-ui` (isimler yeni)

5. `make haven` → 12/15 PASS (baseline değişmeli değil)

6. ArgoCD UI → root altında sadece **ApplicationSets** (ve gateway-api-crds Application). Direct Application yok. Hiyerarşi temiz.

7. Rollback testi (dry-run): `git revert HEAD` ile önceki state'e dönülebilir mi?

---

## 13. Success Criteria

- ✅ `iyziops-root` altında **sadece ApplicationSets** görünüyor (ve -10 wave gateway-api-crds)
- ✅ `platform/argocd/` tree'de orphan Application yok
- ✅ `platform/kyverno-policies/` directory silindi (moved)
- ✅ `haven-api`/`haven-ui` ArgoCD'de görünmüyor, yerine `iyziops-api`/`iyziops-ui`
- ✅ `platform/manifests/haven-*` dizinleri silindi, `iyziops-*` olarak rename edildi
- ✅ 5 Kyverno ClusterPolicy aktif
- ✅ `make haven` → 12/15 PASS (baseline aynı)
- ✅ main'de commit, backup tag atıldı, feature branch silindi
- ✅ Cluster 10+ Applications Synced+Healthy

---

## 14. Implementation Order Checklist

- [ ] Phase 0: Backup tag + branch + version check
- [ ] Phase 1: Create new files (appsets + apps/platform-config + apps/iyziops-platform + manifests/iyziops-*)
- [ ] Phase 2: Delete old files (apps/iyziops, apps/operators, apps/services, kyverno-policies, manifests/haven-*)
- [ ] Phase 3: Local verification (tree, grep)
- [ ] Phase 4: Commit + push feature branch
- [ ] Phase 5: PR + merge main
- [ ] Phase 6: ArgoCD refresh + state verify
- [ ] Phase 7: Post-verify + Kyverno policies count
- [ ] Phase 8: `make haven` baseline verify
- [ ] Phase 9: Delete old backup tag after 48h if stable

---

## 15. Future Sprints (post-R)

- **Sprint M1**: kube-prometheus-stack → `platform-observability` appset'ine ekle (empty → populated)
- **Sprint M2**: Loki + Alloy → `platform-observability` appset'ine ekle
- **Sprint D1**: Everest + Redis Operator + RabbitMQ Operator → `data-services` appset'ine ekle
- **Sprint H1a-OIDC**: Keycloak realm + kube-apiserver OIDC flags (Haven check #4)
- **Sprint H-net-private**: Private networking investigation (Haven check #7)
- **Sprint Rename-Full**: `docs/sprints/RENAME_IYZIOPS_PLAN.md` tam rename (`haven-system` → `iyziops-system`, tüm dosyalar + code + docs)

Bu sprint R1 + R2 paralel veya sequential olabilir, sonra M1 → M2 → D1 sırasıyla gidilir.
