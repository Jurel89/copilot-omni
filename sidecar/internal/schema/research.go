package schema

import (
	"fmt"
	"strings"
)

type ResearchReport struct {
	RunID         string               `json:"run_id"`
	Query         string               `json:"query"`
	Provenance    []ResearchProvenance `json:"provenance"`
	Findings      []ResearchFinding    `json:"findings"`
	OpenQuestions []string             `json:"open_questions,omitempty"`
	Summary       string               `json:"summary"`
	Timestamp     string               `json:"timestamp"`
}

type ResearchProvenance struct {
	Source string `json:"source"`
	Type   string `json:"type"`
	URL    string `json:"url,omitempty"`
	Query  string `json:"query,omitempty"`
}

type ResearchFinding struct {
	Title      string   `json:"title"`
	Content    string   `json:"content"`
	Category   string   `json:"category"`
	Confidence string   `json:"confidence"`
	Sources    []string `json:"sources,omitempty"`
}

func ValidateResearchReport(report map[string]interface{}) ([]string, error) {
	warnings := make([]string, 0)
	validationErrors := make([]string, 0)

	if len(report) == 0 {
		validationErrors = append(validationErrors, "research report payload must not be empty")
		return warnings, &ValidationError{Code: "invalid_research_report", Messages: validationErrors}
	}

	if _, ok := getRequiredString(report, "run_id"); !ok {
		validationErrors = append(validationErrors, "run_id must be a non-empty string")
	}

	if _, ok := getRequiredString(report, "query"); !ok {
		validationErrors = append(validationErrors, "query must be a non-empty string")
	}

	if _, ok := getRequiredString(report, "summary"); !ok {
		validationErrors = append(validationErrors, "summary must be a non-empty string")
	}

	if _, ok := getOptionalString(report, "timestamp"); !ok {
		warnings = append(warnings, "timestamp should be a string when provided")
	} else if strings.TrimSpace(reportStringValue(report, "timestamp")) == "" {
		warnings = append(warnings, "timestamp is missing")
	}

	rawProvenance, ok := report["provenance"].([]interface{})
	if !ok || len(rawProvenance) == 0 {
		warnings = append(warnings, "provenance is empty or missing; report should cite sources")
	} else {
		for i, raw := range rawProvenance {
			p, ok := raw.(map[string]interface{})
			if !ok {
				validationErrors = append(validationErrors, fmt.Sprintf("provenance[%d] must be an object", i))
				continue
			}
			if _, ok := getRequiredString(p, "source"); !ok {
				validationErrors = append(validationErrors, fmt.Sprintf("provenance[%d].source must be a non-empty string", i))
			}
			if _, ok := getRequiredString(p, "type"); !ok {
				validationErrors = append(validationErrors, fmt.Sprintf("provenance[%d].type must be a non-empty string", i))
			}
		}
	}

	rawFindings, ok := report["findings"].([]interface{})
	if !ok {
		warnings = append(warnings, "findings is missing or not an array")
	} else {
		for i, raw := range rawFindings {
			f, ok := raw.(map[string]interface{})
			if !ok {
				validationErrors = append(validationErrors, fmt.Sprintf("findings[%d] must be an object", i))
				continue
			}
			if _, ok := getRequiredString(f, "title"); !ok {
				validationErrors = append(validationErrors, fmt.Sprintf("findings[%d].title must be a non-empty string", i))
			}
			if _, ok := getRequiredString(f, "content"); !ok {
				validationErrors = append(validationErrors, fmt.Sprintf("findings[%d].content must be a non-empty string", i))
			}
			category, _ := getRequiredString(f, "category")
			if category != "fact" && category != "inference" && category != "open_question" {
				validationErrors = append(validationErrors, fmt.Sprintf("findings[%d].category must be one of: fact, inference, open_question", i))
			}
			confidence, _ := getRequiredString(f, "confidence")
			if confidence != "high" && confidence != "medium" && confidence != "low" {
				validationErrors = append(validationErrors, fmt.Sprintf("findings[%d].confidence must be one of: high, medium, low", i))
			}
		}
	}

	if len(validationErrors) > 0 {
		return warnings, &ValidationError{Code: "invalid_research_report", Messages: validationErrors}
	}

	return warnings, nil
}
