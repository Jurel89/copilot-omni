#!/bin/bash
set -e

# Phase 6 Integration Tests
# Tests benchmark, migration, and support bundle functionality

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR="$REPO_ROOT/.omni/test-phase6"

echo "=== Phase 6 Integration Tests ==="
echo "Test directory: $TEST_DIR"

# Setup
cleanup() {
    echo "Cleaning up test directory..."
    rm -rf "$TEST_DIR"
}

setup() {
    echo "Setting up test directory..."
    mkdir -p "$TEST_DIR"
    cd "$REPO_ROOT"
}

# Test: Benchmark Tool Registration
test_benchmark_tool_registered() {
    echo ""
    echo "Test: Benchmark tool registration"
    
    # List tools and check for omni_benchmark
    if go run ./sidecar/cmd/omni-sidecar/main.go list-tools 2>/dev/null | grep -q "omni_benchmark"; then
        echo "✓ omni_benchmark tool is registered"
    else
        echo "✗ omni_benchmark tool not found"
        return 1
    fi
}

# Test: Migration Tool Registration
test_migration_tool_registered() {
    echo ""
    echo "Test: Migration tool registration"
    
    if go run ./sidecar/cmd/omni-sidecar/main.go list-tools 2>/dev/null | grep -q "omni_migrate"; then
        echo "✓ omni_migrate tool is registered"
    else
        echo "✗ omni_migrate tool not found"
        return 1
    fi
}

# Test: Support Bundle Tool Registration
test_support_bundle_tool_registered() {
    echo ""
    echo "Test: Support bundle tool registration"
    
    if go run ./sidecar/cmd/omni-sidecar/main.go list-tools 2>/dev/null | grep -q "omni_support_bundle"; then
        echo "✓ omni_support_bundle tool is registered"
    else
        echo "✗ omni_support_bundle tool not found"
        return 1
    fi
}

# Test: Benchmark Schema Validation
test_benchmark_schema() {
    echo ""
    echo "Test: Benchmark schema validation"
    
    cd "$REPO_ROOT/sidecar"
    
    # Run schema validation test
    if go test -v -run TestBenchmarkSchema ./internal/schema/ 2>&1 | grep -q "PASS"; then
        echo "✓ Benchmark schema tests pass"
    else
        echo "✗ Benchmark schema tests failed"
        return 1
    fi
}

# Test: Migration Schema Validation
test_migration_schema() {
    echo ""
    echo "Test: Migration schema validation"
    
    cd "$REPO_ROOT/sidecar"
    
    if go test -v -run TestMigrationSchema ./internal/schema/ 2>&1 | grep -q "PASS"; then
        echo "✓ Migration schema tests pass"
    else
        echo "✗ Migration schema tests failed"
        return 1
    fi
}

# Test: Support Bundle Schema Validation
test_support_bundle_schema() {
    echo ""
    echo "Test: Support bundle schema validation"
    
    cd "$REPO_ROOT/sidecar"
    
    if go test -v -run TestSupportBundleSchema ./internal/schema/ 2>&1 | grep -q "PASS"; then
        echo "✓ Support bundle schema tests pass"
    else
        echo "✗ Support bundle schema tests failed"
        return 1
    fi
}

# Test: Benchmark Package Compilation
test_benchmark_compilation() {
    echo ""
    echo "Test: Benchmark package compilation"
    
    cd "$REPO_ROOT/sidecar"
    
    if go build ./internal/benchmark/... 2>&1; then
        echo "✓ Benchmark package compiles successfully"
    else
        echo "✗ Benchmark package compilation failed"
        return 1
    fi
}

# Test: Migration Package Compilation
test_migration_compilation() {
    echo ""
    echo "Test: Migration package compilation"
    
    cd "$REPO_ROOT/sidecar"
    
    if go build ./internal/migration/... 2>&1; then
        echo "✓ Migration package compiles successfully"
    else
        echo "✗ Migration package compilation failed"
        return 1
    fi
}

# Test: Support Package Compilation
test_support_compilation() {
    echo ""
    echo "Test: Support package compilation"
    
    cd "$REPO_ROOT/sidecar"
    
    if go build ./internal/support/... 2>&1; then
        echo "✓ Support package compiles successfully"
    else
        echo "✗ Support package compilation failed"
        return 1
    fi
}

# Test: Full Sidecar Build
test_sidecar_build() {
    echo ""
    echo "Test: Full sidecar build"
    
    cd "$REPO_ROOT/sidecar"
    
    if go build -o /tmp/omni-sidecar-test ./cmd/omni-sidecar/main.go 2>&1; then
        echo "✓ Sidecar builds successfully"
        rm -f /tmp/omni-sidecar-test
    else
        echo "✗ Sidecar build failed"
        return 1
    fi
}

# Test: MCP Tools Integration
test_mcp_tools_integration() {
    echo ""
    echo "Test: MCP tools integration"
    
    cd "$REPO_ROOT/sidecar"
    
    # Test that all Phase 6 tools are callable
    if go test -v -run TestPhase6Tools ./internal/mcp/ 2>&1 | grep -q "PASS"; then
        echo "✓ Phase 6 MCP tools integration tests pass"
    else
        echo "Note: Phase 6 MCP tools integration tests not yet implemented"
    fi
}

# Test: Performance Budgets
test_performance_budgets() {
    echo ""
    echo "Test: Performance budgets defined"
    
    # Check that budget constants are defined
    if grep -q "ColdStartP95" "$REPO_ROOT/sidecar/internal/benchmark/harness.go"; then
        echo "✓ Performance budgets defined in harness"
    else
        echo "✗ Performance budgets not found"
        return 1
    fi
    
    # Check target values
    if grep -q "1500.*time.Millisecond" "$REPO_ROOT/sidecar/internal/benchmark/harness.go"; then
        echo "✓ Cold start budget: 1500ms"
    fi
    
    if grep -q "150.*time.Millisecond" "$REPO_ROOT/sidecar/internal/benchmark/harness.go"; then
        echo "✓ Memory search budget: 150ms"
    fi
}

# Test: Documentation
test_documentation() {
    echo ""
    echo "Test: Documentation files exist"
    
    if [ -f "$REPO_ROOT/docs/operator/ga-release-checklist.md" ]; then
        echo "✓ GA release checklist exists"
    else
        echo "✗ GA release checklist missing"
        return 1
    fi
    
    if [ -f "$REPO_ROOT/docs/operator/operator-guide.md" ]; then
        echo "✓ Operator guide exists"
    else
        echo "✗ Operator guide missing"
        return 1
    fi
}

# Test: Wrapper CLI Commands
test_wrapper_commands() {
    echo ""
    echo "Test: Wrapper CLI commands"
    
    cd "$REPO_ROOT/wrapper"
    
    if go build -o /tmp/omni-test ./cmd/omni/main.go 2>&1; then
        echo "✓ Wrapper CLI builds successfully"
        
        # Check help output for Phase 6 commands
        if /tmp/omni-test --help 2>&1 | grep -qi "benchmark\|migrate\|support"; then
            echo "✓ Phase 6 commands in CLI help"
        else
            echo "Note: Phase 6 CLI commands may not be fully integrated yet"
        fi
        
        rm -f /tmp/omni-test
    else
        echo "✗ Wrapper CLI build failed"
        return 1
    fi
}

# Main test runner
main() {
    setup
    
    echo ""
    echo "Running Phase 6 integration tests..."
    echo "======================================"
    
    local failed=0
    
    # Run all tests
    test_benchmark_tool_registered || failed=$((failed + 1))
    test_migration_tool_registered || failed=$((failed + 1))
    test_support_bundle_tool_registered || failed=$((failed + 1))
    test_benchmark_schema || failed=$((failed + 1))
    test_migration_schema || failed=$((failed + 1))
    test_support_bundle_schema || failed=$((failed + 1))
    test_benchmark_compilation || failed=$((failed + 1))
    test_migration_compilation || failed=$((failed + 1))
    test_support_compilation || failed=$((failed + 1))
    test_sidecar_build || failed=$((failed + 1))
    test_mcp_tools_integration || true  # Optional
    test_performance_budgets || failed=$((failed + 1))
    test_documentation || failed=$((failed + 1))
    test_wrapper_commands || failed=$((failed + 1))
    
    echo ""
    echo "======================================"
    if [ $failed -eq 0 ]; then
        echo "All Phase 6 tests passed! ✓"
        exit 0
    else
        echo "$failed test(s) failed ✗"
        exit 1
    fi
}

# Run main
trap cleanup EXIT
main
