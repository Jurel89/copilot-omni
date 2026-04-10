package merge

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type Decision struct {
	SubtaskID string `json:"subtask_id"`
	Action    string `json:"action"` // "accept", "reject", "conflict"
	Reason    string `json:"reason,omitempty"`
	Reviewer  string `json:"reviewer,omitempty"`
	Timestamp string `json:"timestamp"`
}

type MergeResult struct {
	RunID         string     `json:"run_id"`
	TotalSubtasks int        `json:"total_subtasks"`
	Accepted      int        `json:"accepted"`
	Rejected      int        `json:"rejected"`
	Conflicts     int        `json:"conflicts"`
	Decisions     []Decision `json:"decisions"`
	Summary       string     `json:"summary"`
	Timestamp     string     `json:"timestamp"`
}

type Coordinator struct {
	repoRoot string
}

func NewCoordinator(repoRoot string) *Coordinator {
	return &Coordinator{repoRoot: repoRoot}
}

func (c *Coordinator) Merge(runID string, decisions []Decision) (*MergeResult, error) {
	if strings.TrimSpace(runID) == "" {
		return nil, fmt.Errorf("run_id is required")
	}
	if len(decisions) == 0 {
		return nil, fmt.Errorf("at least one merge decision is required")
	}

	now := time.Now().UTC().Format(time.RFC3339)
	accepted := 0
	rejected := 0
	conflicts := 0

	for i := range decisions {
		if decisions[i].Timestamp == "" {
			decisions[i].Timestamp = now
		}
		switch decisions[i].Action {
		case "accept":
			accepted++
		case "reject":
			rejected++
		case "conflict":
			conflicts++
		default:
			return nil, fmt.Errorf("invalid merge action %q for subtask %s", decisions[i].Action, decisions[i].SubtaskID)
		}
	}

	result := &MergeResult{
		RunID:         runID,
		TotalSubtasks: len(decisions),
		Accepted:      accepted,
		Rejected:      rejected,
		Conflicts:     conflicts,
		Decisions:     decisions,
		Summary:       fmt.Sprintf("Merged %d subtasks: %d accepted, %d rejected, %d conflicts", len(decisions), accepted, rejected, conflicts),
		Timestamp:     now,
	}

	if err := c.writeMergeResult(runID, result); err != nil {
		return nil, err
	}

	return result, nil
}

func (c *Coordinator) ReadMergeResult(runID string) (*MergeResult, error) {
	path := filepath.Join(c.repoRoot, ".omni", "runs", runID, "merge-result.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read merge result: %w", err)
	}

	var result MergeResult
	if err := json.Unmarshal(data, &result); err != nil {
		return nil, fmt.Errorf("decode merge result: %w", err)
	}
	return &result, nil
}

func (c *Coordinator) writeMergeResult(runID string, result *MergeResult) error {
	dir := filepath.Join(c.repoRoot, ".omni", "runs", runID)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("create run directory: %w", err)
	}

	path := filepath.Join(dir, "merge-result.json")
	payload, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal merge result: %w", err)
	}

	return os.WriteFile(path, payload, 0o644)
}

func ValidateMergeDecisions(decisions []Decision) error {
	if len(decisions) == 0 {
		return fmt.Errorf("merge decisions must not be empty")
	}
	seen := make(map[string]bool, len(decisions))
	for _, d := range decisions {
		if strings.TrimSpace(d.SubtaskID) == "" {
			return fmt.Errorf("merge decision subtask_id must not be empty")
		}
		if seen[d.SubtaskID] {
			return fmt.Errorf("duplicate merge decision for subtask %s", d.SubtaskID)
		}
		seen[d.SubtaskID] = true
		if d.Action != "accept" && d.Action != "reject" && d.Action != "conflict" {
			return fmt.Errorf("invalid merge action %q for subtask %s", d.Action, d.SubtaskID)
		}
	}
	return nil
}
