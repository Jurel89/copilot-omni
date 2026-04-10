package run

type Status string

const (
	StatusDraft     Status = "draft"
	StatusSpecReady Status = "spec_ready"
	StatusPlanReady Status = "plan_ready"
	StatusExecuting Status = "executing"
	StatusVerifying Status = "verifying"
	StatusDone      Status = "done"
	StatusBlocked   Status = "blocked"
	StatusAborted   Status = "aborted"
)

var validStatuses = map[Status]struct{}{
	StatusDraft:     {},
	StatusSpecReady: {},
	StatusPlanReady: {},
	StatusExecuting: {},
	StatusVerifying: {},
	StatusDone:      {},
	StatusBlocked:   {},
	StatusAborted:   {},
}

var ValidTransitions = map[Status][]Status{
	StatusDraft:     {StatusSpecReady, StatusAborted},
	StatusSpecReady: {StatusPlanReady, StatusBlocked, StatusAborted},
	StatusPlanReady: {StatusExecuting, StatusBlocked, StatusAborted},
	StatusExecuting: {StatusVerifying, StatusBlocked, StatusAborted},
	StatusVerifying: {StatusDone, StatusBlocked, StatusAborted},
	StatusBlocked:   {StatusSpecReady, StatusPlanReady, StatusExecuting, StatusVerifying, StatusAborted},
	StatusDone:      {},
	StatusAborted:   {},
}

func CanTransition(from, to Status) bool {
	if !from.IsValid() || !to.IsValid() {
		return false
	}

	allowed := ValidTransitions[from]
	for _, candidate := range allowed {
		if candidate == to {
			return true
		}
	}

	return false
}

func (s Status) IsValid() bool {
	_, ok := validStatuses[s]
	return ok
}
