package memory

import (
	"encoding/json"
	"fmt"

	"github.com/copilot-omni/sidecar/internal/artifact"
	"github.com/copilot-omni/sidecar/internal/run"
)

type HydrationBundle struct {
	RunID           string         `json:"run_id"`
	CurrentRun      *RunContext    `json:"current_run"`
	RecentDecisions []ScoredRecord `json:"recent_decisions"`
	RelatedRuns     []ScoredRecord `json:"related_runs"`
	ProjectNotes    []ScoredRecord `json:"project_notes"`
	Summary         string         `json:"summary"`
}

type RunContext struct {
	Status       string   `json:"status"`
	CurrentPhase string   `json:"current_phase"`
	LastAction   string   `json:"last_completed_action"`
	Prompt       string   `json:"prompt"`
	Blockers     []string `json:"blockers,omitempty"`
}

func HydrateContext(store *Store, repoRoot, runID string) (*HydrationBundle, error) {
	if store == nil {
		return nil, &Error{Code: "nil_store"}
	}

	bundle := &HydrationBundle{
		RunID: runID,
	}

	artStore := artifact.NewStore(repoRoot)
	runObj, err := artStore.ReadRun(runID)
	if err == nil && runObj != nil {
		bundle.CurrentRun = &RunContext{
			Status:       string(runObj.Status),
			CurrentPhase: runObj.CurrentPhase,
			LastAction:   runObj.LastCompletedAction,
			Prompt:       runObj.Prompt,
			Blockers:     cloneTags(runObj.Blockers),
		}
	}

	decisions, _ := store.Search(SearchQuery{
		Type:  TypeDecision,
		Scope: ScopeProject,
		Limit: 5,
	})
	if decisions != nil {
		bundle.RecentDecisions = decisions.Records
	}

	runRecords, _ := store.Search(SearchQuery{
		Type:  TypeSummary,
		Scope: ScopeProject,
		Limit: 5,
	})
	if runRecords != nil {
		bundle.RelatedRuns = runRecords.Records
	}

	notes, _ := store.Search(SearchQuery{
		Type:  TypeNote,
		Scope: ScopeProject,
		Limit: 5,
	})
	if notes != nil {
		bundle.ProjectNotes = notes.Records
	}

	if bundle.CurrentRun != nil {
		summary := run.Summarize(runObj)
		if summary != nil {
			bundle.Summary = fmt.Sprintf(
				"Resuming run %s at phase %s (status: %s). Next action: %s",
				runID, summary.CurrentPhase, summary.Status, summary.NextSafeAction,
			)
		}
	}

	return bundle, nil
}

func HydrateContextJSON(store *Store, repoRoot, runID string) ([]byte, error) {
	bundle, err := HydrateContext(store, repoRoot, runID)
	if err != nil {
		return nil, err
	}

	data, err := json.MarshalIndent(bundle, "", "  ")
	if err != nil {
		return nil, &Error{Code: "hydrate_marshal_failed", Err: err}
	}

	return data, nil
}
