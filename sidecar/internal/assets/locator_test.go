package assets

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestResolveFromExecutableSourceLayout(t *testing.T) {
	repoRoot := t.TempDir()
	createAssetRoot(t, repoRoot)
	execPath := createExecutable(t, filepath.Join(repoRoot, "sidecar", "omni-sidecar"))

	location, err := ResolveFromExecutable(execPath)
	if err != nil {
		t.Fatalf("ResolveFromExecutable() error = %v", err)
	}

	assertLocation(t, location, ModeSource, repoRoot, execPath)
}

func TestResolveFromExecutableInstalledLayout(t *testing.T) {
	prefix := t.TempDir()
	assetRoot := filepath.Join(prefix, "share", "copilot-omni")
	createAssetRoot(t, assetRoot)
	execPath := createExecutable(t, filepath.Join(prefix, "bin", "omni-sidecar"))

	location, err := ResolveFromExecutable(execPath)
	if err != nil {
		t.Fatalf("ResolveFromExecutable() error = %v", err)
	}

	assertLocation(t, location, ModeInstalled, assetRoot, execPath)
}

func TestResolveFromExecutableEnvOverride(t *testing.T) {
	assetRoot := t.TempDir()
	createAssetRoot(t, assetRoot)
	customExecPath := createExecutable(t, filepath.Join(t.TempDir(), "custom", "omni-sidecar"))
	t.Setenv(assetRootEnv, assetRoot)

	location, err := ResolveFromExecutable(customExecPath)
	if err != nil {
		t.Fatalf("ResolveFromExecutable() error = %v", err)
	}

	assertLocation(t, location, ModeOverride, assetRoot, customExecPath)
}

func TestResolveFromExecutableMissingAssetFailure(t *testing.T) {
	repoRoot := t.TempDir()
	mustMkdirAll(t, filepath.Join(repoRoot, "templates"))
	mustMkdirAll(t, filepath.Join(repoRoot, "policies"))
	mustWriteFile(t, filepath.Join(repoRoot, "marketplace.json"), []byte("{}"))
	execPath := createExecutable(t, filepath.Join(repoRoot, "sidecar", "omni-sidecar"))

	_, err := ResolveFromExecutable(execPath)
	if err == nil {
		t.Fatal("ResolveFromExecutable() error = nil, want missing asset error")
	}

	missingPath := filepath.Join(repoRoot, "plugin")
	if !strings.Contains(err.Error(), "source asset root") {
		t.Fatalf("error %q does not mention source asset root", err)
	}
	if !strings.Contains(err.Error(), missingPath) {
		t.Fatalf("error %q does not mention missing path %q", err, missingPath)
	}
	if !strings.Contains(err.Error(), "missing required directory") {
		t.Fatalf("error %q does not mention missing required directory", err)
	}
}

func assertLocation(t *testing.T, got Location, wantMode Mode, wantRoot, wantExecPath string) {
	t.Helper()

	wantResolvedRoot := mustResolvePath(t, wantRoot)
	wantResolvedExecPath := mustResolvePath(t, wantExecPath)
	wantExecDir := filepath.Dir(wantResolvedExecPath)

	if got.Mode != wantMode {
		t.Fatalf("Mode = %q, want %q", got.Mode, wantMode)
	}
	if got.AssetRoot != wantResolvedRoot {
		t.Fatalf("AssetRoot = %q, want %q", got.AssetRoot, wantResolvedRoot)
	}
	if got.PluginDir != filepath.Join(wantResolvedRoot, "plugin") {
		t.Fatalf("PluginDir = %q, want %q", got.PluginDir, filepath.Join(wantResolvedRoot, "plugin"))
	}
	if got.TemplateDir != filepath.Join(wantResolvedRoot, "templates") {
		t.Fatalf("TemplateDir = %q, want %q", got.TemplateDir, filepath.Join(wantResolvedRoot, "templates"))
	}
	if got.PolicyDir != filepath.Join(wantResolvedRoot, "policies") {
		t.Fatalf("PolicyDir = %q, want %q", got.PolicyDir, filepath.Join(wantResolvedRoot, "policies"))
	}
	if got.MarketplacePath != filepath.Join(wantResolvedRoot, "marketplace.json") {
		t.Fatalf("MarketplacePath = %q, want %q", got.MarketplacePath, filepath.Join(wantResolvedRoot, "marketplace.json"))
	}
	if got.ExecPath != wantResolvedExecPath {
		t.Fatalf("ExecPath = %q, want %q", got.ExecPath, wantResolvedExecPath)
	}
	if got.ExecDir != wantExecDir {
		t.Fatalf("ExecDir = %q, want %q", got.ExecDir, wantExecDir)
	}
}

func createAssetRoot(t *testing.T, root string) {
	t.Helper()

	mustMkdirAll(t, filepath.Join(root, "plugin"))
	mustMkdirAll(t, filepath.Join(root, "templates"))
	mustMkdirAll(t, filepath.Join(root, "policies"))
	mustWriteFile(t, filepath.Join(root, "marketplace.json"), []byte("{}"))
}

func createExecutable(t *testing.T, path string) string {
	t.Helper()

	mustMkdirAll(t, filepath.Dir(path))
	mustWriteFile(t, path, []byte("#!/bin/sh\n"))

	return path
}

func mustMkdirAll(t *testing.T, path string) {
	t.Helper()

	if err := os.MkdirAll(path, 0o755); err != nil {
		t.Fatalf("MkdirAll(%q) error = %v", path, err)
	}
}

func mustWriteFile(t *testing.T, path string, data []byte) {
	t.Helper()

	if err := os.WriteFile(path, data, 0o755); err != nil {
		t.Fatalf("WriteFile(%q) error = %v", path, err)
	}
}

func mustResolvePath(t *testing.T, path string) string {
	t.Helper()

	resolvedPath, err := resolvePath(path)
	if err != nil {
		t.Fatalf("resolvePath(%q) error = %v", path, err)
	}

	return resolvedPath
}
