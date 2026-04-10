package run

import "strings"

func DerivePhase(run *Run) string {
	if run == nil {
		return ""
	}

	switch run.Status {
	case StatusDraft:
		return "draft"
	case StatusSpecReady:
		return "spec"
	case StatusPlanReady:
		return "plan"
	case StatusExecuting:
		return "executing"
	case StatusVerifying:
		return "verifying"
	case StatusDone:
		return "done"
	case StatusBlocked:
		return "blocked"
	case StatusAborted:
		return "aborted"
	default:
		return ""
	}
}

func NextSafeAction(run *Run) string {
	if run == nil {
		return "Run state is unavailable"
	}

	switch run.Status {
	case StatusDraft:
		return "Run the discuss/spec phase to generate a specification"
	case StatusSpecReady:
		return "Run the plan phase to create an implementation plan"
	case StatusPlanReady:
		return "Review the plan, then run execution"
	case StatusExecuting:
		return "Continue execution"
	case StatusVerifying:
		return "Run verification"
	case StatusDone:
		return "Run is complete"
	case StatusBlocked:
		if len(run.Blockers) == 0 {
			return "Resolve blockers"
		}
		return "Resolve blockers: " + strings.Join(run.Blockers, ", ")
	case StatusAborted:
		return "Run was aborted"
	default:
		return "Run state is unknown"
	}
}
