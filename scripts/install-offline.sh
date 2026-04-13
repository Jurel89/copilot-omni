#!/usr/bin/env bash
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
      echo "Usage: $0 [--bundle-dir <path>] [--target <path>]"
      echo
      echo "Thin Unix convenience wrapper for: omni bundle install"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$SKIP_VALIDATE" == true ]]; then
  echo "ERROR: --skip-validate is no longer supported; use 'omni bundle install' validation." >&2
  exit 1
fi

if [[ -z "$BUNDLE_DIR" ]]; then
  BUNDLE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
fi

if [[ ! -d "$BUNDLE_DIR" ]]; then
  echo "ERROR: Bundle directory not found: $BUNDLE_DIR" >&2
  exit 1
fi

OMNI_BIN="$BUNDLE_DIR/omni"
if [[ ! -x "$OMNI_BIN" ]]; then
  echo "ERROR: bundled omni binary not found or not executable at $OMNI_BIN" >&2
  exit 1
fi

echo "=== Copilot Omni Offline Installer Wrapper ==="
echo "Bundle: $BUNDLE_DIR"
echo "Target: $TARGET_DIR"
echo "Delegating to: $OMNI_BIN bundle install"
echo

exec "$OMNI_BIN" bundle install --bundle-dir "$BUNDLE_DIR" --target "$TARGET_DIR"
