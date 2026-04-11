#!/usr/bin/env bash
# Offline installer for Copilot Omni
# Usage: ./install-offline.sh [--bundle-dir <path>] [--target <path>] [--skip-validate]
#
# Installs a pre-built release bundle into a target directory without
# requiring internet access. Validates checksums before installing.
set -euo pipefail

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
    BUNDLE_DIR="$(cd "$(dirname "$0")/.." && pwd)/.omni/bundle"
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
        echo "WARNING: checksums.txt not found, skipping validation"
    else
        FAILED=0
        while IFS= read -r line; do
            EXPECTED=$(echo "$line" | awk '{print $1}')
            FILE=$(echo "$line" | awk '{print $2}')
            if [[ -z "$FILE" ]]; then
                continue
            fi
            FILEPATH="$BUNDLE_DIR/$FILE"
            if [[ ! -f "$FILEPATH" ]]; then
                echo "  FAIL: $FILE missing from bundle"
                FAILED=1
                continue
            fi
            ACTUAL=$(sha256sum "$FILEPATH" | awk '{print $1}')
            if [[ "$ACTUAL" != "$EXPECTED" ]]; then
                echo "  FAIL: $FILE checksum mismatch (expected $EXPECTED, got $ACTUAL)"
                FAILED=1
            else
                echo "  OK: $FILE"
            fi
        done < "$CHECKSUMS_FILE"

        if [[ $FAILED -ne 0 ]]; then
            echo "" >&2
            echo "ERROR: Bundle validation failed. Aborting installation." >&2
            exit 1
        fi
        echo "All checksums verified."
    fi
fi

echo ""
echo "Installing components..."

PRODUCT=$(python3 -c "import json; print(json.load(open('$MANIFEST'))['product'])" 2>/dev/null || echo "unknown")
VERSION=$(python3 -c "import json; print(json.load(open('$MANIFEST'))['release_tag'])" 2>/dev/null || echo "unknown")

echo "Product: $PRODUCT"
echo "Version: $VERSION"
echo ""

INSTALL_DIR="$TARGET_DIR/share/copilot-omni"
BIN_DIR="$TARGET_DIR/bin"

mkdir -p "$INSTALL_DIR" "$BIN_DIR"

COMPONENTS=$(python3 -c "
import json
m = json.load(open('$MANIFEST'))
for c in m.get('components', []):
    print(c['path'])
" 2>/dev/null || true)

while IFS= read -r component; do
    [[ -z "$component" ]] && continue
    SRC="$BUNDLE_DIR/$component"
    if [[ ! -f "$SRC" ]]; then
        echo "  SKIP: $component (not found)"
        continue
    fi

    DEST="$INSTALL_DIR/$component"
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
