package migration

import (
	"fmt"
	"maps"
	"sort"
	"strconv"
	"strings"
)

type Error struct {
	Code string
	Path string
	Err  error
}

func (e *Error) Error() string {
	if e == nil {
		return ""
	}

	if e.Path != "" && e.Err != nil {
		return fmt.Sprintf("%s: %s: %v", e.Code, e.Path, e.Err)
	}

	if e.Path != "" {
		return fmt.Sprintf("%s: %s", e.Code, e.Path)
	}

	if e.Err != nil {
		return fmt.Sprintf("%s: %v", e.Code, e.Err)
	}

	return e.Code
}

func (e *Error) Unwrap() error {
	if e == nil {
		return nil
	}

	return e.Err
}

type Func func(*Context) error

type RollbackCheck func(*Context) error

type Context struct {
	Schema       string
	RepoRoot     string
	ConfigPath   string
	ArtifactRoot string
	MemoryDBPath string
	StatePath    string
	FromVersion  int
	ToVersion    int
	Metadata     map[string]string
}

func (c Context) clone() Context {
	cloned := c
	if len(c.Metadata) == 0 {
		cloned.Metadata = nil
		return cloned
	}

	cloned.Metadata = make(map[string]string, len(c.Metadata))
	maps.Copy(cloned.Metadata, c.Metadata)

	return cloned
}

func (c Context) transition(schema string, fromVersion, toVersion int) *Context {
	cloned := c.clone()
	cloned.Schema = normalizeSchemaName(schema)
	cloned.FromVersion = fromVersion
	cloned.ToVersion = toVersion
	return &cloned
}

type Migration struct {
	Version       int           `json:"version"`
	Name          string        `json:"name"`
	Up            Func          `json:"-"`
	Down          Func          `json:"-"`
	RollbackCheck RollbackCheck `json:"-"`
}

type Engine struct {
	name       string
	registry   *Registry
	context    Context
	migrations map[int]Migration
}

func NewEngine(name string, registry *Registry, context Context) *Engine {
	normalizedName := normalizeSchemaName(name)
	context.Schema = normalizedName
	if registry != nil && strings.TrimSpace(context.StatePath) == "" {
		context.StatePath = registry.Path()
	}

	return &Engine{
		name:       normalizedName,
		registry:   registry,
		context:    context,
		migrations: make(map[int]Migration),
	}
}

func (e *Engine) Register(migration Migration) error {
	if e == nil {
		return &Error{Code: "nil_engine"}
	}

	if migration.Version <= 0 {
		return &Error{Code: "invalid_migration_version", Path: strconv.Itoa(migration.Version)}
	}

	migration.Name = strings.TrimSpace(migration.Name)
	if migration.Name == "" {
		return &Error{Code: "invalid_migration_name", Path: versionPath(e.name, migration.Version)}
	}

	if migration.Up == nil {
		return &Error{Code: "missing_up_migration", Path: versionPath(e.name, migration.Version)}
	}

	if migration.Down == nil {
		return &Error{Code: "missing_down_migration", Path: versionPath(e.name, migration.Version)}
	}

	if e.migrations == nil {
		e.migrations = make(map[int]Migration)
	}

	if _, exists := e.migrations[migration.Version]; exists {
		return &Error{Code: "duplicate_migration_version", Path: versionPath(e.name, migration.Version)}
	}

	e.migrations[migration.Version] = migration

	if e.registry != nil {
		if err := e.registry.RegisterAvailable(e.name, migration); err != nil {
			return err
		}
	}

	return nil
}

func (e *Engine) MigrateUp(targetVersion int) error {
	if err := e.Validate(); err != nil {
		return err
	}

	currentVersion, err := e.GetCurrentVersion()
	if err != nil {
		return err
	}

	latestVersion := e.latestVersion()
	if targetVersion == 0 {
		targetVersion = latestVersion
	}

	if targetVersion < currentVersion {
		return &Error{Code: "invalid_target_version", Path: strconv.Itoa(targetVersion)}
	}

	if targetVersion > latestVersion {
		return &Error{Code: "unknown_target_version", Path: versionPath(e.name, targetVersion)}
	}

	for version := currentVersion + 1; version <= targetVersion; version++ {
		migration, err := e.getMigration(version)
		if err != nil {
			return err
		}

		if err := migration.Up(e.context.transition(e.name, version-1, version)); err != nil {
			return &Error{Code: "apply_migration_failed", Path: versionPath(e.name, version), Err: err}
		}

		if err := e.registry.RecordApplied(e.name, migration); err != nil {
			return err
		}
	}

	return nil
}

func (e *Engine) MigrateDown(targetVersion int) error {
	if targetVersion < 0 {
		return &Error{Code: "invalid_rollback_target", Path: strconv.Itoa(targetVersion)}
	}

	if err := e.Validate(); err != nil {
		return err
	}

	currentVersion, err := e.GetCurrentVersion()
	if err != nil {
		return err
	}

	if targetVersion > currentVersion {
		return &Error{Code: "invalid_rollback_target", Path: strconv.Itoa(targetVersion)}
	}

	if err := e.CheckRollbackSafety(targetVersion); err != nil {
		return err
	}

	for version := currentVersion; version > targetVersion; version-- {
		migration, err := e.getMigration(version)
		if err != nil {
			return err
		}

		if err := migration.Down(e.context.transition(e.name, version, version-1)); err != nil {
			return &Error{Code: "rollback_migration_failed", Path: versionPath(e.name, version), Err: err}
		}

		if err := e.registry.RecordRolledBack(e.name, migration); err != nil {
			return err
		}
	}

	return nil
}

func (e *Engine) GetCurrentVersion() (int, error) {
	if e == nil {
		return 0, &Error{Code: "nil_engine"}
	}

	if e.registry == nil {
		return 0, &Error{Code: "nil_registry", Path: e.name}
	}

	return e.registry.CurrentVersion(e.name)
}

func (e *Engine) Validate() error {
	if e == nil {
		return &Error{Code: "nil_engine"}
	}

	if e.name == "" {
		return &Error{Code: "invalid_engine_name"}
	}

	if e.registry == nil {
		return &Error{Code: "nil_registry", Path: e.name}
	}

	versions := e.versions()
	if len(versions) == 0 {
		return &Error{Code: "no_migrations_registered", Path: e.name}
	}

	for index, version := range versions {
		migration := e.migrations[version]
		if version <= 0 {
			return &Error{Code: "invalid_migration_version", Path: strconv.Itoa(version)}
		}

		if index == 0 && version != 1 {
			return &Error{Code: "non_contiguous_migration_versions", Path: e.name}
		}

		if index > 0 && version != versions[index-1]+1 {
			return &Error{Code: "non_contiguous_migration_versions", Path: e.name}
		}

		if strings.TrimSpace(migration.Name) == "" {
			return &Error{Code: "invalid_migration_name", Path: versionPath(e.name, version)}
		}

		if migration.Up == nil {
			return &Error{Code: "missing_up_migration", Path: versionPath(e.name, version)}
		}

		if migration.Down == nil {
			return &Error{Code: "missing_down_migration", Path: versionPath(e.name, version)}
		}
	}

	currentVersion, err := e.registry.CurrentVersion(e.name)
	if err != nil {
		return err
	}

	if currentVersion < 0 {
		return &Error{Code: "invalid_current_version", Path: e.name}
	}

	if currentVersion > versions[len(versions)-1] {
		return &Error{Code: "unknown_current_version", Path: versionPath(e.name, currentVersion)}
	}

	applied, err := e.registry.Applied(e.name)
	if err != nil {
		return err
	}

	if len(applied) != currentVersion {
		return &Error{Code: "applied_history_mismatch", Path: e.name}
	}

	for index, appliedMigration := range applied {
		expectedVersion := index + 1
		expectedMigration := e.migrations[expectedVersion]
		if appliedMigration.Version != expectedVersion {
			return &Error{Code: "applied_history_mismatch", Path: versionPath(e.name, appliedMigration.Version)}
		}

		if strings.TrimSpace(appliedMigration.Name) != strings.TrimSpace(expectedMigration.Name) {
			return &Error{Code: "applied_history_mismatch", Path: versionPath(e.name, appliedMigration.Version)}
		}
	}

	return nil
}

func (e *Engine) latestVersion() int {
	versions := e.versions()
	if len(versions) == 0 {
		return 0
	}

	return versions[len(versions)-1]
}

func (e *Engine) versions() []int {
	if e == nil || len(e.migrations) == 0 {
		return nil
	}

	versions := make([]int, 0, len(e.migrations))
	for version := range e.migrations {
		versions = append(versions, version)
	}

	sort.Ints(versions)
	return versions
}

func (e *Engine) getMigration(version int) (Migration, error) {
	if e == nil {
		return Migration{}, &Error{Code: "nil_engine"}
	}

	migration, ok := e.migrations[version]
	if !ok {
		return Migration{}, &Error{Code: "migration_not_registered", Path: versionPath(e.name, version)}
	}

	return migration, nil
}

func normalizeSchemaName(schema string) string {
	return strings.TrimSpace(strings.ToLower(schema))
}

func versionPath(schema string, version int) string {
	normalizedSchema := normalizeSchemaName(schema)
	if normalizedSchema == "" {
		return strconv.Itoa(version)
	}

	return fmt.Sprintf("%s:%d", normalizedSchema, version)
}
