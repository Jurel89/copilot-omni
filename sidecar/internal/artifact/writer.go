package artifact

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func WriteFile(path string, data []byte) error {
	cleanedPath := filepath.Clean(path)
	if strings.TrimSpace(cleanedPath) == "" || cleanedPath == "." {
		return &Error{Code: "invalid_path", Path: path}
	}

	parentDir := filepath.Dir(cleanedPath)
	if err := os.MkdirAll(parentDir, 0o755); err != nil {
		return &Error{Code: "create_parent_dir_failed", Path: parentDir, Err: err}
	}

	tempFile, err := os.CreateTemp(parentDir, ".copilot-omni-*")
	if err != nil {
		return &Error{Code: "create_temp_file_failed", Path: cleanedPath, Err: err}
	}

	tempPath := tempFile.Name()
	defer func() {
		_ = os.Remove(tempPath)
	}()

	if err := tempFile.Chmod(0o644); err != nil {
		_ = tempFile.Close()
		return &Error{Code: "chmod_temp_file_failed", Path: tempPath, Err: err}
	}

	if _, err := tempFile.Write(data); err != nil {
		_ = tempFile.Close()
		return &Error{Code: "write_temp_file_failed", Path: tempPath, Err: err}
	}

	if err := tempFile.Sync(); err != nil {
		_ = tempFile.Close()
		return &Error{Code: "sync_temp_file_failed", Path: tempPath, Err: err}
	}

	if err := tempFile.Close(); err != nil {
		return &Error{Code: "close_temp_file_failed", Path: tempPath, Err: err}
	}

	if err := os.Rename(tempPath, cleanedPath); err != nil {
		return &Error{Code: "rename_temp_file_failed", Path: fmt.Sprintf("%s -> %s", tempPath, cleanedPath), Err: err}
	}

	return nil
}
