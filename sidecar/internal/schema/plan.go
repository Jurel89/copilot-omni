package schema

import (
	"fmt"
	"sort"
	"strings"
)

type PlanTask struct {
	ID              string   `json:"id"`
	Title           string   `json:"title"`
	Description     string   `json:"description"`
	Dependencies    []string `json:"dependencies"`
	FileTargets     []string `json:"file_targets"`
	VerificationCmd string   `json:"verification_cmd"`
	RollbackNote    string   `json:"rollback_note"`
}

type Plan struct {
	RunID   string     `json:"run_id"`
	Version string     `json:"version"`
	Tasks   []PlanTask `json:"tasks"`
}

type ValidationError struct {
	Code     string
	Messages []string
}

func (e *ValidationError) Error() string {
	if e == nil {
		return ""
	}

	return fmt.Sprintf("%s: %s", e.Code, strings.Join(e.Messages, "; "))
}

func ValidatePlan(plan map[string]interface{}) ([]string, error) {
	warnings := make([]string, 0)
	errors := make([]string, 0)

	if len(plan) == 0 {
		errors = append(errors, "plan payload must not be empty")
		return warnings, &ValidationError{Code: "invalid_plan", Messages: errors}
	}

	runID, ok := getRequiredString(plan, "run_id")
	if !ok {
		errors = append(errors, "run_id must be a non-empty string")
	}

	if _, ok := getRequiredString(plan, "version"); !ok {
		errors = append(errors, "version must be a non-empty string")
	}

	rawTasks, ok := plan["tasks"].([]interface{})
	if !ok || len(rawTasks) == 0 {
		errors = append(errors, "tasks must be a non-empty array")
		return warnings, finalizeValidation(errors)
	}

	knownTaskIDs := make(map[string]struct{}, len(rawTasks))
	dependenciesByTask := make(map[string][]string, len(rawTasks))

	for index, rawTask := range rawTasks {
		taskMap, ok := rawTask.(map[string]interface{})
		if !ok {
			errors = append(errors, fmt.Sprintf("tasks[%d] must be an object", index))
			continue
		}

		taskID, ok := getRequiredString(taskMap, "id")
		if !ok {
			errors = append(errors, fmt.Sprintf("tasks[%d].id must be a non-empty string", index))
		} else {
			if _, exists := knownTaskIDs[taskID]; exists {
				errors = append(errors, fmt.Sprintf("tasks[%d].id %q is duplicated", index, taskID))
			} else {
				knownTaskIDs[taskID] = struct{}{}
			}
		}

		if _, ok := getRequiredString(taskMap, "title"); !ok {
			errors = append(errors, fmt.Sprintf("tasks[%d].title must be a non-empty string", index))
		}

		fileTargets, ok := getStringSlice(taskMap, "file_targets")
		if !ok || len(fileTargets) == 0 {
			errors = append(errors, fmt.Sprintf("tasks[%d].file_targets must be a non-empty array of strings", index))
		}

		if _, ok := getRequiredString(taskMap, "verification_cmd"); !ok {
			errors = append(errors, fmt.Sprintf("tasks[%d].verification_cmd must be a non-empty string", index))
		}

		dependencies, ok := getOptionalStringSlice(taskMap, "dependencies")
		if !ok {
			errors = append(errors, fmt.Sprintf("tasks[%d].dependencies must be an array of strings", index))
		} else if taskID != "" {
			dependenciesByTask[taskID] = dependencies
		}

		if description, ok := getOptionalString(taskMap, "description"); !ok {
			errors = append(errors, fmt.Sprintf("tasks[%d].description must be a string", index))
		} else if strings.TrimSpace(description) == "" {
			warnings = append(warnings, fmt.Sprintf("task %q has an empty description", taskIDOrFallback(taskID, index)))
		}

		if rollbackNote, ok := getOptionalString(taskMap, "rollback_note"); !ok {
			errors = append(errors, fmt.Sprintf("tasks[%d].rollback_note must be a string", index))
		} else if strings.TrimSpace(rollbackNote) == "" {
			errors = append(errors, fmt.Sprintf("tasks[%d].rollback_note must be a non-empty string", index))
		}
	}

	for taskID, dependencies := range dependenciesByTask {
		for _, dependencyID := range dependencies {
			if _, ok := knownTaskIDs[dependencyID]; !ok {
				errors = append(errors, fmt.Sprintf("task %q depends on unknown task %q", taskID, dependencyID))
			}
		}
	}

	if runID != "" && !strings.HasPrefix(runID, "run-") {
		warnings = append(warnings, "run_id does not use the expected run-<unix-timestamp> format")
	}

	sort.Strings(warnings)
	return warnings, finalizeValidation(errors)
}

func finalizeValidation(messages []string) error {
	if len(messages) == 0 {
		return nil
	}

	return &ValidationError{Code: "invalid_plan", Messages: messages}
}

func getRequiredString(values map[string]interface{}, key string) (string, bool) {
	value, ok := values[key].(string)
	if !ok || strings.TrimSpace(value) == "" {
		return "", false
	}
	return strings.TrimSpace(value), true
}

func getOptionalString(values map[string]interface{}, key string) (string, bool) {
	rawValue, exists := values[key]
	if !exists || rawValue == nil {
		return "", true
	}

	value, ok := rawValue.(string)
	if !ok {
		return "", false
	}

	return value, true
}

func getStringSlice(values map[string]interface{}, key string) ([]string, bool) {
	items, ok := getOptionalStringSlice(values, key)
	if !ok {
		return nil, false
	}

	trimmed := make([]string, 0, len(items))
	for _, item := range items {
		item = strings.TrimSpace(item)
		if item == "" {
			continue
		}
		trimmed = append(trimmed, item)
	}

	return trimmed, true
}

func getOptionalStringSlice(values map[string]interface{}, key string) ([]string, bool) {
	rawValue, exists := values[key]
	if !exists || rawValue == nil {
		return nil, true
	}

	rawItems, ok := rawValue.([]interface{})
	if !ok {
		return nil, false
	}

	items := make([]string, 0, len(rawItems))
	for _, rawItem := range rawItems {
		value, ok := rawItem.(string)
		if !ok {
			return nil, false
		}
		items = append(items, value)
	}

	return items, true
}

func taskIDOrFallback(taskID string, index int) string {
	if strings.TrimSpace(taskID) != "" {
		return taskID
	}

	return fmt.Sprintf("tasks[%d]", index)
}
