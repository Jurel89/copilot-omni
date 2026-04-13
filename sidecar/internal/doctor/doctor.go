package doctor

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/Jurel89/copilot-omni/sidecar/internal/assets"
	"github.com/Jurel89/copilot-omni/sidecar/internal/version"
)

const (
	diagnosticCategoryRepo   = "repo"
	diagnosticCategoryAssets = "assets"
	diagnosticCategoryConfig = "config"
	diagnosticCategoryLaunch = "launch"

	assetRootEnvName  = "COPILOT_OMNI_ASSET_ROOT"
	pluginStateDirEnv = "COPILOT_OMNI_PLUGIN_STATE_DIR"
	sidecarServer     = "copilot-omni-sidecar"

	mcpCommandExplicitExistingPath = "explicit_existing_path"
	mcpCommandExplicitStalePath    = "explicit_stale_path"
	mcpCommandBareResolvable       = "bare_command_resolvable"
	mcpCommandBareMissing          = "bare_command_missing"
)

type Diagnostic struct {
	Category    string `json:"category,omitempty"`
	Name        string `json:"name"`
	Status      string `json:"status"` // "pass", "fail", "warn"
	Message     string `json:"message"`
	Remediation string `json:"remediation,omitempty"`
}

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
	Status           string           `json:"status"` // "healthy", "degraded", "unhealthy"
	Version          string           `json:"version"`
	TrustedAssets    TrustedAssets    `json:"trusted_assets"`
	MCPServerCommand MCPServerCommand `json:"mcp_server_command"`
	Diagnostics      []Diagnostic     `json:"diagnostics"`
}

func CheckConfigFile(repoRoot string) Diagnostic {
	return checkPath(
		diagnosticCategoryRepo,
		"ConfigFile",
		filepath.Join(repoRoot, ".omni", "config.json"),
		false,
		"Found .omni/config.json",
		"Missing .omni/config.json",
		"Create .omni/config.json from the default Omni template.",
	)
}

func CheckInstructionsFile(repoRoot string) Diagnostic {
	return checkPath(
		diagnosticCategoryRepo,
		"InstructionsFile",
		filepath.Join(repoRoot, ".github", "copilot-instructions.md"),
		false,
		"Found .github/copilot-instructions.md",
		"Missing .github/copilot-instructions.md",
		"Create .github/copilot-instructions.md from the Omni template.",
	)
}

func CheckAgentsFile(repoRoot string) Diagnostic {
	return checkPath(
		diagnosticCategoryRepo,
		"AgentsFile",
		filepath.Join(repoRoot, "AGENTS.md"),
		false,
		"Found AGENTS.md",
		"Missing AGENTS.md",
		"Create AGENTS.md and append the Omni agents section.",
	)
}

func CheckOmniDirectory(repoRoot string) Diagnostic {
	return checkPath(
		diagnosticCategoryRepo,
		"OmniDirectory",
		filepath.Join(repoRoot, ".omni"),
		true,
		"Found .omni directory",
		"Missing .omni directory",
		"Create the .omni directory in the repository root.",
	)
}

func CheckTrustedAssets(trusted TrustedAssets) Diagnostic {
	if trusted.Status != "pass" {
		return Diagnostic{
			Category:    diagnosticCategoryAssets,
			Name:        "TrustedAssets",
			Status:      "fail",
			Message:     "Unable to resolve trusted sidecar assets: " + trusted.Error,
			Remediation: "Install the sidecar with its shipped assets, or set COPILOT_OMNI_ASSET_ROOT to a complete asset bundle.",
		}
	}

	return Diagnostic{
		Category: diagnosticCategoryAssets,
		Name:     "TrustedAssets",
		Status:   "pass",
		Message:  fmt.Sprintf("Trusted %s asset root %s", trusted.Mode, trusted.AssetRoot),
	}
}

func CheckPluginManifest(trusted TrustedAssets) Diagnostic {
	if trusted.Status != "pass" {
		return skippedTrustedAssetDiagnostic(
			"PluginManifest",
			"Skipped plugin.json validation because the trusted plugin directory could not be resolved",
			trusted.Error,
		)
	}

	manifestPath := filepath.Join(trusted.PluginDir, "plugin.json")
	data, err := os.ReadFile(manifestPath)
	if err != nil {
		if os.IsNotExist(err) {
			return Diagnostic{Category: diagnosticCategoryConfig, Name: "PluginManifest", Status: "warn", Message: "Missing trusted plugin manifest at " + manifestPath, Remediation: "Ensure the shipped plugin directory is installed with plugin.json."}
		}
		return Diagnostic{Category: diagnosticCategoryConfig, Name: "PluginManifest", Status: "fail", Message: "Cannot read trusted plugin.json: " + err.Error()}
	}
	var manifest struct {
		Name    string `json:"name"`
		Version string `json:"version"`
	}
	if err := json.Unmarshal(data, &manifest); err != nil {
		return Diagnostic{Category: diagnosticCategoryConfig, Name: "PluginManifest", Status: "fail", Message: "Trusted plugin.json is not valid JSON: " + err.Error(), Remediation: "Validate plugin.json syntax."}
	}
	if manifest.Name == "" {
		return Diagnostic{Category: diagnosticCategoryConfig, Name: "PluginManifest", Status: "fail", Message: "Trusted plugin.json missing required 'name' field", Remediation: "Add a 'name' field to plugin.json."}
	}
	return Diagnostic{Category: diagnosticCategoryConfig, Name: "PluginManifest", Status: "pass", Message: fmt.Sprintf("Trusted plugin manifest valid (%s v%s)", manifest.Name, manifest.Version)}
}

func CheckMCPConfig(trusted TrustedAssets) (Diagnostic, MCPServerCommand) {
	command := MCPServerCommand{
		ServerName: sidecarServer,
	}

	if trusted.Status != "pass" {
		command.Status = "warn"
		command.Error = trusted.Error
		return skippedTrustedAssetDiagnostic(
			"MCPConfig",
			"Skipped .mcp.json validation because the trusted plugin directory could not be resolved",
			trusted.Error,
		), command
	}

	mcpPath := filepath.Join(trusted.PluginDir, ".mcp.json")
	if state, statePath, err := readManagedInstallState(); err == nil {
		command = classifyMCPCommand(statePath, state.Command)
		command.ServerName = sidecarServer
		command.SourcePath = statePath
		if command.Status == "pass" {
			return Diagnostic{Category: diagnosticCategoryLaunch, Name: "MCPConfig", Status: "pass", Message: fmt.Sprintf("Managed plugin install configures %s as %s", sidecarServer, commandSummary(command))}, command
		}
		return Diagnostic{Category: diagnosticCategoryLaunch, Name: "MCPConfig", Status: "fail", Message: fmt.Sprintf("Managed plugin install configures %s as %s", sidecarServer, commandSummary(command)), Remediation: remediationForCommand(command)}, command
	}
	command.SourcePath = mcpPath
	data, err := os.ReadFile(mcpPath)
	if err != nil {
		if os.IsNotExist(err) {
			command.Status = "warn"
			command.Error = "trusted plugin .mcp.json not found"
			return Diagnostic{Category: diagnosticCategoryConfig, Name: "MCPConfig", Status: "warn", Message: "Missing trusted plugin .mcp.json at " + mcpPath, Remediation: "Ensure .mcp.json declares the sidecar MCP server."}, command
		}
		command.Status = "fail"
		command.Error = err.Error()
		return Diagnostic{Category: diagnosticCategoryConfig, Name: "MCPConfig", Status: "fail", Message: "Cannot read trusted .mcp.json: " + err.Error()}, command
	}
	var mcpConfig struct {
		MCPServers map[string]struct {
			Command string   `json:"command"`
			Args    []string `json:"args"`
		} `json:"mcpServers"`
	}
	if err := json.Unmarshal(data, &mcpConfig); err != nil {
		command.Status = "fail"
		command.Error = err.Error()
		return Diagnostic{Category: diagnosticCategoryConfig, Name: "MCPConfig", Status: "fail", Message: "Trusted .mcp.json is not valid JSON: " + err.Error()}, command
	}
	if len(mcpConfig.MCPServers) == 0 {
		command.Status = "fail"
		command.Error = "no mcpServers defined"
		return Diagnostic{Category: diagnosticCategoryConfig, Name: "MCPConfig", Status: "fail", Message: "Trusted .mcp.json has no mcpServers defined", Remediation: "Add at least one MCP server declaration."}, command
	}

	serverConfig, ok := mcpConfig.MCPServers[sidecarServer]
	if !ok {
		command.Status = "fail"
		command.Error = fmt.Sprintf("%s server is not declared", sidecarServer)
		return Diagnostic{Category: diagnosticCategoryConfig, Name: "MCPConfig", Status: "fail", Message: fmt.Sprintf("Trusted .mcp.json does not declare the %s server", sidecarServer), Remediation: "Add the sidecar MCP server declaration to plugin/.mcp.json."}, command
	}

	command = classifyMCPCommand(mcpPath, serverConfig.Command)
	command.ServerName = sidecarServer
	if command.Command == "" {
		return Diagnostic{Category: diagnosticCategoryConfig, Name: "MCPConfig", Status: "fail", Message: fmt.Sprintf("Trusted .mcp.json is missing a command for the %s server", sidecarServer), Remediation: "Set the sidecar server command in plugin/.mcp.json."}, command
	}

	if command.Status == "pass" {
		return Diagnostic{Category: diagnosticCategoryLaunch, Name: "MCPConfig", Status: "pass", Message: fmt.Sprintf("Trusted .mcp.json configures %s as %s", sidecarServer, commandSummary(command))}, command
	}

	return Diagnostic{Category: diagnosticCategoryLaunch, Name: "MCPConfig", Status: "fail", Message: fmt.Sprintf("Trusted .mcp.json configures %s as %s", sidecarServer, commandSummary(command)), Remediation: remediationForCommand(command)}, command
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

func CheckHooksConfig(trusted TrustedAssets) Diagnostic {
	if trusted.Status != "pass" {
		return skippedTrustedAssetDiagnostic(
			"HooksConfig",
			"Skipped hooks.json validation because the trusted plugin directory could not be resolved",
			trusted.Error,
		)
	}

	hooksPath := filepath.Join(trusted.PluginDir, "hooks.json")
	data, err := os.ReadFile(hooksPath)
	if err != nil {
		if os.IsNotExist(err) {
			return Diagnostic{Name: "HooksConfig", Category: diagnosticCategoryConfig, Status: "warn", Message: "Missing trusted hooks.json at " + hooksPath, Remediation: "Create hooks.json with preToolUse policy."}
		}
		return Diagnostic{Name: "HooksConfig", Category: diagnosticCategoryConfig, Status: "fail", Message: "Cannot read trusted hooks.json: " + err.Error()}
	}
	var hooks struct {
		Version int                   `json:"version"`
		Hooks   map[string][]struct{} `json:"hooks"`
	}
	if err := json.Unmarshal(data, &hooks); err != nil {
		return Diagnostic{Name: "HooksConfig", Category: diagnosticCategoryConfig, Status: "fail", Message: "Trusted hooks.json is not valid JSON: " + err.Error()}
	}
	if hooks.Version != 1 {
		return Diagnostic{Name: "HooksConfig", Category: diagnosticCategoryConfig, Status: "fail", Message: "Trusted hooks.json version must be 1", Remediation: "Set version to 1 in hooks.json."}
	}
	_, hasPreToolUse := hooks.Hooks["preToolUse"]
	if !hasPreToolUse {
		return Diagnostic{Name: "HooksConfig", Category: diagnosticCategoryConfig, Status: "warn", Message: "Trusted hooks.json has no preToolUse hook", Remediation: "Add a preToolUse hook for policy enforcement."}
	}
	return Diagnostic{Name: "HooksConfig", Category: diagnosticCategoryConfig, Status: "pass", Message: "Trusted hooks.json valid with preToolUse policy"}
}

func CheckMemoryDatabase(repoRoot string) Diagnostic {
	memoryPath := filepath.Join(repoRoot, ".omni", "memory.db")
	info, err := os.Stat(memoryPath)
	if err != nil {
		if os.IsNotExist(err) {
			return Diagnostic{
				Category:    diagnosticCategoryRepo,
				Name:        "MemoryDatabase",
				Status:      "warn",
				Message:     "No memory database found at .omni/memory.db",
				Remediation: "Memory will be created on first use. Run omni-memory or omni-run to initialize.",
			}
		}
		return Diagnostic{
			Category:    diagnosticCategoryRepo,
			Name:        "MemoryDatabase",
			Status:      "fail",
			Message:     "Cannot stat memory database: " + err.Error(),
			Remediation: "Check filesystem permissions on .omni/memory.db",
		}
	}

	if info.IsDir() {
		return Diagnostic{
			Category:    diagnosticCategoryRepo,
			Name:        "MemoryDatabase",
			Status:      "fail",
			Message:     ".omni/memory.db is a directory, expected a file",
			Remediation: "Remove the directory and let Omni create the database file.",
		}
	}

	file, err := os.Open(memoryPath)
	if err != nil {
		return Diagnostic{
			Category:    diagnosticCategoryRepo,
			Name:        "MemoryDatabase",
			Status:      "warn",
			Message:     "Cannot open memory database for validation",
			Remediation: "Check filesystem permissions on .omni/memory.db",
		}
	}
	defer file.Close()

	const sqliteHeader = "SQLite format 3\x00"
	header := make([]byte, len(sqliteHeader))
	n, _ := file.Read(header)
	if info.Size() > 0 && (n < len(sqliteHeader) || string(header[:len(sqliteHeader)]) != sqliteHeader) {
		return Diagnostic{
			Category:    diagnosticCategoryRepo,
			Name:        "MemoryDatabase",
			Status:      "fail",
			Message:     ".omni/memory.db is not a valid SQLite database",
			Remediation: "Delete the corrupted file and let Omni recreate it.",
		}
	}

	sizeMB := info.Size() / (1024 * 1024)
	status := "pass"
	message := fmt.Sprintf("Memory database found (%d MB)", sizeMB)
	if sizeMB > 200 {
		status = "warn"
		message = fmt.Sprintf("Memory database is large (%d MB). Consider pruning.", sizeMB)
	}

	return Diagnostic{Category: diagnosticCategoryRepo, Name: "MemoryDatabase", Status: status, Message: message}
}

func RunAll(repoRoot string) Report {
	trustedAssets := resolveTrustedAssets()
	mcpDiagnostic, mcpCommand := CheckMCPConfig(trustedAssets)

	diagnostics := []Diagnostic{
		CheckConfigFile(repoRoot),
		CheckInstructionsFile(repoRoot),
		CheckAgentsFile(repoRoot),
		CheckOmniDirectory(repoRoot),
		CheckTrustedAssets(trustedAssets),
		CheckPluginManifest(trustedAssets),
		mcpDiagnostic,
		CheckHooksConfig(trustedAssets),
		CheckMemoryDatabase(repoRoot),
	}

	reportStatus := "healthy"
	for _, diagnostic := range diagnostics {
		switch diagnostic.Status {
		case "fail":
			reportStatus = "unhealthy"
		case "warn":
			if reportStatus != "unhealthy" {
				reportStatus = "degraded"
			}
		}
	}

	return Report{
		Status:           reportStatus,
		Version:          version.Version,
		TrustedAssets:    trustedAssets,
		MCPServerCommand: mcpCommand,
		Diagnostics:      diagnostics,
	}
}

func checkPath(category string, name string, targetPath string, expectDir bool, passMessage string, warnMessage string, remediation string) Diagnostic {
	info, err := os.Stat(targetPath)
	if err == nil {
		if expectDir && !info.IsDir() {
			return Diagnostic{
				Category:    category,
				Name:        name,
				Status:      "fail",
				Message:     targetPath + " exists but is not a directory",
				Remediation: remediation,
			}
		}

		if !expectDir && info.IsDir() {
			return Diagnostic{
				Category:    category,
				Name:        name,
				Status:      "fail",
				Message:     targetPath + " exists but is not a file",
				Remediation: remediation,
			}
		}

		return Diagnostic{Category: category, Name: name, Status: "pass", Message: passMessage}
	}

	if os.IsNotExist(err) {
		return Diagnostic{
			Category:    category,
			Name:        name,
			Status:      "warn",
			Message:     warnMessage,
			Remediation: remediation,
		}
	}

	return Diagnostic{
		Category:    category,
		Name:        name,
		Status:      "fail",
		Message:     "Unable to inspect " + targetPath + ": " + err.Error(),
		Remediation: "Check filesystem permissions and try again.",
	}
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

func skippedTrustedAssetDiagnostic(name string, message string, cause string) Diagnostic {
	if cause == "" {
		cause = "trusted assets unavailable"
	}

	return Diagnostic{
		Category:    diagnosticCategoryAssets,
		Name:        name,
		Status:      "warn",
		Message:     message + ": " + cause,
		Remediation: "Fix trusted asset resolution before validating shipped plugin files.",
	}
}

func classifyMCPCommand(configPath string, command string) MCPServerCommand {
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

func remediationForCommand(command MCPServerCommand) string {
	switch command.Classification {
	case mcpCommandExplicitStalePath:
		return "Update plugin/.mcp.json to point at an existing sidecar binary, or switch to a command available on PATH."
	case mcpCommandBareMissing:
		return "Install the sidecar binary on PATH, or configure plugin/.mcp.json with an explicit binary path."
	default:
		return "Update plugin/.mcp.json so the sidecar server command resolves to a launchable binary."
	}
}
