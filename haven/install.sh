#!/usr/bin/env bash
# =============================================================================
# Haven CLI installer — official VNG Haven Compliancy Checker
# =============================================================================
# Downloads the pinned version (see VERSION file) from the GitLab package
# registry, extracts it, and installs to haven/bin/haven.
#
# Idempotent: noop if the correct version is already installed.
# Upgrade path: edit haven/VERSION, then run this script (or `make haven-install`).
#
# Source: https://gitlab.com/commonground/haven/haven
# Docs:   https://haven.commonground.nl/techniek/compliancy-checker
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(tr -d '[:space:]' < "$SCRIPT_DIR/VERSION")"
BIN_DIR="$SCRIPT_DIR/bin"
BIN="$BIN_DIR/haven"

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

# ----- Download --------------------------------------------------------------

# GitLab generic package URL quirk:
#   - path version is WITHOUT the "v" prefix (12.8.0)
#   - file name IS WITH the "v" prefix (haven-v12.8.0-...)
VERSION_NO_V="${VERSION#v}"
ZIP="haven-${VERSION}-${OS}-${ARCH}.zip"
URL="https://gitlab.com/api/v4/projects/commonground%2Fhaven%2Fhaven/packages/generic/cli/${VERSION_NO_V}/${ZIP}"

mkdir -p "$BIN_DIR"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "→ Downloading Haven CLI $VERSION ($OS-$ARCH)..."
if ! curl -fsSL --retry 3 --retry-delay 2 -o "$TMP/$ZIP" "$URL"; then
    echo "Failed to download $URL" >&2
    echo "Check network connectivity and that version $VERSION exists on GitLab." >&2
    exit 1
fi

echo "→ Extracting..."
unzip -q -o "$TMP/$ZIP" -d "$TMP"

# Archive layout from VNG: <os>-<arch>/haven
SRC="$TMP/${OS}-${ARCH}/haven"
if [[ ! -f "$SRC" ]]; then
    echo "Archive layout unexpected; searching for haven binary..." >&2
    SRC="$(find "$TMP" -type f -name haven 2>/dev/null | head -1 || true)"
fi

if [[ -z "${SRC:-}" || ! -f "$SRC" ]]; then
    echo "Could not locate haven binary in archive $ZIP" >&2
    exit 1
fi

install -m 0755 "$SRC" "$BIN"

echo "→ Installed: $("$BIN" version 2>&1 | head -1)"
echo "→ Location:  $BIN"
