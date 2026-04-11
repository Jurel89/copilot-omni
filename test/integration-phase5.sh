#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAILED=0

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILED=1; }

echo "=== Phase 5: Enterprise, Offline Distribution & Operability ==="
echo ""

ARTIFACT_DIR=$(mktemp -d)
SIDECAR="$REPO_ROOT/sidecar/omni-sidecar"

call_tool() {
    local tool_name="$1"
    local args="$2"
    echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"'"$tool_name"'","arguments":'"$args"'}}' | "$SIDECAR" serve 2>/dev/null
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

echo "--- Release Bundle Create ---"
mkdir -p "$ARTIFACT_DIR/.omni/runs/test-run-p5"

BUNDLE_RESULT=$(call_tool "omni_release_bundle" "{\"repo_root\":\"$REPO_ROOT\",\"action\":\"create\",\"output_dir\":\"$ARTIFACT_DIR/bundle\",\"release_tag\":\"v0.1.0\",\"platform\":\"linux/amd64\"}")

BUNDLE_TEXT=$(get_result_text "$BUNDLE_RESULT") || true
echo "$BUNDLE_TEXT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t['action'] == 'create'
assert 'manifest_path' in t
assert t['components'] >= 2, f'Expected at least 2 components, got {t[\"components\"]}'
assert 'signing_enabled' in t
print('  PASS: omni_release_bundle create returns ok with components')
" || fail "omni_release_bundle create"

[ -f "$ARTIFACT_DIR/bundle/release-manifest.json" ] && pass "release manifest created" || fail "release manifest missing"
[ -f "$ARTIFACT_DIR/bundle/checksums.txt" ] && pass "checksums file created" || fail "checksums file missing"
[ -f "$ARTIFACT_DIR/bundle/sbom.json" ] && pass "SBOM file created" || fail "SBOM file missing"

echo "$BUNDLE_TEXT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t['release_tag'] == 'v0.1.0'
print('  PASS: bundle has correct release tag and metadata')
" || fail "bundle metadata"

echo ""
echo "--- Release Bundle Validate ---"
VALIDATE_RESULT=$(call_tool "omni_release_bundle" "{\"repo_root\":\"$REPO_ROOT\",\"action\":\"validate\",\"bundle_dir\":\"$ARTIFACT_DIR/bundle\"}")

VALIDATE_TEXT=$(get_result_text "$VALIDATE_RESULT") || true
echo "$VALIDATE_TEXT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t['valid'] == True, f'Bundle validation failed: {t}'
print('  PASS: bundle validates successfully (create→validate round-trip)')
" || fail "bundle validate round-trip"

echo ""
echo "--- Bundle Validation (corrupted checksums.txt) ---"
CORRUPT_BUNDLE="$ARTIFACT_DIR/bundle-corrupt"
cp -r "$ARTIFACT_DIR/bundle" "$CORRUPT_BUNDLE"
echo "deadbeefdeadbeef  omni-sidecar" > "$CORRUPT_BUNDLE/checksums.txt"

CORRUPT_RESULT=$(call_tool "omni_release_bundle" "{\"repo_root\":\"$REPO_ROOT\",\"action\":\"validate\",\"bundle_dir\":\"$CORRUPT_BUNDLE\"}")

get_result_text "$CORRUPT_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t['valid'] == False, f'Expected valid=False for corrupted checksums, got {t}'
print('  PASS: corrupted checksums.txt correctly detected')
" || fail "corrupted checksums detection"
rm -rf "$CORRUPT_BUNDLE"

echo ""
echo "--- Bundle Validation (missing component file) ---"
MISSING_BUNDLE="$ARTIFACT_DIR/bundle-missing"
cp -r "$ARTIFACT_DIR/bundle" "$MISSING_BUNDLE"
rm -f "$MISSING_BUNDLE/omni-sidecar"

MISSING_RESULT=$(call_tool "omni_release_bundle" "{\"repo_root\":\"$REPO_ROOT\",\"action\":\"validate\",\"bundle_dir\":\"$MISSING_BUNDLE\"}")

get_result_text "$MISSING_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t['valid'] == False, f'Expected valid=False for missing component, got {t}'
print('  PASS: missing component file correctly detected')
" || fail "missing component detection"
rm -rf "$MISSING_BUNDLE"

echo ""
echo "--- Bundle Validation (missing sbom.json) ---"
NOSBOM_BUNDLE="$ARTIFACT_DIR/bundle-nosbom"
cp -r "$ARTIFACT_DIR/bundle" "$NOSBOM_BUNDLE"
rm -f "$NOSBOM_BUNDLE/sbom.json"

NOSBOM_RESULT=$(call_tool "omni_release_bundle" "{\"repo_root\":\"$REPO_ROOT\",\"action\":\"validate\",\"bundle_dir\":\"$NOSBOM_BUNDLE\"}")

get_result_text "$NOSBOM_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t['valid'] == False, f'Expected valid=False for missing sbom.json, got {t}'
print('  PASS: missing sbom.json correctly detected')
" || fail "missing sbom.json detection"
rm -rf "$NOSBOM_BUNDLE"

echo ""
echo "--- Bundle Validation (tampered manifest components) ---"
TAMPERED_BUNDLE="$ARTIFACT_DIR/bundle-tampered"
cp -r "$ARTIFACT_DIR/bundle" "$TAMPERED_BUNDLE"
python3 -c "
import json
m = json.load(open('$TAMPERED_BUNDLE/release-manifest.json'))
for c in m.get('components', []):
    if c['name'] == 'omni-sidecar':
        c['checksum'] = 'deadbeef'
json.dump(m, open('$TAMPERED_BUNDLE/release-manifest.json', 'w'), indent=2)
"

TAMPERED_RESULT=$(call_tool "omni_release_bundle" "{\"repo_root\":\"$REPO_ROOT\",\"action\":\"validate\",\"bundle_dir\":\"$TAMPERED_BUNDLE\"}")

get_result_text "$TAMPERED_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t['valid'] == False, f'Expected valid=False for tampered component checksum, got {t}'
print('  PASS: tampered manifest checksum correctly detected')
" || fail "tampered manifest detection"
rm -rf "$TAMPERED_BUNDLE"

echo ""
echo "--- Policy Pack Runtime Enforcement ---"
STRICT_CHECK=$(call_tool "omni_policy_check" "{\"repo_root\":\"$REPO_ROOT\",\"operation\":\"command\",\"value\":\"sudo rm -rf /\"}")

get_result_text "$STRICT_CHECK" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t['allowed'] == False, f'Expected allowed=False for sudo rm -rf under strict profile, got {t}'
print('  PASS: shipped policy pack denies dangerous command at runtime')
" || fail "policy pack runtime enforcement"

echo ""
echo "--- Shipped Policy Packs ---"
for profile in strict standard permissive; do
    PACK="$REPO_ROOT/policies/$profile.json"
    [ -f "$PACK" ] && pass "policy pack $profile.json exists" || fail "policy pack $profile.json missing"
    python3 -c "import json; d=json.load(open('$PACK')); assert d['profile']=='$profile'; assert len(d['rules'])>0" && pass "policy pack $profile valid with rules" || fail "policy pack $profile invalid"
done

echo ""
echo "--- Policy Pack Validation (valid pack) ---"
VALID_POLICY_RESULT=$(call_tool "omni_policy_pack_validate" "{\"repo_root\":\"$REPO_ROOT\",\"pack_path\":\"$REPO_ROOT/policies/standard.json\"}")

get_result_text "$VALID_POLICY_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t['valid'] == True, f'Expected valid=True, got {t}'
assert len(t.get('rule_results', [])) > 0
print('  PASS: standard policy pack validates with rules')
" || fail "standard policy pack validation"

echo ""
echo "--- Policy Pack Validation (invalid pack) ---"
INVALID_PACK_DIR="$ARTIFACT_DIR/policies"
mkdir -p "$INVALID_PACK_DIR"
echo '{"name":"","version":"","profile":"nonexistent"}' > "$INVALID_PACK_DIR/invalid.json"

INVALID_RESULT=$(call_tool "omni_policy_pack_validate" "{\"repo_root\":\"$REPO_ROOT\",\"pack_path\":\"$INVALID_PACK_DIR/invalid.json\"}")

get_result_text "$INVALID_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t['valid'] == False, f'Expected valid=False for invalid pack, got {t}'
assert len(t.get('errors', [])) > 0, 'Expected errors'
print('  PASS: invalid policy pack correctly rejected')
" || fail "invalid policy pack rejection"

echo ""
echo "--- Policy Pack Validation (duplicate rule IDs) ---"
echo '{"name":"dup-test","version":"1","profile":"standard","rules":[{"id":"r1","category":"commands","severity":"high","description":"test","check_type":"deny_list","enabled":true},{"id":"r1","category":"tools","severity":"medium","description":"dup","check_type":"allow_list","enabled":true}]}' > "$INVALID_PACK_DIR/dup-rules.json"

DUP_RESULT=$(call_tool "omni_policy_pack_validate" "{\"repo_root\":\"$REPO_ROOT\",\"pack_path\":\"$INVALID_PACK_DIR/dup-rules.json\"}")

get_result_text "$DUP_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t['valid'] == False, f'Expected valid=False for duplicate rule IDs'
errors = t.get('errors', [])
assert any('duplicate' in e.lower() for e in errors), f'Expected duplicate error, got {errors}'
print('  PASS: duplicate rule IDs detected')
" || fail "duplicate rule ID detection"

echo ""
echo "--- Audit Export ---"
mkdir -p "$ARTIFACT_DIR/.omni/runs/test-run-p5"
cat > "$ARTIFACT_DIR/.omni/runs/test-run-p5/run.json" <<'RUN_EOF'
{"status": "done", "profile": "standard", "phases": [{"phase": "discuss", "status": "done", "started_at": "2025-01-01T00:00:00Z", "ended_at": "2025-01-01T00:01:00Z"}, {"phase": "plan", "status": "done", "started_at": "2025-01-01T00:01:00Z", "ended_at": "2025-01-01T00:05:00Z"}]}
RUN_EOF
cat > "$ARTIFACT_DIR/.omni/runs/test-run-p5/decisions.md" <<'DEC_EOF'
# Decisions
- Approved approach A over B
DEC_EOF

AUDIT_RESULT=$(call_tool "omni_audit_export" "{\"repo_root\":\"$ARTIFACT_DIR\",\"run_id\":\"test-run-p5\"}")

get_result_text "$AUDIT_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t['run_id'] == 'test-run-p5'
assert t['run_status'] == 'done'
assert t['redacted'] == True
assert len(t.get('phases', [])) == 2, f'Expected 2 phases, got {t.get(\"phases\")}'
assert 'artifacts' in t, 'Missing artifacts list'
assert 'run.json' in t['artifacts'], 'run.json not in artifacts'
assert 'decisions.md' in t['artifacts'], 'decisions.md not in artifacts'
assert 'enterprise' in t, 'Missing enterprise info'
assert 'policy_audit' in t, 'Missing policy_audit'
pa = t.get('policy_audit')
assert pa is not None, 'policy_audit is null'
assert len(pa.get('decisions', [])) > 0, 'policy_audit has no decisions'
assert pa['decisions'][0]['operation'] == 'decision', f'Expected operation=decision, got {pa[\"decisions\"][0]}'
assert pa['decisions'][0]['allowed'] == True, 'Expected first decision to be allowed'
print('  PASS: audit export has phases, artifacts, real policy decisions, enterprise info')
" || fail "audit export with rich data"

echo ""
echo "--- Audit Export Path Traversal Rejection ---"
TRAVERSAL_RESULT=$(call_tool "omni_audit_export" "{\"repo_root\":\"$ARTIFACT_DIR\",\"run_id\":\"../../escape\"}")

has_error "$TRAVERSAL_RESULT" && pass "audit path traversal rejected" || fail "audit path traversal NOT rejected"

echo ""
echo "--- Policy Pack Category Coverage ---"
for profile in strict standard permissive; do
    python3 -c "
import json
d = json.load(open('$REPO_ROOT/policies/$profile.json'))
categories = set(r['category'] for r in d['rules'])
required = {'commands', 'tools', 'network', 'paths', 'memory', 'updates'}
missing = required - categories
assert not missing, f'$profile policy pack missing categories: {missing}'
print(f'  PASS: $profile policy pack covers all 6 categories')
" || fail "$profile policy pack category coverage"
done

echo ""
echo "--- Release Bundle Includes Extras ---"
python3 -c "
import json
m = json.load(open('$ARTIFACT_DIR/bundle/release-manifest.json'))
paths = [c['path'] for c in m['components']]
assert any('marketplace.json' in p for p in paths), f'marketplace.json not in bundle: {paths}'
assert any('policies/' in p for p in paths), f'policies/ not in bundle: {paths}'
assert any('install-offline.sh' in p for p in paths), f'install-offline.sh not in bundle: {paths}'
print('  PASS: bundle includes marketplace.json, policies, and install script')
" || fail "bundle extras"

echo ""
echo "--- Enterprise Diagnostics ---"
DIAG_RESULT=$(call_tool "omni_enterprise_diagnose" "{\"repo_root\":\"$REPO_ROOT\"}")

get_result_text "$DIAG_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert 'platform' in t
assert 'checks' in t
assert isinstance(t['checks'], list)
assert len(t['checks']) >= 9, f'Expected >= 9 checks, got {len(t[\"checks\"])}'
check_names = [c['name'] for c in t['checks']]
assert 'platform' in check_names
assert 'git' in check_names
assert 'sidecar_binary' in check_names
assert 'plugin_structure' in check_names
assert 'repo_writable' in check_names
assert 'github_settings' in check_names
assert 'mcp_config' in check_names
assert 'enterprise_policy' in check_names
print('  PASS: enterprise diagnostics returns full compatibility report')
" || fail "enterprise diagnostics"

echo ""
echo "--- Enterprise Config ---"
CONFIG_RESULT=$(call_tool "omni_config_resolve" "{\"repo_root\":\"$REPO_ROOT\"}")

get_result_text "$CONFIG_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert 'enterprise' in t
ent = t['enterprise']
assert ent['offline_mode'] == False
assert ent['audit_retention_days'] > 0
assert ent['signing_enabled'] == False
print('  PASS: enterprise config in resolved config')
" || fail "enterprise config"

echo ""
echo "--- Marketplace Metadata ---"
[ -f "$REPO_ROOT/marketplace.json" ] && pass "marketplace.json exists" || fail "marketplace.json missing"
python3 -c "import json; d=json.load(open('$REPO_ROOT/marketplace.json')); assert 'plugins' in d; assert len(d['plugins']) > 0" && pass "marketplace.json valid" || fail "marketplace.json invalid"

echo ""
echo "--- Marketplace Paths Match Bundle Layout ---"
python3 -c "
import json
mp = json.load(open('$REPO_ROOT/marketplace.json'))
plugin = mp['plugins'][0]
assert plugin['sidecar'] == './omni-sidecar', f'Expected ./omni-sidecar, got {plugin[\"sidecar\"]}'
assert plugin['wrapper'] == './omni', f'Expected ./omni, got {plugin[\"wrapper\"]}'
print('  PASS: marketplace.json paths match bundle binary layout')
" || fail "marketplace.json path layout"

echo ""
echo "--- Offline Install Script ---"
bash -n "$REPO_ROOT/scripts/install-offline.sh" && pass "install-offline.sh syntax valid" || fail "install-offline.sh syntax error"
[ -x "$REPO_ROOT/scripts/install-offline.sh" ] && pass "install-offline.sh is executable" || fail "install-offline.sh not executable"

echo ""
echo "--- Offline Installer Round-Trip ---"
INSTALL_TARGET=$(mktemp -d)
bash "$REPO_ROOT/scripts/install-offline.sh" --bundle-dir "$ARTIFACT_DIR/bundle" --target "$INSTALL_TARGET" 2>&1 && pass "installer completes" || fail "installer failed"
[ -f "$INSTALL_TARGET/bin/omni-sidecar" ] && pass "omni-sidecar installed to bin" || fail "omni-sidecar not in bin"
[ -f "$INSTALL_TARGET/bin/omni" ] && pass "omni installed to bin" || fail "omni not in bin"
[ -f "$INSTALL_TARGET/share/copilot-omni/release-manifest.json" ] && pass "manifest installed" || fail "manifest not installed"
rm -rf "$INSTALL_TARGET"

echo ""
echo "--- Installer Path Traversal Rejection ---"
TRAVERSAL_TARGET=$(mktemp -d)
TRAVERSAL_BUNDLE=$(mktemp -d)/bundle
mkdir -p "$TRAVERSAL_BUNDLE/subdir"
echo "evil" > "$TRAVERSAL_BUNDLE/subdir/escape"
echo '{"product":"test","release_tag":"v0","components":[{"name":"evil","path":"subdir/../../escape","checksum":"abc"}]}' > "$TRAVERSAL_BUNDLE/release-manifest.json"
echo '[]' > "$TRAVERSAL_BUNDLE/sbom.json"
ESCAPE_HASH=$(sha256sum "$TRAVERSAL_BUNDLE/subdir/escape" | awk '{print $1}')
MANIFEST_HASH=$(sha256sum "$TRAVERSAL_BUNDLE/release-manifest.json" | awk '{print $1}')
SBOM_HASH=$(sha256sum "$TRAVERSAL_BUNDLE/sbom.json" | awk '{print $1}')
printf "%s  release-manifest.json\n%s  sbom.json\n%s  subdir/../../escape\n" "$MANIFEST_HASH" "$SBOM_HASH" "$ESCAPE_HASH" > "$TRAVERSAL_BUNDLE/checksums.txt"
INSTALLER_TRAV_OUTPUT=$(bash "$REPO_ROOT/scripts/install-offline.sh" --bundle-dir "$TRAVERSAL_BUNDLE" --target "$TRAVERSAL_TARGET" 2>&1 || true)
echo "$INSTALLER_TRAV_OUTPUT" | grep -qiE "escape|FAIL" && pass "installer rejects .. traversal in component path" || fail "installer allowed .. traversal"
rm -rf "$TRAVERSAL_TARGET" "$(dirname "$TRAVERSAL_BUNDLE")"

echo ""
echo "--- Bundle Validation Path Traversal Rejection ---"
TRAVERSAL_DIR2=$(mktemp -d)
mkdir -p "$TRAVERSAL_DIR2/bundle"
echo "evil content" > "$TRAVERSAL_DIR2/bundle/evil"
python3 -c "
import json, hashlib, os
evil_path = os.path.join('$TRAVERSAL_DIR2', 'bundle', 'evil')
evil_hash = hashlib.sha256(open(evil_path,'rb').read()).hexdigest()
manifest = {
    'product': 'test', 'release_tag': 'v0', 'platform': 'linux/amd64',
    'components': [{'name': 'evil', 'path': 'subdir/../../etc/passwd', 'checksum': evil_hash}],
    'checksums': {'subdir/../../etc/passwd': evil_hash},
    'provenance': {'builder': 'test', 'fingerprint': 'sha256:abc'},
    'sbom': []
}
json.dump(manifest, open(os.path.join('$TRAVERSAL_DIR2', 'bundle', 'release-manifest.json'), 'w'))
json.dump([], open(os.path.join('$TRAVERSAL_DIR2', 'bundle', 'sbom.json'), 'w'))
manifest_hash = hashlib.sha256(open(os.path.join('$TRAVERSAL_DIR2', 'bundle', 'release-manifest.json'), 'rb').read()).hexdigest()
sbom_hash = hashlib.sha256(open(os.path.join('$TRAVERSAL_DIR2', 'bundle', 'sbom.json'), 'rb').read()).hexdigest()
with open(os.path.join('$TRAVERSAL_DIR2', 'bundle', 'checksums.txt'), 'w') as f:
    f.write(f'{manifest_hash}  release-manifest.json\n')
    f.write(f'{sbom_hash}  sbom.json\n')
    f.write(f'{evil_hash}  subdir/../../etc/passwd\n')
"
TRAVERSAL_RESULT=$(call_tool "omni_release_bundle" "{\"repo_root\":\"$REPO_ROOT\",\"action\":\"validate\",\"bundle_dir\":\"$TRAVERSAL_DIR2/bundle\"}")
get_result_text "$TRAVERSAL_RESULT" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t.get('valid') == False, f'Expected valid=False for traversal, got {t}'
print('  PASS: bundle validator rejects path traversal')
" || fail "bundle validator allowed path traversal"
rm -rf "$TRAVERSAL_DIR2"

echo ""
echo "--- Wrapper Commands ---"
"$REPO_ROOT/wrapper/omni" --help 2>&1 | grep -q "audit" && pass "wrapper audit command listed" || fail "wrapper audit command missing"
"$REPO_ROOT/wrapper/omni" --help 2>&1 | grep -q "bundle" && pass "wrapper bundle command listed" || fail "wrapper bundle command missing"

echo ""
echo "--- Profile Enterprise Settings ---"
for profile in strict standard permissive; do
    python3 -c "import json; d=json.load(open('$REPO_ROOT/profiles/$profile/config.json')); assert 'enterprise' in d; ent=d['enterprise']; assert 'offline_mode' in ent; assert 'audit_retention_days' in ent; assert 'signing_enabled' in ent" && pass "profile $profile has enterprise settings" || fail "profile $profile missing enterprise settings"
done

python3 -c "import json; d=json.load(open('$REPO_ROOT/profiles/strict/config.json')); assert d['enterprise']['signing_enabled'] == True" && pass "strict profile has signing_enabled=true" || fail "strict profile signing_enabled wrong"

echo ""
echo "--- Strict Policy Pack Denies curl ---"
STRICT_PACK_CHECK=$(call_tool "omni_policy_pack_validate" "{\"repo_root\":\"$REPO_ROOT\",\"pack_path\":\"$REPO_ROOT/policies/strict.json\"}")
get_result_text "$STRICT_PACK_CHECK" | python3 -c "
import sys, json
t = json.loads(sys.stdin.read())
assert t['valid'] == True, f'Strict pack should be valid, got {t}'
rules = t.get('rule_results', [])
assert len(rules) > 0, 'Strict pack should have rules'
print('  PASS: strict policy pack validates and enforces rules')
" || fail "strict policy pack enforcement"

rm -rf "$ARTIFACT_DIR"

echo ""
if [ $FAILED -eq 0 ]; then
    echo "=== ALL PHASE 5 TESTS PASSED ==="
    exit 0
else
    echo "=== SOME PHASE 5 TESTS FAILED ==="
    exit 1
fi
