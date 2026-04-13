package doctor

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

func TestRunAllReportsTrustedAssets(t *testing.T) {
	repoRoot := createDoctorRepoRoot(t)
	explicitPath := writeSidecarExecutable(t, filepath.Join(t.TempDir(), platformSidecarName()))
	assetRoot := createTrustedAssetRoot(t, t.TempDir(), explicitPath)
	t.Setenv(assetRootEnvName, assetRoot)

	report := RunAll(repoRoot)

	if report.TrustedAssets.Status != "pass" {
		t.Fatalf("TrustedAssets.Status = %q, want pass (error: %q)", report.TrustedAssets.Status, report.TrustedAssets.Error)
	}
	if report.TrustedAssets.AssetRoot != resolvePathForTest(t, assetRoot) {
		t.Fatalf("TrustedAssets.AssetRoot = %q, want %q", report.TrustedAssets.AssetRoot, resolvePathForTest(t, assetRoot))
	}
	if report.TrustedAssets.PluginDir != filepath.Join(resolvePathForTest(t, assetRoot), "plugin") {
		t.Fatalf("TrustedAssets.PluginDir = %q, want %q", report.TrustedAssets.PluginDir, filepath.Join(resolvePathForTest(t, assetRoot), "plugin"))
	}
	if report.MCPServerCommand.Classification != mcpCommandExplicitExistingPath {
		t.Fatalf("MCPServerCommand.Classification = %q, want %q", report.MCPServerCommand.Classification, mcpCommandExplicitExistingPath)
	}

	trustedAssetsDiagnostic := findDiagnostic(t, report.Diagnostics, "TrustedAssets")
	if trustedAssetsDiagnostic.Status != "pass" {
		t.Fatalf("TrustedAssets diagnostic status = %q, want pass", trustedAssetsDiagnostic.Status)
	}
	if trustedAssetsDiagnostic.Category != diagnosticCategoryAssets {
		t.Fatalf("TrustedAssets diagnostic category = %q, want %q", trustedAssetsDiagnostic.Category, diagnosticCategoryAssets)
	}

	mcpDiagnostic := findDiagnostic(t, report.Diagnostics, "MCPConfig")
	if mcpDiagnostic.Status != "pass" {
		t.Fatalf("MCPConfig diagnostic status = %q, want pass", mcpDiagnostic.Status)
	}
	if mcpDiagnostic.Category != diagnosticCategoryLaunch {
		t.Fatalf("MCPConfig diagnostic category = %q, want %q", mcpDiagnostic.Category, diagnosticCategoryLaunch)
	}
}

func TestCheckMCPConfigClassifiesConfiguredCommand(t *testing.T) {
	tests := []struct {
		name               string
		command            func(*testing.T) string
		pathEnv            func(*testing.T) string
		wantDiagnostic     string
		wantClassification string
		wantResolvedPath   func(*testing.T, string) string
	}{
		{
			name: "valid explicit path",
			command: func(t *testing.T) string {
				return writeSidecarExecutable(t, filepath.Join(t.TempDir(), platformSidecarName()))
			},
			wantDiagnostic:     "pass",
			wantClassification: mcpCommandExplicitExistingPath,
			wantResolvedPath: func(t *testing.T, command string) string {
				return resolvePathForTest(t, command)
			},
		},
		{
			name: "stale absolute path",
			command: func(t *testing.T) string {
				return filepath.Join(t.TempDir(), "missing", platformSidecarName())
			},
			wantDiagnostic:     "fail",
			wantClassification: mcpCommandExplicitStalePath,
			wantResolvedPath: func(t *testing.T, command string) string {
				return resolvePathForTest(t, command)
			},
		},
		{
			name: "bare command resolvable via PATH",
			command: func(t *testing.T) string {
				return "omni-sidecar"
			},
			pathEnv: func(t *testing.T) string {
				binDir := t.TempDir()
				writeSidecarExecutable(t, filepath.Join(binDir, platformSidecarName()))
				return binDir + string(os.PathListSeparator) + os.Getenv("PATH")
			},
			wantDiagnostic:     "pass",
			wantClassification: mcpCommandBareResolvable,
			wantResolvedPath: func(t *testing.T, _ string) string {
				path, err := exec.LookPath("omni-sidecar")
				if err != nil {
					t.Fatalf("LookPath(omni-sidecar) error = %v", err)
				}
				return resolvePathForTest(t, path)
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
			wantDiagnostic:     "fail",
			wantClassification: mcpCommandBareMissing,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			command := tt.command(t)
			assetRoot := createTrustedAssetRoot(t, t.TempDir(), command)
			t.Setenv(assetRootEnvName, assetRoot)
			if tt.pathEnv != nil {
				t.Setenv("PATH", tt.pathEnv(t))
			}

			trusted := resolveTrustedAssets()
			diagnostic, classified := CheckMCPConfig(trusted)

			if diagnostic.Status != tt.wantDiagnostic {
				t.Fatalf("diagnostic status = %q, want %q", diagnostic.Status, tt.wantDiagnostic)
			}
			if diagnostic.Category != diagnosticCategoryLaunch {
				t.Fatalf("diagnostic category = %q, want %q", diagnostic.Category, diagnosticCategoryLaunch)
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
	explicitPath := writeSidecarExecutable(t, filepath.Join(t.TempDir(), platformSidecarName()))
	assetRoot := createTrustedAssetRoot(t, t.TempDir(), "omni-sidecar")
	t.Setenv(assetRootEnvName, assetRoot)
	stateDir := t.TempDir()
	t.Setenv(pluginStateDirEnv, stateDir)
	mustWriteFile(t, filepath.Join(stateDir, "plugin-install.json"), []byte(fmt.Sprintf(`{"version":1,"type":"stdio","command":%q,"args":["serve"]}`, explicitPath)), 0o644)

	trusted := resolveTrustedAssets()
	diagnostic, classified := CheckMCPConfig(trusted)
	if diagnostic.Status != "pass" {
		t.Fatalf("diagnostic status = %q, want pass", diagnostic.Status)
	}
	if classified.SourcePath != filepath.Join(stateDir, "plugin-install.json") {
		t.Fatalf("source path = %q", classified.SourcePath)
	}
	if classified.Classification != mcpCommandExplicitExistingPath {
		t.Fatalf("classification = %q", classified.Classification)
	}
}

func TestRunAllReportsMissingTrustedAssets(t *testing.T) {
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
				mustMkdirAll(t, filepath.Join(assetRoot, "templates"))
				mustMkdirAll(t, filepath.Join(assetRoot, "policies"))
				mustWriteFile(t, filepath.Join(assetRoot, "marketplace.json"), []byte("{}"), 0o644)
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
			repoRoot := createDoctorRepoRoot(t)
			assetRoot := tt.assetRoot
			if tt.setupAsset != nil {
				tt.setupAsset(t, assetRoot)
			}
			t.Setenv(assetRootEnvName, assetRoot)

			report := RunAll(repoRoot)

			if report.TrustedAssets.Status != "fail" {
				t.Fatalf("TrustedAssets.Status = %q, want fail", report.TrustedAssets.Status)
			}
			if report.TrustedAssets.AssetRoot != resolvePathForTest(t, assetRoot) {
				t.Fatalf("TrustedAssets.AssetRoot = %q, want %q", report.TrustedAssets.AssetRoot, resolvePathForTest(t, assetRoot))
			}
			if !strings.Contains(report.TrustedAssets.Error, tt.wantError) {
				t.Fatalf("TrustedAssets.Error = %q, want to contain %q", report.TrustedAssets.Error, tt.wantError)
			}

			trustedAssetsDiagnostic := findDiagnostic(t, report.Diagnostics, "TrustedAssets")
			if trustedAssetsDiagnostic.Status != "fail" {
				t.Fatalf("TrustedAssets diagnostic status = %q, want fail", trustedAssetsDiagnostic.Status)
			}
			if trustedAssetsDiagnostic.Category != diagnosticCategoryAssets {
				t.Fatalf("TrustedAssets diagnostic category = %q, want %q", trustedAssetsDiagnostic.Category, diagnosticCategoryAssets)
			}

			mcpDiagnostic := findDiagnostic(t, report.Diagnostics, "MCPConfig")
			if mcpDiagnostic.Status != "warn" {
				t.Fatalf("MCPConfig diagnostic status = %q, want warn", mcpDiagnostic.Status)
			}
			if mcpDiagnostic.Category != diagnosticCategoryAssets {
				t.Fatalf("MCPConfig diagnostic category = %q, want %q", mcpDiagnostic.Category, diagnosticCategoryAssets)
			}
		})
	}
}

func findDiagnostic(t *testing.T, diagnostics []Diagnostic, name string) Diagnostic {
	t.Helper()

	for _, diagnostic := range diagnostics {
		if diagnostic.Name == name {
			return diagnostic
		}
	}

	t.Fatalf("diagnostic %q not found", name)
	return Diagnostic{}
}

func createDoctorRepoRoot(t *testing.T) string {
	t.Helper()

	repoRoot := t.TempDir()
	mustMkdirAll(t, filepath.Join(repoRoot, ".omni"))
	mustMkdirAll(t, filepath.Join(repoRoot, ".github"))
	mustWriteFile(t, filepath.Join(repoRoot, ".omni", "config.json"), []byte("{}"), 0o644)
	mustWriteFile(t, filepath.Join(repoRoot, ".github", "copilot-instructions.md"), []byte("# test\n"), 0o644)
	mustWriteFile(t, filepath.Join(repoRoot, "AGENTS.md"), []byte("# test\n"), 0o644)
	mustWriteFile(t, filepath.Join(repoRoot, ".omni", "memory.db"), nil, 0o644)

	return repoRoot
}

func createTrustedAssetRoot(t *testing.T, root string, command string) string {
	t.Helper()

	mustMkdirAll(t, filepath.Join(root, "plugin"))
	mustMkdirAll(t, filepath.Join(root, "templates"))
	mustMkdirAll(t, filepath.Join(root, "policies"))
	mustWriteFile(t, filepath.Join(root, "marketplace.json"), []byte("{}"), 0o644)
	mustWriteFile(t, filepath.Join(root, "plugin", "plugin.json"), []byte(`{"name":"copilot-omni","version":"0.1.0"}`), 0o644)
	mustWriteFile(t, filepath.Join(root, "plugin", "hooks.json"), []byte(`{"version":1,"hooks":{"preToolUse":[]}}`), 0o644)
	mustWriteFile(t, filepath.Join(root, "policies", "strict.json"), []byte("{}"), 0o644)

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
	mustWriteFile(t, filepath.Join(root, "plugin", ".mcp.json"), mcpConfigBytes, 0o644)

	return root
}

func writeSidecarExecutable(t *testing.T, path string) string {
	t.Helper()

	mustMkdirAll(t, filepath.Dir(path))
	mustWriteFile(t, path, []byte("#!/bin/sh\n"), 0o755)
	return path
}

func resolvePathForTest(t *testing.T, path string) string {
	t.Helper()

	resolvedPath := resolveReportPath(path)
	if resolvedPath == "" {
		t.Fatalf("resolveReportPath(%q) returned empty path", path)
	}
	return resolvedPath
}

func platformSidecarName() string {
	if runtime.GOOS == "windows" {
		return "omni-sidecar.exe"
	}
	return "omni-sidecar"
}

func mustMkdirAll(t *testing.T, path string) {
	t.Helper()

	if err := os.MkdirAll(path, 0o755); err != nil {
		t.Fatalf("MkdirAll(%q) error = %v", path, err)
	}
}

func mustWriteFile(t *testing.T, path string, data []byte, mode os.FileMode) {
	t.Helper()

	if err := os.WriteFile(path, data, mode); err != nil {
		t.Fatalf("WriteFile(%q) error = %v", path, err)
	}
}
