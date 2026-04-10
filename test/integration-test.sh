#!/usr/bin/env bash
set -euo pipefail

# Integration test for Copilot Omni Phase 0
# Validates the full plugin + sidecar + wrapper system

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAILED=0

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILED=1; }

echo "=== Copilot Omni Integration Tests ==="
echo ""

echo "--- Plugin Structure ---"
# Check plugin manifest exists and is valid JSON
python3 -c "import json; d=json.load(open('$REPO_ROOT/plugin/plugin.json')); assert d['name']=='copilot-omni'; assert d['version']=='0.1.0'" && pass "plugin.json valid" || fail "plugin.json invalid"

# Check MCP config
python3 -c "import json; d=json.load(open('$REPO_ROOT/plugin/.mcp.json')); assert 'copilot-omni-sidecar' in d['mcpServers']" && pass ".mcp.json valid" || fail ".mcp.json invalid"

# Check hooks config
python3 -c "import json; d=json.load(open('$REPO_ROOT/plugin/hooks.json')); assert d['version']==1; assert 'preToolUse' in d['hooks']" && pass "hooks.json valid" || fail "hooks.json invalid"

# Check agents exist
for agent in conductor planner reviewer verifier; do
    [ -f "$REPO_ROOT/plugin/agents/omni-${agent}.agent.md" ] && pass "agent omni-${agent} exists" || fail "agent omni-${agent} missing"
done

# Check skills exist
for skill in init doctor run plan resume; do
    [ -f "$REPO_ROOT/plugin/skills/omni-${skill}/SKILL.md" ] && pass "skill omni-${skill} exists" || fail "skill omni-${skill} missing"
done

echo ""
echo "--- Sidecar Binary ---"
# Build sidecar
(cd "$REPO_ROOT/sidecar" && go build ./cmd/omni-sidecar/) && pass "sidecar builds" || fail "sidecar build failed"

# Create a temp artifact dir for read/write tests
ARTIFACT_DIR=$(mktemp -d)
mkdir -p "$ARTIFACT_DIR/.omni/runs/test-run-001"

# Test MCP protocol - send 8 JSON-RPC messages (init, notification, tools/list, 5 tool calls)
RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"omni_health","arguments":{}}}
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"omni_config_resolve","arguments":{"repo_root":"/tmp"}}}
{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"omni_doctor","arguments":{"repo_root":"/tmp"}}}
{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"omni_artifact_write","arguments":{"repo_root":"'"$ARTIFACT_DIR"'","run_id":"test-run-001","filename":"notes.md","content":"# Test Notes\nHello world"}}}
{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"omni_artifact_read","arguments":{"repo_root":"'"$ARTIFACT_DIR"'","run_id":"test-run-001","filename":"notes.md"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

# Verify initialize
printf '%s\n' "$RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
assert len(lines) == 7, f'Expected 7 responses, got {len(lines)}'
r = json.loads(lines[0])
assert r['result']['serverInfo']['name'] == 'copilot-omni-sidecar'
print('  PASS: MCP initialize handshake')
" || fail "MCP initialize"

# Verify tools/list has all 7 tools
printf '%s\n' "$RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
tools = json.loads(lines[1])
names = sorted([t['name'] for t in tools['result']['tools']])
expected = ['omni_artifact_read', 'omni_artifact_write', 'omni_config_resolve', 'omni_doctor', 'omni_guarded_patch', 'omni_health', 'omni_policy_check', 'omni_repo_map', 'omni_resume_context', 'omni_run_status', 'omni_verification_run']
assert names == expected, f'Wrong tools: {names}'
print('  PASS: All 11 MCP tools registered')
" || fail "tools/list"

# Verify omni_health
printf '%s\n' "$RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[2])
text = json.loads(r['result']['content'][0]['text'])
assert text['status'] == 'ok'
assert text['version'] == '0.1.0'
print('  PASS: omni_health returns ok')
" || fail "omni_health"

# Verify omni_config_resolve
printf '%s\n' "$RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[3])
text = json.loads(r['result']['content'][0]['text'])
assert text['version'] == '1'
assert 'policy' in text
print('  PASS: omni_config_resolve returns config')
" || fail "omni_config_resolve"

# Verify omni_doctor
printf '%s\n' "$RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[4])
text = json.loads(r['result']['content'][0]['text'])
assert text['version'] == '0.1.0'
assert 'diagnostics' in text
print('  PASS: omni_doctor returns report')
" || fail "omni_doctor"

# Verify omni_artifact_write
printf '%s\n' "$RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[5])
text = json.loads(r['result']['content'][0]['text'])
assert text['status'] == 'ok'
assert text['run_id'] == 'test-run-001'
assert 'test-run-001' in text['path']
print('  PASS: omni_artifact_write creates artifact')
" || fail "omni_artifact_write"

# Verify omni_artifact_read
printf '%s\n' "$RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[6])
text = r['result']['content'][0]['text']
assert 'Test Notes' in text
assert 'Hello world' in text
print('  PASS: omni_artifact_read returns content')
" || fail "omni_artifact_read"

# Verify artifact file exists on disk
[ -f "$ARTIFACT_DIR/.omni/runs/test-run-001/notes.md" ] && pass "artifact file exists on disk" || fail "artifact file missing on disk"

# Verify path traversal is rejected
TRAVERSAL_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_artifact_write","arguments":{"repo_root":"'"$ARTIFACT_DIR"'","run_id":"../../escape","filename":"evil.txt","content":"pwned"}}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"omni_artifact_read","arguments":{"repo_root":"'"$ARTIFACT_DIR"'","run_id":"../../escape","filename":"evil.txt"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$TRAVERSAL_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
write_result = json.loads(lines[1])
assert 'error' in write_result, f'Expected error for path traversal write, got: {write_result}'
read_result = json.loads(lines[2])
assert 'error' in read_result, f'Expected error for path traversal read, got: {read_result}'
print('  PASS: path traversal rejected')
" || fail "path traversal rejection"

# Cleanup artifact dir
rm -rf "$ARTIFACT_DIR"

echo ""
echo "--- Wrapper Binary ---"
# Build wrapper
(cd "$REPO_ROOT/wrapper" && go build ./cmd/omni/) && pass "wrapper builds" || fail "wrapper build failed"

# Test version
OUTPUT=$("$REPO_ROOT/wrapper/omni" version)
[ "$OUTPUT" = "omni v0.1.0" ] && pass "omni version correct" || fail "omni version wrong: $OUTPUT"

# Test usage
OUTPUT=$("$REPO_ROOT/wrapper/omni" 2>&1 || true)
[[ "$OUTPUT" == *"Usage: omni"* ]] && pass "usage message works" || fail "usage message missing"

echo ""
echo "--- Wrapper End-to-End ---"
# Create temp repo for e2e testing
E2E_DIR=$(mktemp -d)
cp -r "$REPO_ROOT/plugin" "$E2E_DIR/"
cp -r "$REPO_ROOT/sidecar" "$E2E_DIR/"
cp -r "$REPO_ROOT/wrapper" "$E2E_DIR/"
cp -r "$REPO_ROOT/templates" "$E2E_DIR/"
cp -r "$REPO_ROOT/profiles" "$E2E_DIR/"
(cd "$E2E_DIR/sidecar" && go build ./cmd/omni-sidecar/) && pass "e2e sidecar builds" || fail "e2e sidecar build"
(cd "$E2E_DIR/wrapper" && go build ./cmd/omni/) && pass "e2e wrapper builds" || fail "e2e wrapper build"

# Test omni init generates files
(cd "$E2E_DIR" && ./wrapper/omni init 2>/dev/null)
[ -f "$E2E_DIR/.omni/config.json" ] && pass "omni init creates config.json" || fail "omni init config.json missing"
[ -f "$E2E_DIR/.github/copilot-instructions.md" ] && pass "omni init creates copilot-instructions.md" || fail "omni init copilot-instructions.md missing"
[ -f "$E2E_DIR/.github/instructions/omni.instructions.md" ] && pass "omni init creates instructions/omni.instructions.md" || fail "omni init instructions/omni.instructions.md missing"
[ -f "$E2E_DIR/AGENTS.md" ] && pass "omni init creates AGENTS.md" || fail "omni init AGENTS.md missing"
grep -q 'omni:managed:start' "$E2E_DIR/.github/copilot-instructions.md" && pass "init output has managed regions" || fail "init output missing managed regions"

# Test omni doctor reports healthy after init
DOCTOR_OUTPUT=$(cd "$E2E_DIR" && ./wrapper/omni doctor 2>/dev/null)
echo "$DOCTOR_OUTPUT" | grep -q '"status":"healthy"' && pass "doctor reports healthy after init" || fail "doctor not healthy after init"

# Test config resolve returns non-empty policy arrays
CONFIG_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_config_resolve","arguments":{"repo_root":"'"$E2E_DIR"'"}}}' | "$E2E_DIR/sidecar/omni-sidecar" serve 2>/dev/null)
printf '%s\n' "$CONFIG_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
text = json.loads(r['result']['content'][0]['text'])
assert 'policy' in text, 'Missing policy key'
paths = text['policy'].get('protected_paths')
cmds = text['policy'].get('denied_commands')
assert isinstance(paths, list) and len(paths) > 0, f'protected_paths should be non-empty list, got: {paths}'
assert isinstance(cmds, list) and len(cmds) > 0, f'denied_commands should be non-empty list, got: {cmds}'
print('  PASS: config resolve has non-empty policy arrays')
" || fail "config resolve policy arrays"

# Test idempotent re-init preserves content
cp "$E2E_DIR/.github/copilot-instructions.md" /tmp/omni-test-original.md
(cd "$E2E_DIR" && ./wrapper/omni init 2>/dev/null)
diff /tmp/omni-test-original.md "$E2E_DIR/.github/copilot-instructions.md" && pass "re-init is idempotent" || fail "re-init changed managed content"

# Cleanup
rm -rf "$E2E_DIR" /tmp/omni-test-original.md

echo ""
echo "--- Profiles ---"
for profile in strict standard permissive; do
    python3 -c "import json; d=json.load(open('$REPO_ROOT/profiles/$profile/config.json')); assert d['profile']=='$profile'" && pass "profile $profile valid" || fail "profile $profile invalid"
done

echo ""
echo "--- Templates ---"
for tmpl in copilot-instructions.md.tmpl agents-md.md.tmpl instructions-md.md.tmpl config.json.tmpl; do
    [ -f "$REPO_ROOT/templates/$tmpl" ] && pass "template $tmpl exists" || fail "template $tmpl missing"
done

# Check managed region markers
for tmpl in copilot-instructions.md.tmpl agents-md.md.tmpl instructions-md.md.tmpl; do
    grep -q 'omni:managed:start' "$REPO_ROOT/templates/$tmpl" && grep -q 'omni:managed:end' "$REPO_ROOT/templates/$tmpl" && pass "$tmpl has managed regions" || fail "$tmpl missing managed regions"
done

echo ""
if [ $FAILED -eq 0 ]; then
    echo "=== ALL TESTS PASSED ==="
    exit 0
else
    echo "=== SOME TESTS FAILED ==="
    exit 1
fi
