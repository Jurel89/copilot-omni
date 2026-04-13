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

	want, err := filepath.EvalSymlinks(filepath.Join(assetRoot, "plugin"))
	if err != nil {
		t.Fatalf("EvalSymlinks(plugin dir) error = %v", err)
	}
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

func TestParsePluginInstallArgs(t *testing.T) {
	tests := []struct {
		name     string
		args     []string
		wantKeep bool
		wantHelp bool
		wantErr  bool
	}{
		{name: "no flags", args: nil},
		{name: "keep staging", args: []string{"--keep-staging"}, wantKeep: true},
		{name: "help long", args: []string{"--help"}, wantHelp: true},
		{name: "help short", args: []string{"-h"}, wantHelp: true},
		{name: "unknown flag", args: []string{"--keep-stagin"}, wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotKeep, gotHelp, err := parsePluginInstallArgs(tt.args)
			if tt.wantErr {
				if err == nil {
					t.Fatal("parsePluginInstallArgs() error = nil, want error")
				}
				return
			}
			if err != nil {
				t.Fatalf("parsePluginInstallArgs() error = %v", err)
			}
			if gotKeep != tt.wantKeep || gotHelp != tt.wantHelp {
				t.Fatalf("parsePluginInstallArgs() = (%v, %v), want (%v, %v)", gotKeep, gotHelp, tt.wantKeep, tt.wantHelp)
			}
		})
	}
}

func TestRepoRootFallsBackToSourceAssetRootWhenInvokedFromWrapperDir(t *testing.T) {
	assetRoot := t.TempDir()
	createAssetRoot(t, assetRoot)
	if err := os.MkdirAll(filepath.Join(assetRoot, "wrapper"), 0o755); err != nil {
		t.Fatalf("MkdirAll(wrapper) error = %v", err)
	}
	t.Setenv("COPILOT_OMNI_ASSET_ROOT", assetRoot)

	originalWD, err := os.Getwd()
	if err != nil {
		t.Fatalf("Getwd() error = %v", err)
	}
	defer os.Chdir(originalWD)

	if err := os.Chdir(filepath.Join(assetRoot, "wrapper")); err != nil {
		t.Fatalf("Chdir(wrapper) error = %v", err)
	}

	if got := repoRoot(); got != assetRoot {
		t.Fatalf("repoRoot() = %q, want %q", got, assetRoot)
	}
}
