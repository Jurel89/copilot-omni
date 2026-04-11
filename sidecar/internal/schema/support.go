package schema

import (
	"fmt"
	"strings"
)

type SupportBundle struct {
	Version        string          `json:"version"`
	BundleID       string          `json:"bundle_id"`
	GeneratedAt    string          `json:"generated_at"`
	RunID          string          `json:"run_id,omitempty"`
	Items          []BundleItem    `json:"items"`
	RedactionRules []RedactionRule `json:"redaction_rules"`
}

type BundleItem struct {
	Path      string `json:"path"`
	Category  string `json:"category"`
	SizeBytes int    `json:"size_bytes"`
	SHA256    string `json:"sha256,omitempty"`
	Redacted  bool   `json:"redacted"`
}

type RedactionRule struct {
	Name         string `json:"name"`
	Pattern      string `json:"pattern"`
	Replacement  string `json:"replacement"`
	AppliedCount int    `json:"applied_count"`
}

func ValidateSupportBundle(bundle map[string]any) ([]string, error) {
	warnings := make([]string, 0)
	validationErrors := make([]string, 0)

	if len(bundle) == 0 {
		validationErrors = append(validationErrors, "support bundle payload must not be empty")
		return warnings, &ValidationError{Code: "invalid_support_bundle", Messages: validationErrors}
	}

	if _, ok := getRequiredString(bundle, "version"); !ok {
		validationErrors = append(validationErrors, "version must be a non-empty string")
	}

	if _, ok := getRequiredString(bundle, "bundle_id"); !ok {
		validationErrors = append(validationErrors, "bundle_id must be a non-empty string")
	}

	if _, ok := getOptionalString(bundle, "generated_at"); !ok {
		warnings = append(warnings, "generated_at should be a string when provided")
	} else if strings.TrimSpace(reportStringValue(bundle, "generated_at")) == "" {
		warnings = append(warnings, "generated_at is missing")
	}

	if _, ok := getOptionalString(bundle, "run_id"); !ok {
		validationErrors = append(validationErrors, "run_id must be a string")
	}

	rawItems, ok := bundle["items"].([]interface{})
	if !ok || len(rawItems) == 0 {
		validationErrors = append(validationErrors, "items must be a non-empty array")
	}

	rawRules, ok := bundle["redaction_rules"].([]interface{})
	if !ok {
		validationErrors = append(validationErrors, "redaction_rules must be an array")
	}

	itemPaths := make(map[string]struct{}, len(rawItems))
	hasRedactedItems := false

	for index, rawItem := range rawItems {
		item, ok := rawItem.(map[string]any)
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("items[%d] must be an object", index))
			continue
		}

		path, ok := getRequiredString(item, "path")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("items[%d].path must be a non-empty string", index))
		} else {
			if _, exists := itemPaths[path]; exists {
				validationErrors = append(validationErrors, fmt.Sprintf("items[%d].path %q is duplicated", index, path))
			} else {
				itemPaths[path] = struct{}{}
			}
			if strings.HasPrefix(path, "/") || strings.Contains(path, "..") {
				validationErrors = append(validationErrors, fmt.Sprintf("items[%d].path must stay within the support bundle", index))
			}
		}

		if _, ok := getRequiredString(item, "category"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("items[%d].category must be a non-empty string", index))
		}

		if sizeBytes, ok := getInt(item, "size_bytes"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("items[%d].size_bytes must be an integer", index))
		} else if sizeBytes < 0 {
			validationErrors = append(validationErrors, fmt.Sprintf("items[%d].size_bytes must be zero or greater", index))
		}

		if _, ok := getOptionalString(item, "sha256"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("items[%d].sha256 must be a string", index))
		}

		redacted, ok := getRequiredBool(item, "redacted")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("items[%d].redacted must be a boolean", index))
		} else if redacted {
			hasRedactedItems = true
		}
	}

	ruleNames := make(map[string]struct{}, len(rawRules))
	totalApplied := 0

	for index, rawRule := range rawRules {
		rule, ok := rawRule.(map[string]any)
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("redaction_rules[%d] must be an object", index))
			continue
		}

		ruleName, ok := getRequiredString(rule, "name")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("redaction_rules[%d].name must be a non-empty string", index))
		} else if _, exists := ruleNames[ruleName]; exists {
			validationErrors = append(validationErrors, fmt.Sprintf("redaction_rules[%d].name %q is duplicated", index, ruleName))
		} else {
			ruleNames[ruleName] = struct{}{}
		}

		if _, ok := getRequiredString(rule, "pattern"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("redaction_rules[%d].pattern must be a non-empty string", index))
		}

		if _, ok := getRequiredString(rule, "replacement"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("redaction_rules[%d].replacement must be a non-empty string", index))
		}

		if appliedCount, ok := getInt(rule, "applied_count"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("redaction_rules[%d].applied_count must be an integer", index))
		} else if appliedCount < 0 {
			validationErrors = append(validationErrors, fmt.Sprintf("redaction_rules[%d].applied_count must be zero or greater", index))
		} else {
			totalApplied += appliedCount
		}
	}

	if len(rawRules) == 0 {
		warnings = append(warnings, "redaction_rules is empty")
	}

	if hasRedactedItems && len(rawRules) == 0 {
		warnings = append(warnings, "bundle contains redacted items but no redaction rules")
	}

	if hasRedactedItems && totalApplied == 0 && len(rawRules) > 0 {
		warnings = append(warnings, "bundle contains redacted items but redaction_rules report zero applications")
	}

	return warnings, finalizeArtifactValidation("invalid_support_bundle", validationErrors)
}
