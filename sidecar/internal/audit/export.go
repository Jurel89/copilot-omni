package audit

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type Export struct {
	RunID       string       `json:"run_id"`
	RepoRoot    string       `json:"repo_root"`
	ExportedAt  string       `json:"exported_at"`
	Profile     string       `json:"profile,omitempty"`
	RunStatus   string       `json:"run_status"`
	Phases      []PhaseAudit `json:"phases"`
	PolicyAudit *PolicyAudit `json:"policy_audit,omitempty"`
	Redacted    bool         `json:"redacted"`
}

type PhaseAudit struct {
	Phase     string `json:"phase"`
	Status    string `json:"status"`
	StartedAt string `json:"started_at,omitempty"`
	EndedAt   string `json:"ended_at,omitempty"`
	Error     string `json:"error,omitempty"`
}

type PolicyAudit struct {
	TotalChecks int              `json:"total_checks"`
	Allowed     int              `json:"allowed"`
	Denied      int              `json:"denied"`
	Decisions   []PolicyDecision `json:"decisions,omitempty"`
}

type PolicyDecision struct {
	Operation  string `json:"operation"`
	Value      string `json:"value"`
	Allowed    bool   `json:"allowed"`
	ReasonCode string `json:"reason_code,omitempty"`
	Profile    string `json:"profile,omitempty"`
}

func NewExport(runID, repoRoot, profile string) *Export {
	return &Export{
		RunID:      runID,
		RepoRoot:   repoRoot,
		ExportedAt: time.Now().UTC().Format(time.RFC3339),
		Profile:    profile,
		Phases:     make([]PhaseAudit, 0),
		Redacted:   true,
	}
}

func (e *Export) AddPhase(phase, status, startedAt, endedAt, err string) {
	e.Phases = append(e.Phases, PhaseAudit{
		Phase:     phase,
		Status:    status,
		StartedAt: startedAt,
		EndedAt:   endedAt,
		Error:     err,
	})
}

func (e *Export) SetPolicyAudit(total, allowed, denied int, decisions []PolicyDecision) {
	e.PolicyAudit = &PolicyAudit{
		TotalChecks: total,
		Allowed:     allowed,
		Denied:      denied,
		Decisions:   decisions,
	}
}

func (e *Export) Write(outputPath string) (string, error) {
	payload, err := json.MarshalIndent(e, "", "  ")
	if err != nil {
		return "", fmt.Errorf("marshal audit export: %w", err)
	}

	dir := filepath.Dir(outputPath)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", fmt.Errorf("create output directory: %w", err)
	}

	if err := os.WriteFile(outputPath, payload, 0o644); err != nil {
		return "", fmt.Errorf("write audit export: %w", err)
	}

	return outputPath, nil
}

func ExportRun(repoRoot, runID, outputPath string) (*Export, error) {
	if strings.TrimSpace(runID) == "" {
		return nil, fmt.Errorf("run_id is required")
	}

	runDir := filepath.Join(repoRoot, ".omni", "runs", runID)
	if _, err := os.Stat(runDir); err != nil {
		return nil, fmt.Errorf("run directory not found: %w", err)
	}

	export := NewExport(runID, repoRoot, "")

	runData, err := os.ReadFile(filepath.Join(runDir, "run.json"))
	if err == nil {
		var run map[string]interface{}
		if json.Unmarshal(runData, &run) == nil {
			if status, ok := run["status"].(string); ok {
				export.RunStatus = status
			}
			if profile, ok := run["profile"].(string); ok {
				export.Profile = profile
			}
		}
	}

	if _, outputErr := export.Write(outputPath); outputErr != nil {
		return nil, outputErr
	}

	return export, nil
}
