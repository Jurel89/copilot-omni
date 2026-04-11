package benchmark

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

type Report struct {
	GeneratedAt time.Time          `json:"generated_at"`
	Summary     ReportSummary      `json:"summary"`
	Results     []*BenchmarkResult `json:"results"`
	Budgets     BudgetSet          `json:"budgets"`
}

type ReportSummary struct {
	TotalBenchmarks int           `json:"total_benchmarks"`
	Passed          int           `json:"passed"`
	Warned          int           `json:"warned"`
	Failed          int           `json:"failed"`
	TotalDuration   time.Duration `json:"total_duration_ms"`
}

func GenerateReport(results []*BenchmarkResult, budgets BudgetSet) *Report {
	summary := ReportSummary{
		TotalBenchmarks: len(results),
	}

	for _, r := range results {
		switch r.Status {
		case BudgetPass:
			summary.Passed++
		case BudgetWarn:
			summary.Warned++
		case BudgetFail:
			summary.Failed++
		}
		summary.TotalDuration += r.Duration
	}

	return &Report{
		GeneratedAt: time.Now(),
		Summary:     summary,
		Results:     results,
		Budgets:     budgets,
	}
}

func (r *Report) ToJSON() ([]byte, error) {
	return json.MarshalIndent(r, "", "  ")
}

func (r *Report) ToMarkdown() string {
	md := fmt.Sprintf("# Benchmark Report\n\n")
	md += fmt.Sprintf("Generated: %s\n\n", r.GeneratedAt.Format(time.RFC3339))

	md += "## Summary\n\n"
	md += fmt.Sprintf("- Total: %d\n", r.Summary.TotalBenchmarks)
	md += fmt.Sprintf("- Passed: %d\n", r.Summary.Passed)
	md += fmt.Sprintf("- Warning: %d\n", r.Summary.Warned)
	md += fmt.Sprintf("- Failed: %d\n", r.Summary.Failed)
	md += fmt.Sprintf("- Duration: %s\n\n", r.Summary.TotalDuration)

	md += "## Budgets\n\n"
	md += fmt.Sprintf("| Metric | Target |\n")
	md += fmt.Sprintf("|--------|--------|\n")
	md += fmt.Sprintf("| Cold Start P95 | %s |\n", r.Budgets.ColdStartP95)
	md += fmt.Sprintf("| Memory Search P95 | %s |\n", r.Budgets.MemorySearchP95)
	md += fmt.Sprintf("| Policy Check P95 | %s |\n", r.Budgets.PolicyCheckP95)
	md += fmt.Sprintf("| Artifact Load P95 | %s |\n", r.Budgets.ArtifactLoadP95)
	md += fmt.Sprintf("| Plan Parse P95 | %s |\n\n", r.Budgets.PlanParseP95)

	md += "## Results\n\n"
	for _, result := range r.Results {
		statusIcon := "✓"
		if result.Status == BudgetWarn {
			statusIcon = "⚠"
		} else if result.Status == BudgetFail {
			statusIcon = "✗"
		}

		md += fmt.Sprintf("### %s %s\n\n", statusIcon, result.Name)
		md += fmt.Sprintf("- Description: %s\n", result.Description)
		md += fmt.Sprintf("- Status: %s\n", result.Status)
		md += fmt.Sprintf("- Duration: %s\n", result.Duration)
		md += fmt.Sprintf("- Iterations: %d\n\n", result.Iterations)

		if len(result.Metrics) > 0 {
			md += "| Metric | Mean | P95 | Budget | Status |\n"
			md += "|--------|------|-----|--------|--------|\n"
			for name, metric := range result.Metrics {
				budgetStr := "-"
				if metric.Budget > 0 {
					budgetStr = metric.Budget.String()
				}
				md += fmt.Sprintf("| %s | %.2f | %.2f | %s | %s |\n",
					name, metric.Mean, metric.P95, budgetStr, metric.Status)
			}
			md += "\n"
		}

		if len(result.Errors) > 0 {
			md += "**Errors:**\n"
			for _, err := range result.Errors {
				md += fmt.Sprintf("- %s\n", err)
			}
			md += "\n"
		}
	}

	return md
}

func (r *Report) Save(dir string) error {
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("failed to create report directory: %w", err)
	}

	timestamp := r.GeneratedAt.Format("20060102-150405")

	jsonPath := filepath.Join(dir, fmt.Sprintf("benchmark-report-%s.json", timestamp))
	jsonData, err := r.ToJSON()
	if err != nil {
		return fmt.Errorf("failed to marshal report: %w", err)
	}
	if err := os.WriteFile(jsonPath, jsonData, 0644); err != nil {
		return fmt.Errorf("failed to write JSON report: %w", err)
	}

	mdPath := filepath.Join(dir, fmt.Sprintf("benchmark-report-%s.md", timestamp))
	if err := os.WriteFile(mdPath, []byte(r.ToMarkdown()), 0644); err != nil {
		return fmt.Errorf("failed to write Markdown report: %w", err)
	}

	return nil
}
