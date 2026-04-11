#!/usr/bin/env bash
# Offline installer for Copilot Omni
# Usage: ./install-offline.sh [--bundle-dir <path>] [--target <path>] [--skip-validate]
#
# Installs a pre-built release bundle into a target directory without
# requiring internet access. Validates checksums before installing.
# Supports Linux and macOS. Windows install deferred to GA phase (Phase 6).
set -euo pipefail

sha256_hash() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    elif command -v openssl >/dev/null 2>&1; then
        openssl dgst -sha256 "$1" | awk '{print $NF}'
    else
        echo "ERROR: no sha256 tool found (tried sha256sum, shasum, openssl)" >&2
        exit 1
    fi
}

resolve_path() {
    if command -v realpath >/dev/null 2>&1; then
        realpath "$1" 2>/dev/null && return 0
    fi
    if command -v readlink >/dev/null 2>&1 && readlink -f / >/dev/null 2>&1; then
        readlink -f "$1" 2>/dev/null && return 0
    fi
    return 1
}

resolve_existing_parent() {
    local p="$1"
    while [[ -n "$p" && "$p" != "/" ]]; do
        local resolved
        resolved="$(resolve_path "$p")" && echo "$resolved" && return 0
        p="$(dirname "$p")"
    done
    return 1
}

path_contained() {
    local base="$1"
    local candidate="$2"
    local abs_base
    abs_base="$(resolve_path "$base")" || return 1
    local abs_candidate
    abs_candidate="$(resolve_path "$candidate")" 2>/dev/null
    if [[ -n "$abs_candidate" ]]; then
        if [[ "$abs_candidate" != "$abs_base" && "$abs_candidate" != "$abs_base/"* ]]; then
            return 1
        fi
        return 0
    fi
    local abs_parent
    abs_parent="$(resolve_existing_parent "$candidate")" || return 1
    if [[ "$abs_parent" != "$abs_base" && "$abs_parent" != "$abs_base/"* ]]; then
        return 1
    fi
    return 0
}

BUNDLE_DIR=""
TARGET_DIR="/usr/local"
SKIP_VALIDATE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bundle-dir)
            BUNDLE_DIR="$2"
            shift 2
            ;;
        --target)
            TARGET_DIR="$2"
            shift 2
            ;;
        --skip-validate)
            SKIP_VALIDATE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--bundle-dir <path>] [--target <path>] [--skip-validate]"
            echo ""
            echo "  --bundle-dir   Path to the release bundle directory"
            echo "  --target       Installation target directory (default: /usr/local)"
            echo "  --skip-validate  Skip bundle checksum validation"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$BUNDLE_DIR" ]]; then
    BUNDLE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
fi

if [[ ! -d "$BUNDLE_DIR" ]]; then
    echo "ERROR: Bundle directory not found: $BUNDLE_DIR" >&2
    exit 1
fi

MANIFEST="$BUNDLE_DIR/release-manifest.json"
if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: release-manifest.json not found in bundle directory" >&2
    exit 1
fi

echo "=== Copilot Omni Offline Installer ==="
echo "Bundle: $BUNDLE_DIR"
echo "Target: $TARGET_DIR"
echo ""

if [[ "$SKIP_VALIDATE" == false ]]; then
    echo "Validating bundle checksums..."

    CHECKSUMS_FILE="$BUNDLE_DIR/checksums.txt"
    if [[ ! -f "$CHECKSUMS_FILE" ]]; then
        echo "ERROR: checksums.txt not found in bundle" >&2
        exit 1
    fi

    HAS_MANIFEST_ENTRY=false
    HAS_SBOM_ENTRY=false
    FAILED=0
    while IFS= read -r line; do
        EXPECTED=$(echo "$line" | awk '{print $1}')
        FILE=$(echo "$line" | awk '{print $2}')
        if [[ -z "$FILE" ]]; then
            continue
        fi
        if [[ "$FILE" == "release-manifest.json" ]]; then
            HAS_MANIFEST_ENTRY=true
        fi
        if [[ "$FILE" == "sbom.json" ]]; then
            HAS_SBOM_ENTRY=true
        fi
        FILEPATH="$BUNDLE_DIR/$FILE"
        if ! path_contained "$BUNDLE_DIR" "$FILEPATH"; then
            echo "  FAIL: $FILE path escapes bundle directory"
            FAILED=1
            continue
        fi
        if [[ ! -f "$FILEPATH" ]]; then
            echo "  FAIL: $FILE missing from bundle"
            FAILED=1
            continue
        fi
        ACTUAL=$(sha256_hash "$FILEPATH")
        if [[ "$ACTUAL" != "$EXPECTED" ]]; then
            echo "  FAIL: $FILE checksum mismatch (expected $EXPECTED, got $ACTUAL)"
            FAILED=1
        else
            echo "  OK: $FILE"
        fi
    done < "$CHECKSUMS_FILE"

    if [[ "$HAS_MANIFEST_ENTRY" == false ]]; then
        echo "  FAIL: checksums.txt missing required entry: release-manifest.json" >&2
        FAILED=1
    fi
    if [[ "$HAS_SBOM_ENTRY" == false ]]; then
        echo "  FAIL: checksums.txt missing required entry: sbom.json" >&2
        FAILED=1
    fi

    if [[ $FAILED -ne 0 ]]; then
        echo "" >&2
        echo "ERROR: Bundle validation failed. Aborting installation." >&2
        exit 1
    fi
    echo "All checksums verified."
fi

echo ""
echo "Installing components..."

PRODUCT=$(grep -o '"product"[[:space:]]*:[[:space:]]*"[^"]*"' "$MANIFEST" | head -1 | sed 's/.*:.*"\([^"]*\)"/\1/' 2>/dev/null || echo "unknown")
VERSION=$(grep -o '"release_tag"[[:space:]]*:[[:space:]]*"[^"]*"' "$MANIFEST" | head -1 | sed 's/.*:.*"\([^"]*\)"/\1/' 2>/dev/null || echo "unknown")

echo "Product: $PRODUCT"
echo "Version: $VERSION"
echo ""

INSTALL_DIR="$TARGET_DIR/share/copilot-omni"
BIN_DIR="$TARGET_DIR/bin"

mkdir -p "$INSTALL_DIR" "$BIN_DIR"

COMPONENTS=$(grep -o '"path"[[:space:]]*:[[:space:]]*"[^"]*"' "$MANIFEST" | sed 's/.*:.*"\([^"]*\)"/\1/' 2>/dev/null || true)

while IFS= read -r component; do
    [[ -z "$component" ]] && continue
    SRC="$BUNDLE_DIR/$component"
    DEST="$INSTALL_DIR/$component"
    if ! path_contained "$BUNDLE_DIR" "$SRC"; then
        echo "  SKIP: $component (source escapes bundle directory)" >&2
        continue
    fi
    if ! path_contained "$INSTALL_DIR" "$DEST"; then
        echo "  SKIP: $component (destination escapes install directory)" >&2
        continue
    fi
    if [[ ! -f "$SRC" ]]; then
        echo "  SKIP: $component (not found)"
        continue
    fi

    mkdir -p "$(dirname "$DEST")"
    cp "$SRC" "$DEST"
    chmod 755 "$DEST"

    BASENAME=$(basename "$component")
    case "$BASENAME" in
        omni-sidecar)
            ln -sf "$DEST" "$BIN_DIR/omni-sidecar"
            echo "  Installed: $component -> $BIN_DIR/omni-sidecar"
            ;;
        omni)
            ln -sf "$DEST" "$BIN_DIR/omni"
            echo "  Installed: $component -> $BIN_DIR/omni"
            ;;
        *)
            echo "  Installed: $component"
            ;;
    esac
done <<< "$COMPONENTS"

cp "$MANIFEST" "$INSTALL_DIR/release-manifest.json"

echo ""
echo "=== Installation Complete ==="
echo "Installed to: $INSTALL_DIR"
echo "Binaries linked in: $BIN_DIR"
echo ""
echo "Ensure $BIN_DIR is in your PATH, then run:"
echo "  omni doctor"
