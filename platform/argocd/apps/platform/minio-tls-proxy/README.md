# MinIO TLS Proxy (Helper for pgBackRest)

pgBackRest 2.55+ requires S3 endpoints to be `https://`. MinIO's cluster-
internal Service is plaintext HTTP. This thin nginx proxy terminates TLS
with a self-signed cert and forwards to `minio:9000`, giving us a
working `https://minio-tls.minio-system.svc:9443` endpoint for
Everest's `BackupStorage` CR.

**Self-signed** is fine here — it never leaves the cluster and
BackupStorage has `verifyTLS: false`. Certificate is regenerated on every
bootstrap via the Job; 10-year validity so mid-flight rotations aren't
an ops concern.

Replace with a cert-manager-issued cert when Vault+ESO is wired up.
