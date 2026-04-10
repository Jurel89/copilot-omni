package subtask

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

const (
	ModeReadOnly = "read_only"
	ModeWrite    = "write"

	StatusPending   = "pending"
	StatusRunning   = "running"
	StatusCompleted = "completed"
	StatusFailed    = "failed"
	StatusDiscarded = "discarded"
)

type Subtask struct {
	ID              string   `json:"id"`
	Title           string   `json:"title"`
	Description     string   `json:"description"`
	Mode            string   `json:"mode"`
	Dependencies    []string `json:"dependencies"`
	FileTargets     []string `json:"file_targets,omitempty"`
	VerificationCmd string   `json:"verification_cmd,omitempty"`
	OutputContract  string   `json:"output_contract,omitempty"`
	Status          string   `json:"status"`
	WorkspacePath   string   `json:"workspace_path,omitempty"`
	StartedAt       string   `json:"started_at,omitempty"`
	CompletedAt     string   `json:"completed_at,omitempty"`
	Error           string   `json:"error,omitempty"`
}

type Manifest struct {
	RunID      string    `json:"run_id"`
	ParentTask string    `json:"parent_task"`
	Subtasks   []Subtask `json:"subtasks"`
	CreatedAt  string    `json:"created_at"`
}

type ManifestResult struct {
	RunID      string          `json:"run_id"`
	ParentTask string          `json:"parent_task"`
	Results    []SubtaskResult `json:"results"`
}

type SubtaskResult struct {
	ID         string `json:"id"`
	Status     string `json:"status"`
	Output     string `json:"output,omitempty"`
	Error      string `json:"error,omitempty"`
	DurationMs int64  `json:"duration_ms,omitempty"`
}

func NewManifest(runID, parentTask string) *Manifest {
	return &Manifest{
		RunID:      runID,
		ParentTask: parentTask,
		Subtasks:   make([]Subtask, 0),
		CreatedAt:  time.Now().UTC().Format(time.RFC3339),
	}
}

func (m *Manifest) AddSubtask(sub Subtask) error {
	if strings.TrimSpace(sub.ID) == "" {
		return fmt.Errorf("subtask id is required")
	}
	for _, existing := range m.Subtasks {
		if existing.ID == sub.ID {
			return fmt.Errorf("duplicate subtask id: %s", sub.ID)
		}
	}
	if sub.Status == "" {
		sub.Status = StatusPending
	}
	m.Subtasks = append(m.Subtasks, sub)
	return nil
}

func (m *Manifest) ReadySubtasks() []*Subtask {
	completed := make(map[string]bool, len(m.Subtasks))
	for _, sub := range m.Subtasks {
		if sub.Status == StatusCompleted {
			completed[sub.ID] = true
		}
	}

	var ready []*Subtask
	for i := range m.Subtasks {
		sub := &m.Subtasks[i]
		if sub.Status != StatusPending {
			continue
		}
		allDepsMet := true
		for _, dep := range sub.Dependencies {
			if !completed[dep] {
				allDepsMet = false
				break
			}
		}
		if allDepsMet {
			ready = append(ready, sub)
		}
	}

	sort.Slice(ready, func(i, j int) bool {
		return ready[i].ID < ready[j].ID
	})
	return ready
}

func (m *Manifest) AllCompleted() bool {
	for _, sub := range m.Subtasks {
		if sub.Status != StatusCompleted && sub.Status != StatusDiscarded {
			return false
		}
	}
	return true
}

func (m *Manifest) ReadOnlySubtasks() []*Subtask {
	var result []*Subtask
	for i := range m.Subtasks {
		if m.Subtasks[i].Mode == ModeReadOnly {
			result = append(result, &m.Subtasks[i])
		}
	}
	return result
}

func (m *Manifest) WriteSubtasks() []*Subtask {
	var result []*Subtask
	for i := range m.Subtasks {
		if m.Subtasks[i].Mode == ModeWrite {
			result = append(result, &m.Subtasks[i])
		}
	}
	return result
}

func WriteManifest(repoRoot, runID string, manifest *Manifest) (string, error) {
	if manifest == nil {
		return "", fmt.Errorf("manifest is nil")
	}

	dir := filepath.Join(repoRoot, ".omni", "runs", runID)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", fmt.Errorf("create run directory: %w", err)
	}

	path := filepath.Join(dir, "subtask-manifest.json")
	payload, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return "", fmt.Errorf("marshal subtask manifest: %w", err)
	}

	if err := os.WriteFile(path, payload, 0o644); err != nil {
		return "", fmt.Errorf("write subtask manifest: %w", err)
	}

	return path, nil
}

func ReadManifest(repoRoot, runID string) (*Manifest, error) {
	path := filepath.Join(repoRoot, ".omni", "runs", runID, "subtask-manifest.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read subtask manifest: %w", err)
	}

	var manifest Manifest
	if err := json.Unmarshal(data, &manifest); err != nil {
		return nil, fmt.Errorf("decode subtask manifest: %w", err)
	}

	return &manifest, nil
}

func UpdateSubtaskStatus(repoRoot, runID, subtaskID, status string) error {
	manifest, err := ReadManifest(repoRoot, runID)
	if err != nil {
		return err
	}

	found := false
	for i := range manifest.Subtasks {
		if manifest.Subtasks[i].ID == subtaskID {
			manifest.Subtasks[i].Status = status
			now := time.Now().UTC().Format(time.RFC3339)
			if status == StatusRunning {
				manifest.Subtasks[i].StartedAt = now
			} else if status == StatusCompleted || status == StatusFailed || status == StatusDiscarded {
				manifest.Subtasks[i].CompletedAt = now
			}
			found = true
			break
		}
	}

	if !found {
		return fmt.Errorf("subtask %s not found in manifest for run %s", subtaskID, runID)
	}

	_, err = WriteManifest(repoRoot, runID, manifest)
	return err
}
