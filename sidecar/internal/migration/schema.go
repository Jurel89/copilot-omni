package migration

import (
	"database/sql"
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

const (
	SchemaConfig   = "config"
	SchemaArtifact = "artifact"
	SchemaMemory   = "memory"
)

const (
	ConfigSchemaVersion1         = 1
	CurrentConfigSchemaVersion   = ConfigSchemaVersion1
	ArtifactSchemaVersion1       = 1
	CurrentArtifactSchemaVersion = ArtifactSchemaVersion1
	MemorySchemaVersion1         = 1
	CurrentMemorySchemaVersion   = MemorySchemaVersion1
)

func NewRegistryForRepo(repoRoot string) *Registry {
	return NewRegistry(DefaultStatePath(repoRoot))
}

func NewConfigEngine(repoRoot, configPath string, registry *Registry) (*Engine, error) {
	return newSchemaEngine(SchemaConfig, Context{
		RepoRoot:   strings.TrimSpace(repoRoot),
		ConfigPath: strings.TrimSpace(configPath),
	}, registry, ConfigMigrations())
}

func NewArtifactEngine(repoRoot, artifactRoot string, registry *Registry) (*Engine, error) {
	return newSchemaEngine(SchemaArtifact, Context{
		RepoRoot:     strings.TrimSpace(repoRoot),
		ArtifactRoot: strings.TrimSpace(artifactRoot),
	}, registry, ArtifactMigrations())
}

func NewMemoryEngine(repoRoot, memoryDBPath string, registry *Registry) (*Engine, error) {
	return newSchemaEngine(SchemaMemory, Context{
		RepoRoot:     strings.TrimSpace(repoRoot),
		MemoryDBPath: strings.TrimSpace(memoryDBPath),
	}, registry, MemoryMigrations())
}

func DefaultStatePath(repoRoot string) string {
	repoRoot = strings.TrimSpace(repoRoot)
	if repoRoot == "" {
		return ""
	}

	return filepath.Join(repoRoot, ".omni", "migrations", "state.json")
}

func DefaultConfigPath(repoRoot string) string {
	repoRoot = strings.TrimSpace(repoRoot)
	if repoRoot == "" {
		return ""
	}

	return filepath.Join(repoRoot, ".omni", "config.json")
}

func DefaultArtifactRoot(repoRoot string) string {
	repoRoot = strings.TrimSpace(repoRoot)
	if repoRoot == "" {
		return ""
	}

	return filepath.Join(repoRoot, ".omni")
}

func DefaultArtifactSchemaPath(repoRoot, artifactRoot string) string {
	root := resolveRelativePath(repoRoot, artifactRoot)
	if root == "" {
		root = DefaultArtifactRoot(repoRoot)
	}

	if root == "" {
		return ""
	}

	return filepath.Join(root, "schema", "artifacts.json")
}

func DefaultMemoryDBPath(repoRoot string) string {
	repoRoot = strings.TrimSpace(repoRoot)
	if repoRoot == "" {
		return ""
	}

	return filepath.Join(repoRoot, ".omni", "memory.db")
}

func ConfigMigrations() []Migration {
	return []Migration{{
		Version: ConfigSchemaVersion1,
		Name:    "config_schema_v1",
		Up:      applyConfigSchemaV1,
		Down:    rollbackConfigSchemaV1,
	}}
}

func ArtifactMigrations() []Migration {
	return []Migration{{
		Version: ArtifactSchemaVersion1,
		Name:    "artifact_schema_v1",
		Up:      applyArtifactSchemaV1,
		Down:    rollbackArtifactSchemaV1,
	}}
}

func MemoryMigrations() []Migration {
	return []Migration{{
		Version:       MemorySchemaVersion1,
		Name:          "memory_schema_v1",
		Up:            applyMemorySchemaV1,
		Down:          rollbackMemorySchemaV1,
		RollbackCheck: ensureMemoryRollbackSafe,
	}}
}

func newSchemaEngine(name string, context Context, registry *Registry, migrations []Migration) (*Engine, error) {
	if registry == nil {
		registry = NewRegistry(DefaultStatePath(context.RepoRoot))
	}

	engine := NewEngine(name, registry, context)
	for _, migration := range migrations {
		if err := engine.Register(migration); err != nil {
			return nil, err
		}
	}

	return engine, nil
}

func applyConfigSchemaV1(ctx *Context) error {
	configPath, err := resolveConfigPath(ctx)
	if err != nil {
		return err
	}

	values, exists, err := readOptionalJSONObject(configPath)
	if err != nil {
		return err
	}

	if !exists {
		return nil
	}

	values["version"] = strconv.Itoa(ConfigSchemaVersion1)
	return writeJSONObject(configPath, values)
}

func rollbackConfigSchemaV1(ctx *Context) error {
	configPath, err := resolveConfigPath(ctx)
	if err != nil {
		return err
	}

	values, exists, err := readOptionalJSONObject(configPath)
	if err != nil {
		return err
	}

	if !exists {
		return nil
	}

	if versionString(values["version"]) != strconv.Itoa(ConfigSchemaVersion1) {
		return nil
	}

	delete(values, "version")
	return writeJSONObject(configPath, values)
}

func applyArtifactSchemaV1(ctx *Context) error {
	schemaPath, err := resolveArtifactSchemaPath(ctx)
	if err != nil {
		return err
	}

	values, exists, err := readOptionalJSONObject(schemaPath)
	if err != nil {
		return err
	}

	if !exists {
		values = make(map[string]any)
	}

	values["kind"] = SchemaArtifact
	values["version"] = ArtifactSchemaVersion1
	values["updated_at"] = time.Now().UTC().Format(time.RFC3339)
	return writeJSONObject(schemaPath, values)
}

func rollbackArtifactSchemaV1(ctx *Context) error {
	schemaPath, err := resolveArtifactSchemaPath(ctx)
	if err != nil {
		return err
	}

	values, exists, err := readOptionalJSONObject(schemaPath)
	if err != nil {
		return err
	}

	if !exists {
		return nil
	}

	delete(values, "kind")
	delete(values, "version")
	delete(values, "updated_at")

	if len(values) == 0 {
		return removeFileIfExists(schemaPath)
	}

	return writeJSONObject(schemaPath, values)
}

func applyMemorySchemaV1(ctx *Context) error {
	dbPath, err := resolveMemoryDBPath(ctx)
	if err != nil {
		return err
	}

	db, err := openSQLiteForMigration(dbPath)
	if err != nil {
		return err
	}
	defer db.Close()

	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS memory_records (
			id TEXT PRIMARY KEY,
			type TEXT NOT NULL,
			source TEXT NOT NULL,
			scope TEXT NOT NULL,
			run_id TEXT NOT NULL DEFAULT '',
			title TEXT NOT NULL,
			content TEXT NOT NULL,
			metadata TEXT NOT NULL DEFAULT '{}',
			tags TEXT NOT NULL DEFAULT '',
			trust_level TEXT NOT NULL DEFAULT 'medium',
			sensitivity TEXT NOT NULL DEFAULT 'normal',
			created_at DATETIME NOT NULL,
			updated_at DATETIME NOT NULL
		);
		CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_records(type);
		CREATE INDEX IF NOT EXISTS idx_memory_scope ON memory_records(scope);
		CREATE INDEX IF NOT EXISTS idx_memory_run_id ON memory_records(run_id);
		CREATE INDEX IF NOT EXISTS idx_memory_created_at ON memory_records(created_at);
	`)
	if err != nil {
		return &Error{Code: "apply_memory_schema_failed", Path: dbPath, Err: err}
	}

	return nil
}

func rollbackMemorySchemaV1(ctx *Context) error {
	dbPath, err := resolveMemoryDBPath(ctx)
	if err != nil {
		return err
	}

	db, exists, err := openSQLiteIfExists(dbPath)
	if err != nil {
		return err
	}

	if !exists {
		return nil
	}
	defer db.Close()

	_, err = db.Exec(`
		DROP INDEX IF EXISTS idx_memory_created_at;
		DROP INDEX IF EXISTS idx_memory_run_id;
		DROP INDEX IF EXISTS idx_memory_scope;
		DROP INDEX IF EXISTS idx_memory_type;
		DROP TABLE IF EXISTS memory_records;
	`)
	if err != nil {
		return &Error{Code: "rollback_memory_schema_failed", Path: dbPath, Err: err}
	}

	return nil
}

func ensureMemoryRollbackSafe(ctx *Context) error {
	dbPath, err := resolveMemoryDBPath(ctx)
	if err != nil {
		return err
	}

	db, exists, err := openSQLiteIfExists(dbPath)
	if err != nil {
		return err
	}

	if !exists {
		return nil
	}
	defer db.Close()

	tableExists, err := sqliteTableExists(db, "memory_records")
	if err != nil {
		return err
	}

	if !tableExists {
		return nil
	}

	var count int
	if err := db.QueryRow(`SELECT COUNT(*) FROM memory_records`).Scan(&count); err != nil {
		return &Error{Code: "count_memory_records_failed", Path: dbPath, Err: err}
	}

	if count > 0 {
		return &Error{Code: "rollback_requires_empty_memory_store", Path: dbPath}
	}

	return nil
}

func resolveConfigPath(ctx *Context) (string, error) {
	if ctx == nil {
		return "", &Error{Code: "nil_context"}
	}

	configPath := resolveRelativePath(ctx.RepoRoot, ctx.ConfigPath)
	if configPath == "" {
		configPath = DefaultConfigPath(ctx.RepoRoot)
	}

	if configPath == "" {
		return "", &Error{Code: "invalid_config_path"}
	}

	return configPath, nil
}

func resolveArtifactSchemaPath(ctx *Context) (string, error) {
	if ctx == nil {
		return "", &Error{Code: "nil_context"}
	}

	schemaPath := DefaultArtifactSchemaPath(ctx.RepoRoot, ctx.ArtifactRoot)
	if schemaPath == "" {
		return "", &Error{Code: "invalid_artifact_path"}
	}

	return schemaPath, nil
}

func resolveMemoryDBPath(ctx *Context) (string, error) {
	if ctx == nil {
		return "", &Error{Code: "nil_context"}
	}

	dbPath := resolveRelativePath(ctx.RepoRoot, ctx.MemoryDBPath)
	if dbPath == "" {
		dbPath = DefaultMemoryDBPath(ctx.RepoRoot)
	}

	if dbPath == "" {
		return "", &Error{Code: "invalid_db_path"}
	}

	return dbPath, nil
}

func resolveRelativePath(repoRoot, value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}

	if filepath.IsAbs(value) {
		return filepath.Clean(value)
	}

	repoRoot = strings.TrimSpace(repoRoot)
	if repoRoot == "" {
		return filepath.Clean(value)
	}

	return filepath.Join(repoRoot, value)
}

func readOptionalJSONObject(path string) (map[string]any, bool, error) {
	payload, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, false, nil
		}

		return nil, false, &Error{Code: "read_file_failed", Path: path, Err: err}
	}

	values := make(map[string]any)
	if len(payload) == 0 {
		return values, true, nil
	}

	if err := json.Unmarshal(payload, &values); err != nil {
		return nil, true, &Error{Code: "parse_json_failed", Path: path, Err: err}
	}

	return values, true, nil
}

func writeJSONObject(path string, values map[string]any) error {
	if values == nil {
		values = make(map[string]any)
	}

	payload, err := json.MarshalIndent(values, "", "  ")
	if err != nil {
		return &Error{Code: "marshal_json_failed", Path: path, Err: err}
	}

	return writeFile(path, payload)
}

func removeFileIfExists(path string) error {
	if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
		return &Error{Code: "remove_file_failed", Path: path, Err: err}
	}

	return nil
}

func versionString(value any) string {
	switch typed := value.(type) {
	case string:
		return strings.TrimSpace(typed)
	case json.Number:
		return strings.TrimSpace(typed.String())
	case float64:
		if typed == float64(int64(typed)) {
			return strconv.FormatInt(int64(typed), 10)
		}
		return strconv.FormatFloat(typed, 'f', -1, 64)
	case float32:
		if typed == float32(int32(typed)) {
			return strconv.FormatInt(int64(typed), 10)
		}
		return strconv.FormatFloat(float64(typed), 'f', -1, 32)
	case int:
		return strconv.Itoa(typed)
	case int32:
		return strconv.FormatInt(int64(typed), 10)
	case int64:
		return strconv.FormatInt(typed, 10)
	case uint:
		return strconv.FormatUint(uint64(typed), 10)
	case uint32:
		return strconv.FormatUint(uint64(typed), 10)
	case uint64:
		return strconv.FormatUint(typed, 10)
	default:
		return ""
	}
}

func openSQLiteForMigration(dbPath string) (*sql.DB, error) {
	if strings.TrimSpace(dbPath) == "" {
		return nil, &Error{Code: "invalid_db_path"}
	}

	parentDir := filepath.Dir(dbPath)
	if err := os.MkdirAll(parentDir, 0o755); err != nil {
		return nil, &Error{Code: "create_db_dir_failed", Path: parentDir, Err: err}
	}

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, &Error{Code: "open_db_failed", Path: dbPath, Err: err}
	}

	db.SetMaxOpenConns(1)
	_, _ = db.Exec("PRAGMA journal_mode=WAL")
	_, _ = db.Exec("PRAGMA busy_timeout=5000")
	_, _ = db.Exec("PRAGMA foreign_keys=ON")

	if err := db.Ping(); err != nil {
		_ = db.Close()
		return nil, &Error{Code: "ping_db_failed", Path: dbPath, Err: err}
	}

	return db, nil
}

func openSQLiteIfExists(dbPath string) (*sql.DB, bool, error) {
	if strings.TrimSpace(dbPath) == "" {
		return nil, false, &Error{Code: "invalid_db_path"}
	}

	_, err := os.Stat(dbPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, false, nil
		}

		return nil, false, &Error{Code: "stat_db_failed", Path: dbPath, Err: err}
	}

	db, err := openSQLiteForMigration(dbPath)
	if err != nil {
		return nil, false, err
	}

	return db, true, nil
}

func sqliteTableExists(db *sql.DB, tableName string) (bool, error) {
	if db == nil {
		return false, &Error{Code: "nil_db", Path: tableName}
	}

	var count int
	if err := db.QueryRow(`SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?`, tableName).Scan(&count); err != nil {
		return false, &Error{Code: "read_schema_failed", Path: tableName, Err: err}
	}

	return count > 0, nil
}
