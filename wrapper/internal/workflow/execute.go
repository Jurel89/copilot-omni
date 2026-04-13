package workflow

import (
	"context"
	"encoding/json"
	"fmt"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/Jurel89/copilot-omni/wrapper/internal/copilot"
)

type executePhaseReport struct {
	Tasks []executeTaskRecord `json:"tasks"`
}

type executeTaskRecord struct {
	TaskID           string   `json:"task_id"`
	Title            string   `json:"title"`
	Status           string   `json:"status"`
	FileTargets      []string `json:"file_targets,omitempty"`
	VerificationCmd  string   `json:"verification_cmd,omitempty"`
	TranscriptPath   string   `json:"transcript_path,omitempty"`
	ResultSummary    string   `json:"result_summary,omitempty"`
	DurationMillis   int64    `json:"duration_ms,omitempty"`
	FailureReason    string   `json:"failure_reason,omitempty"`
	StartedAtRFC3339 string   `json:"started_at,omitempty"`
	EndedAtRFC3339   string   `json:"ended_at,omitempty"`
}

type policyCheckResult struct {
	Allowed    bool   `json:"allowed"`
	ReasonCode string `json:"reason_code,omitempty"`
	Message    string `json:"message,omitempty"`
	Profile    string `json:"profile,omitempty"`
}

type repoMapResult struct {
	Files    []repoMapFile `json:"files"`
	Warnings []string      `json:"warnings,omitempty"`
}

type repoMapFile struct {
	Path string `json:"path"`
}

func (r *Runner) ExecutePhase(ctx context.Context, state *runState) error {
	if err := r.transitionState(state, "executing", "execute_started"); err != nil {
		return err
	}
	if err := r.persistRunState(ctx, state); err != nil {
		return err
	}

	planContent, err := r.readCanonicalArtifact(ctx, state.ID, "plan.json")
	if err != nil {
		return r.failExecutePhase(ctx, state, nil, fmt.Errorf("read plan.json: %w", err))
	}

	var plan planDocument
	if err := json.Unmarshal([]byte(planContent), &plan); err != nil {
		return r.failExecutePhase(ctx, state, nil, fmt.Errorf("decode plan.json: %w", err))
	}
	if len(plan.Tasks) == 0 {
		return r.failExecutePhase(ctx, state, nil, fmt.Errorf("plan.json does not contain any tasks"))
	}

	policyResult, err := r.callPolicyCheck(ctx, map[string]any{
		"repo_root": r.repoRoot,
		"operation": "command",
		"value":     "execute plan",
	})
	if err != nil {
		return r.failExecutePhase(ctx, state, nil, fmt.Errorf("check execute policy: %w", err))
	}
	if !policyResult.Allowed {
		return r.failExecutePhase(ctx, state, nil, fmt.Errorf("execute policy denied: %s", policyDenyMessage(policyResult, "execute plan is not allowed")))
	}

	orderedTasks, err := orderedExecutableTasks(plan.Tasks)
	if err != nil {
		return r.failExecutePhase(ctx, state, nil, fmt.Errorf("order plan tasks: %w", err))
	}

	report := executePhaseReport{Tasks: make([]executeTaskRecord, 0, len(plan.Tasks))}
	completed := make(map[string]bool, len(plan.Tasks))

	for len(completed) < len(plan.Tasks) {
		nextTask := nextReadyTask(orderedTasks, completed)

		if nextTask == nil {
			return r.failExecutePhase(ctx, state, report.Tasks, fmt.Errorf("no ready tasks remain; unresolved dependency chain in plan"))
		}

		taskInfo := planTaskToMap(*nextTask)
		startedAt := time.Now().UTC()
		record := executeTaskRecord{
			TaskID:           nextTask.ID,
			Title:            nextTask.Title,
			Status:           "running",
			FileTargets:      append([]string(nil), nextTask.FileTargets...),
			VerificationCmd:  nextTask.VerificationCmd,
			TranscriptPath:   transcriptPath(r.repoRoot, state.ID, PhaseExecute),
			StartedAtRFC3339: startedAt.Format(time.RFC3339),
		}

		if err := r.executeTask(ctx, state, nextTask.ID, taskInfo); err != nil {
			record.Status = "failed"
			record.FailureReason = err.Error()
			record.EndedAtRFC3339 = time.Now().UTC().Format(time.RFC3339)
			record.DurationMillis = time.Since(startedAt).Milliseconds()
			report.Tasks = append(report.Tasks, record)
			return r.failExecutePhase(ctx, state, report.Tasks, fmt.Errorf("execute task %s: %w", nextTask.ID, err))
		}

		record.Status = "completed"
		record.ResultSummary = taskExecutionSummary(taskInfo)
		record.EndedAtRFC3339 = time.Now().UTC().Format(time.RFC3339)
		record.DurationMillis = time.Since(startedAt).Milliseconds()
		report.Tasks = append(report.Tasks, record)
		completed[nextTask.ID] = true
	}

	reportPayload, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return r.failExecutePhase(ctx, state, report.Tasks, fmt.Errorf("marshal execute phase report: %w", err))
	}

	result := PhaseResult{
		Phase:  PhaseExecute,
		RunID:  state.ID,
		Status: "completed",
		Output: string(reportPayload),
	}
	state.ArtifactPaths["transcript_"+PhaseExecute] = transcriptPath(r.repoRoot, state.ID, PhaseExecute)
	r.upsertPhaseResult(state, result)

	if err := r.transitionState(state, "verifying", "execute_completed"); err != nil {
		return err
	}

	return r.persistRunState(ctx, state)
}

func (r *Runner) executeTask(ctx context.Context, state *runState, taskID string, taskInfo map[string]any) error {
	taskFileTargets := stringSliceValue(taskInfo["file_targets"])
	allowedTargets := make([]string, 0, len(taskFileTargets))
	skippedTargets := make([]string, 0)
	for _, target := range taskFileTargets {
		check, err := r.callPolicyCheck(ctx, map[string]any{
			"repo_root": r.repoRoot,
			"run_id":    state.ID,
			"task_id":   taskID,
			"operation": "path",
			"value":     target,
		})
		if err != nil {
			return fmt.Errorf("check task target policy for %s: %w", target, err)
		}
		if !check.Allowed {
			skippedTargets = append(skippedTargets, fmt.Sprintf("%s (%s)", target, policyDenyMessage(check, "denied by policy")))
			continue
		}
		allowedTargets = append(allowedTargets, target)
	}
	taskInfo["file_targets"] = allowedTargets
	if len(skippedTargets) > 0 {
		taskInfo["policy_skipped_targets"] = append([]string(nil), skippedTargets...)
	}

	transcriptEntry := buildExecuteTranscriptEntry(taskID, taskInfo)
	if len(skippedTargets) > 0 {
		var builder strings.Builder
		builder.WriteString(transcriptEntry)
		builder.WriteString("\nSkipped by policy:\n")
		for _, skippedTarget := range skippedTargets {
			builder.WriteString("- ")
			builder.WriteString(skippedTarget)
			builder.WriteString("\n")
		}
		transcriptEntry = builder.String()
	}
	if err := appendPhaseTranscript(r.repoRoot, state.ID, PhaseExecute, transcriptEntry); err != nil {
		return err
	}
	if len(allowedTargets) == 0 {
		return nil
	}

	prompt := buildExecutePrompt(state, taskID, taskInfo)
	output, err := r.copilotRunner.Run(ctx, prompt, copilot.RunOptions{
		Agent:     "omni-conductor",
		SharePath: transcriptPath(r.repoRoot, state.ID, PhaseExecute),
		Silent:    true,
		NoAskUser: true,
		AddDirs:   []string{r.pluginDir},
	})

	resultEntry := strings.TrimSpace(output)
	if resultEntry == "" {
		resultEntry = "No Copilot output captured for task."
	}
	if err := appendPhaseTranscript(r.repoRoot, state.ID, PhaseExecute, "## Result for "+taskID+"\n\n"+resultEntry); err != nil {
		return err
	}
	if err != nil {
		return err
	}

	repoMap, err := r.readTaskRepoMap(ctx, state.ID, taskID)
	if err != nil {
		return fmt.Errorf("read repo map for task %s: %w", taskID, err)
	}
	if err := verifyRepoMapScope(repoMap, allowedTargets); err != nil {
		return fmt.Errorf("verify repo map scope for task %s: %w", taskID, err)
	}
	if len(repoMap.Warnings) > 0 {
		warningText := "## Repo map warnings for " + taskID + "\n\n- " + strings.Join(repoMap.Warnings, "\n- ")
		if err := appendPhaseTranscript(r.repoRoot, state.ID, PhaseExecute, warningText); err != nil {
			return err
		}
	}

	return nil
}

func (r *Runner) failExecutePhase(ctx context.Context, state *runState, tasks []executeTaskRecord, executeErr error) error {
	result := PhaseResult{Phase: PhaseExecute, RunID: state.ID, Status: "failed"}
	if len(tasks) > 0 {
		payload, err := json.MarshalIndent(executePhaseReport{Tasks: tasks}, "", "  ")
		if err == nil {
			result.Output = string(payload)
		}
	}
	if executeErr != nil {
		result.Error = executeErr.Error()
		state.Blockers = []string{executeErr.Error()}
	}
	r.upsertPhaseResult(state, result)
	if transErr := r.transitionState(state, "blocked", "execute_failed"); transErr != nil {
		return transErr
	}
	if persistErr := r.persistRunState(ctx, state); persistErr != nil {
		return persistErr
	}
	return executeErr
}

func dependenciesSatisfied(dependencies []string, completed map[string]bool) bool {
	for _, dependency := range dependencies {
		if !completed[dependency] {
			return false
		}
	}
	return true
}

func orderedExecutableTasks(tasks []planTask) ([]*planTask, error) {
	byID := make(map[string]*planTask, len(tasks))
	graph := make(map[string][]string, len(tasks))
	for i := range tasks {
		task := &tasks[i]
		if strings.TrimSpace(task.ID) == "" {
			return nil, fmt.Errorf("task id must not be empty")
		}
		if _, exists := byID[task.ID]; exists {
			return nil, fmt.Errorf("duplicate task id %q", task.ID)
		}
		byID[task.ID] = task
		graph[task.ID] = append([]string(nil), task.Dependencies...)
	}

	for taskID, dependencies := range graph {
		seen := make(map[string]bool, len(dependencies))
		for _, dependencyID := range dependencies {
			if dependencyID == "" {
				return nil, fmt.Errorf("task %s has an empty dependency", taskID)
			}
			if _, ok := byID[dependencyID]; !ok {
				return nil, fmt.Errorf("task %s depends on unknown task %s", taskID, dependencyID)
			}
			if seen[dependencyID] {
				continue
			}
			seen[dependencyID] = true
		}
	}

	orderedIDs, err := topologicalSortTasks(graph)
	if err != nil {
		return nil, err
	}

	orderedTasks := make([]*planTask, 0, len(orderedIDs))
	for _, taskID := range orderedIDs {
		orderedTasks = append(orderedTasks, byID[taskID])
	}
	return orderedTasks, nil
}

func nextReadyTask(tasks []*planTask, completed map[string]bool) *planTask {
	for _, task := range tasks {
		if completed[task.ID] || !dependenciesSatisfied(task.Dependencies, completed) {
			continue
		}
		return task
	}
	return nil
}

func topologicalSortTasks(graph map[string][]string) ([]string, error) {
	indegree := make(map[string]int, len(graph))
	dependents := make(map[string][]string, len(graph))

	for taskID := range graph {
		indegree[taskID] = 0
	}
	for taskID, dependencies := range graph {
		seen := make(map[string]bool, len(dependencies))
		for _, dependencyID := range dependencies {
			if _, ok := graph[dependencyID]; !ok {
				return nil, fmt.Errorf("task %s depends on unknown task %s", taskID, dependencyID)
			}
			if seen[dependencyID] {
				continue
			}
			seen[dependencyID] = true
			indegree[taskID]++
			dependents[dependencyID] = append(dependents[dependencyID], taskID)
		}
	}

	queue := make([]string, 0)
	for taskID, degree := range indegree {
		if degree == 0 {
			queue = append(queue, taskID)
		}
	}
	sort.Strings(queue)

	ordered := make([]string, 0, len(graph))
	for len(queue) > 0 {
		node := queue[0]
		queue = queue[1:]
		ordered = append(ordered, node)

		nextDependents := append([]string(nil), dependents[node]...)
		sort.Strings(nextDependents)
		for _, dependentID := range nextDependents {
			indegree[dependentID]--
			if indegree[dependentID] == 0 {
				queue = append(queue, dependentID)
				sort.Strings(queue)
			}
		}
	}

	if len(ordered) != len(graph) {
		return nil, fmt.Errorf("dependency graph contains a cycle or unreachable task")
	}

	return ordered, nil
}

func planTaskToMap(task planTask) map[string]any {
	return map[string]any{
		"id":               task.ID,
		"title":            task.Title,
		"description":      task.Description,
		"dependencies":     append([]string(nil), task.Dependencies...),
		"file_targets":     append([]string(nil), task.FileTargets...),
		"verification_cmd": task.VerificationCmd,
		"rollback_note":    task.RollbackNote,
	}
}

func (r *Runner) callPolicyCheck(ctx context.Context, args map[string]any) (policyCheckResult, error) {
	result, err := r.sidecarMgr.CallTool(ctx, "omni_policy_check", args)
	if err != nil {
		return policyCheckResult{}, err
	}

	var parsed policyCheckResult
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		return policyCheckResult{}, fmt.Errorf("decode policy check result: %w", err)
	}

	return parsed, nil
}

func (r *Runner) readTaskRepoMap(ctx context.Context, runID, taskID string) (repoMapResult, error) {
	result, err := r.sidecarMgr.CallTool(ctx, "omni_repo_map", map[string]any{
		"repo_root": r.repoRoot,
		"run_id":    runID,
		"task_id":   taskID,
	})
	if err != nil {
		return repoMapResult{}, err
	}

	var parsed repoMapResult
	if err := json.Unmarshal([]byte(result), &parsed); err != nil {
		return repoMapResult{}, fmt.Errorf("decode repo map result: %w", err)
	}

	return parsed, nil
}

func policyDenyMessage(result policyCheckResult, fallback string) string {
	message := strings.TrimSpace(result.Message)
	if message != "" {
		return message
	}
	if reason := strings.TrimSpace(result.ReasonCode); reason != "" {
		return reason
	}
	return fallback
}

func verifyRepoMapScope(repoMap repoMapResult, allowedTargets []string) error {
	if len(allowedTargets) == 0 {
		return nil
	}
	for _, file := range repoMap.Files {
		if pathWithinTargets(file.Path, allowedTargets) {
			continue
		}
		return fmt.Errorf("repo map returned out-of-scope file %q", file.Path)
	}
	return nil
}

func pathWithinTargets(filePath string, targets []string) bool {
	normalizedPath := normalizeTaskPath(filePath)
	for _, target := range targets {
		normalizedTarget := normalizeTaskPath(target)
		if normalizedTarget == "" {
			continue
		}
		if normalizedPath == normalizedTarget {
			return true
		}
		if strings.HasSuffix(normalizedTarget, "/") && strings.HasPrefix(normalizedPath, normalizedTarget) {
			return true
		}
		if strings.ContainsAny(normalizedTarget, "*?") {
			matched, err := filepath.Match(normalizedTarget, normalizedPath)
			if err == nil && matched {
				return true
			}
		}
	}
	return false
}

func normalizeTaskPath(value string) string {
	normalized := filepath.ToSlash(filepath.Clean(strings.TrimSpace(value)))
	if normalized == "." {
		return ""
	}
	if strings.HasSuffix(strings.TrimSpace(value), "/") && !strings.HasSuffix(normalized, "/") {
		return normalized + "/"
	}
	return normalized
}

func buildExecutePrompt(state *runState, taskID string, taskInfo map[string]any) string {
	return fmt.Sprintf(`You are running the bounded execute phase for Copilot Omni.

Run ID: %s
Original request:
%s

Implement only the approved plan task below.

Task ID: %s
Title: %s
Description: %s
File targets: %s
Verification command: %s

Execution rules:
- Stay strictly within this task's scope.
- Modify only the listed file targets unless a directly related generated file is unavoidable.
- Do not change protected Omni-managed files.
- Return a concise plain-text execution summary with files changed and key outcomes.
`, state.ID, state.Prompt, taskID, stringValue(taskInfo["title"]), stringValue(taskInfo["description"]), strings.Join(stringSliceValue(taskInfo["file_targets"]), ", "), stringValue(taskInfo["verification_cmd"]))
}

func buildExecuteTranscriptEntry(taskID string, taskInfo map[string]any) string {
	return fmt.Sprintf("## Executing %s\n\n- Title: %s\n- Description: %s\n- File targets: %s\n- Verification command: %s\n",
		taskID,
		stringValue(taskInfo["title"]),
		stringValue(taskInfo["description"]),
		strings.Join(stringSliceValue(taskInfo["file_targets"]), ", "),
		stringValue(taskInfo["verification_cmd"]),
	)
}

func taskExecutionSummary(taskInfo map[string]any) string {
	fileTargets := stringSliceValue(taskInfo["file_targets"])
	skippedTargets := stringSliceValue(taskInfo["policy_skipped_targets"])
	if len(fileTargets) == 0 {
		if len(skippedTargets) > 0 {
			return "Task skipped because policy denied all declared file targets."
		}
		return "Task completed without declared file targets."
	}
	if len(skippedTargets) > 0 {
		return fmt.Sprintf("Completed approved work for %s while policy skipped %d target(s).", strings.Join(fileTargets, ", "), len(skippedTargets))
	}
	return fmt.Sprintf("Completed approved work for %s.", strings.Join(fileTargets, ", "))
}

func appendPhaseTranscript(repoRoot, runID, phase, content string) error {
	trimmed := strings.TrimSpace(content)
	if trimmed == "" {
		return nil
	}

	existing, err := ReadTranscript(repoRoot, runID, phase)
	if err != nil {
		if writeErr := WriteTranscript(repoRoot, runID, phase, trimmed); writeErr != nil {
			return writeErr
		}
		return nil
	}

	combined := strings.TrimSpace(existing)
	if combined == "" {
		combined = trimmed
	} else {
		combined += "\n\n" + trimmed
	}

	return WriteTranscript(repoRoot, runID, phase, combined)
}

func stringValue(value any) string {
	text, _ := value.(string)
	return strings.TrimSpace(text)
}

func stringSliceValue(value any) []string {
	switch typed := value.(type) {
	case []string:
		return append([]string(nil), typed...)
	case []any:
		result := make([]string, 0, len(typed))
		for _, item := range typed {
			result = append(result, stringValue(item))
		}
		return result
	default:
		return nil
	}
}
