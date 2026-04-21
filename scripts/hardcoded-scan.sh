#!/usr/bin/env bash
# scripts/hardcoded-scan.sh
#
# Rule 1 of iac-discipline.md: "No hardcoded environment values".
# This scanner catches P0 and P1 hardcoded literals across the repo
# using `git grep` (portable, respects .gitignore automatically).
#
# Usage:
#   scripts/hardcoded-scan.sh                 # report mode, exit 0
#   scripts/hardcoded-scan.sh --fail-on-p0    # exit 1 if any P0 present
#   scripts/hardcoded-scan.sh --baseline      # rewrite baseline file
#   scripts/hardcoded-scan.sh --diff          # compare to baseline, exit 1 on new hits
#
# Categories (P0 = severe, P1 = painful):
#   P0 literal_pwd   — known dev defaults: Harbor12345, dev-placeholder, overnight-dev-*, etc.
#   P0 sslip         — legacy 46.225.42.2.sslip.io references
#   P0 cluster_ip    — hardcoded public IPs (prod-only-specific) in non-tfvars files
#   P1 domain        — *.iyziops.com literal in code
#   P1 namespace     — literal "haven-system" in backend services
#   P1 tenant_demo   — tenant-demo / sprint-demo / demo-tenant in prod code
#   P1 localhost     — localhost:PORT defaults in non-test code

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BASELINE_FILE="scripts/.hardcoded-baseline.txt"
MODE="report"
for arg in "$@"; do
  case "$arg" in
    --fail-on-p0) MODE="fail-on-p0" ;;
    --baseline)   MODE="baseline" ;;
    --diff)       MODE="diff" ;;
    --help|-h)    sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# Path excludes via git pathspec.
# Note: macOS git requires `:(glob,exclude)**/pattern` for recursive globs;
# plain `:!tests` matches top-level only so nested test dirs are added.
PATH_EXCLUDES=(
  ':(glob,exclude)**/node_modules/**'
  ':(glob,exclude)**/.next/**'
  ':(glob,exclude)**/.venv/**'
  ':(glob,exclude)**/__pycache__/**'
  ':(glob,exclude)**/.pytest_cache/**'
  ':(glob,exclude)**/playwright-report/**'
  ':(glob,exclude)**/test-results/**'
  ':(glob,exclude)**/*.spec.ts'
  ':(glob,exclude)**/*.test.ts'
  ':(glob,exclude)**/*test*.py'
  ':(glob,exclude)**/*.md'
  ':!tests'
  ':!api/tests'
  ':!ui/tests'
  ':!logs'
  ':!dist'
  ':!build'
  ':!.github'
  ':!docs'
  ':!scripts/hardcoded-scan.sh'
  ':!scripts/.hardcoded-baseline.txt'
  ':(glob,exclude)**/terraform.tfvars*'
  ':(glob,exclude)**/kubeconfig'
  ':(glob,exclude)**/*.pem'
  ':(glob,exclude)**/package-lock.json'
  ':(glob,exclude)**/go.sum'
  ':(glob,exclude)**/poetry.lock'
)

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

grep_hits() {
  local severity="$1"
  local category="$2"
  local pattern="$3"
  # git grep -E uses extended POSIX regex; -n line numbers; -I skip binary
  local results
  results=$(git grep -nIE "$pattern" -- . "${PATH_EXCLUDES[@]}" 2>/dev/null || true)
  if [[ -n "$results" ]]; then
    while IFS= read -r line; do
      printf '%s\t%s\t%s\n' "$severity" "$category" "$line" >> "$TMP"
    done <<< "$results"
  fi
}

# --- P0 literal passwords / placeholders ---
grep_hits P0 literal_pwd 'Harbor12345'
grep_hits P0 literal_pwd 'dev-placeholder'
grep_hits P0 literal_pwd 'overnight-dev-key-do-not-use'
grep_hits P0 literal_pwd 'overnight-dev-nextauth-secret-do-not-use'
grep_hits P0 literal_pwd 'keycloak-admin-dev-2026'
grep_hits P0 literal_pwd 'haven-platform-db-2026'
grep_hits P0 literal_pwd 'haven-ui-dev-secret-2026'
grep_hits P0 literal_pwd 'admin-iyziops-2026'
grep_hits P0 literal_pwd 'gitea-admin-dev-2026'
grep_hits P0 literal_pwd 'changeme'
grep_hits P0 literal_pwd '"placeholder"'
grep_hits P0 literal_pwd "'placeholder'"
grep_hits P0 literal_pwd 'test123456'

# --- P0 sslip ---
grep_hits P0 sslip '46\.225\.42\.2\.sslip\.io'

# --- P0 cluster IPs in code ---
grep_hits P0 cluster_ip '46\.225\.(42|154)\.[0-9]+'
grep_hits P0 cluster_ip '135\.181\.[0-9]+\.[0-9]+'

# --- P1 domain strings in code ---
grep_hits P1 domain '(harbor|api|keycloak|gitea|argocd|grafana|minio|s3)\.iyziops\.com'

# --- P1 namespace literals ---
grep_hits P1 namespace '"haven-system"'

# --- P1 tenant-demo / sprint-demo / demo-tenant ---
grep_hits P1 tenant_demo 'tenant-demo|sprint-demo|demo-tenant'

# --- P1 localhost defaults in prod code ---
grep_hits P1 localhost 'localhost:(3000|3001|3002|8000|5432|6379|8080|8200|9000|9001)'

# --- Sort & count ---
if [[ ! -s "$TMP" ]]; then
  echo "✅ Zero hardcoded hits across repo (after excludes)."
  exit 0
fi

sort -u "$TMP" -o "$TMP"
p0_count=$(awk -F'\t' '$1=="P0"' "$TMP" | wc -l | tr -d ' ')
p1_count=$(awk -F'\t' '$1=="P1"' "$TMP" | wc -l | tr -d ' ')
total=$(wc -l < "$TMP" | tr -d ' ')

case "$MODE" in
  baseline)
    mkdir -p "$(dirname "$BASELINE_FILE")"
    cp "$TMP" "$BASELINE_FILE"
    echo "Baseline rewritten: $BASELINE_FILE"
    echo "P0=$p0_count  P1=$p1_count  total=$total"
    exit 0
    ;;
  diff)
    if [[ ! -f "$BASELINE_FILE" ]]; then
      echo "No baseline yet; run --baseline first." >&2
      exit 2
    fi
    NEW=$(comm -23 "$TMP" "$BASELINE_FILE" || true)
    if [[ -z "$NEW" ]]; then
      echo "✅ No new hardcoded hits beyond baseline."
      exit 0
    fi
    echo "❌ New hardcoded hits beyond baseline:"
    echo "$NEW"
    exit 1
    ;;
  fail-on-p0)
    echo "=== Hardcoded scan report ==="
    echo "  P0=$p0_count  P1=$p1_count  total=$total"
    if [[ "$p0_count" -gt 0 ]]; then
      echo "--- P0 hits ---"
      awk -F'\t' '$1=="P0"' "$TMP" | head -80
      exit 1
    fi
    echo "(No P0; $p1_count P1 in report)"
    exit 0
    ;;
  report)
    echo "=== Hardcoded scan report ==="
    echo "  P0=$p0_count  P1=$p1_count  total=$total"
    echo "--- top P0 (80) ---"
    awk -F'\t' '$1=="P0"' "$TMP" | head -80 || true
    echo
    echo "--- top P1 (40) ---"
    awk -F'\t' '$1=="P1"' "$TMP" | head -40 || true
    echo
    echo "Run with --baseline to snapshot, --diff for regression check, --fail-on-p0 for CI gate."
    exit 0
    ;;
esac
