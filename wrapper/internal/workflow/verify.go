package workflow

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

type verificationRunResult struct {
	Status     string                   `json:"status"`
	Mode       string                   `json:"mode"`
	Commands   []verificationCommandRun `json:"commands"`
	ReportPath string                   `json:"report_path"`
}

type verificationCommandRun struct {
	Command    string `json:"command"`
	ExitCode   int    `json:"exit_code"`
	StdoutPath string `json:"stdout_path"`
	StderrPath string `json:"stderr_path"`
	DurationMs int64  `json:"duration_ms"`
}

func (r *Runner) VerifyPhase(ctx context.Context, state *runState) error {
	if state.Status != "verifying" {
		if err := r.transitionState(state, "verifying", "verify_started"); err != nil {
			return err
		}
		if err := r.persistRunState(ctx, state); err != nil {
			return err
		}
	}

	planContent, err := r.readCanonicalArtifact(ctx, state.ID, "plan.json")
	if err != nil {
		return r.failVerifyPhase(ctx, state, PhaseResult{Phase: PhaseVerify, RunID: state.ID, Status: "failed"}, fmt.Errorf("read plan.json: %w", err))
	}

	var plan planDocument
	if err := json.Unmarshal([]byte(planContent), &plan); err != nil {
		return r.failVerifyPhase(ctx, state, PhaseResult{Phase: PhaseVerify, RunID: state.ID, Status: "failed"}, fmt.Errorf("decode plan.json: %w", err))
	}

	completedTaskIDs := completedTaskIDsForVerification(state, plan)
	commands := collectVerificationCommands(plan, completedTaskIDs)
	if len(commands) == 0 {
		return r.failVerifyPhase(ctx, state, PhaseResult{Phase: PhaseVerify, RunID: state.ID, Status: "failed"}, fmt.Errorf("no verification commands available for completed tasks"))
	}

	rawResult, err := r.sidecarMgr.CallTool(ctx, "omni_verification_run", map[string]any{
		"repo_root": r.repoRoot,
		"run_id":    state.ID,
		"commands":  commands,
		"mode":      "run",
	})
	if err != nil {
		return r.failVerifyPhase(ctx, state, PhaseResult{Phase: PhaseVerify, RunID: state.ID, Status: "failed"}, fmt.Errorf("run verification: %w", err))
	}

	var verification verificationRunResult
	if err := json.Unmarshal([]byte(rawResult), &verification); err != nil {
		return r.failVerifyPhase(ctx, state, PhaseResult{Phase: PhaseVerify, RunID: state.ID, Status: "failed"}, fmt.Errorf("decode verification result: %w", err))
	}

	result := PhaseResult{
		Phase:        PhaseVerify,
		RunID:        state.ID,
		Status:       "completed",
		ArtifactPath: verification.ReportPath,
		Output:       rawResult,
	}

	failures := verificationFailures(verification)
	if len(failures) > 0 {
		result.Status = "failed"
		result.Error = strings.Join(failures, "; ")
		return r.failVerifyPhase(ctx, state, result, errors.New(result.Error))
	}

	r.upsertPhaseResult(state, result)
	if err := r.transitionState(state, "done", "verify_completed"); err != nil {
		return err
	}
	return r.persistRunState(ctx, state)
}

func (r *Runner) failVerifyPhase(ctx context.Context, state *runState, result PhaseResult, verifyErr error) error {
	if verifyErr != nil {
		result.Error = verifyErr.Error()
		state.Blockers = []string{verifyErr.Error()}
	}
	r.upsertPhaseResult(state, result)
	if transErr := r.transitionState(state, "blocked", "verify_failed"); transErr != nil {
		return transErr
	}
	if persistErr := r.persistRunState(ctx, state); persistErr != nil {
		return persistErr
	}
	return verifyErr
}

func completedTaskIDsForVerification(state *runState, plan planDocument) map[string]bool {
	completed := make(map[string]bool, len(plan.Tasks))
	executeResult := rFindPhaseResult(state, PhaseExecute)
	if executeResult == nil || strings.TrimSpace(executeResult.Output) == "" {
		for _, task := range plan.Tasks {
			completed[task.ID] = true
		}
		return completed
	}

	var report executePhaseReport
	if err := json.Unmarshal([]byte(executeResult.Output), &report); err != nil {
		for _, task := range plan.Tasks {
			completed[task.ID] = true
		}
		return completed
	}

	for _, task := range report.Tasks {
		if task.Status == "completed" {
			completed[task.TaskID] = true
		}
	}
	return completed
}

func collectVerificationCommands(plan planDocument, completed map[string]bool) []string {
	commands := make([]string, 0, len(plan.Tasks))
	seen := make(map[string]bool, len(plan.Tasks))
	for _, task := range plan.Tasks {
		if !completed[task.ID] {
			continue
		}
		command := strings.TrimSpace(task.VerificationCmd)
		if command == "" || seen[command] {
			continue
		}
		seen[command] = true
		commands = append(commands, command)
	}
	return commands
}

func verificationFailures(result verificationRunResult) []string {
	failures := make([]string, 0)
	if strings.TrimSpace(result.Status) != "" && !strings.EqualFold(result.Status, "passed") && !strings.EqualFold(result.Status, "ok") && !strings.EqualFold(result.Status, "success") {
		failures = append(failures, fmt.Sprintf("verification status %q", result.Status))
	}
	for _, command := range result.Commands {
		if command.ExitCode == 0 {
			continue
		}
		failures = append(failures, fmt.Sprintf("command %q failed with exit code %d", command.Command, command.ExitCode))
	}
	return failures
}

func rFindPhaseResult(state *runState, phase string) *PhaseResult {
	for i := range state.Phases {
		if state.Phases[i].Phase == phase {
			return &state.Phases[i]
		}
	}
	return nil
}
