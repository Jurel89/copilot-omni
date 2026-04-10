package workflow

import (
	"context"
	"fmt"
)

func (r *Runner) Execute(ctx context.Context, runID string) (*RunResult, error) {
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

	if state.Status != "plan_ready" {
		return nil, fmt.Errorf("run %s is in status %q, expected plan_ready", resolvedRunID, state.Status)
	}

	if err := r.ExecutePhase(ctx, state); err != nil {
		return r.resultFromState(state), err
	}

	if err := r.VerifyPhase(ctx, state); err != nil {
		return r.resultFromState(state), err
	}

	return r.resultFromState(state), nil
}
