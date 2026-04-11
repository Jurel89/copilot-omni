#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAILED=0

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILED=1; }

echo "=== Phase 4 Integration Tests ==="
echo ""

echo "--- Sidecar Build ---"

(cd "$REPO_ROOT/sidecar" && go build ./cmd/omni-sidecar/) && pass "sidecar builds" || fail "sidecar build failed"

echo ""
echo "--- Tool Registry (24 tools) ---"

TOOL_COUNT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
tools = r['result']['tools']
print(len(tools))
tool_names = [t['name'] for t in tools]
for name in ['omni_research', 'omni_subtask_create', 'omni_subtask_status', 'omni_workspace_create', 'omni_workspace_remove', 'omni_merge', 'omni_intent_route']:
    assert name in tool_names, f'Missing tool: {name}'
")

[ "$TOOL_COUNT" = "31" ] && pass "31 MCP tools registered" || fail "expected 31 tools, got $TOOL_COUNT"

echo ""
echo "--- Intent Routing ---"

ROUTE_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_intent_route","arguments":{"prompt":"research the best approach for database migration"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$ROUTE_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
assert 'error' not in r, f'Error in response: {r}'
text = json.loads(r['result']['content'][0]['text'])
assert text.get('intent') == 'research', f'Expected research intent, got: {text}'
assert text.get('route', {}).get('target') == 'omni-researcher', f'Expected omni-researcher target, got: {text}'
assert text.get('route', {}).get('confidence') == 'high', f'Expected high confidence, got: {text}'
print('  PASS: intent router classifies research intent correctly')
" || fail "intent routing"

echo ""
echo "--- Research Report ---"

RES_DIR=$(mktemp -d)
mkdir -p "$RES_DIR/.omni"

RESEARCH_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_research","arguments":{"repo_root":"'"$RES_DIR"'","run_id":"run-1700000044","query":"database migration strategies","web_results":"SQLite supports schema migrations natively\nPostgreSQL offers pg_dump for schema transfer","repo_evidence":"The project uses SQLite for local storage in sidecar/internal/memory/"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$RESEARCH_RESULT" | python3 -c "
import sys, json, os
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
assert 'error' not in r, f'Error in response: {r}'
text = json.loads(r['result']['content'][0]['text'])
assert text.get('run_id') == 'run-1700000044', f'Expected run-1700000044, got: {text}'
assert 'report_path' in text, f'Missing report_path: {text}'
assert text.get('findings', 0) >= 2, f'Expected at least 2 findings, got: {text}'
assert text.get('provenance', 0) >= 2, f'Expected at least 2 provenance entries, got: {text}'

report_path = text['report_path']
assert os.path.exists(report_path), f'Report file not found: {report_path}'
with open(report_path) as f:
    report = json.load(f)
assert report['query'] == 'database migration strategies', f'Query mismatch: {report}'
assert len(report['provenance']) >= 2, f'Expected 2 provenance entries'
assert len(report['findings']) >= 2, f'Expected 2 findings'
for finding in report['findings']:
    assert finding['category'] in ('fact', 'inference', 'open_question'), f'Invalid category: {finding}'
    assert finding['confidence'] in ('high', 'medium', 'low'), f'Invalid confidence: {finding}'
print('  PASS: research report generated with provenance and findings')
" || fail "research report"

echo ""
echo "--- Runtime Config Resolution ---"

python3 -c "
import json, subprocess, os, tempfile

dir = tempfile.mkdtemp()
os.makedirs(os.path.join(dir, '.omni'), exist_ok=True)

result = subprocess.run(
    ['$REPO_ROOT/sidecar/omni-sidecar', 'serve'],
    input='{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test\",\"version\":\"1.0.0\"}}}\n{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}\n{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"omni_config_resolve\",\"arguments\":{\"repo_root\":\"' + dir + '\"}}}',
    capture_output=True, text=True
)
lines = result.stdout.strip().split('\n')
r = json.loads(lines[1])
text = json.loads(r['result']['content'][0]['text'])
cfg = text.get('resolved_config', text)
research = cfg.get('research', {})
assert research.get('max_subtasks', 0) > 0, f'max_subtasks should be > 0, got: {research}'
assert research.get('parallel_read') == True, f'parallel_read should be True, got: {research}'
print(f'  PASS: runtime config resolves research.max_subtasks={research[\"max_subtasks\"]}, parallel_read={research[\"parallel_read\"]}')
" || fail "runtime config resolution"

echo ""
echo "--- Invalid Subtask Status Rejection ---"

INVALID_DIR=$(mktemp -d)
mkdir -p "$INVALID_DIR/.omni/runs/run-test-invalid"

echo "{\"run_id\":\"run-test-invalid\",\"parent_task\":\"task-1\",\"subtasks\":[{\"id\":\"sub-1\",\"title\":\"Test\",\"description\":\"Test\",\"mode\":\"read_only\",\"dependencies\":[],\"status\":\"pending\"}],\"created_at\":\"2024-01-01T00:00:00Z\"}" > "$INVALID_DIR/.omni/runs/run-test-invalid/subtask-manifest.json"

INVALID_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_subtask_status","arguments":{"repo_root":"'"$INVALID_DIR"'","run_id":"run-test-invalid","subtask_id":"sub-1","status":"banana"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$INVALID_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
assert 'error' in r, f'Expected error for invalid status, got success: {r}'
assert 'invalid subtask status' in r['error']['message'].lower(), f'Wrong error message: {r}'
print('  PASS: invalid subtask status rejected')
" || fail "invalid status rejection"

rm -rf "$INVALID_DIR"

echo ""
echo "--- Merge Unknown Subtask Rejection ---"

MERGE_REJ_DIR=$(mktemp -d)
mkdir -p "$MERGE_REJ_DIR/.omni/runs/run-test-merge-rej"

echo "{\"run_id\":\"run-test-merge-rej\",\"parent_task\":\"task-1\",\"subtasks\":[{\"id\":\"sub-1\",\"title\":\"Test\",\"description\":\"Test\",\"mode\":\"read_only\",\"dependencies\":[],\"status\":\"completed\"}],\"created_at\":\"2024-01-01T00:00:00Z\"}" > "$MERGE_REJ_DIR/.omni/runs/run-test-merge-rej/subtask-manifest.json"

MERGE_INVALID=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_merge","arguments":{"repo_root":"'"$MERGE_REJ_DIR"'","run_id":"run-test-merge-rej","decisions":[{"subtask_id":"nonexistent-sub","action":"accept"}]}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$MERGE_INVALID" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
assert 'error' in r, f'Expected error for unknown subtask, got success: {r}'
assert 'unknown subtask' in r['error']['message'].lower(), f'Wrong error message: {r}'
print('  PASS: merge rejects decisions for unknown subtasks')
" || fail "merge unknown subtask rejection"

rm -rf "$MERGE_REJ_DIR"

echo ""
echo "--- Subtask Manifest ---"

SUB_DIR=$(mktemp -d)
mkdir -p "$SUB_DIR/.omni"

SUBTASK_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_subtask_create","arguments":{"repo_root":"'"$SUB_DIR"'","run_id":"run-1700000044","parent_task":"task-1","manifest":{"run_id":"run-1700000044","parent_task":"task-1","subtasks":[{"id":"sub-1","title":"Explore schema","description":"Read schema files","mode":"read_only","dependencies":[]},{"id":"sub-2","title":"Implement migration","description":"Write migration code","mode":"write","dependencies":["sub-1"],"file_targets":["db/migrate.go"],"verification_cmd":"go build ./..."}]}}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$SUBTASK_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
assert 'error' not in r, f'Error in response: {r}'
text = json.loads(r['result']['content'][0]['text'])
assert text.get('status') == 'ok', f'Expected ok, got: {text}'
assert text.get('subtask_count') == 2, f'Expected 2 subtasks, got: {text}'
assert 'path' in text, f'Missing path: {text}'
print('  PASS: subtask manifest created with 2 subtasks')
" || fail "subtask create"

echo ""
echo "--- Subtask Status ---"

STATUS_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_subtask_status","arguments":{"repo_root":"'"$SUB_DIR"'","run_id":"run-1700000044","list_ready":true}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$STATUS_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
assert 'error' not in r, f'Error in response: {r}'
text = json.loads(r['result']['content'][0]['text'])
assert text.get('total_subtasks') == 2, f'Expected 2 subtasks, got: {text}'
ready = text.get('ready_subtasks', [])
assert 'sub-1' in ready, f'sub-1 should be ready, got: {ready}'
print('  PASS: subtask status lists ready subtasks correctly')
" || fail "subtask status"

echo ""
echo "--- Subtask Progress ---"

PROGRESS_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_subtask_status","arguments":{"repo_root":"'"$SUB_DIR"'","run_id":"run-1700000044","subtask_id":"sub-1","status":"completed"}}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"omni_subtask_status","arguments":{"repo_root":"'"$SUB_DIR"'","run_id":"run-1700000044","list_ready":true}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$PROGRESS_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
status_r = json.loads(lines[1])
assert 'error' not in status_r, f'Error: {status_r}'

ready_r = json.loads(lines[2])
ready_text = json.loads(ready_r['result']['content'][0]['text'])
ready = ready_text.get('ready_subtasks', [])
assert 'sub-2' in ready, f'sub-2 should be ready after sub-1 completes, got: {ready}'
print('  PASS: completing sub-1 makes sub-2 ready')
" || fail "subtask progress"

rm -rf "$SUB_DIR"

echo ""
echo "--- Workspace Create (Read-Only) ---"

WS_DIR=$(mktemp -d)
mkdir -p "$WS_DIR/.omni"

WS_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_workspace_create","arguments":{"repo_root":"'"$WS_DIR"'","subtask_id":"sub-1","is_write":false}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$WS_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
assert 'error' not in r, f'Error in response: {r}'
text = json.loads(r['result']['content'][0]['text'])
assert text.get('is_writeable') == False, f'Read-only workspace should not be writeable: {text}'
assert text.get('isolation') == 'tempdir', f'Expected tempdir isolation: {text}'
print('  PASS: read-only workspace created pointing to main repo root')
" || fail "workspace create (read-only)"

rm -rf "$WS_DIR"

echo ""
echo "--- Merge ---"

MERGE_DIR=$(mktemp -d)
mkdir -p "$MERGE_DIR/.omni/runs/run-1700000044"

echo "{\"run_id\":\"run-1700000044\",\"parent_task\":\"task-1\",\"subtasks\":[{\"id\":\"sub-1\",\"title\":\"Explore\",\"description\":\"Read\",\"mode\":\"read_only\",\"dependencies\":[],\"status\":\"completed\",\"started_at\":\"2024-01-01T00:00:00Z\",\"completed_at\":\"2024-01-01T01:00:00Z\"},{\"id\":\"sub-2\",\"title\":\"Implement\",\"description\":\"Write\",\"mode\":\"write\",\"dependencies\":[\"sub-1\"],\"file_targets\":[\"db/migrate.go\"],\"status\":\"completed\",\"started_at\":\"2024-01-01T01:00:00Z\",\"completed_at\":\"2024-01-01T02:00:00Z\"}],\"created_at\":\"2024-01-01T00:00:00Z\"}" > "$MERGE_DIR/.omni/runs/run-1700000044/subtask-manifest.json"

MERGE_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_merge","arguments":{"repo_root":"'"$MERGE_DIR"'","run_id":"run-1700000044","decisions":[{"subtask_id":"sub-1","action":"accept","reason":"No conflicts"},{"subtask_id":"sub-2","action":"accept","reason":"Clean implementation"}]}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$MERGE_RESULT" | python3 -c "
import sys, json, os
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
assert 'error' not in r, f'Error in response: {r}'
text = json.loads(r['result']['content'][0]['text'])
assert text.get('accepted') == 2, f'Expected 2 accepted, got: {text}'
assert text.get('rejected') == 0, f'Expected 0 rejected, got: {text}'
assert text.get('conflicts') == 0, f'Expected 0 conflicts, got: {text}'

merge_path = os.path.join('"$MERGE_DIR"', '.omni', 'runs', 'run-1700000044', 'merge-result.json')
assert os.path.exists(merge_path), f'Merge result file not found'
with open(merge_path) as f:
    merge_data = json.load(f)
assert merge_data['total_subtasks'] == 2, f'Expected 2 total subtasks'
print('  PASS: merge produces correct accept/reject/conflict counts and artifact')
" || fail "merge"

rm -rf "$MERGE_DIR"

echo ""
echo "--- Research Report Schema Validation ---"

python3 -c "
import json
with open('$REPO_ROOT/profiles/standard/config.json') as f:
    cfg = json.load(f)
assert 'research' in cfg, f'Standard profile should have research config'
assert cfg['research']['max_subtasks'] == 4, f'Standard should allow 4 subtasks'
assert cfg['research']['parallel_read'] == True, f'Standard should enable parallel read'
assert cfg['research']['parallel_write'] == False, f'Standard should disable parallel write'
print('  PASS: standard profile has Phase 4 research config')
" || fail "standard profile research config"

python3 -c "
import json
with open('$REPO_ROOT/profiles/strict/config.json') as f:
    cfg = json.load(f)
assert cfg['research']['max_subtasks'] == 2, f'Strict should allow 2 subtasks'
assert cfg['research']['parallel_write'] == False, f'Strict should disable parallel write'
print('  PASS: strict profile limits subtasks and disables parallel write')
" || fail "strict profile research config"

python3 -c "
import json
with open('$REPO_ROOT/profiles/permissive/config.json') as f:
    cfg = json.load(f)
assert cfg['research']['max_subtasks'] == 8, f'Permissive should allow 8 subtasks'
assert cfg['research']['parallel_write'] == True, f'Permissive should enable parallel write'
print('  PASS: permissive profile allows full parallelism')
" || fail "permissive profile research config"

echo ""
echo "--- Wrapper Build ---"

(cd "$REPO_ROOT/wrapper" && go build ./cmd/omni/) && pass "wrapper builds" || fail "wrapper build failed"

echo ""
echo "--- Previous Phase Tests ---"

bash "$REPO_ROOT/test/integration-phase1.sh" > /dev/null 2>&1 && pass "Phase 1 tests still pass" || fail "Phase 1 regression"
bash "$REPO_ROOT/test/integration-phase2.sh" > /dev/null 2>&1 && pass "Phase 2 tests still pass" || fail "Phase 2 regression"
bash "$REPO_ROOT/test/integration-phase3.sh" > /dev/null 2>&1 && pass "Phase 3 tests still pass" || fail "Phase 3 regression"

echo ""
if [ "$FAILED" -eq 0 ]; then
    echo "=== ALL PHASE 4 TESTS PASSED ==="
else
    echo "=== SOME PHASE 4 TESTS FAILED ==="
    exit 1
fi
