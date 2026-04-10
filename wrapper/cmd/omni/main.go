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

const usage = "Usage: omni <command> [options] [arguments]\n\nCommands:\n  init      Bootstrap repository for Omni\n  doctor    Run diagnostics\n  run       Start a full workflow\n  plan      Plan only (no execution)\n  execute   Execute an approved plan with guarded file writes\n  resume    Resume an interrupted run\n  version   Print version\n"

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
	case "run":
		runWorkflow(args[1:])
	case "plan":
		runPlan(args[1:])
	case "execute":
		runExecute(args[1:])
	case "resume":
		runResume(args[1:])
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
