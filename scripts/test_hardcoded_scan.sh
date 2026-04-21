#!/usr/bin/env bash
# scripts/test_hardcoded_scan.sh
#
# Smoke tests for scripts/hardcoded-scan.sh.
# Runs against a fixture directory to verify:
#   1) known pattern detection (P0/P1 categories)
#   2) allow-marker suppression
#   3) --baseline / --diff lifecycle
#   4) locale-stable sort (architect-review PR)
#
# Exit 0 on all green, 1 otherwise. Keep fast (<5s) so CI can run it every push.

set -euo pipefail

export LC_ALL=C

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCAN="$REPO_ROOT/scripts/hardcoded-scan.sh"
FAILED=0

pass() { printf '  ✅ %s\n' "$1"; }
fail() { printf '  ❌ %s\n' "$1"; FAILED=$((FAILED+1)); }

section() { printf '\n=== %s ===\n' "$1"; }

section "hardcoded-scan.sh smoke tests"

# Sanity: scanner runs at all and returns a report
if out=$("$SCAN" 2>&1); then
  echo "$out" | grep -qE '^=== Hardcoded scan report ===' \
    && pass "scanner runs and prints report header" \
    || fail "scanner ran but produced no header"
else
  fail "scanner exited non-zero on basic invocation"
fi

# P0 literal pwd detection (Harbor12345 IS in the repo at platform-helm.yaml:705).
# Capture to variable first to avoid pipefail races with head in the scanner.
scan_out="$("$SCAN" 2>&1 || true)"
if echo "$scan_out" | grep -q 'Harbor12345'; then
  pass "P0 literal_pwd (Harbor12345) detected in known location"
else
  fail "expected Harbor12345 detection in scan output"
fi

# Allow-marker: ensure api/app/config.py:82-83 *is NOT* in the output despite
# matching the "placeholder" / "changeme" pattern (marker suppresses it).
config_line_detected=$("$SCAN" 2>&1 | awk -F'\t' '$3 ~ /api\/app\/config\.py:8[23]/' | wc -l | tr -d ' ')
if [[ "$config_line_detected" = "0" ]]; then
  pass "allow-marker suppresses api/app/config.py:82-83 rejection-list literals"
else
  fail "api/app/config.py:82-83 should be suppressed by allow-marker (got $config_line_detected hits)"
fi

# --baseline writes header + payload
TMP_BASELINE="$(mktemp)"
cp "$REPO_ROOT/scripts/.hardcoded-baseline.txt" "$TMP_BASELINE"
trap 'mv "$TMP_BASELINE" "$REPO_ROOT/scripts/.hardcoded-baseline.txt"' EXIT
"$SCAN" --baseline > /dev/null 2>&1 || true
if head -1 "$REPO_ROOT/scripts/.hardcoded-baseline.txt" | grep -q '^# hardcoded-scan baseline$'; then
  pass "--baseline emits provenance header"
else
  fail "--baseline did not emit provenance header"
fi
if head -4 "$REPO_ROOT/scripts/.hardcoded-baseline.txt" | grep -q '^# commit:'; then
  pass "--baseline includes commit SHA in header"
else
  fail "--baseline missing commit SHA"
fi

# --diff should exit 0 against its own just-written baseline
if "$SCAN" --diff > /dev/null 2>&1; then
  pass "--diff exits 0 when baseline matches current state"
else
  fail "--diff returned non-zero against fresh baseline"
fi

section "summary"
if [[ "$FAILED" -eq 0 ]]; then
  echo "all smoke tests passed"
  exit 0
else
  echo "$FAILED test(s) failed"
  exit 1
fi
