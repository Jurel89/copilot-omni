package schema

import "strings"

func ValidateDecisions(content string) ([]string, error) {
	trimmedContent := strings.TrimSpace(content)
	if trimmedContent == "" {
		return nil, &ValidationError{Code: "invalid_decisions", Messages: []string{"decision content must not be empty"}}
	}

	warnings := make([]string, 0)
	hasHeading := false
	for _, line := range strings.Split(trimmedContent, "\n") {
		if strings.HasPrefix(strings.TrimSpace(line), "#") {
			hasHeading = true
			break
		}
	}

	if !hasHeading {
		warnings = append(warnings, "decision artifact has no heading")
	}

	return warnings, nil
}
