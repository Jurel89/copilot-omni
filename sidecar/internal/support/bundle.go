package support

import (
	"archive/zip"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/copilot-omni/sidecar/internal/artifact"
	"github.com/copilot-omni/sidecar/internal/doctor"
)

type Bundle struct {
	Version        string              `json:"version"`
	BundleID       string              `json:"bundle_id"`
	GeneratedAt    time.Time           `json:"generated_at"`
	RepoRoot       string              `json:"repo_root,omitempty"`
	RunID          string              `json:"run_id,omitempty"`
	Format         string              `json:"format"`
	Status         string              `json:"status"`
	RedactionLevel RedactionLevel      `json:"redaction_level"`
	SystemInfo     SystemInfo          `json:"system_info"`
	MemoryStore    MemoryStoreStats    `json:"memory_store"`
	Diagnostics    []doctor.Diagnostic `json:"diagnostics"`
	Items          []CollectedItem     `json:"items"`
	Errors         []string            `json:"errors,omitempty"`
	SizeBytes      int64               `json:"size_bytes"`
	Checksum       string              `json:"checksum,omitempty"`
	Manifest       *Manifest           `json:"manifest,omitempty"`
}

type CreateOptions struct {
	RepoRoot         string
	RunID            string
	OutputPath       string
	IncludeLogs      bool
	IncludeArtifacts bool
	RedactionLevel   RedactionLevel
	MaxFileSize      int64
	MaxTotalSize     int64
	RecentLogCount   int
	RecentRunCount   int
}

type Creator struct {
	collector *Collector
	redactor  *Redactor
}

func NewCreator() *Creator {
	return &Creator{
		collector: NewCollector(),
		redactor:  NewRedactor(),
	}
}

func (c *Creator) Create(opts CreateOptions) (*Bundle, error) {
	bundleID := generateBundleID()

	if strings.TrimSpace(opts.RepoRoot) == "" {
		cwd, err := os.Getwd()
		if err != nil {
			return nil, fmt.Errorf("get working directory: %w", err)
		}
		opts.RepoRoot = cwd
	}
	if opts.MaxFileSize <= 0 {
		opts.MaxFileSize = 10 * 1024 * 1024
	}
	if opts.MaxTotalSize <= 0 {
		opts.MaxTotalSize = 100 * 1024 * 1024
	}
	if opts.RedactionLevel == "" {
		opts.RedactionLevel = RedactionStandard
	}
	if strings.TrimSpace(opts.OutputPath) == "" {
		opts.OutputPath = filepath.Join(opts.RepoRoot, ".omni", "support", fmt.Sprintf("support-bundle-%s.zip", bundleID))
	}

	collection, err := c.collector.Collect(CollectOptions{
		RepoRoot:         opts.RepoRoot,
		RunID:            opts.RunID,
		IncludeLogs:      opts.IncludeLogs,
		IncludeArtifacts: opts.IncludeArtifacts,
		MaxFileSize:      opts.MaxFileSize,
		RecentLogCount:   opts.RecentLogCount,
		RecentRunCount:   opts.RecentRunCount,
		RedactionLevel:   opts.RedactionLevel,
		Redactor:         c.redactor,
	})
	if err != nil {
		return nil, err
	}

	diagnostics := doctor.RunAll(opts.RepoRoot).Diagnostics
	redactedRepoRoot, _ := c.redactor.RedactPath(opts.RepoRoot, opts.RedactionLevel)
	bundle := &Bundle{
		Version:        "1",
		BundleID:       bundleID,
		GeneratedAt:    time.Now().UTC(),
		RepoRoot:       redactedRepoRoot,
		RunID:          opts.RunID,
		Format:         bundleFormatFromOutputPath(opts.OutputPath),
		Status:         statusFromDiagnostics(diagnostics),
		RedactionLevel: opts.RedactionLevel,
		SystemInfo:     redactSystemInfo(collection.SystemInfo, c.redactor, opts.RedactionLevel),
		MemoryStore:    redactMemoryStore(collection.Memory, c.redactor, opts.RedactionLevel),
		Diagnostics:    diagnostics,
		Items:          make([]CollectedItem, 0, len(collection.Files)),
		Errors:         append([]string(nil), collection.Errors...),
	}

	totalSize := int64(0)
	for _, file := range collection.Files {
		file.Item.Checksum = checksumBytes(file.Content)
		totalSize += int64(len(file.Content))
		if totalSize > opts.MaxTotalSize {
			bundle.Errors = append(bundle.Errors, fmt.Sprintf("bundle size limit reached after %s", file.Item.Path))
			break
		}
		bundle.Items = append(bundle.Items, file.Item)
	}

	manifest, err := NewManifest(bundle)
	if err != nil {
		return nil, err
	}
	bundle.Manifest = manifest
	bundle.Checksum = manifest.Checksum

	stagingDir, err := os.MkdirTemp("", "copilot-omni-support-*")
	if err != nil {
		return nil, fmt.Errorf("create staging directory: %w", err)
	}
	defer os.RemoveAll(stagingDir)

	if err := c.writeStagedBundle(stagingDir, bundle, collection.Files); err != nil {
		return nil, err
	}

	if bundle.Format == "zip" {
		if err := writeZipBundle(stagingDir, opts.OutputPath); err != nil {
			return nil, err
		}
	} else {
		if err := writeDirectoryBundle(stagingDir, opts.OutputPath); err != nil {
			return nil, err
		}
	}

	if info, err := os.Stat(opts.OutputPath); err == nil {
		bundle.SizeBytes = info.Size()
	} else if bundle.Format == "directory" {
		bundle.SizeBytes = totalSize
	}

	return bundle, nil
}

func (c *Creator) writeStagedBundle(stagingDir string, bundle *Bundle, files []CollectedFile) error {
	selected := make(map[string]CollectedFile, len(files))
	for _, file := range files {
		selected[file.Item.Path] = file
	}

	for _, item := range bundle.Items {
		file, ok := selected[item.Path]
		if !ok {
			continue
		}
		targetPath := filepath.Join(stagingDir, filepath.FromSlash(item.Path))
		if err := artifact.WriteFile(targetPath, file.Content); err != nil {
			return fmt.Errorf("write staged file %s: %w", item.Path, err)
		}
	}

	manifestBytes, err := bundle.Manifest.JSON()
	if err != nil {
		return fmt.Errorf("marshal manifest: %w", err)
	}
	if err := artifact.WriteFile(filepath.Join(stagingDir, "manifest.json"), manifestBytes); err != nil {
		return fmt.Errorf("write manifest: %w", err)
	}

	bundleBytes, err := json.MarshalIndent(bundle, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal bundle: %w", err)
	}
	if err := artifact.WriteFile(filepath.Join(stagingDir, "bundle.json"), bundleBytes); err != nil {
		return fmt.Errorf("write bundle metadata: %w", err)
	}

	return nil
}

func bundleFormatFromOutputPath(outputPath string) string {
	if strings.EqualFold(filepath.Ext(outputPath), ".zip") {
		return "zip"
	}
	return "directory"
}

func writeDirectoryBundle(stagingDir, outputDir string) error {
	if err := os.RemoveAll(outputDir); err != nil {
		return fmt.Errorf("reset output directory: %w", err)
	}
	return filepath.WalkDir(stagingDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		relPath, err := filepath.Rel(stagingDir, path)
		if err != nil {
			return err
		}
		if relPath == "." {
			return os.MkdirAll(outputDir, 0o755)
		}
		targetPath := filepath.Join(outputDir, relPath)
		if d.IsDir() {
			return os.MkdirAll(targetPath, 0o755)
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		return artifact.WriteFile(targetPath, data)
	})
}

func writeZipBundle(stagingDir, outputPath string) error {
	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		return fmt.Errorf("create output directory: %w", err)
	}
	tempFile, err := os.CreateTemp(filepath.Dir(outputPath), ".support-bundle-*.zip")
	if err != nil {
		return fmt.Errorf("create temp bundle: %w", err)
	}
	tempPath := tempFile.Name()
	defer os.Remove(tempPath)

	zw := zip.NewWriter(tempFile)
	paths := make([]string, 0)
	if err := filepath.WalkDir(stagingDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		relPath, err := filepath.Rel(stagingDir, path)
		if err != nil {
			return err
		}
		paths = append(paths, relPath)
		return nil
	}); err != nil {
		_ = zw.Close()
		_ = tempFile.Close()
		return fmt.Errorf("walk staged bundle: %w", err)
	}
	sort.Strings(paths)
	for _, relPath := range paths {
		sourcePath := filepath.Join(stagingDir, relPath)
		info, err := os.Stat(sourcePath)
		if err != nil {
			_ = zw.Close()
			_ = tempFile.Close()
			return fmt.Errorf("stat staged file %s: %w", relPath, err)
		}
		header, err := zip.FileInfoHeader(info)
		if err != nil {
			_ = zw.Close()
			_ = tempFile.Close()
			return fmt.Errorf("zip header %s: %w", relPath, err)
		}
		header.Name = filepath.ToSlash(relPath)
		header.Method = zip.Deflate
		writer, err := zw.CreateHeader(header)
		if err != nil {
			_ = zw.Close()
			_ = tempFile.Close()
			return fmt.Errorf("create zip entry %s: %w", relPath, err)
		}
		file, err := os.Open(sourcePath)
		if err != nil {
			_ = zw.Close()
			_ = tempFile.Close()
			return fmt.Errorf("open staged file %s: %w", relPath, err)
		}
		_, copyErr := io.Copy(writer, file)
		closeErr := file.Close()
		if copyErr != nil {
			_ = zw.Close()
			_ = tempFile.Close()
			return fmt.Errorf("copy zip entry %s: %w", relPath, copyErr)
		}
		if closeErr != nil {
			_ = zw.Close()
			_ = tempFile.Close()
			return fmt.Errorf("close staged file %s: %w", relPath, closeErr)
		}
	}
	if err := zw.Close(); err != nil {
		_ = tempFile.Close()
		return fmt.Errorf("close zip writer: %w", err)
	}
	if err := tempFile.Close(); err != nil {
		return fmt.Errorf("close temp bundle: %w", err)
	}
	if err := os.Rename(tempPath, outputPath); err != nil {
		return fmt.Errorf("move bundle into place: %w", err)
	}
	return nil
}

func redactSystemInfo(info SystemInfo, redactor *Redactor, level RedactionLevel) SystemInfo {
	info.Hostname, _ = redactor.RedactString(info.Hostname, level)
	info.WorkingDir, _ = redactor.RedactPath(info.WorkingDir, level)
	if len(info.Environment) > 0 {
		redactedEnv := make(map[string]string, len(info.Environment))
		for key, value := range info.Environment {
			updated := value
			if strings.Contains(strings.ToUpper(key), "PATH") || key == "HOME" {
				updated, _ = redactor.RedactPath(value, level)
			} else {
				updated, _ = redactor.RedactString(value, level)
			}
			redactedEnv[key] = updated
		}
		info.Environment = redactedEnv
	}
	return info
}

func redactMemoryStore(stats MemoryStoreStats, redactor *Redactor, level RedactionLevel) MemoryStoreStats {
	stats.Path, _ = redactor.RedactPath(stats.Path, level)
	if stats.Error != "" {
		stats.Error, _ = redactor.RedactString(stats.Error, level)
	}
	return stats
}

func generateBundleID() string {
	return fmt.Sprintf("%s-%04d", time.Now().UTC().Format("20060102-150405"), time.Now().UTC().UnixNano()%10000)
}

func Validate(bundlePath string) error {
	manifestData, err := readManifestData(bundlePath)
	if err != nil {
		return err
	}
	var manifest Manifest
	if err := json.Unmarshal(manifestData, &manifest); err != nil {
		return fmt.Errorf("decode manifest: %w", err)
	}
	recalculated, err := manifest.computeChecksum()
	if err != nil {
		return err
	}
	if manifest.Checksum != recalculated {
		return fmt.Errorf("manifest checksum mismatch")
	}
	return nil
}

func Extract(bundlePath, destDir string) error {
	reader, err := zip.OpenReader(bundlePath)
	if err != nil {
		return fmt.Errorf("open bundle: %w", err)
	}
	defer reader.Close()
	if err := os.MkdirAll(destDir, 0o755); err != nil {
		return fmt.Errorf("create destination directory: %w", err)
	}
	for _, file := range reader.File {
		targetPath := filepath.Join(destDir, filepath.FromSlash(file.Name))
		if file.FileInfo().IsDir() {
			if err := os.MkdirAll(targetPath, 0o755); err != nil {
				return fmt.Errorf("create extracted directory: %w", err)
			}
			continue
		}
		rc, err := file.Open()
		if err != nil {
			return fmt.Errorf("open zip entry %s: %w", file.Name, err)
		}
		data, readErr := io.ReadAll(rc)
		closeErr := rc.Close()
		if readErr != nil {
			return fmt.Errorf("read zip entry %s: %w", file.Name, readErr)
		}
		if closeErr != nil {
			return fmt.Errorf("close zip entry %s: %w", file.Name, closeErr)
		}
		if err := artifact.WriteFile(targetPath, data); err != nil {
			return fmt.Errorf("write extracted file %s: %w", file.Name, err)
		}
	}
	return nil
}

func readManifestData(bundlePath string) ([]byte, error) {
	if info, err := os.Stat(bundlePath); err == nil && info.IsDir() {
		data, readErr := os.ReadFile(filepath.Join(bundlePath, "manifest.json"))
		if readErr != nil {
			return nil, fmt.Errorf("read manifest: %w", readErr)
		}
		return data, nil
	}
	reader, err := zip.OpenReader(bundlePath)
	if err != nil {
		return nil, fmt.Errorf("open bundle: %w", err)
	}
	defer reader.Close()
	for _, file := range reader.File {
		if file.Name != "manifest.json" {
			continue
		}
		rc, err := file.Open()
		if err != nil {
			return nil, fmt.Errorf("open manifest: %w", err)
		}
		data, readErr := io.ReadAll(rc)
		closeErr := rc.Close()
		if readErr != nil {
			return nil, fmt.Errorf("read manifest: %w", readErr)
		}
		if closeErr != nil {
			return nil, fmt.Errorf("close manifest: %w", closeErr)
		}
		return data, nil
	}
	return nil, fmt.Errorf("bundle missing manifest.json")
}
