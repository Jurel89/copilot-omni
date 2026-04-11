package migration

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

const registryVersion = 1

type MigrationInfo struct {
	Version int    `json:"version"`
	Name    string `json:"name"`
}

type AppliedMigration struct {
	Version   int       `json:"version"`
	Name      string    `json:"name"`
	AppliedAt time.Time `json:"applied_at"`
}

type SchemaState struct {
	CurrentVersion int                `json:"current_version"`
	Applied        []AppliedMigration `json:"applied,omitempty"`
}

type RegistryState struct {
	Version int                     `json:"version"`
	Schemas map[string]*SchemaState `json:"schemas,omitempty"`
}

type Registry struct {
	statePath string
	now       func() time.Time
	mu        sync.Mutex
	loaded    bool
	available map[string]map[int]MigrationInfo
	state     RegistryState
}

func NewRegistry(statePath string) *Registry {
	return &Registry{
		statePath: strings.TrimSpace(statePath),
		now:       time.Now,
		available: make(map[string]map[int]MigrationInfo),
		state: RegistryState{
			Version: registryVersion,
			Schemas: make(map[string]*SchemaState),
		},
	}
}

func (r *Registry) Path() string {
	if r == nil {
		return ""
	}

	return r.statePath
}

func (r *Registry) RegisterAvailable(schema string, migration Migration) error {
	if r == nil {
		return &Error{Code: "nil_registry", Path: schema}
	}

	schema = normalizeSchemaName(schema)
	if schema == "" {
		return &Error{Code: "invalid_schema_name"}
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	if err := r.loadLocked(); err != nil {
		return err
	}

	if r.available == nil {
		r.available = make(map[string]map[int]MigrationInfo)
	}

	if r.available[schema] == nil {
		r.available[schema] = make(map[int]MigrationInfo)
	}

	info := MigrationInfo{Version: migration.Version, Name: strings.TrimSpace(migration.Name)}
	existing, exists := r.available[schema][migration.Version]
	if exists {
		if strings.TrimSpace(existing.Name) != info.Name {
			return &Error{Code: "duplicate_migration_version", Path: versionPath(schema, migration.Version)}
		}
		return nil
	}

	r.available[schema][migration.Version] = info
	return nil
}

func (r *Registry) Available(schema string) []MigrationInfo {
	if r == nil {
		return nil
	}

	schema = normalizeSchemaName(schema)

	r.mu.Lock()
	defer r.mu.Unlock()

	infos := make([]MigrationInfo, 0, len(r.available[schema]))
	for _, info := range r.available[schema] {
		infos = append(infos, info)
	}

	sort.Slice(infos, func(i, j int) bool {
		return infos[i].Version < infos[j].Version
	})

	return infos
}

func (r *Registry) Applied(schema string) ([]AppliedMigration, error) {
	if r == nil {
		return nil, &Error{Code: "nil_registry", Path: schema}
	}

	schema = normalizeSchemaName(schema)
	if schema == "" {
		return nil, &Error{Code: "invalid_schema_name"}
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	if err := r.loadLocked(); err != nil {
		return nil, err
	}

	return cloneAppliedMigrations(r.schemaStateLocked(schema).Applied), nil
}

func (r *Registry) Load() error {
	if r == nil {
		return &Error{Code: "nil_registry"}
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	return r.loadLocked()
}

func (r *Registry) Save() error {
	if r == nil {
		return &Error{Code: "nil_registry"}
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	return r.saveLocked()
}

func (r *Registry) CurrentVersion(schema string) (int, error) {
	if r == nil {
		return 0, &Error{Code: "nil_registry", Path: schema}
	}

	schema = normalizeSchemaName(schema)
	if schema == "" {
		return 0, &Error{Code: "invalid_schema_name"}
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	if err := r.loadLocked(); err != nil {
		return 0, err
	}

	return r.schemaStateLocked(schema).CurrentVersion, nil
}

func (r *Registry) RecordApplied(schema string, migration Migration) error {
	if r == nil {
		return &Error{Code: "nil_registry", Path: schema}
	}

	schema = normalizeSchemaName(schema)
	if schema == "" {
		return &Error{Code: "invalid_schema_name"}
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	if err := r.loadLocked(); err != nil {
		return err
	}

	state := r.schemaStateLocked(schema)
	if migration.Version != state.CurrentVersion+1 {
		return &Error{Code: "invalid_migration_sequence", Path: versionPath(schema, migration.Version)}
	}

	if len(state.Applied) > 0 {
		lastApplied := state.Applied[len(state.Applied)-1]
		if lastApplied.Version >= migration.Version {
			return &Error{Code: "migration_already_applied", Path: versionPath(schema, migration.Version)}
		}
	}

	state.CurrentVersion = migration.Version
	state.Applied = append(state.Applied, AppliedMigration{
		Version:   migration.Version,
		Name:      strings.TrimSpace(migration.Name),
		AppliedAt: r.now().UTC(),
	})

	return r.saveLocked()
}

func (r *Registry) RecordRolledBack(schema string, migration Migration) error {
	if r == nil {
		return &Error{Code: "nil_registry", Path: schema}
	}

	schema = normalizeSchemaName(schema)
	if schema == "" {
		return &Error{Code: "invalid_schema_name"}
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	if err := r.loadLocked(); err != nil {
		return err
	}

	state := r.schemaStateLocked(schema)
	if state.CurrentVersion != migration.Version {
		return &Error{Code: "rollback_state_mismatch", Path: versionPath(schema, migration.Version)}
	}

	if len(state.Applied) == 0 {
		return &Error{Code: "migration_not_applied", Path: versionPath(schema, migration.Version)}
	}

	lastApplied := state.Applied[len(state.Applied)-1]
	if lastApplied.Version != migration.Version || strings.TrimSpace(lastApplied.Name) != strings.TrimSpace(migration.Name) {
		return &Error{Code: "rollback_state_mismatch", Path: versionPath(schema, migration.Version)}
	}

	state.Applied = append([]AppliedMigration(nil), state.Applied[:len(state.Applied)-1]...)
	state.CurrentVersion = migration.Version - 1

	return r.saveLocked()
}

func (r *Registry) loadLocked() error {
	if r.loaded {
		return nil
	}

	if r.available == nil {
		r.available = make(map[string]map[int]MigrationInfo)
	}

	r.state = RegistryState{
		Version: registryVersion,
		Schemas: make(map[string]*SchemaState),
	}

	if strings.TrimSpace(r.statePath) == "" {
		r.loaded = true
		return nil
	}

	payload, err := os.ReadFile(r.statePath)
	if err != nil {
		if os.IsNotExist(err) {
			r.loaded = true
			return nil
		}

		return &Error{Code: "read_migration_state_failed", Path: r.statePath, Err: err}
	}

	if len(payload) == 0 {
		r.loaded = true
		return nil
	}

	if err := json.Unmarshal(payload, &r.state); err != nil {
		return &Error{Code: "parse_migration_state_failed", Path: r.statePath, Err: err}
	}

	if r.state.Version == 0 {
		r.state.Version = registryVersion
	}

	if r.state.Schemas == nil {
		r.state.Schemas = make(map[string]*SchemaState)
	}

	for schema, state := range r.state.Schemas {
		normalizedSchema := normalizeSchemaName(schema)
		if normalizedSchema == "" {
			delete(r.state.Schemas, schema)
			continue
		}

		if state == nil {
			state = &SchemaState{}
		}

		if state.CurrentVersion < 0 {
			return &Error{Code: "invalid_current_version", Path: normalizedSchema}
		}

		state.Applied = cloneAppliedMigrations(state.Applied)
		r.state.Schemas[normalizedSchema] = state
		if normalizedSchema != schema {
			delete(r.state.Schemas, schema)
		}
	}

	r.loaded = true
	return nil
}

func (r *Registry) saveLocked() error {
	if err := r.loadLocked(); err != nil {
		return err
	}

	if strings.TrimSpace(r.statePath) == "" {
		return nil
	}

	r.state.Version = registryVersion
	if r.state.Schemas == nil {
		r.state.Schemas = make(map[string]*SchemaState)
	}

	payload, err := json.MarshalIndent(r.state, "", "  ")
	if err != nil {
		return &Error{Code: "marshal_migration_state_failed", Path: r.statePath, Err: err}
	}

	return writeFile(r.statePath, payload)
}

func (r *Registry) schemaStateLocked(schema string) *SchemaState {
	if r.state.Schemas == nil {
		r.state.Schemas = make(map[string]*SchemaState)
	}

	state, exists := r.state.Schemas[schema]
	if exists && state != nil {
		if state.Applied == nil {
			state.Applied = make([]AppliedMigration, 0)
		}
		return state
	}

	state = &SchemaState{Applied: make([]AppliedMigration, 0)}
	r.state.Schemas[schema] = state
	return state
}

func cloneAppliedMigrations(migrations []AppliedMigration) []AppliedMigration {
	if len(migrations) == 0 {
		return nil
	}

	cloned := make([]AppliedMigration, len(migrations))
	copy(cloned, migrations)
	return cloned
}

func writeFile(path string, data []byte) error {
	cleanedPath := filepath.Clean(path)
	if strings.TrimSpace(cleanedPath) == "" || cleanedPath == "." {
		return &Error{Code: "invalid_path", Path: path}
	}

	parentDir := filepath.Dir(cleanedPath)
	if err := os.MkdirAll(parentDir, 0o755); err != nil {
		return &Error{Code: "create_parent_dir_failed", Path: parentDir, Err: err}
	}

	tempFile, err := os.CreateTemp(parentDir, ".copilot-omni-migrations-*")
	if err != nil {
		return &Error{Code: "create_temp_file_failed", Path: cleanedPath, Err: err}
	}

	tempPath := tempFile.Name()
	defer func() {
		_ = os.Remove(tempPath)
	}()

	if err := tempFile.Chmod(0o644); err != nil {
		_ = tempFile.Close()
		return &Error{Code: "chmod_temp_file_failed", Path: tempPath, Err: err}
	}

	if _, err := tempFile.Write(data); err != nil {
		_ = tempFile.Close()
		return &Error{Code: "write_temp_file_failed", Path: tempPath, Err: err}
	}

	if err := tempFile.Sync(); err != nil {
		_ = tempFile.Close()
		return &Error{Code: "sync_temp_file_failed", Path: tempPath, Err: err}
	}

	if err := tempFile.Close(); err != nil {
		return &Error{Code: "close_temp_file_failed", Path: tempPath, Err: err}
	}

	if err := os.Rename(tempPath, cleanedPath); err != nil {
		return &Error{Code: "rename_temp_file_failed", Path: cleanedPath, Err: err}
	}

	return nil
}
