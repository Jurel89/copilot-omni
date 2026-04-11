package workflow

import (
	"reflect"
	"testing"
	"time"
)

func TestPhaseConstantsMatchWorkflowNames(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		got  string
		want string
	}{
		{name: "discuss", got: PhaseDiscuss, want: "discuss"},
		{name: "spec", got: PhaseSpec, want: "spec"},
		{name: "plan", got: PhasePlan, want: "plan"},
		{name: "review", got: PhaseReview, want: "review"},
		{name: "execute", got: PhaseExecute, want: "execute"},
		{name: "verify", got: PhaseVerify, want: "verify"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.got != tt.want {
				t.Fatalf("phase constant %s = %q, want %q", tt.name, tt.got, tt.want)
			}
		})
	}
}

func TestPhaseOrderPrioritizesKnownPhases(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name  string
		phase string
		want  int
	}{
		{name: "discuss first", phase: PhaseDiscuss, want: 1},
		{name: "spec second", phase: PhaseSpec, want: 2},
		{name: "plan third", phase: PhasePlan, want: 3},
		{name: "review fourth", phase: PhaseReview, want: 4},
		{name: "execute fifth", phase: PhaseExecute, want: 5},
		{name: "verify sixth", phase: PhaseVerify, want: 6},
		{name: "unknown phases last", phase: "custom", want: 99},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := phaseOrder(tt.phase); got != tt.want {
				t.Fatalf("phaseOrder(%q) = %d, want %d", tt.phase, got, tt.want)
			}
		})
	}
}

func TestUpsertPhaseResultOrdersWorkflowPhases(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		inserts []PhaseResult
		want    []string
	}{
		{
			name: "reorders canonical phases into workflow sequence",
			inserts: []PhaseResult{
				{Phase: PhaseVerify},
				{Phase: PhaseDiscuss},
				{Phase: PhasePlan},
				{Phase: PhaseExecute},
				{Phase: PhaseSpec},
				{Phase: PhaseReview},
			},
			want: []string{PhaseDiscuss, PhaseSpec, PhasePlan, PhaseReview, PhaseExecute, PhaseVerify},
		},
		{
			name: "places unknown phases after known phases",
			inserts: []PhaseResult{
				{Phase: "custom"},
				{Phase: PhaseReview},
				{Phase: PhaseDiscuss},
			},
			want: []string{PhaseDiscuss, PhaseReview, "custom"},
		},
		{
			name: "replaces an existing phase result instead of duplicating it",
			inserts: []PhaseResult{
				{Phase: PhaseSpec, Status: "completed"},
				{Phase: PhaseDiscuss, Status: "completed"},
				{Phase: PhaseSpec, Status: "failed"},
			},
			want: []string{PhaseDiscuss, PhaseSpec},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			runner := &Runner{}
			state := &runState{}

			for _, result := range tt.inserts {
				runner.upsertPhaseResult(state, result)
			}

			got := phaseNames(state.Phases)
			if !reflect.DeepEqual(got, tt.want) {
				t.Fatalf("phase order = %v, want %v", got, tt.want)
			}

			if tt.name == "replaces an existing phase result instead of duplicating it" {
				if len(state.Phases) != 2 {
					t.Fatalf("len(state.Phases) = %d, want 2", len(state.Phases))
				}
				if state.Phases[1].Status != "failed" {
					t.Fatalf("updated spec status = %q, want %q", state.Phases[1].Status, "failed")
				}
			}
		})
	}
}

func TestTransitionStateUpdatesPhaseForAllowedTransitions(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name      string
		from      string
		to        string
		action    string
		wantPhase string
	}{
		{name: "draft to spec ready", from: "draft", to: "spec_ready", action: "spec_written", wantPhase: "spec"},
		{name: "plan ready to executing", from: "plan_ready", to: "executing", action: "execute_started", wantPhase: "executing"},
		{name: "verifying to done", from: "verifying", to: "done", action: "verify_completed", wantPhase: "done"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			runner := &Runner{}
			state := &runState{Status: tt.from, UpdatedAt: "2000-01-01T00:00:00Z"}

			if err := runner.transitionState(state, tt.to, tt.action); err != nil {
				t.Fatalf("transitionState(%q -> %q) error = %v", tt.from, tt.to, err)
			}

			if state.Status != tt.to {
				t.Fatalf("state.Status = %q, want %q", state.Status, tt.to)
			}
			if state.CurrentPhase != tt.wantPhase {
				t.Fatalf("state.CurrentPhase = %q, want %q", state.CurrentPhase, tt.wantPhase)
			}
			if state.LastCompletedAction != tt.action {
				t.Fatalf("state.LastCompletedAction = %q, want %q", state.LastCompletedAction, tt.action)
			}
			if state.UpdatedAt == "2000-01-01T00:00:00Z" {
				t.Fatal("state.UpdatedAt was not refreshed")
			}
			if _, err := time.Parse(time.RFC3339, state.UpdatedAt); err != nil {
				t.Fatalf("state.UpdatedAt = %q, want RFC3339 timestamp: %v", state.UpdatedAt, err)
			}

			if len(runner.journal) != 1 {
				t.Fatalf("journal length = %d, want 1", len(runner.journal))
			}

			entry := runner.journal[0]
			if entry.From != tt.from || entry.To != tt.to || entry.Action != tt.action {
				t.Fatalf("journal entry = %+v, want from=%q to=%q action=%q", entry, tt.from, tt.to, tt.action)
			}
		})
	}
}

func TestTransitionStateRejectsInvalidTransitions(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name        string
		from        string
		to          string
		wantErrPart string
	}{
		{name: "rejects skipping ahead from draft", from: "draft", to: "done", wantErrPart: `cannot transition from "draft" to "done"`},
		{name: "rejects unknown current status", from: "mystery", to: "spec_ready", wantErrPart: `invalid current status "mystery"`},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			runner := &Runner{}
			state := &runState{Status: tt.from, CurrentPhase: "original", UpdatedAt: "2000-01-01T00:00:00Z"}

			err := runner.transitionState(state, tt.to, "test_action")
			if err == nil {
				t.Fatalf("transitionState(%q -> %q) error = nil, want error", tt.from, tt.to)
			}
			if err.Error() != tt.wantErrPart {
				t.Fatalf("error = %q, want %q", err.Error(), tt.wantErrPart)
			}

			if state.Status != tt.from {
				t.Fatalf("state.Status = %q, want %q after failed transition", state.Status, tt.from)
			}
			if state.CurrentPhase != "original" {
				t.Fatalf("state.CurrentPhase = %q, want %q after failed transition", state.CurrentPhase, "original")
			}
			if state.UpdatedAt != "2000-01-01T00:00:00Z" {
				t.Fatalf("state.UpdatedAt = %q, want original timestamp after failed transition", state.UpdatedAt)
			}
			if len(runner.journal) != 0 {
				t.Fatalf("journal length = %d, want 0 after failed transition", len(runner.journal))
			}
		})
	}
}

func phaseNames(results []PhaseResult) []string {
	names := make([]string, 0, len(results))
	for _, result := range results {
		names = append(names, result.Phase)
	}
	return names
}
