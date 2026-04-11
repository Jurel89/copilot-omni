#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAILED=0

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILED=1; }

echo "=== Phase 5: Enterprise, Offline Distribution & Operability ==="
echo ""

echo "--- Release Bundle ---"
ARTIFACT_DIR=$(mktemp -d)
mkdir -p "$ARTIFACT_DIR/.omni/runs/test-run-p5"

BUNDLE_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_release_bundle","arguments":{"repo_root":"'"$REPO_ROOT"'","action":"create","output_dir":"'"$ARTIFACT_DIR"'/bundle","release_tag":"v0.1.0","platform":"linux/amd64"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$BUNDLE_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
text = json.loads(r['result']['content'][0]['text'])
assert text['action'] == 'create', f'Expected action=create, got {text}'
assert 'manifest_path' in text, 'Missing manifest_path'
print('  PASS: omni_release_bundle create returns ok')
" || fail "omni_release_bundle create"

[ -f "$ARTIFACT_DIR/bundle/release-manifest.json" ] && pass "release manifest created" || fail "release manifest missing"
[ -f "$ARTIFACT_DIR/bundle/checksums.txt" ] && pass "checksums file created" || fail "checksums file missing"

printf '%s\n' "$BUNDLE_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
text = json.loads(r['result']['content'][0]['text'])
assert text['action'] == 'create'
assert text['release_tag'] == 'v0.1.0'
print('  PASS: release manifest has correct structure')
" || fail "release manifest structure"

echo ""
echo "--- Policy Pack Validation ---"
POLICY_PACK_DIR="$ARTIFACT_DIR/policies"
mkdir -p "$POLICY_PACK_DIR"
cat > "$POLICY_PACK_DIR/test-pack.json" <<'PACK_EOF'
{
  "name": "test-policy",
  "version": "1",
  "profile": "standard",
  "description": "Test policy pack",
  "rules": [
    {
      "id": "deny-sudo",
      "category": "commands",
      "severity": "critical",
      "description": "Deny sudo commands",
      "check_type": "deny_list",
      "values": ["sudo"],
      "enabled": true
    },
    {
      "id": "max-turns",
      "category": "tools",
      "severity": "medium",
      "description": "Limit autopilot turns",
      "check_type": "max_value",
      "values": ["10"],
      "enabled": true
    }
  ]
}
PACK_EOF

POLICY_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_policy_pack_validate","arguments":{"repo_root":"'"$REPO_ROOT"'","pack_path":"'"$POLICY_PACK_DIR"'/test-pack.json"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$POLICY_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
text = json.loads(r['result']['content'][0]['text'])
assert text['valid'] == True, f'Expected valid=True, got {text}'
assert len(text.get('rule_results', [])) == 2, f'Expected 2 rule results'
print('  PASS: policy pack validates successfully')
" || fail "policy pack validation"

echo ""
echo "--- Audit Export ---"
mkdir -p "$ARTIFACT_DIR/.omni/runs/test-run-p5"
cat > "$ARTIFACT_DIR/.omni/runs/test-run-p5/run.json" <<'RUN_EOF'
{"status": "done", "profile": "standard"}
RUN_EOF

AUDIT_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_audit_export","arguments":{"repo_root":"'"$ARTIFACT_DIR"'","run_id":"test-run-p5"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$AUDIT_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
text = json.loads(r['result']['content'][0]['text'])
assert text['run_id'] == 'test-run-p5', f'Expected run_id test-run-p5, got {text.get(\"run_id\")}'
assert text['run_status'] == 'done', f'Expected status done, got {text.get(\"run_status\")}'
assert text['redacted'] == True, 'Expected redacted=True'
print('  PASS: audit export returns run trail')
" || fail "audit export"

echo ""
echo "--- Enterprise Diagnostics ---"
DIAG_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_enterprise_diagnose","arguments":{"repo_root":"'"$REPO_ROOT"'"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$DIAG_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
text = json.loads(r['result']['content'][0]['text'])
assert 'platform' in text, 'Missing platform'
assert 'checks' in text, 'Missing checks'
assert isinstance(text['checks'], list), 'Checks should be a list'
assert len(text['checks']) > 0, 'No checks returned'
print('  PASS: enterprise diagnostics returns compatibility report')
" || fail "enterprise diagnostics"

echo ""
echo "--- Enterprise Config ---"
CONFIG_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_config_resolve","arguments":{"repo_root":"'"$REPO_ROOT"'"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$CONFIG_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
text = json.loads(r['result']['content'][0]['text'])
assert 'enterprise' in text, 'Missing enterprise config section'
ent = text['enterprise']
assert ent['offline_mode'] == False, f'Expected offline_mode=False, got {ent}'
assert ent['audit_retention_days'] > 0, f'Expected positive audit_retention_days'
assert ent['signing_enabled'] == False, f'Expected signing_enabled=False for standard'
print('  PASS: enterprise config in resolved config')
" || fail "enterprise config in config resolve"

echo ""
echo "--- Offline Install Script ---"
[ -f "$REPO_ROOT/scripts/install-offline.sh" ] && pass "install-offline.sh exists" || fail "install-offline.sh missing"
[ -x "$REPO_ROOT/scripts/install-offline.sh" ] && pass "install-offline.sh is executable" || fail "install-offline.sh not executable"

echo ""
echo "--- Wrapper Commands ---"
"$REPO_ROOT/wrapper/omni" --help 2>&1 | grep -q "audit" && pass "wrapper audit command listed" || fail "wrapper audit command missing"
"$REPO_ROOT/wrapper/omni" --help 2>&1 | grep -q "bundle" && pass "wrapper bundle command listed" || fail "wrapper bundle command missing"

rm -rf "$ARTIFACT_DIR"

echo ""
if [ $FAILED -eq 0 ]; then
    echo "=== ALL PHASE 5 TESTS PASSED ==="
    exit 0
else
    echo "=== SOME PHASE 5 TESTS FAILED ==="
    exit 1
fi
