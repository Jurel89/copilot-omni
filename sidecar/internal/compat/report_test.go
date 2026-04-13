package compat

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestRunDiagnosticsReportsTrustedAssets(t *testing.T) {
	repoRoot := createCompatRepoRoot(t)
	explicitPath := writeCompatSidecarExecutable(t, filepath.Join(t.TempDir(), compatSidecarBinaryName()))
	assetRoot := createCompatAssetRoot(t, t.TempDir(), explicitPath)
	t.Setenv(assetRootEnvName, assetRoot)

	report, err := RunDiagnostics(repoRoot)
	if err != nil {
		t.Fatalf("RunDiagnostics() error = %v", err)
	}

	if report.TrustedAssets.Status != "pass" {
		t.Fatalf("TrustedAssets.Status = %q, want pass (error: %q)", report.TrustedAssets.Status, report.TrustedAssets.Error)
	}
	if report.TrustedAssets.AssetRoot != compatResolvePathForTest(t, assetRoot) {
		t.Fatalf("TrustedAssets.AssetRoot = %q, want %q", report.TrustedAssets.AssetRoot, compatResolvePathForTest(t, assetRoot))
	}
	if report.MCPServerCommand.Classification != mcpCommandExplicitExistingPath {
		t.Fatalf("MCPServerCommand.Classification = %q, want %q", report.MCPServerCommand.Classification, mcpCommandExplicitExistingPath)
	}

	trustedAssetsCheck := findCompatCheck(t, report.Checks, "trusted_assets")
	if trustedAssetsCheck.Status != "pass" {
		t.Fatalf("trusted_assets check status = %q, want pass", trustedAssetsCheck.Status)
	}
	if trustedAssetsCheck.Category != checkCategoryAssets {
		t.Fatalf("trusted_assets check category = %q, want %q", trustedAssetsCheck.Category, checkCategoryAssets)
	}

	mcpCheck := findCompatCheck(t, report.Checks, "mcp_config")
	if mcpCheck.Status != "pass" {
		t.Fatalf("mcp_config check status = %q, want pass", mcpCheck.Status)
	}
	if mcpCheck.Category != checkCategoryLaunch {
		t.Fatalf("mcp_config check category = %q, want %q", mcpCheck.Category, checkCategoryLaunch)
	}
}

func TestCheckMCPConfigClassifiesConfiguredCommand(t *testing.T) {
	tests := []struct {
		name               string
		command            func(*testing.T) string
		pathEnv            func(*testing.T) string
		wantStatus         string
		wantClassification string
		wantResolvedPath   func(*testing.T, string) string
	}{
		{
			name: "valid explicit path",
			command: func(t *testing.T) string {
				return writeCompatSidecarExecutable(t, filepath.Join(t.TempDir(), compatSidecarBinaryName()))
			},
			wantStatus:         "pass",
			wantClassification: mcpCommandExplicitExistingPath,
			wantResolvedPath: func(t *testing.T, command string) string {
				return compatResolvePathForTest(t, command)
			},
		},
		{
			name: "stale absolute path",
			command: func(t *testing.T) string {
				return filepath.Join(t.TempDir(), "missing", compatSidecarBinaryName())
			},
			wantStatus:         "fail",
			wantClassification: mcpCommandExplicitStalePath,
			wantResolvedPath: func(t *testing.T, command string) string {
				return compatResolvePathForTest(t, command)
			},
		},
		{
			name: "bare command resolvable via PATH",
			command: func(t *testing.T) string {
				return "omni-sidecar"
			},
			pathEnv: func(t *testing.T) string {
				binDir := t.TempDir()
				writeCompatSidecarExecutable(t, filepath.Join(binDir, compatSidecarBinaryName()))
				return binDir + string(os.PathListSeparator) + os.Getenv("PATH")
			},
			wantStatus:         "pass",
			wantClassification: mcpCommandBareResolvable,
			wantResolvedPath: func(t *testing.T, _ string) string {
				path, err := exec.LookPath("omni-sidecar")
				if err != nil {
					t.Fatalf("LookPath(omni-sidecar) error = %v", err)
				}
				return compatResolvePathForTest(t, path)
			},
		},
		{
			name: "bare command missing",
			command: func(t *testing.T) string {
				return "omni-sidecar"
			},
			pathEnv: func(t *testing.T) string {
				return t.TempDir()
			},
			wantStatus:         "fail",
			wantClassification: mcpCommandBareMissing,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			command := tt.command(t)
			assetRoot := createCompatAssetRoot(t, t.TempDir(), command)
			t.Setenv(assetRootEnvName, assetRoot)
			if tt.pathEnv != nil {
				t.Setenv("PATH", tt.pathEnv(t))
			}

			trusted := resolveTrustedAssets()
			check, classified := checkMCPConfig(trusted)

			if check.Status != tt.wantStatus {
				t.Fatalf("check status = %q, want %q", check.Status, tt.wantStatus)
			}
			if check.Category != checkCategoryLaunch {
				t.Fatalf("check category = %q, want %q", check.Category, checkCategoryLaunch)
			}
			if classified.Classification != tt.wantClassification {
				t.Fatalf("classification = %q, want %q", classified.Classification, tt.wantClassification)
			}
			if tt.wantResolvedPath != nil {
				wantResolvedPath := tt.wantResolvedPath(t, command)
				if classified.ResolvedPath != wantResolvedPath {
					t.Fatalf("resolved path = %q, want %q", classified.ResolvedPath, wantResolvedPath)
				}
			}
		})
	}
}

func TestCheckMCPConfigPrefersManagedInstallState(t *testing.T) {
	explicitPath := writeCompatSidecarExecutable(t, filepath.Join(t.TempDir(), compatSidecarBinaryName()))
	assetRoot := createCompatAssetRoot(t, t.TempDir(), "omni-sidecar")
	t.Setenv(assetRootEnvName, assetRoot)
	stateDir := t.TempDir()
	t.Setenv(pluginStateDirEnv, stateDir)
	compatMustWriteFile(t, filepath.Join(stateDir, "plugin-install.json"), []byte(fmt.Sprintf(`{"version":1,"type":"stdio","command":%q,"args":["serve"]}`, explicitPath)), 0o644)

	trusted := resolveTrustedAssets()
	check, classified := checkMCPConfig(trusted)
	if check.Status != "pass" {
		t.Fatalf("check status = %q, want pass", check.Status)
	}
	if classified.SourcePath != filepath.Join(stateDir, "plugin-install.json") {
		t.Fatalf("source path = %q", classified.SourcePath)
	}
	if classified.Classification != mcpCommandExplicitExistingPath {
		t.Fatalf("classification = %q", classified.Classification)
	}
}

func TestRunDiagnosticsReportsMissingTrustedAssets(t *testing.T) {
	tests := []struct {
		name       string
		assetRoot  string
		setupAsset func(*testing.T, string)
		wantError  string
	}{
		{
			name:      "missing plugin dir",
			assetRoot: t.TempDir(),
			setupAsset: func(t *testing.T, assetRoot string) {
				compatMustMkdirAll(t, filepath.Join(assetRoot, "templates"))
				compatMustMkdirAll(t, filepath.Join(assetRoot, "policies"))
				compatMustWriteFile(t, filepath.Join(assetRoot, "marketplace.json"), []byte("{}"), 0o644)
			},
			wantError: "missing required directory",
		},
		{
			name:       "missing asset root",
			assetRoot:  filepath.Join(t.TempDir(), "missing-root"),
			setupAsset: func(*testing.T, string) {},
			wantError:  "missing required directory",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			repoRoot := createCompatRepoRoot(t)
			if tt.setupAsset != nil {
				tt.setupAsset(t, tt.assetRoot)
			}
			t.Setenv(assetRootEnvName, tt.assetRoot)

			report, err := RunDiagnostics(repoRoot)
			if err != nil {
				t.Fatalf("RunDiagnostics() error = %v", err)
			}

			if report.TrustedAssets.Status != "fail" {
				t.Fatalf("TrustedAssets.Status = %q, want fail", report.TrustedAssets.Status)
			}
			if report.TrustedAssets.AssetRoot != compatResolvePathForTest(t, tt.assetRoot) {
				t.Fatalf("TrustedAssets.AssetRoot = %q, want %q", report.TrustedAssets.AssetRoot, compatResolvePathForTest(t, tt.assetRoot))
			}
			if !strings.Contains(report.TrustedAssets.Error, tt.wantError) {
				t.Fatalf("TrustedAssets.Error = %q, want to contain %q", report.TrustedAssets.Error, tt.wantError)
			}

			trustedAssetsCheck := findCompatCheck(t, report.Checks, "trusted_assets")
			if trustedAssetsCheck.Status != "fail" {
				t.Fatalf("trusted_assets check status = %q, want fail", trustedAssetsCheck.Status)
			}
			if trustedAssetsCheck.Category != checkCategoryAssets {
				t.Fatalf("trusted_assets check category = %q, want %q", trustedAssetsCheck.Category, checkCategoryAssets)
			}

			mcpCheck := findCompatCheck(t, report.Checks, "mcp_config")
			if mcpCheck.Status != "warn" {
				t.Fatalf("mcp_config check status = %q, want warn", mcpCheck.Status)
			}
			if mcpCheck.Category != checkCategoryAssets {
				t.Fatalf("mcp_config check category = %q, want %q", mcpCheck.Category, checkCategoryAssets)
			}
			if report.Compatible {
				t.Fatal("Compatible = true, want false when trusted assets fail")
			}
		})
	}
}

func findCompatCheck(t *testing.T, checks []CompatCheck, name string) CompatCheck {
	t.Helper()

	for _, check := range checks {
		if check.Name == name {
			return check
		}
	}

	t.Fatalf("check %q not found", name)
	return CompatCheck{}
}

func createCompatRepoRoot(t *testing.T) string {
	t.Helper()

	repoRoot := t.TempDir()
	compatMustMkdirAll(t, filepath.Join(repoRoot, ".github"))
	compatMustWriteFile(t, filepath.Join(repoRoot, ".github", "copilot-instructions.md"), []byte("# test\n"), 0o644)
	compatMustWriteFile(t, filepath.Join(repoRoot, "AGENTS.md"), []byte("# test\n"), 0o644)

	return repoRoot
}

func createCompatAssetRoot(t *testing.T, root string, command string) string {
	t.Helper()

	compatMustMkdirAll(t, filepath.Join(root, "plugin"))
	compatMustMkdirAll(t, filepath.Join(root, "templates"))
	compatMustMkdirAll(t, filepath.Join(root, "policies"))
	compatMustWriteFile(t, filepath.Join(root, "marketplace.json"), []byte("{}"), 0o644)
	compatMustWriteFile(t, filepath.Join(root, "plugin", "plugin.json"), []byte(`{"name":"copilot-omni","version":"0.1.0"}`), 0o644)
	compatMustWriteFile(t, filepath.Join(root, "plugin", "hooks.json"), []byte(`{"version":1,"hooks":{"preToolUse":[]}}`), 0o644)
	compatMustWriteFile(t, filepath.Join(root, "policies", "strict.json"), []byte("{}"), 0o644)

	mcpConfigBytes, err := json.Marshal(map[string]any{
		"mcpServers": map[string]any{
			sidecarServer: map[string]any{
				"type":    "stdio",
				"command": command,
				"args":    []string{"serve"},
			},
		},
	})
	if err != nil {
		t.Fatalf("Marshal(mcp config) error = %v", err)
	}
	compatMustWriteFile(t, filepath.Join(root, "plugin", ".mcp.json"), mcpConfigBytes, 0o644)

	return root
}

func writeCompatSidecarExecutable(t *testing.T, path string) string {
	t.Helper()

	compatMustMkdirAll(t, filepath.Dir(path))
	compatMustWriteFile(t, path, []byte("#!/bin/sh\n"), 0o755)
	return path
}

func compatResolvePathForTest(t *testing.T, path string) string {
	t.Helper()

	resolvedPath := resolveReportPath(path)
	if resolvedPath == "" {
		t.Fatalf("resolveReportPath(%q) returned empty path", path)
	}
	return resolvedPath
}

func compatSidecarBinaryName() string {
	if runtime.GOOS == "windows" {
		return "omni-sidecar.exe"
	}
	return "omni-sidecar"
}

func compatMustMkdirAll(t *testing.T, path string) {
	t.Helper()

	if err := os.MkdirAll(path, 0o755); err != nil {
		t.Fatalf("MkdirAll(%q) error = %v", path, err)
	}
}

func compatMustWriteFile(t *testing.T, path string, data []byte, mode os.FileMode) {
	t.Helper()

	if err := os.WriteFile(path, data, mode); err != nil {
		t.Fatalf("WriteFile(%q) error = %v", path, err)
	}
}
