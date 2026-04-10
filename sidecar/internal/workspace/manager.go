package workspace

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

type IsolationType string

const (
	IsolationWorktree IsolationType = "worktree"
	IsolationTempDir  IsolationType = "tempdir"
)

type Manager struct {
	repoRoot string
}

func NewManager(repoRoot string) *Manager {
	return &Manager{repoRoot: repoRoot}
}

type Workspace struct {
	Path        string        `json:"path"`
	Isolation   IsolationType `json:"isolation"`
	SubtaskID   string        `json:"subtask_id"`
	BranchName  string        `json:"branch_name,omitempty"`
	IsWriteable bool          `json:"is_writeable"`
}

func (m *Manager) CreateWorkspace(subtaskID string, isWrite bool) (*Workspace, error) {
	if strings.TrimSpace(subtaskID) == "" {
		return nil, fmt.Errorf("subtask_id is required")
	}

	if !isWrite {
		return &Workspace{
			Path:        m.repoRoot,
			Isolation:   IsolationTempDir,
			SubtaskID:   subtaskID,
			IsWriteable: false,
		}, nil
	}

	branchName := fmt.Sprintf("omni-subtask-%s", subtaskID)
	worktreePath := filepath.Join(m.repoRoot, "..", fmt.Sprintf(".omni-worktree-%s", subtaskID))

	if err := m.createWorktree(branchName, worktreePath); err != nil {
		tempDir, tempErr := os.MkdirTemp("", "omni-subtask-"+subtaskID+"-*")
		if tempErr != nil {
			return nil, fmt.Errorf("worktree creation failed (%v) and tempdir fallback failed (%v)", err, tempErr)
		}
		return &Workspace{
			Path:        tempDir,
			Isolation:   IsolationTempDir,
			SubtaskID:   subtaskID,
			IsWriteable: true,
		}, nil
	}

	return &Workspace{
		Path:        worktreePath,
		Isolation:   IsolationWorktree,
		SubtaskID:   subtaskID,
		BranchName:  branchName,
		IsWriteable: true,
	}, nil
}

func (m *Manager) RemoveWorkspace(ws *Workspace) error {
	if ws == nil {
		return nil
	}

	if ws.Isolation == IsolationWorktree && ws.BranchName != "" {
		_ = m.removeWorktree(ws.Path, ws.BranchName)
		return nil
	}

	if ws.Isolation == IsolationTempDir && ws.IsWriteable {
		return os.RemoveAll(ws.Path)
	}

	return nil
}

func (m *Manager) createWorktree(branchName, worktreePath string) error {
	cmd := exec.Command("git", "worktree", "add", "-b", branchName, worktreePath, "HEAD")
	cmd.Dir = m.repoRoot
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("git worktree add: %s: %w", string(output), err)
	}
	return nil
}

func (m *Manager) removeWorktree(worktreePath, branchName string) error {
	cmd := exec.Command("git", "worktree", "remove", "--force", worktreePath)
	cmd.Dir = m.repoRoot
	_, _ = cmd.CombinedOutput()

	cmd = exec.Command("git", "branch", "-D", branchName)
	cmd.Dir = m.repoRoot
	_, _ = cmd.CombinedOutput()

	return nil
}

func ValidateIsolatedWorkspace(ws *Workspace, mainRepoRoot string) error {
	if ws == nil {
		return fmt.Errorf("workspace is nil")
	}
	if !ws.IsWriteable {
		if ws.Path == mainRepoRoot {
			return nil
		}
		return fmt.Errorf("read-only workspace path must be the main repo root")
	}
	if ws.Path == mainRepoRoot {
		return fmt.Errorf("write-capable workspace must not point to the main repo root")
	}
	return nil
}
