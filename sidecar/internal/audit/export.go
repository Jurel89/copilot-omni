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
	RunID        string              `json:"run_id"`
	RepoRoot     string              `json:"repo_root"`
	ExportedAt   string              `json:"exported_at"`
	Profile      string              `json:"profile,omitempty"`
	RunStatus    string              `json:"run_status"`
	Phases       []PhaseAudit        `json:"phases"`
	PolicyAudit  *PolicyAudit        `json:"policy_audit,omitempty"`
	Artifacts    []string            `json:"artifacts,omitempty"`
	Verification *VerificationResult `json:"verification,omitempty"`
	Packaging    *PackagingMetadata  `json:"packaging,omitempty"`
	Redacted     bool                `json:"redacted"`
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

type VerificationResult struct {
	Status  string `json:"status"`
	Summary string `json:"summary,omitempty"`
	Checks  int    `json:"checks,omitempty"`
	Passed  int    `json:"passed,omitempty"`
	Failed  int    `json:"failed,omitempty"`
}

type PackagingMetadata struct {
	BundleAvailable bool   `json:"bundle_available"`
	ReleaseTag      string `json:"release_tag,omitempty"`
	Platform        string `json:"platform,omitempty"`
	Provenance      string `json:"provenance,omitempty"`
	ComponentCount  int    `json:"component_count,omitempty"`
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
			if phases, ok := run["phases"].([]interface{}); ok {
				for _, p := range phases {
					if pm, ok := p.(map[string]interface{}); ok {
						pa := PhaseAudit{}
						if v, ok := pm["phase"].(string); ok {
							pa.Phase = v
						}
						if v, ok := pm["status"].(string); ok {
							pa.Status = v
						}
						if v, ok := pm["started_at"].(string); ok {
							pa.StartedAt = v
						}
						if v, ok := pm["ended_at"].(string); ok {
							pa.EndedAt = v
						}
						if v, ok := pm["error"].(string); ok {
							pa.Error = v
						}
						export.Phases = append(export.Phases, pa)
					}
				}
			}
		}
	}

	entries, err := os.ReadDir(runDir)
	if err == nil {
		for _, entry := range entries {
			if !entry.IsDir() {
				export.Artifacts = append(export.Artifacts, entry.Name())
			}
		}
	}

	decisionsData, err := os.ReadFile(filepath.Join(runDir, "decisions.md"))
	if err == nil {
		decisions := parseDecisionsFromMarkdown(string(decisionsData), export.Profile)
		if len(decisions) > 0 {
			allowed := 0
			for _, d := range decisions {
				if d.Allowed {
					allowed++
				}
			}
			export.SetPolicyAudit(len(decisions), allowed, len(decisions)-allowed, decisions)
		}
	}

	verifData, err := os.ReadFile(filepath.Join(runDir, "verification-report.json"))
	if err == nil {
		var verif map[string]interface{}
		if json.Unmarshal(verifData, &verif) == nil {
			vr := &VerificationResult{}
			if s, ok := verif["status"].(string); ok {
				vr.Status = s
			}
			if s, ok := verif["summary"].(string); ok {
				vr.Summary = s
			}
			if n, ok := verif["checks"].(float64); ok {
				vr.Checks = int(n)
			}
			if n, ok := verif["passed"].(float64); ok {
				vr.Passed = int(n)
			}
			if n, ok := verif["failed"].(float64); ok {
				vr.Failed = int(n)
			}
			export.Verification = vr
		}
	}

	bundleDir := filepath.Join(repoRoot, ".omni", "bundle")
	manifestPath := filepath.Join(bundleDir, "release-manifest.json")
	manifestData, err := os.ReadFile(manifestPath)
	if err == nil {
		var manifest map[string]interface{}
		if json.Unmarshal(manifestData, &manifest) == nil {
			pkg := &PackagingMetadata{BundleAvailable: true}
			if tag, ok := manifest["release_tag"].(string); ok {
				pkg.ReleaseTag = tag
			}
			if plat, ok := manifest["platform"].(string); ok {
				pkg.Platform = plat
			}
			if prov, ok := manifest["provenance"].(map[string]interface{}); ok {
				if fp, ok := prov["fingerprint"].(string); ok {
					pkg.Provenance = fp
				} else if sig, ok := prov["signature"].(string); ok {
					pkg.Provenance = sig
				}
			}
			if comps, ok := manifest["components"].([]interface{}); ok {
				pkg.ComponentCount = len(comps)
			}
			export.Packaging = pkg
		}
	}

	redactSecrets(export)

	if _, outputErr := export.Write(outputPath); outputErr != nil {
		return nil, outputErr
	}

	return export, nil
}

func redactSecrets(export *Export) {
	export.Redacted = true
	for i := range export.Artifacts {
		name := export.Artifacts[i]
		lower := strings.ToLower(name)
		if strings.Contains(lower, "secret") || strings.Contains(lower, "credential") || strings.Contains(lower, "token") {
			export.Artifacts[i] = name + " [REDACTED]"
		}
	}
}

func parseDecisionsFromMarkdown(content, profile string) []PolicyDecision {
	decisions := make([]PolicyDecision, 0)
	lines := strings.Split(content, "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "- ") || strings.HasPrefix(line, "* ") {
			text := strings.TrimPrefix(line, "- ")
			text = strings.TrimPrefix(text, "* ")
			allowed := !strings.Contains(strings.ToLower(text), "denied") && !strings.Contains(strings.ToLower(text), "blocked") && !strings.Contains(strings.ToLower(text), "rejected")
			reasonCode := "allowed"
			if !allowed {
				reasonCode = "denied"
			}
			decisions = append(decisions, PolicyDecision{
				Operation:  "decision",
				Value:      text,
				Allowed:    allowed,
				ReasonCode: reasonCode,
				Profile:    profile,
			})
		}
	}
	return decisions
}
