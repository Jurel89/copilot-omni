package schema

import (
	"fmt"
	"strings"
)

func ValidateVerificationReport(report map[string]interface{}) ([]string, error) {
	warnings := make([]string, 0)
	validationErrors := make([]string, 0)

	if len(report) == 0 {
		validationErrors = append(validationErrors, "verification report payload must not be empty")
		return warnings, &ValidationError{Code: "invalid_verification_report", Messages: validationErrors}
	}

	if _, ok := getRequiredString(report, "run_id"); !ok {
		validationErrors = append(validationErrors, "run_id must be a non-empty string")
	}

	status, ok := getRequiredString(report, "status")
	if !ok {
		validationErrors = append(validationErrors, "status must be a non-empty string")
	} else if status != "passed" && status != "failed" && status != "error" {
		validationErrors = append(validationErrors, "status must be one of: passed, failed, error")
	}

	rawResults, ok := report["results"].([]interface{})
	if !ok {
		validationErrors = append(validationErrors, "results must be an array")
		return warnings, &ValidationError{Code: "invalid_verification_report", Messages: validationErrors}
	}

	if _, ok := getOptionalString(report, "timestamp"); !ok {
		warnings = append(warnings, "timestamp should be a string when provided")
	} else if strings.TrimSpace(reportStringValue(report, "timestamp")) == "" {
		warnings = append(warnings, "timestamp is missing")
	}

	if _, ok := getOptionalString(report, "mode"); !ok {
		warnings = append(warnings, "mode should be a string when provided")
	} else if strings.TrimSpace(reportStringValue(report, "mode")) == "" {
		warnings = append(warnings, "mode is missing")
	}

	if _, exists := report["summary"]; !exists {
		warnings = append(warnings, "summary is missing")
	}

	for index, rawResult := range rawResults {
		result, ok := rawResult.(map[string]interface{})
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d] must be an object", index))
			continue
		}

		if _, ok := getRequiredString(result, "command"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].command must be a non-empty string", index))
		}

		if _, ok := getInt(result, "exit_code"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].exit_code must be an integer", index))
		}

		resultStatus, ok := getRequiredString(result, "status")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].status must be a non-empty string", index))
		} else if resultStatus != "pass" && resultStatus != "fail" {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].status must be one of: pass, fail", index))
		}

		if _, ok := getOptionalString(result, "task_id"); !ok {
			warnings = append(warnings, fmt.Sprintf("results[%d].task_id should be a string when provided", index))
		}
		if _, ok := getOptionalString(result, "stdout_path"); !ok {
			warnings = append(warnings, fmt.Sprintf("results[%d].stdout_path should be a string when provided", index))
		}
		if _, ok := getOptionalString(result, "stderr_path"); !ok {
			warnings = append(warnings, fmt.Sprintf("results[%d].stderr_path should be a string when provided", index))
		}
		if _, ok := getInt(result, "duration_ms"); !ok {
			warnings = append(warnings, fmt.Sprintf("results[%d].duration_ms is missing or not an integer", index))
		}
	}

	if len(validationErrors) > 0 {
		return warnings, &ValidationError{Code: "invalid_verification_report", Messages: validationErrors}
	}

	return warnings, nil
}

func reportStringValue(values map[string]interface{}, key string) string {
	value, ok := values[key].(string)
	if !ok {
		return ""
	}

	return value
}

func getInt(values map[string]interface{}, key string) (int, bool) {
	rawValue, exists := values[key]
	if !exists || rawValue == nil {
		return 0, false
	}

	switch value := rawValue.(type) {
	case int:
		return value, true
	case int8:
		return int(value), true
	case int16:
		return int(value), true
	case int32:
		return int(value), true
	case int64:
		return int(value), true
	case float64:
		if float64(int(value)) != value {
			return 0, false
		}
		return int(value), true
	case float32:
		if float32(int(value)) != value {
			return 0, false
		}
		return int(value), true
	default:
		return 0, false
	}
}
