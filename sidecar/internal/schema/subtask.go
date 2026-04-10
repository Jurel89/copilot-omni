package schema

import (
	"fmt"
	"strings"
)

type SubtaskManifest struct {
	RunID      string       `json:"run_id"`
	ParentTask string       `json:"parent_task"`
	Subtasks   []SubtaskDef `json:"subtasks"`
}

type SubtaskDef struct {
	ID              string   `json:"id"`
	Title           string   `json:"title"`
	Description     string   `json:"description"`
	Mode            string   `json:"mode"` // "read_only" or "write"
	Dependencies    []string `json:"dependencies"`
	FileTargets     []string `json:"file_targets,omitempty"`
	VerificationCmd string   `json:"verification_cmd,omitempty"`
	OutputContract  string   `json:"output_contract,omitempty"`
}

func ValidateSubtaskManifest(manifest map[string]interface{}) ([]string, error) {
	warnings := make([]string, 0)
	validationErrors := make([]string, 0)

	if len(manifest) == 0 {
		validationErrors = append(validationErrors, "subtask manifest payload must not be empty")
		return warnings, &ValidationError{Code: "invalid_subtask_manifest", Messages: validationErrors}
	}

	if _, ok := getRequiredString(manifest, "run_id"); !ok {
		validationErrors = append(validationErrors, "run_id must be a non-empty string")
	}

	if _, ok := getRequiredString(manifest, "parent_task"); !ok {
		validationErrors = append(validationErrors, "parent_task must be a non-empty string")
	}

	rawSubtasks, ok := manifest["subtasks"].([]interface{})
	if !ok || len(rawSubtasks) == 0 {
		validationErrors = append(validationErrors, "subtasks must be a non-empty array")
		return warnings, finalizeValidation(validationErrors)
	}

	knownIDs := make(map[string]struct{}, len(rawSubtasks))
	depGraph := make(map[string][]string, len(rawSubtasks))

	for i, raw := range rawSubtasks {
		sub, ok := raw.(map[string]interface{})
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("subtasks[%d] must be an object", i))
			continue
		}

		id, ok := getRequiredString(sub, "id")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("subtasks[%d].id must be a non-empty string", i))
		} else {
			if _, exists := knownIDs[id]; exists {
				validationErrors = append(validationErrors, fmt.Sprintf("subtasks[%d].id %q is duplicated", i, id))
			} else {
				knownIDs[id] = struct{}{}
			}
		}

		if _, ok := getRequiredString(sub, "title"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("subtasks[%d].title must be a non-empty string", i))
		}

		if desc, ok := getOptionalString(sub, "description"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("subtasks[%d].description must be a string", i))
		} else if strings.TrimSpace(desc) == "" {
			warnings = append(warnings, fmt.Sprintf("subtask %q has an empty description", id))
		}

		mode, ok := getRequiredString(sub, "mode")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("subtasks[%d].mode must be a non-empty string", i))
		} else if mode != "read_only" && mode != "write" {
			validationErrors = append(validationErrors, fmt.Sprintf("subtasks[%d].mode must be one of: read_only, write", i))
		}

		if mode == "write" {
			targets, ok := getStringSlice(sub, "file_targets")
			if !ok || len(targets) == 0 {
				validationErrors = append(validationErrors, fmt.Sprintf("subtasks[%d].file_targets is required for write mode", i))
			}
		}

		deps, ok := getOptionalStringSlice(sub, "dependencies")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("subtasks[%d].dependencies must be an array of strings", i))
		} else if id != "" {
			depGraph[id] = deps
		}
	}

	for taskID, deps := range depGraph {
		for _, depID := range deps {
			if _, ok := knownIDs[depID]; !ok {
				validationErrors = append(validationErrors, fmt.Sprintf("subtask %q depends on unknown subtask %q", taskID, depID))
			}
		}
	}

	if detectManifestCycle(depGraph) {
		validationErrors = append(validationErrors, "subtask dependency graph contains a cycle")
	}

	if len(validationErrors) > 0 {
		return warnings, &ValidationError{Code: "invalid_subtask_manifest", Messages: validationErrors}
	}

	return warnings, nil
}

func detectManifestCycle(depGraph map[string][]string) bool {
	const (
		stateWhite = 0
		stateGray  = 1
		stateBlack = 2
	)

	states := make(map[string]int, len(depGraph))
	for id := range depGraph {
		states[id] = stateWhite
	}

	var visit func(id string) bool
	visit = func(id string) bool {
		states[id] = stateGray
		for _, dep := range depGraph[id] {
			switch states[dep] {
			case stateGray:
				return true
			case stateWhite:
				if visit(dep) {
					return true
				}
			}
		}
		states[id] = stateBlack
		return false
	}

	for id, state := range states {
		if state == stateWhite {
			if visit(id) {
				return true
			}
		}
	}
	return false
}
