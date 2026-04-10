package schema

import "strings"

func ValidateSpec(content string) ([]string, error) {
	trimmedContent := strings.TrimSpace(content)
	if trimmedContent == "" {
		return nil, &ValidationError{Code: "invalid_spec", Messages: []string{"spec content must not be empty"}}
	}

	warnings := make([]string, 0)
	hasHeading := false
	hasRequiredSection := false
	nonEmptyLines := 0

	for _, line := range strings.Split(trimmedContent, "\n") {
		trimmedLine := strings.TrimSpace(line)
		if trimmedLine == "" {
			continue
		}

		nonEmptyLines++
		if strings.HasPrefix(trimmedLine, "#") {
			hasHeading = true
		}

		lowerLine := strings.ToLower(trimmedLine)
		if strings.Contains(lowerLine, "acceptance criteria") || strings.Contains(lowerLine, "requirements") {
			hasRequiredSection = true
		}
	}

	validationErrors := make([]string, 0)
	if !hasHeading {
		validationErrors = append(validationErrors, "spec must contain at least one heading")
	}
	if !hasRequiredSection {
		validationErrors = append(validationErrors, "spec must contain an Acceptance Criteria or Requirements section")
	}

	if nonEmptyLines < 3 {
		warnings = append(warnings, "spec content is very short")
	}

	if len(validationErrors) > 0 {
		return warnings, &ValidationError{Code: "invalid_spec", Messages: validationErrors}
	}

	return warnings, nil
}
