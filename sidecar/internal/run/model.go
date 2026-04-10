package run

import "time"

type Run struct {
	ID                  string            `json:"id"`
	Status              Status            `json:"status"`
	CurrentPhase        string            `json:"current_phase"`
	Prompt              string            `json:"prompt"`
	CreatedAt           time.Time         `json:"created_at"`
	UpdatedAt           time.Time         `json:"updated_at"`
	Profile             string            `json:"profile,omitempty"`
	LastCompletedAction string            `json:"last_completed_action,omitempty"`
	Blockers            []string          `json:"blockers,omitempty"`
	ArtifactPaths       map[string]string `json:"artifact_paths,omitempty"`
}
