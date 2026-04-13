package assets

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const assetRootEnv = "COPILOT_OMNI_ASSET_ROOT"

const (
	sourceExecutableDirName = "wrapper"
	sourceBinaryName        = "omni"
	installedExecutableDir  = "bin"
	installedAssetDirName   = "copilot-omni"
)

type Mode string

const (
	ModeOverride  Mode = "override"
	ModeSource    Mode = "source"
	ModeInstalled Mode = "installed"
)

type Location struct {
	AssetRoot       string
	PluginDir       string
	TemplateDir     string
	PolicyDir       string
	MarketplacePath string
	Mode            Mode
	ExecPath        string
	ExecDir         string
}

func Locate() (Location, error) {
	execPath, err := os.Executable()
	if err != nil {
		return Location{}, fmt.Errorf("resolve executable path: %w", err)
	}

	return ResolveFromExecutable(execPath)
}

func ResolveFromExecutable(execPath string) (Location, error) {
	resolvedExecPath, err := resolveExistingPath(execPath)
	if err != nil {
		return Location{}, fmt.Errorf("resolve executable path %q: %w", execPath, err)
	}

	execDir := filepath.Dir(resolvedExecPath)
	if envRoot := strings.TrimSpace(os.Getenv(assetRootEnv)); envRoot != "" {
		return buildLocation(envRoot, ModeOverride, resolvedExecPath, execDir)
	}

	if matchesSourceLayout(resolvedExecPath, execDir) {
		return buildLocation(filepath.Join(execDir, ".."), ModeSource, resolvedExecPath, execDir)
	}

	if matchesInstalledLayout(resolvedExecPath, execDir) {
		return buildLocation(filepath.Join(execDir, "..", "share", installedAssetDirName), ModeInstalled, resolvedExecPath, execDir)
	}

	return Location{}, fmt.Errorf("unable to determine trusted asset layout from executable %s", resolvedExecPath)
}

func matchesSourceLayout(execPath, execDir string) bool {
	return filepath.Base(execDir) == sourceExecutableDirName && binaryName(execPath) == sourceBinaryName
}

func matchesInstalledLayout(execPath, execDir string) bool {
	return filepath.Base(execDir) == installedExecutableDir && binaryName(execPath) == sourceBinaryName
}

func binaryName(path string) string {
	name := strings.ToLower(filepath.Base(path))
	return strings.TrimSuffix(name, ".exe")
}

func buildLocation(assetRoot string, mode Mode, execPath, execDir string) (Location, error) {
	resolvedRoot, err := resolvePath(assetRoot)
	if err != nil {
		return Location{}, fmt.Errorf("resolve %s asset root %q: %w", mode, assetRoot, err)
	}

	if err := validateAssetRoot(resolvedRoot, mode); err != nil {
		return Location{}, err
	}

	return Location{
		AssetRoot:       resolvedRoot,
		PluginDir:       filepath.Join(resolvedRoot, "plugin"),
		TemplateDir:     filepath.Join(resolvedRoot, "templates"),
		PolicyDir:       filepath.Join(resolvedRoot, "policies"),
		MarketplacePath: filepath.Join(resolvedRoot, "marketplace.json"),
		Mode:            mode,
		ExecPath:        execPath,
		ExecDir:         execDir,
	}, nil
}

func validateAssetRoot(assetRoot string, mode Mode) error {
	if err := requireDirectory(assetRoot); err != nil {
		return fmt.Errorf("%s asset root %s %w", mode, assetRoot, err)
	}
	if err := requireDirectory(filepath.Join(assetRoot, "plugin")); err != nil {
		return fmt.Errorf("%s asset root %s %w", mode, assetRoot, err)
	}
	if err := requireDirectory(filepath.Join(assetRoot, "templates")); err != nil {
		return fmt.Errorf("%s asset root %s %w", mode, assetRoot, err)
	}
	if err := requireDirectory(filepath.Join(assetRoot, "policies")); err != nil {
		return fmt.Errorf("%s asset root %s %w", mode, assetRoot, err)
	}
	if err := requireFile(filepath.Join(assetRoot, "marketplace.json")); err != nil {
		return fmt.Errorf("%s asset root %s %w", mode, assetRoot, err)
	}

	return nil
}

func requireDirectory(path string) error {
	info, err := os.Stat(path)
	if err != nil {
		return fmt.Errorf("missing required directory %s: %w", path, err)
	}
	if !info.IsDir() {
		return fmt.Errorf("required directory %s is not a directory", path)
	}

	return nil
}

func requireFile(path string) error {
	info, err := os.Stat(path)
	if err != nil {
		return fmt.Errorf("missing required file %s: %w", path, err)
	}
	if info.IsDir() {
		return fmt.Errorf("required file %s is a directory", path)
	}

	return nil
}

func resolveExistingPath(path string) (string, error) {
	resolvedPath, err := resolvePath(path)
	if err != nil {
		return "", err
	}

	if err := requireFile(resolvedPath); err != nil {
		return "", err
	}

	return resolvedPath, nil
}

func resolvePath(path string) (string, error) {
	trimmedPath := strings.TrimSpace(path)
	if trimmedPath == "" {
		return "", fmt.Errorf("path is empty")
	}

	absPath, err := filepath.Abs(trimmedPath)
	if err != nil {
		return "", fmt.Errorf("make absolute path %s: %w", trimmedPath, err)
	}

	if resolvedPath, err := filepath.EvalSymlinks(absPath); err == nil {
		return resolvedPath, nil
	} else if !os.IsNotExist(err) {
		return "", fmt.Errorf("resolve symlink %s: %w", absPath, err)
	}

	return absPath, nil
}
