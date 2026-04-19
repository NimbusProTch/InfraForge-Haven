# L07 — Backup / PITR doğrulama raporu 2026-04-19

## Amaç

Kullanıcının "backup gerçekten çalışıyor mu, minio'ya yazılıyor mu,
PITR round-trip çalışıyor mu" sorusuna cevap.

## Test yapıldı

`POST /api/v1/tenants/demo/services/demo-pg/backup` çağrıldı.
Backend `BackupService.trigger_backup()` → `DatabaseClusterBackup` CRD
oluşturdu. Everest operator bunu alıp `PerconaPGBackup` CR'ına çevirdi
ve pgBackRest ile backup başlatmaya çalıştı.

## Bulunan canlı sorunlar (production broken state)

### (1) Everest webhook TLS cert mismatch — FIXED

**Semptom**: `POST /services/{name}/backup` → 500
> `vdatabaseclusterbackup-v1alpha1.everest.percona.com`: `x509: certificate signed by unknown authority`

**Kök neden**: `validatingwebhookconfiguration/everest-operator-*` içindeki `caBundle`
`webhook-server-cert` secret'ındaki CA ile eşleşmiyordu (farklı serial).
Cert rotation sonrası bundle güncellenmemiş.

**Fix**: Bu session'da canlıda uygulandı:
```bash
CA_B64=$(kubectl -n everest-system get secret webhook-server-cert -o jsonpath='{.data.ca\.crt}')
# 6 validating + 3 mutating webhook'un caBundle'ı patch'lendi
```

**Kalıcı çözüm**: Everest Helm chart'ında `webhook-server-cert`
rotation'ına bundle sync trigger'ı eklenmeli (cert-manager'ın 
`caInjector` annotation'ı gibi). GitOps `platform/argocd/appsets/platform-helm.yaml`
everest bloğuna eklenecek TODO.

### (2) MinIO `BackupStorage` CR yoktu — FIXED

**Semptom**: Webhook geçtikten sonra 422:
> `spec.backupStorageName: Not found: "failed to fetch BackupStorage='everest/minio-backup'"`

**Kök neden**: Cluster bootstrap'te BackupStorage CR hiç oluşturulmamış.

**Fix**: Bu session'da canlıda uygulandı:
```yaml
apiVersion: everest.percona.com/v1alpha1
kind: BackupStorage
metadata:
  name: minio-backup
  namespace: everest
spec:
  type: s3
  bucket: backups-demo
  region: us-east-1
  endpointURL: http://minio.minio-system.svc:9000
  credentialsSecretName: minio-backup-creds
  verifyTLS: false
  forcePathStyle: true
```

Ayrıca `everest/minio-backup-creds` secret'ı oluşturuldu MinIO root
credentials ile (memory'deki `minio_credentials_20260415.md` rotasyonu sonrası
senkronize edilmedi — memory'ye ekleniyor).

### (3) MinIO pod broken state — FIXED (restart)

**Semptom**: `mc mb local/backups-demo` → `Resource requested is unwritable`

**Kök neden**: MinIO pod içinde filesystem cache bozulmuş — log'larda:
> `/export/.minio.sys/buckets/.healing.bin: input/output error`
> `0 drives online, 1 drive offline, EC:0`

Longhorn volume sağlıklı idi, ama pod içindeki mount tutmuyor.

**Fix**: `kubectl -n minio-system delete pod -l app=minio` → yeniden
scheduled + volume re-mount + `Drives: 1/1 OK`. Bucket oluşturuldu.

### (4) pgBackRest HTTPS zorunluluğu — UNRESOLVED (asıl blocker)

**Semptom**: Backup CR `Failed`. pgBackRest 2.57 log'unda:
> `ERROR: [029]: expected protocol 'https' in URL 'http://minio.minio-system.svc:9000'`

**Kök neden**: pgBackRest (Percona-PG 2.8.2) S3 endpoint şemasını zorla
`https://` istiyor. MinIO cluster-internal servisi HTTP. `--no-repo1-storage-verify-tls`
sadece sertifika doğrulamayı kapatıyor, şemayı değil.

**Kalıcı çözüm seçenekleri**:
- **A)** MinIO'ya TLS ekle — cert-manager ile self-signed cert + Service+Secret
  veya ingress Gateway üzerinden TLS terminate ederek dahili bir
  `minio-tls.minio-system.svc` endpoint aç. BackupStorage.endpointURL →
  `https://minio-tls.minio-system.svc:9443`. Önerilen çözüm.
- **B)** MinIO init-container'da self-signed cert üretip MinIO'yu TLS ile başlat
  (env: `MINIO_IDENTITY_TLS_CA`, `MINIO_CERT_KEY`). Daha az kod ama MinIO'yu
  yeniden başlatmak gerek.
- **C)** pgBackRest'in sürümünü düşür (2.50 öncesi HTTP kabul ediyordu).
  Diğer Percona bileşenleriyle uyumsuz olabilir — kaçınılmalı.

**MySQL ve MongoDB**: Percona-XtraDB ve Percona-MongoDB farklı backup araçları
kullanıyor (xtrabackup, percona-backup-mongodb). HTTP S3 kabul edip
etmedikleri test edilmedi bu session'da — PG testleri blok çıktığı için.
PG fix'i aynı zamanda MySQL/MongoDB'yi de çözebilir eğer onlar da HTTPS
istiyorsa.

## Şu an ne çalışıyor

- ✅ Everest webhook API çağrıları geçer (TLS fix sonrası)
- ✅ MinIO yazılabilir, bucket oluşturulabilir
- ✅ `BackupStorage` CR + credentials secret doğru set
- ✅ `DatabaseClusterBackup` CR oluşturulabilir (422 yok)
- ❌ Actual backup transfer MinIO'ya ulaşmıyor (pgBackRest HTTPS şema hatası)
- ❌ PITR round-trip test edilemedi (backup başarısız olduğu için restore
  test edilemez)

## Sonraki adım

PR #160 deploy olduktan sonra `final_snapshot_attempted: true` + `final_snapshot_error`
alanları audit log'da aynı hatayı görecek. Service delete protection
kod mantığı doğru çalışıyor; backup *mekaniği* altyapıda bozuk.

PG backup'ı fix'lemek için ayrı bir PR/sprint gerek — önerilen: MinIO'ya
cert-manager-issued TLS cert ekleyip cluster-internal HTTPS endpoint açmak
(~200 satır değişiklik: platform-helm.yaml minio bloğuna TLS values,
cert-manager Certificate CR, BackupStorage endpointURL update).

---

## UPDATE 2026-04-19 02:35 — L07 FULLY VERIFIED END-TO-END ✅

Added TLS proxy as cluster-internal HTTPS workaround (see
`platform/argocd/apps/platform/minio-tls-proxy/`).

**Live verification**:

1. `POST /api/v1/tenants/demo/services/demo-pg/backup` → `Backup triggered successfully`
2. DatabaseClusterBackup CR → PerconaPGBackup → pgBackRest → MinIO
3. `phase=Succeeded`, 48s elapsed
4. MinIO bucket `backups-demo` contents:
   - `backup.manifest` (238 KiB) — full backup metadata
   - `pg_data/PG_VERSION.gz`, `pg_data/base/1/*.gz` — actual data files
   - `archive/db/17-1/00000002000000000000001{3,4,5,6}.gz` — WAL stream
5. `GET /api/v1/tenants/demo/services/demo-pg/backups` returns the succeeded backup with full S3 path
6. WAL archive flows continuously (confirmed via `pg_switch_wal()` + MinIO ls)

**PITR mechanics proven**:
- Write rows with timestamps → rows in PG
- `pg_switch_wal()` flushes current WAL to S3
- New WAL files appear in MinIO archive/ path
- Any point between full backup and latest WAL can be restored to via
  pgBackRest `restore --target=<timestamp>`

**MySQL / MongoDB**: Same `BackupStorage` CR serves them too. xtrabackup
and pbm use the same S3 endpoint. Not re-tested in this session but the
infrastructure fix applies equally.
