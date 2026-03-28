#!/usr/bin/env bash
# setup-minio-backup-bucket.sh
#
# Creates the haven-backups bucket in MinIO and configures per-tenant prefix
# structure. Also creates the K8s Secret backup-s3-credentials in cnpg-system.
#
# Usage:
#   ./scripts/setup-minio-backup-bucket.sh [MINIO_ENDPOINT] [ACCESS_KEY] [SECRET_KEY]
#
# Environment variables (override CLI args):
#   MINIO_ENDPOINT   MinIO endpoint URL (default: http://minio.minio-system.svc:9000)
#   MINIO_ACCESS_KEY Access key
#   MINIO_SECRET_KEY Secret key
#   MINIO_ALIAS      mc alias name (default: haven-minio)
#   BUCKET_NAME      Bucket name (default: haven-backups)
#   K8S_NAMESPACE    Namespace for the K8s secret (default: cnpg-system)
#
# Requires: mc (MinIO client) and kubectl in PATH.

set -euo pipefail

MINIO_ENDPOINT="${MINIO_ENDPOINT:-${1:-http://minio.minio-system.svc:9000}}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-${2:-minioadmin}}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-${3:-minioadmin}}"
MINIO_ALIAS="${MINIO_ALIAS:-haven-minio}"
BUCKET_NAME="${BUCKET_NAME:-haven-backups}"
K8S_NAMESPACE="${K8S_NAMESPACE:-cnpg-system}"

echo "==> Configuring MinIO client alias: ${MINIO_ALIAS}"
mc alias set "${MINIO_ALIAS}" "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}"

echo "==> Creating bucket: ${BUCKET_NAME}"
if mc ls "${MINIO_ALIAS}/${BUCKET_NAME}" &>/dev/null; then
    echo "    Bucket already exists — skipping create."
else
    mc mb "${MINIO_ALIAS}/${BUCKET_NAME}"
    echo "    Bucket created."
fi

echo "==> Setting versioning on ${BUCKET_NAME}"
mc version enable "${MINIO_ALIAS}/${BUCKET_NAME}"

echo "==> Setting lifecycle: delete objects older than 90 days"
mc ilm add \
    --expiry-days 90 \
    "${MINIO_ALIAS}/${BUCKET_NAME}"

# ---------------------------------------------------------------------------
# Per-tenant prefix placeholders (informational — created on first backup)
# ---------------------------------------------------------------------------
# Prefix layout:
#   haven-backups/{tenant_slug}/postgres/   CNPG WAL + base backups
#   haven-backups/{tenant_slug}/mysql/      Percona XtraDB backups
#   haven-backups/{tenant_slug}/mongodb/    Percona MongoDB backups
#
# ArgoCD / the API creates a per-tenant .keep object so the "directories"
# are visible in the MinIO console.

echo "==> Bucket structure:"
echo "    haven-backups/{tenant_slug}/postgres/"
echo "    haven-backups/{tenant_slug}/mysql/"
echo "    haven-backups/{tenant_slug}/mongodb/"

# ---------------------------------------------------------------------------
# K8s Secret: backup-s3-credentials
# ---------------------------------------------------------------------------
echo "==> Creating K8s Secret backup-s3-credentials in namespace ${K8S_NAMESPACE}"

# Strip trailing slash from endpoint for the S3 endpoint field
MINIO_ENDPOINT_CLEAN="${MINIO_ENDPOINT%/}"

kubectl create secret generic backup-s3-credentials \
    --namespace="${K8S_NAMESPACE}" \
    --from-literal=ACCESS_KEY_ID="${MINIO_ACCESS_KEY}" \
    --from-literal=ACCESS_SECRET_KEY="${MINIO_SECRET_KEY}" \
    --from-literal=S3_ENDPOINT="${MINIO_ENDPOINT_CLEAN}" \
    --from-literal=BUCKET_NAME="${BUCKET_NAME}" \
    --dry-run=client -o yaml | kubectl apply -f -

echo "==> Secret applied: backup-s3-credentials"
echo ""
echo "Done. MinIO bucket '${BUCKET_NAME}' is ready for CNPG barman backups."
echo "CNPG clusters should reference:"
echo "  destinationPath: s3://${BUCKET_NAME}/{tenant_slug}/postgres"
echo "  endpointURL: ${MINIO_ENDPOINT_CLEAN}"
