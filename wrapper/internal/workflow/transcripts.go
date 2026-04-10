package workflow

import (
	"fmt"
	"os"
	"path/filepath"
)

func WriteTranscript(repoRoot, runID, phase, content string) error {
	transcriptPath := transcriptPath(repoRoot, runID, phase)
	if err := os.MkdirAll(filepath.Dir(transcriptPath), 0o755); err != nil {
		return fmt.Errorf("create transcript directory: %w", err)
	}
	if err := os.WriteFile(transcriptPath, []byte(content), 0o644); err != nil {
		return fmt.Errorf("write transcript %s: %w", phase, err)
	}
	return nil
}

func ReadTranscript(repoRoot, runID, phase string) (string, error) {
	data, err := os.ReadFile(transcriptPath(repoRoot, runID, phase))
	if err != nil {
		return "", fmt.Errorf("read transcript %s: %w", phase, err)
	}
	return string(data), nil
}

func transcriptPath(repoRoot, runID, phase string) string {
	return filepath.Join(repoRoot, ".omni", "runs", runID, "transcripts", phase+".md")
}
