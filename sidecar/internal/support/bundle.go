package support

import (
	"archive/zip"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"
)

// Bundle represents a support bundle with all diagnostic data
type Bundle struct {
	Version        string          `json:"version"`
	BundleID       string          `json:"bundle_id"`
	GeneratedAt    time.Time       `json:"generated_at"`
	RepoRoot       string          `json:"repo_root,omitempty"`
	RunID          string          `json:"run_id,omitempty"`
	Items          []BundleItem    `json:"items"`
	SystemInfo     SystemInfo      `json:"system_info"`
	RedactionRules []RedactionRule `json:"redaction_rules,omitempty"`
	RedactionLevel string          `json:"redaction_level"`
	SizeBytes      int64           `json:"size_bytes"`
	Checksum       string          `json:"checksum,omitempty"`
}

// BundleItem represents a single file in the bundle
type BundleItem struct {
	Path            string `json:"path"`
	Category        string `json:"category"`
	SizeBytes       int64  `json:"size_bytes"`
	SHA256          string `json:"sha256,omitempty"`
	Redacted        bool   `json:"redacted"`
	RedactionReason string `json:"redaction_reason,omitempty"`
}

// SystemInfo contains system diagnostic information
type SystemInfo struct {
	OS           string            `json:"os"`
	Architecture string            `json:"architecture"`
	GoVersion    string            `json:"go_version"`
	Hostname     string            `json:"hostname,omitempty"`
	Environment  map[string]string `json:"environment,omitempty"`
	WorkingDir   string            `json:"working_dir"`
	OmniVersion  string            `json:"omni_version,omitempty"`
}

// RedactionRule defines a pattern to redact from bundle
type RedactionRule struct {
	Name        string `json:"name"`
	Pattern     string `json:"pattern"`
	Replacement string `json:"replacement,omitempty"`
	Description string `json:"description,omitempty"`
}

// RedactionLevel controls how much data is redacted
type RedactionLevel string

const (
	RedactionMinimal    RedactionLevel = "minimal"
	RedactionStandard   RedactionLevel = "standard"
	RedactionAggressive RedactionLevel = "aggressive"
)

// CreateOptions configures bundle creation
type CreateOptions struct {
	RepoRoot         string
	RunID            string
	OutputPath       string
	IncludeLogs      bool
	IncludeArtifacts bool
	RedactionLevel   RedactionLevel
	MaxFileSize      int64
	MaxTotalSize     int64
}

// Creator generates support bundles
type Creator struct {
	collector *Collector
	redactor  *Redactor
}

// NewCreator creates a new bundle creator
func NewCreator() *Creator {
	return &Creator{
		collector: NewCollector(),
		redactor:  NewRedactor(),
	}
}

// Create generates a support bundle
func (c *Creator) Create(opts CreateOptions) (*Bundle, error) {
	if opts.RepoRoot == "" {
		cwd, err := os.Getwd()
		if err != nil {
			return nil, fmt.Errorf("get working directory: %w", err)
		}
		opts.RepoRoot = cwd
	}

	if opts.MaxFileSize == 0 {
		opts.MaxFileSize = 10 * 1024 * 1024 // 10MB default
	}
	if opts.MaxTotalSize == 0 {
		opts.MaxTotalSize = 100 * 1024 * 1024 // 100MB default
	}
	if opts.RedactionLevel == "" {
		opts.RedactionLevel = RedactionStandard
	}

	bundle := &Bundle{
		Version:        "1.0.0",
		BundleID:       generateBundleID(),
		GeneratedAt:    time.Now().UTC(),
		RepoRoot:       opts.RepoRoot,
		RunID:          opts.RunID,
		Items:          make([]BundleItem, 0),
		RedactionLevel: string(opts.RedactionLevel),
		RedactionRules: c.redactor.GetRules(opts.RedactionLevel),
	}

	// Collect system info
	sysInfo, err := c.collector.CollectSystemInfo()
	if err != nil {
		return nil, fmt.Errorf("collect system info: %w", err)
	}
	bundle.SystemInfo = sysInfo

	// Determine output path
	if opts.OutputPath == "" {
		opts.OutputPath = filepath.Join(opts.RepoRoot, ".omni", "support",
			fmt.Sprintf("support-bundle-%s.zip", bundle.BundleID))
	}

	// Create output directory
	if err := os.MkdirAll(filepath.Dir(opts.OutputPath), 0755); err != nil {
		return nil, fmt.Errorf("create output directory: %w", err)
	}

	// Create zip file
	zipFile, err := os.Create(opts.OutputPath)
	if err != nil {
		return nil, fmt.Errorf("create bundle file: %w", err)
	}
	defer zipFile.Close()

	zipWriter := zip.NewWriter(zipFile)
	defer zipWriter.Close()

	// Collect and add files
	if err := c.collectFiles(bundle, opts, zipWriter); err != nil {
		return nil, fmt.Errorf("collect files: %w", err)
	}

	// Write manifest
	if err := c.writeManifest(bundle, zipWriter); err != nil {
		return nil, fmt.Errorf("write manifest: %w", err)
	}

	// Calculate final size
	stat, err := zipFile.Stat()
	if err == nil {
		bundle.SizeBytes = stat.Size()
	}

	return bundle, nil
}

// collectFiles gathers all diagnostic files
func (c *Creator) collectFiles(bundle *Bundle, opts CreateOptions, zw *zip.Writer) error {
	collectedSize := int64(0)

	// Collect config files
	configFiles := []string{
		filepath.Join(opts.RepoRoot, ".omni", "config.json"),
	}

	for _, path := range configFiles {
		if _, err := os.Stat(path); err == nil {
			if err := c.addFile(bundle, zw, path, "config", opts, &collectedSize); err != nil {
				// Continue on error, log warning
				continue
			}
		}
	}

	// Collect recent logs
	if opts.IncludeLogs {
		logDir := filepath.Join(opts.RepoRoot, ".omni", "logs")
		if entries, err := os.ReadDir(logDir); err == nil {
			for _, entry := range entries {
				if entry.IsDir() {
					continue
				}
				path := filepath.Join(logDir, entry.Name())
				if err := c.addFile(bundle, zw, path, "logs", opts, &collectedSize); err != nil {
					continue
				}
			}
		}
	}

	// Collect run artifacts
	if opts.IncludeArtifacts && opts.RunID != "" {
		runDir := filepath.Join(opts.RepoRoot, ".omni", "runs", opts.RunID)
		if entries, err := os.ReadDir(runDir); err == nil {
			for _, entry := range entries {
				if entry.IsDir() {
					continue
				}
				path := filepath.Join(runDir, entry.Name())
				if err := c.addFile(bundle, zw, path, "artifacts", opts, &collectedSize); err != nil {
					continue
				}
			}
		}
	}

	return nil
}

// addFile adds a single file to the bundle
func (c *Creator) addFile(bundle *Bundle, zw *zip.Writer, path, category string, opts CreateOptions, totalSize *int64) error {
	info, err := os.Stat(path)
	if err != nil {
		return err
	}

	if info.Size() > opts.MaxFileSize {
		return fmt.Errorf("file exceeds max size: %s", path)
	}

	if *totalSize+info.Size() > opts.MaxTotalSize {
		return fmt.Errorf("bundle would exceed max total size")
	}

	// Read file content
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}

	// Apply redaction
	redactedData, wasRedacted := c.redactor.Redact(data, opts.RedactionLevel)

	// Add to zip
	relPath, _ := filepath.Rel(bundle.RepoRoot, path)
	if relPath == "" {
		relPath = filepath.Base(path)
	}

	header := &zip.FileHeader{
		Name:     relPath,
		Method:   zip.Deflate,
		Modified: info.ModTime(),
	}

	writer, err := zw.CreateHeader(header)
	if err != nil {
		return err
	}

	if _, err := writer.Write(redactedData); err != nil {
		return err
	}

	*totalSize += int64(len(redactedData))

	// Record item
	item := BundleItem{
		Path:      relPath,
		Category:  category,
		SizeBytes: int64(len(redactedData)),
		Redacted:  wasRedacted,
	}
	if wasRedacted {
		item.RedactionReason = "sensitive data"
	}

	bundle.Items = append(bundle.Items, item)
	return nil
}

// writeManifest writes the bundle manifest to the zip
func (c *Creator) writeManifest(bundle *Bundle, zw *zip.Writer) error {
	manifestData, err := json.MarshalIndent(bundle, "", "  ")
	if err != nil {
		return err
	}

	header := &zip.FileHeader{
		Name:     "manifest.json",
		Method:   zip.Deflate,
		Modified: bundle.GeneratedAt,
	}

	writer, err := zw.CreateHeader(header)
	if err != nil {
		return err
	}

	_, err = writer.Write(manifestData)
	return err
}

// generateBundleID creates a unique bundle identifier
func generateBundleID() string {
	return fmt.Sprintf("%s-%d", time.Now().Format("20060102-150405"), time.Now().UnixNano()%10000)
}

// Validate checks if a bundle is valid
func Validate(bundlePath string) error {
	reader, err := zip.OpenReader(bundlePath)
	if err != nil {
		return fmt.Errorf("open bundle: %w", err)
	}
	defer reader.Close()

	var manifestFound bool
	for _, file := range reader.File {
		if file.Name == "manifest.json" {
			manifestFound = true
			break
		}
	}

	if !manifestFound {
		return fmt.Errorf("bundle missing manifest.json")
	}

	return nil
}

// Extract extracts a bundle to a directory
func Extract(bundlePath, destDir string) error {
	reader, err := zip.OpenReader(bundlePath)
	if err != nil {
		return fmt.Errorf("open bundle: %w", err)
	}
	defer reader.Close()

	if err := os.MkdirAll(destDir, 0755); err != nil {
		return err
	}

	for _, file := range reader.File {
		path := filepath.Join(destDir, file.Name)

		if file.FileInfo().IsDir() {
			os.MkdirAll(path, file.Mode())
			continue
		}

		if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
			return err
		}

		outFile, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, file.Mode())
		if err != nil {
			return err
		}

		rc, err := file.Open()
		if err != nil {
			outFile.Close()
			return err
		}

		_, err = io.Copy(outFile, rc)
		rc.Close()
		outFile.Close()

		if err != nil {
			return err
		}
	}

	return nil
}
