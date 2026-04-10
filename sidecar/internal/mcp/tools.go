package mcp

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/copilot-omni/sidecar/internal/artifact"
	"github.com/copilot-omni/sidecar/internal/config"
	"github.com/copilot-omni/sidecar/internal/doctor"
	runpkg "github.com/copilot-omni/sidecar/internal/run"
	"github.com/copilot-omni/sidecar/internal/schema"
	"github.com/copilot-omni/sidecar/internal/version"
)

type ToolHandler func(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error)

type ConfigResolver func(repoRoot string) (*config.Config, error)

type Registry struct {
	startedAt      time.Time
	tools          map[string]registeredTool
	configResolver ConfigResolver
}

type registeredTool struct {
	definition Tool
	handler    ToolHandler
}

func NewRegistry(startedAt time.Time, resolver ConfigResolver) *Registry {
	registry := &Registry{
		startedAt:      startedAt,
		tools:          make(map[string]registeredTool),
		configResolver: resolver,
	}

	registry.register(
		Tool{
			Name:        "omni_health",
			Description: "Check sidecar health and return version information",
			InputSchema: InputSchema{
				Type:       "object",
				Properties: map[string]interface{}{},
				Required:   []string{},
			},
		},
		registry.omniHealth,
	)

	registry.register(
		Tool{
			Name:        "omni_doctor",
			Description: "Run diagnostics on the Omni installation and return a health report",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
				},
				Required: []string{"repo_root"},
			},
		},
		registry.omniDoctor,
	)

	registry.register(
		Tool{
			Name:        "omni_config_resolve",
			Description: "Resolve and return the merged configuration for the current context",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
				},
				Required: []string{"repo_root"},
			},
		},
		registry.omniConfigResolve,
	)

	registry.register(
		Tool{
			Name:        "omni_artifact_read",
			Description: "Read a workflow artifact from .omni/runs/<run-id>/. Returns artifact content as text.",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"run_id": map[string]interface{}{
						"type":        "string",
						"description": "Run ID containing the artifact",
					},
					"filename": map[string]interface{}{
						"type":        "string",
						"description": "Artifact filename (e.g. spec.md, plan.md, transcript.md)",
					},
				},
				Required: []string{"repo_root", "run_id", "filename"},
			},
		},
		registry.omniArtifactRead,
	)

	registry.register(
		Tool{
			Name:        "omni_artifact_write",
			Description: "Write a workflow artifact to .omni/runs/<run-id>/. Creates the run directory if needed.",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"run_id": map[string]interface{}{
						"type":        "string",
						"description": "Run ID for the artifact",
					},
					"filename": map[string]interface{}{
						"type":        "string",
						"description": "Artifact filename (e.g. spec.md, plan.md, decisions.json)",
					},
					"content": map[string]interface{}{
						"type":        "string",
						"description": "Artifact content to write",
					},
				},
				Required: []string{"repo_root", "run_id", "filename", "content"},
			},
		},
		registry.omniArtifactWrite,
	)

	registry.register(
		Tool{
			Name:        "omni_run_status",
			Description: "Return the authoritative run-state snapshot including status, current phase, next safe action, blockers, and artifact paths.",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"run_id": map[string]interface{}{
						"type":        "string",
						"description": "Run ID to look up",
					},
				},
				Required: []string{"repo_root", "run_id"},
			},
		},
		registry.omniRunStatus,
	)

	registry.register(
		Tool{
			Name:        "omni_resume_context",
			Description: "Build a deterministic resume bundle from artifacts so the wrapper can restart at the correct phase with bounded context.",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"run_id": map[string]interface{}{
						"type":        "string",
						"description": "Run ID to resume",
					},
				},
				Required: []string{"repo_root", "run_id"},
			},
		},
		registry.omniResumeContext,
	)

	return registry
}

func (r *Registry) register(tool Tool, handler ToolHandler) {
	r.tools[tool.Name] = registeredTool{definition: tool, handler: handler}
}

func (r *Registry) List() []Tool {
	toolNames := make([]string, 0, len(r.tools))
	for name := range r.tools {
		toolNames = append(toolNames, name)
	}
	sort.Strings(toolNames)

	tools := make([]Tool, 0, len(r.tools))
	for _, name := range toolNames {
		tools = append(tools, r.tools[name].definition)
	}
	return tools
}

func (r *Registry) Call(ctx context.Context, name string, arguments map[string]interface{}) (ToolCallResult, error) {
	tool, ok := r.tools[name]
	if !ok {
		return ToolCallResult{}, fmt.Errorf("unknown tool: %s", name)
	}

	if arguments == nil {
		arguments = map[string]interface{}{}
	}

	return tool.handler(ctx, arguments)
}

func (r *Registry) omniHealth(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	health := map[string]interface{}{
		"status":         "ok",
		"version":        version.Version,
		"protocol":       "mcp",
		"uptime_seconds": int(time.Since(r.startedAt).Seconds()),
	}

	payload, err := json.Marshal(health)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("marshal omni_health response: %w", err)
	}

	return ToolCallResult{
		Content: []ToolContent{{
			Type: "text",
			Text: string(payload),
		}},
	}, nil
}

func (r *Registry) omniDoctor(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, ok := arguments["repo_root"].(string)
	if !ok || repoRoot == "" {
		return ToolCallResult{}, fmt.Errorf("repo_root must be a non-empty string")
	}

	report := doctor.RunAll(repoRoot)
	payload, err := json.Marshal(report)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("marshal omni_doctor response: %w", err)
	}

	return ToolCallResult{
		Content: []ToolContent{{
			Type: "text",
			Text: string(payload),
		}},
	}, nil
}

func (r *Registry) omniConfigResolve(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	if r.configResolver == nil {
		return ToolCallResult{}, fmt.Errorf("config resolver is not configured")
	}

	repoRoot, ok := arguments["repo_root"].(string)
	if !ok || repoRoot == "" {
		return ToolCallResult{}, fmt.Errorf("repo_root must be a non-empty string")
	}

	resolvedConfig, err := r.configResolver(repoRoot)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("resolve config: %w", err)
	}

	payload, err := json.Marshal(resolvedConfig)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("marshal omni_config_resolve response: %w", err)
	}

	return ToolCallResult{
		Content: []ToolContent{{
			Type: "text",
			Text: string(payload),
		}},
	}, nil
}

func validateArtifactPath(repoRoot, runID, filename string) (string, error) {
	if repoRoot == "" || runID == "" || filename == "" {
		return "", fmt.Errorf("repo_root, run_id, and filename are required")
	}

	if strings.Contains(runID, "..") || strings.Contains(filename, "..") {
		return "", fmt.Errorf("invalid run_id or filename: path traversal rejected")
	}

	if filepath.IsAbs(runID) || filepath.IsAbs(filename) {
		return "", fmt.Errorf("invalid run_id or filename: absolute paths rejected")
	}

	runDir := filepath.Join(repoRoot, ".omni", "runs", runID)
	artifactPath := filepath.Join(runDir, filename)

	cleanedPath := filepath.Clean(artifactPath)
	if !strings.HasPrefix(cleanedPath, filepath.Clean(runDir)+string(os.PathSeparator)) && cleanedPath != filepath.Clean(runDir) {
		return "", fmt.Errorf("invalid artifact path: escapes run directory")
	}

	return artifactPath, nil
}

func (r *Registry) omniArtifactRead(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, _ := arguments["repo_root"].(string)
	runID, _ := arguments["run_id"].(string)
	filename, _ := arguments["filename"].(string)

	var data []byte
	switch filename {
	case "spec.md":
		store := artifact.NewStore(repoRoot)
		content, err := store.ReadSpec(runID)
		if err != nil {
			return ToolCallResult{}, fmt.Errorf("read spec %s: %w", runID, err)
		}
		data = []byte(content)
	case "plan.json":
		store := artifact.NewStore(repoRoot)
		plan, err := store.ReadPlan(runID)
		if err != nil {
			return ToolCallResult{}, fmt.Errorf("read plan %s: %w", runID, err)
		}
		var marshalErr error
		data, marshalErr = json.Marshal(plan)
		if marshalErr != nil {
			return ToolCallResult{}, fmt.Errorf("marshal plan for read: %w", marshalErr)
		}
	case "decisions.md":
		store := artifact.NewStore(repoRoot)
		content, err := store.ReadDecisions(runID)
		if err != nil {
			return ToolCallResult{}, fmt.Errorf("read decisions %s: %w", runID, err)
		}
		data = []byte(content)
	default:
		artifactPath, err := validateArtifactPath(repoRoot, runID, filename)
		if err != nil {
			return ToolCallResult{}, err
		}
		data, err = os.ReadFile(artifactPath)
		if err != nil {
			return ToolCallResult{}, fmt.Errorf("read artifact %s/%s: %w", runID, filename, err)
		}
	}

	return ToolCallResult{
		Content: []ToolContent{{
			Type: "text",
			Text: string(data),
		}},
	}, nil
}

func runCanonicalFallback(repoRoot, runID string, artifactPaths map[string]string) {
	fallbacks := map[string]string{
		"spec":     filepath.Join(repoRoot, ".omni", "runs", runID, "spec.md"),
		"plan":     filepath.Join(repoRoot, ".omni", "runs", runID, "plan.json"),
		"decision": filepath.Join(repoRoot, ".omni", "runs", runID, "decisions.md"),
	}
	for key, path := range fallbacks {
		if _, ok := artifactPaths[key]; !ok {
			if _, err := os.Stat(path); err == nil {
				artifactPaths[key] = path
			}
		}
	}
}

func (r *Registry) omniRunStatus(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, _ := arguments["repo_root"].(string)
	runID, _ := arguments["run_id"].(string)

	if repoRoot == "" || runID == "" {
		return ToolCallResult{}, fmt.Errorf("repo_root and run_id are required")
	}

	store := artifact.NewStore(repoRoot)
	runObj, err := store.ReadRun(runID)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("read run %s: %w", runID, err)
	}

	artifactPaths, _ := store.ListRunArtifacts(runID)
	if artifactPaths == nil {
		artifactPaths = make(map[string]string)
	}

	runCanonicalFallback(repoRoot, runID, artifactPaths)

	summary := runpkg.Summarize(runObj)
	if summary == nil {
		return ToolCallResult{}, fmt.Errorf("run %s: failed to generate summary", runID)
	}

	response := map[string]interface{}{
		"run_id":                summary.RunID,
		"status":                summary.Status,
		"current_phase":         summary.CurrentPhase,
		"last_completed_action": summary.LastCompletedAction,
		"next_safe_action":      summary.NextSafeAction,
		"blockers":              summary.Blockers,
		"artifact_paths":        artifactPaths,
	}

	payload, err := json.Marshal(response)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("marshal omni_run_status response: %w", err)
	}

	return ToolCallResult{
		Content: []ToolContent{{
			Type: "text",
			Text: string(payload),
		}},
	}, nil
}

func (r *Registry) omniResumeContext(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, _ := arguments["repo_root"].(string)
	runID, _ := arguments["run_id"].(string)

	if repoRoot == "" || runID == "" {
		return ToolCallResult{}, fmt.Errorf("repo_root and run_id are required")
	}

	store := artifact.NewStore(repoRoot)
	runObj, err := store.ReadRun(runID)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("read run %s: %w", runID, err)
	}

	hydrateFrom := make(map[string]interface{})
	artifactPaths, _ := store.ListRunArtifacts(runID)

	if spec, err := store.ReadSpec(runID); err == nil {
		hydrateFrom["spec"] = spec
	} else if data, err := os.ReadFile(filepath.Join(repoRoot, ".omni", "runs", runID, "spec.md")); err == nil {
		hydrateFrom["spec"] = string(data)
		if artifactPaths == nil {
			artifactPaths = make(map[string]string)
		}
		artifactPaths["spec"] = filepath.Join(repoRoot, ".omni", "runs", runID, "spec.md")
	}

	if plan, err := store.ReadPlan(runID); err == nil {
		hydrateFrom["plan"] = plan
	} else if data, err := os.ReadFile(filepath.Join(repoRoot, ".omni", "runs", runID, "plan.json")); err == nil {
		var planObj map[string]interface{}
		if json.Unmarshal(data, &planObj) == nil {
			hydrateFrom["plan"] = planObj
		} else {
			hydrateFrom["plan"] = string(data)
		}
		if artifactPaths == nil {
			artifactPaths = make(map[string]string)
		}
		artifactPaths["plan"] = filepath.Join(repoRoot, ".omni", "runs", runID, "plan.json")
	}

	if decisions, err := store.ReadDecisions(runID); err == nil {
		hydrateFrom["decisions"] = decisions
	} else if data, err := os.ReadFile(filepath.Join(repoRoot, ".omni", "runs", runID, "decisions.md")); err == nil {
		hydrateFrom["decisions"] = string(data)
		if artifactPaths == nil {
			artifactPaths = make(map[string]string)
		}
		artifactPaths["decision"] = filepath.Join(repoRoot, ".omni", "runs", runID, "decisions.md")
	}

	transcripts := make(map[string]string)
	for key, path := range artifactPaths {
		if strings.HasPrefix(key, "transcript:") {
			phase := strings.TrimPrefix(key, "transcript:")
			data, err := os.ReadFile(path)
			if err == nil {
				transcripts[phase] = string(data)
			}
		}
	}
	if len(transcripts) > 0 {
		hydrateFrom["transcripts"] = transcripts
	}

	hydrateFrom["run"] = runObj

	summary := runpkg.Summarize(runObj)
	if summary == nil {
		summary = &runpkg.RunSummary{}
	}

	response := map[string]interface{}{
		"run_id":             runObj.ID,
		"status":             string(runObj.Status),
		"hydrate_from":       hydrateFrom,
		"artifact_paths":     artifactPaths,
		"summary":            summary.NextSafeAction,
		"recommended_prompt": r.buildResumePrompt(runObj),
		"next_safe_action":   runpkg.NextSafeAction(runObj),
	}

	payload, err := json.Marshal(response)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("marshal omni_resume_context response: %w", err)
	}

	return ToolCallResult{
		Content: []ToolContent{{
			Type: "text",
			Text: string(payload),
		}},
	}, nil
}

func (r *Registry) buildResumePrompt(runObj *runpkg.Run) string {
	switch runObj.Status {
	case runpkg.StatusDraft:
		return "Continue the discuss/spec phase to generate a specification from the original prompt."
	case runpkg.StatusSpecReady:
		return "A specification exists. Continue with the plan phase to create an implementation plan."
	case runpkg.StatusPlanReady:
		return "A plan exists. Continue with the review phase to validate spec/plan alignment."
	case runpkg.StatusExecuting:
		return "Execution is in progress. Continue from the last completed task."
	case runpkg.StatusVerifying:
		return "Verification is in progress. Continue running verification commands."
	case runpkg.StatusBlocked:
		return "The run is blocked. Resolve blockers before continuing."
	case runpkg.StatusAborted:
		return "The run was aborted. Start a new run if needed."
	case runpkg.StatusDone:
		return "The run is complete. No further action needed."
	default:
		return "Resume the workflow from the current state."
	}
}

func (r *Registry) omniArtifactWrite(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, _ := arguments["repo_root"].(string)
	runID, _ := arguments["run_id"].(string)
	filename, _ := arguments["filename"].(string)
	content, _ := arguments["content"].(string)

	if content == "" {
		return ToolCallResult{}, fmt.Errorf("content is required")
	}

	store := artifact.NewStore(repoRoot)
	var writePath string

	switch filename {
	case "spec.md":
		if _, err := schema.ValidateSpec(content); err != nil {
			return ToolCallResult{}, fmt.Errorf("spec validation failed: %s", err)
		}
		if err := store.WriteSpec(runID, content); err != nil {
			return ToolCallResult{}, fmt.Errorf("write spec: %w", err)
		}
		writePath = artifact.SpecPath(repoRoot, runID)
	case "plan.json":
		var planObj map[string]interface{}
		if err := json.Unmarshal([]byte(content), &planObj); err != nil {
			return ToolCallResult{}, fmt.Errorf("plan must be valid JSON: %w", err)
		}
		if _, err := schema.ValidatePlan(planObj); err != nil {
			return ToolCallResult{}, fmt.Errorf("plan validation failed: %s", err)
		}
		if err := store.WritePlan(runID, planObj); err != nil {
			return ToolCallResult{}, fmt.Errorf("write plan: %w", err)
		}
		writePath = artifact.PlanPath(repoRoot, runID)
	case "decisions.md":
		if _, err := schema.ValidateDecisions(content); err != nil {
			return ToolCallResult{}, fmt.Errorf("decisions validation failed: %s", err)
		}
		if err := store.WriteDecisions(runID, content); err != nil {
			return ToolCallResult{}, fmt.Errorf("write decisions: %w", err)
		}
		writePath = artifact.DecisionsPath(repoRoot, runID)
	default:
		artifactPath, err := validateArtifactPath(repoRoot, runID, filename)
		if err != nil {
			return ToolCallResult{}, err
		}
		runDir := filepath.Dir(artifactPath)
		if err := os.MkdirAll(runDir, 0o755); err != nil {
			return ToolCallResult{}, fmt.Errorf("create run directory: %w", err)
		}
		if err := os.WriteFile(artifactPath, []byte(content), 0o644); err != nil {
			return ToolCallResult{}, fmt.Errorf("write artifact: %w", err)
		}
		writePath = artifactPath
	}

	result := map[string]interface{}{
		"status":  "ok",
		"path":    writePath,
		"run_id":  runID,
		"written": len(content),
	}
	payload, err := json.Marshal(result)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("marshal response: %w", err)
	}

	return ToolCallResult{
		Content: []ToolContent{{
			Type: "text",
			Text: string(payload),
		}},
	}, nil
}
