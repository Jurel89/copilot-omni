package copilot

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
)

type RunOptions struct {
	Model      string
	Agent      string
	AllowTools []string
	DenyTools  []string
	SharePath  string
	NoAskUser  bool
	Silent     bool
	AddDirs    []string
}

func FindCopilot() (string, error) {
	path, err := exec.LookPath("copilot")
	if err != nil {
		return "", fmt.Errorf("find copilot CLI: %w", err)
	}

	return path, nil
}

func Run(ctx context.Context, prompt string, opts RunOptions) (string, error) {
	if prompt == "" {
		return "", fmt.Errorf("prompt is required")
	}

	args := []string{"-p", prompt}
	args = appendRunOptions(args, opts)

	cmd, err := commandForCopilot(ctx, args...)
	if err != nil {
		return "", err
	}

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err = cmd.Run()
	output := stdout.String() + stderr.String()
	if err != nil {
		return output, fmt.Errorf("run copilot: %w", err)
	}

	return output, nil
}

func RunInteractive(ctx context.Context, agent string, addDirs []string) error {
	args := make([]string, 0, 1+len(addDirs))
	if agent != "" {
		args = append(args, fmt.Sprintf("--agent=%s", agent))
	}
	for _, dir := range addDirs {
		args = append(args, fmt.Sprintf("--add-dir=%s", dir))
	}

	cmd, err := commandForCopilot(ctx, args...)
	if err != nil {
		return err
	}
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Run(); err != nil {
		return fmt.Errorf("run copilot interactively: %w", err)
	}

	return nil
}

func appendRunOptions(args []string, opts RunOptions) []string {
	if opts.Model != "" {
		args = append(args, fmt.Sprintf("--model=%s", opts.Model))
	}
	if opts.Agent != "" {
		args = append(args, fmt.Sprintf("--agent=%s", opts.Agent))
	}
	if opts.SharePath != "" {
		args = append(args, fmt.Sprintf("--share=%s", opts.SharePath))
	}
	if opts.NoAskUser {
		args = append(args, "--no-ask-user")
	}
	if opts.Silent {
		args = append(args, "-s")
	}
	for _, tool := range opts.AllowTools {
		args = append(args, fmt.Sprintf("--allow-tool=%s", tool))
	}
	for _, tool := range opts.DenyTools {
		args = append(args, fmt.Sprintf("--deny-tool=%s", tool))
	}
	for _, dir := range opts.AddDirs {
		args = append(args, fmt.Sprintf("--add-dir=%s", dir))
	}

	return args
}

func commandForCopilot(ctx context.Context, args ...string) (*exec.Cmd, error) {
	path, err := FindCopilot()
	if err != nil {
		return nil, err
	}
	if runtime.GOOS == "windows" {
		ext := filepath.Ext(path)
		if ext == ".bat" || ext == ".cmd" {
			cmdArgs := append([]string{"/c", path}, args...)
			return exec.CommandContext(ctx, "cmd.exe", cmdArgs...), nil
		}
	}
	return exec.CommandContext(ctx, path, args...), nil
}
