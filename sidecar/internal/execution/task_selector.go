package execution

import (
	"encoding/json"
	"fmt"
	"strings"
)

func ParsePlanTasks(plan map[string]interface{}) ([]TaskInfo, error) {
	if plan == nil {
		return nil, &Error{Code: reasonCodeNilPlan}
	}

	rawTasks, ok := plan["tasks"]
	if !ok {
		return nil, &Error{Code: reasonCodeMissingTasks}
	}

	payload, err := json.Marshal(rawTasks)
	if err != nil {
		return nil, &Error{Code: reasonCodeInvalidPlanTasks, Err: err}
	}

	var tasks []TaskInfo
	if err := json.Unmarshal(payload, &tasks); err != nil {
		return nil, &Error{Code: reasonCodeInvalidPlanTasks, Err: err}
	}

	state, err := readExecutionState(plan)
	if err != nil {
		return nil, err
	}

	for index := range tasks {
		task := &tasks[index]
		task.ID = strings.TrimSpace(task.ID)
		task.Title = strings.TrimSpace(task.Title)
		task.Description = strings.TrimSpace(task.Description)
		task.VerificationCmd = strings.TrimSpace(task.VerificationCmd)
		task.RollbackNote = strings.TrimSpace(task.RollbackNote)
		task.Dependencies = cloneTrimmedStrings(task.Dependencies)
		task.FileTargets = cloneTrimmedStrings(task.FileTargets)

		if task.ID == "" {
			return nil, &Error{Code: reasonCodeInvalidTask, Err: fmt.Errorf("tasks[%d].id must be a non-empty string", index)}
		}
		if task.Title == "" {
			return nil, &Error{Code: reasonCodeInvalidTask, TaskID: task.ID, Err: fmt.Errorf("title must be a non-empty string")}
		}
		if task.VerificationCmd == "" {
			return nil, &Error{Code: reasonCodeInvalidTask, TaskID: task.ID, Err: fmt.Errorf("verification_cmd must be a non-empty string")}
		}
		if task.RollbackNote == "" {
			return nil, &Error{Code: reasonCodeInvalidTask, TaskID: task.ID, Err: fmt.Errorf("rollback_note must be a non-empty string")}
		}

		task.Status = statusForTask(task.ID, state)
		if !isValidTaskStatus(task.Status) {
			return nil, &Error{Code: reasonCodeInvalidTaskStatus, TaskID: task.ID, Err: fmt.Errorf("status %q is not supported", task.Status)}
		}
	}

	if tasks == nil {
		return []TaskInfo{}, nil
	}

	return tasks, nil
}

func SelectReadyTasks(tasks []TaskInfo, completed map[string]bool) []*TaskInfo {
	ready := make([]*TaskInfo, 0)
	for index := range tasks {
		task := &tasks[index]
		if task.Status != taskStatusPending {
			continue
		}
		if isTaskReady(task, completed) {
			ready = append(ready, task)
		}
	}
	return ready
}

func ValidateTaskDependencies(tasks []TaskInfo) error {
	graph, err := BuildDependencyGraph(tasks)
	if err != nil {
		return err
	}

	cycle, err := DetectCycle(graph)
	if err != nil {
		return err
	}
	if len(cycle) > 0 {
		return &Error{Code: reasonCodeCyclicDependency, TaskID: strings.Join(cycle, " -> ")}
	}

	return nil
}

func isTaskReady(task *TaskInfo, completed map[string]bool) bool {
	if task == nil {
		return false
	}

	for _, dependencyID := range task.Dependencies {
		if !completed[dependencyID] {
			return false
		}
	}

	return true
}
