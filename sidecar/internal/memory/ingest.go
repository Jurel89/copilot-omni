package memory

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/copilot-omni/sidecar/internal/artifact"
	"github.com/copilot-omni/sidecar/internal/run"
)

func IngestRunArtifacts(store *Store, repoRoot, runID string) error {
	if store == nil {
		return &Error{Code: "nil_store"}
	}

	artStore := artifact.NewStore(repoRoot)
	ingestErrors := make([]string, 0)

	if err := ingestSpec(store, artStore, runID); err != nil {
		if !os.IsNotExist(err) {
			ingestErrors = append(ingestErrors, fmt.Sprintf("spec: %v", err))
		}
	}

	if err := ingestPlan(store, artStore, runID); err != nil {
		if !os.IsNotExist(err) {
			ingestErrors = append(ingestErrors, fmt.Sprintf("plan: %v", err))
		}
	}

	if err := ingestDecisions(store, artStore, runID); err != nil {
		if !os.IsNotExist(err) {
			ingestErrors = append(ingestErrors, fmt.Sprintf("decisions: %v", err))
		}
	}

	if err := ingestRunSummary(store, artStore, repoRoot, runID); err != nil {
		if !os.IsNotExist(err) {
			ingestErrors = append(ingestErrors, fmt.Sprintf("summary: %v", err))
		}
	}

	if len(ingestErrors) > 0 {
		return fmt.Errorf("ingest run artifacts: %s", strings.Join(ingestErrors, "; "))
	}

	return nil
}

func ingestSpec(memStore *Store, artStore *artifact.Store, runID string) error {
	spec, err := artStore.ReadSpec(runID)
	if err != nil {
		return err
	}

	content, wasRedacted := RedactSecrets(spec)

	title := extractTitle(content, "Spec")
	if strings.TrimSpace(title) == "" {
		title = fmt.Sprintf("Specification for %s", runID)
	}

	sensitivity := SensitivityNormal
	if wasRedacted {
		sensitivity = SensitivitySensitive
	}

	record := &MemoryRecord{
		Type:        TypeSpec,
		Source:      SourceArtifact,
		Scope:       ScopeProject,
		RunID:       runID,
		Title:       title,
		Content:     truncateContent(content),
		TrustLevel:  TrustMedium,
		Sensitivity: sensitivity,
		Tags:        []string{"spec", "artifact"},
		Metadata:    map[string]string{"artifact_type": "spec"},
	}

	return memStore.CreateOrUpdate(record)
}

func ingestPlan(memStore *Store, artStore *artifact.Store, runID string) error {
	plan, err := artStore.ReadPlan(runID)
	if err != nil {
		return err
	}

	planJSON, err := json.Marshal(plan)
	if err != nil {
		return err
	}

	content := string(planJSON)
	content, wasRedacted := RedactSecrets(content)

	sensitivity := SensitivityNormal
	if wasRedacted {
		sensitivity = SensitivitySensitive
	}

	taskCount := 0
	if tasks, ok := plan["tasks"].([]interface{}); ok {
		taskCount = len(tasks)
	}

	title := fmt.Sprintf("Plan for %s (%d tasks)", runID, taskCount)
	if runIDVal, ok := plan["run_id"].(string); ok && runIDVal != "" {
		title = fmt.Sprintf("Implementation plan (%d tasks)", taskCount)
	}

	record := &MemoryRecord{
		Type:        TypePlan,
		Source:      SourceArtifact,
		Scope:       ScopeProject,
		RunID:       runID,
		Title:       title,
		Content:     truncateContent(content),
		TrustLevel:  TrustMedium,
		Sensitivity: sensitivity,
		Tags:        []string{"plan", "artifact"},
		Metadata:    map[string]string{"artifact_type": "plan", "task_count": fmt.Sprintf("%d", taskCount)},
	}

	return memStore.CreateOrUpdate(record)
}

func ingestDecisions(memStore *Store, artStore *artifact.Store, runID string) error {
	decisions, err := artStore.ReadDecisions(runID)
	if err != nil {
		return err
	}

	content, wasRedacted := RedactSecrets(decisions)

	title := extractTitle(content, "Decisions")

	sensitivity := SensitivityNormal
	if wasRedacted {
		sensitivity = SensitivitySensitive
	}

	record := &MemoryRecord{
		Type:        TypeDecision,
		Source:      SourceArtifact,
		Scope:       ScopeProject,
		RunID:       runID,
		Title:       title,
		Content:     truncateContent(content),
		TrustLevel:  TrustHigh,
		Sensitivity: sensitivity,
		Tags:        []string{"decision", "artifact"},
		Metadata:    map[string]string{"artifact_type": "decisions"},
	}

	return memStore.CreateOrUpdate(record)
}

func ingestRunSummary(memStore *Store, artStore *artifact.Store, repoRoot, runID string) error {
	runObj, err := artStore.ReadRun(runID)
	if err != nil {
		return err
	}

	summary := run.Summarize(runObj)
	if summary == nil {
		return nil
	}

	summaryJSON, err := json.Marshal(summary)
	if err != nil {
		return err
	}

	content := string(summaryJSON)
	record := &MemoryRecord{
		Type:       TypeSummary,
		Source:     SourceSystem,
		Scope:      ScopeProject,
		RunID:      runID,
		Title:      fmt.Sprintf("Run summary: %s (%s)", runID, summary.Status),
		Content:    truncateContent(content),
		TrustLevel: TrustMedium,
		Tags:       []string{"summary", "run"},
		Metadata: map[string]string{
			"status":         summary.Status,
			"current_phase":  summary.CurrentPhase,
			"artifact_count": fmt.Sprintf("%d", summary.ArtifactCount),
		},
	}

	return memStore.CreateOrUpdate(record)
}

func IngestVerificationReport(memStore *Store, repoRoot, runID string) error {
	reportPath := filepath.Join(repoRoot, ".omni", "runs", runID, "verification-report.json")
	data, err := os.ReadFile(reportPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return &Error{Code: "read_verification_report", Err: err}
	}

	content := string(data)
	content, wasRedacted := RedactSecrets(content)

	sensitivity := SensitivityNormal
	if wasRedacted {
		sensitivity = SensitivitySensitive
	}

	var report map[string]interface{}
	status := "unknown"
	if json.Unmarshal(data, &report) == nil {
		if s, ok := report["status"].(string); ok {
			status = s
		}
	}

	record := &MemoryRecord{
		Type:        TypeVerification,
		Source:      SourceSystem,
		Scope:       ScopeProject,
		RunID:       runID,
		Title:       fmt.Sprintf("Verification report: %s (%s)", runID, status),
		Content:     truncateContent(content),
		TrustLevel:  TrustHigh,
		Sensitivity: sensitivity,
		Tags:        []string{"verification", "artifact"},
		Metadata:    map[string]string{"status": status, "artifact_type": "verification-report"},
	}

	return memStore.CreateOrUpdate(record)
}

func extractTitle(content, defaultPrefix string) string {
	lines := strings.Split(content, "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "# ") {
			title := strings.TrimPrefix(line, "# ")
			title = strings.TrimSpace(title)
			if title != "" {
				return title
			}
		}
	}
	return defaultPrefix
}

func truncateContent(content string) string {
	const maxContentLen = 50000
	if len(content) > maxContentLen {
		return content[:maxContentLen] + "\n... [truncated]"
	}
	return content
}

var (
	secretPatterns = []*regexp.Regexp{
		regexp.MustCompile(`(?i)["']?(?:api[_-]?key|apikey|secret|token|password|credential)["']?\s*[:=]\s*["']?[a-zA-Z0-9\-._~+/]{16,}["']?`),
		regexp.MustCompile(`(?i)(api[_-]?key|apikey|access[_-]?token|secret[_-]?key|auth[_-]?token|password|passwd|credentials?)\s*[:=]\s*['"]?[^\s'"]{8,}['"]?`),
		regexp.MustCompile(`(?i)bearer\s+[a-zA-Z0-9\-._~+/]+=*`),
		regexp.MustCompile(`(?i)ghp_[a-zA-Z0-9]{36}`),
		regexp.MustCompile(`(?i)gho_[a-zA-Z0-9]{36}`),
		regexp.MustCompile(`(?i)sk-[a-zA-Z0-9]{20,}`),
		regexp.MustCompile(`(?i)xox[bpas]-[a-zA-Z0-9\-]{10,}`),
		regexp.MustCompile(`(?i)-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----`),
		regexp.MustCompile(`(?i)AKIA[0-9A-Z]{16}`),
	}

	redactReplacement = "[REDACTED]"
)

func RedactSecrets(content string) (string, bool) {
	found := false
	result := content
	for _, pattern := range secretPatterns {
		if pattern.MatchString(result) {
			found = true
			result = pattern.ReplaceAllStringFunc(result, func(match string) string {
				prefix := ""
				parts := strings.SplitN(match, "=", 2)
				if len(parts) == 2 {
					prefix = parts[0] + "="
					return prefix + redactReplacement
				}
				parts = strings.SplitN(match, ":", 2)
				if len(parts) == 2 {
					prefix = parts[0] + ":"
					return prefix + redactReplacement
				}
				parts = strings.SplitN(match, " ", 2)
				if len(parts) == 2 {
					return parts[0] + " " + redactReplacement
				}
				return redactReplacement
			})
		}
	}
	return result, found
}
