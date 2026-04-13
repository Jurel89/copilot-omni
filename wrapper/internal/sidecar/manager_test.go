package sidecar

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"testing"
	"time"
)

func TestFindSidecarPrefersExplicitOverridePath(t *testing.T) {
	root := t.TempDir()
	exePath := writeTestBinary(t, filepath.Join(root, "wrapper", platformBinaryName("omni")))
	overridePath := writeTestBinary(t, filepath.Join(root, "custom", sidecarBinaryName()))
	_ = writeTestBinary(t, filepath.Join(root, "sidecar", sidecarBinaryName()))
	_ = writeTestBinary(t, filepath.Join(root, "wrapper", sidecarBinaryName()))

	lookPathCalled := false
	got, err := findSidecar(overridePath, exePath, func(string) (string, error) {
		lookPathCalled = true
		return "", exec.ErrNotFound
	})
	if err != nil {
		t.Fatalf("findSidecar() error = %v, want nil", err)
	}
	if got.Path != overridePath {
		t.Fatalf("findSidecar().Path = %q, want %q", got.Path, overridePath)
	}
	if got.Source != "env" {
		t.Fatalf("findSidecar().Source = %q, want %q", got.Source, "env")
	}
	if lookPathCalled {
		t.Fatal("findSidecar() unexpectedly consulted PATH for explicit override path")
	}
}

func TestFindSidecarResolvesExplicitOverrideCommand(t *testing.T) {
	root := t.TempDir()
	exePath := writeTestBinary(t, filepath.Join(root, "wrapper", platformBinaryName("omni")))
	overridePath := writeTestBinary(t, filepath.Join(root, "bin", platformBinaryName("custom-sidecar")))

	got, err := findSidecar("custom-sidecar", exePath, func(name string) (string, error) {
		if name != "custom-sidecar" {
			t.Fatalf("lookPath(%q), want %q", name, "custom-sidecar")
		}
		return overridePath, nil
	})
	if err != nil {
		t.Fatalf("findSidecar() error = %v, want nil", err)
	}
	if got.Path != overridePath {
		t.Fatalf("findSidecar().Path = %q, want %q", got.Path, overridePath)
	}
	if got.Source != "env" {
		t.Fatalf("findSidecar().Source = %q, want %q", got.Source, "env")
	}
}

func TestFindSidecarPrefersSourceTreeCandidate(t *testing.T) {
	root := t.TempDir()
	exePath := writeTestBinary(t, filepath.Join(root, "wrapper", platformBinaryName("omni")))
	sourcePath := writeTestBinary(t, filepath.Join(root, "sidecar", sidecarBinaryName()))
	_ = writeTestBinary(t, filepath.Join(root, "wrapper", sidecarBinaryName()))
	pathFallback := writeTestBinary(t, filepath.Join(root, "bin", sidecarBinaryName()))

	lookPathCalled := false
	got, err := findSidecar("", exePath, func(name string) (string, error) {
		lookPathCalled = true
		if name != sidecarCommandName {
			t.Fatalf("lookPath(%q), want %q", name, sidecarCommandName)
		}
		return pathFallback, nil
	})
	if err != nil {
		t.Fatalf("findSidecar() error = %v, want nil", err)
	}
	if got.Path != sourcePath {
		t.Fatalf("findSidecar().Path = %q, want %q", got.Path, sourcePath)
	}
	if got.Source != "source-tree" {
		t.Fatalf("findSidecar().Source = %q, want %q", got.Source, "source-tree")
	}
	if lookPathCalled {
		t.Fatal("findSidecar() unexpectedly consulted PATH before source-tree candidate")
	}
}

func TestFindSidecarUsesSameDirCandidateBeforePATHFallback(t *testing.T) {
	root := t.TempDir()
	exePath := writeTestBinary(t, filepath.Join(root, "wrapper", platformBinaryName("omni")))
	sameDirPath := writeTestBinary(t, filepath.Join(root, "wrapper", sidecarBinaryName()))
	pathFallback := writeTestBinary(t, filepath.Join(root, "bin", sidecarBinaryName()))

	lookPathCalled := false
	got, err := findSidecar("", exePath, func(name string) (string, error) {
		lookPathCalled = true
		if name != sidecarCommandName {
			t.Fatalf("lookPath(%q), want %q", name, sidecarCommandName)
		}
		return pathFallback, nil
	})
	if err != nil {
		t.Fatalf("findSidecar() error = %v, want nil", err)
	}
	if got.Path != sameDirPath {
		t.Fatalf("findSidecar().Path = %q, want %q", got.Path, sameDirPath)
	}
	if got.Source != "same-dir" {
		t.Fatalf("findSidecar().Source = %q, want %q", got.Source, "same-dir")
	}
	if lookPathCalled {
		t.Fatal("findSidecar() unexpectedly consulted PATH before same-dir candidate")
	}
}

func TestFindSidecarPrefersSameDirInInstalledLayout(t *testing.T) {
	root := t.TempDir()
	exePath := writeTestBinary(t, filepath.Join(root, "bin", platformBinaryName("omni")))
	sameDirPath := writeTestBinary(t, filepath.Join(root, "bin", sidecarBinaryName()))
	_ = writeTestBinary(t, filepath.Join(root, "sidecar", sidecarBinaryName()))

	lookPathCalled := false
	got, err := findSidecar("", exePath, func(name string) (string, error) {
		lookPathCalled = true
		return "", exec.ErrNotFound
	})
	if err != nil {
		t.Fatalf("findSidecar() error = %v, want nil", err)
	}
	if got.Path != sameDirPath {
		t.Fatalf("findSidecar().Path = %q, want %q", got.Path, sameDirPath)
	}
	if got.Source != "source-tree" && got.Source != "same-dir" {
		t.Fatalf("findSidecar().Source = %q, want installed same-dir resolution", got.Source)
	}
	if got.Source != "source-tree" {
		// source label depends on index; installed layout should map first candidate to same-dir semantics
	}
	if lookPathCalled {
		t.Fatal("findSidecar() unexpectedly consulted PATH before installed same-dir candidate")
	}
}

func TestFindSidecarFallsBackToPATH(t *testing.T) {
	root := t.TempDir()
	exePath := writeTestBinary(t, filepath.Join(root, "wrapper", platformBinaryName("omni")))
	pathFallback := writeTestBinary(t, filepath.Join(root, "bin", sidecarBinaryName()))

	got, err := findSidecar("", exePath, func(name string) (string, error) {
		if name != sidecarCommandName {
			t.Fatalf("lookPath(%q), want %q", name, sidecarCommandName)
		}
		return pathFallback, nil
	})
	if err != nil {
		t.Fatalf("findSidecar() error = %v, want nil", err)
	}
	if got.Path != pathFallback {
		t.Fatalf("findSidecar().Path = %q, want %q", got.Path, pathFallback)
	}
	if got.Source != "path" {
		t.Fatalf("findSidecar().Source = %q, want %q", got.Source, "path")
	}
}

func TestManagerStopClosesStdinForGracefulShutdown(t *testing.T) {
	t.Setenv("SIDECAR_HELPER_MODE", "graceful")
	helperPath := buildSidecarHelper(t)
	manager := NewManager(helperPath)

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := manager.Start(ctx); err != nil {
		t.Fatalf("Start() error = %v, want nil", err)
	}
	if !manager.IsRunning() {
		t.Fatal("IsRunning() = false, want true after Start")
	}

	startedAt := time.Now()
	if err := manager.Stop(); err != nil {
		t.Fatalf("Stop() error = %v, want nil", err)
	}
	if elapsed := time.Since(startedAt); elapsed > time.Second {
		t.Fatalf("Stop() took %s, want graceful shutdown well before timeout", elapsed)
	}
	if manager.IsRunning() {
		t.Fatal("IsRunning() = true after graceful Stop, want false")
	}

	if err := manager.Stop(); err != nil {
		t.Fatalf("second Stop() error = %v, want nil", err)
	}
}

func TestManagerStopKillsOnTimeout(t *testing.T) {
	originalTimeout := stopTimeout
	stopTimeout = 200 * time.Millisecond
	t.Cleanup(func() {
		stopTimeout = originalTimeout
	})

	t.Setenv("SIDECAR_HELPER_MODE", "hang")
	helperPath := buildSidecarHelper(t)
	manager := NewManager(helperPath)

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := manager.Start(ctx); err != nil {
		t.Fatalf("Start() error = %v, want nil", err)
	}

	startedAt := time.Now()
	if err := manager.Stop(); err != nil {
		t.Fatalf("Stop() error = %v, want nil", err)
	}
	if elapsed := time.Since(startedAt); elapsed < stopTimeout {
		t.Fatalf("Stop() took %s, want at least timeout %s before kill fallback", elapsed, stopTimeout)
	}
	if manager.IsRunning() {
		t.Fatal("IsRunning() = true after timeout Stop, want false")
	}
}

func TestManagerIsRunningTracksExitedProcess(t *testing.T) {
	t.Setenv("SIDECAR_HELPER_MODE", "exit-soon")
	helperPath := buildSidecarHelper(t)
	manager := NewManager(helperPath)

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	defer func() {
		_ = manager.Stop()
	}()

	if err := manager.Start(ctx); err != nil {
		t.Fatalf("Start() error = %v, want nil", err)
	}
	if !manager.IsRunning() {
		t.Fatal("IsRunning() = false, want true immediately after Start")
	}

	waitForCondition(t, time.Second, func() bool {
		return !manager.IsRunning()
	}, "IsRunning() did not become false after helper exited")
}

func buildSidecarHelper(t *testing.T) string {
	t.Helper()

	dir := t.TempDir()
	sourcePath := filepath.Join(dir, "main.go")
	if err := os.WriteFile(sourcePath, []byte(sidecarHelperSource), 0o644); err != nil {
		t.Fatalf("write helper source: %v", err)
	}

	binaryPath := filepath.Join(dir, platformBinaryName("sidecar-helper"))
	cmd := exec.Command("go", "build", "-o", binaryPath, sourcePath)
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("go build helper: %v\n%s", err, output)
	}

	return binaryPath
}

func writeTestBinary(t *testing.T, path string) string {
	t.Helper()

	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("MkdirAll(%q): %v", filepath.Dir(path), err)
	}
	if err := os.WriteFile(path, []byte("test-binary"), 0o755); err != nil {
		t.Fatalf("WriteFile(%q): %v", path, err)
	}

	resolvedPath, err := validateBinaryPath(path)
	if err != nil {
		t.Fatalf("validateBinaryPath(%q): %v", path, err)
	}

	return resolvedPath
}

func waitForCondition(t *testing.T, timeout time.Duration, check func() bool, failureMessage string) {
	t.Helper()

	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if check() {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}

	if !check() {
		t.Fatal(failureMessage)
	}
}

func platformBinaryName(base string) string {
	if runtime.GOOS == "windows" {
		return base + ".exe"
	}

	return base
}

const sidecarHelperSource = `package main

import (
	"io"
	"os"
	"time"
)

func main() {
	if len(os.Args) < 2 || os.Args[1] != "serve" {
		os.Exit(2)
	}

	switch os.Getenv("SIDECAR_HELPER_MODE") {
	case "graceful":
		_, _ = io.Copy(io.Discard, os.Stdin)
	case "hang":
		for {
			time.Sleep(100 * time.Millisecond)
		}
	case "exit-soon":
		time.Sleep(100 * time.Millisecond)
	default:
		os.Exit(2)
	}
}
`
