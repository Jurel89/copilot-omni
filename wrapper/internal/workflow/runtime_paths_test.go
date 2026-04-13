package workflow

import (
	"context"
	"reflect"
	"testing"
	"time"

	"github.com/Jurel89/copilot-omni/wrapper/internal/copilot"
)

func TestInvokePhaseUsesTrustedPluginDir(t *testing.T) {
	repoRoot := t.TempDir()
	trustedPluginDir := t.TempDir()
	runner := NewRunner(repoRoot, trustedPluginDir, runtimePathSidecarManager{}, &capturingCopilotRunner{output: "ok"})
	copilotRunner := runner.copilotRunner.(*capturingCopilotRunner)

	if _, err := runner.invokePhase(context.Background(), "run-1", PhaseDiscuss, "prompt"); err != nil {
		t.Fatalf("invokePhase() error = %v", err)
	}

	if !reflect.DeepEqual(copilotRunner.lastOpts.AddDirs, []string{trustedPluginDir}) {
		t.Fatalf("invokePhase AddDirs = %v, want [%s]", copilotRunner.lastOpts.AddDirs, trustedPluginDir)
	}
}

func TestExecuteTaskUsesTrustedPluginDir(t *testing.T) {
	repoRoot := t.TempDir()
	trustedPluginDir := t.TempDir()
	runner := NewRunner(repoRoot, trustedPluginDir, runtimePathSidecarManager{}, &capturingCopilotRunner{output: "task complete"})
	copilotRunner := runner.copilotRunner.(*capturingCopilotRunner)
	state := &runState{ID: "run-1", Prompt: "ship the change"}
	taskInfo := map[string]any{
		"title":            "Implement trusted path usage",
		"description":      "Use the trusted plugin dir for execution",
		"file_targets":     []string{"allowed.txt"},
		"verification_cmd": "go test ./...",
	}

	if err := runner.executeTask(context.Background(), state, "task-1", taskInfo); err != nil {
		t.Fatalf("executeTask() error = %v", err)
	}

	if !reflect.DeepEqual(copilotRunner.lastOpts.AddDirs, []string{trustedPluginDir}) {
		t.Fatalf("executeTask AddDirs = %v, want [%s]", copilotRunner.lastOpts.AddDirs, trustedPluginDir)
	}
}

type capturingCopilotRunner struct {
	lastOpts copilot.RunOptions
	output   string
}

func (r *capturingCopilotRunner) Run(_ context.Context, _ string, opts copilot.RunOptions) (string, error) {
	r.lastOpts = opts
	return r.output, nil
}

type runtimePathSidecarManager struct{}

func (runtimePathSidecarManager) Start(context.Context) error { return nil }

func (runtimePathSidecarManager) HealthCheck(context.Context, time.Duration) error { return nil }

func (runtimePathSidecarManager) CallTool(_ context.Context, tool string, _ map[string]any) (string, error) {
	switch tool {
	case "omni_policy_check":
		return `{"allowed":true}`, nil
	case "omni_repo_map":
		return `{"files":[{"path":"allowed.txt"}]}`, nil
	default:
		return `{}`, nil
	}
}

func (runtimePathSidecarManager) Stop() error { return nil }

func (runtimePathSidecarManager) IsRunning() bool { return true }
