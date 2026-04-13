package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestTrustedPluginDirUsesAssetLocator(t *testing.T) {
	assetRoot := t.TempDir()
	createAssetRoot(t, assetRoot)
	t.Setenv("COPILOT_OMNI_ASSET_ROOT", assetRoot)

	pluginDir, err := trustedPluginDir()
	if err != nil {
		t.Fatalf("trustedPluginDir() error = %v", err)
	}

	want := filepath.Join(assetRoot, "plugin")
	if pluginDir != want {
		t.Fatalf("trustedPluginDir() = %q, want %q", pluginDir, want)
	}
}

func createAssetRoot(t *testing.T, root string) {
	t.Helper()

	for _, dir := range []string{"plugin", "templates", "policies"} {
		if err := os.MkdirAll(filepath.Join(root, dir), 0o755); err != nil {
			t.Fatalf("MkdirAll(%q) error = %v", filepath.Join(root, dir), err)
		}
	}
	if err := os.WriteFile(filepath.Join(root, "marketplace.json"), []byte("{}"), 0o644); err != nil {
		t.Fatalf("WriteFile(marketplace.json) error = %v", err)
	}
}
