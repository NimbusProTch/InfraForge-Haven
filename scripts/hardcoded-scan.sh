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
#   P0 literal_pwd     — known dev defaults: Harbor12345, dev-placeholder, etc.
#   P0 generic_secret  — AWS keys, GitHub PATs, PEM blocks, common weak passwords
#   P0 sslip           — legacy 46.225.42.2.sslip.io references
#   P0 cluster_ip      — hardcoded public IPs (prod-only-specific)
#   P1 domain          — *.iyziops.com literal in code
#   P1 namespace       — literal "haven-system" in backend services
#   P1 tenant_demo     — tenant-demo / sprint-demo / demo-tenant
#   P1 localhost       — localhost:PORT defaults in non-test code
#
# Inline allow-marker:
#   A source line containing `# hardcoded-scan: allow` (or `// hardcoded-scan: allow`)
#   is ignored even if it matches a pattern. Use for rejection-list literals
#   (e.g. `"placeholder"` inside a guard tuple that says "reject this string").

set -euo pipefail

# Locale-stable sort across runners
export LC_ALL=C

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BASELINE_FILE="scripts/.hardcoded-baseline.txt"
MODE="report"
for arg in "$@"; do
  case "$arg" in
    --fail-on-p0) MODE="fail-on-p0" ;;
    --baseline)   MODE="baseline" ;;
    --diff)       MODE="diff" ;;
    --help|-h)    sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# Path excludes via git pathspec.
# macOS git requires `:(glob,exclude)**/pattern` for recursive globs;
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
  # git grep -E uses extended POSIX regex; -n line numbers; -I skip binary.
  # Filter out any line carrying the allow-marker, plus container image
  # digest pins (e.g. `image: harbor.iyziops.com/...@sha256:...`) which are
  # auto-managed CI pins and drift on every merge to main — not hardcoded
  # environment values in the Rule 1 sense.
  local results
  results=$(git grep -nIE "$pattern" -- . "${PATH_EXCLUDES[@]}" 2>/dev/null \
              | grep -v 'hardcoded-scan: allow' \
              | grep -vE 'image:[[:space:]]+.*@sha256:' || true)
  if [[ -n "$results" ]]; then
    while IFS= read -r line; do
      printf '%s\t%s\t%s\n' "$severity" "$category" "$line" >> "$TMP"
    done <<< "$results"
  fi
}

# --- P0 literal passwords / placeholders (known dev defaults) ---
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

# --- P0 generic high-entropy secret patterns (architect-review additions) ---
# AWS access key
grep_hits P0 generic_secret 'AKIA[0-9A-Z]{16}'
# AWS session token marker
grep_hits P0 generic_secret 'aws_session_token'
# GitHub PAT (classic)
grep_hits P0 generic_secret 'ghp_[A-Za-z0-9]{36}'
# GitHub fine-grained PAT
grep_hits P0 generic_secret 'github_pat_[A-Za-z0-9_]{82}'
# Slack bot token
grep_hits P0 generic_secret 'xoxb-[0-9]+-[0-9]+-[A-Za-z0-9]+'
# Private key blocks
grep_hits P0 generic_secret 'BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY'
# Very common weak passwords likely to appear as dev defaults
grep_hits P0 generic_secret '(password|admin|root)(123|1234|12345)'
grep_hits P0 generic_secret 'welcome1'
grep_hits P0 generic_secret 'Pa\$\$w0rd'
grep_hits P0 generic_secret 'Password1!'

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

write_baseline_with_header() {
  local target="$1"
  local tmp_with_header
  tmp_with_header="$(mktemp)"
  {
    echo "# hardcoded-scan baseline"
    echo "# generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "# commit:    $(git rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "# P0=$p0_count  P1=$p1_count  total=$total"
    echo "#"
    cat "$TMP"
  } > "$tmp_with_header"
  mv "$tmp_with_header" "$target"
}

# When diffing, strip header lines from both files (lines starting with #).
strip_header() {
  grep -v '^#' "$1" 2>/dev/null || true
}

case "$MODE" in
  baseline)
    mkdir -p "$(dirname "$BASELINE_FILE")"
    write_baseline_with_header "$BASELINE_FILE"
    echo "Baseline rewritten: $BASELINE_FILE"
    echo "P0=$p0_count  P1=$p1_count  total=$total"
    exit 0
    ;;
  diff)
    if [[ ! -f "$BASELINE_FILE" ]]; then
      echo "No baseline yet; run --baseline first." >&2
      exit 2
    fi
    BASELINE_PAYLOAD="$(mktemp)"
    CURRENT_PAYLOAD="$(mktemp)"
    trap 'rm -f "$TMP" "$BASELINE_PAYLOAD" "$CURRENT_PAYLOAD"' EXIT
    strip_header "$BASELINE_FILE" | sort -u > "$BASELINE_PAYLOAD"
    sort -u "$TMP" > "$CURRENT_PAYLOAD"
    NEW=$(comm -23 "$CURRENT_PAYLOAD" "$BASELINE_PAYLOAD" || true)
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
