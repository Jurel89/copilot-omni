package plugininstall

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/Jurel89/copilot-omni/wrapper/internal/assets"
)

type Options struct {
	AssetLocation assets.Location
	SidecarPath   string
	KeepStaging   bool
	StagingDir    string
	CopilotPath   string
}

type Result struct {
	StagingDir string
}

func Install(ctx context.Context, opts Options) (Result, error) {
	if opts.AssetLocation.PluginDir == "" {
		return Result{}, fmt.Errorf("plugin asset directory is required")
	}
	if opts.SidecarPath == "" {
		return Result{}, fmt.Errorf("sidecar path is required")
	}

	copilotPath := opts.CopilotPath
	if copilotPath == "" {
		resolvedPath, err := exec.LookPath("copilot")
		if err != nil {
			return Result{}, fmt.Errorf("find copilot CLI: %w", err)
		}
		copilotPath = resolvedPath
	}

	stagingDir := opts.StagingDir
	if stagingDir == "" {
		var err error
		stagingDir, err = os.MkdirTemp("", "copilot-omni-plugin-")
		if err != nil {
			return Result{}, fmt.Errorf("create staging directory: %w", err)
		}
	} else {
		if err := os.RemoveAll(stagingDir); err != nil {
			return Result{}, fmt.Errorf("reset staging directory: %w", err)
		}
		if err := os.MkdirAll(stagingDir, 0o755); err != nil {
			return Result{}, fmt.Errorf("create staging directory: %w", err)
		}
	}

	cleanup := !opts.KeepStaging
	if cleanup {
		defer os.RemoveAll(stagingDir)
	}

	if err := copyDir(opts.AssetLocation.PluginDir, stagingDir); err != nil {
		return Result{}, fmt.Errorf("stage plugin assets: %w", err)
	}
	if err := writeMCPConfig(filepath.Join(stagingDir, ".mcp.json"), opts.SidecarPath); err != nil {
		return Result{}, fmt.Errorf("write staged .mcp.json: %w", err)
	}

	cmd := exec.CommandContext(ctx, copilotPath, "plugin", "install", stagingDir)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return Result{}, fmt.Errorf("run copilot plugin install: %w", err)
	}

	return Result{StagingDir: stagingDir}, nil
}

func writeMCPConfig(path string, sidecarPath string) error {
	payload := map[string]any{
		"mcpServers": map[string]any{
			"copilot-omni-sidecar": map[string]any{
				"type":    "stdio",
				"command": sidecarPath,
				"args":    []string{"serve"},
				"tools":   []string{"*"},
			},
		},
	}

	content, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal staged mcp config: %w", err)
	}
	content = append(content, '\n')
	return os.WriteFile(path, content, 0o644)
}

func copyDir(srcDir, dstDir string) error {
	return filepath.Walk(srcDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		relPath, err := filepath.Rel(srcDir, path)
		if err != nil {
			return fmt.Errorf("relative path for %s: %w", path, err)
		}
		if relPath == "." {
			return nil
		}

		targetPath := filepath.Join(dstDir, relPath)
		if info.IsDir() {
			return os.MkdirAll(targetPath, 0o755)
		}

		if err := os.MkdirAll(filepath.Dir(targetPath), 0o755); err != nil {
			return err
		}
		return copyFile(path, targetPath, info.Mode())
	})
}

func copyFile(src, dst string, mode os.FileMode) error {
	input, err := os.Open(src)
	if err != nil {
		return fmt.Errorf("open %s: %w", src, err)
	}
	defer input.Close()

	output, err := os.OpenFile(dst, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, mode.Perm())
	if err != nil {
		return fmt.Errorf("create %s: %w", dst, err)
	}
	defer output.Close()

	if _, err := io.Copy(output, input); err != nil {
		return fmt.Errorf("copy %s to %s: %w", src, dst, err)
	}

	return nil
}
