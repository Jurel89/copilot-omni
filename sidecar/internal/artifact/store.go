package artifact

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"

	runpkg "github.com/copilot-omni/sidecar/internal/run"
)

type Store struct {
	repoRoot string
}

func NewStore(repoRoot string) *Store {
	return &Store{repoRoot: repoRoot}
}

func (s *Store) WriteRun(run *runpkg.Run) error {
	if s == nil {
		return &Error{Code: "nil_store"}
	}

	if run == nil {
		return &Error{Code: "nil_run"}
	}

	if !isValidRunID(run.ID) {
		return &Error{Code: "invalid_run_id", Path: run.ID}
	}

	payload, err := json.MarshalIndent(run, "", "  ")
	if err != nil {
		return &Error{Code: "marshal_run_failed", Path: run.ID, Err: err}
	}

	return WriteFile(RunFilePath(s.repoRoot, run.ID), payload)
}

func (s *Store) ReadRun(runID string) (*runpkg.Run, error) {
	if s == nil {
		return nil, &Error{Code: "nil_store"}
	}

	if !isValidRunID(runID) {
		return nil, &Error{Code: "invalid_run_id", Path: runID}
	}

	payload, err := safeReadPath(RunFilePath(s.repoRoot, runID))
	if err != nil {
		return nil, err
	}

	var run runpkg.Run
	if err := json.Unmarshal(payload, &run); err != nil {
		return nil, &Error{Code: "unmarshal_run_failed", Path: runID, Err: err}
	}

	return &run, nil
}

func (s *Store) WriteSpec(runID, content string) error {
	if s == nil {
		return &Error{Code: "nil_store"}
	}

	if !isValidRunID(runID) {
		return &Error{Code: "invalid_run_id", Path: runID}
	}

	return WriteFile(SpecPath(s.repoRoot, runID), []byte(content))
}

func (s *Store) ReadSpec(runID string) (string, error) {
	if s == nil {
		return "", &Error{Code: "nil_store"}
	}

	if !isValidRunID(runID) {
		return "", &Error{Code: "invalid_run_id", Path: runID}
	}

	payload, err := safeReadPath(SpecPath(s.repoRoot, runID))
	if err != nil {
		return "", err
	}

	return string(payload), nil
}

func (s *Store) WritePlan(runID string, plan map[string]interface{}) error {
	if s == nil {
		return &Error{Code: "nil_store"}
	}

	if !isValidRunID(runID) {
		return &Error{Code: "invalid_run_id", Path: runID}
	}

	payload, err := json.MarshalIndent(plan, "", "  ")
	if err != nil {
		return &Error{Code: "marshal_plan_failed", Path: runID, Err: err}
	}

	return WriteFile(PlanPath(s.repoRoot, runID), payload)
}

func (s *Store) ReadPlan(runID string) (map[string]interface{}, error) {
	if s == nil {
		return nil, &Error{Code: "nil_store"}
	}

	if !isValidRunID(runID) {
		return nil, &Error{Code: "invalid_run_id", Path: runID}
	}

	payload, err := safeReadPath(PlanPath(s.repoRoot, runID))
	if err != nil {
		return nil, err
	}

	var plan map[string]interface{}
	if err := json.Unmarshal(payload, &plan); err != nil {
		return nil, &Error{Code: "unmarshal_plan_failed", Path: runID, Err: err}
	}

	return plan, nil
}

func (s *Store) WriteDecisions(runID, content string) error {
	if s == nil {
		return &Error{Code: "nil_store"}
	}

	if !isValidRunID(runID) {
		return &Error{Code: "invalid_run_id", Path: runID}
	}

	return WriteFile(DecisionsPath(s.repoRoot, runID), []byte(content))
}

func (s *Store) ReadDecisions(runID string) (string, error) {
	if s == nil {
		return "", &Error{Code: "nil_store"}
	}

	if !isValidRunID(runID) {
		return "", &Error{Code: "invalid_run_id", Path: runID}
	}

	payload, err := safeReadPath(DecisionsPath(s.repoRoot, runID))
	if err != nil {
		return "", err
	}

	return string(payload), nil
}

func (s *Store) WriteTranscript(runID, phase, content string) error {
	if s == nil {
		return &Error{Code: "nil_store"}
	}

	if !isValidRunID(runID) {
		return &Error{Code: "invalid_run_id", Path: runID}
	}

	if !isValidPhase(phase) {
		return &Error{Code: "invalid_transcript_phase", Path: phase}
	}

	return WriteFile(TranscriptPath(s.repoRoot, runID, phase), []byte(content))
}

func (s *Store) ReadTranscript(runID, phase string) (string, error) {
	if s == nil {
		return "", &Error{Code: "nil_store"}
	}

	if !isValidRunID(runID) {
		return "", &Error{Code: "invalid_run_id", Path: runID}
	}

	if !isValidPhase(phase) {
		return "", &Error{Code: "invalid_transcript_phase", Path: phase}
	}

	payload, err := ReadFile(s.repoRoot, runID, filepath.Join("transcripts", phase+".md"))
	if err != nil {
		return "", err
	}

	return string(payload), nil
}

func (s *Store) ListRunArtifacts(runID string) (map[string]string, error) {
	if s == nil {
		return nil, &Error{Code: "nil_store"}
	}

	if !isValidRunID(runID) {
		return nil, &Error{Code: "invalid_run_id", Path: runID}
	}

	artifacts := make(map[string]string)

	knownArtifacts := map[string]string{
		"run":      RunFilePath(s.repoRoot, runID),
		"spec":     SpecPath(s.repoRoot, runID),
		"plan":     PlanPath(s.repoRoot, runID),
		"decision": DecisionsPath(s.repoRoot, runID),
	}

	for artifactType, path := range knownArtifacts {
		exists, err := pathExists(path)
		if err != nil {
			return nil, err
		}
		if exists {
			artifacts[artifactType] = path
		}
	}

	transcriptDir := TranscriptDir(s.repoRoot, runID)
	entries, err := os.ReadDir(transcriptDir)
	if err != nil {
		if !os.IsNotExist(err) {
			return nil, &Error{Code: "read_transcript_dir_failed", Path: transcriptDir, Err: err}
		}
		return artifacts, nil
	}

	phaseNames := make([]string, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".md" {
			continue
		}
		phaseNames = append(phaseNames, strings.TrimSuffix(entry.Name(), ".md"))
	}
	sort.Strings(phaseNames)

	for _, phase := range phaseNames {
		artifacts["transcript:"+phase] = TranscriptPath(s.repoRoot, runID, phase)
	}

	return artifacts, nil
}

func pathExists(path string) (bool, error) {
	_, err := os.Stat(path)
	if err == nil {
		return true, nil
	}
	if os.IsNotExist(err) {
		return false, nil
	}
	return false, &Error{Code: "stat_artifact_failed", Path: path, Err: err}
}

func isValidRunID(runID string) bool {
	runID = strings.TrimSpace(runID)
	if !strings.HasPrefix(runID, "run-") {
		return false
	}

	if strings.Contains(runID, "..") || strings.Contains(runID, "/") || strings.Contains(runID, "\\") {
		return false
	}

	trimmed := strings.TrimPrefix(runID, "run-")
	if trimmed == "" {
		return false
	}

	return true
}

func isValidPhase(phase string) bool {
	phase = strings.TrimSpace(phase)
	if phase == "" {
		return false
	}

	if filepath.IsAbs(phase) {
		return false
	}

	if phase != filepath.Base(phase) {
		return false
	}

	return !strings.Contains(phase, "..")
}
