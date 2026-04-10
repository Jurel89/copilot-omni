package workflow

type RunResult struct {
	RunID         string            `json:"run_id"`
	Status        string            `json:"status"`
	Phases        []PhaseResult     `json:"phases"`
	ArtifactPaths map[string]string `json:"artifact_paths"`
	Summary       string            `json:"summary"`
}
