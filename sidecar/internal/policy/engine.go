package policy

import (
	"fmt"
	"path/filepath"
	"strings"

	"github.com/copilot-omni/sidecar/internal/config"
)

type OperationType string

const (
	OpCommand          OperationType = "command"
	OpPathWrite        OperationType = "path_write"
	OpPathRead         OperationType = "path_read"
	OpArtifactMutation OperationType = "artifact_mutation"
	OpTool             OperationType = "tool"
	OpNetwork          OperationType = "network"
	OpMemory           OperationType = "memory"
	OpUpdate           OperationType = "update"
)

type Decision struct {
	Operation   OperationType // command, path_write, path_read, artifact_mutation
	Value       string        // the command, path, or artifact being checked
	RunID       string
	TaskID      string
	FileTargets []string // approved file targets from plan
	Metadata    map[string]string
}

type PolicyResult struct {
	Allowed     bool   `json:"allowed"`
	ReasonCode  string `json:"reason_code,omitempty"`
	Message     string `json:"message,omitempty"`
	Profile     string `json:"profile"`
	MatchedRule string `json:"matched_rule,omitempty"`
}

type Engine struct {
	cfg     config.PolicyConfig
	profile string
}

func NewEngine(cfg *config.PolicyConfig) *Engine {
	if cfg == nil {
		return &Engine{profile: profileName(config.PolicyConfig{})}
	}

	cloned := *cfg
	cloned.ProtectedPaths = append([]string(nil), cfg.ProtectedPaths...)
	cloned.DeniedCommands = append([]string(nil), cfg.DeniedCommands...)

	return &Engine{cfg: cloned, profile: profileName(cloned)}
}

func (e *Engine) Evaluate(decision Decision) PolicyResult {
	profile := e.profile
	if profile == "" {
		profile = profileName(e.cfg)
	}

	if decision.Operation == OpArtifactMutation {
		scan := ScanForInjection(decision.Value)
		if !scan.Clean && (profile != "permissive" || scan.Severity == "critical") {
			return PolicyResult{
				Allowed:    false,
				ReasonCode: ReasonInjectionDetected,
				Message:    fmt.Sprintf("artifact content matched prompt injection patterns (%s)", strings.Join(scan.Detections, ", ")),
				Profile:    profile,
			}
		}
	}

	switch decision.Operation {
	case OpCommand:
		if denied, matchedRule := IsDeniedCommand(decision.Value, e.cfg.DeniedCommands); denied {
			return PolicyResult{
				Allowed:     false,
				ReasonCode:  ReasonDeniedCommand,
				Message:     fmt.Sprintf("command %q is denied by policy", strings.TrimSpace(decision.Value)),
				Profile:     profile,
				MatchedRule: matchedRule,
			}
		}

		if e.cfg.StrictMode && !isCommandAllowed(decision.Value, decision.Metadata) {
			return PolicyResult{
				Allowed:    false,
				ReasonCode: ReasonStrictModeDefault,
				Message:    "strict mode blocks commands unless explicitly allowed",
				Profile:    profile,
			}
		}

		return allowedResult(profile)
	case OpPathWrite, OpPathRead:
		normalizedPath, err := normalizeDecisionPath(decision)
		if err != nil {
			return pathErrorResult(profile, err)
		}

		if decision.Operation == OpPathWrite && IsProtectedPath(normalizedPath, e.cfg.ProtectedPaths) {
			return PolicyResult{
				Allowed:    false,
				ReasonCode: ReasonProtectedPath,
				Message:    fmt.Sprintf("path %q is protected by policy", normalizedPath),
				Profile:    profile,
			}
		}

		inScope := IsWithinScope(normalizedPath, decision.FileTargets)
		if decision.Operation == OpPathWrite && profile != "permissive" && !inScope {
			return PolicyResult{
				Allowed:    false,
				ReasonCode: ReasonOutOfScope,
				Message:    fmt.Sprintf("path %q is outside approved plan targets", normalizedPath),
				Profile:    profile,
			}
		}

		if e.cfg.StrictMode && !inScope {
			return PolicyResult{
				Allowed:    false,
				ReasonCode: ReasonStrictModeDefault,
				Message:    fmt.Sprintf("strict mode requires explicit scope for %q", normalizedPath),
				Profile:    profile,
			}
		}

		return allowedResult(profile)
	case OpArtifactMutation:
		return allowedResult(profile)
	case OpTool, OpNetwork, OpMemory, OpUpdate:
		return allowedResult(profile)
	default:
		return PolicyResult{
			Allowed:    false,
			ReasonCode: ReasonUnknownOperation,
			Message:    fmt.Sprintf("operation %q is not recognized", decision.Operation),
			Profile:    profile,
		}
	}
}

func allowedResult(profile string) PolicyResult {
	return PolicyResult{
		Allowed:    true,
		ReasonCode: ReasonAllowed,
		Profile:    profile,
	}
}

func pathErrorResult(profile string, err error) PolicyResult {
	if policyErr, ok := err.(*pathError); ok {
		return PolicyResult{
			Allowed:    false,
			ReasonCode: policyErr.Code,
			Message:    policyErr.Error(),
			Profile:    profile,
		}
	}

	return PolicyResult{
		Allowed:    false,
		ReasonCode: ReasonPathTraversal,
		Message:    err.Error(),
		Profile:    profile,
	}
}

func normalizeDecisionPath(decision Decision) (string, error) {
	if repoRoot := strings.TrimSpace(decision.Metadata["repo_root"]); repoRoot != "" {
		return NormalizePath(repoRoot, decision.Value)
	}

	value := strings.TrimSpace(decision.Value)
	if value == "" || filepath.IsAbs(value) {
		return "", &pathError{Code: ReasonPathTraversal}
	}

	cleaned := filepath.Clean(value)
	if cleaned == "." || cleaned == ".." || strings.HasPrefix(cleaned, ".."+string(filepath.Separator)) {
		return "", &pathError{Code: ReasonPathTraversal}
	}

	return filepath.ToSlash(cleaned), nil
}

func isCommandAllowed(command string, metadata map[string]string) bool {
	if len(metadata) == 0 {
		return false
	}

	allowed := strings.TrimSpace(metadata["allowed_commands"])
	if allowed == "" {
		return false
	}

	normalized := NormalizeCommand(command)
	for _, entry := range strings.FieldsFunc(allowed, splitList) {
		candidate := strings.ToLower(strings.TrimSpace(entry))
		if candidate == "" {
			continue
		}

		if normalized == NormalizeCommand(candidate) || strings.EqualFold(strings.TrimSpace(command), strings.TrimSpace(candidate)) {
			return true
		}
	}

	return false
}

func splitList(r rune) bool {
	return r == ',' || r == '\n' || r == ';'
}

func profileName(cfg config.PolicyConfig) string {
	if cfg.StrictMode {
		return "strict"
	}

	if len(cfg.ProtectedPaths) == 0 && len(cfg.DeniedCommands) == 0 {
		return "permissive"
	}

	return "standard"
}
