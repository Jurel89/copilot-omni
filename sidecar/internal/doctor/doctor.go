package doctor

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"github.com/copilot-omni/sidecar/internal/version"
)

type Diagnostic struct {
	Name        string `json:"name"`
	Status      string `json:"status"` // "pass", "fail", "warn"
	Message     string `json:"message"`
	Remediation string `json:"remediation,omitempty"`
}

type Report struct {
	Status      string       `json:"status"` // "healthy", "degraded", "unhealthy"
	Version     string       `json:"version"`
	Diagnostics []Diagnostic `json:"diagnostics"`
}

func CheckConfigFile(repoRoot string) Diagnostic {
	return checkPath(
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
		"OmniDirectory",
		filepath.Join(repoRoot, ".omni"),
		true,
		"Found .omni directory",
		"Missing .omni directory",
		"Create the .omni directory in the repository root.",
	)
}

func CheckPluginManifest(repoRoot string) Diagnostic {
	manifestPath := filepath.Join(repoRoot, "plugin", "plugin.json")
	data, err := os.ReadFile(manifestPath)
	if err != nil {
		if os.IsNotExist(err) {
			return Diagnostic{Name: "PluginManifest", Status: "warn", Message: "Missing plugin/plugin.json", Remediation: "Ensure the plugin directory is installed."}
		}
		return Diagnostic{Name: "PluginManifest", Status: "fail", Message: "Cannot read plugin.json: " + err.Error()}
	}
	var manifest struct {
		Name    string `json:"name"`
		Version string `json:"version"`
	}
	if err := json.Unmarshal(data, &manifest); err != nil {
		return Diagnostic{Name: "PluginManifest", Status: "fail", Message: "plugin.json is not valid JSON: " + err.Error(), Remediation: "Validate plugin.json syntax."}
	}
	if manifest.Name == "" {
		return Diagnostic{Name: "PluginManifest", Status: "fail", Message: "plugin.json missing required 'name' field", Remediation: "Add a 'name' field to plugin.json."}
	}
	return Diagnostic{Name: "PluginManifest", Status: "pass", Message: "plugin.json valid (" + manifest.Name + " v" + manifest.Version + ")"}
}

func CheckMCPConfig(repoRoot string) Diagnostic {
	mcpPath := filepath.Join(repoRoot, "plugin", ".mcp.json")
	data, err := os.ReadFile(mcpPath)
	if err != nil {
		if os.IsNotExist(err) {
			return Diagnostic{Name: "MCPConfig", Status: "warn", Message: "Missing plugin/.mcp.json", Remediation: "Ensure .mcp.json declares the sidecar MCP server."}
		}
		return Diagnostic{Name: "MCPConfig", Status: "fail", Message: "Cannot read .mcp.json: " + err.Error()}
	}
	var mcpConfig struct {
		MCPServers map[string]struct{} `json:"mcpServers"`
	}
	if err := json.Unmarshal(data, &mcpConfig); err != nil {
		return Diagnostic{Name: "MCPConfig", Status: "fail", Message: ".mcp.json is not valid JSON: " + err.Error()}
	}
	if len(mcpConfig.MCPServers) == 0 {
		return Diagnostic{Name: "MCPConfig", Status: "fail", Message: ".mcp.json has no mcpServers defined", Remediation: "Add at least one MCP server declaration."}
	}
	return Diagnostic{Name: "MCPConfig", Status: "pass", Message: ".mcp.json valid with " + fmt.Sprintf("%d", len(mcpConfig.MCPServers)) + " server(s)"}
}

func CheckHooksConfig(repoRoot string) Diagnostic {
	hooksPath := filepath.Join(repoRoot, "plugin", "hooks.json")
	data, err := os.ReadFile(hooksPath)
	if err != nil {
		if os.IsNotExist(err) {
			return Diagnostic{Name: "HooksConfig", Status: "warn", Message: "Missing plugin/hooks.json", Remediation: "Create hooks.json with preToolUse policy."}
		}
		return Diagnostic{Name: "HooksConfig", Status: "fail", Message: "Cannot read hooks.json: " + err.Error()}
	}
	var hooks struct {
		Version int                   `json:"version"`
		Hooks   map[string][]struct{} `json:"hooks"`
	}
	if err := json.Unmarshal(data, &hooks); err != nil {
		return Diagnostic{Name: "HooksConfig", Status: "fail", Message: "hooks.json is not valid JSON: " + err.Error()}
	}
	if hooks.Version != 1 {
		return Diagnostic{Name: "HooksConfig", Status: "fail", Message: "hooks.json version must be 1", Remediation: "Set version to 1 in hooks.json."}
	}
	_, hasPreToolUse := hooks.Hooks["preToolUse"]
	if !hasPreToolUse {
		return Diagnostic{Name: "HooksConfig", Status: "warn", Message: "hooks.json has no preToolUse hook", Remediation: "Add a preToolUse hook for policy enforcement."}
	}
	return Diagnostic{Name: "HooksConfig", Status: "pass", Message: "hooks.json valid with preToolUse policy"}
}

func CheckMemoryDatabase(repoRoot string) Diagnostic {
	memoryPath := filepath.Join(repoRoot, ".omni", "memory.db")
	info, err := os.Stat(memoryPath)
	if err != nil {
		if os.IsNotExist(err) {
			return Diagnostic{
				Name:        "MemoryDatabase",
				Status:      "warn",
				Message:     "No memory database found at .omni/memory.db",
				Remediation: "Memory will be created on first use. Run omni-memory or omni-run to initialize.",
			}
		}
		return Diagnostic{
			Name:        "MemoryDatabase",
			Status:      "fail",
			Message:     "Cannot stat memory database: " + err.Error(),
			Remediation: "Check filesystem permissions on .omni/memory.db",
		}
	}

	if info.IsDir() {
		return Diagnostic{
			Name:        "MemoryDatabase",
			Status:      "fail",
			Message:     ".omni/memory.db is a directory, expected a file",
			Remediation: "Remove the directory and let Omni create the database file.",
		}
	}

	file, err := os.Open(memoryPath)
	if err != nil {
		return Diagnostic{
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

	return Diagnostic{Name: "MemoryDatabase", Status: status, Message: message}
}

func RunAll(repoRoot string) Report {
	diagnostics := []Diagnostic{
		CheckConfigFile(repoRoot),
		CheckInstructionsFile(repoRoot),
		CheckAgentsFile(repoRoot),
		CheckOmniDirectory(repoRoot),
		CheckPluginManifest(repoRoot),
		CheckMCPConfig(repoRoot),
		CheckHooksConfig(repoRoot),
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
		Status:      reportStatus,
		Version:     version.Version,
		Diagnostics: diagnostics,
	}
}

func checkPath(name string, targetPath string, expectDir bool, passMessage string, warnMessage string, remediation string) Diagnostic {
	info, err := os.Stat(targetPath)
	if err == nil {
		if expectDir && !info.IsDir() {
			return Diagnostic{
				Name:        name,
				Status:      "fail",
				Message:     targetPath + " exists but is not a directory",
				Remediation: remediation,
			}
		}

		if !expectDir && info.IsDir() {
			return Diagnostic{
				Name:        name,
				Status:      "fail",
				Message:     targetPath + " exists but is not a file",
				Remediation: remediation,
			}
		}

		return Diagnostic{Name: name, Status: "pass", Message: passMessage}
	}

	if os.IsNotExist(err) {
		return Diagnostic{
			Name:        name,
			Status:      "warn",
			Message:     warnMessage,
			Remediation: remediation,
		}
	}

	return Diagnostic{
		Name:        name,
		Status:      "fail",
		Message:     "Unable to inspect " + targetPath + ": " + err.Error(),
		Remediation: "Check filesystem permissions and try again.",
	}
}
