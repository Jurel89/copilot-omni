package execution

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/copilot-omni/sidecar/internal/artifact"
	"github.com/copilot-omni/sidecar/internal/config"
	runpkg "github.com/copilot-omni/sidecar/internal/run"
)

const (
	taskStatusPending    = "pending"
	taskStatusInProgress = "in_progress"
	taskStatusCompleted  = "completed"
	taskStatusFailed     = "failed"

	reasonCodeNilStore          = "nil_store"
	reasonCodeNilPlan           = "nil_plan"
	reasonCodeMissingTasks      = "missing_tasks"
	reasonCodeInvalidPlanTasks  = "invalid_plan_tasks"
	reasonCodeInvalidTask       = "invalid_task"
	reasonCodeInvalidTaskStatus = "invalid_task_status"
	reasonCodeDuplicateTaskID   = "duplicate_task_id"
	reasonCodeUnknownTaskRef    = "unknown_task_ref"
	reasonCodeCyclicDependency  = "cyclic_dependency"
	reasonCodeTaskNotFound      = "task_not_found"
	reasonCodeTaskNotReady      = "task_not_ready"
	reasonCodeTaskNotInProgress = "task_not_in_progress"
	reasonCodeInvalidTaskResult = "invalid_task_result"
	reasonCodeInvalidRunStatus  = "invalid_run_status"
	reasonCodeDeniedCommand     = "denied_command"
	reasonCodeTopologicalSort   = "topological_sort_failed"

	executionStateKey = "execution"
)

type TaskInfo struct {
	ID              string   `json:"id"`
	Title           string   `json:"title"`
	Description     string   `json:"description"`
	Dependencies    []string `json:"dependencies"`
	FileTargets     []string `json:"file_targets"`
	VerificationCmd string   `json:"verification_cmd"`
	RollbackNote    string   `json:"rollback_note"`
	Status          string   `json:"status"`
}

type TaskResult struct {
	TaskID        string   `json:"task_id"`
	Status        string   `json:"status"`
	FilesModified []string `json:"files_modified,omitempty"`
	Output        string   `json:"output,omitempty"`
	Error         string   `json:"error,omitempty"`
	DurationMs    int64    `json:"duration_ms,omitempty"`
}

type Error struct {
	Code         string
	RunID        string
	TaskID       string
	DependencyID string
	Err          error
}

func (e *Error) Error() string {
	if e == nil {
		return ""
	}

	parts := []string{e.Code}
	if e.RunID != "" {
		parts = append(parts, "run="+e.RunID)
	}
	if e.TaskID != "" {
		parts = append(parts, "task="+e.TaskID)
	}
	if e.DependencyID != "" {
		parts = append(parts, "dependency="+e.DependencyID)
	}
	if e.Err != nil {
		parts = append(parts, e.Err.Error())
	}

	return strings.Join(parts, ": ")
}

func (e *Error) Unwrap() error {
	if e == nil {
		return nil
	}

	return e.Err
}

type Executor struct {
	store          *artifact.Store
	configResolver func(string) (*config.Config, error)
}

type executionState struct {
	TaskStatuses map[string]string     `json:"task_statuses,omitempty"`
	TaskResults  map[string]TaskResult `json:"task_results,omitempty"`
}

func NewExecutor(store *artifact.Store, configResolver func(string) (*config.Config, error)) *Executor {
	return &Executor{store: store, configResolver: configResolver}
}

func (e *Executor) SelectNextTask(runID string) (*TaskInfo, error) {
	_, runObj, tasks, _, err := e.loadExecutionContext(runID)
	if err != nil {
		return nil, err
	}

	if err := ValidateTaskDependencies(tasks); err != nil {
		return nil, err
	}

	resolvedConfig, err := validateResolvedConfig(e.configResolver, runObj)
	if err != nil {
		return nil, err
	}

	completed := completedTaskSet(tasks)
	readyTasks := SelectReadyTasks(tasks, completed)
	if len(readyTasks) == 0 {
		return nil, nil
	}

	graph, err := BuildDependencyGraph(tasks)
	if err != nil {
		return nil, err
	}

	orderedTaskIDs, err := TopologicalSort(graph)
	if err != nil {
		return nil, err
	}

	readyByID := make(map[string]*TaskInfo, len(readyTasks))
	for _, task := range readyTasks {
		readyByID[task.ID] = task
	}

	for _, taskID := range orderedTaskIDs {
		task, ok := readyByID[taskID]
		if !ok {
			continue
		}

		if err := validateTaskPolicy(*task, resolvedConfig); err != nil {
			return nil, err
		}

		selected := *task
		return &selected, nil
	}

	return nil, &Error{Code: reasonCodeTopologicalSort, RunID: runID, Err: fmt.Errorf("no ready task found in sorted task list")}
}

func (e *Executor) MarkTaskStarted(runID, taskID string) error {
	plan, runObj, tasks, state, err := e.loadExecutionContext(runID)
	if err != nil {
		return err
	}

	if err := ValidateTaskDependencies(tasks); err != nil {
		return err
	}

	task, err := findTask(tasks, taskID)
	if err != nil {
		return err
	}

	if task.Status != taskStatusPending {
		return &Error{Code: reasonCodeTaskNotReady, RunID: runID, TaskID: taskID, Err: fmt.Errorf("task status is %q", task.Status)}
	}

	completed := completedTaskSet(tasks)
	if !isTaskReady(task, completed) {
		return &Error{Code: reasonCodeTaskNotReady, RunID: runID, TaskID: taskID, Err: fmt.Errorf("dependencies are not satisfied")}
	}

	state.TaskStatuses[taskID] = taskStatusInProgress
	writeExecutionState(plan, state)
	if err := e.store.WritePlan(runID, plan); err != nil {
		return err
	}

	if err := updateRunForTaskStart(runObj, taskID); err != nil {
		return err
	}

	return e.store.WriteRun(runObj)
}

func (e *Executor) MarkTaskCompleted(runID, taskID string, result TaskResult) error {
	plan, runObj, tasks, state, err := e.loadExecutionContext(runID)
	if err != nil {
		return err
	}

	if err := ValidateTaskDependencies(tasks); err != nil {
		return err
	}

	task, err := findTask(tasks, taskID)
	if err != nil {
		return err
	}

	if task.Status != taskStatusInProgress {
		return &Error{Code: reasonCodeTaskNotInProgress, RunID: runID, TaskID: taskID, Err: fmt.Errorf("task status is %q", task.Status)}
	}

	normalizedResult, err := normalizeTaskResult(taskID, result, taskStatusCompleted)
	if err != nil {
		return err
	}

	state.TaskStatuses[taskID] = taskStatusCompleted
	state.TaskResults[taskID] = normalizedResult
	writeExecutionState(plan, state)
	if err := e.store.WritePlan(runID, plan); err != nil {
		return err
	}

	allDone := allTasksCompleted(tasks, state)
	if err := updateRunForTaskCompletion(runObj, taskID, allDone); err != nil {
		return err
	}

	return e.store.WriteRun(runObj)
}

func (e *Executor) MarkTaskFailed(runID, taskID string, result TaskResult) error {
	plan, runObj, tasks, state, err := e.loadExecutionContext(runID)
	if err != nil {
		return err
	}

	if err := ValidateTaskDependencies(tasks); err != nil {
		return err
	}

	task, err := findTask(tasks, taskID)
	if err != nil {
		return err
	}

	if task.Status != taskStatusInProgress {
		return &Error{Code: reasonCodeTaskNotInProgress, RunID: runID, TaskID: taskID, Err: fmt.Errorf("task status is %q", task.Status)}
	}

	normalizedResult, err := normalizeTaskResult(taskID, result, taskStatusFailed)
	if err != nil {
		return err
	}

	state.TaskStatuses[taskID] = taskStatusFailed
	state.TaskResults[taskID] = normalizedResult
	writeExecutionState(plan, state)
	if err := e.store.WritePlan(runID, plan); err != nil {
		return err
	}

	if err := updateRunForTaskFailure(runObj, taskID, normalizedResult); err != nil {
		return err
	}

	return e.store.WriteRun(runObj)
}

func (e *Executor) loadExecutionContext(runID string) (map[string]interface{}, *runpkg.Run, []TaskInfo, executionState, error) {
	if e == nil || e.store == nil {
		return nil, nil, nil, executionState{}, &Error{Code: reasonCodeNilStore, RunID: runID}
	}

	runObj, err := e.store.ReadRun(runID)
	if err != nil {
		return nil, nil, nil, executionState{}, err
	}

	plan, err := e.store.ReadPlan(runID)
	if err != nil {
		return nil, nil, nil, executionState{}, err
	}

	tasks, err := ParsePlanTasks(plan)
	if err != nil {
		return nil, nil, nil, executionState{}, err
	}

	state, err := readExecutionState(plan)
	if err != nil {
		return nil, nil, nil, executionState{}, err
	}

	return plan, runObj, tasks, state, nil
}

func readExecutionState(plan map[string]interface{}) (executionState, error) {
	if plan == nil {
		return executionState{}, &Error{Code: reasonCodeNilPlan}
	}

	rawState, ok := plan[executionStateKey]
	if !ok || rawState == nil {
		return executionState{
			TaskStatuses: make(map[string]string),
			TaskResults:  make(map[string]TaskResult),
		}, nil
	}

	payload, err := json.Marshal(rawState)
	if err != nil {
		return executionState{}, &Error{Code: reasonCodeInvalidPlanTasks, Err: err}
	}

	var state executionState
	if err := json.Unmarshal(payload, &state); err != nil {
		return executionState{}, &Error{Code: reasonCodeInvalidPlanTasks, Err: err}
	}

	if state.TaskStatuses == nil {
		state.TaskStatuses = make(map[string]string)
	}
	if state.TaskResults == nil {
		state.TaskResults = make(map[string]TaskResult)
	}

	for taskID, status := range state.TaskStatuses {
		if !isValidTaskStatus(status) {
			return executionState{}, &Error{Code: reasonCodeInvalidTaskStatus, TaskID: taskID, Err: fmt.Errorf("status %q is not supported", status)}
		}
	}

	for taskID, result := range state.TaskResults {
		if result.TaskID != "" && result.TaskID != taskID {
			return executionState{}, &Error{Code: reasonCodeInvalidTaskResult, TaskID: taskID, Err: fmt.Errorf("result task_id %q does not match key", result.TaskID)}
		}
		if result.Status != "" && result.Status != taskStatusCompleted && result.Status != taskStatusFailed {
			return executionState{}, &Error{Code: reasonCodeInvalidTaskResult, TaskID: taskID, Err: fmt.Errorf("result status %q is not supported", result.Status)}
		}
	}

	return state, nil
}

func writeExecutionState(plan map[string]interface{}, state executionState) {
	plan[executionStateKey] = state
}

func normalizeTaskResult(taskID string, result TaskResult, expectedStatus string) (TaskResult, error) {
	if result.TaskID != "" && result.TaskID != taskID {
		return TaskResult{}, &Error{Code: reasonCodeInvalidTaskResult, TaskID: taskID, Err: fmt.Errorf("result task_id %q does not match", result.TaskID)}
	}

	if result.Status != expectedStatus {
		return TaskResult{}, &Error{Code: reasonCodeInvalidTaskResult, TaskID: taskID, Err: fmt.Errorf("result status must be %q", expectedStatus)}
	}

	result.TaskID = taskID
	result.FilesModified = cloneTrimmedStrings(result.FilesModified)
	result.Output = strings.TrimSpace(result.Output)
	result.Error = strings.TrimSpace(result.Error)

	if result.DurationMs < 0 {
		return TaskResult{}, &Error{Code: reasonCodeInvalidTaskResult, TaskID: taskID, Err: fmt.Errorf("duration_ms must be zero or greater")}
	}

	return result, nil
}

func completedTaskSet(tasks []TaskInfo) map[string]bool {
	completed := make(map[string]bool, len(tasks))
	for _, task := range tasks {
		if task.Status == taskStatusCompleted {
			completed[task.ID] = true
		}
	}
	return completed
}

func allTasksCompleted(tasks []TaskInfo, state executionState) bool {
	for _, task := range tasks {
		if statusForTask(task.ID, state) != taskStatusCompleted {
			return false
		}
	}
	return true
}

func findTask(tasks []TaskInfo, taskID string) (*TaskInfo, error) {
	for index := range tasks {
		if tasks[index].ID == taskID {
			return &tasks[index], nil
		}
	}

	return nil, &Error{Code: reasonCodeTaskNotFound, TaskID: taskID}
}

func updateRunForTaskStart(runObj *runpkg.Run, taskID string) error {
	action := fmt.Sprintf("started task %s", taskID)
	runObj.Blockers = nil

	switch runObj.Status {
	case runpkg.StatusPlanReady, runpkg.StatusBlocked:
		return runpkg.Transition(runObj, runpkg.StatusExecuting, action)
	case runpkg.StatusExecuting:
		touchRun(runObj, action)
		return nil
	default:
		return &Error{Code: reasonCodeInvalidRunStatus, RunID: runObj.ID, TaskID: taskID, Err: fmt.Errorf("cannot start a task from run status %q", runObj.Status)}
	}
}

func updateRunForTaskCompletion(runObj *runpkg.Run, taskID string, allDone bool) error {
	action := fmt.Sprintf("completed task %s", taskID)
	runObj.Blockers = nil

	if allDone {
		switch runObj.Status {
		case runpkg.StatusExecuting, runpkg.StatusBlocked:
			return runpkg.Transition(runObj, runpkg.StatusVerifying, action)
		case runpkg.StatusVerifying:
			touchRun(runObj, action)
			return nil
		default:
			return &Error{Code: reasonCodeInvalidRunStatus, RunID: runObj.ID, TaskID: taskID, Err: fmt.Errorf("cannot finish execution from run status %q", runObj.Status)}
		}
	}

	switch runObj.Status {
	case runpkg.StatusPlanReady, runpkg.StatusBlocked:
		return runpkg.Transition(runObj, runpkg.StatusExecuting, action)
	case runpkg.StatusExecuting:
		touchRun(runObj, action)
		return nil
	default:
		return &Error{Code: reasonCodeInvalidRunStatus, RunID: runObj.ID, TaskID: taskID, Err: fmt.Errorf("cannot record progress from run status %q", runObj.Status)}
	}
}

func updateRunForTaskFailure(runObj *runpkg.Run, taskID string, result TaskResult) error {
	action := fmt.Sprintf("failed task %s", taskID)
	runObj.Blockers = []string{buildBlockerMessage(taskID, result)}

	switch runObj.Status {
	case runpkg.StatusPlanReady, runpkg.StatusExecuting, runpkg.StatusVerifying:
		return runpkg.Transition(runObj, runpkg.StatusBlocked, action)
	case runpkg.StatusBlocked:
		touchRun(runObj, action)
		return nil
	default:
		return &Error{Code: reasonCodeInvalidRunStatus, RunID: runObj.ID, TaskID: taskID, Err: fmt.Errorf("cannot block a run from status %q", runObj.Status)}
	}
}

func touchRun(runObj *runpkg.Run, action string) {
	now := time.Now().UTC()
	if runObj.CreatedAt.IsZero() {
		runObj.CreatedAt = now
	}
	runObj.UpdatedAt = now
	runObj.CurrentPhase = runpkg.DerivePhase(runObj)
	runObj.LastCompletedAction = strings.TrimSpace(action)
}

func buildBlockerMessage(taskID string, result TaskResult) string {
	if result.Error != "" {
		return fmt.Sprintf("task %s failed: %s", taskID, result.Error)
	}
	if result.Output != "" {
		return fmt.Sprintf("task %s failed: %s", taskID, result.Output)
	}
	return fmt.Sprintf("task %s failed", taskID)
}

func validateResolvedConfig(resolver func(string) (*config.Config, error), runObj *runpkg.Run) (*config.Config, error) {
	if resolver == nil || runObj == nil {
		return nil, nil
	}

	return resolver(runObj.Profile)
}

func validateTaskPolicy(task TaskInfo, cfg *config.Config) error {
	if cfg == nil {
		return nil
	}

	command := strings.TrimSpace(task.VerificationCmd)
	for _, denied := range cfg.Policy.DeniedCommands {
		denied = strings.TrimSpace(denied)
		if denied == "" {
			continue
		}
		if commandMatchesDenied(command, denied) {
			return &Error{Code: reasonCodeDeniedCommand, TaskID: task.ID, Err: fmt.Errorf("verification command %q matches denied command %q", command, denied)}
		}
	}

	return nil
}

func commandMatchesDenied(command, denied string) bool {
	if command == denied {
		return true
	}

	if !strings.Contains(denied, " ") {
		parts := strings.Fields(command)
		return len(parts) > 0 && parts[0] == denied
	}

	return false
}

func cloneTrimmedStrings(values []string) []string {
	if len(values) == 0 {
		return nil
	}

	cloned := make([]string, 0, len(values))
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed == "" {
			continue
		}
		cloned = append(cloned, trimmed)
	}

	if len(cloned) == 0 {
		return nil
	}

	return cloned
}

func statusForTask(taskID string, state executionState) string {
	status := strings.TrimSpace(state.TaskStatuses[taskID])
	if status != "" {
		return status
	}
	if result, ok := state.TaskResults[taskID]; ok && strings.TrimSpace(result.Status) != "" {
		return strings.TrimSpace(result.Status)
	}
	return taskStatusPending
}

func isValidTaskStatus(status string) bool {
	switch strings.TrimSpace(status) {
	case taskStatusPending, taskStatusInProgress, taskStatusCompleted, taskStatusFailed:
		return true
	default:
		return false
	}
}
