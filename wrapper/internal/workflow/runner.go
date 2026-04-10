package workflow

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/copilot-omni/wrapper/internal/copilot"
)

const runStateVersion = "1"

type Runner struct {
	repoRoot      string
	sidecarMgr    sidecarManager
	copilotRunner copilotRunner
}

type sidecarManager interface {
	Start(ctx context.Context) error
	HealthCheck(ctx context.Context, timeout time.Duration) error
	CallTool(ctx context.Context, tool string, args map[string]any) (string, error)
	Stop() error
	IsRunning() bool
}

type copilotRunner interface {
	Run(ctx context.Context, prompt string, opts copilot.RunOptions) (string, error)
}

type StandardCopilotRunner struct{}

type runState struct {
	RunID         string            `json:"run_id"`
	Version       string            `json:"version"`
	Status        string            `json:"status"`
	UserPrompt    string            `json:"user_prompt,omitempty"`
	UpdatedAt     string            `json:"updated_at"`
	Phases        []PhaseResult     `json:"phases"`
	ArtifactPaths map[string]string `json:"artifact_paths,omitempty"`
	Summary       string            `json:"summary,omitempty"`
}

type planDocument struct {
	RunID   string     `json:"run_id"`
	Version string     `json:"version"`
	Tasks   []planTask `json:"tasks"`
}

type planTask struct {
	ID              string   `json:"id"`
	Title           string   `json:"title"`
	Description     string   `json:"description"`
	Dependencies    []string `json:"dependencies"`
	FileTargets     []string `json:"file_targets"`
	VerificationCmd string   `json:"verification_cmd"`
	RollbackNote    string   `json:"rollback_note"`
}

type toolWriteResult struct {
	Status string `json:"status"`
	Path   string `json:"path"`
	RunID  string `json:"run_id"`
}

type resumeContext struct {
	RunID         string            `json:"run_id"`
	Status        string            `json:"status"`
	ArtifactPaths map[string]string `json:"artifact_paths"`
	Summary       string            `json:"summary"`
}

func (StandardCopilotRunner) Run(ctx context.Context, prompt string, opts copilot.RunOptions) (string, error) {
	return copilot.Run(ctx, prompt, opts)
}

func NewRunner(repoRoot string, mgr sidecarManager, cr copilotRunner) *Runner {
	return &Runner{repoRoot: repoRoot, sidecarMgr: mgr, copilotRunner: cr}
}

func (r *Runner) Run(ctx context.Context, userPrompt string) (*RunResult, error) {
	return r.runWorkflow(ctx, userPrompt, "workflow")
}

func (r *Runner) Plan(ctx context.Context, userPrompt string) (*RunResult, error) {
	return r.runWorkflow(ctx, userPrompt, "plan")
}

func (r *Runner) Resume(ctx context.Context, runID string) (*RunResult, error) {
	if err := r.ensureReady(ctx); err != nil {
		return nil, err
	}

	resolvedRunID, err := r.resolveRunID(runID)
	if err != nil {
		return nil, err
	}

	state, err := r.loadResumeState(ctx, resolvedRunID)
	if err != nil {
		return nil, err
	}
	if state.UserPrompt == "" {
		return nil, fmt.Errorf("resume %s: run.json is missing user_prompt", resolvedRunID)
	}

	if err := r.executeRemainingPhases(ctx, state, "resume"); err != nil {
		return r.resultFromState(state), err
	}

	return r.resultFromState(state), nil
}

func (r *Runner) runWorkflow(ctx context.Context, userPrompt, mode string) (*RunResult, error) {
	if strings.TrimSpace(userPrompt) == "" {
		return nil, fmt.Errorf("prompt is required")
	}
	if err := r.ensureReady(ctx); err != nil {
		return nil, err
	}

	runID := newRunID()
	state := &runState{
		RunID:         runID,
		Version:       runStateVersion,
		Status:        "draft",
		UserPrompt:    strings.TrimSpace(userPrompt),
		UpdatedAt:     time.Now().UTC().Format(time.RFC3339),
		Phases:        []PhaseResult{},
		ArtifactPaths: map[string]string{"run": artifactPath(r.repoRoot, runID, "run.json")},
		Summary:       "Run created. Discuss phase pending.",
	}

	if err := r.persistRunState(ctx, state); err != nil {
		return nil, err
	}

	if err := r.executeRemainingPhases(ctx, state, mode); err != nil {
		return r.resultFromState(state), err
	}

	return r.resultFromState(state), nil
}

func (r *Runner) executeRemainingPhases(ctx context.Context, state *runState, mode string) error {
	if !r.hasPhaseArtifact(state, PhaseDiscuss) {
		if _, err := r.runDiscussPhase(ctx, state); err != nil {
			return err
		}
	}

	discussOutput, err := r.readDiscussOutput(state)
	if err != nil {
		return err
	}

	if !r.hasArtifactFile(state, "spec") {
		if _, err := r.runSpecPhase(ctx, state, discussOutput); err != nil {
			return err
		}
	}

	specContent, err := r.readArtifactContent(state.RunID, "spec.md")
	if err != nil {
		return err
	}

	if !r.hasArtifactFile(state, "plan") {
		if _, err := r.runPlanPhase(ctx, state, specContent); err != nil {
			return err
		}
	}

	planContent, err := r.readArtifactContent(state.RunID, "plan.json")
	if err != nil {
		return err
	}

	if !r.hasArtifactFile(state, "decisions") {
		if _, err := r.runReviewPhase(ctx, state, specContent, planContent); err != nil {
			return err
		}
	}

	decisionContent, err := r.readArtifactContent(state.RunID, "decisions.md")
	if err != nil {
		return err
	}

	state.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	if strings.Contains(strings.ToUpper(decisionContent), "BLOCKING:") {
		state.Status = "blocked"
		state.Summary = "Workflow paused. Review produced blocking findings in decisions.md."
	} else if mode == "plan" {
		state.Status = "plan_ready"
		state.Summary = "Plan workflow completed. Review passed and artifacts are ready for execution."
	} else if mode == "resume" {
		state.Status = "plan_ready"
		state.Summary = "Resume completed. Remaining planning phases finished without duplicating existing artifacts."
	} else {
		state.Status = "plan_ready"
		state.Summary = "Review completed. Plan is approved and ready for the execute phase (Phase 2)."
	}

	return r.persistRunState(ctx, state)
}

func (r *Runner) runDiscussPhase(ctx context.Context, state *runState) (string, error) {
	output, err := r.invokePhase(ctx, state.RunID, PhaseDiscuss, DiscussPrompt(state.UserPrompt))
	transcriptContent := strings.TrimSpace(output)
	if transcriptContent == "" {
		transcriptContent = "No output captured from Copilot discuss phase."
	}
	if writeErr := WriteTranscript(r.repoRoot, state.RunID, PhaseDiscuss, transcriptContent); writeErr != nil && err == nil {
		err = writeErr
	}

	result := PhaseResult{Phase: PhaseDiscuss, RunID: state.RunID, Status: "completed", Output: transcriptContent}
	if err != nil {
		result.Status = "failed"
		result.Error = err.Error()
		state.Status = "blocked"
		state.Summary = "Discuss phase failed. Check the discuss transcript and retry resume."
		r.upsertPhaseResult(state, result)
		_ = r.persistRunState(ctx, state)
		return transcriptContent, fmt.Errorf("discuss phase: %w", err)
	}

	state.Status = "draft"
	state.Summary = "Discuss phase completed. Spec phase pending."
	state.ArtifactPaths["transcript_discuss"] = transcriptPath(r.repoRoot, state.RunID, PhaseDiscuss)
	state.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	r.upsertPhaseResult(state, result)
	if persistErr := r.persistRunState(ctx, state); persistErr != nil {
		return transcriptContent, persistErr
	}

	return transcriptContent, nil
}

func (r *Runner) runSpecPhase(ctx context.Context, state *runState, discussOutput string) (string, error) {
	output, err := r.invokePhase(ctx, state.RunID, PhaseSpec, SpecPrompt(state.UserPrompt, discussOutput))
	content := strings.TrimSpace(output)
	if content == "" && err == nil {
		err = fmt.Errorf("spec output was empty")
	}
	if writeErr := WriteTranscript(r.repoRoot, state.RunID, PhaseSpec, content); writeErr != nil && err == nil {
		err = writeErr
	}

	result := PhaseResult{Phase: PhaseSpec, RunID: state.RunID, Status: "completed", Output: content}
	if err == nil {
		path, writeArtifactErr := r.writeArtifact(ctx, state.RunID, "spec.md", content)
		if writeArtifactErr != nil {
			err = writeArtifactErr
		} else {
			result.ArtifactPath = path
			state.ArtifactPaths["spec"] = path
		}
	}
	if err != nil {
		result.Status = "failed"
		result.Error = err.Error()
		state.Status = "blocked"
		state.Summary = "Spec phase failed. Check spec transcript and resume when ready."
		r.upsertPhaseResult(state, result)
		_ = r.persistRunState(ctx, state)
		return content, fmt.Errorf("spec phase: %w", err)
	}

	state.Status = "spec_ready"
	state.Summary = "Spec written. Plan phase pending."
	state.ArtifactPaths["transcript_spec"] = transcriptPath(r.repoRoot, state.RunID, PhaseSpec)
	state.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	r.upsertPhaseResult(state, result)
	if persistErr := r.persistRunState(ctx, state); persistErr != nil {
		return content, persistErr
	}

	return content, nil
}

func (r *Runner) runPlanPhase(ctx context.Context, state *runState, specContent string) (string, error) {
	output, err := r.invokePhase(ctx, state.RunID, PhasePlan, PlanPrompt(specContent)+"\nCurrent run ID: "+state.RunID+"\n")
	content, normalizeErr := normalizePlanContent(output, state.RunID)
	if normalizeErr != nil && err == nil {
		err = normalizeErr
	}
	transcriptContent := strings.TrimSpace(output)
	if transcriptContent == "" {
		transcriptContent = content
	}
	if writeErr := WriteTranscript(r.repoRoot, state.RunID, PhasePlan, transcriptContent); writeErr != nil && err == nil {
		err = writeErr
	}

	result := PhaseResult{Phase: PhasePlan, RunID: state.RunID, Status: "completed", Output: content}
	if err == nil {
		path, writeArtifactErr := r.writeArtifact(ctx, state.RunID, "plan.json", content)
		if writeArtifactErr != nil {
			err = writeArtifactErr
		} else {
			result.ArtifactPath = path
			state.ArtifactPaths["plan"] = path
		}
	}
	if err != nil {
		result.Status = "failed"
		result.Error = err.Error()
		state.Status = "blocked"
		state.Summary = "Plan phase failed. Fix the plan prompt or artifact and resume."
		r.upsertPhaseResult(state, result)
		_ = r.persistRunState(ctx, state)
		return content, fmt.Errorf("plan phase: %w", err)
	}

	state.Status = "plan_ready"
	state.Summary = "Plan written. Review phase pending."
	state.ArtifactPaths["transcript_plan"] = transcriptPath(r.repoRoot, state.RunID, PhasePlan)
	state.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	r.upsertPhaseResult(state, result)
	if persistErr := r.persistRunState(ctx, state); persistErr != nil {
		return content, persistErr
	}

	return content, nil
}

func (r *Runner) runReviewPhase(ctx context.Context, state *runState, specContent, planContent string) (string, error) {
	output, err := r.invokePhase(ctx, state.RunID, PhaseReview, ReviewPrompt(specContent, planContent))
	content := strings.TrimSpace(output)
	if content == "" && err == nil {
		err = fmt.Errorf("review output was empty")
	}
	if writeErr := WriteTranscript(r.repoRoot, state.RunID, PhaseReview, content); writeErr != nil && err == nil {
		err = writeErr
	}

	result := PhaseResult{Phase: PhaseReview, RunID: state.RunID, Status: "completed", Output: content}
	if err == nil {
		path, writeArtifactErr := r.writeArtifact(ctx, state.RunID, "decisions.md", content)
		if writeArtifactErr != nil {
			err = writeArtifactErr
		} else {
			result.ArtifactPath = path
			state.ArtifactPaths["decisions"] = path
		}
	}
	if err != nil {
		result.Status = "failed"
		result.Error = err.Error()
		state.Status = "blocked"
		state.Summary = "Review phase failed. Inspect decisions transcript and resume."
		r.upsertPhaseResult(state, result)
		_ = r.persistRunState(ctx, state)
		return content, fmt.Errorf("review phase: %w", err)
	}

	if strings.Contains(strings.ToUpper(content), "BLOCKING:") {
		state.Status = "blocked"
		state.Summary = "Review completed with blocking findings. Resolve decisions.md before execution."
	} else {
		state.Status = "plan_ready"
		state.Summary = "Review completed without blocking findings."
	}
	state.ArtifactPaths["transcript_review"] = transcriptPath(r.repoRoot, state.RunID, PhaseReview)
	state.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	r.upsertPhaseResult(state, result)
	if persistErr := r.persistRunState(ctx, state); persistErr != nil {
		return content, persistErr
	}

	return content, nil
}

func (r *Runner) invokePhase(ctx context.Context, runID, phase, prompt string) (string, error) {
	sharePath := transcriptPath(r.repoRoot, runID, phase)
	if err := os.MkdirAll(filepath.Dir(sharePath), 0o755); err != nil {
		return "", fmt.Errorf("create transcript directory for %s: %w", phase, err)
	}

	agent := "omni-conductor"
	switch phase {
	case PhasePlan:
		agent = "omni-planner"
	case PhaseReview:
		agent = "omni-reviewer"
	}

	return r.copilotRunner.Run(ctx, prompt, copilot.RunOptions{
		Agent:     agent,
		SharePath: sharePath,
		Silent:    true,
		NoAskUser: true,
		AddDirs:   []string{filepath.Join(r.repoRoot, "plugin")},
	})
}

func (r *Runner) ensureReady(ctx context.Context) error {
	if r.sidecarMgr == nil {
		return fmt.Errorf("sidecar manager is required")
	}
	if r.copilotRunner == nil {
		return fmt.Errorf("copilot runner is required")
	}
	if !r.sidecarMgr.IsRunning() {
		if err := r.sidecarMgr.Start(ctx); err != nil {
			return fmt.Errorf("start sidecar: %w", err)
		}
	}
	if err := r.sidecarMgr.HealthCheck(ctx, 5*time.Second); err != nil {
		return fmt.Errorf("sidecar health check: %w", err)
	}
	return nil
}

func (r *Runner) persistRunState(ctx context.Context, state *runState) error {
	if state.ArtifactPaths == nil {
		state.ArtifactPaths = map[string]string{}
	}
	state.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	content, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal run state: %w", err)
	}
	path, err := r.writeRunState(ctx, state.RunID, string(content))
	if err != nil {
		return err
	}
	state.ArtifactPaths["run"] = path
	return nil
}

func (r *Runner) writeRunState(ctx context.Context, runID, content string) (string, error) {
	return r.writeArtifact(ctx, runID, "run.json", content)
}

func (r *Runner) writeArtifact(ctx context.Context, runID, filename, content string) (string, error) {
	result, err := r.sidecarMgr.CallTool(ctx, "omni_artifact_write", map[string]any{
		"repo_root": r.repoRoot,
		"run_id":    runID,
		"filename":  filename,
		"content":   content,
	})
	if err != nil {
		return "", fmt.Errorf("write artifact %s: %w", filename, err)
	}

	var parsed toolWriteResult
	if err := json.Unmarshal([]byte(result), &parsed); err == nil && parsed.Path != "" {
		return parsed.Path, nil
	}

	return artifactPath(r.repoRoot, runID, filename), nil
}

func (r *Runner) loadResumeState(ctx context.Context, runID string) (*runState, error) {
	if resumeState, err := r.loadResumeContext(ctx, runID); err == nil {
		resumeState.UserPrompt = strings.TrimSpace(resumeState.UserPrompt)
		if resumeState.ArtifactPaths == nil {
			resumeState.ArtifactPaths = map[string]string{}
		}
		resumeState.ArtifactPaths["run"] = artifactPath(r.repoRoot, runID, "run.json")
		return resumeState, nil
	}

	content, err := r.readArtifactContent(runID, "run.json")
	if err != nil {
		return nil, fmt.Errorf("load run state %s: %w", runID, err)
	}

	var state runState
	if err := json.Unmarshal([]byte(content), &state); err != nil {
		return nil, fmt.Errorf("decode run.json for %s: %w", runID, err)
	}
	if state.RunID == "" {
		state.RunID = runID
	}
	if state.Version == "" {
		state.Version = runStateVersion
	}
	if state.ArtifactPaths == nil {
		state.ArtifactPaths = map[string]string{}
	}
	state.ArtifactPaths["run"] = artifactPath(r.repoRoot, runID, "run.json")
	r.populateExistingArtifacts(&state)
	return &state, nil
}

func (r *Runner) loadResumeContext(ctx context.Context, runID string) (*runState, error) {
	result, err := r.sidecarMgr.CallTool(ctx, "omni_resume_context", map[string]any{
		"repo_root": r.repoRoot,
		"run_id":    runID,
	})
	if err != nil {
		return nil, err
	}

	var ctxResult resumeContext
	if err := json.Unmarshal([]byte(result), &ctxResult); err != nil {
		return nil, fmt.Errorf("decode resume context: %w", err)
	}

	state := &runState{
		RunID:         runID,
		Version:       runStateVersion,
		Status:        ctxResult.Status,
		UpdatedAt:     time.Now().UTC().Format(time.RFC3339),
		Phases:        []PhaseResult{},
		ArtifactPaths: ctxResult.ArtifactPaths,
		Summary:       ctxResult.Summary,
	}
	if state.ArtifactPaths == nil {
		state.ArtifactPaths = map[string]string{}
	}
	content, readErr := r.readArtifactContent(runID, "run.json")
	if readErr == nil {
		var persisted runState
		if unmarshalErr := json.Unmarshal([]byte(content), &persisted); unmarshalErr == nil {
			state.UserPrompt = persisted.UserPrompt
			state.Phases = persisted.Phases
		}
	}
	r.populateExistingArtifacts(state)
	return state, nil
}

func (r *Runner) readDiscussOutput(state *runState) (string, error) {
	if output, err := ReadTranscript(r.repoRoot, state.RunID, PhaseDiscuss); err == nil && strings.TrimSpace(output) != "" {
		return output, nil
	}
	if phase := r.findPhaseResult(state, PhaseDiscuss); phase != nil && strings.TrimSpace(phase.Output) != "" {
		return phase.Output, nil
	}
	return "", fmt.Errorf("run %s has no discuss transcript to continue from", state.RunID)
}

func (r *Runner) readArtifactContent(runID, filename string) (string, error) {
	path := artifactPath(r.repoRoot, runID, filename)
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("read %s: %w", filename, err)
	}
	return string(data), nil
}

func (r *Runner) populateExistingArtifacts(state *runState) {
	for key, filename := range map[string]string{
		"spec":      "spec.md",
		"plan":      "plan.json",
		"decisions": "decisions.md",
	} {
		path := artifactPath(r.repoRoot, state.RunID, filename)
		if _, err := os.Stat(path); err == nil {
			state.ArtifactPaths[key] = path
		}
	}
	for _, phase := range []string{PhaseDiscuss, PhaseSpec, PhasePlan, PhaseReview} {
		path := transcriptPath(r.repoRoot, state.RunID, phase)
		if _, err := os.Stat(path); err == nil {
			state.ArtifactPaths["transcript_"+phase] = path
		}
	}
}

func (r *Runner) hasPhaseArtifact(state *runState, phase string) bool {
	path := transcriptPath(r.repoRoot, state.RunID, phase)
	if _, err := os.Stat(path); err == nil {
		return true
	}
	phaseResult := r.findPhaseResult(state, phase)
	return phaseResult != nil && phaseResult.Status == "completed"
}

func (r *Runner) hasArtifactFile(state *runState, key string) bool {
	path := state.ArtifactPaths[key]
	if path == "" {
		switch key {
		case "spec":
			path = artifactPath(r.repoRoot, state.RunID, "spec.md")
		case "plan":
			path = artifactPath(r.repoRoot, state.RunID, "plan.json")
		case "decisions":
			path = artifactPath(r.repoRoot, state.RunID, "decisions.md")
		}
	}
	if path == "" {
		return false
	}
	_, err := os.Stat(path)
	return err == nil
}

func (r *Runner) findPhaseResult(state *runState, phase string) *PhaseResult {
	for i := range state.Phases {
		if state.Phases[i].Phase == phase {
			return &state.Phases[i]
		}
	}
	return nil
}

func (r *Runner) upsertPhaseResult(state *runState, result PhaseResult) {
	for i := range state.Phases {
		if state.Phases[i].Phase == result.Phase {
			state.Phases[i] = result
			return
		}
	}
	state.Phases = append(state.Phases, result)
	sort.SliceStable(state.Phases, func(i, j int) bool {
		return phaseOrder(state.Phases[i].Phase) < phaseOrder(state.Phases[j].Phase)
	})
}

func (r *Runner) resultFromState(state *runState) *RunResult {
	paths := make(map[string]string, len(state.ArtifactPaths))
	for k, v := range state.ArtifactPaths {
		paths[k] = v
	}
	return &RunResult{
		RunID:         state.RunID,
		Status:        state.Status,
		Phases:        append([]PhaseResult(nil), state.Phases...),
		ArtifactPaths: paths,
		Summary:       state.Summary,
	}
}

func (r *Runner) resolveRunID(runID string) (string, error) {
	runID = strings.TrimSpace(runID)
	if runID != "" {
		return runID, nil
	}

	runsDir := filepath.Join(r.repoRoot, ".omni", "runs")
	entries, err := os.ReadDir(runsDir)
	if err != nil {
		return "", fmt.Errorf("read runs directory: %w", err)
	}

	runIDs := make([]string, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() {
			runIDs = append(runIDs, entry.Name())
		}
	}
	if len(runIDs) == 0 {
		return "", fmt.Errorf("no runs found in %s", runsDir)
	}
	sort.Strings(runIDs)
	return runIDs[len(runIDs)-1], nil
}

func normalizePlanContent(raw string, runID string) (string, error) {
	trimmed := strings.TrimSpace(raw)
	trimmed = strings.TrimPrefix(trimmed, "```json")
	trimmed = strings.TrimPrefix(trimmed, "```")
	trimmed = strings.TrimSuffix(trimmed, "```")
	trimmed = strings.TrimSpace(trimmed)
	if !json.Valid([]byte(trimmed)) {
		return "", fmt.Errorf("plan output is not valid JSON")
	}

	var doc planDocument
	if err := json.Unmarshal([]byte(trimmed), &doc); err != nil {
		return "", fmt.Errorf("decode plan output: %w", err)
	}
	if strings.TrimSpace(doc.RunID) == "" {
		doc.RunID = runID
	}
	if strings.TrimSpace(doc.Version) == "" {
		doc.Version = runStateVersion
	}
	if len(doc.Tasks) == 0 {
		return "", fmt.Errorf("plan output is missing tasks")
	}
	for _, task := range doc.Tasks {
		if strings.TrimSpace(task.ID) == "" || strings.TrimSpace(task.Title) == "" || strings.TrimSpace(task.Description) == "" {
			return "", fmt.Errorf("plan task is missing id, title, or description")
		}
		if strings.TrimSpace(task.VerificationCmd) == "" {
			return "", fmt.Errorf("plan task %s is missing verification_cmd", task.ID)
		}
		if strings.TrimSpace(task.RollbackNote) == "" {
			return "", fmt.Errorf("plan task %s is missing rollback_note", task.ID)
		}
		if task.Dependencies == nil || task.FileTargets == nil {
			return "", fmt.Errorf("plan task %s must include dependencies and file_targets arrays", task.ID)
		}
	}

	normalized, err := json.MarshalIndent(doc, "", "  ")
	if err != nil {
		return "", fmt.Errorf("marshal normalized plan: %w", err)
	}
	return string(normalized), nil
}

func newRunID() string {
	return "run-" + time.Now().UTC().Format("20060102-150405-000000000")
}

func artifactPath(repoRoot, runID, filename string) string {
	return filepath.Join(repoRoot, ".omni", "runs", runID, filename)
}

func isUnknownToolError(err error) bool {
	if err == nil {
		return false
	}
	message := strings.ToLower(err.Error())
	return strings.Contains(message, "unknown tool") || errors.Is(err, os.ErrNotExist)
}

func phaseOrder(phase string) int {
	switch phase {
	case PhaseDiscuss:
		return 1
	case PhaseSpec:
		return 2
	case PhasePlan:
		return 3
	case PhaseReview:
		return 4
	case PhaseExecute:
		return 5
	case PhaseVerify:
		return 6
	default:
		return 99
	}
}
