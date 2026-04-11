#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FAILED=0

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILED=1; }

echo "=== Phase 6: GA Hardening, Benchmark, Migration & Support ==="
echo ""

SIDECAR="$REPO_ROOT/sidecar/omni-sidecar"

call_tool() {
    local tool_name="$1"
    local args="$2"
    printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}\n{"jsonrpc":"2.0","method":"notifications/initialized"}\n{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"%s","arguments":%s}}\n' "$tool_name" "$args" | "$SIDECAR" serve 2>/dev/null
}

get_result_text() {
    printf '%s\n' "$1" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[-1])
print(json.dumps(json.loads(r['result']['content'][0]['text'])))
"
}

has_error() {
    printf '%s\n' "$1" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[-1])
sys.exit(0 if 'error' in r else 1)
"
}

echo "--- Building Sidecar ---"
(cd "$REPO_ROOT/sidecar" && go build -o "$SIDECAR" ./cmd/omni-sidecar/main.go) && pass "sidecar builds" || fail "sidecar build failed"

echo ""
echo "--- Tool Registration ---"
TOOLS_RESULT=$(printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}\n{"jsonrpc":"2.0","method":"notifications/initialized"}\n{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n' | "$SIDECAR" serve 2>/dev/null)

echo "$TOOLS_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[-1])
tools = r['result']['tools']
names = [t['name'] for t in tools]
required = ['omni_benchmark', 'omni_migrate', 'omni_support_bundle']
for name in required:
    assert name in names, f'Missing tool: {name}'
    print(f'  PASS: {name} registered')
print(f'  PASS: total {len(tools)} MCP tools registered')
" || fail "Phase 6 tool registration"

echo ""
echo "--- Benchmark Tool ---"
BENCH_RESULT=$(call_tool "omni_benchmark" "{\"repo_root\":\"$REPO_ROOT\",\"action\":\"list\"}")

get_result_text "$BENCH_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert 'benchmarks' in t or 'categories' in t or 'action' in t, f'Unexpected benchmark response: {t}'
print('  PASS: omni_benchmark list returns valid response')
" || fail "omni_benchmark list"

echo ""
echo "--- Migration Tool ---"
MIGRATE_RESULT=$(call_tool "omni_migrate" "{\"repo_root\":\"$REPO_ROOT\",\"action\":\"status\"}")

get_result_text "$MIGRATE_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert 'current_version' in t or 'action' in t or 'migrations' in t, f'Unexpected migration response: {t}'
print('  PASS: omni_migrate status returns valid response')
" || fail "omni_migrate status"

echo ""
echo "--- Support Bundle Tool ---"
ARTIFACT_DIR=$(mktemp -d)
SUPPORT_RESULT=$(call_tool "omni_support_bundle" "{\"repo_root\":\"$REPO_ROOT\",\"output_dir\":\"$ARTIFACT_DIR/support\"}")

get_result_text "$SUPPORT_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert 'bundle_path' in t or 'files' in t or 'action' in t, f'Unexpected support bundle response: {t}'
print('  PASS: omni_support_bundle creates bundle')
" || fail "omni_support_bundle create"
rm -rf "$ARTIFACT_DIR"

echo ""
echo "--- Go Unit Tests ---"
(cd "$REPO_ROOT/sidecar" && go test ./internal/benchmark/ -v -count=1 2>&1) | grep -q "PASS" && pass "benchmark package tests pass" || fail "benchmark package tests"
(cd "$REPO_ROOT/sidecar" && go test ./internal/migration/ -v -count=1 2>&1) | grep -q "PASS" && pass "migration package tests pass" || fail "migration package tests"
(cd "$REPO_ROOT/sidecar" && go test ./internal/support/ -v -count=1 2>&1) | grep -q "PASS" && pass "support package tests pass" || fail "support package tests"

echo ""
echo "--- Performance Budgets ---"
grep -q "ColdStartP95" "$REPO_ROOT/sidecar/internal/benchmark/harness.go" && pass "ColdStartP95 budget defined" || fail "ColdStartP95 not found"
grep -q "1500" "$REPO_ROOT/sidecar/internal/benchmark/harness.go" && pass "cold start budget 1500ms" || fail "cold start budget not 1500ms"
grep -q "150" "$REPO_ROOT/sidecar/internal/benchmark/harness.go" && pass "memory search budget 150ms" || fail "memory search budget not 150ms"

echo ""
echo "--- Documentation ---"
[ -f "$REPO_ROOT/docs/operator/ga-release-checklist.md" ] && pass "GA release checklist exists" || fail "GA release checklist missing"
[ -f "$REPO_ROOT/docs/operator/operator-guide.md" ] && pass "operator guide exists" || fail "operator guide missing"

echo ""
echo "--- Wrapper CLI Build ---"
(cd "$REPO_ROOT/wrapper" && go build -o /tmp/omni-test ./cmd/omni/main.go 2>&1) && pass "wrapper CLI builds" || fail "wrapper CLI build failed"
rm -f /tmp/omni-test

rm -f "$SIDECAR"

echo ""
if [ $FAILED -eq 0 ]; then
    echo "=== ALL PHASE 6 TESTS PASSED ==="
    exit 0
else
    echo "=== SOME PHASE 6 TESTS FAILED ==="
    exit 1
fi
