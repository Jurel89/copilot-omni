package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/Jurel89/copilot-omni/wrapper/internal/assets"
	"github.com/Jurel89/copilot-omni/wrapper/internal/copilot"
	"github.com/Jurel89/copilot-omni/wrapper/internal/install"
	"github.com/Jurel89/copilot-omni/wrapper/internal/plugininstall"
	"github.com/Jurel89/copilot-omni/wrapper/internal/sidecar"
	"github.com/Jurel89/copilot-omni/wrapper/internal/version"
	"github.com/Jurel89/copilot-omni/wrapper/internal/workflow"
)

const usage = `Usage: omni <command> [options] [arguments]

Commands:
  init              Bootstrap repository for Omni
  doctor            Run diagnostics
  plugin            Manage Copilot plugin installation
  status            Check current workflow status
  run               Start a full workflow
  plan              Plan only (no execution)
  execute           Execute an approved plan with guarded file writes
  resume            Resume an interrupted run
  research          Conduct structured research and produce a report
  audit             Export audit trail for a run
	bundle            Create, validate, or install a release bundle
  benchmark         Run performance benchmarks (Phase 6)
  migrate           Run database and config migrations (Phase 6)
  support-bundle    Generate support bundle with diagnostics (Phase 6)
  version           Print version
`

func main() {
	args := os.Args[1:]
	if len(args) == 0 {
		fmt.Print(usage)
		os.Exit(0)
	}

	switch args[0] {
	case "init":
		runInit()
	case "doctor":
		runDoctor()
	case "plugin":
		runPlugin(args[1:])
	case "status":
		runStatus()
	case "run":
		runWorkflow(args[1:])
	case "plan":
		runPlan(args[1:])
	case "execute":
		runExecute(args[1:])
	case "resume":
		runResume(args[1:])
	case "research":
		runResearch(args[1:])
	case "audit":
		runAudit(args[1:])
	case "bundle":
		runBundle(args[1:])
	case "benchmark":
		runBenchmark(args[1:])
	case "migrate":
		runMigrate(args[1:])
	case "support-bundle":
		runSupportBundle(args[1:])
	case "version":
		fmt.Printf("omni v%s\n", version.Version)
	case "--help", "-h":
		fmt.Print(usage)
	default:
		fmt.Fprintf(os.Stderr, "Unknown command: %s\n", args[0])
		fmt.Print(usage)
		os.Exit(1)
	}
}

func runInit() {
	ctx := context.Background()
	fmt.Println("Bootstrapping repository for Copilot Omni...")

	path, err := sidecar.FindSidecar()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar binary: not found (%v)\n", err)
		os.Exit(1)
	}

	mgr := sidecar.NewManager(path)
	if err := mgr.Start(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar start: failed (%v)\n", err)
		os.Exit(1)
	}
	defer stopManager(mgr)

	if err := mgr.HealthCheck(ctx, 5*time.Second); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar health: failed (%v)\n", err)
		os.Exit(1)
	}
	fmt.Println("Sidecar health: ok")

	root := repoRoot()
	location, err := assets.Locate()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Trusted assets: failed (%v)\n", err)
		os.Exit(1)
	}
	templateDir := location.TemplateDir

	managedMarkerStart := "<!-- omni:managed:start -->"
	managedMarkerEnd := "<!-- omni:managed:end -->"

	type fileGen struct {
		src  string
		dest string
	}
	gens := []fileGen{
		{filepath.Join(templateDir, "copilot-instructions.md.tmpl"), filepath.Join(root, ".github", "copilot-instructions.md")},
		{filepath.Join(templateDir, "instructions-md.md.tmpl"), filepath.Join(root, ".github", "instructions", "omni.instructions.md")},
		{filepath.Join(templateDir, "agents-md.md.tmpl"), filepath.Join(root, "AGENTS.md")},
		{filepath.Join(templateDir, "config.json.tmpl"), filepath.Join(root, ".omni", "config.json")},
	}

	for _, gen := range gens {
		if err := generateFromTemplate(gen.src, gen.dest, managedMarkerStart, managedMarkerEnd); err != nil {
			fmt.Fprintf(os.Stderr, "generate %s: %v\n", gen.dest, err)
			os.Exit(1)
		}
		fmt.Printf("  Generated: %s\n", gen.dest)
	}

	fmt.Println("\nNext: omni plugin install")
}

func runDoctor() {
	ctx := context.Background()
	fmt.Println("Running Copilot Omni diagnostics...")
	workspaceRoot := repoRoot()

	resolution, sidecarErr := sidecar.FindSidecarResolution()
	sidecarBinaryStatus := "not found"
	sidecarResolution := "unavailable"
	sidecarHealthStatus := "failed"
	var mgr *sidecar.Manager
	if sidecarErr == nil {
		sidecarBinaryStatus = fmt.Sprintf("found (%s)", resolution.Path)
		sidecarResolution = resolution.Source
		mgr = sidecar.NewManager(resolution.Path)
		if err := mgr.Start(ctx); err == nil {
			if err := mgr.HealthCheck(ctx, 5*time.Second); err == nil {
				sidecarHealthStatus = "ok"
			} else {
				sidecarHealthStatus = fmt.Sprintf("failed (%v)", err)
			}
		} else {
			sidecarHealthStatus = fmt.Sprintf("failed (%v)", err)
		}
	}

	fmt.Printf("Sidecar binary: %s\n", sidecarBinaryStatus)
	fmt.Printf("Sidecar resolution: %s\n", sidecarResolution)
	if sidecarErr != nil {
		fmt.Printf("Sidecar binary error: %v\n", sidecarErr)
	}
	fmt.Printf("Sidecar health: %s\n", sidecarHealthStatus)

	assetStatus := "not found"
	assetMode := "unknown"
	pluginStatus := "unavailable"
	templateStatus := "unavailable"
	if location, err := assets.Locate(); err == nil {
		assetStatus = location.AssetRoot
		assetMode = string(location.Mode)
		pluginStatus = fmt.Sprintf("exists (%s)", location.PluginDir)
		templateStatus = fmt.Sprintf("exists (%s)", location.TemplateDir)
	} else {
		assetStatus = fmt.Sprintf("failed (%v)", err)
	}

	if mgr != nil && mgr.IsRunning() {
		doctorResult, err := mgr.CallTool(ctx, "omni_doctor", map[string]any{
			"repo_root": workspaceRoot,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "Sidecar doctor: %v\n", err)
		} else {
			fmt.Println("Sidecar doctor report:")
			fmt.Println(doctorResult)
		}
		defer stopManager(mgr)
	} else {
		printFallbackDoctorDiagnostics()
	}

	copilotStatus := "not found"
	if copilotPath, err := copilot.FindCopilot(); err == nil {
		copilotStatus = fmt.Sprintf("found (%s)", copilotPath)
	}

	fmt.Printf("Workspace root: %s\n", workspaceRoot)
	fmt.Printf("Trusted asset root: %s\n", assetStatus)
	fmt.Printf("Trusted asset mode: %s\n", assetMode)
	fmt.Printf("Copilot CLI: %s\n", copilotStatus)
	fmt.Printf("Trusted plugin assets: %s\n", pluginStatus)
	fmt.Printf("Trusted template assets: %s\n", templateStatus)
}

func printFallbackDoctorDiagnostics() {
	if sourcePath, command, classification, remediation, ok := resolveManagedPluginInstallState(); ok {
		fmt.Println("Managed plugin install state:")
		fmt.Printf("  Source: %s\n", sourcePath)
		fmt.Printf("  Command: %s\n", command)
		fmt.Printf("  Classification: %s\n", classification)
		if remediation != "" {
			fmt.Printf("  Remediation: %s\n", remediation)
		}
		return
	}

	if sourcePath, command, classification, remediation, ok := resolveTrustedPluginCommand(); ok {
		fmt.Println("Trusted plugin fallback config:")
		fmt.Printf("  Source: %s\n", sourcePath)
		fmt.Printf("  Command: %s\n", command)
		fmt.Printf("  Classification: %s\n", classification)
		if remediation != "" {
			fmt.Printf("  Remediation: %s\n", remediation)
		}
	}
}

func resolveManagedPluginInstallState() (sourcePath string, command string, classification string, remediation string, ok bool) {
	stateDir := os.Getenv("COPILOT_OMNI_PLUGIN_STATE_DIR")
	if stateDir == "" {
		configDir, err := os.UserConfigDir()
		if err != nil {
			return "", "", "", "", false
		}
		stateDir = filepath.Join(configDir, "copilot-omni")
	}
	statePath := filepath.Join(stateDir, "plugin-install.json")
	content, err := os.ReadFile(statePath)
	if err != nil {
		return "", "", "", "", false
	}
	var state struct {
		Type    string   `json:"type"`
		Command string   `json:"command"`
		Args    []string `json:"args"`
	}
	if err := json.Unmarshal(content, &state); err != nil {
		return statePath, "", "invalid_managed_state", "Re-run 'omni plugin install' to refresh the managed plugin state.", true
	}
	classification, remediation = classifyCommandForDoctor(state.Type, state.Command, state.Args)
	return statePath, state.Command, classification, remediation, true
}

func resolveTrustedPluginCommand() (sourcePath string, command string, classification string, remediation string, ok bool) {
	location, err := assets.Locate()
	if err != nil {
		return "", "", "", "", false
	}
	configPath := filepath.Join(location.PluginDir, ".mcp.json")
	content, err := os.ReadFile(configPath)
	if err != nil {
		return "", "", "", "", false
	}
	var cfg struct {
		MCPServers map[string]struct {
			Type    string   `json:"type"`
			Command string   `json:"command"`
			Args    []string `json:"args"`
		} `json:"mcpServers"`
	}
	if err := json.Unmarshal(content, &cfg); err != nil {
		return configPath, "", "invalid_json", "Ensure the trusted .mcp.json is valid JSON.", true
	}
	server, ok := cfg.MCPServers["copilot-omni-sidecar"]
	if !ok {
		return configPath, "", "missing_server", "Ensure the trusted .mcp.json declares the copilot-omni-sidecar server.", true
	}
	classification, remediation = classifyCommandForDoctor(server.Type, server.Command, server.Args)
	return configPath, server.Command, classification, remediation, true
}

func classifyCommandForDoctor(transportType string, command string, args []string) (classification string, remediation string) {
	if strings.TrimSpace(transportType) != "stdio" {
		return "invalid_type", "Ensure the sidecar server type is 'stdio', or re-run 'omni plugin install'."
	}
	trimmed := strings.TrimSpace(command)
	if trimmed == "" {
		return "missing_command", "Set the sidecar server command to a launchable binary path or command."
	}
	if len(args) == 0 || args[0] != "serve" {
		return "invalid_args", "Ensure the sidecar server args begin with 'serve', or re-run 'omni plugin install'."
	}
	if filepath.IsAbs(trimmed) || filepath.VolumeName(trimmed) != "" || filepath.Base(trimmed) != trimmed || strings.ContainsAny(trimmed, `/\\`) {
		if _, err := os.Stat(trimmed); err == nil {
			return "explicit_existing_path", ""
		}
		return "explicit_stale_path", "Update the managed plugin state or plugin config so it points to an existing sidecar binary."
	}
	if _, err := exec.LookPath(trimmed); err == nil {
		return "bare_command_resolvable", ""
	}
	return "bare_command_missing", "Run 'omni plugin install' or place the sidecar on PATH so the configured command resolves."
}

func runPlugin(args []string) {
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "plugin requires an action: install")
		os.Exit(1)
	}

	switch args[0] {
	case "install":
		runPluginInstall(args[1:])
	default:
		fmt.Fprintf(os.Stderr, "Unknown plugin action: %s\n", args[0])
		os.Exit(1)
	}
}

func runPluginInstall(args []string) {
	keepStaging, showHelp, err := parsePluginInstallArgs(args)
	if err != nil {
		fmt.Fprintf(os.Stderr, "plugin install: %v\n", err)
		fmt.Fprintln(os.Stderr, "Usage: omni plugin install [--keep-staging]")
		os.Exit(1)
	}
	if showHelp {
		fmt.Println("Usage: omni plugin install [--keep-staging]")
		fmt.Println()
		fmt.Println("Stages trusted plugin assets, generates an explicit sidecar command path, and runs 'copilot plugin install'.")
		return
	}

	location, err := assets.Locate()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Trusted assets: failed (%v)\n", err)
		os.Exit(1)
	}

	sidecarPath, err := sidecar.FindSidecar()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar binary: not found (%v)\n", err)
		os.Exit(1)
	}

	result, err := plugininstall.Install(context.Background(), plugininstall.Options{
		AssetLocation: location,
		SidecarPath:   sidecarPath,
		KeepStaging:   keepStaging,
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "plugin install failed: %v\n", err)
		os.Exit(1)
	}

	if keepStaging {
		fmt.Printf("Plugin staging preserved at: %s\n", result.StagingDir)
	}
	fmt.Println("Plugin installed successfully")
}

func parsePluginInstallArgs(args []string) (keepStaging bool, showHelp bool, err error) {
	for _, arg := range args {
		switch arg {
		case "--keep-staging":
			keepStaging = true
		case "--help", "-h":
			showHelp = true
		case "":
			continue
		default:
			return false, false, fmt.Errorf("unknown flag %q", arg)
		}
	}
	return keepStaging, showHelp, nil
}

func runStatus() {
	ctx := context.Background()
	fmt.Println("Checking workflow status...")

	sidecarPath, err := sidecar.FindSidecar()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar binary: not found (%v)\n", err)
		os.Exit(1)
	}

	mgr := sidecar.NewManager(sidecarPath)
	defer stopManager(mgr)

	if err := mgr.Start(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar start: failed (%v)\n", err)
		os.Exit(1)
	}
	if err := mgr.HealthCheck(ctx, 5*time.Second); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar health: failed (%v)\n", err)
		os.Exit(1)
	}

	runsDir := filepath.Join(repoRoot(), ".omni", "runs")
	runID, err := findLatestRunID(runsDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "No runs found: %v\n", err)
		fmt.Fprintln(os.Stderr, "Run 'omni run <prompt>' first to create a workflow.")
		os.Exit(1)
	}

	result, err := mgr.CallTool(ctx, "omni_run_status", map[string]any{
		"repo_root": repoRoot(),
		"run_id":    runID,
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "status check failed: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("Workflow status (run: %s):\n", runID)
	fmt.Println(result)
}

func runBenchmark(args []string) {
	action := "run"
	category := ""
	benchmark := ""

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "--list", "-l":
			action = "list"
		case "--report", "-r":
			action = "report"
		case "--category", "-c":
			if i+1 < len(args) {
				category = args[i+1]
				i++
			}
		case "--benchmark", "-b":
			if i+1 < len(args) {
				benchmark = args[i+1]
				i++
			}
		default:
			if !strings.HasPrefix(args[i], "-") {
				action = args[i]
			}
		}
	}

	sidecarPath, err := sidecar.FindSidecar()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar binary: not found (%v)\n", err)
		os.Exit(1)
	}

	mgr := sidecar.NewManager(sidecarPath)
	defer stopManager(mgr)

	ctx := context.Background()
	if err := mgr.Start(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar start: failed (%v)\n", err)
		os.Exit(1)
	}
	if err := mgr.HealthCheck(ctx, 5*time.Second); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar health: failed (%v)\n", err)
		os.Exit(1)
	}

	toolArgs := map[string]any{
		"action": action,
	}
	if category != "" {
		toolArgs["category"] = category
	}
	if benchmark != "" {
		toolArgs["benchmark"] = benchmark
	}

	result, err := mgr.CallTool(ctx, "omni_benchmark", toolArgs)
	if err != nil {
		fmt.Fprintf(os.Stderr, "benchmark failed: %v\n", err)
		os.Exit(1)
	}

	if failed := parseBenchmarkFailures(result); failed > 0 {
		fmt.Fprintf(os.Stderr, "benchmark failed: %d benchmark(s) exceeded performance budgets\n", failed)
		os.Exit(1)
	}

	fmt.Println("Benchmark results:")
	fmt.Println(result)
}

func runMigrate(args []string) {
	action := "status"
	targetVersion := ""
	dryRun := false

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "status", "up", "down", "validate":
			action = args[i]
		case "--target-version", "-t":
			if i+1 < len(args) {
				targetVersion = args[i+1]
				i++
			}
		case "--dry-run", "-d":
			dryRun = true
		}
	}

	sidecarPath, err := sidecar.FindSidecar()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar binary: not found (%v)\n", err)
		os.Exit(1)
	}

	mgr := sidecar.NewManager(sidecarPath)
	defer stopManager(mgr)

	ctx := context.Background()
	if err := mgr.Start(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar start: failed (%v)\n", err)
		os.Exit(1)
	}
	if err := mgr.HealthCheck(ctx, 5*time.Second); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar health: failed (%v)\n", err)
		os.Exit(1)
	}

	toolArgs := map[string]any{
		"action":    action,
		"repo_root": repoRoot(),
		"dry_run":   dryRun,
	}
	if targetVersion != "" {
		toolArgs["target_version"] = targetVersion
	}

	result, err := mgr.CallTool(ctx, "omni_migrate", toolArgs)
	if err != nil {
		fmt.Fprintf(os.Stderr, "migrate failed: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("Migration %s:\n", action)
	fmt.Println(result)
}

func runSupportBundle(args []string) {
	outputPath := ""
	includeLogs := false
	redactionLevel := "standard"
	runID := ""

	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "--output", "-o":
			if i+1 < len(args) {
				outputPath = args[i+1]
				i++
			}
		case "--include-logs", "-l":
			includeLogs = true
		case "--redaction", "-r":
			if i+1 < len(args) {
				redactionLevel = args[i+1]
				i++
			}
		case "--run-id":
			if i+1 < len(args) {
				runID = args[i+1]
				i++
			}
		}
	}

	sidecarPath, err := sidecar.FindSidecar()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar binary: not found (%v)\n", err)
		os.Exit(1)
	}

	mgr := sidecar.NewManager(sidecarPath)
	defer stopManager(mgr)

	ctx := context.Background()
	if err := mgr.Start(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar start: failed (%v)\n", err)
		os.Exit(1)
	}
	if err := mgr.HealthCheck(ctx, 5*time.Second); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar health: failed (%v)\n", err)
		os.Exit(1)
	}

	toolArgs := map[string]any{
		"repo_root":       repoRoot(),
		"include_logs":    includeLogs,
		"redaction_level": redactionLevel,
	}
	if outputPath != "" {
		toolArgs["output_path"] = outputPath
	}
	if runID != "" {
		toolArgs["run_id"] = runID
	}

	result, err := mgr.CallTool(ctx, "omni_support_bundle", toolArgs)
	if err != nil {
		fmt.Fprintf(os.Stderr, "support bundle failed: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("Support bundle created:")
	fmt.Println(result)
}

func runWorkflow(args []string) {
	prompt := strings.TrimSpace(strings.Join(args, " "))
	if prompt == "" {
		fmt.Fprintln(os.Stderr, "run requires a prompt")
		os.Exit(1)
	}

	if _, err := copilot.FindCopilot(); err != nil {
		fmt.Fprintf(os.Stderr, "Copilot CLI: not found (%v)\n", err)
		os.Exit(1)
	}

	sidecarPath, err := sidecar.FindSidecar()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar binary: not found (%v)\n", err)
		os.Exit(1)
	}

	mgr := sidecar.NewManager(sidecarPath)
	defer stopManager(mgr)

	pluginDir, err := trustedPluginDir()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Trusted assets: failed (%v)\n", err)
		os.Exit(1)
	}

	runner := workflow.NewRunner(repoRoot(), pluginDir, mgr, workflow.StandardCopilotRunner{})
	result, err := runner.Run(context.Background(), prompt)
	if err != nil {
		fmt.Fprintf(os.Stderr, "workflow failed: %v\n", err)
		fmt.Fprintln(os.Stderr, "Remediation: inspect the latest .omni/runs/<run-id>/ artifacts and retry with 'omni resume <run-id>'.")
		if result != nil {
			printRunResult("Workflow result", result)
		}
		os.Exit(1)
	}

	printRunResult("Workflow result", result)
}

func runPlan(args []string) {
	prompt := strings.TrimSpace(strings.Join(args, " "))
	if prompt == "" {
		prompt = "Create a plan for the current repository"
	}

	if _, err := copilot.FindCopilot(); err != nil {
		fmt.Fprintf(os.Stderr, "Copilot CLI: not found (%v)\n", err)
		os.Exit(1)
	}

	sidecarPath, err := sidecar.FindSidecar()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar binary: not found (%v)\n", err)
		os.Exit(1)
	}

	mgr := sidecar.NewManager(sidecarPath)
	defer stopManager(mgr)

	pluginDir, err := trustedPluginDir()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Trusted assets: failed (%v)\n", err)
		os.Exit(1)
	}

	runner := workflow.NewRunner(repoRoot(), pluginDir, mgr, workflow.StandardCopilotRunner{})
	result, err := runner.Plan(context.Background(), prompt)
	if err != nil {
		fmt.Fprintf(os.Stderr, "plan failed: %v\n", err)
		fmt.Fprintln(os.Stderr, "Remediation: inspect the latest .omni/runs/<run-id>/ artifacts and retry with 'omni resume <run-id>'.")
		if result != nil {
			printRunResult("Plan result", result)
		}
		os.Exit(1)
	}

	printRunResult("Plan result", result)
}

func runExecute(args []string) {
	runID := ""
	if len(args) > 0 {
		runID = strings.TrimSpace(args[0])
	}

	if _, err := copilot.FindCopilot(); err != nil {
		fmt.Fprintf(os.Stderr, "Copilot CLI: not found (%v)\n", err)
		os.Exit(1)
	}

	sidecarPath, err := sidecar.FindSidecar()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar binary: not found (%v)\n", err)
		os.Exit(1)
	}

	mgr := sidecar.NewManager(sidecarPath)
	defer stopManager(mgr)

	pluginDir, err := trustedPluginDir()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Trusted assets: failed (%v)\n", err)
		os.Exit(1)
	}

	runner := workflow.NewRunner(repoRoot(), pluginDir, mgr, workflow.StandardCopilotRunner{})
	result, err := runner.Execute(context.Background(), runID)
	if err != nil {
		fmt.Fprintf(os.Stderr, "execute failed: %v\n", err)
		fmt.Fprintln(os.Stderr, "Remediation: check verification-report.json and execution journal under .omni/runs/<run-id>/")
		if result != nil {
			printRunResult("Execute result", result)
		}
		os.Exit(1)
	}

	printRunResult("Execute result", result)
}

func runResearch(args []string) {
	query := strings.TrimSpace(strings.Join(args, " "))
	if query == "" {
		fmt.Fprintln(os.Stderr, "research requires a query")
		os.Exit(1)
	}

	sidecarPath, err := sidecar.FindSidecar()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar binary: not found (%v)\n", err)
		os.Exit(1)
	}

	mgr := sidecar.NewManager(sidecarPath)
	defer stopManager(mgr)

	ctx := context.Background()
	if err := mgr.Start(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar start: failed (%v)\n", err)
		os.Exit(1)
	}
	if err := mgr.HealthCheck(ctx, 5*time.Second); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar health: failed (%v)\n", err)
		os.Exit(1)
	}

	runID := fmt.Sprintf("run-%d", time.Now().Unix())
	result, err := mgr.CallTool(ctx, "omni_research", map[string]any{
		"repo_root": repoRoot(),
		"run_id":    runID,
		"query":     query,
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "research failed: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("Research report:")
	fmt.Println(result)
	fmt.Printf("\nRun ID: %s\n", runID)
}

func runAudit(args []string) {
	runID := ""
	if len(args) > 0 {
		runID = strings.TrimSpace(args[0])
	}
	if runID == "" {
		fmt.Fprintln(os.Stderr, "audit requires a run ID")
		os.Exit(1)
	}

	sidecarPath, err := sidecar.FindSidecar()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar binary: not found (%v)\n", err)
		os.Exit(1)
	}

	mgr := sidecar.NewManager(sidecarPath)
	defer stopManager(mgr)

	ctx := context.Background()
	if err := mgr.Start(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar start: failed (%v)\n", err)
		os.Exit(1)
	}
	if err := mgr.HealthCheck(ctx, 5*time.Second); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar health: failed (%v)\n", err)
		os.Exit(1)
	}

	result, err := mgr.CallTool(ctx, "omni_audit_export", map[string]any{
		"repo_root": repoRoot(),
		"run_id":    runID,
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "audit export failed: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("Audit export:")
	fmt.Println(result)
}

func runBundle(args []string) {
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "bundle requires an action: create, validate, or install")
		os.Exit(1)
	}
	action := strings.TrimSpace(args[0])
	if action == "install" {
		runBundleInstall(args[1:])
		return
	}

	sidecarPath, err := sidecar.FindSidecar()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar binary: not found (%v)\n", err)
		os.Exit(1)
	}

	mgr := sidecar.NewManager(sidecarPath)
	defer stopManager(mgr)

	ctx := context.Background()
	if err := mgr.Start(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar start: failed (%v)\n", err)
		os.Exit(1)
	}
	if err := mgr.HealthCheck(ctx, 5*time.Second); err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar health: failed (%v)\n", err)
		os.Exit(1)
	}

	toolArgs := map[string]any{
		"repo_root": repoRoot(),
		"action":    action,
	}

	if action == "create" && len(args) > 1 {
		toolArgs["output_dir"] = args[1]
	}
	if action == "validate" && len(args) > 1 {
		toolArgs["bundle_dir"] = args[1]
	}

	result, err := mgr.CallTool(ctx, "omni_release_bundle", toolArgs)
	if err != nil {
		fmt.Fprintf(os.Stderr, "bundle %s failed: %v\n", action, err)
		os.Exit(1)
	}

	fmt.Printf("Bundle %s:\n", action)
	fmt.Println(result)
}

func runBundleInstall(args []string) {
	const bundleInstallUsage = `Usage: omni bundle install --bundle-dir <path> --target <path>

Install a validated release bundle into:
  <target>/bin
  <target>/share/copilot-omni
`

	var usage bytes.Buffer
	flagSet := flag.NewFlagSet("bundle install", flag.ContinueOnError)
	flagSet.SetOutput(&usage)
	bundleDir := flagSet.String("bundle-dir", "", "Path to the release bundle directory")
	targetDir := flagSet.String("target", "", "Installation target prefix")
	flagSet.Usage = func() {
		fmt.Fprint(&usage, bundleInstallUsage)
	}

	if err := flagSet.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			fmt.Print(usage.String())
			os.Exit(0)
		}
		fmt.Fprint(os.Stderr, usage.String())
		fmt.Fprintf(os.Stderr, "bundle install argument error: %v\n", err)
		os.Exit(1)
	}
	if flagSet.NArg() != 0 {
		fmt.Fprint(os.Stderr, usage.String())
		fmt.Fprintf(os.Stderr, "bundle install does not accept positional arguments: %s\n", strings.Join(flagSet.Args(), " "))
		os.Exit(1)
	}
	if strings.TrimSpace(*bundleDir) == "" || strings.TrimSpace(*targetDir) == "" {
		fmt.Fprint(os.Stderr, usage.String())
		fmt.Fprintln(os.Stderr, "bundle install requires --bundle-dir and --target")
		os.Exit(1)
	}

	result, err := install.Install(install.Options{BundleDir: *bundleDir, Target: *targetDir})
	if err != nil {
		fmt.Fprintf(os.Stderr, "bundle install failed: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("Bundle install:")
	fmt.Printf("  Bundle: %s\n", result.BundleDir)
	fmt.Printf("  Target: %s\n", result.TargetDir)
	fmt.Printf("  Binaries: %s\n", result.BinDir)
	fmt.Printf("  Shared assets: %s\n", result.ShareDir)
	if len(result.ValidationWarning) > 0 {
		fmt.Println("  Validation warnings:")
		for _, warning := range result.ValidationWarning {
			fmt.Printf("    - %s\n", warning)
		}
	}
}

func runResume(args []string) {
	runID := ""
	if len(args) > 0 {
		runID = strings.TrimSpace(args[0])
	}

	if _, err := copilot.FindCopilot(); err != nil {
		fmt.Fprintf(os.Stderr, "Copilot CLI: not found (%v)\n", err)
		os.Exit(1)
	}

	sidecarPath, err := sidecar.FindSidecar()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Sidecar binary: not found (%v)\n", err)
		os.Exit(1)
	}

	mgr := sidecar.NewManager(sidecarPath)
	defer stopManager(mgr)

	pluginDir, err := trustedPluginDir()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Trusted assets: failed (%v)\n", err)
		os.Exit(1)
	}

	runner := workflow.NewRunner(repoRoot(), pluginDir, mgr, workflow.StandardCopilotRunner{})
	result, err := runner.Resume(context.Background(), runID)
	if err != nil {
		fmt.Fprintf(os.Stderr, "resume failed: %v\n", err)
		fmt.Fprintln(os.Stderr, "Remediation: inspect run.json, transcripts, and generated artifacts under .omni/runs/<run-id>/ before retrying.")
		if result != nil {
			printRunResult("Resume result", result)
		}
		os.Exit(1)
	}

	printRunResult("Resume result", result)
}

func printRunResult(label string, result *workflow.RunResult) {
	if result == nil {
		return
	}

	fmt.Println(label + ":")
	fmt.Printf("  Run ID: %s\n", result.RunID)
	fmt.Printf("  Status: %s\n", result.Status)
	fmt.Printf("  Summary: %s\n", result.Summary)

	artifactKeys := make([]string, 0, len(result.ArtifactPaths))
	for key := range result.ArtifactPaths {
		artifactKeys = append(artifactKeys, key)
	}
	sort.Strings(artifactKeys)
	if len(artifactKeys) > 0 {
		fmt.Println("  Artifacts:")
		for _, key := range artifactKeys {
			fmt.Printf("    %s: %s\n", key, result.ArtifactPaths[key])
		}
	}

	fmt.Printf("  Next action: %s\n", nextActionForStatus(result.Status))
}

func nextActionForStatus(status string) string {
	switch status {
	case "blocked":
		return "Review decisions.md and resolve blocking findings before continuing."
	case "done":
		return "Review the generated artifacts, then proceed to guarded execution when ready."
	default:
		return "Inspect run.json for the last completed phase, then resume if more work remains."
	}
}

func generateFromTemplate(src, dest, markerStart, markerEnd string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return fmt.Errorf("read template: %w", err)
	}

	destDir := filepath.Dir(dest)
	if err := os.MkdirAll(destDir, 0o755); err != nil {
		return fmt.Errorf("create directory: %w", err)
	}

	existing, readErr := os.ReadFile(dest)
	if readErr == nil {
		startIdx := bytes.Index(existing, []byte(markerStart))
		endIdx := bytes.Index(existing, []byte(markerEnd))
		if startIdx >= 0 && endIdx > startIdx {
			templateStart := bytes.Index(data, []byte(markerStart))
			templateEnd := bytes.Index(data, []byte(markerEnd))
			if templateStart >= 0 && templateEnd > templateStart {
				var buf bytes.Buffer
				buf.Write(existing[:startIdx])
				buf.Write(data[templateStart : templateEnd+len(markerEnd)])
				buf.Write(existing[endIdx+len(markerEnd):])
				result := buf.Bytes()
				if len(result) > 0 && result[len(result)-1] != '\n' {
					result = append(result, '\n')
				}
				return os.WriteFile(dest, result, 0o644)
			}
		}
	}

	return os.WriteFile(dest, data, 0o644)
}

func parseBenchmarkFailures(result string) int {
	type summary struct {
		Failed int `json:"failed"`
	}
	type resultStruct struct {
		Summary summary `json:"summary"`
	}

	var r resultStruct
	if err := json.Unmarshal([]byte(result), &r); err != nil {
		return 0
	}
	return r.Summary.Failed
}

func stopManager(mgr *sidecar.Manager) {
	if err := mgr.Stop(); err != nil && !errors.Is(err, os.ErrProcessDone) {
		fmt.Fprintf(os.Stderr, "Stop sidecar: %v\n", err)
	}
}

func findLatestRunID(runsDir string) (string, error) {
	entries, err := os.ReadDir(runsDir)
	if err != nil {
		return "", fmt.Errorf("read runs directory: %w", err)
	}

	runIDs := make([]string, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() {
			runIDs = append(runIDs, entry.Name())
		}
	}
	if len(runIDs) == 0 {
		return "", fmt.Errorf("no runs found in %s", runsDir)
	}

	sort.Strings(runIDs)
	return runIDs[len(runIDs)-1], nil
}

func repoRoot() string {
	wd, err := os.Getwd()
	if err != nil {
		return "."
	}
	if out, err := exec.Command("git", "rev-parse", "--show-toplevel").Output(); err == nil {
		return strings.TrimSpace(string(out))
	}
	if location, err := assets.Locate(); err == nil {
		normalizedWD := normalizePathForCompare(wd)
		wrapperDir := normalizePathForCompare(filepath.Join(location.AssetRoot, "wrapper"))
		sidecarDir := normalizePathForCompare(filepath.Join(location.AssetRoot, "sidecar"))
		if normalizedWD == wrapperDir || normalizedWD == sidecarDir {
			return location.AssetRoot
		}
	}
	return wd
}

func normalizePathForCompare(path string) string {
	if absPath, err := filepath.Abs(path); err == nil {
		path = absPath
	}
	if resolvedPath, err := filepath.EvalSymlinks(path); err == nil {
		path = resolvedPath
	}
	return filepath.Clean(path)
}

func trustedPluginDir() (string, error) {
	location, err := assets.Locate()
	if err != nil {
		return "", err
	}
	return location.PluginDir, nil
}
