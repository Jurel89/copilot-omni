package sidecar

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

type Manager struct {
	binaryPath string
	cmd        *exec.Cmd
	stdin      io.WriteCloser
	stdout     io.ReadCloser
	mu         sync.Mutex
	running    bool
	waitCh     chan error
	decoder    *json.Decoder
}

type mcpRequest struct {
	JSONRPC string `json:"jsonrpc"`
	ID      any    `json:"id,omitempty"`
	Method  string `json:"method"`
	Params  any    `json:"params,omitempty"`
}

type mcpResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      any             `json:"id,omitempty"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *mcpError       `json:"error,omitempty"`
}

type mcpError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type initializeResult struct {
	ProtocolVersion string `json:"protocolVersion"`
}

type toolCallResult struct {
	Content []toolCallContent `json:"content"`
}

type toolCallContent struct {
	Type string `json:"type"`
	Text string `json:"text"`
}

type healthPayload struct {
	Status        string `json:"status"`
	Version       string `json:"version"`
	Protocol      string `json:"protocol"`
	UptimeSeconds int    `json:"uptime_seconds"`
}

const (
	mcpProtocolVersion = "2024-11-05"
	sidecarCommandName = "omni-sidecar"
)

var stopTimeout = 5 * time.Second

func FindSidecar() (string, error) {
	executablePath, err := os.Executable()
	if err != nil {
		return "", fmt.Errorf("resolve executable path: %w", err)
	}

	return findSidecar(os.Getenv("COPILOT_OMNI_SIDECAR"), executablePath, exec.LookPath)
}

func findSidecar(envPath, executablePath string, lookPath func(string) (string, error)) (string, error) {
	if envPath != "" {
		path, err := resolveSidecarOverride(envPath, lookPath)
		if err != nil {
			return "", fmt.Errorf("resolve COPILOT_OMNI_SIDECAR: %w", err)
		}
		return path, nil
	}

	candidates, err := sidecarCandidatePaths(executablePath)
	if err != nil {
		return "", err
	}

	for _, candidate := range candidates {
		if path, err := validateBinaryPath(candidate); err == nil {
			return path, nil
		}
	}

	path, err := lookPath(sidecarCommandName)
	if err != nil {
		return "", fmt.Errorf("find %s: %w", sidecarCommandName, err)
	}

	resolvedPath, err := validateBinaryPath(path)
	if err != nil {
		return "", fmt.Errorf("validate %s from PATH: %w", path, err)
	}

	return resolvedPath, nil
}

func resolveSidecarOverride(envPath string, lookPath func(string) (string, error)) (string, error) {
	if isPathLike(envPath) {
		return validateBinaryPath(envPath)
	}

	path, err := lookPath(envPath)
	if err != nil {
		return "", fmt.Errorf("find %s: %w", envPath, err)
	}

	resolvedPath, err := validateBinaryPath(path)
	if err != nil {
		return "", fmt.Errorf("validate %s: %w", path, err)
	}

	return resolvedPath, nil
}

func sidecarCandidatePaths(executablePath string) ([]string, error) {
	resolvedExecutablePath, err := validateBinaryPath(executablePath)
	if err != nil {
		return nil, fmt.Errorf("resolve executable path: %w", err)
	}

	exeDir := filepath.Dir(resolvedExecutablePath)
	binaryName := sidecarBinaryName()

	return []string{
		filepath.Join(exeDir, "..", "sidecar", binaryName),
		filepath.Join(exeDir, binaryName),
	}, nil
}

func sidecarBinaryName() string {
	if runtime.GOOS == "windows" {
		return sidecarCommandName + ".exe"
	}

	return sidecarCommandName
}

func isPathLike(path string) bool {
	return filepath.IsAbs(path) || filepath.VolumeName(path) != "" || filepath.Base(path) != path || strings.ContainsAny(path, `/\\`)
}

func NewManager(binaryPath string) *Manager {
	return &Manager{binaryPath: binaryPath}
}

func (m *Manager) Start(ctx context.Context) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.running && m.cmd != nil && m.stdin != nil && m.decoder != nil {
		return nil
	}

	cmd := exec.CommandContext(ctx, m.binaryPath, "serve")
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return fmt.Errorf("open sidecar stdin: %w", err)
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		_ = stdin.Close()
		return fmt.Errorf("open sidecar stdout: %w", err)
	}
	cmd.Stderr = os.Stderr

	if err := cmd.Start(); err != nil {
		_ = stdin.Close()
		_ = stdout.Close()
		return fmt.Errorf("start sidecar: %w", err)
	}

	m.cmd = cmd
	m.stdin = stdin
	m.stdout = stdout
	m.decoder = json.NewDecoder(stdout)
	m.waitCh = make(chan error, 1)
	m.running = true

	go func(waitCh chan error) {
		err := cmd.Wait()
		m.mu.Lock()
		if m.cmd == cmd {
			m.cmd = nil
			m.stdin = nil
			m.stdout = nil
			m.decoder = nil
			m.waitCh = nil
			m.running = false
		}
		m.mu.Unlock()
		waitCh <- err
		close(waitCh)
	}(m.waitCh)

	return nil
}

func (m *Manager) HealthCheck(ctx context.Context, timeout time.Duration) error {
	healthCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	m.mu.Lock()
	defer m.mu.Unlock()

	if !m.running || m.cmd == nil || m.stdin == nil || m.decoder == nil {
		return fmt.Errorf("sidecar is not running")
	}

	if err := m.writeRequest(healthCtx, mcpRequest{
		JSONRPC: "2.0",
		ID:      1,
		Method:  "initialize",
		Params: map[string]any{
			"protocolVersion": mcpProtocolVersion,
			"capabilities": map[string]any{
				"tools": map[string]any{"listChanged": false},
			},
			"clientInfo": map[string]any{
				"name":    "omni-wrapper",
				"version": "0.1.0",
			},
		},
	}); err != nil {
		return err
	}

	initResp, err := m.readResponse(healthCtx)
	if err != nil {
		return err
	}
	if initResp.Error != nil {
		return fmt.Errorf("initialize failed: %s (%d)", initResp.Error.Message, initResp.Error.Code)
	}

	var initResult initializeResult
	if err := json.Unmarshal(initResp.Result, &initResult); err != nil {
		return fmt.Errorf("decode initialize response: %w", err)
	}
	if initResult.ProtocolVersion != mcpProtocolVersion {
		return fmt.Errorf("unexpected protocol version: %s", initResult.ProtocolVersion)
	}

	if err := m.writeRequest(healthCtx, mcpRequest{
		JSONRPC: "2.0",
		Method:  "notifications/initialized",
	}); err != nil {
		return err
	}

	if err := m.writeRequest(healthCtx, mcpRequest{
		JSONRPC: "2.0",
		ID:      2,
		Method:  "tools/call",
		Params: map[string]any{
			"name":      "omni_health",
			"arguments": map[string]any{},
		},
	}); err != nil {
		return err
	}

	healthResp, err := m.readResponse(healthCtx)
	if err != nil {
		return err
	}
	if healthResp.Error != nil {
		return fmt.Errorf("omni_health failed: %s (%d)", healthResp.Error.Message, healthResp.Error.Code)
	}

	var toolResult toolCallResult
	if err := json.Unmarshal(healthResp.Result, &toolResult); err != nil {
		return fmt.Errorf("decode tool response: %w", err)
	}
	if len(toolResult.Content) == 0 {
		return fmt.Errorf("omni_health returned no content")
	}

	var payload healthPayload
	if err := json.Unmarshal([]byte(toolResult.Content[0].Text), &payload); err != nil {
		return fmt.Errorf("decode omni_health payload: %w", err)
	}
	if payload.Status != "ok" {
		return fmt.Errorf("unexpected omni_health status: %s", payload.Status)
	}
	if payload.Protocol != "mcp" {
		return fmt.Errorf("unexpected omni_health protocol: %s", payload.Protocol)
	}

	return nil
}

func (m *Manager) Stop() error {
	m.mu.Lock()
	if m.cmd == nil || m.cmd.Process == nil || !m.running {
		m.mu.Unlock()
		return nil
	}

	cmd := m.cmd
	stdin := m.stdin
	stdout := m.stdout
	waitCh := m.waitCh
	m.mu.Unlock()

	if stdin != nil {
		if err := stdin.Close(); err != nil && !errors.Is(err, os.ErrClosed) {
			return fmt.Errorf("close sidecar stdin: %w", err)
		}
	}

	timer := time.NewTimer(stopTimeout)
	defer timer.Stop()

	select {
	case err := <-waitCh:
		if stdout != nil {
			_ = stdout.Close()
		}
		if err != nil && !isFinishedProcessError(err) {
			return fmt.Errorf("wait for sidecar exit: %w", err)
		}
		return nil
	case <-timer.C:
		if err := cmd.Process.Kill(); err != nil && !isFinishedProcessError(err) {
			return fmt.Errorf("kill sidecar: %w", err)
		}
		if waitCh != nil {
			_, _ = <-waitCh
		}
		if stdout != nil {
			_ = stdout.Close()
		}
		return nil
	}
}

func (m *Manager) IsRunning() bool {
	m.mu.Lock()
	defer m.mu.Unlock()

	return m.running && m.cmd != nil
}

func (m *Manager) CallTool(ctx context.Context, toolName string, arguments map[string]any) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if !m.running || m.cmd == nil || m.stdin == nil || m.decoder == nil {
		return "", fmt.Errorf("sidecar is not running")
	}

	if err := m.writeRequest(ctx, mcpRequest{
		JSONRPC: "2.0",
		ID:      10,
		Method:  "tools/call",
		Params: map[string]any{
			"name":      toolName,
			"arguments": arguments,
		},
	}); err != nil {
		return "", err
	}

	resp, err := m.readResponse(ctx)
	if err != nil {
		return "", err
	}
	if resp.Error != nil {
		return "", fmt.Errorf("%s failed: %s (%d)", toolName, resp.Error.Message, resp.Error.Code)
	}

	var toolResult toolCallResult
	if err := json.Unmarshal(resp.Result, &toolResult); err != nil {
		return "", fmt.Errorf("decode tool response: %w", err)
	}
	if len(toolResult.Content) == 0 {
		return "", fmt.Errorf("%s returned no content", toolName)
	}

	return toolResult.Content[0].Text, nil
}

func (m *Manager) writeRequest(ctx context.Context, req mcpRequest) error {
	if err := ctx.Err(); err != nil {
		return fmt.Errorf("sidecar request cancelled: %w", err)
	}

	payload, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("marshal request %s: %w", req.Method, err)
	}
	payload = append(payload, '\n')

	type writeResult struct{ err error }
	resultCh := make(chan writeResult, 1)
	go func() {
		_, err := m.stdin.Write(payload)
		resultCh <- writeResult{err: err}
	}()

	select {
	case <-ctx.Done():
		return fmt.Errorf("write request %s: %w", req.Method, ctx.Err())
	case result := <-resultCh:
		if result.err != nil {
			return fmt.Errorf("write request %s: %w", req.Method, result.err)
		}
		return nil
	}
}

func (m *Manager) readResponse(ctx context.Context) (mcpResponse, error) {
	type readResult struct {
		resp mcpResponse
		err  error
	}

	resultCh := make(chan readResult, 1)
	go func() {
		var resp mcpResponse
		resultCh <- readResult{resp: resp, err: m.decoder.Decode(&resp)}
	}()

	select {
	case <-ctx.Done():
		return mcpResponse{}, fmt.Errorf("read sidecar response: %w", ctx.Err())
	case result := <-resultCh:
		if result.err != nil {
			return mcpResponse{}, fmt.Errorf("decode sidecar response: %w", result.err)
		}
		return result.resp, nil
	}
}

func validateBinaryPath(path string) (string, error) {
	absPath, err := filepath.Abs(path)
	if err != nil {
		return "", fmt.Errorf("resolve path %s: %w", path, err)
	}

	resolvedPath, err := filepath.EvalSymlinks(absPath)
	if err != nil {
		return "", fmt.Errorf("resolve symlink %s: %w", absPath, err)
	}

	info, err := os.Stat(resolvedPath)
	if err != nil {
		return "", fmt.Errorf("stat %s: %w", resolvedPath, err)
	}
	if info.IsDir() {
		return "", fmt.Errorf("%s is a directory", resolvedPath)
	}

	return resolvedPath, nil
}

func isFinishedProcessError(err error) bool {
	if err == nil {
		return false
	}

	return err == os.ErrProcessDone || err.Error() == "os: process already finished"
}
