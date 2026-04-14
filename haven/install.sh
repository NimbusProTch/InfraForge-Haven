#!/usr/bin/env bash
# =============================================================================
# Haven CLI installer — iyziops fork
# =============================================================================
# Downloads the pinned version (see VERSION file) from this repository's
# GitHub release (assets are pre-built from a tiny upstream patch that
# adds `HAVEN_RELEASES_URL` env-var support). Verifies SHA256 against
# haven/releases.json before installing.
#
# Idempotent: noop if the correct version is already installed.
# Upgrade path: edit haven/VERSION + haven/releases.json, then run this
# script (or `make haven-install`).
#
# Why a fork?
#   Upstream Haven CLI hardcodes `https://gitlab.com/.../releases.json` in
#   its bootstrap. Since Aug 2025 Cloudflare returns a bot-challenge page
#   for Go's default http.Client User-Agent, causing `haven check` to
#   fail with "Could not parse latest Haven releases". The fork adds one
#   function-level env-var shim — everything else is byte-identical to
#   upstream v12.8.0 (tag: 87047a70). Patch recipe is in PATCH.md.
#
# Upstream:  https://gitlab.com/commonground/haven/haven
# Fork:      https://github.com/NimbusProTch/InfraForge-Haven/releases
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(tr -d '[:space:]' < "$SCRIPT_DIR/VERSION")"
RELEASES_JSON="$SCRIPT_DIR/releases.json"
BIN_DIR="$SCRIPT_DIR/bin"
BIN="$BIN_DIR/haven"

GITHUB_REPO="NimbusProTch/InfraForge-Haven"
RELEASE_URL="https://github.com/${GITHUB_REPO}/releases/download/${VERSION}"

# ----- Already installed? Idempotent early exit ------------------------------

if [[ -x "$BIN" ]]; then
    current="$("$BIN" version 2>/dev/null | head -1 || echo none)"
    if [[ "$current" == *"$VERSION"* ]]; then
        echo "Haven CLI $VERSION already installed at $BIN"
        exit 0
    fi
    echo "Haven CLI version mismatch (have: $current, want: $VERSION), re-installing..."
fi

# ----- Detect OS / arch ------------------------------------------------------

case "$(uname -s)" in
    Darwin) OS=darwin ;;
    Linux)  OS=linux ;;
    *)
        echo "Unsupported OS: $(uname -s)" >&2
        exit 1
        ;;
esac

case "$(uname -m)" in
    x86_64|amd64)   ARCH=amd64 ;;
    arm64|aarch64)  ARCH=arm64 ;;
    *)
        echo "Unsupported arch: $(uname -m)" >&2
        exit 1
        ;;
esac

ASSET="haven-${OS}-${ARCH}"
URL="${RELEASE_URL}/${ASSET}"

# ----- Lookup expected SHA256 from releases.json -----------------------------

if [[ ! -f "$RELEASES_JSON" ]]; then
    echo "Missing $RELEASES_JSON — cannot verify download integrity." >&2
    exit 1
fi

EXPECTED_SHA="$(
    python3 - "$RELEASES_JSON" "$VERSION" "$OS/$ARCH" <<'PY'
import json, sys
path, version, key = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    data = json.load(f)
for r in data.get("releases", []):
    if r.get("version") == version:
        print(r.get("hashes", {}).get(key, ""))
        break
PY
)"

if [[ -z "$EXPECTED_SHA" ]]; then
    echo "No SHA256 entry for $OS/$ARCH $VERSION in $RELEASES_JSON" >&2
    exit 1
fi

# ----- Download --------------------------------------------------------------

mkdir -p "$BIN_DIR"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "→ Downloading Haven CLI $VERSION ($OS-$ARCH) from GitHub release..."
if ! curl -fsSL --retry 3 --retry-delay 2 -o "$TMP/$ASSET" "$URL"; then
    echo "Failed to download $URL" >&2
    echo "Check network connectivity and that version $VERSION exists on GitHub." >&2
    exit 1
fi

# ----- Verify SHA256 ---------------------------------------------------------

echo "→ Verifying SHA256..."
if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL_SHA="$(sha256sum "$TMP/$ASSET" | awk '{print $1}')"
else
    ACTUAL_SHA="$(shasum -a 256 "$TMP/$ASSET" | awk '{print $1}')"
fi

if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
    echo "SHA256 mismatch!" >&2
    echo "  expected: $EXPECTED_SHA" >&2
    echo "  actual:   $ACTUAL_SHA" >&2
    exit 1
fi

install -m 0755 "$TMP/$ASSET" "$BIN"

echo "→ Installed: $("$BIN" version 2>&1 | head -1)"
echo "→ Location:  $BIN"
