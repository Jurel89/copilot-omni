package compat

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/Jurel89/copilot-omni/sidecar/internal/assets"
)

const (
	checkCategorySystem = "system"
	checkCategoryRepo   = "repo"
	checkCategoryAssets = "assets"
	checkCategoryConfig = "config"
	checkCategoryLaunch = "launch"

	assetRootEnvName  = "COPILOT_OMNI_ASSET_ROOT"
	pluginStateDirEnv = "COPILOT_OMNI_PLUGIN_STATE_DIR"
	sidecarServer     = "copilot-omni-sidecar"

	mcpCommandExplicitExistingPath = "explicit_existing_path"
	mcpCommandExplicitStalePath    = "explicit_stale_path"
	mcpCommandBareResolvable       = "bare_command_resolvable"
	mcpCommandBareMissing          = "bare_command_missing"
)

type TrustedAssets struct {
	Status          string `json:"status"`
	Mode            string `json:"mode,omitempty"`
	ExecPath        string `json:"exec_path,omitempty"`
	AssetRoot       string `json:"asset_root,omitempty"`
	PluginDir       string `json:"plugin_dir,omitempty"`
	TemplateDir     string `json:"template_dir,omitempty"`
	PolicyDir       string `json:"policy_dir,omitempty"`
	MarketplacePath string `json:"marketplace_path,omitempty"`
	Error           string `json:"error,omitempty"`
}

type MCPServerCommand struct {
	Status         string `json:"status,omitempty"`
	SourcePath     string `json:"source_path,omitempty"`
	ServerName     string `json:"server_name,omitempty"`
	Command        string `json:"command,omitempty"`
	Classification string `json:"classification,omitempty"`
	ResolvedPath   string `json:"resolved_path,omitempty"`
	Error          string `json:"error,omitempty"`
}

type managedInstallState struct {
	Version int      `json:"version"`
	Command string   `json:"command"`
	Args    []string `json:"args"`
}

type Report struct {
	Platform         string           `json:"platform"`
	Arch             string           `json:"arch"`
	GoVersion        string           `json:"go_version"`
	SidecarFound     bool             `json:"sidecar_found"`
	SidecarPath      string           `json:"sidecar_path,omitempty"`
	SidecarHealthy   bool             `json:"sidecar_healthy"`
	TrustedAssets    TrustedAssets    `json:"trusted_assets"`
	MCPServerCommand MCPServerCommand `json:"mcp_server_command"`
	CopilotFound     bool             `json:"copilot_found"`
	CopilotPath      string           `json:"copilot_path,omitempty"`
	GitFound         bool             `json:"git_found"`
	GitVersion       string           `json:"git_version,omitempty"`
	PluginValid      bool             `json:"plugin_valid"`
	Checks           []CompatCheck    `json:"checks"`
	Compatible       bool             `json:"compatible"`
	Warnings         []string         `json:"warnings,omitempty"`
}

type CompatCheck struct {
	Category string `json:"category,omitempty"`
	Name     string `json:"name"`
	Status   string `json:"status"`
	Detail   string `json:"detail,omitempty"`
}

func RunDiagnostics(repoRoot string) (*Report, error) {
	trustedAssets := resolveTrustedAssets()
	mcpCheck, mcpCommand := checkMCPConfig(trustedAssets)

	report := &Report{
		Platform:         runtime.GOOS,
		Arch:             runtime.GOARCH,
		GoVersion:        runtime.Version(),
		TrustedAssets:    trustedAssets,
		MCPServerCommand: mcpCommand,
		Checks:           make([]CompatCheck, 0),
		Warnings:         make([]string, 0),
		Compatible:       true,
	}

	report.addCheck("platform", checkPlatform())
	report.addCheck("git", checkGit())
	report.addCheck("copilot_cli", checkCopilot())
	report.addCheck("sidecar_binary", checkSidecar())
	report.addCheck("trusted_assets", checkTrustedAssets(trustedAssets))
	report.addCheck("plugin_structure", checkPlugin(trustedAssets))
	report.addCheck("repo_writable", checkRepoWritable(repoRoot))
	report.addCheck("github_settings", checkGitHubSettings(repoRoot))
	report.addCheck("mcp_config", mcpCheck)
	report.addCheck("enterprise_policy", checkEnterprisePolicy(trustedAssets))

	for _, check := range report.Checks {
		if check.Status == "fail" {
			report.Compatible = false
		}
		if check.Status == "warn" && check.Detail != "" {
			report.Warnings = append(report.Warnings, check.Detail)
		}
	}

	return report, nil
}

func (r *Report) addCheck(name string, result CompatCheck) {
	r.Checks = append(r.Checks, result)
	switch name {
	case "git":
		r.GitFound = result.Status == "pass"
		if result.Status == "pass" {
			r.GitVersion = result.Detail
		}
	case "copilot_cli":
		r.CopilotFound = result.Status == "pass"
		if result.Status == "pass" {
			r.CopilotPath = result.Detail
		}
	case "sidecar_binary":
		r.SidecarFound = result.Status == "pass"
		if result.Status == "pass" {
			r.SidecarPath = result.Detail
		}
		r.SidecarHealthy = false
	case "plugin_structure":
		r.PluginValid = result.Status == "pass"
	}
}

func checkPlatform() CompatCheck {
	os := runtime.GOOS
	arch := runtime.GOARCH
	if os == "linux" || os == "darwin" || os == "windows" {
		return CompatCheck{Category: checkCategorySystem, Name: "platform", Status: "pass", Detail: fmt.Sprintf("%s/%s", os, arch)}
	}
	return CompatCheck{Category: checkCategorySystem, Name: "platform", Status: "warn", Detail: fmt.Sprintf("unsupported platform %s/%s", os, arch)}
}

func checkGit() CompatCheck {
	cmd := exec.Command("git", "--version")
	output, err := cmd.CombinedOutput()
	if err != nil {
		return CompatCheck{Category: checkCategorySystem, Name: "git", Status: "fail", Detail: "git not found"}
	}
	version := strings.TrimSpace(string(output))
	return CompatCheck{Category: checkCategorySystem, Name: "git", Status: "pass", Detail: version}
}

func checkCopilot() CompatCheck {
	path, err := exec.LookPath("copilot")
	if err != nil {
		return CompatCheck{Category: checkCategoryLaunch, Name: "copilot_cli", Status: "warn", Detail: "copilot CLI not found in PATH"}
	}
	return CompatCheck{Category: checkCategoryLaunch, Name: "copilot_cli", Status: "pass", Detail: path}
}

func checkSidecar() CompatCheck {
	execPath, err := resolveExecutablePath()
	if err != nil {
		return CompatCheck{Category: checkCategoryLaunch, Name: "sidecar_binary", Status: "fail", Detail: err.Error()}
	}

	info, err := os.Stat(execPath)
	if err != nil {
		return CompatCheck{Category: checkCategoryLaunch, Name: "sidecar_binary", Status: "fail", Detail: fmt.Sprintf("cannot inspect sidecar executable %s: %v", execPath, err)}
	}
	if info.IsDir() {
		return CompatCheck{Category: checkCategoryLaunch, Name: "sidecar_binary", Status: "fail", Detail: fmt.Sprintf("sidecar executable %s is a directory", execPath)}
	}

	return CompatCheck{Category: checkCategoryLaunch, Name: "sidecar_binary", Status: "pass", Detail: execPath}
}

func checkTrustedAssets(trusted TrustedAssets) CompatCheck {
	if trusted.Status != "pass" {
		return CompatCheck{Category: checkCategoryAssets, Name: "trusted_assets", Status: "fail", Detail: trusted.Error}
	}

	return CompatCheck{Category: checkCategoryAssets, Name: "trusted_assets", Status: "pass", Detail: fmt.Sprintf("%s asset root %s", trusted.Mode, trusted.AssetRoot)}
}

func checkPlugin(trusted TrustedAssets) CompatCheck {
	if trusted.Status != "pass" {
		return skippedTrustedAssetCheck("plugin_structure", "skipped plugin validation because the trusted plugin directory could not be resolved", trusted.Error)
	}

	pluginJSON := filepath.Join(trusted.PluginDir, "plugin.json")
	data, err := os.ReadFile(pluginJSON)
	if err != nil {
		return CompatCheck{Category: checkCategoryConfig, Name: "plugin_structure", Status: "warn", Detail: fmt.Sprintf("trusted plugin.json not found at %s", pluginJSON)}
	}
	var parsed map[string]any
	if err := json.Unmarshal(data, &parsed); err != nil {
		return CompatCheck{Category: checkCategoryConfig, Name: "plugin_structure", Status: "fail", Detail: "trusted plugin.json is invalid JSON"}
	}
	if name, ok := parsed["name"].(string); !ok || name != "copilot-omni" {
		return CompatCheck{Category: checkCategoryConfig, Name: "plugin_structure", Status: "fail", Detail: "trusted plugin.json has wrong name"}
	}
	return CompatCheck{Category: checkCategoryConfig, Name: "plugin_structure", Status: "pass", Detail: "valid"}
}

func checkRepoWritable(repoRoot string) CompatCheck {
	testFile := filepath.Join(repoRoot, ".omni", ".compat-test")
	if err := os.MkdirAll(filepath.Dir(testFile), 0o755); err != nil {
		return CompatCheck{Category: checkCategoryRepo, Name: "repo_writable", Status: "fail", Detail: fmt.Sprintf("cannot create .omni directory: %v", err)}
	}
	if err := os.WriteFile(testFile, []byte("test"), 0o644); err != nil {
		return CompatCheck{Category: checkCategoryRepo, Name: "repo_writable", Status: "fail", Detail: fmt.Sprintf("repo not writable: %v", err)}
	}
	os.Remove(testFile)
	return CompatCheck{Category: checkCategoryRepo, Name: "repo_writable", Status: "pass", Detail: "writable"}
}

func checkGitHubSettings(repoRoot string) CompatCheck {
	instructionsPath := filepath.Join(repoRoot, ".github", "copilot-instructions.md")
	if _, err := os.Stat(instructionsPath); err != nil {
		return CompatCheck{Category: checkCategoryRepo, Name: "github_settings", Status: "warn", Detail: "copilot-instructions.md not found; GitHub Copilot integration may be incomplete"}
	}
	agentsPath := filepath.Join(repoRoot, "AGENTS.md")
	if _, err := os.Stat(agentsPath); err != nil {
		return CompatCheck{Category: checkCategoryRepo, Name: "github_settings", Status: "warn", Detail: "AGENTS.md not found; agent instructions not configured"}
	}
	return CompatCheck{Category: checkCategoryRepo, Name: "github_settings", Status: "pass", Detail: "GitHub Copilot instructions and agents configured"}
}

func checkMCPConfig(trusted TrustedAssets) (CompatCheck, MCPServerCommand) {
	command := MCPServerCommand{ServerName: sidecarServer}

	if trusted.Status != "pass" {
		command.Status = "warn"
		command.Error = trusted.Error
		return skippedTrustedAssetCheck("mcp_config", "skipped MCP config validation because the trusted plugin directory could not be resolved", trusted.Error), command
	}

	mcpPath := filepath.Join(trusted.PluginDir, ".mcp.json")
	if state, statePath, err := readManagedInstallState(); err == nil {
		command = classifyMCPCommand(statePath, state.Command, state.Args)
		command.ServerName = sidecarServer
		command.SourcePath = statePath
		if command.Status == "pass" {
			return CompatCheck{Category: checkCategoryLaunch, Name: "mcp_config", Status: "pass", Detail: fmt.Sprintf("managed plugin install configures %s as %s", sidecarServer, commandSummary(command))}, command
		}
		return CompatCheck{Category: checkCategoryLaunch, Name: "mcp_config", Status: "fail", Detail: fmt.Sprintf("managed plugin install configures %s as %s", sidecarServer, commandSummary(command))}, command
	} else if !os.IsNotExist(err) {
		command.Status = "fail"
		command.SourcePath = statePath
		command.Error = err.Error()
		return CompatCheck{Category: checkCategoryLaunch, Name: "mcp_config", Status: "fail", Detail: fmt.Sprintf("managed plugin install state is unreadable: %v", err)}, command
	}
	command.SourcePath = mcpPath
	data, err := os.ReadFile(mcpPath)
	if err != nil {
		command.Status = "warn"
		command.Error = err.Error()
		return CompatCheck{Category: checkCategoryConfig, Name: "mcp_config", Status: "warn", Detail: fmt.Sprintf("trusted plugin .mcp.json not found at %s", mcpPath)}, command
	}
	var parsed struct {
		MCPServers map[string]struct {
			Command string   `json:"command"`
			Args    []string `json:"args"`
		} `json:"mcpServers"`
	}
	if err := json.Unmarshal(data, &parsed); err != nil {
		command.Status = "fail"
		command.Error = err.Error()
		return CompatCheck{Category: checkCategoryConfig, Name: "mcp_config", Status: "fail", Detail: "trusted .mcp.json is invalid JSON"}, command
	}
	if len(parsed.MCPServers) == 0 {
		command.Status = "fail"
		command.Error = "no mcpServers defined"
		return CompatCheck{Category: checkCategoryConfig, Name: "mcp_config", Status: "fail", Detail: "trusted .mcp.json has no mcpServers defined"}, command
	}

	serverConfig, ok := parsed.MCPServers[sidecarServer]
	if !ok {
		command.Status = "fail"
		command.Error = fmt.Sprintf("%s server is not declared", sidecarServer)
		return CompatCheck{Category: checkCategoryConfig, Name: "mcp_config", Status: "fail", Detail: fmt.Sprintf("trusted .mcp.json does not declare %s", sidecarServer)}, command
	}

	command = classifyMCPCommand(mcpPath, serverConfig.Command, serverConfig.Args)
	command.ServerName = sidecarServer
	if command.Command == "" {
		return CompatCheck{Category: checkCategoryConfig, Name: "mcp_config", Status: "fail", Detail: fmt.Sprintf("trusted .mcp.json is missing the %s command", sidecarServer)}, command
	}

	if command.Status == "pass" {
		return CompatCheck{Category: checkCategoryLaunch, Name: "mcp_config", Status: "pass", Detail: fmt.Sprintf("%s configured as %s", sidecarServer, commandSummary(command))}, command
	}

	return CompatCheck{Category: checkCategoryLaunch, Name: "mcp_config", Status: "fail", Detail: fmt.Sprintf("%s configured as %s", sidecarServer, commandSummary(command))}, command
}

func readManagedInstallState() (managedInstallState, string, error) {
	stateDir, err := managedInstallStateDir()
	if err != nil {
		return managedInstallState{}, "", err
	}
	statePath := filepath.Join(stateDir, "plugin-install.json")
	content, err := os.ReadFile(statePath)
	if err != nil {
		return managedInstallState{}, statePath, err
	}
	var state managedInstallState
	if err := json.Unmarshal(content, &state); err != nil {
		return managedInstallState{}, statePath, err
	}
	return state, statePath, nil
}

func managedInstallStateDir() (string, error) {
	if override := os.Getenv(pluginStateDirEnv); override != "" {
		return override, nil
	}
	configDir, err := os.UserConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(configDir, "copilot-omni"), nil
}

func checkEnterprisePolicy(trusted TrustedAssets) CompatCheck {
	if trusted.Status != "pass" {
		return skippedTrustedAssetCheck("enterprise_policy", "skipped policy pack validation because the trusted policy directory could not be resolved", trusted.Error)
	}

	policiesDir := trusted.PolicyDir
	entries, err := os.ReadDir(policiesDir)
	if err != nil {
		return CompatCheck{Category: checkCategoryAssets, Name: "enterprise_policy", Status: "warn", Detail: "no trusted policies directory found"}
	}
	count := 0
	for _, entry := range entries {
		if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".json") {
			count++
		}
	}
	if count == 0 {
		return CompatCheck{Category: checkCategoryAssets, Name: "enterprise_policy", Status: "warn", Detail: "no trusted policy pack files found"}
	}
	return CompatCheck{Category: checkCategoryAssets, Name: "enterprise_policy", Status: "pass", Detail: fmt.Sprintf("%d policy pack(s) available", count)}
}

func resolveTrustedAssets() TrustedAssets {
	trusted := TrustedAssets{Status: "fail"}

	execPath, err := resolveExecutablePath()
	if err != nil {
		trusted.Error = err.Error()
		return trusted
	}
	trusted.ExecPath = execPath

	if overrideRoot := strings.TrimSpace(os.Getenv(assetRootEnvName)); overrideRoot != "" {
		trusted.AssetRoot = resolveReportPath(overrideRoot)
		trusted.PluginDir = filepath.Join(trusted.AssetRoot, "plugin")
		trusted.TemplateDir = filepath.Join(trusted.AssetRoot, "templates")
		trusted.PolicyDir = filepath.Join(trusted.AssetRoot, "policies")
		trusted.MarketplacePath = filepath.Join(trusted.AssetRoot, "marketplace.json")
	}

	location, err := assets.ResolveFromExecutable(execPath)
	if err != nil {
		trusted.Error = err.Error()
		return trusted
	}

	trusted.Status = "pass"
	trusted.Mode = string(location.Mode)
	trusted.AssetRoot = location.AssetRoot
	trusted.PluginDir = location.PluginDir
	trusted.TemplateDir = location.TemplateDir
	trusted.PolicyDir = location.PolicyDir
	trusted.MarketplacePath = location.MarketplacePath

	return trusted
}

func resolveExecutablePath() (string, error) {
	execPath, err := os.Executable()
	if err != nil {
		return "", fmt.Errorf("resolve executable path: %w", err)
	}

	return resolveReportPath(execPath), nil
}

func resolveReportPath(path string) string {
	if path == "" {
		return ""
	}

	absPath, err := filepath.Abs(path)
	if err == nil {
		path = absPath
	}

	resolvedPath, err := filepath.EvalSymlinks(path)
	if err == nil {
		return resolvedPath
	}

	return path
}

func skippedTrustedAssetCheck(name string, message string, cause string) CompatCheck {
	if cause == "" {
		cause = "trusted assets unavailable"
	}

	return CompatCheck{Category: checkCategoryAssets, Name: name, Status: "warn", Detail: message + ": " + cause}
}

func classifyMCPCommand(configPath string, command string, args []string) MCPServerCommand {
	classification := MCPServerCommand{
		ServerName: sidecarServer,
		SourcePath: configPath,
		Command:    strings.TrimSpace(command),
	}

	if classification.Command == "" {
		classification.Status = "fail"
		classification.Error = "missing command"
		return classification
	}
	if len(args) == 0 || args[0] != "serve" {
		classification.Status = "fail"
		classification.Classification = "invalid_args"
		classification.Error = "sidecar args must begin with serve"
		return classification
	}

	if isExplicitCommandPath(classification.Command) {
		resolvedPath := classification.Command
		if !filepath.IsAbs(resolvedPath) {
			resolvedPath = filepath.Join(filepath.Dir(configPath), resolvedPath)
		}
		classification.ResolvedPath = resolveReportPath(resolvedPath)

		info, err := os.Stat(classification.ResolvedPath)
		if err == nil && !info.IsDir() {
			classification.Status = "pass"
			classification.Classification = mcpCommandExplicitExistingPath
			return classification
		}

		classification.Status = "fail"
		classification.Classification = mcpCommandExplicitStalePath
		if err != nil {
			classification.Error = err.Error()
		} else {
			classification.Error = "configured path is a directory"
		}
		return classification
	}

	resolvedPath, err := exec.LookPath(classification.Command)
	if err != nil {
		classification.Status = "fail"
		classification.Classification = mcpCommandBareMissing
		classification.Error = err.Error()
		return classification
	}

	classification.Status = "pass"
	classification.Classification = mcpCommandBareResolvable
	classification.ResolvedPath = resolveReportPath(resolvedPath)
	return classification
}

func isExplicitCommandPath(command string) bool {
	return filepath.IsAbs(command) || strings.ContainsAny(command, `/\\`)
}

func commandSummary(command MCPServerCommand) string {
	summary := fmt.Sprintf("%q as %s", command.Command, command.Classification)
	if command.ResolvedPath != "" {
		summary += " (" + command.ResolvedPath + ")"
	}
	if command.Error != "" {
		summary += ": " + command.Error
	}

	return summary
}
