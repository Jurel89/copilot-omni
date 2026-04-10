package run

type RunSummary struct {
	RunID               string   `json:"run_id"`
	Status              string   `json:"status"`
	CurrentPhase        string   `json:"current_phase"`
	NextSafeAction      string   `json:"next_safe_action"`
	ArtifactCount       int      `json:"artifact_count"`
	LastCompletedAction string   `json:"last_completed_action,omitempty"`
	Blockers            []string `json:"blockers,omitempty"`
}

func Summarize(run *Run) *RunSummary {
	if run == nil {
		return nil
	}

	blockers := append([]string(nil), run.Blockers...)

	return &RunSummary{
		RunID:               run.ID,
		Status:              string(run.Status),
		CurrentPhase:        DerivePhase(run),
		NextSafeAction:      NextSafeAction(run),
		ArtifactCount:       len(run.ArtifactPaths),
		LastCompletedAction: run.LastCompletedAction,
		Blockers:            blockers,
	}
}
