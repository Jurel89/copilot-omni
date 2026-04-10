package research

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type Report struct {
	RunID         string            `json:"run_id"`
	Query         string            `json:"query"`
	Provenance    []ProvenanceEntry `json:"provenance"`
	Findings      []Finding         `json:"findings"`
	OpenQuestions []string          `json:"open_questions,omitempty"`
	Summary       string            `json:"summary"`
	Timestamp     string            `json:"timestamp"`
}

type ProvenanceEntry struct {
	Source string `json:"source"`
	Type   string `json:"type"`
	URL    string `json:"url,omitempty"`
	Query  string `json:"query,omitempty"`
}

type Finding struct {
	Title      string   `json:"title"`
	Content    string   `json:"content"`
	Category   string   `json:"category"`
	Confidence string   `json:"confidence"`
	Sources    []string `json:"sources,omitempty"`
}

type GenerateOptions struct {
	RunID         string
	Query         string
	RepoRoot      string
	WebResults    string
	RepoEvidence  string
	MemoryResults string
}

func Generate(opts GenerateOptions) (*Report, error) {
	if strings.TrimSpace(opts.RunID) == "" {
		return nil, fmt.Errorf("run_id is required")
	}
	if strings.TrimSpace(opts.Query) == "" {
		return nil, fmt.Errorf("query is required")
	}

	provenance := make([]ProvenanceEntry, 0)
	findings := make([]Finding, 0)
	openQuestions := make([]string, 0)

	if strings.TrimSpace(opts.WebResults) != "" {
		provenance = append(provenance, ProvenanceEntry{
			Source: "web",
			Type:   "reference",
			Query:  opts.Query,
		})
		findings = appendFindingsFromText(findings, opts.WebResults, "web", "inference", "medium")
	}

	if strings.TrimSpace(opts.RepoEvidence) != "" {
		provenance = append(provenance, ProvenanceEntry{
			Source: "repository",
			Type:   "fact",
		})
		findings = appendFindingsFromText(findings, opts.RepoEvidence, "repository", "fact", "high")
	}

	if strings.TrimSpace(opts.MemoryResults) != "" {
		provenance = append(provenance, ProvenanceEntry{
			Source: "memory",
			Type:   "fact",
		})
		findings = appendFindingsFromText(findings, opts.MemoryResults, "memory", "fact", "high")
	}

	if len(findings) == 0 {
		openQuestions = append(openQuestions, "No structured findings were produced for query: "+opts.Query)
	}

	summary := buildSummary(opts.Query, findings)

	report := &Report{
		RunID:         opts.RunID,
		Query:         opts.Query,
		Provenance:    provenance,
		Findings:      findings,
		OpenQuestions: openQuestions,
		Summary:       summary,
		Timestamp:     time.Now().UTC().Format(time.RFC3339),
	}

	return report, nil
}

func WriteReport(repoRoot, runID string, report *Report) (string, error) {
	if report == nil {
		return "", fmt.Errorf("report is nil")
	}

	dir := filepath.Join(repoRoot, ".omni", "runs", runID)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", fmt.Errorf("create run directory: %w", err)
	}

	path := filepath.Join(dir, "research-report.json")
	payload, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return "", fmt.Errorf("marshal research report: %w", err)
	}

	if err := os.WriteFile(path, payload, 0o644); err != nil {
		return "", fmt.Errorf("write research report: %w", err)
	}

	return path, nil
}

func ReadReport(repoRoot, runID string) (*Report, error) {
	path := filepath.Join(repoRoot, ".omni", "runs", runID, "research-report.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read research report: %w", err)
	}

	var report Report
	if err := json.Unmarshal(data, &report); err != nil {
		return nil, fmt.Errorf("decode research report: %w", err)
	}

	return &report, nil
}

func appendFindingsFromText(findings []Finding, text, source, category, confidence string) []Finding {
	lines := strings.Split(text, "\n")
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}
		if len(trimmed) < 10 {
			continue
		}
		findings = append(findings, Finding{
			Title:      source + ": " + truncate(trimmed, 80),
			Content:    trimmed,
			Category:   category,
			Confidence: confidence,
			Sources:    []string{source},
		})
	}
	return findings
}

func buildSummary(query string, findings []Finding) string {
	if len(findings) == 0 {
		return "No findings produced for query: " + query
	}
	return fmt.Sprintf("Research on %q produced %d findings across multiple sources.", query, len(findings))
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-3] + "..."
}
