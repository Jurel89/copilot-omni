#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAILED=0

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILED=1; }

echo "=== Phase 3 Integration Tests ==="
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
for name in ['omni_memory_search', 'omni_memory_capture', 'omni_memory_ingest', 'omni_memory_wipe', 'omni_memory_export', 'omni_memory_prune']:
    assert name in tool_names, f'Missing tool: {name}'
")

[ "$TOOL_COUNT" = "28" ] && pass "28 MCP tools registered" || fail "expected 28 tools, got $TOOL_COUNT"

echo ""
echo "--- Memory Capture ---"

MEM_DIR=$(mktemp -d)
mkdir -p "$MEM_DIR/.omni"

CAPTURE_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_memory_capture","arguments":{"repo_root":"'"$MEM_DIR"'","title":"Test Decision","content":"We chose SQLite over PostgreSQL for local storage because it requires no server process","type":"decision","tags":["architecture","database"]}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$CAPTURE_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
assert 'error' not in r, f'Error in response: {r}'
text = json.loads(r['result']['content'][0]['text'])
assert text.get('status') == 'ok', f'Expected ok, got: {text}'
assert 'id' in text, f'Missing id: {text}'
assert text.get('type') == 'decision', f'Expected decision type, got: {text}'
assert text.get('sensitivity') == 'normal', f'Expected normal sensitivity, got: {text}'
print('  PASS: memory capture creates record with id and correct metadata')
" || fail "memory capture"

echo ""
echo "--- Memory Search ---"

SEARCH_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_memory_search","arguments":{"repo_root":"'"$MEM_DIR"'","query":"SQLite local storage","limit":5}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$SEARCH_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
assert 'error' not in r, f'Error: {r}'
text = json.loads(r['result']['content'][0]['text'])
assert text.get('total', 0) >= 1, f'Expected at least 1 result, got: {text}'
records = text.get('records', [])
assert len(records) >= 1, f'Expected at least 1 record'
assert 'SQLite' in records[0]['record']['content'], f'Content should mention SQLite'
print('  PASS: memory search finds captured record by query terms')
" || fail "memory search"

echo ""
echo "--- Memory Search by Type ---"

SEARCH_TYPE=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_memory_search","arguments":{"repo_root":"'"$MEM_DIR"'","type":"decision","limit":10}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$SEARCH_TYPE" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
text = json.loads(r['result']['content'][0]['text'])
assert text.get('total', 0) >= 1, f'Expected at least 1 decision'
for rec in text.get('records', []):
    assert rec['record']['type'] == 'decision', f'All results should be decisions'
print('  PASS: memory search filters by type')
" || fail "memory search by type"

echo ""
echo "--- Secret Redaction ---"

SECRET_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_memory_capture","arguments":{"repo_root":"'"$MEM_DIR"'","title":"Secret test","content":"The API key is sk-1234567890abcdefghijklmnop and the token is ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345678","type":"note"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$SECRET_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
text = json.loads(r['result']['content'][0]['text'])
assert text.get('redacted') == True, f'Expected redacted=True, got: {text}'
assert text.get('sensitivity') == 'sensitive', f'Expected sensitive, got: {text}'
print('  PASS: secrets are redacted and sensitivity is auto-upgraded')
" || fail "secret redaction"

rm -rf "$MEM_DIR"

echo ""
echo "--- Memory Ingest ---"

INGEST_DIR=$(mktemp -d)
INGEST_RUN_ID="run-1700000099"
mkdir -p "$INGEST_DIR/.omni/runs/$INGEST_RUN_ID" "$INGEST_DIR/.omni/specs" "$INGEST_DIR/.omni/plans" "$INGEST_DIR/.omni/decisions"

echo "# Test Spec

## Objective
Build a memory system

## Requirements
- SQLite storage
- Fast search

## Acceptance Criteria
- Memory search works
" > "$INGEST_DIR/.omni/specs/$INGEST_RUN_ID.md"

echo "{\"run_id\":\"$INGEST_RUN_ID\",\"version\":\"1\",\"tasks\":[{\"id\":\"task-1\",\"title\":\"Create store\",\"description\":\"Build SQLite store\",\"dependencies\":[],\"file_targets\":[\"sidecar/internal/memory/store.go\"],\"verification_cmd\":\"go build ./...\",\"rollback_note\":\"Delete memory package\"}]}" > "$INGEST_DIR/.omni/plans/$INGEST_RUN_ID.json"

echo "# Decisions

## ADR-001: Use SQLite
We chose SQLite because it is embedded and requires no server.
" > "$INGEST_DIR/.omni/decisions/$INGEST_RUN_ID.md"

echo "{\"id\":\"$INGEST_RUN_ID\",\"status\":\"done\",\"current_phase\":\"done\",\"prompt\":\"Add memory\",\"created_at\":\"2024-01-01T00:00:00Z\",\"updated_at\":\"2024-01-01T01:00:00Z\"}" > "$INGEST_DIR/.omni/runs/$INGEST_RUN_ID/run.json"

INGEST_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_memory_ingest","arguments":{"repo_root":"'"$INGEST_DIR"'","run_id":"'"$INGEST_RUN_ID"'"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$INGEST_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
assert 'error' not in r, f'Error: {r}'
text = json.loads(r['result']['content'][0]['text'])
assert text.get('status') == 'ok', f'Expected ok, got: {text}'
assert text.get('total_records', 0) >= 3, f'Expected at least 3 records after ingest (spec+plan+decision+summary), got: {text}'
print('  PASS: memory ingest captures spec, plan, decisions, and summary')
" || fail "memory ingest"

INGEST_SEARCH=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_memory_search","arguments":{"repo_root":"'"$INGEST_DIR"'","query":"SQLite embedded","run_id":"'"$INGEST_RUN_ID"'","limit":10}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$INGEST_SEARCH" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
text = json.loads(r['result']['content'][0]['text'])
assert text.get('total', 0) >= 1, f'Expected at least 1 result for ingested content'
print('  PASS: ingested artifacts are searchable')
" || fail "ingest search"

rm -rf "$INGEST_DIR"

echo ""
echo "--- Memory Export ---"

EXPORT_DIR=$(mktemp -d)
mkdir -p "$EXPORT_DIR/.omni"

EXPORT_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_memory_capture","arguments":{"repo_root":"'"$EXPORT_DIR"'","title":"Export test","content":"Test content for export","type":"note"}}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"omni_memory_export","arguments":{"repo_root":"'"$EXPORT_DIR"'"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$EXPORT_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[2])
assert 'error' not in r, f'Error: {r}'
text = r['result']['content'][0]['text']
records = json.loads(text)
assert isinstance(records, list), f'Expected list, got: {type(records)}'
assert len(records) >= 1, f'Expected at least 1 record in export'
print('  PASS: memory export returns valid JSON array of records')
" || fail "memory export"

rm -rf "$EXPORT_DIR"

echo ""
echo "--- Memory Wipe ---"

WIPE_DIR=$(mktemp -d)
mkdir -p "$WIPE_DIR/.omni"

WIPE_RESULT=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_memory_capture","arguments":{"repo_root":"'"$WIPE_DIR"'","title":"Wipe test","content":"Will be wiped","type":"note"}}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"omni_memory_wipe","arguments":{"repo_root":"'"$WIPE_DIR"'","scope":"project"}}}
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"omni_memory_search","arguments":{"repo_root":"'"$WIPE_DIR"'","limit":10}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$WIPE_RESULT" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
wipe_r = json.loads(lines[2])
wipe_text = json.loads(wipe_r['result']['content'][0]['text'])
assert wipe_text.get('status') == 'ok', f'Wipe should succeed, got: {wipe_text}'

search_r = json.loads(lines[3])
search_text = json.loads(search_r['result']['content'][0]['text'])
assert search_text.get('total', -1) == 0, f'Expected 0 records after wipe, got: {search_text}'
print('  PASS: memory wipe removes all project records')
" || fail "memory wipe"

rm -rf "$WIPE_DIR"

echo ""
echo "--- Doctor Memory Check ---"

DOCTOR_DIR=$(mktemp -d)
mkdir -p "$DOCTOR_DIR/.omni" "$DOCTOR_DIR/plugin"

echo '{"name":"test","version":"1.0.0"}' > "$DOCTOR_DIR/plugin/plugin.json"
echo '{"mcpServers":{"test":{}}}' > "$DOCTOR_DIR/plugin/.mcp.json"
echo '{"version":1,"hooks":{}}' > "$DOCTOR_DIR/plugin/hooks.json"

DOCTOR_NO_DB=$(echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"omni_doctor","arguments":{"repo_root":"'"$DOCTOR_DIR"'"}}}' | "$REPO_ROOT/sidecar/omni-sidecar" serve 2>/dev/null)

printf '%s\n' "$DOCTOR_NO_DB" | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
r = json.loads(lines[1])
text = json.loads(r['result']['content'][0]['text'])
diagnostics = text.get('diagnostics', [])
memory_diag = [d for d in diagnostics if d['name'] == 'MemoryDatabase']
assert len(memory_diag) == 1, f'Expected MemoryDatabase diagnostic'
assert memory_diag[0]['status'] == 'warn', f'Expected warn for missing DB, got: {memory_diag[0]}'
print('  PASS: doctor detects missing memory database')
" || fail "doctor memory check (no db)"

rm -rf "$DOCTOR_DIR"

echo ""
echo "--- Config Retention Settings ---"

python3 -c "
import json
with open('$REPO_ROOT/profiles/standard/config.json') as f:
    cfg = json.load(f)
assert cfg['memory']['retention_days'] == 90, f'Standard profile should have 90 day retention'
assert cfg['memory']['auto_ingest'] == True, f'Standard profile should have auto_ingest enabled'
print('  PASS: standard profile has Phase 3 memory config')
" || fail "standard profile memory config"

python3 -c "
import json
with open('$REPO_ROOT/profiles/strict/config.json') as f:
    cfg = json.load(f)
assert cfg['memory']['retention_days'] == 30, f'Strict profile should have 30 day retention'
print('  PASS: strict profile has shorter retention')
" || fail "strict profile memory config"

python3 -c "
import json
with open('$REPO_ROOT/profiles/permissive/config.json') as f:
    cfg = json.load(f)
assert cfg['memory']['retention_days'] == 365, f'Permissive profile should have 365 day retention'
print('  PASS: permissive profile has longer retention')
" || fail "permissive profile memory config"

echo ""
echo "--- Wrapper Build ---"

(cd "$REPO_ROOT/wrapper" && go build ./cmd/omni/) && pass "wrapper builds" || fail "wrapper build"

echo ""
echo "--- Previous Phase Tests ---"

bash "$REPO_ROOT/test/integration-phase1.sh" > /dev/null 2>&1 && pass "Phase 1 tests still pass" || fail "Phase 1 regression"
bash "$REPO_ROOT/test/integration-phase2.sh" > /dev/null 2>&1 && pass "Phase 2 tests still pass" || fail "Phase 2 regression"

echo ""
if [ "$FAILED" -eq 0 ]; then
    echo "=== ALL PHASE 3 TESTS PASSED ==="
else
    echo "=== SOME PHASE 3 TESTS FAILED ==="
    exit 1
fi
