package plugininstall

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/Jurel89/copilot-omni/wrapper/internal/assets"
)

func TestInstallStagesPluginAndWritesExplicitMCPConfig(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Windows plugin install path is covered by PowerShell smoke tests")
	}
	root := t.TempDir()
	pluginDir := filepath.Join(root, "plugin")
	mustWriteFile(t, filepath.Join(pluginDir, "plugin.json"), []byte(`{"name":"copilot-omni"}`), 0o644)
	mustWriteFile(t, filepath.Join(pluginDir, ".mcp.json"), []byte(`{"old":true}`), 0o644)
	mustWriteFile(t, filepath.Join(pluginDir, "agents", "omni-conductor.agent.md"), []byte("agent"), 0o644)
	sidecarPath := mustWriteExecutable(t, filepath.Join(root, binaryName("omni-sidecar")))
	copilotPath := buildFakeCopilot(t)
	stagingDir := filepath.Join(root, "staging")
	installRecord := filepath.Join(root, "installed-path.txt")
	stateDir := filepath.Join(root, "state")
	t.Setenv("FAKE_COPILOT_INSTALL_RECORD", installRecord)
	t.Setenv(pluginStateDirEnv, stateDir)

	result, err := Install(context.Background(), Options{
		AssetLocation: assets.Location{PluginDir: pluginDir},
		SidecarPath:   sidecarPath,
		CopilotPath:   copilotPath,
		KeepStaging:   true,
		StagingDir:    stagingDir,
	})
	if err != nil {
		t.Fatalf("Install() error = %v", err)
	}
	if result.StagingDir != stagingDir {
		t.Fatalf("StagingDir = %q, want %q", result.StagingDir, stagingDir)
	}

	installedPathBytes, err := os.ReadFile(installRecord)
	if err != nil {
		t.Fatalf("ReadFile(install record) error = %v", err)
	}
	installedPath := string(installedPathBytes)
	if installedPath != stagingDir {
		t.Fatalf("copilot installed path = %q, want %q", installedPath, stagingDir)
	}

	if _, err := os.Stat(filepath.Join(stagingDir, "agents", "omni-conductor.agent.md")); err != nil {
		t.Fatalf("staged nested plugin asset missing: %v", err)
	}

	configBytes, err := os.ReadFile(filepath.Join(stagingDir, ".mcp.json"))
	if err != nil {
		t.Fatalf("ReadFile(.mcp.json) error = %v", err)
	}

	var payload struct {
		MCPServers map[string]struct {
			Type    string   `json:"type"`
			Command string   `json:"command"`
			Args    []string `json:"args"`
		} `json:"mcpServers"`
	}
	if err := json.Unmarshal(configBytes, &payload); err != nil {
		t.Fatalf("json.Unmarshal(.mcp.json) error = %v", err)
	}
	server := payload.MCPServers["copilot-omni-sidecar"]
	if server.Type != "stdio" {
		t.Fatalf("type = %q, want stdio", server.Type)
	}
	if server.Command != sidecarPath {
		t.Fatalf("command = %q, want %q", server.Command, sidecarPath)
	}
	if len(server.Args) != 1 || server.Args[0] != "serve" {
		t.Fatalf("args = %#v, want [serve]", server.Args)
	}
	if _, err := os.Stat(filepath.Join(stateDir, "plugin-install.json")); err != nil {
		t.Fatalf("managed install state not written: %v", err)
	}
}

func TestInstallCleansUpGeneratedStagingDirAndUsesPATHCopilot(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Windows plugin install path is covered by PowerShell smoke tests")
	}
	root := t.TempDir()
	pluginDir := filepath.Join(root, "plugin")
	mustWriteFile(t, filepath.Join(pluginDir, "plugin.json"), []byte(`{"name":"copilot-omni"}`), 0o644)
	sidecarPath := mustWriteExecutable(t, filepath.Join(root, binaryName("omni-sidecar")))
	installRecord := filepath.Join(root, "installed-path.txt")
	stateDir := filepath.Join(root, "state")
	t.Setenv("FAKE_COPILOT_INSTALL_RECORD", installRecord)
	t.Setenv(pluginStateDirEnv, stateDir)
	copilotPath := buildFakeCopilot(t)
	t.Setenv("PATH", filepath.Dir(copilotPath)+string(os.PathListSeparator)+os.Getenv("PATH"))

	result, err := Install(context.Background(), Options{
		AssetLocation: assets.Location{PluginDir: pluginDir},
		SidecarPath:   sidecarPath,
	})
	if err != nil {
		t.Fatalf("Install() error = %v", err)
	}

	installedPathBytes, err := os.ReadFile(installRecord)
	if err != nil {
		t.Fatalf("ReadFile(install record) error = %v", err)
	}
	installedPath := string(installedPathBytes)
	if installedPath != result.StagingDir {
		t.Fatalf("copilot installed path = %q, want %q", installedPath, result.StagingDir)
	}
	if _, err := os.Stat(result.StagingDir); !os.IsNotExist(err) {
		t.Fatalf("staging dir = %q, want cleaned up after install, stat err = %v", result.StagingDir, err)
	}
	if _, err := os.Stat(filepath.Join(stateDir, "plugin-install.json")); err != nil {
		t.Fatalf("managed install state not written: %v", err)
	}
}

func TestInstallFailsWithoutSidecar(t *testing.T) {
	root := t.TempDir()
	pluginDir := filepath.Join(root, "plugin")
	mustWriteFile(t, filepath.Join(pluginDir, "plugin.json"), []byte(`{"name":"copilot-omni"}`), 0o644)

	_, err := Install(context.Background(), Options{
		AssetLocation: assets.Location{PluginDir: pluginDir},
		CopilotPath:   buildFakeCopilot(t),
	})
	if err == nil {
		t.Fatal("Install() error = nil, want missing sidecar error")
	}
}

func TestInstallRollsBackManagedStateWhenCopilotInstallFails(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Windows plugin install path is covered by PowerShell smoke tests")
	}
	root := t.TempDir()
	pluginDir := filepath.Join(root, "plugin")
	mustWriteFile(t, filepath.Join(pluginDir, "plugin.json"), []byte(`{"name":"copilot-omni"}`), 0o644)
	sidecarPath := mustWriteExecutable(t, filepath.Join(root, binaryName("omni-sidecar")))
	stateDir := filepath.Join(root, "state")
	t.Setenv(pluginStateDirEnv, stateDir)
	t.Setenv("FAKE_COPILOT_FAIL", "1")
	copilotPath := buildFakeCopilot(t)

	_, err := Install(context.Background(), Options{
		AssetLocation: assets.Location{PluginDir: pluginDir},
		SidecarPath:   sidecarPath,
		CopilotPath:   copilotPath,
	})
	if err == nil {
		t.Fatal("Install() error = nil, want copilot failure")
	}
	if _, statErr := os.Stat(filepath.Join(stateDir, "plugin-install.json")); !os.IsNotExist(statErr) {
		t.Fatalf("managed install state should be rolled back, stat err = %v", statErr)
	}
}

func buildFakeCopilot(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	path := filepath.Join(root, binaryName("copilot"))
	script := "#!/bin/sh\nset -eu\n[ \"$1\" = \"plugin\" ]\n[ \"$2\" = \"install\" ]\nprintf '%s' \"$3\" > \"$FAKE_COPILOT_INSTALL_RECORD\"\n"
	if os.Getenv("FAKE_COPILOT_FAIL") == "1" {
		script += "exit 7\n"
	}
	if runtime.GOOS == "windows" {
		path = filepath.Join(root, "copilot.bat")
		script = "@echo off\r\nif not \"%1\"==\"plugin\" exit /b 1\r\nif not \"%2\"==\"install\" exit /b 1\r\nset \"TARGET=%~f3\"\r\n> \"%FAKE_COPILOT_INSTALL_RECORD%\" <nul set /p =%TARGET%\r\n"
	}
	mustWriteFile(t, path, []byte(script), 0o755)
	return path
}

func mustWriteExecutable(t *testing.T, path string) string {
	t.Helper()
	mustWriteFile(t, path, []byte("binary"), 0o755)
	return path
}

func mustWriteFile(t *testing.T, path string, content []byte, mode os.FileMode) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("MkdirAll(%q) error = %v", filepath.Dir(path), err)
	}
	if err := os.WriteFile(path, content, mode); err != nil {
		t.Fatalf("WriteFile(%q) error = %v", path, err)
	}
}

func binaryName(base string) string {
	if runtime.GOOS == "windows" {
		return base + ".exe"
	}
	return base
}
