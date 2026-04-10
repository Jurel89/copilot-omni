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

	"github.com/copilot-omni/sidecar/internal/config"
	"github.com/copilot-omni/sidecar/internal/doctor"
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

	artifactPath, err := validateArtifactPath(repoRoot, runID, filename)
	if err != nil {
		return ToolCallResult{}, err
	}

	data, err := os.ReadFile(artifactPath)
	if err != nil {
		return ToolCallResult{}, fmt.Errorf("read artifact %s/%s: %w", runID, filename, err)
	}

	return ToolCallResult{
		Content: []ToolContent{{
			Type: "text",
			Text: string(data),
		}},
	}, nil
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

	result := map[string]interface{}{
		"status":  "ok",
		"path":    artifactPath,
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
