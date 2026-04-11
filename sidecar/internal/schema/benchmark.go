package schema

import (
	"fmt"
	"maps"
	"strings"
)

type BenchmarkReport struct {
	GeneratedAt string            `json:"generated_at"`
	Summary     BenchmarkSummary  `json:"summary"`
	Results     []BenchmarkResult `json:"results"`
	Budgets     BudgetSet         `json:"budgets"`
}

type BenchmarkSummary struct {
	TotalBenchmarks int `json:"total_benchmarks"`
	Passed          int `json:"passed"`
	Warned          int `json:"warned"`
	Failed          int `json:"failed"`
	TotalDurationMS int `json:"total_duration_ms"`
}

type BenchmarkResult struct {
	Name        string            `json:"name"`
	Description string            `json:"description"`
	StartTime   string            `json:"start_time"`
	EndTime     string            `json:"end_time"`
	DurationMS  int               `json:"duration_ms"`
	Iterations  int               `json:"iterations"`
	Metrics     map[string]Metric `json:"metrics"`
	Status      string            `json:"status"`
	Errors      []string          `json:"errors,omitempty"`
	Metadata    map[string]string `json:"metadata,omitempty"`
}

type Metric struct {
	Name   string    `json:"name"`
	Unit   string    `json:"unit"`
	Values []float64 `json:"values,omitempty"`
	Min    float64   `json:"min"`
	Max    float64   `json:"max"`
	Mean   float64   `json:"mean"`
	P50    float64   `json:"p50"`
	P95    float64   `json:"p95"`
	P99    float64   `json:"p99"`
	StdDev float64   `json:"stddev"`
	Budget int       `json:"budget,omitempty"`
	Status string    `json:"status"`
}

type BudgetSet struct {
	ColdStartP95MS    int `json:"cold_start_p95_ms"`
	MemorySearchP95MS int `json:"memory_search_p95_ms"`
	PolicyCheckP95MS  int `json:"policy_check_p95_ms"`
	ArtifactLoadP95MS int `json:"artifact_load_p95_ms"`
	PlanParseP95MS    int `json:"plan_parse_p95_ms"`
	VerificationP95MS int `json:"verification_p95_ms"`
}

func ValidateBenchmarkReport(report map[string]any) ([]string, error) {
	warnings := make([]string, 0)
	validationErrors := make([]string, 0)

	if len(report) == 0 {
		validationErrors = append(validationErrors, "benchmark report payload must not be empty")
		return warnings, &ValidationError{Code: "invalid_benchmark_report", Messages: validationErrors}
	}

	if _, ok := getOptionalString(report, "generated_at"); !ok {
		warnings = append(warnings, "generated_at should be a string when provided")
	} else if strings.TrimSpace(reportStringValue(report, "generated_at")) == "" {
		warnings = append(warnings, "generated_at is missing")
	}

	totalBenchmarks := -1
	passedCount := -1
	warnedCount := -1
	failedCount := -1

	rawSummary, ok := report["summary"].(map[string]any)
	if !ok {
		validationErrors = append(validationErrors, "summary must be an object")
	} else {
		if value, ok := getInt(rawSummary, "total_benchmarks"); !ok {
			validationErrors = append(validationErrors, "summary.total_benchmarks must be an integer")
		} else {
			totalBenchmarks = value
			if value < 0 {
				validationErrors = append(validationErrors, "summary.total_benchmarks must be zero or greater")
			}
		}

		if value, ok := getInt(rawSummary, "passed"); !ok {
			validationErrors = append(validationErrors, "summary.passed must be an integer")
		} else {
			passedCount = value
			if value < 0 {
				validationErrors = append(validationErrors, "summary.passed must be zero or greater")
			}
		}

		if value, ok := getInt(rawSummary, "warned"); !ok {
			validationErrors = append(validationErrors, "summary.warned must be an integer")
		} else {
			warnedCount = value
			if value < 0 {
				validationErrors = append(validationErrors, "summary.warned must be zero or greater")
			}
		}

		if value, ok := getInt(rawSummary, "failed"); !ok {
			validationErrors = append(validationErrors, "summary.failed must be an integer")
		} else {
			failedCount = value
			if value < 0 {
				validationErrors = append(validationErrors, "summary.failed must be zero or greater")
			}
		}

		if value, ok := getInt(rawSummary, "total_duration_ms"); !ok {
			validationErrors = append(validationErrors, "summary.total_duration_ms must be an integer")
		} else if value < 0 {
			validationErrors = append(validationErrors, "summary.total_duration_ms must be zero or greater")
		}
	}

	rawResults, ok := report["results"].([]interface{})
	if !ok {
		validationErrors = append(validationErrors, "results must be an array")
	}

	rawBudgets, ok := report["budgets"].(map[string]any)
	if !ok {
		validationErrors = append(validationErrors, "budgets must be an object")
	} else {
		validationErrors = append(validationErrors, validateBudgetSet(rawBudgets)...)
	}

	statusCounts := map[string]int{"pass": 0, "warn": 0, "fail": 0}

	for index, rawResult := range rawResults {
		result, ok := rawResult.(map[string]any)
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d] must be an object", index))
			continue
		}

		resultName, ok := getRequiredString(result, "name")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].name must be a non-empty string", index))
		}

		if description, ok := getOptionalString(result, "description"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].description must be a string", index))
		} else if strings.TrimSpace(description) == "" {
			warnings = append(warnings, fmt.Sprintf("benchmark result %q has an empty description", resultNameOrFallback(resultName, index)))
		}

		if _, ok := getOptionalString(result, "start_time"); !ok {
			warnings = append(warnings, fmt.Sprintf("results[%d].start_time should be a string when provided", index))
		} else if strings.TrimSpace(reportStringValue(result, "start_time")) == "" {
			warnings = append(warnings, fmt.Sprintf("results[%d].start_time is missing", index))
		}

		if _, ok := getOptionalString(result, "end_time"); !ok {
			warnings = append(warnings, fmt.Sprintf("results[%d].end_time should be a string when provided", index))
		} else if strings.TrimSpace(reportStringValue(result, "end_time")) == "" {
			warnings = append(warnings, fmt.Sprintf("results[%d].end_time is missing", index))
		}

		if value, ok := getInt(result, "duration_ms"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].duration_ms must be an integer", index))
		} else if value < 0 {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].duration_ms must be zero or greater", index))
		}

		if value, ok := getInt(result, "iterations"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].iterations must be an integer", index))
		} else if value <= 0 {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].iterations must be greater than zero", index))
		}

		status, ok := getRequiredString(result, "status")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].status must be a non-empty string", index))
		} else if status != "pass" && status != "warn" && status != "fail" {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].status must be one of: pass, warn, fail", index))
		} else {
			statusCounts[status]++
		}

		rawMetrics, hasMetrics := result["metrics"]
		if !hasMetrics || rawMetrics == nil {
			if status == "pass" || status == "warn" {
				warnings = append(warnings, fmt.Sprintf("results[%d].metrics is missing", index))
			}
		} else {
			metrics, ok := rawMetrics.(map[string]any)
			if !ok {
				validationErrors = append(validationErrors, fmt.Sprintf("results[%d].metrics must be an object", index))
			} else {
				if len(metrics) == 0 && (status == "pass" || status == "warn") {
					warnings = append(warnings, fmt.Sprintf("results[%d].metrics is empty", index))
				}
				for metricName, rawMetric := range metrics {
					metric, ok := rawMetric.(map[string]any)
					if !ok {
						validationErrors = append(validationErrors, fmt.Sprintf("results[%d].metrics[%q] must be an object", index, metricName))
						continue
					}

					metricWarnings, metricErrors := validateMetric(resultNameOrFallback(resultName, index), metricName, metric)
					warnings = append(warnings, metricWarnings...)
					validationErrors = append(validationErrors, metricErrors...)
				}
			}
		}

		if _, ok := getOptionalStringSlice(result, "errors"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].errors must be an array of strings", index))
		}

		if _, ok := getOptionalStringMap(result, "metadata"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("results[%d].metadata must be an object of strings", index))
		}
	}

	if totalBenchmarks >= 0 && len(rawResults) > 0 && totalBenchmarks != len(rawResults) {
		validationErrors = append(validationErrors, "summary.total_benchmarks must match the number of results")
	}

	if totalBenchmarks >= 0 && passedCount >= 0 && warnedCount >= 0 && failedCount >= 0 {
		if totalBenchmarks != passedCount+warnedCount+failedCount {
			validationErrors = append(validationErrors, "summary counts must add up to summary.total_benchmarks")
		}
		if len(rawResults) > 0 && passedCount != statusCounts["pass"] {
			validationErrors = append(validationErrors, "summary.passed must match the number of passing results")
		}
		if len(rawResults) > 0 && warnedCount != statusCounts["warn"] {
			validationErrors = append(validationErrors, "summary.warned must match the number of warning results")
		}
		if len(rawResults) > 0 && failedCount != statusCounts["fail"] {
			validationErrors = append(validationErrors, "summary.failed must match the number of failing results")
		}
	}

	return warnings, finalizeArtifactValidation("invalid_benchmark_report", validationErrors)
}

func validateBudgetSet(budgets map[string]any) []string {
	validationErrors := make([]string, 0)

	requiredFields := []string{
		"cold_start_p95_ms",
		"memory_search_p95_ms",
		"policy_check_p95_ms",
		"artifact_load_p95_ms",
		"plan_parse_p95_ms",
		"verification_p95_ms",
	}

	for _, field := range requiredFields {
		value, ok := getInt(budgets, field)
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("budgets.%s must be an integer", field))
			continue
		}
		if value <= 0 {
			validationErrors = append(validationErrors, fmt.Sprintf("budgets.%s must be greater than zero", field))
		}
	}

	return validationErrors
}

func validateMetric(resultName string, metricKey string, metric map[string]any) ([]string, []string) {
	warnings := make([]string, 0)
	validationErrors := make([]string, 0)
	prefix := fmt.Sprintf("metric %q on result %q", metricKey, resultName)

	metricName, ok := getRequiredString(metric, "name")
	if !ok {
		validationErrors = append(validationErrors, fmt.Sprintf("%s must include a non-empty name", prefix))
	} else if metricName != metricKey {
		warnings = append(warnings, fmt.Sprintf("%s name %q does not match metric key %q", prefix, metricName, metricKey))
	}

	if _, ok := getRequiredString(metric, "unit"); !ok {
		validationErrors = append(validationErrors, fmt.Sprintf("%s must include a non-empty unit", prefix))
	}

	min, ok := getFloat64(metric, "min")
	if !ok {
		validationErrors = append(validationErrors, fmt.Sprintf("%s.min must be a number", prefix))
	}

	max, ok := getFloat64(metric, "max")
	if !ok {
		validationErrors = append(validationErrors, fmt.Sprintf("%s.max must be a number", prefix))
	}

	mean, ok := getFloat64(metric, "mean")
	if !ok {
		validationErrors = append(validationErrors, fmt.Sprintf("%s.mean must be a number", prefix))
	}

	p50, ok := getFloat64(metric, "p50")
	if !ok {
		validationErrors = append(validationErrors, fmt.Sprintf("%s.p50 must be a number", prefix))
	}

	p95, ok := getFloat64(metric, "p95")
	if !ok {
		validationErrors = append(validationErrors, fmt.Sprintf("%s.p95 must be a number", prefix))
	}

	p99, ok := getFloat64(metric, "p99")
	if !ok {
		validationErrors = append(validationErrors, fmt.Sprintf("%s.p99 must be a number", prefix))
	}

	if _, ok := getFloat64(metric, "stddev"); !ok {
		validationErrors = append(validationErrors, fmt.Sprintf("%s.stddev must be a number", prefix))
	}

	if values, ok := getOptionalFloat64Slice(metric, "values"); !ok {
		validationErrors = append(validationErrors, fmt.Sprintf("%s.values must be an array of numbers", prefix))
	} else if len(values) == 0 {
		warnings = append(warnings, fmt.Sprintf("%s.values is empty", prefix))
	}

	if budget, ok := getInt(metric, "budget"); ok {
		if budget < 0 {
			validationErrors = append(validationErrors, fmt.Sprintf("%s.budget must be zero or greater", prefix))
		}
	}

	status, ok := getRequiredString(metric, "status")
	if !ok {
		validationErrors = append(validationErrors, fmt.Sprintf("%s must include a non-empty status", prefix))
	} else if status != "pass" && status != "warn" && status != "fail" {
		validationErrors = append(validationErrors, fmt.Sprintf("%s.status must be one of: pass, warn, fail", prefix))
	}

	if min > max {
		validationErrors = append(validationErrors, fmt.Sprintf("%s.min must be less than or equal to %s.max", prefix, prefix))
	}
	if p50 > p95 {
		validationErrors = append(validationErrors, fmt.Sprintf("%s.p50 must be less than or equal to %s.p95", prefix, prefix))
	}
	if p95 > p99 {
		validationErrors = append(validationErrors, fmt.Sprintf("%s.p95 must be less than or equal to %s.p99", prefix, prefix))
	}
	if mean < min || mean > max {
		warnings = append(warnings, fmt.Sprintf("%s.mean is outside the min/max range", prefix))
	}

	return warnings, validationErrors
}

func finalizeArtifactValidation(code string, messages []string) error {
	if len(messages) == 0 {
		return nil
	}

	return &ValidationError{Code: code, Messages: messages}
}

func getFloat64(values map[string]any, key string) (float64, bool) {
	rawValue, exists := values[key]
	if !exists || rawValue == nil {
		return 0, false
	}

	switch value := rawValue.(type) {
	case float64:
		return value, true
	case float32:
		return float64(value), true
	case int:
		return float64(value), true
	case int8:
		return float64(value), true
	case int16:
		return float64(value), true
	case int32:
		return float64(value), true
	case int64:
		return float64(value), true
	default:
		return 0, false
	}
}

func getOptionalFloat64Slice(values map[string]any, key string) ([]float64, bool) {
	rawValue, exists := values[key]
	if !exists || rawValue == nil {
		return nil, true
	}

	rawItems, ok := rawValue.([]interface{})
	if !ok {
		return nil, false
	}

	items := make([]float64, 0, len(rawItems))
	for _, rawItem := range rawItems {
		switch value := rawItem.(type) {
		case float64:
			items = append(items, value)
		case float32:
			items = append(items, float64(value))
		case int:
			items = append(items, float64(value))
		case int8:
			items = append(items, float64(value))
		case int16:
			items = append(items, float64(value))
		case int32:
			items = append(items, float64(value))
		case int64:
			items = append(items, float64(value))
		default:
			return nil, false
		}
	}

	return items, true
}

func getRequiredBool(values map[string]any, key string) (bool, bool) {
	rawValue, exists := values[key]
	if !exists || rawValue == nil {
		return false, false
	}

	value, ok := rawValue.(bool)
	if !ok {
		return false, false
	}

	return value, true
}

func getOptionalStringMap(values map[string]any, key string) (map[string]string, bool) {
	rawValue, exists := values[key]
	if !exists || rawValue == nil {
		return nil, true
	}

	switch typed := rawValue.(type) {
	case map[string]string:
		result := make(map[string]string, len(typed))
		maps.Copy(result, typed)
		return result, true
	case map[string]any:
		result := make(map[string]string, len(typed))
		for k, rawItem := range typed {
			value, ok := rawItem.(string)
			if !ok {
				return nil, false
			}
			result[k] = value
		}
		return result, true
	default:
		return nil, false
	}
}

func resultNameOrFallback(name string, index int) string {
	if strings.TrimSpace(name) != "" {
		return name
	}

	return fmt.Sprintf("results[%d]", index)
}
