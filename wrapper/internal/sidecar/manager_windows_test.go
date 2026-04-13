//go:build windows

package sidecar

import (
	"os/exec"
	"path/filepath"
	"testing"
)

func TestFindSidecarUsesWindowsExecutableNameForSourceCandidate(t *testing.T) {
	root := t.TempDir()
	exePath := writeTestBinary(t, filepath.Join(root, "wrapper", "omni.exe"))
	sourcePath := writeTestBinary(t, filepath.Join(root, "sidecar", "omni-sidecar.exe"))

	got, err := findSidecar("", exePath, func(string) (string, error) {
		return "", exec.ErrNotFound
	})
	if err != nil {
		t.Fatalf("findSidecar() error = %v, want nil", err)
	}
	if got != sourcePath {
		t.Fatalf("findSidecar() = %q, want %q", got, sourcePath)
	}
}
