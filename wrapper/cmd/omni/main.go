package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/copilot-omni/wrapper/internal/copilot"
	"github.com/copilot-omni/wrapper/internal/sidecar"
	"github.com/copilot-omni/wrapper/internal/version"
	"github.com/copilot-omni/wrapper/internal/workflow"
)

const usage = `Usage: omni <command> [options] [arguments]

Commands:
  init              Bootstrap repository for Omni
  doctor            Run diagnostics
  status            Check current workflow status
  run               Start a full workflow
  plan              Plan only (no execution)
  execute           Execute an approved plan with guarded file writes
  resume            Resume an interrupted run
  research          Conduct structured research and produce a report
  audit             Export audit trail for a run
  bundle            Create or validate a release bundle
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
	templateDir := findTemplateDir(root)

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
			continue
		}
		fmt.Printf("  Generated: %s\n", gen.dest)
	}

	fmt.Println("\nPlugin install: copilot plugin install ./plugin")
}

func runDoctor() {
	ctx := context.Background()
	fmt.Println("Running Copilot Omni diagnostics...")

	sidecarPath, sidecarErr := sidecar.FindSidecar()
	sidecarBinaryStatus := "not found"
	sidecarHealthStatus := "failed"
	var mgr *sidecar.Manager
	if sidecarErr == nil {
		sidecarBinaryStatus = fmt.Sprintf("found (%s)", sidecarPath)
		mgr = sidecar.NewManager(sidecarPath)
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
	if sidecarErr != nil {
		fmt.Printf("Sidecar binary error: %v\n", sidecarErr)
	}
	fmt.Printf("Sidecar health: %s\n", sidecarHealthStatus)

	if mgr != nil && mgr.IsRunning() {
		doctorResult, err := mgr.CallTool(ctx, "omni_doctor", map[string]any{
			"repo_root": repoRoot(),
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "Sidecar doctor: %v\n", err)
		} else {
			fmt.Println("Sidecar doctor report:")
			fmt.Println(doctorResult)
		}
		defer stopManager(mgr)
	}

	copilotStatus := "not found"
	if copilotPath, err := copilot.FindCopilot(); err == nil {
		copilotStatus = fmt.Sprintf("found (%s)", copilotPath)
	}

	pluginDir := filepath.Join(repoRoot(), "plugin")
	pluginStatus := "missing"
	if info, err := os.Stat(pluginDir); err == nil && info.IsDir() {
		pluginStatus = fmt.Sprintf("exists (%s)", pluginDir)
	}

	fmt.Printf("Copilot CLI: %s\n", copilotStatus)
	fmt.Printf("Plugin directory: %s\n", pluginStatus)
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

	runner := workflow.NewRunner(repoRoot(), mgr, workflow.StandardCopilotRunner{})
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

	runner := workflow.NewRunner(repoRoot(), mgr, workflow.StandardCopilotRunner{})
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

	runner := workflow.NewRunner(repoRoot(), mgr, workflow.StandardCopilotRunner{})
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
		fmt.Fprintln(os.Stderr, "bundle requires an action: create or validate")
		os.Exit(1)
	}
	action := strings.TrimSpace(args[0])

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

	runner := workflow.NewRunner(repoRoot(), mgr, workflow.StandardCopilotRunner{})
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

func findTemplateDir(root string) string {
	candidates := []string{
		filepath.Join(root, "templates"),
		filepath.Join(root, "..", "templates"),
	}
	for _, dir := range candidates {
		if info, err := os.Stat(dir); err == nil && info.IsDir() {
			return dir
		}
	}
	return ""
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

func stopManager(mgr *sidecar.Manager) {
	if err := mgr.Stop(); err != nil && !errors.Is(err, os.ErrProcessDone) {
		fmt.Fprintf(os.Stderr, "Stop sidecar: %v\n", err)
	}
}

func createRunDir(root string) (string, string, error) {
	runID := fmt.Sprintf("run-%d", time.Now().Unix())
	runsDir := filepath.Join(root, ".omni", "runs")
	if err := os.MkdirAll(runsDir, 0o755); err != nil {
		return "", "", fmt.Errorf("create runs directory: %w", err)
	}

	runDir := filepath.Join(runsDir, runID)
	if err := os.MkdirAll(runDir, 0o755); err != nil {
		return "", "", fmt.Errorf("create run directory: %w", err)
	}

	return runDir, runID, nil
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
	if _, err := os.Stat(filepath.Join(wd, "plugin")); err == nil {
		return wd
	}
	if _, err := os.Stat(filepath.Join(wd, "..", "plugin")); err == nil {
		return filepath.Clean(filepath.Join(wd, ".."))
	}
	if out, err := exec.Command("git", "rev-parse", "--show-toplevel").Output(); err == nil {
		return strings.TrimSpace(string(out))
	}
	return wd
}
