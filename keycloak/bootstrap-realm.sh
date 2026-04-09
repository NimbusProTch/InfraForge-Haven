#!/usr/bin/env bash
#
# bootstrap-realm.sh — render keycloak/haven-realm.json with secrets injected
# from environment variables and either (a) print to stdout, (b) write to a
# file, or (c) `kubectl exec` into the running Keycloak pod and import.
#
# Sprint H2 P7 (H2 #21): the haven-realm.json file used to carry hardcoded
# admin password and client secret values. Both are now `${VAR}` placeholders
# and this script does the substitution at deploy time, so the secrets never
# touch git.
#
# Usage:
#
#   # Just render to stdout (for piping into kc.sh / kcadm.sh)
#   HAVEN_REALM_ADMIN_PASSWORD='...' HAVEN_UI_CLIENT_SECRET='...' \
#       ./keycloak/bootstrap-realm.sh
#
#   # Render to a file (gitignored — see .gitignore)
#   HAVEN_REALM_ADMIN_PASSWORD='...' HAVEN_UI_CLIENT_SECRET='...' \
#       ./keycloak/bootstrap-realm.sh -o /tmp/haven-realm.rendered.json
#
#   # Render + import directly via kubectl exec
#   HAVEN_REALM_ADMIN_PASSWORD='...' HAVEN_UI_CLIENT_SECRET='...' \
#       ./keycloak/bootstrap-realm.sh --apply
#
# Required env vars:
#   HAVEN_REALM_ADMIN_PASSWORD   — bootstrap password for the realm 'admin' user
#   HAVEN_UI_CLIENT_SECRET       — OAuth client secret for the haven-ui client
#
# Optional env vars:
#   KUBECONFIG                   — when --apply is set, kubeconfig path
#   KEYCLOAK_NAMESPACE           — default 'keycloak'
#   KEYCLOAK_POD_LABEL           — default 'app=keycloak'

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$SCRIPT_DIR/haven-realm.json"

OUT_FILE=""
APPLY=0
NAMESPACE="${KEYCLOAK_NAMESPACE:-keycloak}"
POD_LABEL="${KEYCLOAK_POD_LABEL:-app=keycloak}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -o|--output)
            OUT_FILE="$2"
            shift 2
            ;;
        --apply)
            APPLY=1
            shift
            ;;
        -h|--help)
            sed -n '2,30p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

# ----- validation -----

if [[ -z "${HAVEN_REALM_ADMIN_PASSWORD:-}" ]]; then
    echo "ERROR: HAVEN_REALM_ADMIN_PASSWORD is not set" >&2
    exit 1
fi

if [[ -z "${HAVEN_UI_CLIENT_SECRET:-}" ]]; then
    echo "ERROR: HAVEN_UI_CLIENT_SECRET is not set" >&2
    exit 1
fi

if [[ ${#HAVEN_REALM_ADMIN_PASSWORD} -lt 16 ]]; then
    echo "ERROR: HAVEN_REALM_ADMIN_PASSWORD must be at least 16 characters" >&2
    exit 1
fi

if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: template not found: $TEMPLATE" >&2
    exit 1
fi

# ----- render -----
# `envsubst` is the safest substitution tool — it only replaces ${VAR} tokens
# that match exported env vars and leaves the rest of the JSON untouched.
# We export ONLY the two we want substituted, so accidental ${other} tokens
# in the realm JSON would be left alone.

if ! command -v envsubst >/dev/null 2>&1; then
    echo "ERROR: envsubst not found (install gettext: 'brew install gettext' or 'apt install gettext-base')" >&2
    exit 1
fi

RENDERED=$(envsubst '${HAVEN_REALM_ADMIN_PASSWORD} ${HAVEN_UI_CLIENT_SECRET}' < "$TEMPLATE")

# ----- output -----

if [[ -n "$OUT_FILE" ]]; then
    printf '%s\n' "$RENDERED" > "$OUT_FILE"
    chmod 600 "$OUT_FILE"
    echo "Wrote rendered realm to $OUT_FILE (mode 600)" >&2
elif [[ "$APPLY" -eq 1 ]]; then
    POD=$(kubectl get pods -n "$NAMESPACE" -l "$POD_LABEL" -o jsonpath='{.items[0].metadata.name}')
    if [[ -z "$POD" ]]; then
        echo "ERROR: no Keycloak pod found in namespace $NAMESPACE matching label $POD_LABEL" >&2
        exit 1
    fi
    echo "Importing realm into pod $POD..." >&2
    kubectl exec -n "$NAMESPACE" "$POD" -- sh -c '
        cat > /tmp/haven-realm.json
        /opt/keycloak/bin/kc.sh import --file=/tmp/haven-realm.json --override=true
        rm -f /tmp/haven-realm.json
    ' <<< "$RENDERED"
    echo "Realm imported. Verify with kubectl logs -n $NAMESPACE $POD" >&2
else
    printf '%s\n' "$RENDERED"
fi
