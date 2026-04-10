package workflow

const (
	PhaseDiscuss = "discuss"
	PhaseSpec    = "spec"
	PhasePlan    = "plan"
	PhaseReview  = "review"
	PhaseExecute = "execute"
	PhaseVerify  = "verify"
)

type PhaseResult struct {
	Phase        string `json:"phase"`
	RunID        string `json:"run_id"`
	Status       string `json:"status"`
	ArtifactPath string `json:"artifact_path,omitempty"`
	Error        string `json:"error,omitempty"`
	Output       string `json:"output,omitempty"`
}
