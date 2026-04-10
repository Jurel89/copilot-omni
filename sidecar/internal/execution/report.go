package execution

import "time"

type VerificationReport struct {
	RunID     string               `json:"run_id"`
	Timestamp string               `json:"timestamp"`
	Mode      string               `json:"mode"`
	Status    string               `json:"status"`
	Results   []VerificationResult `json:"results"`
	Summary   VerificationSummary  `json:"summary"`
}

type VerificationResult struct {
	TaskID     string `json:"task_id,omitempty"`
	Command    string `json:"command"`
	ExitCode   int    `json:"exit_code"`
	StdoutPath string `json:"stdout_path,omitempty"`
	StderrPath string `json:"stderr_path,omitempty"`
	DurationMs int64  `json:"duration_ms"`
	Status     string `json:"status"`
}

type VerificationSummary struct {
	Total  int `json:"total"`
	Passed int `json:"passed"`
	Failed int `json:"failed"`
}

func GenerateVerificationReport(runID string, results []VerificationResult, mode string) *VerificationReport {
	reportResults := make([]VerificationResult, len(results))
	copy(reportResults, results)

	summary := VerificationSummary{Total: len(reportResults)}
	status := "passed"
	for _, result := range reportResults {
		if result.Status == "pass" {
			summary.Passed++
			continue
		}

		summary.Failed++
		status = "failed"
	}

	return &VerificationReport{
		RunID:     runID,
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Mode:      mode,
		Status:    status,
		Results:   reportResults,
		Summary:   summary,
	}
}
