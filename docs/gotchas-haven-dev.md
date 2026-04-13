# Haven Dev-Era Gotcha'ları (Rancher-based cluster)

> Arşivlenmiş tuzaklar. CLAUDE.md'den taşındı 2026-04-13.
> **Aktif (iyziops Option B) gotcha'lar için** → `CLAUDE.md` ana dosyası.
> Bu dosya Haven dev cluster'ını (2026-01 → 2026-04) çalıştırırken karşılaşılan sorunları arşivler. iyziops prod Option B mimarisinde Rancher/Bitnami/Kind kullanılmadığından bunların çoğu artık geçerli değil; ama Haven dev'i ya da benzer bir Rancher kurulumunu debug ediyorsan lazım olabilir.

---

## Infrastructure / Rancher era

- Hetzner primary IP limit ~5 per account → request increase for 3+3 nodes
- `HavenAdmin2026!` → `!` breaks in bash, never pass through shell
- rancher2 provider v5.x → Rancher 2.9.x (version must match)
- cloud-init `$$` for shell variable escaping in templatefile
- cloud-init `${VAR:0:16}` bash substring = Bad substitution (dash shell)
- Provider: `token_key` (provider config) vs `.token` (resource output)
- `cni: "none"` = chicken-and-egg problem → use `cni: "cilium"` + `chart_values`
- CIS profile taint: `node-role.kubernetes.io/etcd:NoExecute` → `tolerations: [{operator: "Exists"}]`
- `rancher2_app_v2` "Cluster not active" → `rancher2_cluster_sync` with `wait_catalogs=true` + `state_confirm=3`
- **Hetzner firewall**: Nodes use PUBLIC IPs for inter-node traffic, not private network → restricting to `network_cidr` breaks cluster. Need RKE2 `--node-ip` private network config first
- NodePort range (30000-32767) removed from firewall → Gateway API replaces it
- **Cilium 1.16 Gateway API + NodePort bug**: L7LB Proxy Port only applied to ClusterIP BPF entry, NOT NodePort entries → NodePort unreachable externally. Workaround: nginx DaemonSet (hostNetwork, port 80) proxies to gateway ClusterIP
- **nginx proxy_http_version**: Default is HTTP/1.0. Cilium Envoy gateway requires HTTP/1.1. Add `proxy_http_version 1.1; proxy_set_header Connection ""` to nginx config
- **Hetzner LB private IP**: `use_private_ip = true` + `depends_on = [hcloud_server_network.*]` bypasses public firewall for LB→node traffic
- **GatewayClass Unknown status**: Cilium 1.16 writes `supportedFeatures` as strings, but Gateway API CRD v1.2.1 expects objects → cosmetic only, Gateway itself works (PROGRAMMED: True)
- Longhorn destroy timeout → `timeouts { delete = "20m" }` + serialized destroy (Longhorn last)
- Longhorn destroy fallback: if 20m timeout, `tofu state rm 'rancher2_app_v2.longhorn[0]'` then re-destroy
- `nonsensitive()` in local-exec environment block to avoid output suppression
- cert-manager NOT in rancher-charts → use `rancher2_catalog_v2` (Jetstack repo) + `rancher2_app_v2`
- rancher-monitoring/logging need CRD chart installed first (e.g., `rancher-monitoring-crd`)
- Rancher 2.9.3 chart versions: `104.x.x` prefix (NOT `105.x.x`) → query live catalog API
- Longhorn version in catalog may differ from tfvars default → check `deployment_values` after apply
- **Bitnami images decommissioned**: `registry.bitnami.com` = NXDOMAIN, `docker.io/bitnami/*` tags removed, `ghcr.io/bitnami` = 403. Use official images (e.g. `quay.io/keycloak/keycloak:26.1`)
- **CNPG Cluster tolerations**: `spec.affinity.tolerations` NOT `spec.tolerations` (strict CRD validation)
- **Keycloak 26 start-dev**: management port 9000 not exposed → use `tcpSocket` probe on port 8080
- **kubectl apply + Service selector**: strategic merge patch does NOT remove extra labels from existing Service. Fix: `kubectl delete svc <name> --ignore-not-found` before `kubectl apply` to reset selector cleanly
- **ssh_resource via Rancher fleet secret**: `kubectl get secret -n fleet-default ${cluster_name}-kubeconfig -o jsonpath='{.data.value}' | base64 -d > /tmp/workload-kubeconfig` gives RKE2 cluster access from K3s management node
- **base64encode() trick for kubectl apply**: `echo '${base64encode(yaml)}' | base64 -d | kubectl apply -f -` avoids heredoc/escaping issues in ssh_resource commands

## Build / Deploy (Kaniko → BuildKit era)

- **BuildKit > Kaniko**: Kaniko 15+dk, BuildKit 3-4dk (5x hız). BuildKit paralel layer build + akıllı cache. `moby/buildkit:rootless` + `--oci-worker-no-process-sandbox` Kind'da çalışır
- **BuildKit daemon**: `buildkitd` Deployment + Service (`tcp://buildkitd.haven-builds.svc:1234`), `buildctl` Job olarak build submit
- **Nixpacks ARM64**: `aarch64-unknown-linux-musl` binary indirmeli, `uname -m` ile detect
- **Nixpacks "No start command"**: Otomatik tespit: Python (main.py, app.py, FastAPI/Flask/Django), Node (package.json scripts.start), Go (main.go), fallback Dockerfile üretimi
- **Kind insecure registry**: containerd config.toml'a `[plugins."io.containerd.grpc.v1.cri".registry.mirrors]` + `[...registry.configs...tls]` ekle, `/etc/hosts`'a ClusterIP ekle, `systemctl restart containerd`
- **GitHub OAuth org repos**: `read:org` scope + `/user/orgs` → `/orgs/{login}/repos` endpoint'leri ile org repo'ları listele
- **GitHub private repo clone**: `https://oauth2:{token}@github.com/owner/repo.git` — token DB'de tenant bazında sakla, build sırasında clone URL'ye inject et
- **SQLAlchemy Enum case**: `Enum(MyEnum, values_callable=lambda e: [x.value for x in e])` — DB lowercase, Python uppercase uyumsuzluğu
- **Next.js 14 useSearchParams**: Suspense boundary zorunlu, `export const dynamic = "force-dynamic"` ile cache engelle
- **App port konfigürasyonu**: Dockerfile EXPOSE portu ile liveness probe portu eşleşmeli, `Application.port` field ile konfigüre et

## Managed services & backend (Haven dev 3-tenant E2E)

- **Redis connection_hint**: OpsTree operator service adı `{name}` (NOT `{name}-redis`)
- **PG password URL-encoding**: Everest random password'lerde özel karakterler var (`:?()=|{}@`), kullanıcı `urllib.parse.quote` ile encode etmeli
- **Everest PG default DB**: `postgres` (custom DB adı oluşturmuyor, connection_hint'teki DB adı yanlış olabilir)
- **Harbor URL**: Build pipeline'da `HARBOR_URL` env var set edilmeli, docker config secret'taki host ile match etmeli
- **apptype enum**: DB'de yoksa manual oluştur: `CREATE TYPE apptype AS ENUM ('web', 'worker', 'cron')`
- **MySQL memory**: PXC 8.4 + Galera minimum **3Gi** RAM for backup SST (2Gi OOMKill during xtrabackup), 5Gi storage
- **Redis fsGroup**: OpsTree Redis Operator CRD'deki `securityContext.fsGroup` alanını StatefulSet'e aktarmıyor. Dev tier'da persistent storage kaldırıldı (ephemeral Redis)
- **Redis passwordless tenant secret**: OpsTree Redis secret oluşturmuyor. `_create_crd_tenant_secret` sadece `REDIS_URL` ile secret yaratır
- **ArgoCD per-tenant AppSet**: Global ApplicationSet kaldırıldı. Her tenant için `appset-{slug}` K8s API ile oluşturuluyor (tenant_service.py)
- **Everest CPU minimum**: Everest v1.13 `CPU limits should be above 600m` — 600m dahil değil! Dev tier `1` core olarak set edildi
- **EVEREST_URL configmap**: `http://everest.everest-system.svc.cluster.local:8080` — yoksa Everest path hiç çalışmaz
- **Helm chart empty image guard**: `image.repository` boşken Deployment/Service/HPA/HTTPRoute oluşturulmamalı. `{{- if .Values.image.repository }}` guard eklendi — aksi halde `:latest` image → InvalidImageName
- **ArgoCD auto-sync wipe protection**: Helm chart image guard sonrası tüm resources siliniyor → ArgoCD "auto-sync will wipe out all resources" uyarısı, manuel sync gerekli
- **haven-api image build (ARM64 → AMD64)**: Local Mac'te build edince `exec format error`. `docker build --platform linux/amd64` zorunlu
- **Gitea admin password**: `must-change-password` flag'i set edilmiş olabilir. `gitea admin user change-password --must-change-password=false`
- **Port-forward'lar**: haven-api svc port 80 (not 8000!), keycloak svc `keycloak-keycloakx-http` port 80
- **App port**: rotterdam-api 8080 dinliyor, default 8000 değil
- **GITOPS_ARGOCD_REPO_URL**: ArgoCD cluster içinde çalışır, lokal `localhost:3030` URL'sine erişemez. `http://gitea-http.gitea-system.svc.cluster.local:3000/haven/haven-gitops.git` set edilmeli
- **PG custom user**: `create_custom_database()` primary endpoint üzerinden bağlanır (PgBouncer bypass). Lokal dev'de cluster-internal DNS erişilemez → admin creds fallback
- **Background credential loop**: 15sn aralığı, per-service isolation. Her service kendi session+transaction'ında işlenir
- **Config credential default'lar boş**: `keycloak_admin_password`, `harbor_admin_password`, `everest_admin_password`, `secret_key` default `""`
- **DB unique constraints**: `applications(tenant_id, slug)`, `managed_services(tenant_id, name)` compound unique. Concurrent create → IntegrityError → 409
- **PATCH image_tag guard**: PATCH /apps image_tag None ise GitOps values.yaml güncellenmez (boş image yazıp Deployment'ı silmeyi engeller)
- **ArgoCD deploy fallback**: ArgoCD API erişilemezse pipeline K8s Deployment'ı direkt kontrol eder (60sn timeout)
- **Vault prod**: Vault dev mode cluster'da çalışıyor. Prod için HA mode + persistent storage + auto-unseal gerekli
- **haven-api image stale**: `platform/manifests/haven-api/deployment.yaml` image tag manual güncellenmeli
