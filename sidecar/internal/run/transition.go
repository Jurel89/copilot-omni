package run

import (
	"fmt"
	"strings"
	"time"
)

const (
	ReasonCodeNilRun            = "nil_run"
	ReasonCodeInvalidFromStatus = "invalid_from_status"
	ReasonCodeInvalidToStatus   = "invalid_to_status"
	ReasonCodeInvalidTransition = "invalid_transition"
)

type TransitionError struct {
	Code string
	From Status
	To   Status
}

func (e *TransitionError) Error() string {
	switch e.Code {
	case ReasonCodeNilRun:
		return e.Code + ": run is nil"
	case ReasonCodeInvalidFromStatus:
		return fmt.Sprintf("%s: invalid current status %q", e.Code, e.From)
	case ReasonCodeInvalidToStatus:
		return fmt.Sprintf("%s: invalid target status %q", e.Code, e.To)
	default:
		return fmt.Sprintf("%s: cannot transition from %q to %q", e.Code, e.From, e.To)
	}
}

func Transition(run *Run, to Status, action string) error {
	if run == nil {
		return &TransitionError{Code: ReasonCodeNilRun}
	}

	if !run.Status.IsValid() {
		return &TransitionError{Code: ReasonCodeInvalidFromStatus, From: run.Status, To: to}
	}

	if !to.IsValid() {
		return &TransitionError{Code: ReasonCodeInvalidToStatus, From: run.Status, To: to}
	}

	if !CanTransition(run.Status, to) {
		return &TransitionError{Code: ReasonCodeInvalidTransition, From: run.Status, To: to}
	}

	now := time.Now().UTC()
	if run.CreatedAt.IsZero() {
		run.CreatedAt = now
	}

	run.Status = to
	run.UpdatedAt = now
	run.CurrentPhase = DerivePhase(run)
	run.LastCompletedAction = strings.TrimSpace(action)

	return nil
}
