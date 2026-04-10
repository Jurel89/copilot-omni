package mcp

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/copilot-omni/sidecar/internal/artifact"
	"github.com/copilot-omni/sidecar/internal/config"
	"github.com/copilot-omni/sidecar/internal/doctor"
	"github.com/copilot-omni/sidecar/internal/execution"
	"github.com/copilot-omni/sidecar/internal/memory"
	"github.com/copilot-omni/sidecar/internal/merge"
	"github.com/copilot-omni/sidecar/internal/policy"
	"github.com/copilot-omni/sidecar/internal/research"
	"github.com/copilot-omni/sidecar/internal/router"
	runpkg "github.com/copilot-omni/sidecar/internal/run"
	"github.com/copilot-omni/sidecar/internal/schema"
	subtaskpkg "github.com/copilot-omni/sidecar/internal/subtask"
	"github.com/copilot-omni/sidecar/internal/version"
	"github.com/copilot-omni/sidecar/internal/workspace"
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

	registry.register(
		Tool{
			Name:        "omni_guarded_patch",
			Description: "Apply a task-scoped patch only when policy and plan scope allow the file write",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"run_id": map[string]interface{}{
						"type":        "string",
						"description": "Run ID containing the plan",
					},
					"task_id": map[string]interface{}{
						"type":        "string",
						"description": "Task ID whose file_targets define the approved patch scope",
					},
					"file_path": map[string]interface{}{
						"type":        "string",
						"description": "Repository-relative file path to patch",
					},
					"patch": map[string]interface{}{
						"type":        "string",
						"description": "Unified diff patch content for the target file",
					},
					"expected_hash": map[string]interface{}{
						"type":        "string",
						"description": "Optional expected SHA256 hash of the patched file contents",
					},
				},
				Required: []string{"repo_root", "run_id", "task_id", "file_path", "patch"},
			},
		},
		registry.omniGuardedPatch,
	)

	registry.register(
		Tool{
			Name:        "omni_verification_run",
			Description: "Execute verification commands, store stdout and stderr artifacts, and write a verification report",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"run_id": map[string]interface{}{
						"type":        "string",
						"description": "Run ID for verification artifacts",
					},
					"task_id": map[string]interface{}{
						"type":        "string",
						"description": "Optional task ID associated with task-mode verification",
					},
					"commands": map[string]interface{}{
						"type":        "array",
						"description": "Shell commands to execute in order",
					},
					"mode": map[string]interface{}{
						"type":        "string",
						"description": "Verification mode: task or run",
					},
				},
				Required: []string{"repo_root", "run_id", "commands", "mode"},
			},
		},
		registry.omniVerificationRun,
	)

	registry.register(
		Tool{
			Name:        "omni_repo_map",
			Description: "Walk the repository and return a bounded file map without reading file contents",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"include": map[string]interface{}{
						"type":        "array",
						"description": "Optional include glob patterns",
					},
					"exclude": map[string]interface{}{
						"type":        "array",
						"description": "Optional exclude glob patterns",
					},
					"max_files": map[string]interface{}{
						"type":        "number",
						"description": "Maximum number of files to return",
					},
					"task_id": map[string]interface{}{
						"type":        "string",
						"description": "Optional task ID to limit results to the task file_targets scope",
					},
				},
				Required: []string{"repo_root"},
			},
		},
		registry.omniRepoMap,
	)

	registry.register(
		Tool{
			Name:        "omni_policy_check",
			Description: "Evaluate a command, path, artifact mutation, or prompt against the active policy profile",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"run_id": map[string]interface{}{
						"type":        "string",
						"description": "Optional run ID used to resolve task scope",
					},
					"task_id": map[string]interface{}{
						"type":        "string",
						"description": "Optional task ID used to resolve plan file_targets",
					},
					"operation": map[string]interface{}{
						"type":        "string",
						"description": "Operation type: command, path, artifact, or prompt",
					},
					"value": map[string]interface{}{
						"type":        "string",
						"description": "Value to evaluate against policy",
					},
					"metadata": map[string]interface{}{
						"type":        "object",
						"description": "Optional metadata passed to the policy decision",
					},
				},
				Required: []string{"repo_root", "operation", "value"},
			},
		},
		registry.omniPolicyCheck,
	)

	registry.register(
		Tool{
			Name:        "omni_memory_search",
			Description: "Search local memory for past decisions, specs, plans, notes, and verification results",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"query": map[string]interface{}{
						"type":        "string",
						"description": "Search terms for lexical matching",
					},
					"type": map[string]interface{}{
						"type":        "string",
						"description": "Filter by record type: decision, spec, plan, summary, note, verification",
					},
					"scope": map[string]interface{}{
						"type":        "string",
						"description": "Filter by scope: project or global",
					},
					"run_id": map[string]interface{}{
						"type":        "string",
						"description": "Filter to a specific run ID",
					},
					"tags": map[string]interface{}{
						"type":        "array",
						"description": "Filter by tags",
					},
					"trust_level": map[string]interface{}{
						"type":        "string",
						"description": "Filter by trust level: high, medium, low",
					},
					"limit": map[string]interface{}{
						"type":        "number",
						"description": "Maximum results to return (default 10)",
					},
				},
				Required: []string{"repo_root"},
			},
		},
		registry.omniMemorySearch,
	)

	registry.register(
		Tool{
			Name:        "omni_memory_capture",
			Description: "Store a user-authored or system-generated note in local memory",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"title": map[string]interface{}{
						"type":        "string",
						"description": "Short title for the memory entry",
					},
					"content": map[string]interface{}{
						"type":        "string",
						"description": "The memory content to store",
					},
					"type": map[string]interface{}{
						"type":        "string",
						"description": "Record type (default: note)",
					},
					"source": map[string]interface{}{
						"type":        "string",
						"description": "Source: user, system, or artifact (default: user)",
					},
					"tags": map[string]interface{}{
						"type":        "array",
						"description": "Tags for categorization",
					},
					"sensitivity": map[string]interface{}{
						"type":        "string",
						"description": "Sensitivity level: normal, sensitive, secret (default: normal)",
					},
				},
				Required: []string{"repo_root", "title", "content"},
			},
		},
		registry.omniMemoryCapture,
	)

	registry.register(
		Tool{
			Name:        "omni_memory_ingest",
			Description: "Ingest run artifacts (spec, plan, decisions, verification) into local memory",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"run_id": map[string]interface{}{
						"type":        "string",
						"description": "Run ID whose artifacts to ingest",
					},
				},
				Required: []string{"repo_root", "run_id"},
			},
		},
		registry.omniMemoryIngest,
	)

	registry.register(
		Tool{
			Name:        "omni_memory_wipe",
			Description: "Wipe all memory records for a given scope (project or global)",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"scope": map[string]interface{}{
						"type":        "string",
						"description": "Scope to wipe: project or global",
					},
				},
				Required: []string{"repo_root", "scope"},
			},
		},
		registry.omniMemoryWipe,
	)

	registry.register(
		Tool{
			Name:        "omni_memory_export",
			Description: "Export all memory records as JSON for compliance or backup",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"scope": map[string]interface{}{
						"type":        "string",
						"description": "Scope to export: project or global (default: project)",
					},
				},
				Required: []string{"repo_root"},
			},
		},
		registry.omniMemoryExport,
	)

	registry.register(
		Tool{
			Name:        "omni_memory_prune",
			Description: "Prune retained memory records by maximum age and/or record count",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"max_age_days": map[string]interface{}{
						"type":        "number",
						"description": "Optional maximum age in days for retained records",
					},
					"max_records": map[string]interface{}{
						"type":        "number",
						"description": "Optional maximum number of retained records for the selected scope",
					},
					"scope": map[string]interface{}{
						"type":        "string",
						"description": "Scope to prune by count: project or global (default: project)",
					},
				},
				Required: []string{"repo_root"},
			},
		},
		registry.omniMemoryPrune,
	)

	registry.register(
		Tool{
			Name:        "omni_research",
			Description: "Generate a structured research report combining web findings, repository evidence, and memory",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"run_id": map[string]interface{}{
						"type":        "string",
						"description": "Run ID for the research report artifact",
					},
					"query": map[string]interface{}{
						"type":        "string",
						"description": "Research query to investigate",
					},
					"web_results": map[string]interface{}{
						"type":        "string",
						"description": "Optional web research results to include",
					},
					"repo_evidence": map[string]interface{}{
						"type":        "string",
						"description": "Optional repository exploration evidence to include",
					},
					"memory_results": map[string]interface{}{
						"type":        "string",
						"description": "Optional memory search results to include",
					},
				},
				Required: []string{"repo_root", "run_id", "query"},
			},
		},
		registry.omniResearch,
	)

	registry.register(
		Tool{
			Name:        "omni_subtask_create",
			Description: "Create a subtask manifest for bounded parallel work with explicit scopes and isolation requirements",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"run_id": map[string]interface{}{
						"type":        "string",
						"description": "Run ID for the subtask manifest artifact",
					},
					"parent_task": map[string]interface{}{
						"type":        "string",
						"description": "Parent plan task ID that this manifest decomposes",
					},
					"manifest": map[string]interface{}{
						"type":        "object",
						"description": "Subtask manifest object with subtasks array",
					},
				},
				Required: []string{"repo_root", "run_id", "parent_task", "manifest"},
			},
		},
		registry.omniSubtaskCreate,
	)

	registry.register(
		Tool{
			Name:        "omni_subtask_status",
			Description: "Read or update subtask status within a manifest, and list ready subtasks for parallel execution",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"run_id": map[string]interface{}{
						"type":        "string",
						"description": "Run ID containing the subtask manifest",
					},
					"subtask_id": map[string]interface{}{
						"type":        "string",
						"description": "Optional subtask ID to update status for",
					},
					"status": map[string]interface{}{
						"type":        "string",
						"description": "New status: running, completed, failed, or discarded",
					},
					"list_ready": map[string]interface{}{
						"type":        "boolean",
						"description": "If true, list subtasks ready for execution (default: false)",
					},
				},
				Required: []string{"repo_root", "run_id"},
			},
		},
		registry.omniSubtaskStatus,
	)

	registry.register(
		Tool{
			Name:        "omni_workspace_create",
			Description: "Create an isolated workspace for a write-capable subtask using git worktrees or temp directories",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"subtask_id": map[string]interface{}{
						"type":        "string",
						"description": "Subtask ID to create workspace for",
					},
					"is_write": map[string]interface{}{
						"type":        "boolean",
						"description": "Whether the workspace needs write access (default: false)",
					},
				},
				Required: []string{"repo_root", "subtask_id"},
			},
		},
		registry.omniWorkspaceCreate,
	)

	registry.register(
		Tool{
			Name:        "omni_workspace_remove",
			Description: "Remove an isolated workspace after subtask completion or failure",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"workspace_path": map[string]interface{}{
						"type":        "string",
						"description": "Path to the workspace to remove",
					},
					"subtask_id": map[string]interface{}{
						"type":        "string",
						"description": "Subtask ID the workspace belongs to",
					},
					"isolation": map[string]interface{}{
						"type":        "string",
						"description": "Isolation type: worktree or tempdir",
					},
					"branch_name": map[string]interface{}{
						"type":        "string",
						"description": "Branch name for worktree cleanup",
					},
				},
				Required: []string{"repo_root", "subtask_id"},
			},
		},
		registry.omniWorkspaceRemove,
	)

	registry.register(
		Tool{
			Name:        "omni_merge",
			Description: "Merge subtask outputs through a review pipeline with accept/reject/conflict decisions",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"repo_root": map[string]interface{}{
						"type":        "string",
						"description": "Repository root path",
					},
					"run_id": map[string]interface{}{
						"type":        "string",
						"description": "Run ID containing the subtask manifest",
					},
					"decisions": map[string]interface{}{
						"type":        "array",
						"description": "Array of merge decisions with subtask_id, action, and optional reason",
					},
				},
				Required: []string{"repo_root", "run_id", "decisions"},
			},
		},
		registry.omniMerge,
	)

	registry.register(
		Tool{
			Name:        "omni_intent_route",
			Description: "Classify user intent and route to the minimal required capability (skill, agent, sidecar tool, or built-in)",
			InputSchema: InputSchema{
				Type: "object",
				Properties: map[string]interface{}{
					"prompt": map[string]interface{}{
						"type":        "string",
						"description": "User prompt to classify and route",
					},
				},
				Required: []string{"prompt"},
			},
		},
		registry.omniIntentRoute,
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

	memStore, _, memErr := r.openMemoryStore(repoRoot)
	if memErr == nil && memStore != nil {
		bundle, err := memory.HydrateContext(memStore, repoRoot, runID)
		if err == nil && bundle != nil {
			response["memory_context"] = bundle
		}
		memStore.Close()
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

func (r *Registry) omniGuardedPatch(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	runID, err := requiredStringArg(arguments, "run_id")
	if err != nil {
		return ToolCallResult{}, err
	}
	taskID, err := requiredStringArg(arguments, "task_id")
	if err != nil {
		return ToolCallResult{}, err
	}
	filePath, err := requiredStringArg(arguments, "file_path")
	if err != nil {
		return ToolCallResult{}, err
	}
	patchText, err := requiredStringArg(arguments, "patch")
	if err != nil {
		return ToolCallResult{}, err
	}
	expectedHash, err := optionalStringArg(arguments, "expected_hash")
	if err != nil {
		return ToolCallResult{}, err
	}

	engine, taskInfo, normalizedPath, policyResult, err := r.evaluateTaskPathPolicy(repoRoot, runID, taskID, filePath, policy.OpPathWrite)
	if err != nil {
		return ToolCallResult{}, err
	}
	scopeMatch := policy.IsWithinScope(normalizedPath, taskInfo.FileTargets)

	response := map[string]interface{}{
		"applied":     false,
		"file_path":   normalizedPath,
		"before_hash": sha256Hex(nil),
		"after_hash":  sha256Hex(nil),
		"policy":      policyResult,
		"scope_match": scopeMatch,
	}

	if !policyResult.Allowed || engine == nil {
		return jsonToolResult(response)
	}

	targetPath := filepath.Join(repoRoot, filepath.FromSlash(normalizedPath))
	beforeBytes, err := os.ReadFile(targetPath)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return ToolCallResult{}, fmt.Errorf("read patch target %s: %w", normalizedPath, err)
	}
	response["before_hash"] = sha256Hex(beforeBytes)

	afterBytes, err := applyUnifiedPatch(beforeBytes, patchText)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("apply patch to %s: %w", normalizedPath, err)
	}
	response["after_hash"] = sha256Hex(afterBytes)

	if expectedHash != "" && !strings.EqualFold(strings.TrimSpace(expectedHash), response["after_hash"].(string)) {
		return jsonToolResult(response)
	}

	if err := artifact.WriteFile(targetPath, afterBytes); err != nil {
		return ToolCallResult{}, fmt.Errorf("write patch target %s: %w", normalizedPath, err)
	}

	response["applied"] = true
	return jsonToolResult(response)
}

func (r *Registry) omniVerificationRun(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	runID, err := requiredStringArg(arguments, "run_id")
	if err != nil {
		return ToolCallResult{}, err
	}
	mode, err := requiredStringArg(arguments, "mode")
	if err != nil {
		return ToolCallResult{}, err
	}
	mode = strings.ToLower(strings.TrimSpace(mode))
	if mode != "task" && mode != "run" {
		return ToolCallResult{}, fmt.Errorf("mode must be \"task\" or \"run\"")
	}
	taskID, err := optionalStringArg(arguments, "task_id")
	if err != nil {
		return ToolCallResult{}, err
	}

	commands, err := stringArrayArg(arguments, "commands")
	if err != nil {
		return ToolCallResult{}, err
	}
	if len(commands) == 0 {
		return ToolCallResult{}, fmt.Errorf("commands must contain at least one command")
	}

	var taskInfo *execution.TaskInfo
	if mode == "task" {
		if taskID == "" {
			return ToolCallResult{}, fmt.Errorf("task_id is required in task mode")
		}
		taskInfo, err = r.loadTaskInfo(repoRoot, runID, taskID)
		if err != nil {
			return ToolCallResult{}, err
		}
		commands = []string{taskInfo.VerificationCmd}
	}

	resolvedConfig, err := resolveConfig(r.configResolver, repoRoot)
	if err != nil {
		return ToolCallResult{}, err
	}
	policyEngine := policy.NewEngine(&resolvedConfig.Policy)

	verificationDir := filepath.Join(repoRoot, ".omni", "runs", runID, "verification")
	reportPath := filepath.Join(repoRoot, ".omni", "runs", runID, "verification-report.json")
	commandResults := make([]execution.VerificationResult, 0, len(commands))
	journal := execution.NewExecutionJournal()

	for index, command := range commands {
		command = strings.TrimSpace(command)
		if command == "" {
			return ToolCallResult{}, fmt.Errorf("commands[%d] must be a non-empty string", index)
		}

		policyDecision := policy.Decision{
			Operation: policy.OpCommand,
			Value:     command,
			RunID:     runID,
			TaskID:    taskID,
			Metadata: map[string]string{
				"repo_root":        repoRoot,
				"allowed_commands": command,
			},
		}
		if taskInfo != nil {
			policyDecision.FileTargets = append([]string(nil), taskInfo.FileTargets...)
		}
		policyResult := policyEngine.Evaluate(policyDecision)
		if policyResult.Profile == "" {
			policyResult.Profile = resolvedConfig.Profile
		}
		if !policyResult.Allowed {
			report := execution.GenerateVerificationReport(runID, commandResults, mode)
			report.Status = "error"

			reportPayload, marshalErr := json.Marshal(report)
			if marshalErr != nil {
				return ToolCallResult{}, fmt.Errorf("marshal verification report: %w", marshalErr)
			}

			var reportMap map[string]interface{}
			if unmarshalErr := json.Unmarshal(reportPayload, &reportMap); unmarshalErr != nil {
				return ToolCallResult{}, fmt.Errorf("decode verification report payload: %w", unmarshalErr)
			}
			if _, validationErr := schema.ValidateVerificationReport(reportMap); validationErr != nil {
				return ToolCallResult{}, fmt.Errorf("verification report validation failed: %w", validationErr)
			}

			prettyReportPayload, marshalIndentErr := json.MarshalIndent(reportMap, "", "  ")
			if marshalIndentErr != nil {
				return ToolCallResult{}, fmt.Errorf("marshal verification report: %w", marshalIndentErr)
			}
			if writeErr := artifact.WriteFile(reportPath, prettyReportPayload); writeErr != nil {
				return ToolCallResult{}, fmt.Errorf("write verification report: %w", writeErr)
			}

			response := map[string]interface{}{
				"run_id":      report.RunID,
				"timestamp":   report.Timestamp,
				"mode":        report.Mode,
				"status":      report.Status,
				"results":     report.Results,
				"summary":     report.Summary,
				"report_path": reportPath,
				"policy":      policyResult,
			}
			if taskInfo != nil {
				response["task_id"] = taskID
			}
			return jsonToolResult(response)
		}

		stdoutPath := filepath.Join(verificationDir, fmt.Sprintf("command-%02d.stdout.log", index+1))
		stderrPath := filepath.Join(verificationDir, fmt.Sprintf("command-%02d.stderr.log", index+1))
		start := time.Now()

		execCtx, cancel := context.WithTimeout(ctx, 60*time.Second)
		cmd := exec.CommandContext(execCtx, "sh", "-c", command)
		cmd.Dir = repoRoot
		stdoutBytes, stderrBytes, runErr := runCommandCapture(cmd)
		cancel()

		if err := artifact.WriteFile(stdoutPath, stdoutBytes); err != nil {
			return ToolCallResult{}, fmt.Errorf("write stdout artifact for %q: %w", command, err)
		}
		if err := artifact.WriteFile(stderrPath, stderrBytes); err != nil {
			return ToolCallResult{}, fmt.Errorf("write stderr artifact for %q: %w", command, err)
		}

		exitCode := 0
		resultStatus := "pass"
		if runErr != nil {
			exitCode = exitCodeForError(runErr)
			resultStatus = "fail"
		}
		durationMs := time.Since(start).Milliseconds()

		commandResults = append(commandResults, execution.VerificationResult{
			TaskID:     taskID,
			Command:    command,
			ExitCode:   exitCode,
			StdoutPath: stdoutPath,
			StderrPath: stderrPath,
			DurationMs: durationMs,
			Status:     resultStatus,
		})
		journal.Record(execution.JournalEntry{
			RunID:     runID,
			TaskID:    taskID,
			Timestamp: time.Now().UTC(),
			Action:    "verification_command",
			CommandsRun: []execution.CommandRecord{{
				Command:    command,
				ExitCode:   exitCode,
				DurationMs: durationMs,
			}},
			DurationMs: durationMs,
			Error:      strings.TrimSpace(string(stderrBytes)),
		})
	}

	report := execution.GenerateVerificationReport(runID, commandResults, mode)

	reportPayload, err := json.Marshal(report)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("marshal verification report: %w", err)
	}

	var reportMap map[string]interface{}
	if err := json.Unmarshal(reportPayload, &reportMap); err != nil {
		return ToolCallResult{}, fmt.Errorf("decode verification report payload: %w", err)
	}
	if _, err := schema.ValidateVerificationReport(reportMap); err != nil {
		return ToolCallResult{}, fmt.Errorf("verification report validation failed: %w", err)
	}

	prettyReportPayload, err := json.MarshalIndent(reportMap, "", "  ")
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("marshal verification report: %w", err)
	}
	if err := artifact.WriteFile(reportPath, prettyReportPayload); err != nil {
		return ToolCallResult{}, fmt.Errorf("write verification report: %w", err)
	}

	response := map[string]interface{}{
		"run_id":      report.RunID,
		"timestamp":   report.Timestamp,
		"mode":        report.Mode,
		"status":      report.Status,
		"results":     report.Results,
		"summary":     report.Summary,
		"report_path": reportPath,
	}
	if taskInfo != nil && report.Status != "passed" {
		response["rollback"] = execution.RecommendRollback(*taskInfo, journal)
	}

	return jsonToolResult(response)
}

func (r *Registry) omniRepoMap(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	include, err := optionalStringArrayArg(arguments, "include")
	if err != nil {
		return ToolCallResult{}, err
	}
	exclude, err := optionalStringArrayArg(arguments, "exclude")
	if err != nil {
		return ToolCallResult{}, err
	}
	maxFiles := intFromArgument(arguments["max_files"], 500)
	if maxFiles <= 0 {
		maxFiles = 500
	}
	taskID, err := optionalStringArg(arguments, "task_id")
	if err != nil {
		return ToolCallResult{}, err
	}

	fileTargets := []string(nil)
	warnings := make([]string, 0)
	if taskID != "" {
		runID, runIDErr := optionalStringArg(arguments, "run_id")
		if runIDErr != nil {
			return ToolCallResult{}, runIDErr
		}
		if runID == "" {
			warnings = append(warnings, "task_id provided without run_id; task scope was not applied")
		} else {
			taskInfo, loadErr := r.loadTaskInfo(repoRoot, runID, taskID)
			if loadErr != nil {
				return ToolCallResult{}, loadErr
			}
			fileTargets = append(fileTargets, taskInfo.FileTargets...)
		}
	}

	files := make([]map[string]interface{}, 0, maxFiles)
	walkErr := filepath.WalkDir(repoRoot, func(currentPath string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if currentPath == repoRoot {
			return nil
		}

		relPath, err := filepath.Rel(repoRoot, currentPath)
		if err != nil {
			return err
		}
		relPath = filepath.ToSlash(filepath.Clean(relPath))

		if entry.IsDir() {
			name := entry.Name()
			if name == ".git" || name == ".omni" || name == "node_modules" || name == "vendor" {
				return filepath.SkipDir
			}
			return nil
		}

		if len(fileTargets) > 0 && !policy.IsWithinScope(relPath, fileTargets) {
			return nil
		}
		if !matchesGlobFilters(relPath, include, exclude) {
			return nil
		}

		info, err := entry.Info()
		if err != nil {
			return err
		}

		language, role := detectRepoMapMetadata(relPath)
		files = append(files, map[string]interface{}{
			"path":       relPath,
			"language":   language,
			"size_bytes": info.Size(),
			"role":       role,
		})

		if len(files) >= maxFiles {
			warnings = append(warnings, fmt.Sprintf("file list truncated at max_files=%d", maxFiles))
			return errRepoMapLimitReached
		}

		return nil
	})
	if walkErr != nil && !errors.Is(walkErr, errRepoMapLimitReached) {
		return ToolCallResult{}, fmt.Errorf("walk repository: %w", walkErr)
	}

	response := map[string]interface{}{
		"files":    files,
		"warnings": warnings,
	}
	return jsonToolResult(response)
}

func (r *Registry) omniPolicyCheck(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	operation, err := requiredStringArg(arguments, "operation")
	if err != nil {
		return ToolCallResult{}, err
	}
	value, err := requiredStringArg(arguments, "value")
	if err != nil {
		return ToolCallResult{}, err
	}
	runID, err := optionalStringArg(arguments, "run_id")
	if err != nil {
		return ToolCallResult{}, err
	}
	taskID, err := optionalStringArg(arguments, "task_id")
	if err != nil {
		return ToolCallResult{}, err
	}
	metadata, err := metadataArg(arguments["metadata"])
	if err != nil {
		return ToolCallResult{}, err
	}

	resolvedConfig, err := resolveConfig(r.configResolver, repoRoot)
	if err != nil {
		return ToolCallResult{}, err
	}
	engine := policy.NewEngine(&resolvedConfig.Policy)

	if strings.EqualFold(strings.TrimSpace(operation), "prompt") {
		scan := policy.ScanForInjection(value)
		result := policy.PolicyResult{
			Allowed:    scan.Clean,
			ReasonCode: policy.ReasonAllowed,
			Profile:    resolvedConfig.Profile,
		}
		if !scan.Clean {
			result.Allowed = false
			result.ReasonCode = policy.ReasonInjectionDetected
			result.Message = fmt.Sprintf("prompt content matched injection patterns (%s)", strings.Join(scan.Detections, ", "))
			result.MatchedRule = strings.Join(scan.Detections, ", ")
		}
		return jsonToolResult(result)
	}

	if metadata == nil {
		metadata = make(map[string]string)
	}
	metadata["repo_root"] = repoRoot

	decision := policy.Decision{
		Value:    value,
		RunID:    runID,
		TaskID:   taskID,
		Metadata: metadata,
	}
	if runID != "" && taskID != "" {
		taskInfo, loadErr := r.loadTaskInfo(repoRoot, runID, taskID)
		if loadErr != nil {
			return ToolCallResult{}, loadErr
		}
		decision.FileTargets = append([]string(nil), taskInfo.FileTargets...)
	}

	switch strings.ToLower(strings.TrimSpace(operation)) {
	case "command":
		decision.Operation = policy.OpCommand
	case "path":
		decision.Operation = policy.OpPathWrite
	case "artifact":
		decision.Operation = policy.OpArtifactMutation
	default:
		return ToolCallResult{}, fmt.Errorf("operation must be one of: command, path, artifact, prompt")
	}

	result := engine.Evaluate(decision)
	if result.Profile == "" {
		result.Profile = resolvedConfig.Profile
	}
	return jsonToolResult(result)
}

func (r *Registry) openMemoryStore(repoRoot string) (*memory.Store, *config.Config, error) {
	resolvedConfig, err := resolveConfig(r.configResolver, repoRoot)
	if err != nil {
		return nil, nil, err
	}

	if !resolvedConfig.Memory.Enabled {
		return nil, nil, fmt.Errorf("memory is disabled in configuration")
	}

	dbPath := memory.DBPath(repoRoot, resolvedConfig.Memory.DBPath)
	store, err := memory.NewStore(dbPath)
	if err != nil {
		return nil, nil, fmt.Errorf("open memory store: %w", err)
	}

	return store, resolvedConfig, nil
}

func (r *Registry) omniMemorySearch(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}

	store, _, err := r.openMemoryStore(repoRoot)
	if err != nil {
		return ToolCallResult{}, err
	}
	defer store.Close()

	query := memory.SearchQuery{
		Query:      stringVal(arguments, "query"),
		Type:       stringVal(arguments, "type"),
		Scope:      stringVal(arguments, "scope"),
		RunID:      stringVal(arguments, "run_id"),
		TrustLevel: stringVal(arguments, "trust_level"),
	}

	if tags, err := optionalStringArrayArg(arguments, "tags"); err == nil && tags != nil {
		query.Tags = tags
	}

	if limit, ok := arguments["limit"].(float64); ok && limit > 0 {
		query.Limit = int(limit)
	}

	result, err := store.Search(query)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("memory search failed: %w", err)
	}

	return jsonToolResult(result)
}

func (r *Registry) omniMemoryCapture(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	title, err := requiredStringArg(arguments, "title")
	if err != nil {
		return ToolCallResult{}, err
	}
	content, err := requiredStringArg(arguments, "content")
	if err != nil {
		return ToolCallResult{}, err
	}

	store, _, err := r.openMemoryStore(repoRoot)
	if err != nil {
		return ToolCallResult{}, err
	}
	defer store.Close()

	cleanedContent, wasRedacted := memory.RedactSecrets(content)

	sensitivity := stringVal(arguments, "sensitivity")
	if sensitivity == "" {
		sensitivity = "normal"
	}
	if wasRedacted && sensitivity == "normal" {
		sensitivity = "sensitive"
	}

	record := &memory.MemoryRecord{
		Type:        stringVal(arguments, "type"),
		Source:      stringVal(arguments, "source"),
		Scope:       memory.ScopeProject,
		Title:       title,
		Content:     cleanedContent,
		Sensitivity: sensitivity,
	}

	if record.Type == "" {
		record.Type = memory.TypeNote
	}
	if record.Source == "" {
		record.Source = memory.SourceUser
	}

	if tags, err := optionalStringArrayArg(arguments, "tags"); err == nil && tags != nil {
		record.Tags = tags
	}

	if err := store.Create(record); err != nil {
		return ToolCallResult{}, fmt.Errorf("memory capture failed: %w", err)
	}

	return jsonToolResult(map[string]interface{}{
		"status":      "ok",
		"id":          record.ID,
		"type":        record.Type,
		"sensitivity": record.Sensitivity,
		"redacted":    wasRedacted,
	})
}

func (r *Registry) omniMemoryIngest(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	runID, err := requiredStringArg(arguments, "run_id")
	if err != nil {
		return ToolCallResult{}, err
	}

	store, resolvedConfig, err := r.openMemoryStore(repoRoot)
	if err != nil {
		return ToolCallResult{}, err
	}
	defer store.Close()

	if err := memory.IngestRunArtifacts(store, repoRoot, runID); err != nil {
		return ToolCallResult{}, fmt.Errorf("memory ingest failed: %w", err)
	}

	// Verification report is optional (returns nil if missing), but
	// parse/store failures are real errors that should be surfaced.
	if err := memory.IngestVerificationReport(store, repoRoot, runID); err != nil {
		return ToolCallResult{}, fmt.Errorf("verification report ingest failed: %w", err)
	}

	if resolvedConfig != nil && resolvedConfig.Memory.AutoIngest && resolvedConfig.Memory.RetentionDays > 0 {
		maxAge := time.Duration(resolvedConfig.Memory.RetentionDays) * 24 * time.Hour
		_, _ = memory.PruneByAge(store, maxAge)
	}

	count, _ := store.RecordCount(memory.ScopeProject)

	return jsonToolResult(map[string]interface{}{
		"status":        "ok",
		"run_id":        runID,
		"total_records": count,
	})
}

func (r *Registry) omniMemoryWipe(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	scope, err := requiredStringArg(arguments, "scope")
	if err != nil {
		return ToolCallResult{}, err
	}

	store, _, err := r.openMemoryStore(repoRoot)
	if err != nil {
		return ToolCallResult{}, err
	}
	defer store.Close()

	if err := memory.WipeScope(store, scope); err != nil {
		return ToolCallResult{}, fmt.Errorf("memory wipe failed: %w", err)
	}

	return jsonToolResult(map[string]interface{}{
		"status": "ok",
		"scope":  scope,
	})
}

func (r *Registry) omniMemoryExport(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	scope := stringVal(arguments, "scope")
	if scope == "" {
		scope = memory.ScopeProject
	}

	store, _, err := r.openMemoryStore(repoRoot)
	if err != nil {
		return ToolCallResult{}, err
	}
	defer store.Close()

	data, err := memory.ExportRecords(store, scope)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("memory export failed: %w", err)
	}

	return ToolCallResult{
		Content: []ToolContent{{
			Type: "text",
			Text: string(data),
		}},
	}, nil
}

func (r *Registry) omniMemoryPrune(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}

	scope := stringVal(arguments, "scope")
	if scope == "" {
		scope = memory.ScopeProject
	}

	maxAgeDays := intFromArgument(arguments["max_age_days"], 0)
	maxRecords := intFromArgument(arguments["max_records"], 0)
	if maxAgeDays <= 0 && maxRecords <= 0 {
		return ToolCallResult{}, fmt.Errorf("at least one of max_age_days or max_records must be provided")
	}

	store, _, err := r.openMemoryStore(repoRoot)
	if err != nil {
		return ToolCallResult{}, err
	}
	defer store.Close()

	prunedByAge := 0
	if maxAgeDays > 0 {
		prunedByAge, err = memory.PruneByAge(store, time.Duration(maxAgeDays)*24*time.Hour)
		if err != nil {
			return ToolCallResult{}, fmt.Errorf("memory prune by age failed: %w", err)
		}
	}

	prunedByCount := 0
	if maxRecords > 0 {
		prunedByCount, err = memory.PruneByCount(store, maxRecords, scope)
		if err != nil {
			return ToolCallResult{}, fmt.Errorf("memory prune by count failed: %w", err)
		}
	}

	totalPruned := prunedByAge + prunedByCount
	remaining, err := store.RecordCount(scope)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("memory prune count failed: %w", err)
	}

	return jsonToolResult(map[string]interface{}{
		"status":          "ok",
		"scope":           scope,
		"pruned_by_age":   prunedByAge,
		"pruned_by_count": prunedByCount,
		"pruned_total":    totalPruned,
		"remaining":       remaining,
	})
}

func (r *Registry) omniResearch(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	runID, err := requiredStringArg(arguments, "run_id")
	if err != nil {
		return ToolCallResult{}, err
	}
	query, err := requiredStringArg(arguments, "query")
	if err != nil {
		return ToolCallResult{}, err
	}

	opts := research.GenerateOptions{
		RunID:         runID,
		Query:         query,
		RepoRoot:      repoRoot,
		WebResults:    stringVal(arguments, "web_results"),
		RepoEvidence:  stringVal(arguments, "repo_evidence"),
		MemoryResults: stringVal(arguments, "memory_results"),
	}

	if strings.TrimSpace(opts.MemoryResults) == "" {
		memStore, _, memErr := r.openMemoryStore(repoRoot)
		if memErr == nil && memStore != nil {
			searchResult, searchErr := memStore.Search(memory.SearchQuery{
				Query: query,
				Limit: 5,
			})
			if searchErr == nil && searchResult != nil && searchResult.Total > 0 {
				var sb strings.Builder
				for _, rec := range searchResult.Records {
					sb.WriteString(rec.Record.Title)
					sb.WriteString(": ")
					sb.WriteString(rec.Record.Content)
					sb.WriteString("\n")
				}
				opts.MemoryResults = sb.String()
			}
			memStore.Close()
		}
	}

	report, genErr := research.Generate(opts)
	if genErr != nil {
		return ToolCallResult{}, fmt.Errorf("generate research report: %w", genErr)
	}

	reportPath, writeErr := research.WriteReport(repoRoot, runID, report)
	if writeErr != nil {
		return ToolCallResult{}, fmt.Errorf("write research report: %w", writeErr)
	}

	reportPayload, marshalErr := json.Marshal(report)
	if marshalErr != nil {
		return ToolCallResult{}, fmt.Errorf("marshal research report: %w", marshalErr)
	}

	var reportMap map[string]interface{}
	if json.Unmarshal(reportPayload, &reportMap) != nil {
		return ToolCallResult{}, fmt.Errorf("normalize research report")
	}

	warnings, validateErr := schema.ValidateResearchReport(reportMap)
	if validateErr != nil {
		return ToolCallResult{}, fmt.Errorf("research report validation failed: %w", validateErr)
	}

	response := map[string]interface{}{
		"run_id":      report.RunID,
		"query":       report.Query,
		"summary":     report.Summary,
		"findings":    len(report.Findings),
		"provenance":  len(report.Provenance),
		"report_path": reportPath,
	}
	if len(warnings) > 0 {
		response["warnings"] = warnings
	}

	return jsonToolResult(response)
}

func (r *Registry) omniSubtaskCreate(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	runID, err := requiredStringArg(arguments, "run_id")
	if err != nil {
		return ToolCallResult{}, err
	}
	parentTask, err := requiredStringArg(arguments, "parent_task")
	if err != nil {
		return ToolCallResult{}, err
	}

	rawManifest, ok := arguments["manifest"].(map[string]interface{})
	if !ok || len(rawManifest) == 0 {
		return ToolCallResult{}, fmt.Errorf("manifest must be a non-empty object")
	}

	warnings, validateErr := schema.ValidateSubtaskManifest(rawManifest)
	if validateErr != nil {
		return ToolCallResult{}, fmt.Errorf("subtask manifest validation failed: %w", validateErr)
	}

	manifest := subtaskpkg.NewManifest(runID, parentTask)

	rawSubtasks, ok := rawManifest["subtasks"].([]interface{})
	if !ok {
		return ToolCallResult{}, fmt.Errorf("manifest.subtasks must be an array")
	}

	for _, raw := range rawSubtasks {
		subMap, ok := raw.(map[string]interface{})
		if !ok {
			continue
		}
		sub := subtaskpkg.Subtask{
			ID:              stringVal(subMap, "id"),
			Title:           stringVal(subMap, "title"),
			Description:     stringVal(subMap, "description"),
			Mode:            stringVal(subMap, "mode"),
			VerificationCmd: stringVal(subMap, "verification_cmd"),
			OutputContract:  stringVal(subMap, "output_contract"),
		}
		if deps, err := optionalStringArrayArg(subMap, "dependencies"); err == nil && deps != nil {
			sub.Dependencies = deps
		}
		if targets, err := optionalStringArrayArg(subMap, "file_targets"); err == nil && targets != nil {
			sub.FileTargets = targets
		}
		if addErr := manifest.AddSubtask(sub); addErr != nil {
			return ToolCallResult{}, fmt.Errorf("add subtask: %w", addErr)
		}
	}

	path, writeErr := subtaskpkg.WriteManifest(repoRoot, runID, manifest)
	if writeErr != nil {
		return ToolCallResult{}, fmt.Errorf("write subtask manifest: %w", writeErr)
	}

	response := map[string]interface{}{
		"status":        "ok",
		"run_id":        runID,
		"parent_task":   parentTask,
		"subtask_count": len(manifest.Subtasks),
		"path":          path,
	}
	if len(warnings) > 0 {
		response["warnings"] = warnings
	}

	return jsonToolResult(response)
}

func (r *Registry) omniSubtaskStatus(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	runID, err := requiredStringArg(arguments, "run_id")
	if err != nil {
		return ToolCallResult{}, err
	}

	manifest, readErr := subtaskpkg.ReadManifest(repoRoot, runID)
	if readErr != nil {
		return ToolCallResult{}, fmt.Errorf("read subtask manifest: %w", readErr)
	}

	subtaskID := stringVal(arguments, "subtask_id")
	newStatus := stringVal(arguments, "status")
	listReady, _ := arguments["list_ready"].(bool)

	if subtaskID != "" && newStatus != "" {
		if updateErr := subtaskpkg.UpdateSubtaskStatus(repoRoot, runID, subtaskID, newStatus); updateErr != nil {
			return ToolCallResult{}, fmt.Errorf("update subtask status: %w", updateErr)
		}
		manifest, _ = subtaskpkg.ReadManifest(repoRoot, runID)
	}

	response := map[string]interface{}{
		"run_id":         runID,
		"parent_task":    manifest.ParentTask,
		"total_subtasks": len(manifest.Subtasks),
		"subtasks":       manifest.Subtasks,
		"all_completed":  manifest.AllCompleted(),
	}

	if listReady {
		ready := manifest.ReadySubtasks()
		readyIDs := make([]string, 0, len(ready))
		for _, s := range ready {
			readyIDs = append(readyIDs, s.ID)
		}
		response["ready_subtasks"] = readyIDs
	}

	return jsonToolResult(response)
}

func (r *Registry) omniWorkspaceCreate(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	subtaskID, err := requiredStringArg(arguments, "subtask_id")
	if err != nil {
		return ToolCallResult{}, err
	}

	isWrite := false
	if raw, ok := arguments["is_write"].(bool); ok {
		isWrite = raw
	}

	mgr := workspace.NewManager(repoRoot)
	ws, createErr := mgr.CreateWorkspace(subtaskID, isWrite)
	if createErr != nil {
		return ToolCallResult{}, fmt.Errorf("create workspace: %w", createErr)
	}

	return jsonToolResult(ws)
}

func (r *Registry) omniWorkspaceRemove(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	subtaskID, err := requiredStringArg(arguments, "subtask_id")
	if err != nil {
		return ToolCallResult{}, err
	}

	wsPath := stringVal(arguments, "workspace_path")
	isolation := stringVal(arguments, "isolation")
	branchName := stringVal(arguments, "branch_name")

	ws := &workspace.Workspace{
		Path:        wsPath,
		Isolation:   workspace.IsolationType(isolation),
		SubtaskID:   subtaskID,
		BranchName:  branchName,
		IsWriteable: isolation == string(workspace.IsolationWorktree),
	}

	mgr := workspace.NewManager(repoRoot)
	if removeErr := mgr.RemoveWorkspace(ws); removeErr != nil {
		return ToolCallResult{}, fmt.Errorf("remove workspace: %w", removeErr)
	}

	return jsonToolResult(map[string]interface{}{
		"status":     "ok",
		"subtask_id": subtaskID,
	})
}

func (r *Registry) omniMerge(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	repoRoot, err := requiredStringArg(arguments, "repo_root")
	if err != nil {
		return ToolCallResult{}, err
	}
	runID, err := requiredStringArg(arguments, "run_id")
	if err != nil {
		return ToolCallResult{}, err
	}

	rawDecisions, ok := arguments["decisions"].([]interface{})
	if !ok || len(rawDecisions) == 0 {
		return ToolCallResult{}, fmt.Errorf("decisions must be a non-empty array")
	}

	decisions := make([]merge.Decision, 0, len(rawDecisions))
	for _, raw := range rawDecisions {
		dMap, ok := raw.(map[string]interface{})
		if !ok {
			return ToolCallResult{}, fmt.Errorf("each decision must be an object")
		}
		decisions = append(decisions, merge.Decision{
			SubtaskID: stringVal(dMap, "subtask_id"),
			Action:    stringVal(dMap, "action"),
			Reason:    stringVal(dMap, "reason"),
			Reviewer:  stringVal(dMap, "reviewer"),
		})
	}

	if validateErr := merge.ValidateMergeDecisions(decisions); validateErr != nil {
		return ToolCallResult{}, fmt.Errorf("merge validation: %w", validateErr)
	}

	coord := merge.NewCoordinator(repoRoot)
	result, mergeErr := coord.Merge(runID, decisions)
	if mergeErr != nil {
		return ToolCallResult{}, fmt.Errorf("merge subtasks: %w", mergeErr)
	}

	return jsonToolResult(result)
}

func (r *Registry) omniIntentRoute(ctx context.Context, arguments map[string]interface{}) (ToolCallResult, error) {
	select {
	case <-ctx.Done():
		return ToolCallResult{}, ctx.Err()
	default:
	}

	prompt, err := requiredStringArg(arguments, "prompt")
	if err != nil {
		return ToolCallResult{}, err
	}

	rt := router.NewRouter()
	intent := router.ClassifyIntent(prompt)
	route := rt.Route(intent)

	return jsonToolResult(map[string]interface{}{
		"intent": string(intent),
		"route":  route,
	})
}

func stringVal(arguments map[string]interface{}, key string) string {
	val, _ := arguments[key].(string)
	return strings.TrimSpace(val)
}

var errRepoMapLimitReached = errors.New("repo_map_limit_reached")

var globTokenPattern = regexp.MustCompile(`(\*\*|\*|\?|[^*?]+)`)

func jsonToolResult(payload interface{}) (ToolCallResult, error) {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("marshal tool response: %w", err)
	}

	return ToolCallResult{
		Content: []ToolContent{{
			Type: "text",
			Text: string(encoded),
		}},
	}, nil
}

func requiredStringArg(arguments map[string]interface{}, key string) (string, error) {
	value, ok := arguments[key].(string)
	if !ok || strings.TrimSpace(value) == "" {
		return "", fmt.Errorf("%s must be a non-empty string", key)
	}
	return strings.TrimSpace(value), nil
}

func optionalStringArg(arguments map[string]interface{}, key string) (string, error) {
	raw, ok := arguments[key]
	if !ok || raw == nil {
		return "", nil
	}
	value, ok := raw.(string)
	if !ok {
		return "", fmt.Errorf("%s must be a string when provided", key)
	}
	return strings.TrimSpace(value), nil
}

func stringArrayArg(arguments map[string]interface{}, key string) ([]string, error) {
	values, err := optionalStringArrayArg(arguments, key)
	if err != nil {
		return nil, err
	}
	if values == nil {
		return nil, fmt.Errorf("%s must be an array of strings", key)
	}
	return values, nil
}

func optionalStringArrayArg(arguments map[string]interface{}, key string) ([]string, error) {
	raw, ok := arguments[key]
	if !ok || raw == nil {
		return nil, nil
	}
	items, ok := raw.([]interface{})
	if !ok {
		return nil, fmt.Errorf("%s must be an array of strings", key)
	}
	values := make([]string, 0, len(items))
	for index, item := range items {
		value, ok := item.(string)
		if !ok {
			return nil, fmt.Errorf("%s[%d] must be a string", key, index)
		}
		trimmed := strings.TrimSpace(value)
		if trimmed == "" {
			return nil, fmt.Errorf("%s[%d] must be a non-empty string", key, index)
		}
		values = append(values, trimmed)
	}
	return values, nil
}

func intFromArgument(raw interface{}, defaultValue int) int {
	if raw == nil {
		return defaultValue
	}
	value, ok := raw.(float64)
	if !ok {
		return defaultValue
	}
	return int(value)
}

func metadataArg(raw interface{}) (map[string]string, error) {
	if raw == nil {
		return nil, nil
	}
	valueMap, ok := raw.(map[string]interface{})
	if !ok {
		return nil, fmt.Errorf("metadata must be an object")
	}
	metadata := make(map[string]string, len(valueMap))
	for key, value := range valueMap {
		metadata[key] = fmt.Sprint(value)
	}
	return metadata, nil
}

func resolveConfig(resolver ConfigResolver, repoRoot string) (*config.Config, error) {
	if resolver == nil {
		return nil, fmt.Errorf("config resolver is not configured")
	}
	resolvedConfig, err := resolver(repoRoot)
	if err != nil {
		return nil, fmt.Errorf("resolve config: %w", err)
	}
	return resolvedConfig, nil
}

func (r *Registry) loadTaskInfo(repoRoot, runID, taskID string) (*execution.TaskInfo, error) {
	store := artifact.NewStore(repoRoot)
	plan, err := store.ReadPlan(runID)
	if err != nil {
		return nil, fmt.Errorf("read plan %s: %w", runID, err)
	}
	planTasks, err := execution.ParsePlanTasks(plan)
	if err != nil {
		return nil, fmt.Errorf("parse plan tasks for %s: %w", runID, err)
	}
	for index := range planTasks {
		if planTasks[index].ID == taskID {
			task := planTasks[index]
			return &task, nil
		}
	}
	return nil, fmt.Errorf("task %s not found in run %s", taskID, runID)
}

func (r *Registry) evaluateTaskPathPolicy(repoRoot, runID, taskID, filePath string, operation policy.OperationType) (*policy.Engine, *execution.TaskInfo, string, policy.PolicyResult, error) {
	resolvedConfig, err := resolveConfig(r.configResolver, repoRoot)
	if err != nil {
		return nil, nil, "", policy.PolicyResult{}, err
	}
	engine := policy.NewEngine(&resolvedConfig.Policy)
	taskInfo, err := r.loadTaskInfo(repoRoot, runID, taskID)
	if err != nil {
		return nil, nil, "", policy.PolicyResult{}, err
	}
	normalizedPath, err := policy.NormalizePath(repoRoot, filePath)
	if err != nil {
		result := policy.PolicyResult{
			Allowed:    false,
			ReasonCode: policy.ReasonPathTraversal,
			Message:    err.Error(),
			Profile:    resolvedConfig.Profile,
		}
		return engine, taskInfo, strings.TrimSpace(filePath), result, nil
	}

	decision := policy.Decision{
		Operation:   operation,
		Value:       normalizedPath,
		RunID:       runID,
		TaskID:      taskID,
		FileTargets: append([]string(nil), taskInfo.FileTargets...),
		Metadata: map[string]string{
			"repo_root": repoRoot,
		},
	}
	result := engine.Evaluate(decision)
	if result.Profile == "" {
		result.Profile = resolvedConfig.Profile
	}
	return engine, taskInfo, normalizedPath, result, nil
}

func sha256Hex(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func runCommandCapture(cmd *exec.Cmd) ([]byte, []byte, error) {
	var stdoutBuilder strings.Builder
	var stderrBuilder strings.Builder
	cmd.Stdout = &stdoutBuilder
	cmd.Stderr = &stderrBuilder
	err := cmd.Run()
	return []byte(stdoutBuilder.String()), []byte(stderrBuilder.String()), err
}

func exitCodeForError(err error) int {
	if err == nil {
		return 0
	}
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) {
		return exitErr.ExitCode()
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return -1
	}
	return -1
}

func matchesGlobFilters(relPath string, include, exclude []string) bool {
	if len(include) > 0 && !matchesAnyPattern(relPath, include) {
		return false
	}
	if len(exclude) > 0 && matchesAnyPattern(relPath, exclude) {
		return false
	}
	return true
}

func matchesAnyPattern(relPath string, patterns []string) bool {
	for _, pattern := range patterns {
		if matchGlob(relPath, pattern) {
			return true
		}
	}
	return false
}

func matchGlob(relPath, pattern string) bool {
	if strings.TrimSpace(pattern) == "" {
		return false
	}
	normalizedPattern := filepath.ToSlash(strings.TrimSpace(pattern))
	normalizedPath := filepath.ToSlash(strings.TrimSpace(relPath))
	regexParts := globTokenPattern.FindAllString(normalizedPattern, -1)
	var builder strings.Builder
	builder.WriteString("^")
	for _, token := range regexParts {
		switch token {
		case "**":
			builder.WriteString(".*")
		case "*":
			builder.WriteString("[^/]*")
		case "?":
			builder.WriteString("[^/]")
		default:
			builder.WriteString(regexp.QuoteMeta(token))
		}
	}
	builder.WriteString("$")
	re, err := regexp.Compile(builder.String())
	if err != nil {
		matched, fallbackErr := path.Match(normalizedPattern, normalizedPath)
		return fallbackErr == nil && matched
	}
	return re.MatchString(normalizedPath)
}

func detectRepoMapMetadata(relPath string) (string, string) {
	ext := strings.ToLower(filepath.Ext(relPath))
	pathLower := strings.ToLower(relPath)
	if strings.Contains(pathLower, "test") {
		return languageForExtension(ext), "test"
	}
	if ext == ".md" {
		return "Markdown", "doc"
	}
	if isConfigExtension(ext) {
		return languageForExtension(ext), "config"
	}
	if isSourceExtension(ext) {
		return languageForExtension(ext), "source"
	}
	return languageForExtension(ext), "other"
}

func languageForExtension(ext string) string {
	switch ext {
	case ".go":
		return "Go"
	case ".ts", ".tsx":
		return "TypeScript"
	case ".js", ".jsx":
		return "JavaScript"
	case ".py":
		return "Python"
	case ".rs":
		return "Rust"
	case ".md":
		return "Markdown"
	case ".json":
		return "JSON"
	case ".yaml", ".yml":
		return "YAML"
	case ".toml":
		return "TOML"
	default:
		return "Unknown"
	}
}

func isSourceExtension(ext string) bool {
	switch ext {
	case ".go", ".ts", ".tsx", ".js", ".jsx", ".py", ".rs":
		return true
	default:
		return false
	}
}

func isConfigExtension(ext string) bool {
	switch ext {
	case ".json", ".yaml", ".yml", ".toml":
		return true
	default:
		return false
	}
}

func applyUnifiedPatch(original []byte, patchText string) ([]byte, error) {
	lines, hadTrailingNewline := splitContentLines(string(original))
	patchLines := splitPatchLines(patchText)
	hunks, endWithNewline, err := parsePatchHunks(patchLines)
	if err != nil {
		return nil, err
	}

	result := make([]string, 0, len(lines))
	currentIndex := 0
	for _, hunk := range hunks {
		startIndex := hunk.oldStart
		if startIndex > 0 {
			startIndex--
		}
		if startIndex < currentIndex || startIndex > len(lines) {
			return nil, fmt.Errorf("hunk start %d is outside the target file", hunk.oldStart)
		}
		result = append(result, lines[currentIndex:startIndex]...)
		currentIndex = startIndex

		for _, operation := range hunk.lines {
			switch operation.kind {
			case ' ':
				if currentIndex >= len(lines) || lines[currentIndex] != operation.text {
					return nil, fmt.Errorf("context mismatch at line %d", currentIndex+1)
				}
				result = append(result, lines[currentIndex])
				currentIndex++
			case '-':
				if currentIndex >= len(lines) || lines[currentIndex] != operation.text {
					return nil, fmt.Errorf("delete mismatch at line %d", currentIndex+1)
				}
				currentIndex++
			case '+':
				result = append(result, operation.text)
			default:
				return nil, fmt.Errorf("unsupported patch operation %q", string(operation.kind))
			}
		}
	}

	result = append(result, lines[currentIndex:]...)
	return []byte(joinPatchedLines(result, hadTrailingNewline, endWithNewline)), nil
}

type patchHunk struct {
	oldStart int
	lines    []patchOperation
}

type patchOperation struct {
	kind byte
	text string
}

func parsePatchHunks(patchLines []string) ([]patchHunk, *bool, error) {
	hunks := make([]patchHunk, 0)
	var current *patchHunk
	var endWithNewline *bool

	for _, line := range patchLines {
		if strings.HasPrefix(line, "--- ") || strings.HasPrefix(line, "+++ ") || strings.HasPrefix(line, "diff ") || strings.HasPrefix(line, "index ") {
			continue
		}
		if strings.HasPrefix(line, "@@") {
			if current != nil {
				hunks = append(hunks, *current)
			}
			oldStart, err := parseHunkHeader(line)
			if err != nil {
				return nil, nil, err
			}
			current = &patchHunk{oldStart: oldStart, lines: make([]patchOperation, 0)}
			continue
		}
		if line == `\ No newline at end of file` {
			value := false
			endWithNewline = &value
			continue
		}
		if current == nil {
			if strings.TrimSpace(line) == "" {
				continue
			}
			return nil, nil, fmt.Errorf("patch missing unified diff hunk header")
		}
		if line == "" {
			current.lines = append(current.lines, patchOperation{kind: ' ', text: ""})
			continue
		}
		kind := line[0]
		if kind != ' ' && kind != '+' && kind != '-' {
			return nil, nil, fmt.Errorf("unsupported patch line %q", line)
		}
		current.lines = append(current.lines, patchOperation{kind: kind, text: line[1:]})
	}

	if current != nil {
		hunks = append(hunks, *current)
	}
	if len(hunks) == 0 {
		return nil, nil, fmt.Errorf("patch does not contain any hunks")
	}
	return hunks, endWithNewline, nil
}

func parseHunkHeader(line string) (int, error) {
	parts := strings.Split(line, " ")
	if len(parts) < 3 {
		return 0, fmt.Errorf("invalid hunk header %q", line)
	}
	oldRange := strings.TrimPrefix(parts[1], "-")
	values := strings.SplitN(oldRange, ",", 2)
	if len(values) == 0 || strings.TrimSpace(values[0]) == "" {
		return 0, fmt.Errorf("invalid old range in hunk header %q", line)
	}
	var oldStart int
	if _, err := fmt.Sscanf(values[0], "%d", &oldStart); err != nil {
		return 0, fmt.Errorf("parse hunk header %q: %w", line, err)
	}
	return oldStart, nil
}

func splitContentLines(content string) ([]string, bool) {
	if content == "" {
		return []string{}, false
	}
	hadTrailingNewline := strings.HasSuffix(content, "\n")
	trimmed := strings.TrimSuffix(content, "\n")
	return strings.Split(trimmed, "\n"), hadTrailingNewline
}

func splitPatchLines(patchText string) []string {
	normalized := strings.ReplaceAll(patchText, "\r\n", "\n")
	normalized = strings.TrimSuffix(normalized, "\n")
	if normalized == "" {
		return []string{}
	}
	return strings.Split(normalized, "\n")
}

func joinPatchedLines(lines []string, originalTrailingNewline bool, endWithNewline *bool) string {
	joined := strings.Join(lines, "\n")
	finalTrailingNewline := originalTrailingNewline
	if endWithNewline != nil {
		finalTrailingNewline = *endWithNewline
	}
	if finalTrailingNewline && (joined != "" || len(lines) > 0) {
		joined += "\n"
	}
	return joined
}
