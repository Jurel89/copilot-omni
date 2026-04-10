package artifact

import (
	"os"
	"path/filepath"
	"strings"
)

func ReadFile(repoRoot, runID, filename string) ([]byte, error) {
	artifactPath, err := safeRunArtifactPath(repoRoot, runID, filename)
	if err != nil {
		return nil, err
	}

	return safeReadPath(artifactPath)
}

func safeReadPath(path string) ([]byte, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, &Error{Code: "artifact_not_found", Path: path, Err: err}
		}

		return nil, &Error{Code: "read_artifact_failed", Path: path, Err: err}
	}

	return data, nil
}

func safeRunArtifactPath(repoRoot, runID, filename string) (string, error) {
	if strings.TrimSpace(repoRoot) == "" {
		return "", &Error{Code: "invalid_repo_root", Path: repoRoot}
	}

	if !isValidRunID(runID) {
		return "", &Error{Code: "invalid_run_id", Path: runID}
	}

	if strings.TrimSpace(filename) == "" {
		return "", &Error{Code: "invalid_filename", Path: filename}
	}

	if filepath.IsAbs(filename) {
		return "", &Error{Code: "absolute_path_rejected", Path: filename}
	}

	runDir := filepath.Clean(RunDir(repoRoot, runID))
	candidatePath := filepath.Clean(filepath.Join(runDir, filename))
	if candidatePath != runDir && !strings.HasPrefix(candidatePath, runDir+string(os.PathSeparator)) {
		return "", &Error{Code: "path_escape_rejected", Path: filename}
	}

	return candidatePath, nil
}
