#!/usr/bin/env bash
# scripts/test_destroy_safety.sh
#
# Drift guard for the destroy-safety fixes that keep `tofu destroy` clean.
# These fixes have been silently absent before (documented in CLAUDE.md as
# "fixed" while missing from code), which burned trust. This guard makes that
# class of doc-vs-code drift fail CI instead of going unnoticed.
#
# Asserts:
#   1) C14 — CCM route-controller is disabled (`--controllers=*,-route`) so the
#      cloud route-controller stops writing orphan routes that hang subnet
#      deletion on destroy.
#   2) Bring-up safety net — the Gateway API CRDs are still applied in master
#      cloud-init (`kubectl apply --server-side`). If this ever disappears, a
#      fresh cluster ships with no Gateway/ingress.
#   3) C16 design lock — no `when = destroy` local-exec provisioner has been
#      (re-)introduced into the hetzner-infra module. The provisioner approach
#      was evaluated and rejected (needs the unused hcloud CLI + token plumbing
#      and reintroduces bash-in-HCL, iac-discipline Rule 2). This assertion
#      stops a future reader from "re-fixing" the rejected design.
#
# Exit 0 on all green, 1 otherwise. Keep fast (<2s) so CI runs it every push.

set -euo pipefail

export LC_ALL=C

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CCM="$REPO_ROOT/infrastructure/modules/rke2-cluster/manifests/hetzner-ccm.yaml.tpl"
CLOUD_INIT="$REPO_ROOT/infrastructure/modules/rke2-cluster/templates/master-cloud-init.yaml.tpl"
HETZNER_INFRA_DIR="$REPO_ROOT/infrastructure/modules/hetzner-infra"
FAILED=0

pass() { printf '  ✅ %s\n' "$1"; }
fail() { printf '  ❌ %s\n' "$1"; FAILED=$((FAILED+1)); }

section() { printf '\n=== %s ===\n' "$1"; }

section "destroy-safety drift guard"

# 1) C14 — route-controller disabled
if grep -qF -- '--controllers=*,-route' "$CCM"; then
  pass "C14: CCM route-controller disabled (--controllers=*,-route present)"
else
  fail "C14 REGRESSION: --controllers=*,-route missing from hetzner-ccm.yaml.tpl → orphan routes will hang destroy"
fi

# 2) Bring-up safety net — Gateway API CRDs still applied in cloud-init
if grep -qE 'apply --server-side' "$CLOUD_INIT"; then
  pass "bring-up: Gateway API CRDs still applied in master cloud-init"
else
  fail "BRING-UP REGRESSION: 'apply --server-side' for Gateway API CRDs missing from master cloud-init"
fi

# 3) C16 design lock — rejected destroy provisioner must not reappear anywhere
#    in the hetzner-infra module (scan the whole dir, not just main.tf, so a
#    provisioner re-introduced in a sibling .tf — nat.tf etc. — can't evade it).
if grep -rqE 'when[[:space:]]*=[[:space:]]*destroy' "$HETZNER_INFRA_DIR" --include='*.tf'; then
  fail "C16 design drift: a 'when = destroy' provisioner reappeared in hetzner-infra/ (rejected approach — see CLAUDE.md C16)"
else
  pass "C16: no rejected 'when = destroy' provisioner anywhere in hetzner-infra/"
fi

section "summary"
if [[ "$FAILED" -eq 0 ]]; then
  echo "all destroy-safety assertions passed"
  exit 0
else
  echo "$FAILED assertion(s) failed"
  exit 1
fi
