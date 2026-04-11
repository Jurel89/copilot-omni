package compat

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
)

type Report struct {
	Platform       string        `json:"platform"`
	Arch           string        `json:"arch"`
	GoVersion      string        `json:"go_version"`
	SidecarFound   bool          `json:"sidecar_found"`
	SidecarPath    string        `json:"sidecar_path,omitempty"`
	SidecarHealthy bool          `json:"sidecar_healthy"`
	CopilotFound   bool          `json:"copilot_found"`
	CopilotPath    string        `json:"copilot_path,omitempty"`
	GitFound       bool          `json:"git_found"`
	GitVersion     string        `json:"git_version,omitempty"`
	PluginValid    bool          `json:"plugin_valid"`
	Checks         []CompatCheck `json:"checks"`
	Compatible     bool          `json:"compatible"`
	Warnings       []string      `json:"warnings,omitempty"`
}

type CompatCheck struct {
	Name   string `json:"name"`
	Status string `json:"status"`
	Detail string `json:"detail,omitempty"`
}

func RunDiagnostics(repoRoot string) (*Report, error) {
	report := &Report{
		Platform:   runtime.GOOS,
		Arch:       runtime.GOARCH,
		GoVersion:  runtime.Version(),
		Checks:     make([]CompatCheck, 0),
		Warnings:   make([]string, 0),
		Compatible: true,
	}

	report.addCheck("platform", checkPlatform())
	report.addCheck("git", checkGit())
	report.addCheck("copilot_cli", checkCopilot())
	report.addCheck("sidecar_binary", checkSidecar(repoRoot))
	report.addCheck("plugin_structure", checkPlugin(repoRoot))
	report.addCheck("repo_writable", checkRepoWritable(repoRoot))

	for _, check := range report.Checks {
		if check.Status == "fail" {
			report.Compatible = false
		}
		if check.Status == "warn" {
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
		r.CopilotPath = result.Detail
	case "sidecar_binary":
		r.SidecarFound = result.Status == "pass" || result.Status == "warn"
		r.SidecarPath = result.Detail
		r.SidecarHealthy = result.Status == "pass"
	case "plugin_structure":
		r.PluginValid = result.Status == "pass"
	}
}

func checkPlatform() CompatCheck {
	os := runtime.GOOS
	arch := runtime.GOARCH
	if os == "linux" || os == "darwin" || os == "windows" {
		return CompatCheck{Name: "platform", Status: "pass", Detail: fmt.Sprintf("%s/%s", os, arch)}
	}
	return CompatCheck{Name: "platform", Status: "warn", Detail: fmt.Sprintf("unsupported platform %s/%s", os, arch)}
}

func checkGit() CompatCheck {
	cmd := exec.Command("git", "--version")
	output, err := cmd.CombinedOutput()
	if err != nil {
		return CompatCheck{Name: "git", Status: "fail", Detail: "git not found"}
	}
	version := strings.TrimSpace(string(output))
	return CompatCheck{Name: "git", Status: "pass", Detail: version}
}

func checkCopilot() CompatCheck {
	path, err := exec.LookPath("copilot")
	if err != nil {
		return CompatCheck{Name: "copilot_cli", Status: "warn", Detail: "copilot CLI not found in PATH"}
	}
	return CompatCheck{Name: "copilot_cli", Status: "pass", Detail: path}
}

func checkSidecar(repoRoot string) CompatCheck {
	candidates := []string{
		filepath.Join(repoRoot, "sidecar", "omni-sidecar"),
		"omni-sidecar",
	}
	for _, candidate := range candidates {
		if _, err := os.Stat(candidate); err == nil {
			return CompatCheck{Name: "sidecar_binary", Status: "pass", Detail: candidate}
		}
	}
	path, err := exec.LookPath("omni-sidecar")
	if err == nil {
		return CompatCheck{Name: "sidecar_binary", Status: "pass", Detail: path}
	}
	return CompatCheck{Name: "sidecar_binary", Status: "warn", Detail: "sidecar binary not found"}
}

func checkPlugin(repoRoot string) CompatCheck {
	pluginJSON := filepath.Join(repoRoot, "plugin", "plugin.json")
	data, err := os.ReadFile(pluginJSON)
	if err != nil {
		return CompatCheck{Name: "plugin_structure", Status: "warn", Detail: "plugin.json not found"}
	}
	var parsed map[string]interface{}
	if err := json.Unmarshal(data, &parsed); err != nil {
		return CompatCheck{Name: "plugin_structure", Status: "fail", Detail: "plugin.json is invalid JSON"}
	}
	if name, ok := parsed["name"].(string); !ok || name != "copilot-omni" {
		return CompatCheck{Name: "plugin_structure", Status: "fail", Detail: "plugin.json has wrong name"}
	}
	return CompatCheck{Name: "plugin_structure", Status: "pass", Detail: "valid"}
}

func checkRepoWritable(repoRoot string) CompatCheck {
	testFile := filepath.Join(repoRoot, ".omni", ".compat-test")
	if err := os.MkdirAll(filepath.Dir(testFile), 0o755); err != nil {
		return CompatCheck{Name: "repo_writable", Status: "fail", Detail: fmt.Sprintf("cannot create .omni directory: %v", err)}
	}
	if err := os.WriteFile(testFile, []byte("test"), 0o644); err != nil {
		return CompatCheck{Name: "repo_writable", Status: "fail", Detail: fmt.Sprintf("repo not writable: %v", err)}
	}
	os.Remove(testFile)
	return CompatCheck{Name: "repo_writable", Status: "pass", Detail: "writable"}
}
