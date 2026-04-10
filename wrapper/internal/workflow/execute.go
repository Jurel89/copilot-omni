package workflow

import (
	"context"
	"encoding/json"
	"fmt"
	"path/filepath"
	"strings"
	"time"

	"github.com/copilot-omni/wrapper/internal/copilot"
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

	report := executePhaseReport{Tasks: make([]executeTaskRecord, 0, len(plan.Tasks))}
	completed := make(map[string]bool, len(plan.Tasks))

	for len(completed) < len(plan.Tasks) {
		var nextTask *planTask
		for i := range plan.Tasks {
			task := &plan.Tasks[i]
			if completed[task.ID] || !dependenciesSatisfied(task.Dependencies, completed) {
				continue
			}
			nextTask = task
			break
		}

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
	transcriptEntry := buildExecuteTranscriptEntry(taskID, taskInfo)
	if err := appendPhaseTranscript(r.repoRoot, state.ID, PhaseExecute, transcriptEntry); err != nil {
		return err
	}

	prompt := buildExecutePrompt(state, taskID, taskInfo)
	output, err := r.copilotRunner.Run(ctx, prompt, copilot.RunOptions{
		Agent:     "omni-conductor",
		SharePath: transcriptPath(r.repoRoot, state.ID, PhaseExecute),
		Silent:    true,
		NoAskUser: true,
		AddDirs:   []string{filepath.Join(r.repoRoot, "plugin")},
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
	if len(fileTargets) == 0 {
		return "Task completed without declared file targets."
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
