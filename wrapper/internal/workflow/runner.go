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
	journal       []journalEntry
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

type journalEntry struct {
	Timestamp string `json:"timestamp"`
	Action    string `json:"action"`
	From      string `json:"from"`
	To        string `json:"to"`
	Message   string `json:"message,omitempty"`
}

type runState struct {
	ID                  string            `json:"id"`
	Status              string            `json:"status"`
	CurrentPhase        string            `json:"current_phase"`
	Prompt              string            `json:"prompt"`
	CreatedAt           string            `json:"created_at"`
	UpdatedAt           string            `json:"updated_at"`
	Profile             string            `json:"profile,omitempty"`
	LastCompletedAction string            `json:"last_completed_action,omitempty"`
	Blockers            []string          `json:"blockers,omitempty"`
	ArtifactPaths       map[string]string `json:"artifact_paths,omitempty"`
	Version             string            `json:"version,omitempty"`
	Phases              []PhaseResult     `json:"phases"`
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

type toolReadResult struct {
	Content []struct {
		Type string `json:"type"`
		Text string `json:"text"`
	} `json:"content"`
}

type resumeContext struct {
	RunID         string            `json:"run_id"`
	Status        string            `json:"status"`
	ArtifactPaths map[string]string `json:"artifact_paths"`
	Summary       string            `json:"summary"`
}

var validStatuses = map[string][]string{
	"draft":      {"spec_ready", "aborted"},
	"spec_ready": {"plan_ready", "blocked", "aborted"},
	"plan_ready": {"executing", "blocked", "aborted"},
	"executing":  {"verifying", "blocked", "aborted"},
	"verifying":  {"done", "blocked", "aborted"},
	"blocked":    {"spec_ready", "plan_ready", "executing", "verifying", "aborted"},
	"done":       {},
	"aborted":    {},
}

func (StandardCopilotRunner) Run(ctx context.Context, prompt string, opts copilot.RunOptions) (string, error) {
	return copilot.Run(ctx, prompt, opts)
}

func NewRunner(repoRoot string, mgr sidecarManager, cr copilotRunner) *Runner {
	return &Runner{repoRoot: repoRoot, sidecarMgr: mgr, copilotRunner: cr, journal: make([]journalEntry, 0)}
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
	if state.Prompt == "" {
		return nil, fmt.Errorf("resume %s: run.json is missing prompt", resolvedRunID)
	}

	if err := r.executeRemainingPhases(ctx, state, "resume"); err != nil {
		return r.resultFromState(state), err
	}

	return r.resultFromState(state), nil
}

func (r *Runner) transitionState(state *runState, to string, action string) error {
	from := state.Status
	allowed, ok := validStatuses[from]
	if !ok {
		return fmt.Errorf("invalid current status %q", from)
	}

	validTarget := false
	for _, candidate := range allowed {
		if candidate == to {
			validTarget = true
			break
		}
	}
	if !validTarget {
		return fmt.Errorf("cannot transition from %q to %q", from, to)
	}

	state.Status = to
	state.CurrentPhase = derivePhase(to)
	state.LastCompletedAction = action
	state.UpdatedAt = time.Now().UTC().Format(time.RFC3339)

	r.journal = append(r.journal, journalEntry{
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Action:    action,
		From:      from,
		To:        to,
	})

	return nil
}

func derivePhase(status string) string {
	switch status {
	case "draft":
		return "draft"
	case "spec_ready":
		return "spec"
	case "plan_ready":
		return "plan"
	case "executing":
		return "executing"
	case "verifying":
		return "verifying"
	case "done":
		return "done"
	case "blocked":
		return "blocked"
	case "aborted":
		return "aborted"
	default:
		return ""
	}
}

func (r *Runner) runWorkflow(ctx context.Context, userPrompt, mode string) (*RunResult, error) {
	if strings.TrimSpace(userPrompt) == "" {
		return nil, fmt.Errorf("prompt is required")
	}
	if err := r.ensureReady(ctx); err != nil {
		return nil, err
	}

	now := time.Now().UTC().Format(time.RFC3339)
	runID := newRunID()
	state := &runState{
		ID:            runID,
		Version:       runStateVersion,
		Status:        "draft",
		CurrentPhase:  "draft",
		Prompt:        strings.TrimSpace(userPrompt),
		CreatedAt:     now,
		UpdatedAt:     now,
		Phases:        []PhaseResult{},
		ArtifactPaths: map[string]string{},
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

	if !r.hasCanonicalArtifact(state, "spec") {
		if _, err := r.runSpecPhase(ctx, state, discussOutput); err != nil {
			return err
		}
	}

	specContent, err := r.readCanonicalArtifact(ctx, state.ID, "spec.md")
	if err != nil {
		return err
	}

	if !r.hasCanonicalArtifact(state, "plan") {
		if _, err := r.runPlanPhase(ctx, state, specContent); err != nil {
			return err
		}
	}

	planContent, err := r.readCanonicalArtifact(ctx, state.ID, "plan.json")
	if err != nil {
		return err
	}

	if !r.hasCanonicalArtifact(state, "decisions") {
		if _, err := r.runReviewPhase(ctx, state, specContent, planContent); err != nil {
			return err
		}
	}

	decisionContent, err := r.readCanonicalArtifact(ctx, state.ID, "decisions.md")
	if err != nil {
		return err
	}

	if strings.Contains(strings.ToUpper(decisionContent), "BLOCKING:") {
		if transErr := r.transitionState(state, "blocked", "review_produced_blocking"); transErr != nil {
			return transErr
		}
		state.Blockers = extractBlockers(decisionContent)
	}

	return r.persistRunState(ctx, state)
}

func (r *Runner) runDiscussPhase(ctx context.Context, state *runState) (string, error) {
	output, err := r.invokePhase(ctx, state.ID, PhaseDiscuss, DiscussPrompt(state.Prompt))
	transcriptContent := strings.TrimSpace(output)
	if transcriptContent == "" {
		transcriptContent = "No output captured from Copilot discuss phase."
	}
	if writeErr := WriteTranscript(r.repoRoot, state.ID, PhaseDiscuss, transcriptContent); writeErr != nil && err == nil {
		err = writeErr
	}

	result := PhaseResult{Phase: PhaseDiscuss, RunID: state.ID, Status: "completed", Output: transcriptContent}
	if err != nil {
		result.Status = "failed"
		result.Error = err.Error()
		_ = r.transitionState(state, "blocked", "discuss_failed")
		r.upsertPhaseResult(state, result)
		_ = r.persistRunState(ctx, state)
		return transcriptContent, fmt.Errorf("discuss phase: %w", err)
	}

	state.ArtifactPaths["transcript_discuss"] = transcriptPath(r.repoRoot, state.ID, PhaseDiscuss)
	r.upsertPhaseResult(state, result)
	if persistErr := r.persistRunState(ctx, state); persistErr != nil {
		return transcriptContent, persistErr
	}

	return transcriptContent, nil
}

func (r *Runner) runSpecPhase(ctx context.Context, state *runState, discussOutput string) (string, error) {
	output, err := r.invokePhase(ctx, state.ID, PhaseSpec, SpecPrompt(state.Prompt, discussOutput))
	content := strings.TrimSpace(output)
	if content == "" && err == nil {
		err = fmt.Errorf("spec output was empty")
	}
	if writeErr := WriteTranscript(r.repoRoot, state.ID, PhaseSpec, content); writeErr != nil && err == nil {
		err = writeErr
	}

	result := PhaseResult{Phase: PhaseSpec, RunID: state.ID, Status: "completed", Output: content}
	if err == nil {
		path, writeArtifactErr := r.writeArtifact(ctx, state.ID, "spec.md", content)
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
		_ = r.transitionState(state, "blocked", "spec_failed")
		r.upsertPhaseResult(state, result)
		_ = r.persistRunState(ctx, state)
		return content, fmt.Errorf("spec phase: %w", err)
	}

	if transErr := r.transitionState(state, "spec_ready", "spec_written"); transErr != nil {
		r.upsertPhaseResult(state, result)
		return content, transErr
	}
	state.ArtifactPaths["transcript_spec"] = transcriptPath(r.repoRoot, state.ID, PhaseSpec)
	r.upsertPhaseResult(state, result)
	if persistErr := r.persistRunState(ctx, state); persistErr != nil {
		return content, persistErr
	}

	return content, nil
}

func (r *Runner) runPlanPhase(ctx context.Context, state *runState, specContent string) (string, error) {
	output, err := r.invokePhase(ctx, state.ID, PhasePlan, PlanPrompt(specContent)+"\nCurrent run ID: "+state.ID+"\n")
	content, normalizeErr := normalizePlanContent(output, state.ID)
	if normalizeErr != nil && err == nil {
		err = normalizeErr
	}
	transcriptContent := strings.TrimSpace(output)
	if transcriptContent == "" {
		transcriptContent = content
	}
	if writeErr := WriteTranscript(r.repoRoot, state.ID, PhasePlan, transcriptContent); writeErr != nil && err == nil {
		err = writeErr
	}

	result := PhaseResult{Phase: PhasePlan, RunID: state.ID, Status: "completed", Output: content}
	if err == nil {
		path, writeArtifactErr := r.writeArtifact(ctx, state.ID, "plan.json", content)
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
		_ = r.transitionState(state, "blocked", "plan_failed")
		r.upsertPhaseResult(state, result)
		_ = r.persistRunState(ctx, state)
		return content, fmt.Errorf("plan phase: %w", err)
	}

	if transErr := r.transitionState(state, "plan_ready", "plan_written"); transErr != nil {
		r.upsertPhaseResult(state, result)
		return content, transErr
	}
	state.ArtifactPaths["transcript_plan"] = transcriptPath(r.repoRoot, state.ID, PhasePlan)
	r.upsertPhaseResult(state, result)
	if persistErr := r.persistRunState(ctx, state); persistErr != nil {
		return content, persistErr
	}

	return content, nil
}

func (r *Runner) runReviewPhase(ctx context.Context, state *runState, specContent, planContent string) (string, error) {
	output, err := r.invokePhase(ctx, state.ID, PhaseReview, ReviewPrompt(specContent, planContent))
	content := strings.TrimSpace(output)
	if content == "" && err == nil {
		err = fmt.Errorf("review output was empty")
	}
	if writeErr := WriteTranscript(r.repoRoot, state.ID, PhaseReview, content); writeErr != nil && err == nil {
		err = writeErr
	}

	result := PhaseResult{Phase: PhaseReview, RunID: state.ID, Status: "completed", Output: content}
	if err == nil {
		path, writeArtifactErr := r.writeArtifact(ctx, state.ID, "decisions.md", content)
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
		_ = r.transitionState(state, "blocked", "review_failed")
		r.upsertPhaseResult(state, result)
		_ = r.persistRunState(ctx, state)
		return content, fmt.Errorf("review phase: %w", err)
	}

	if strings.Contains(strings.ToUpper(content), "BLOCKING:") {
		_ = r.transitionState(state, "blocked", "review_blocking")
	}
	state.ArtifactPaths["transcript_review"] = transcriptPath(r.repoRoot, state.ID, PhaseReview)
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
	if state.CurrentPhase == "" {
		state.CurrentPhase = derivePhase(state.Status)
	}
	content, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal run state: %w", err)
	}
	path, err := r.writeArtifact(ctx, state.ID, "run.json", string(content))
	if err != nil {
		return err
	}
	state.ArtifactPaths["run"] = path
	return nil
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

	return runFilePath(r.repoRoot, runID, filename), nil
}

func (r *Runner) readCanonicalArtifact(ctx context.Context, runID, filename string) (string, error) {
	result, err := r.sidecarMgr.CallTool(ctx, "omni_artifact_read", map[string]any{
		"repo_root": r.repoRoot,
		"run_id":    runID,
		"filename":  filename,
	})
	if err != nil {
		if isUnknownToolError(err) {
			return r.readArtifactFallback(runID, filename)
		}
		return "", fmt.Errorf("read %s via sidecar: %w", filename, err)
	}

	var parsed toolReadResult
	if err := json.Unmarshal([]byte(result), &parsed); err == nil && len(parsed.Content) > 0 {
		return parsed.Content[0].Text, nil
	}

	return result, nil
}

func (r *Runner) readArtifactFallback(runID, filename string) (string, error) {
	switch filename {
	case "spec.md":
		path := filepath.Join(r.repoRoot, ".omni", "specs", runID+".md")
		data, err := os.ReadFile(path)
		if err != nil {
			return "", fmt.Errorf("read spec %s: %w", runID, err)
		}
		return string(data), nil
	case "plan.json":
		path := filepath.Join(r.repoRoot, ".omni", "plans", runID+".json")
		data, err := os.ReadFile(path)
		if err != nil {
			return "", fmt.Errorf("read plan %s: %w", runID, err)
		}
		return string(data), nil
	case "decisions.md":
		path := filepath.Join(r.repoRoot, ".omni", "decisions", runID+".md")
		data, err := os.ReadFile(path)
		if err != nil {
			return "", fmt.Errorf("read decisions %s: %w", runID, err)
		}
		return string(data), nil
	default:
		path := runFilePath(r.repoRoot, runID, filename)
		data, err := os.ReadFile(path)
		if err != nil {
			return "", fmt.Errorf("read %s/%s: %w", runID, filename, err)
		}
		return string(data), nil
	}
}

func (r *Runner) loadResumeState(ctx context.Context, runID string) (*runState, error) {
	if resumeState, err := r.loadResumeContext(ctx, runID); err == nil {
		resumeState.Prompt = strings.TrimSpace(resumeState.Prompt)
		if resumeState.ArtifactPaths == nil {
			resumeState.ArtifactPaths = map[string]string{}
		}
		resumeState.ArtifactPaths["run"] = runFilePath(r.repoRoot, runID, "run.json")
		return resumeState, nil
	}

	content, err := r.readCanonicalArtifact(ctx, runID, "run.json")
	if err != nil {
		return nil, fmt.Errorf("load run state %s: %w", runID, err)
	}

	var state runState
	if err := json.Unmarshal([]byte(content), &state); err != nil {
		return nil, fmt.Errorf("decode run.json for %s: %w", runID, err)
	}
	if state.ID == "" {
		state.ID = runID
	}
	if state.Version == "" {
		state.Version = runStateVersion
	}
	if state.ArtifactPaths == nil {
		state.ArtifactPaths = map[string]string{}
	}
	state.ArtifactPaths["run"] = runFilePath(r.repoRoot, runID, "run.json")
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
		ID:            runID,
		Version:       runStateVersion,
		Status:        ctxResult.Status,
		CurrentPhase:  derivePhase(ctxResult.Status),
		UpdatedAt:     time.Now().UTC().Format(time.RFC3339),
		Phases:        []PhaseResult{},
		ArtifactPaths: ctxResult.ArtifactPaths,
	}
	if state.ArtifactPaths == nil {
		state.ArtifactPaths = map[string]string{}
	}

	content, readErr := r.readCanonicalArtifact(ctx, runID, "run.json")
	if readErr == nil {
		var persisted runState
		if unmarshalErr := json.Unmarshal([]byte(content), &persisted); unmarshalErr == nil {
			state.Prompt = persisted.Prompt
			state.CreatedAt = persisted.CreatedAt
			state.Phases = persisted.Phases
			if persisted.Version != "" {
				state.Version = persisted.Version
			}
		}
	}
	r.populateExistingArtifacts(state)
	return state, nil
}

func (r *Runner) readDiscussOutput(state *runState) (string, error) {
	if output, err := ReadTranscript(r.repoRoot, state.ID, PhaseDiscuss); err == nil && strings.TrimSpace(output) != "" {
		return output, nil
	}
	if phase := r.findPhaseResult(state, PhaseDiscuss); phase != nil && strings.TrimSpace(phase.Output) != "" {
		return phase.Output, nil
	}
	return "", fmt.Errorf("run %s has no discuss transcript to continue from", state.ID)
}

func (r *Runner) populateExistingArtifacts(state *runState) {
	for key, filename := range map[string]string{
		"spec":      "spec.md",
		"plan":      "plan.json",
		"decisions": "decisions.md",
	} {
		path := canonicalArtifactPath(r.repoRoot, state.ID, filename)
		if _, err := os.Stat(path); err == nil {
			state.ArtifactPaths[key] = path
		}
	}
	for _, phase := range []string{PhaseDiscuss, PhaseSpec, PhasePlan, PhaseReview} {
		path := transcriptPath(r.repoRoot, state.ID, phase)
		if _, err := os.Stat(path); err == nil {
			state.ArtifactPaths["transcript_"+phase] = path
		}
	}
}

func (r *Runner) hasPhaseArtifact(state *runState, phase string) bool {
	path := transcriptPath(r.repoRoot, state.ID, phase)
	if _, err := os.Stat(path); err == nil {
		return true
	}
	phaseResult := r.findPhaseResult(state, phase)
	return phaseResult != nil && phaseResult.Status == "completed"
}

func (r *Runner) hasCanonicalArtifact(state *runState, key string) bool {
	if path, ok := state.ArtifactPaths[key]; ok && path != "" {
		if _, err := os.Stat(path); err == nil {
			return true
		}
	}

	filename := ""
	switch key {
	case "spec":
		filename = "spec.md"
	case "plan":
		filename = "plan.json"
	case "decisions":
		filename = "decisions.md"
	}
	if filename == "" {
		return false
	}

	path := canonicalArtifactPath(r.repoRoot, state.ID, filename)
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
		RunID:         state.ID,
		Status:        state.Status,
		Phases:        append([]PhaseResult(nil), state.Phases...),
		ArtifactPaths: paths,
		Summary:       nextActionSummary(state.Status),
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

func extractBlockers(content string) []string {
	var blockers []string
	for _, line := range strings.Split(content, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(strings.ToUpper(trimmed), "BLOCKING:") {
			blockers = append(blockers, strings.TrimSpace(strings.TrimPrefix(trimmed, "BLOCKING:")))
		}
	}
	if len(blockers) == 0 {
		blockers = []string{"Review produced blocking findings"}
	}
	return blockers
}

func nextActionSummary(status string) string {
	switch status {
	case "draft":
		return "Run created. Discuss phase pending."
	case "spec_ready":
		return "Spec written. Plan phase pending."
	case "plan_ready":
		return "Review completed. Plan is approved and ready for the execute phase (Phase 2)."
	case "blocked":
		return "Workflow paused. Review produced blocking findings."
	case "executing":
		return "Execution is in progress."
	case "verifying":
		return "Verification is in progress."
	case "done":
		return "Run is complete."
	case "aborted":
		return "Run was aborted."
	default:
		return "Run state is unknown."
	}
}

func newRunID() string {
	return "run-" + time.Now().UTC().Format("20060102-150405-000000000")
}

func runFilePath(repoRoot, runID, filename string) string {
	return filepath.Join(repoRoot, ".omni", "runs", runID, filename)
}

func canonicalArtifactPath(repoRoot, runID, filename string) string {
	switch filename {
	case "spec.md":
		return filepath.Join(repoRoot, ".omni", "specs", runID+".md")
	case "plan.json":
		return filepath.Join(repoRoot, ".omni", "plans", runID+".json")
	case "decisions.md":
		return filepath.Join(repoRoot, ".omni", "decisions", runID+".md")
	default:
		return runFilePath(repoRoot, runID, filename)
	}
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
