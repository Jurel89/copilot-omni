package support

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"time"

	"github.com/Jurel89/copilot-omni/sidecar/internal/config"
	"github.com/Jurel89/copilot-omni/sidecar/internal/memory"
	"github.com/Jurel89/copilot-omni/sidecar/internal/version"
)

type SystemInfo struct {
	OS           string            `json:"os"`
	OSVersion    string            `json:"os_version,omitempty"`
	Architecture string            `json:"architecture"`
	GoVersion    string            `json:"go_version"`
	Hostname     string            `json:"hostname,omitempty"`
	WorkingDir   string            `json:"working_dir,omitempty"`
	OmniVersion  string            `json:"omni_version"`
	Environment  map[string]string `json:"environment,omitempty"`
}

type MemoryStoreStats struct {
	Path         string `json:"path,omitempty"`
	Exists       bool   `json:"exists"`
	SizeBytes    int64  `json:"size_bytes,omitempty"`
	RecordCount  int    `json:"record_count,omitempty"`
	ProjectCount int    `json:"project_count,omitempty"`
	GlobalCount  int    `json:"global_count,omitempty"`
	Status       string `json:"status"`
	Error        string `json:"error,omitempty"`
}

type CollectedItem struct {
	Path        string    `json:"path"`
	Category    string    `json:"category"`
	SourcePath  string    `json:"source_path,omitempty"`
	SizeBytes   int64     `json:"size_bytes"`
	Checksum    string    `json:"checksum,omitempty"`
	Redacted    bool      `json:"redacted"`
	CollectedAt time.Time `json:"collected_at"`
}

type CollectedFile struct {
	Item    CollectedItem
	Content []byte
}

type Collection struct {
	SystemInfo    SystemInfo       `json:"system_info"`
	Memory        MemoryStoreStats `json:"memory_store"`
	Files         []CollectedFile  `json:"-"`
	Errors        []string         `json:"errors,omitempty"`
	ConfigSummary map[string]any   `json:"config_summary,omitempty"`
}

type Collector struct{}

type CollectOptions struct {
	RepoRoot         string
	RunID            string
	IncludeLogs      bool
	IncludeArtifacts bool
	MaxFileSize      int64
	RecentLogCount   int
	RecentRunCount   int
	RedactionLevel   RedactionLevel
	Redactor         *Redactor
}

func NewCollector() *Collector {
	return &Collector{}
}

func (c *Collector) Collect(opts CollectOptions) (*Collection, error) {
	if strings.TrimSpace(opts.RepoRoot) == "" {
		return nil, fmt.Errorf("repo_root is required")
	}
	if opts.MaxFileSize <= 0 {
		opts.MaxFileSize = 10 * 1024 * 1024
	}
	if opts.RecentLogCount <= 0 {
		opts.RecentLogCount = 10
	}
	if opts.RecentRunCount <= 0 {
		opts.RecentRunCount = 3
	}
	if opts.Redactor == nil {
		opts.Redactor = NewRedactor()
	}

	collection := &Collection{
		Files:         make([]CollectedFile, 0),
		Errors:        make([]string, 0),
		ConfigSummary: make(map[string]any),
	}

	systemInfo, err := c.CollectSystemInfo(opts.RepoRoot)
	if err != nil {
		return nil, fmt.Errorf("collect system info: %w", err)
	}
	collection.SystemInfo = systemInfo

	memoryStats, err := c.CollectMemoryStoreStats(opts.RepoRoot)
	if err != nil {
		collection.Errors = append(collection.Errors, err.Error())
	} else {
		collection.Memory = memoryStats
	}

	if err := c.collectConfigFiles(collection, opts); err != nil {
		collection.Errors = append(collection.Errors, err.Error())
	}
	if opts.IncludeLogs {
		if err := c.collectRecentLogs(collection, opts); err != nil {
			collection.Errors = append(collection.Errors, err.Error())
		}
	}
	if opts.IncludeArtifacts {
		if err := c.collectRunArtifacts(collection, opts); err != nil {
			collection.Errors = append(collection.Errors, err.Error())
		}
	}

	return collection, nil
}

func (c *Collector) CollectSystemInfo(repoRoot string) (SystemInfo, error) {
	hostname, err := os.Hostname()
	if err != nil {
		hostname = ""
	}
	workingDir, err := os.Getwd()
	if err != nil {
		workingDir = ""
	}

	info := SystemInfo{
		OS:           runtime.GOOS,
		OSVersion:    detectOSVersion(),
		Architecture: runtime.GOARCH,
		GoVersion:    runtime.Version(),
		Hostname:     hostname,
		WorkingDir:   workingDir,
		OmniVersion:  version.Version,
		Environment: map[string]string{
			"COPILOT_OMNI_PROFILE": os.Getenv("COPILOT_OMNI_PROFILE"),
			"COPILOT_OMNI_DEBUG":   os.Getenv("COPILOT_OMNI_DEBUG"),
			"XDG_CONFIG_HOME":      os.Getenv("XDG_CONFIG_HOME"),
			"HOME":                 os.Getenv("HOME"),
			"USER":                 os.Getenv("USER"),
			"SHELL":                os.Getenv("SHELL"),
		},
	}

	if strings.TrimSpace(repoRoot) != "" {
		info.Environment["REPO_ROOT"] = repoRoot
	}

	return info, nil
}

func (c *Collector) CollectMemoryStoreStats(repoRoot string) (MemoryStoreStats, error) {
	resolvedConfig, err := config.Resolve(repoRoot)
	if err != nil {
		return MemoryStoreStats{}, fmt.Errorf("resolve config: %w", err)
	}

	dbPath := memory.DBPath(repoRoot, resolvedConfig.Memory.DBPath)
	stats := MemoryStoreStats{Path: dbPath, Status: "missing"}
	info, err := os.Stat(dbPath)
	if err != nil {
		if os.IsNotExist(err) {
			return stats, nil
		}
		stats.Status = "error"
		stats.Error = err.Error()
		return stats, nil
	}

	stats.Exists = true
	stats.SizeBytes = info.Size()
	stats.Status = "ok"

	store, err := memory.NewStore(dbPath)
	if err != nil {
		stats.Status = "error"
		stats.Error = err.Error()
		return stats, nil
	}
	defer store.Close()

	if stats.RecordCount, err = store.RecordCount(""); err != nil {
		stats.Status = "error"
		stats.Error = err.Error()
		return stats, nil
	}
	stats.ProjectCount, _ = store.RecordCount(memory.ScopeProject)
	stats.GlobalCount, _ = store.RecordCount(memory.ScopeGlobal)

	return stats, nil
}

func (c *Collector) collectConfigFiles(collection *Collection, opts CollectOptions) error {
	paths := []string{
		filepath.Join(opts.RepoRoot, ".omni", "config.json"),
		filepath.Join(opts.RepoRoot, "plugin", "plugin.json"),
		filepath.Join(opts.RepoRoot, "plugin", ".mcp.json"),
		filepath.Join(opts.RepoRoot, "plugin", "hooks.json"),
		filepath.Join(opts.RepoRoot, ".github", "copilot-instructions.md"),
		filepath.Join(opts.RepoRoot, "AGENTS.md"),
	}

	if global := resolvedGlobalConfigPath(); global != "" {
		paths = append(paths, global)
	}

	for _, path := range paths {
		if err := c.addFile(collection, path, "config", opts); err != nil {
			if !os.IsNotExist(err) {
				collection.Errors = append(collection.Errors, err.Error())
			}
		}
	}

	resolved, err := config.Resolve(opts.RepoRoot)
	if err == nil && resolved != nil {
		payload, marshalErr := json.MarshalIndent(resolved, "", "  ")
		if marshalErr == nil {
			redactedPayload, redacted := opts.Redactor.Redact(payload, opts.RedactionLevel)
			collection.ConfigSummary["resolved_config"] = json.RawMessage(payload)
			collection.Files = append(collection.Files, CollectedFile{
				Item: CollectedItem{
					Path:        filepath.Join("config", "resolved-config.json"),
					Category:    "config",
					SourcePath:  "resolved-config",
					SizeBytes:   int64(len(redactedPayload)),
					Redacted:    redacted,
					CollectedAt: time.Now().UTC(),
				},
				Content: redactedPayload,
			})
		}
	}

	return nil
}

func (c *Collector) collectRecentLogs(collection *Collection, opts CollectOptions) error {
	logDir := filepath.Join(opts.RepoRoot, ".omni", "logs")
	if resolved, err := config.Resolve(opts.RepoRoot); err == nil && strings.TrimSpace(resolved.Sidecar.LogPath) != "" {
		if filepath.IsAbs(resolved.Sidecar.LogPath) {
			logDir = resolved.Sidecar.LogPath
		} else {
			logDir = filepath.Join(opts.RepoRoot, resolved.Sidecar.LogPath)
		}
	}

	entries, err := os.ReadDir(logDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return fmt.Errorf("read logs directory %s: %w", logDir, err)
	}

	type logEntry struct {
		name string
		path string
		mod  time.Time
	}

	logs := make([]logEntry, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			continue
		}
		logs = append(logs, logEntry{name: entry.Name(), path: filepath.Join(logDir, entry.Name()), mod: info.ModTime()})
	}

	sort.Slice(logs, func(i, j int) bool { return logs[i].mod.After(logs[j].mod) })
	if len(logs) > opts.RecentLogCount {
		logs = logs[:opts.RecentLogCount]
	}

	for _, entry := range logs {
		if err := c.addFile(collection, entry.path, "logs", opts); err != nil {
			collection.Errors = append(collection.Errors, err.Error())
		}
	}

	return nil
}

func (c *Collector) collectRunArtifacts(collection *Collection, opts CollectOptions) error {
	runsRoot := filepath.Join(opts.RepoRoot, ".omni", "runs")
	if strings.TrimSpace(opts.RunID) != "" {
		return c.addRunDirectory(collection, filepath.Join(runsRoot, opts.RunID), opts)
	}

	entries, err := os.ReadDir(runsRoot)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return fmt.Errorf("read runs directory %s: %w", runsRoot, err)
	}

	type runEntry struct {
		path string
		mod  time.Time
	}

	runs := make([]runEntry, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			continue
		}
		runs = append(runs, runEntry{path: filepath.Join(runsRoot, entry.Name()), mod: info.ModTime()})
	}
	sort.Slice(runs, func(i, j int) bool { return runs[i].mod.After(runs[j].mod) })
	if len(runs) > opts.RecentRunCount {
		runs = runs[:opts.RecentRunCount]
	}
	for _, run := range runs {
		if err := c.addRunDirectory(collection, run.path, opts); err != nil {
			collection.Errors = append(collection.Errors, err.Error())
		}
	}
	return nil
}

func (c *Collector) addRunDirectory(collection *Collection, runDir string, opts CollectOptions) error {
	entries, err := os.ReadDir(runDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return fmt.Errorf("read run directory %s: %w", runDir, err)
	}

	for _, entry := range entries {
		path := filepath.Join(runDir, entry.Name())
		if entry.IsDir() {
			if entry.Name() != "verification" && entry.Name() != "transcripts" {
				continue
			}
			if err := c.addDirectoryFiles(collection, path, "artifacts", opts); err != nil {
				collection.Errors = append(collection.Errors, err.Error())
			}
			continue
		}
		if err := c.addFile(collection, path, "artifacts", opts); err != nil {
			collection.Errors = append(collection.Errors, err.Error())
		}
	}

	return nil
}

func (c *Collector) addDirectoryFiles(collection *Collection, root string, category string, opts CollectOptions) error {
	return filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		if addErr := c.addFile(collection, path, category, opts); addErr != nil {
			collection.Errors = append(collection.Errors, addErr.Error())
		}
		return nil
	})
}

func (c *Collector) addFile(collection *Collection, sourcePath string, category string, opts CollectOptions) error {
	info, err := os.Stat(sourcePath)
	if err != nil {
		return err
	}
	if info.IsDir() {
		return nil
	}
	if info.Size() > opts.MaxFileSize {
		return fmt.Errorf("skip %s: file exceeds max size", sourcePath)
	}

	content, err := os.ReadFile(sourcePath)
	if err != nil {
		return fmt.Errorf("read %s: %w", sourcePath, err)
	}

	redactedContent, redacted := opts.Redactor.Redact(content, opts.RedactionLevel)
	relPath, err := relativeBundlePath(opts.RepoRoot, sourcePath, category)
	if err != nil {
		return err
	}
	redactedSource, _ := opts.Redactor.RedactPath(sourcePath, opts.RedactionLevel)

	collection.Files = append(collection.Files, CollectedFile{
		Item: CollectedItem{
			Path:        relPath,
			Category:    category,
			SourcePath:  redactedSource,
			SizeBytes:   int64(len(redactedContent)),
			Redacted:    redacted,
			CollectedAt: time.Now().UTC(),
		},
		Content: redactedContent,
	})

	return nil
}

func relativeBundlePath(repoRoot, sourcePath, category string) (string, error) {
	relPath, err := filepath.Rel(repoRoot, sourcePath)
	if err == nil && relPath != "." && !strings.HasPrefix(relPath, ".."+string(filepath.Separator)) {
		return filepath.ToSlash(relPath), nil
	}
	base := filepath.Base(sourcePath)
	if strings.TrimSpace(category) == "" {
		return base, nil
	}
	return filepath.ToSlash(filepath.Join(category, base)), nil
}

func resolvedGlobalConfigPath() string {
	if xdgConfigHome := strings.TrimSpace(os.Getenv("XDG_CONFIG_HOME")); xdgConfigHome != "" {
		return filepath.Join(xdgConfigHome, "copilot-omni", "config.json")
	}
	homeDir, err := os.UserHomeDir()
	if err != nil || strings.TrimSpace(homeDir) == "" {
		return ""
	}
	return filepath.Join(homeDir, ".copilot-omni", "config.json")
}

func detectOSVersion() string {
	data, err := os.ReadFile("/etc/os-release")
	if err != nil {
		return ""
	}
	scanner := bufio.NewScanner(strings.NewReader(string(data)))
	for scanner.Scan() {
		line := scanner.Text()
		if value, ok := strings.CutPrefix(line, "PRETTY_NAME="); ok {
			return strings.Trim(value, `"`)
		}
	}
	return ""
}
