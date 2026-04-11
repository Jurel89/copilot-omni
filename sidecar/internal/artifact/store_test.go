package artifact

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"

	runpkg "github.com/copilot-omni/sidecar/internal/run"
)

var testRunCreatedAt = time.Date(2026, time.April, 11, 10, 0, 0, 0, time.UTC)

func newTestRun(runID string) *runpkg.Run {
	return &runpkg.Run{
		ID:                  runID,
		Status:              runpkg.StatusDraft,
		CurrentPhase:        "discuss",
		Prompt:              "Write comprehensive artifact store tests",
		CreatedAt:           testRunCreatedAt,
		UpdatedAt:           testRunCreatedAt.Add(5 * time.Minute),
		Profile:             "default",
		LastCompletedAction: "created",
		Blockers:            []string{"waiting-for-review"},
		ArtifactPaths: map[string]string{
			"spec": "specs/" + runID + ".md",
		},
	}
}

func newTestStore(t *testing.T) (*Store, string) {
	t.Helper()

	repoRoot := t.TempDir()
	return NewStore(repoRoot), repoRoot
}

func assertArtifactError(t *testing.T, err error, wantCode string) *Error {
	t.Helper()

	if err == nil {
		t.Fatal("expected error, got nil")
	}

	var artifactErr *Error
	if !errors.As(err, &artifactErr) {
		t.Fatalf("expected *Error, got %T", err)
	}

	if artifactErr.Code != wantCode {
		t.Fatalf("expected error code %q, got %q", wantCode, artifactErr.Code)
	}

	return artifactErr
}

func TestNewStore(t *testing.T) {
	repoRoot := t.TempDir()

	store := NewStore(repoRoot)
	if store == nil {
		t.Fatal("expected store, got nil")
	}

	if store.repoRoot != repoRoot {
		t.Errorf("expected repoRoot %q, got %q", repoRoot, store.repoRoot)
	}
}

func TestStore_WriteRun(t *testing.T) {
	t.Run("happy path", func(t *testing.T) {
		store, repoRoot := newTestStore(t)
		wantRun := newTestRun("run-123")

		if err := store.WriteRun(wantRun); err != nil {
			t.Fatalf("write run failed: %v", err)
		}

		payload, err := os.ReadFile(RunFilePath(repoRoot, wantRun.ID))
		if err != nil {
			t.Fatalf("read written run failed: %v", err)
		}

		var gotRun runpkg.Run
		if err := json.Unmarshal(payload, &gotRun); err != nil {
			t.Fatalf("unmarshal written run failed: %v", err)
		}

		if !reflect.DeepEqual(gotRun, *wantRun) {
			t.Errorf("written run mismatch: got %+v want %+v", gotRun, *wantRun)
		}
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store

		err := store.WriteRun(newTestRun("run-123"))
		assertArtifactError(t, err, "nil_store")
	})

	t.Run("nil run", func(t *testing.T) {
		store, repoRoot := newTestStore(t)

		err := store.WriteRun(nil)
		assertArtifactError(t, err, "nil_run")

		if _, statErr := os.Stat(filepath.Join(repoRoot, ".omni")); !os.IsNotExist(statErr) {
			t.Fatalf("expected no artifacts to be created, stat error: %v", statErr)
		}
	})

	t.Run("invalid run ids", func(t *testing.T) {
		store, repoRoot := newTestStore(t)

		tests := []struct {
			name  string
			runID string
		}{
			{name: "empty", runID: ""},
			{name: "missing suffix", runID: "run-"},
			{name: "missing prefix", runID: "task-123"},
			{name: "path traversal", runID: "run-../escape"},
		}

		for _, tt := range tests {
			t.Run(tt.name, func(t *testing.T) {
				err := store.WriteRun(newTestRun(tt.runID))
				artifactErr := assertArtifactError(t, err, "invalid_run_id")
				if artifactErr.Path != tt.runID {
					t.Errorf("expected error path %q, got %q", tt.runID, artifactErr.Path)
				}
			})
		}

		if _, statErr := os.Stat(filepath.Join(repoRoot, ".omni")); !os.IsNotExist(statErr) {
			t.Fatalf("expected no artifacts to be created, stat error: %v", statErr)
		}
	})
}

func TestStore_ReadRun(t *testing.T) {
	t.Run("happy path", func(t *testing.T) {
		store, repoRoot := newTestStore(t)
		wantRun := newTestRun("run-123")

		if err := store.WriteRun(wantRun); err != nil {
			t.Fatalf("write run failed: %v", err)
		}

		gotRun, err := store.ReadRun(wantRun.ID)
		if err != nil {
			t.Fatalf("read run failed: %v", err)
		}

		if !reflect.DeepEqual(gotRun, wantRun) {
			t.Errorf("read run mismatch: got %+v want %+v", gotRun, wantRun)
		}

		if gotRun.ID != filepath.Base(filepath.Dir(RunFilePath(repoRoot, wantRun.ID))) {
			t.Errorf("expected run ID %q, got %q", wantRun.ID, gotRun.ID)
		}
	})

	t.Run("not found", func(t *testing.T) {
		store, repoRoot := newTestStore(t)

		gotRun, err := store.ReadRun("run-404")
		if gotRun != nil {
			t.Fatalf("expected nil run, got %+v", gotRun)
		}

		artifactErr := assertArtifactError(t, err, "artifact_not_found")
		wantPath := RunFilePath(repoRoot, "run-404")
		if artifactErr.Path != wantPath {
			t.Errorf("expected error path %q, got %q", wantPath, artifactErr.Path)
		}
		if !errors.Is(err, os.ErrNotExist) {
			t.Errorf("expected wrapped os.ErrNotExist, got %v", err)
		}
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store

		gotRun, err := store.ReadRun("run-123")
		if gotRun != nil {
			t.Fatalf("expected nil run, got %+v", gotRun)
		}
		assertArtifactError(t, err, "nil_store")
	})

	t.Run("invalid run ids", func(t *testing.T) {
		store, repoRoot := newTestStore(t)

		tests := []struct {
			name  string
			runID string
		}{
			{name: "empty", runID: ""},
			{name: "missing prefix", runID: "123"},
			{name: "dot dot", runID: ".."},
			{name: "nested path", runID: "run-sub/dir"},
		}

		for _, tt := range tests {
			t.Run(tt.name, func(t *testing.T) {
				gotRun, err := store.ReadRun(tt.runID)
				if gotRun != nil {
					t.Fatalf("expected nil run, got %+v", gotRun)
				}

				artifactErr := assertArtifactError(t, err, "invalid_run_id")
				if artifactErr.Path != tt.runID {
					t.Errorf("expected error path %q, got %q", tt.runID, artifactErr.Path)
				}
			})
		}

		if _, statErr := os.Stat(filepath.Join(repoRoot, ".omni")); !os.IsNotExist(statErr) {
			t.Fatalf("expected no artifacts to be created, stat error: %v", statErr)
		}
	})
}

func TestStore_WriteSpecReadSpec(t *testing.T) {
	t.Run("round trip", func(t *testing.T) {
		store, repoRoot := newTestStore(t)
		runID := "run-123"
		wantContent := "# Spec\n\n- cover edge cases\n"

		if err := store.WriteSpec(runID, wantContent); err != nil {
			t.Fatalf("write spec failed: %v", err)
		}

		gotContent, err := store.ReadSpec(runID)
		if err != nil {
			t.Fatalf("read spec failed: %v", err)
		}

		if gotContent != wantContent {
			t.Errorf("expected content %q, got %q", wantContent, gotContent)
		}

		payload, err := os.ReadFile(SpecPath(repoRoot, runID))
		if err != nil {
			t.Fatalf("read spec from disk failed: %v", err)
		}

		if string(payload) != wantContent {
			t.Errorf("expected on-disk content %q, got %q", wantContent, string(payload))
		}
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store

		err := store.WriteSpec("run-123", "content")
		assertArtifactError(t, err, "nil_store")

		gotContent, readErr := store.ReadSpec("run-123")
		if gotContent != "" {
			t.Fatalf("expected empty content, got %q", gotContent)
		}
		assertArtifactError(t, readErr, "nil_store")
	})

	t.Run("invalid run ids", func(t *testing.T) {
		store, repoRoot := newTestStore(t)

		tests := []struct {
			name  string
			runID string
		}{
			{name: "empty", runID: ""},
			{name: "missing prefix", runID: "spec-123"},
			{name: "path traversal", runID: "run-../escape"},
		}

		for _, tt := range tests {
			t.Run(tt.name, func(t *testing.T) {
				writeErr := store.WriteSpec(tt.runID, "content")
				writeArtifactErr := assertArtifactError(t, writeErr, "invalid_run_id")
				if writeArtifactErr.Path != tt.runID {
					t.Errorf("expected write error path %q, got %q", tt.runID, writeArtifactErr.Path)
				}

				gotContent, readErr := store.ReadSpec(tt.runID)
				if gotContent != "" {
					t.Fatalf("expected empty content, got %q", gotContent)
				}

				readArtifactErr := assertArtifactError(t, readErr, "invalid_run_id")
				if readArtifactErr.Path != tt.runID {
					t.Errorf("expected read error path %q, got %q", tt.runID, readArtifactErr.Path)
				}
			})
		}

		if _, statErr := os.Stat(filepath.Join(repoRoot, ".omni")); !os.IsNotExist(statErr) {
			t.Fatalf("expected no artifacts to be created, stat error: %v", statErr)
		}
	})
}

func TestStore_WritePlanReadPlan(t *testing.T) {
	t.Run("round trip", func(t *testing.T) {
		store, repoRoot := newTestStore(t)
		runID := "run-123"
		wantPlan := map[string]any{
			"goal":     "ship tests",
			"priority": float64(1),
			"steps":    []any{"read", "write", "verify"},
			"metadata": map[string]any{"approved": true},
		}

		if err := store.WritePlan(runID, wantPlan); err != nil {
			t.Fatalf("write plan failed: %v", err)
		}

		gotPlan, err := store.ReadPlan(runID)
		if err != nil {
			t.Fatalf("read plan failed: %v", err)
		}

		if !reflect.DeepEqual(gotPlan, wantPlan) {
			t.Errorf("plan mismatch: got %#v want %#v", gotPlan, wantPlan)
		}

		payload, err := os.ReadFile(PlanPath(repoRoot, runID))
		if err != nil {
			t.Fatalf("read plan from disk failed: %v", err)
		}

		var onDisk map[string]any
		if err := json.Unmarshal(payload, &onDisk); err != nil {
			t.Fatalf("unmarshal on-disk plan failed: %v", err)
		}

		if !reflect.DeepEqual(onDisk, wantPlan) {
			t.Errorf("on-disk plan mismatch: got %#v want %#v", onDisk, wantPlan)
		}
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store

		err := store.WritePlan("run-123", map[string]any{"goal": "tests"})
		assertArtifactError(t, err, "nil_store")

		gotPlan, readErr := store.ReadPlan("run-123")
		if gotPlan != nil {
			t.Fatalf("expected nil plan, got %#v", gotPlan)
		}
		assertArtifactError(t, readErr, "nil_store")
	})

	t.Run("invalid run ids", func(t *testing.T) {
		store, repoRoot := newTestStore(t)
		plan := map[string]any{"goal": "tests"}

		tests := []struct {
			name  string
			runID string
		}{
			{name: "empty", runID: ""},
			{name: "missing suffix", runID: "run-"},
			{name: "nested path", runID: "run-123/plan"},
		}

		for _, tt := range tests {
			t.Run(tt.name, func(t *testing.T) {
				writeErr := store.WritePlan(tt.runID, plan)
				writeArtifactErr := assertArtifactError(t, writeErr, "invalid_run_id")
				if writeArtifactErr.Path != tt.runID {
					t.Errorf("expected write error path %q, got %q", tt.runID, writeArtifactErr.Path)
				}

				gotPlan, readErr := store.ReadPlan(tt.runID)
				if gotPlan != nil {
					t.Fatalf("expected nil plan, got %#v", gotPlan)
				}

				readArtifactErr := assertArtifactError(t, readErr, "invalid_run_id")
				if readArtifactErr.Path != tt.runID {
					t.Errorf("expected read error path %q, got %q", tt.runID, readArtifactErr.Path)
				}
			})
		}

		if _, statErr := os.Stat(filepath.Join(repoRoot, ".omni")); !os.IsNotExist(statErr) {
			t.Fatalf("expected no artifacts to be created, stat error: %v", statErr)
		}
	})
}

func TestStore_WriteDecisionsReadDecisions(t *testing.T) {
	t.Run("round trip", func(t *testing.T) {
		store, repoRoot := newTestStore(t)
		runID := "run-123"
		wantContent := "# Decisions\n\n- Keep tests table-driven.\n"

		if err := store.WriteDecisions(runID, wantContent); err != nil {
			t.Fatalf("write decisions failed: %v", err)
		}

		gotContent, err := store.ReadDecisions(runID)
		if err != nil {
			t.Fatalf("read decisions failed: %v", err)
		}

		if gotContent != wantContent {
			t.Errorf("expected content %q, got %q", wantContent, gotContent)
		}

		payload, err := os.ReadFile(DecisionsPath(repoRoot, runID))
		if err != nil {
			t.Fatalf("read decisions from disk failed: %v", err)
		}

		if string(payload) != wantContent {
			t.Errorf("expected on-disk content %q, got %q", wantContent, string(payload))
		}
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store

		err := store.WriteDecisions("run-123", "content")
		assertArtifactError(t, err, "nil_store")

		gotContent, readErr := store.ReadDecisions("run-123")
		if gotContent != "" {
			t.Fatalf("expected empty content, got %q", gotContent)
		}
		assertArtifactError(t, readErr, "nil_store")
	})

	t.Run("invalid run ids", func(t *testing.T) {
		store, repoRoot := newTestStore(t)

		tests := []struct {
			name  string
			runID string
		}{
			{name: "empty", runID: ""},
			{name: "missing prefix", runID: "decision-123"},
			{name: "windows separator", runID: `run-123\\decisions`},
		}

		for _, tt := range tests {
			t.Run(tt.name, func(t *testing.T) {
				writeErr := store.WriteDecisions(tt.runID, "content")
				writeArtifactErr := assertArtifactError(t, writeErr, "invalid_run_id")
				if writeArtifactErr.Path != tt.runID {
					t.Errorf("expected write error path %q, got %q", tt.runID, writeArtifactErr.Path)
				}

				gotContent, readErr := store.ReadDecisions(tt.runID)
				if gotContent != "" {
					t.Fatalf("expected empty content, got %q", gotContent)
				}

				readArtifactErr := assertArtifactError(t, readErr, "invalid_run_id")
				if readArtifactErr.Path != tt.runID {
					t.Errorf("expected read error path %q, got %q", tt.runID, readArtifactErr.Path)
				}
			})
		}

		if _, statErr := os.Stat(filepath.Join(repoRoot, ".omni")); !os.IsNotExist(statErr) {
			t.Fatalf("expected no artifacts to be created, stat error: %v", statErr)
		}
	})
}

func TestStore_WriteTranscriptReadTranscript(t *testing.T) {
	t.Run("round trip", func(t *testing.T) {
		store, repoRoot := newTestStore(t)
		runID := "run-123"
		phase := "discuss"
		wantContent := "# Transcript\n\nUser asked for tests.\n"

		if err := store.WriteTranscript(runID, phase, wantContent); err != nil {
			t.Fatalf("write transcript failed: %v", err)
		}

		gotContent, err := store.ReadTranscript(runID, phase)
		if err != nil {
			t.Fatalf("read transcript failed: %v", err)
		}

		if gotContent != wantContent {
			t.Errorf("expected content %q, got %q", wantContent, gotContent)
		}

		payload, err := os.ReadFile(TranscriptPath(repoRoot, runID, phase))
		if err != nil {
			t.Fatalf("read transcript from disk failed: %v", err)
		}

		if string(payload) != wantContent {
			t.Errorf("expected on-disk content %q, got %q", wantContent, string(payload))
		}
	})

	t.Run("invalid phase", func(t *testing.T) {
		store, repoRoot := newTestStore(t)
		runID := "run-123"

		tests := []struct {
			name  string
			phase string
		}{
			{name: "empty", phase: ""},
			{name: "dot dot", phase: ".."},
			{name: "nested path", phase: "../plan"},
			{name: "absolute path", phase: "/tmp/discuss"},
		}

		for _, tt := range tests {
			t.Run(tt.name, func(t *testing.T) {
				writeErr := store.WriteTranscript(runID, tt.phase, "content")
				writeArtifactErr := assertArtifactError(t, writeErr, "invalid_transcript_phase")
				if writeArtifactErr.Path != tt.phase {
					t.Errorf("expected write error path %q, got %q", tt.phase, writeArtifactErr.Path)
				}

				gotContent, readErr := store.ReadTranscript(runID, tt.phase)
				if gotContent != "" {
					t.Fatalf("expected empty content, got %q", gotContent)
				}

				readArtifactErr := assertArtifactError(t, readErr, "invalid_transcript_phase")
				if readArtifactErr.Path != tt.phase {
					t.Errorf("expected read error path %q, got %q", tt.phase, readArtifactErr.Path)
				}
			})
		}

		if _, statErr := os.Stat(filepath.Join(repoRoot, ".omni")); !os.IsNotExist(statErr) {
			t.Fatalf("expected no artifacts to be created, stat error: %v", statErr)
		}
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store

		err := store.WriteTranscript("run-123", "discuss", "content")
		assertArtifactError(t, err, "nil_store")

		gotContent, readErr := store.ReadTranscript("run-123", "discuss")
		if gotContent != "" {
			t.Fatalf("expected empty content, got %q", gotContent)
		}
		assertArtifactError(t, readErr, "nil_store")
	})
}

func TestStore_ListRunArtifacts(t *testing.T) {
	t.Run("empty", func(t *testing.T) {
		store, repoRoot := newTestStore(t)

		artifacts, err := store.ListRunArtifacts("run-123")
		if err != nil {
			t.Fatalf("list run artifacts failed: %v", err)
		}

		if artifacts == nil {
			t.Fatal("expected non-nil map, got nil")
		}

		if len(artifacts) != 0 {
			t.Errorf("expected no artifacts, got %#v", artifacts)
		}

		if _, statErr := os.Stat(filepath.Join(repoRoot, ".omni")); !os.IsNotExist(statErr) {
			t.Fatalf("expected no artifacts to be created, stat error: %v", statErr)
		}
	})

	t.Run("with artifacts", func(t *testing.T) {
		store, repoRoot := newTestStore(t)
		runID := "run-123"

		if err := store.WriteRun(newTestRun(runID)); err != nil {
			t.Fatalf("write run failed: %v", err)
		}
		if err := store.WriteSpec(runID, "spec"); err != nil {
			t.Fatalf("write spec failed: %v", err)
		}
		if err := store.WritePlan(runID, map[string]any{"goal": "tests"}); err != nil {
			t.Fatalf("write plan failed: %v", err)
		}
		if err := store.WriteDecisions(runID, "decisions"); err != nil {
			t.Fatalf("write decisions failed: %v", err)
		}

		artifacts, err := store.ListRunArtifacts(runID)
		if err != nil {
			t.Fatalf("list run artifacts failed: %v", err)
		}

		wantArtifacts := map[string]string{
			"run":      RunFilePath(repoRoot, runID),
			"spec":     SpecPath(repoRoot, runID),
			"plan":     PlanPath(repoRoot, runID),
			"decision": DecisionsPath(repoRoot, runID),
		}

		if !reflect.DeepEqual(artifacts, wantArtifacts) {
			t.Errorf("artifacts mismatch: got %#v want %#v", artifacts, wantArtifacts)
		}
	})

	t.Run("with transcripts", func(t *testing.T) {
		store, repoRoot := newTestStore(t)
		runID := "run-123"

		if err := store.WriteTranscript(runID, "plan", "plan transcript"); err != nil {
			t.Fatalf("write plan transcript failed: %v", err)
		}
		if err := store.WriteTranscript(runID, "discuss", "discuss transcript"); err != nil {
			t.Fatalf("write discuss transcript failed: %v", err)
		}

		transcriptDir := TranscriptDir(repoRoot, runID)
		if err := os.MkdirAll(filepath.Join(transcriptDir, "ignored"), 0o755); err != nil {
			t.Fatalf("create ignored transcript directory failed: %v", err)
		}
		if err := os.WriteFile(filepath.Join(transcriptDir, "notes.txt"), []byte("ignore me"), 0o644); err != nil {
			t.Fatalf("write ignored transcript file failed: %v", err)
		}

		artifacts, err := store.ListRunArtifacts(runID)
		if err != nil {
			t.Fatalf("list run artifacts failed: %v", err)
		}

		wantArtifacts := map[string]string{
			"transcript:discuss": TranscriptPath(repoRoot, runID, "discuss"),
			"transcript:plan":    TranscriptPath(repoRoot, runID, "plan"),
		}

		if !reflect.DeepEqual(artifacts, wantArtifacts) {
			t.Errorf("artifacts mismatch: got %#v want %#v", artifacts, wantArtifacts)
		}
	})
}

func TestIsValidRunID(t *testing.T) {
	tests := []struct {
		name  string
		runID string
		want  bool
	}{
		{name: "valid run id", runID: "run-123", want: true},
		{name: "invalid dot dot", runID: "..", want: false},
		{name: "invalid without prefix", runID: "123", want: false},
		{name: "empty", runID: "", want: false},
		{name: "path traversal", runID: "run-../secret", want: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := isValidRunID(tt.runID)
			if got != tt.want {
				t.Errorf("expected %v, got %v for runID %q", tt.want, got, tt.runID)
			}
		})
	}
}

func TestIsValidPhase(t *testing.T) {
	tests := []struct {
		name  string
		phase string
		want  bool
	}{
		{name: "valid phase", phase: "discuss", want: true},
		{name: "invalid dot dot", phase: "..", want: false},
		{name: "invalid absolute path", phase: "/tmp/discuss", want: false},
		{name: "nested path", phase: "phase/discuss", want: false},
		{name: "empty", phase: "", want: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := isValidPhase(tt.phase)
			if got != tt.want {
				t.Errorf("expected %v, got %v for phase %q", tt.want, got, tt.phase)
			}
		})
	}
}

func TestSafeRunArtifactPath_RejectsPathTraversalRunIDs(t *testing.T) {
	repoRoot := t.TempDir()

	tests := []struct {
		name  string
		runID string
	}{
		{name: "dot dot segment", runID: "run-../escape"},
		{name: "forward slash", runID: "run-child/escape"},
		{name: "backslash", runID: `run-child\\escape`},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotPath, err := safeRunArtifactPath(repoRoot, tt.runID, "run.json")
			if gotPath != "" {
				t.Fatalf("expected empty path, got %q", gotPath)
			}

			artifactErr := assertArtifactError(t, err, "invalid_run_id")
			if artifactErr.Path != tt.runID {
				t.Errorf("expected error path %q, got %q", tt.runID, artifactErr.Path)
			}
		})
	}
}

func TestError_Behavior(t *testing.T) {
	t.Run("error string formatting", func(t *testing.T) {
		boom := errors.New("boom")

		tests := []struct {
			name string
			err  *Error
			want string
		}{
			{name: "nil receiver", err: nil, want: ""},
			{name: "code only", err: &Error{Code: "invalid_run_id"}, want: "invalid_run_id"},
			{name: "code and path", err: &Error{Code: "invalid_run_id", Path: "run-123"}, want: "invalid_run_id: run-123"},
			{name: "code and wrapped error", err: &Error{Code: "read_artifact_failed", Err: boom}, want: "read_artifact_failed: boom"},
			{name: "code path and wrapped error", err: &Error{Code: "read_artifact_failed", Path: "/tmp/file", Err: boom}, want: "read_artifact_failed: /tmp/file: boom"},
		}

		for _, tt := range tests {
			t.Run(tt.name, func(t *testing.T) {
				got := tt.err.Error()
				if got != tt.want {
					t.Errorf("expected %q, got %q", tt.want, got)
				}
			})
		}
	})

	t.Run("unwrap", func(t *testing.T) {
		boom := errors.New("boom")
		artifactErr := &Error{Code: "read_artifact_failed", Path: "artifact.txt", Err: boom}

		if !errors.Is(artifactErr, boom) {
			t.Fatal("expected errors.Is to match wrapped error")
		}

		if errors.Unwrap(artifactErr) != boom {
			t.Fatalf("expected unwrap to return %v", boom)
		}

		var nilErr *Error
		if nilErr.Unwrap() != nil {
			t.Fatal("expected nil receiver unwrap to return nil")
		}
	})
}
