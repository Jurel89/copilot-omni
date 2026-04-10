package artifact

import (
	"fmt"
	"path/filepath"
	"strings"
)

type Error struct {
	Code string
	Path string
	Err  error
}

func (e *Error) Error() string {
	if e == nil {
		return ""
	}

	if e.Path != "" && e.Err != nil {
		return fmt.Sprintf("%s: %s: %v", e.Code, e.Path, e.Err)
	}

	if e.Path != "" {
		return fmt.Sprintf("%s: %s", e.Code, e.Path)
	}

	if e.Err != nil {
		return fmt.Sprintf("%s: %v", e.Code, e.Err)
	}

	return e.Code
}

func (e *Error) Unwrap() error {
	if e == nil {
		return nil
	}

	return e.Err
}

func RunDir(repoRoot, runID string) string {
	return filepath.Join(repoRoot, ".omni", "runs", runID)
}

func RunFilePath(repoRoot, runID string) string {
	return filepath.Join(RunDir(repoRoot, runID), "run.json")
}

func SpecPath(repoRoot, runID string) string {
	return filepath.Join(repoRoot, ".omni", "specs", runID+".md")
}

func PlanPath(repoRoot, runID string) string {
	return filepath.Join(repoRoot, ".omni", "plans", runID+".json")
}

func DecisionsPath(repoRoot, runID string) string {
	return filepath.Join(repoRoot, ".omni", "decisions", runID+".md")
}

func TranscriptDir(repoRoot, runID string) string {
	return filepath.Join(RunDir(repoRoot, runID), "transcripts")
}

func TranscriptPath(repoRoot, runID, phase string) string {
	return filepath.Join(TranscriptDir(repoRoot, runID), phase+".md")
}

func ArtifactPath(repoRoot, artifactType, runID string) (string, error) {
	switch strings.TrimSpace(strings.ToLower(artifactType)) {
	case "run":
		return RunFilePath(repoRoot, runID), nil
	case "spec":
		return SpecPath(repoRoot, runID), nil
	case "plan":
		return PlanPath(repoRoot, runID), nil
	case "decision":
		return DecisionsPath(repoRoot, runID), nil
	case "transcript":
		return "", &Error{Code: "missing_transcript_phase", Path: artifactType}
	default:
		return "", &Error{Code: "invalid_artifact_type", Path: artifactType}
	}
}
