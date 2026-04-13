package install

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"sort"
	"strings"
)

const (
	checksumsFileName = "checksums.txt"
	manifestFileName  = "release-manifest.json"
	shareDirName      = "copilot-omni"
	sbomFileName      = "sbom.json"
)

type Options struct {
	BundleDir string
	Target    string
}

type Result struct {
	Assets            []string
	Binaries          []string
	BundleDir         string
	Manifest          Manifest
	Metadata          []string
	ShareDir          string
	TargetDir         string
	ValidationWarning []string
	BinDir            string
}

type Manifest struct {
	Version    string            `json:"version"`
	Product    string            `json:"product"`
	ReleaseTag string            `json:"release_tag"`
	BuildDate  string            `json:"build_date"`
	CommitHash string            `json:"commit_hash,omitempty"`
	Platform   string            `json:"platform"`
	Components []Component       `json:"components"`
	Checksums  map[string]string `json:"checksums"`
	Provenance Provenance        `json:"provenance"`
	SBOM       []SBOMEntry       `json:"sbom"`
}

type Component struct {
	Name     string `json:"name"`
	Path     string `json:"path"`
	Type     string `json:"type"`
	Arch     string `json:"arch,omitempty"`
	Checksum string `json:"checksum"`
}

type Provenance struct {
	Builder     string `json:"builder"`
	Signature   string `json:"signature,omitempty"`
	Fingerprint string `json:"fingerprint,omitempty"`
	Workflow    string `json:"workflow,omitempty"`
	Repository  string `json:"repository,omitempty"`
}

type SBOMEntry struct {
	Name    string `json:"name"`
	Version string `json:"version"`
	Type    string `json:"type"`
	Hash    string `json:"hash,omitempty"`
}

func Install(options Options) (*Result, error) {
	bundleDir, err := resolveExistingDir(options.BundleDir)
	if err != nil {
		return nil, fmt.Errorf("resolve bundle directory: %w", err)
	}

	validationWarnings, manifest, err := validateBundle(bundleDir)
	if err != nil {
		return nil, err
	}

	hasWrapperBinary := false
	hasSidecarBinary := false
	for _, component := range manifest.Components {
		if strings.EqualFold(strings.TrimSpace(component.Type), "binary") {
			switch component.Name {
			case "omni-wrapper":
				hasWrapperBinary = true
			case "omni-sidecar":
				hasSidecarBinary = true
			}
		}
	}
	if !hasWrapperBinary || !hasSidecarBinary {
		return nil, fmt.Errorf("bundle is missing required wrapper or sidecar binaries")
	}

	targetDir, err := ensureDirectory(options.Target)
	if err != nil {
		return nil, fmt.Errorf("resolve target directory: %w", err)
	}

	binDir, err := ensureSubdir(targetDir, "bin")
	if err != nil {
		return nil, fmt.Errorf("prepare bin directory: %w", err)
	}

	shareDir, err := ensureSubdir(targetDir, path.Join("share", shareDirName))
	if err != nil {
		return nil, fmt.Errorf("prepare shared asset directory: %w", err)
	}

	result := &Result{
		Assets:            make([]string, 0, len(manifest.Components)),
		Binaries:          make([]string, 0, len(manifest.Components)),
		BinDir:            binDir,
		BundleDir:         bundleDir,
		Manifest:          *manifest,
		Metadata:          make([]string, 0, 3),
		ShareDir:          shareDir,
		TargetDir:         targetDir,
		ValidationWarning: append([]string(nil), validationWarnings...),
	}

	for _, component := range manifest.Components {
		sourcePath, err := bundleFilePath(bundleDir, component.Path)
		if err != nil {
			return nil, fmt.Errorf("resolve component %s source path: %w", component.Name, err)
		}

		if strings.EqualFold(strings.TrimSpace(component.Type), "binary") {
			binaryName, err := bundleBinaryName(component.Path)
			if err != nil {
				return nil, fmt.Errorf("resolve binary destination for %s: %w", component.Name, err)
			}

			installedPath, err := copyFileUnder(binDir, binaryName, sourcePath, 0o755)
			if err != nil {
				return nil, fmt.Errorf("install binary %s: %w", component.Name, err)
			}
			result.Binaries = append(result.Binaries, installedPath)
			continue
		}

		installedPath, err := copyFileUnder(shareDir, component.Path, sourcePath, assetMode(component.Path))
		if err != nil {
			return nil, fmt.Errorf("install asset %s: %w", component.Name, err)
		}
		result.Assets = append(result.Assets, installedPath)
	}

	for _, metadataName := range []string{manifestFileName, checksumsFileName, sbomFileName} {
		sourcePath, err := bundleFilePath(bundleDir, metadataName)
		if err != nil {
			return nil, fmt.Errorf("resolve metadata %s: %w", metadataName, err)
		}

		installedPath, err := copyFileUnder(shareDir, metadataName, sourcePath, 0o644)
		if err != nil {
			return nil, fmt.Errorf("install metadata %s: %w", metadataName, err)
		}
		result.Metadata = append(result.Metadata, installedPath)
	}

	sort.Strings(result.Assets)
	sort.Strings(result.Binaries)
	sort.Strings(result.Metadata)

	return result, nil
}

func validateBundle(bundleDir string) ([]string, *Manifest, error) {
	warnings := make([]string, 0)
	bundleErrors := make([]string, 0)

	checksumsPath, err := bundleFilePath(bundleDir, checksumsFileName)
	if err != nil {
		return warnings, nil, fmt.Errorf("%s missing: %w", checksumsFileName, err)
	}

	checksumsData, err := os.ReadFile(checksumsPath)
	if err != nil {
		return warnings, nil, fmt.Errorf("read %s: %w", checksumsFileName, err)
	}

	checksumsMap := make(map[string]string)
	for _, line := range strings.Split(string(checksumsData), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}

		parts := strings.SplitN(line, "  ", 2)
		if len(parts) != 2 {
			continue
		}

		normalizedPath, pathErr := validateManifestPath(parts[1])
		if pathErr != nil {
			bundleErrors = append(bundleErrors, fmt.Sprintf("%s entry %q invalid: %v", checksumsFileName, parts[1], pathErr))
			continue
		}
		checksumsMap[normalizedPath] = parts[0]
	}

	manifest, err := readManifest(bundleDir)
	if err != nil {
		return warnings, nil, fmt.Errorf("read manifest: %w", err)
	}

	if strings.TrimSpace(manifest.Product) == "" {
		bundleErrors = append(bundleErrors, "manifest product is empty")
	}
	if strings.TrimSpace(manifest.ReleaseTag) == "" {
		bundleErrors = append(bundleErrors, "manifest release_tag is empty")
	}
	if strings.TrimSpace(manifest.BuildDate) == "" {
		warnings = append(warnings, "manifest build_date is empty")
	}
	if len(manifest.Components) == 0 {
		bundleErrors = append(bundleErrors, "manifest has no components")
	}

	if _, err := bundleFilePath(bundleDir, sbomFileName); err != nil {
		bundleErrors = append(bundleErrors, sbomFileName+" missing from bundle")
	}

	for _, requiredEntry := range []string{manifestFileName, sbomFileName} {
		if _, exists := checksumsMap[requiredEntry]; !exists {
			bundleErrors = append(bundleErrors, fmt.Sprintf("%s missing required entry: %s", checksumsFileName, requiredEntry))
		}
	}

	if strings.TrimSpace(manifest.Provenance.Fingerprint) != "" {
		storedFingerprint := strings.TrimSpace(manifest.Provenance.Fingerprint)
		if strings.HasPrefix(storedFingerprint, "sha256:") {
			fingerprintChecksums := make(map[string]string, len(checksumsMap))
			for fileName, checksum := range checksumsMap {
				if fileName == manifestFileName {
					continue
				}
				fingerprintChecksums[fileName] = checksum
			}

			if computeFingerprintFromChecksums(fingerprintChecksums) != strings.TrimPrefix(storedFingerprint, "sha256:") {
				bundleErrors = append(bundleErrors, "provenance fingerprint mismatch: bundle may have been tampered with")
			}
		}
	}

	for _, component := range manifest.Components {
		componentPath, pathErr := validateManifestPath(component.Path)
		if pathErr != nil {
			bundleErrors = append(bundleErrors, fmt.Sprintf("component %s path %q invalid: %v", component.Name, component.Path, pathErr))
			continue
		}
		if !isPathContained(bundleDir, componentPath) {
			bundleErrors = append(bundleErrors, fmt.Sprintf("component %s path %q escapes bundle directory", component.Name, component.Path))
			continue
		}
		if _, exists := checksumsMap[componentPath]; !exists {
			bundleErrors = append(bundleErrors, fmt.Sprintf("component %s (%s) not covered by %s", component.Name, component.Path, checksumsFileName))
		}
	}

	for _, component := range manifest.Components {
		componentPath, pathErr := validateManifestPath(component.Path)
		if pathErr != nil || !isPathContained(bundleDir, componentPath) {
			continue
		}

		componentFilePath := filepath.Join(bundleDir, filepath.FromSlash(componentPath))
		if _, err := os.Stat(componentFilePath); err != nil {
			bundleErrors = append(bundleErrors, fmt.Sprintf("component %s file missing: %s", component.Name, component.Path))
			continue
		}

		actualChecksum, err := fileChecksum(componentFilePath)
		if err != nil {
			bundleErrors = append(bundleErrors, fmt.Sprintf("component %s checksum failed: %v", component.Name, err))
			continue
		}
		if actualChecksum != component.Checksum {
			bundleErrors = append(bundleErrors, fmt.Sprintf("component %s checksum mismatch: expected %s got %s", component.Name, component.Checksum, actualChecksum))
		}
	}

	if len(bundleErrors) > 0 {
		return warnings, nil, fmt.Errorf("bundle validation failed: %s", strings.Join(bundleErrors, "; "))
	}

	for fileName, expectedChecksum := range checksumsMap {
		if !isPathContained(bundleDir, fileName) {
			bundleErrors = append(bundleErrors, fmt.Sprintf("%s entry %q escapes bundle directory", checksumsFileName, fileName))
			continue
		}

		filePath := filepath.Join(bundleDir, filepath.FromSlash(fileName))
		actualChecksum, err := fileChecksum(filePath)
		if err != nil {
			bundleErrors = append(bundleErrors, fmt.Sprintf("%s entry %s: file not found", checksumsFileName, fileName))
			continue
		}
		if actualChecksum != expectedChecksum {
			bundleErrors = append(bundleErrors, fmt.Sprintf("%s entry %s: hash mismatch expected %s got %s", checksumsFileName, fileName, expectedChecksum, actualChecksum))
		}
	}

	if len(bundleErrors) > 0 {
		return warnings, nil, fmt.Errorf("bundle validation failed: %s", strings.Join(bundleErrors, "; "))
	}

	return warnings, manifest, nil
}

func readManifest(bundleDir string) (*Manifest, error) {
	manifestPath, err := bundleFilePath(bundleDir, manifestFileName)
	if err != nil {
		return nil, err
	}

	payload, err := os.ReadFile(manifestPath)
	if err != nil {
		return nil, fmt.Errorf("read manifest: %w", err)
	}

	var manifest Manifest
	if err := json.Unmarshal(payload, &manifest); err != nil {
		return nil, fmt.Errorf("decode manifest: %w", err)
	}

	return &manifest, nil
}

func bundleFilePath(bundleDir, relPath string) (string, error) {
	normalizedPath, err := validateManifestPath(relPath)
	if err != nil {
		return "", err
	}

	fullPath := filepath.Join(bundleDir, filepath.FromSlash(normalizedPath))
	resolvedPath, err := resolveExistingPath(fullPath)
	if err != nil {
		return "", err
	}
	if !pathWithinBase(bundleDir, resolvedPath) {
		return "", fmt.Errorf("path escapes bundle directory")
	}

	return resolvedPath, nil
}

func bundleBinaryName(relPath string) (string, error) {
	normalizedPath, err := validateManifestPath(relPath)
	if err != nil {
		return "", err
	}

	binaryName := path.Base(normalizedPath)
	if binaryName == "." || binaryName == "/" || strings.TrimSpace(binaryName) == "" {
		return "", fmt.Errorf("binary path is empty")
	}

	return binaryName, nil
}

func assetMode(relPath string) os.FileMode {
	normalizedPath, err := validateManifestPath(relPath)
	if err == nil && strings.HasPrefix(normalizedPath, "scripts/") {
		return 0o755
	}

	return 0o644
}

func copyFileUnder(baseDir, relPath, sourcePath string, mode os.FileMode) (string, error) {
	normalizedPath, err := validateManifestPath(relPath)
	if err != nil {
		return "", err
	}

	destinationDir := baseDir
	directoryPath := path.Dir(normalizedPath)
	if directoryPath != "." {
		destinationDir, err = ensureSubdir(baseDir, directoryPath)
		if err != nil {
			return "", err
		}
	}

	destinationPath := filepath.Join(destinationDir, filepath.Base(filepath.FromSlash(normalizedPath)))
	if err := copyFile(sourcePath, destinationPath, mode); err != nil {
		return "", err
	}

	return destinationPath, nil
}

func copyFile(sourcePath, destinationPath string, mode os.FileMode) (copyErr error) {
	sourceFile, err := os.Open(sourcePath)
	if err != nil {
		return fmt.Errorf("open source file: %w", err)
	}
	defer sourceFile.Close()

	if info, err := os.Lstat(destinationPath); err == nil && info.IsDir() {
		return fmt.Errorf("destination %s is a directory", destinationPath)
	}

	tempFile, err := os.CreateTemp(filepath.Dir(destinationPath), ".copilot-omni-install-*")
	if err != nil {
		return fmt.Errorf("create temp file for %s: %w", destinationPath, err)
	}

	tempPath := tempFile.Name()
	defer func() {
		if copyErr != nil {
			_ = os.Remove(tempPath)
		}
	}()

	if _, err := io.Copy(tempFile, sourceFile); err != nil {
		_ = tempFile.Close()
		return fmt.Errorf("copy %s to temp file: %w", sourcePath, err)
	}
	if err := tempFile.Chmod(mode); err != nil {
		_ = tempFile.Close()
		return fmt.Errorf("set mode on temp file for %s: %w", destinationPath, err)
	}
	if err := tempFile.Close(); err != nil {
		return fmt.Errorf("close temp file for %s: %w", destinationPath, err)
	}
	if err := os.Rename(tempPath, destinationPath); err != nil {
		return fmt.Errorf("move temp file into place for %s: %w", destinationPath, err)
	}

	return nil
}

func ensureDirectory(dirPath string) (string, error) {
	absPath, err := absolutePath(dirPath)
	if err != nil {
		return "", err
	}

	if err := os.MkdirAll(absPath, 0o755); err != nil {
		return "", fmt.Errorf("create directory %s: %w", absPath, err)
	}

	return resolveExistingDir(absPath)
}

func ensureSubdir(baseDir, relPath string) (string, error) {
	normalizedPath, err := validateManifestPath(relPath)
	if err != nil {
		return "", err
	}

	currentPath := baseDir
	for _, segment := range strings.Split(normalizedPath, "/") {
		if segment == "" {
			continue
		}

		nextPath := filepath.Join(currentPath, segment)
		if err := ensureDirectoryPath(nextPath); err != nil {
			return "", err
		}

		resolvedNextPath, err := resolveExistingDir(nextPath)
		if err != nil {
			return "", err
		}
		if !pathWithinBase(baseDir, resolvedNextPath) {
			return "", fmt.Errorf("path %s escapes install root", nextPath)
		}

		currentPath = resolvedNextPath
	}

	return currentPath, nil
}

func ensureDirectoryPath(dirPath string) error {
	info, err := os.Stat(dirPath)
	if err == nil {
		if !info.IsDir() {
			return fmt.Errorf("path %s is not a directory", dirPath)
		}
		return nil
	}
	if !os.IsNotExist(err) {
		return fmt.Errorf("stat %s: %w", dirPath, err)
	}
	if err := os.Mkdir(dirPath, 0o755); err != nil {
		return fmt.Errorf("create directory %s: %w", dirPath, err)
	}
	return nil
}

func computeFingerprintFromChecksums(checksumsMap map[string]string) string {
	keys := make([]string, 0, len(checksumsMap))
	for fileName := range checksumsMap {
		keys = append(keys, fileName)
	}
	sort.Strings(keys)

	hash := sha256.New()
	for _, fileName := range keys {
		_, _ = hash.Write([]byte(fileName))
		_, _ = hash.Write([]byte(checksumsMap[fileName]))
	}

	return hex.EncodeToString(hash.Sum(nil))
}

func fileChecksum(filePath string) (string, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return "", err
	}
	defer file.Close()

	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return "", err
	}

	return hex.EncodeToString(hash.Sum(nil)), nil
}

func normalizeManifestPath(relPath string) string {
	relPath = strings.TrimSpace(relPath)
	if relPath == "" {
		return ""
	}

	normalizedPath := strings.ReplaceAll(relPath, `\`, "/")
	cleanedPath := path.Clean(normalizedPath)
	if cleanedPath == "." {
		return ""
	}

	return strings.TrimPrefix(cleanedPath, "./")
}

func validateManifestPath(relPath string) (string, error) {
	normalizedPath := normalizeManifestPath(relPath)
	if normalizedPath == "" {
		return "", fmt.Errorf("path is empty")
	}
	if strings.HasPrefix(normalizedPath, "/") {
		return "", fmt.Errorf("path is absolute")
	}
	if normalizedPath == ".." || strings.HasPrefix(normalizedPath, "../") {
		return "", fmt.Errorf("path escapes bundle directory")
	}

	return normalizedPath, nil
}

func isPathContained(baseDir, relPath string) bool {
	normalizedPath, err := validateManifestPath(relPath)
	if err != nil {
		return false
	}

	fullPath := filepath.Join(baseDir, filepath.FromSlash(normalizedPath))
	resolvedBase, err := resolvePath(baseDir)
	if err != nil {
		return false
	}
	resolvedCandidate, err := resolvePath(fullPath)
	if err != nil {
		return false
	}

	return pathWithinBase(resolvedBase, resolvedCandidate)
}

func pathWithinBase(baseDir, candidatePath string) bool {
	cleanBaseDir := filepath.Clean(baseDir)
	cleanCandidatePath := filepath.Clean(candidatePath)
	if cleanCandidatePath == cleanBaseDir {
		return true
	}
	return strings.HasPrefix(cleanCandidatePath, cleanBaseDir+string(filepath.Separator))
}

func resolveExistingPath(filePath string) (string, error) {
	resolvedPath, err := resolvePath(filePath)
	if err != nil {
		return "", err
	}

	if _, err := os.Stat(resolvedPath); err != nil {
		return "", err
	}

	return resolvedPath, nil
}

func resolveExistingDir(dirPath string) (string, error) {
	resolvedPath, err := resolveExistingPath(dirPath)
	if err != nil {
		return "", err
	}

	info, err := os.Stat(resolvedPath)
	if err != nil {
		return "", err
	}
	if !info.IsDir() {
		return "", fmt.Errorf("%s is not a directory", resolvedPath)
	}

	return resolvedPath, nil
}

func resolvePath(filePath string) (string, error) {
	absPath, err := absolutePath(filePath)
	if err != nil {
		return "", err
	}

	if resolvedPath, err := filepath.EvalSymlinks(absPath); err == nil {
		return resolvedPath, nil
	} else if !os.IsNotExist(err) {
		return "", fmt.Errorf("resolve symlink %s: %w", absPath, err)
	}

	return absPath, nil
}

func absolutePath(filePath string) (string, error) {
	trimmedPath := strings.TrimSpace(filePath)
	if trimmedPath == "" {
		return "", fmt.Errorf("path is empty")
	}

	absPath, err := filepath.Abs(trimmedPath)
	if err != nil {
		return "", fmt.Errorf("make absolute path %s: %w", trimmedPath, err)
	}

	return absPath, nil
}
