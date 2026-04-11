package migration

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestEngine_Register(t *testing.T) {
	registry := NewRegistry("")
	engine := NewEngine("test", registry, Context{RepoRoot: "/tmp/test"})

	tests := []struct {
		name      string
		migration Migration
		wantErr   bool
		errCode   string
	}{
		{
			name: "valid migration",
			migration: Migration{
				Version: 1,
				Name:    "test_migration",
				Up:      func(*Context) error { return nil },
				Down:    func(*Context) error { return nil },
			},
			wantErr: false,
		},
		{
			name: "invalid version - zero",
			migration: Migration{
				Version: 0,
				Name:    "invalid",
				Up:      func(*Context) error { return nil },
				Down:    func(*Context) error { return nil },
			},
			wantErr: true,
			errCode: "invalid_migration_version",
		},
		{
			name: "invalid version - negative",
			migration: Migration{
				Version: -1,
				Name:    "invalid",
				Up:      func(*Context) error { return nil },
				Down:    func(*Context) error { return nil },
			},
			wantErr: true,
			errCode: "invalid_migration_version",
		},
		{
			name: "missing name",
			migration: Migration{
				Version: 1,
				Name:    "",
				Up:      func(*Context) error { return nil },
				Down:    func(*Context) error { return nil },
			},
			wantErr: true,
			errCode: "invalid_migration_name",
		},
		{
			name: "missing up migration",
			migration: Migration{
				Version: 1,
				Name:    "no_up",
				Up:      nil,
				Down:    func(*Context) error { return nil },
			},
			wantErr: true,
			errCode: "missing_up_migration",
		},
		{
			name: "missing down migration",
			migration: Migration{
				Version: 1,
				Name:    "no_down",
				Up:      func(*Context) error { return nil },
				Down:    nil,
			},
			wantErr: true,
			errCode: "missing_down_migration",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := engine.Register(tt.migration)
			if tt.wantErr {
				if err == nil {
					t.Fatalf("expected error, got nil")
				}
				migrationErr, ok := err.(*Error)
				if !ok {
					t.Fatalf("expected *Error, got %T", err)
				}
				if migrationErr.Code != tt.errCode {
					t.Errorf("expected error code %q, got %q", tt.errCode, migrationErr.Code)
				}
			} else {
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
			}
		})
	}
}

func TestEngine_Register_DuplicateVersion(t *testing.T) {
	registry := NewRegistry("")
	engine := NewEngine("test", registry, Context{RepoRoot: "/tmp/test"})

	migration1 := Migration{
		Version: 1,
		Name:    "first_migration",
		Up:      func(*Context) error { return nil },
		Down:    func(*Context) error { return nil },
	}
	migration2 := Migration{
		Version: 1,
		Name:    "second_migration",
		Up:      func(*Context) error { return nil },
		Down:    func(*Context) error { return nil },
	}

	if err := engine.Register(migration1); err != nil {
		t.Fatalf("failed to register first migration: %v", err)
	}
	err := engine.Register(migration2)
	if err == nil {
		t.Fatal("expected error for duplicate version, got nil")
	}
	migrationErr, ok := err.(*Error)
	if !ok {
		t.Fatalf("expected *Error, got %T", err)
	}
	if migrationErr.Code != "duplicate_migration_version" {
		t.Errorf("expected error code 'duplicate_migration_version', got %q", migrationErr.Code)
	}
}

func TestEngine_MigrateUp(t *testing.T) {
	tmpDir := t.TempDir()
	statePath := filepath.Join(tmpDir, "migrations.json")
	registry := NewRegistry(statePath)
	engine := NewEngine("test", registry, Context{RepoRoot: tmpDir})

	upCalls := []int{}

	migrations := []Migration{
		{
			Version: 1,
			Name:    "migration_1",
			Up: func(ctx *Context) error {
				upCalls = append(upCalls, 1)
				return nil
			},
			Down: func(*Context) error { return nil },
		},
		{
			Version: 2,
			Name:    "migration_2",
			Up: func(ctx *Context) error {
				upCalls = append(upCalls, 2)
				return nil
			},
			Down: func(*Context) error { return nil },
		},
		{
			Version: 3,
			Name:    "migration_3",
			Up: func(ctx *Context) error {
				upCalls = append(upCalls, 3)
				return nil
			},
			Down: func(*Context) error { return nil },
		},
	}

	for _, m := range migrations {
		if err := engine.Register(m); err != nil {
			t.Fatalf("failed to register migration: %v", err)
		}
	}

	t.Run("migrate to specific version", func(t *testing.T) {
		upCalls = nil
		if err := engine.MigrateUp(2); err != nil {
			t.Fatalf("migrate up failed: %v", err)
		}
		if len(upCalls) != 2 || upCalls[0] != 1 || upCalls[1] != 2 {
			t.Errorf("expected upCalls [1, 2], got %v", upCalls)
		}

		version, err := engine.GetCurrentVersion()
		if err != nil {
			t.Fatalf("get current version failed: %v", err)
		}
		if version != 2 {
			t.Errorf("expected version 2, got %d", version)
		}
	})

	t.Run("migrate to latest", func(t *testing.T) {
		upCalls = nil
		if err := engine.MigrateUp(0); err != nil {
			t.Fatalf("migrate up failed: %v", err)
		}
		if len(upCalls) != 1 || upCalls[0] != 3 {
			t.Errorf("expected upCalls [3], got %v", upCalls)
		}

		version, err := engine.GetCurrentVersion()
		if err != nil {
			t.Fatalf("get current version failed: %v", err)
		}
		if version != 3 {
			t.Errorf("expected version 3, got %d", version)
		}
	})

	t.Run("migrate already applied", func(t *testing.T) {
		upCalls = nil
		if err := engine.MigrateUp(3); err != nil {
			t.Fatalf("migrate up failed: %v", err)
		}
		if len(upCalls) != 0 {
			t.Errorf("expected no up calls, got %v", upCalls)
		}
	})

	t.Run("invalid target version", func(t *testing.T) {
		err := engine.MigrateUp(1)
		if err == nil {
			t.Fatal("expected error for invalid target, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "invalid_target_version" {
			t.Errorf("expected error code 'invalid_target_version', got %q", migrationErr.Code)
		}
	})

	t.Run("unknown target version", func(t *testing.T) {
		err := engine.MigrateUp(99)
		if err == nil {
			t.Fatal("expected error for unknown target, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "unknown_target_version" {
			t.Errorf("expected error code 'unknown_target_version', got %q", migrationErr.Code)
		}
	})
}

func TestEngine_MigrateDown(t *testing.T) {
	tmpDir := t.TempDir()
	statePath := filepath.Join(tmpDir, "migrations.json")
	registry := NewRegistry(statePath)
	engine := NewEngine("test", registry, Context{RepoRoot: tmpDir})

	downCalls := []int{}

	migrations := []Migration{
		{
			Version: 1,
			Name:    "migration_1",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { downCalls = append(downCalls, 1); return nil },
		},
		{
			Version: 2,
			Name:    "migration_2",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { downCalls = append(downCalls, 2); return nil },
		},
		{
			Version: 3,
			Name:    "migration_3",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { downCalls = append(downCalls, 3); return nil },
		},
	}

	for _, m := range migrations {
		if err := engine.Register(m); err != nil {
			t.Fatalf("failed to register migration: %v", err)
		}
	}

	// Apply all migrations first
	if err := engine.MigrateUp(3); err != nil {
		t.Fatalf("migrate up failed: %v", err)
	}

	t.Run("rollback to version", func(t *testing.T) {
		downCalls = nil
		if err := engine.MigrateDown(1); err != nil {
			t.Fatalf("migrate down failed: %v", err)
		}
		if len(downCalls) != 2 || downCalls[0] != 3 || downCalls[1] != 2 {
			t.Errorf("expected downCalls [3, 2], got %v", downCalls)
		}

		version, err := engine.GetCurrentVersion()
		if err != nil {
			t.Fatalf("get current version failed: %v", err)
		}
		if version != 1 {
			t.Errorf("expected version 1, got %d", version)
		}
	})

	t.Run("invalid rollback target - negative", func(t *testing.T) {
		err := engine.MigrateDown(-1)
		if err == nil {
			t.Fatal("expected error for negative target, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "invalid_rollback_target" {
			t.Errorf("expected error code 'invalid_rollback_target', got %q", migrationErr.Code)
		}
	})

	t.Run("invalid rollback target - higher than current", func(t *testing.T) {
		err := engine.MigrateDown(2)
		if err == nil {
			t.Fatal("expected error for higher target, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "invalid_rollback_target" {
			t.Errorf("expected error code 'invalid_rollback_target', got %q", migrationErr.Code)
		}
	})

	t.Run("rollback to zero", func(t *testing.T) {
		downCalls = nil
		if err := engine.MigrateDown(0); err != nil {
			t.Fatalf("migrate down failed: %v", err)
		}
		if len(downCalls) != 1 || downCalls[0] != 1 {
			t.Errorf("expected downCalls [1], got %v", downCalls)
		}

		version, err := engine.GetCurrentVersion()
		if err != nil {
			t.Fatalf("get current version failed: %v", err)
		}
		if version != 0 {
			t.Errorf("expected version 0, got %d", version)
		}
	})
}

func TestEngine_Validate(t *testing.T) {
	t.Run("valid engine", func(t *testing.T) {
		registry := NewRegistry("")
		engine := NewEngine("test", registry, Context{RepoRoot: "/tmp/test"})
		if err := engine.Register(Migration{
			Version: 1,
			Name:    "test",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { return nil },
		}); err != nil {
			t.Fatalf("failed to register migration: %v", err)
		}
		if err := engine.Validate(); err != nil {
			t.Errorf("validate failed: %v", err)
		}
	})

	t.Run("no migrations registered", func(t *testing.T) {
		registry := NewRegistry("")
		engine := NewEngine("test", registry, Context{RepoRoot: "/tmp/test"})
		err := engine.Validate()
		if err == nil {
			t.Fatal("expected error for no migrations, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "no_migrations_registered" {
			t.Errorf("expected error code 'no_migrations_registered', got %q", migrationErr.Code)
		}
	})

	t.Run("non-contiguous versions", func(t *testing.T) {
		registry := NewRegistry("")
		engine := NewEngine("test", registry, Context{RepoRoot: "/tmp/test"})
		if err := engine.Register(Migration{
			Version: 1,
			Name:    "test1",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { return nil },
		}); err != nil {
			t.Fatalf("failed to register migration: %v", err)
		}
		if err := engine.Register(Migration{
			Version: 3,
			Name:    "test3",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { return nil },
		}); err != nil {
			t.Fatalf("failed to register migration: %v", err)
		}
		err := engine.Validate()
		if err == nil {
			t.Fatal("expected error for non-contiguous versions, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "non_contiguous_migration_versions" {
			t.Errorf("expected error code 'non_contiguous_migration_versions', got %q", migrationErr.Code)
		}
	})
}

func TestEngine_CheckRollbackSafety(t *testing.T) {
	tmpDir := t.TempDir()
	statePath := filepath.Join(tmpDir, "migrations.json")
	registry := NewRegistry(statePath)
	engine := NewEngine("test", registry, Context{RepoRoot: tmpDir})

	// Migration with rollback check
	checkCalled := false
	migrations := []Migration{
		{
			Version: 1,
			Name:    "migration_1",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { return nil },
			RollbackCheck: func(*Context) error {
				checkCalled = true
				return nil
			},
		},
		{
			Version: 2,
			Name:    "migration_2",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { return nil },
		},
	}

	for _, m := range migrations {
		if err := engine.Register(m); err != nil {
			t.Fatalf("failed to register migration: %v", err)
		}
	}

	if err := engine.MigrateUp(2); err != nil {
		t.Fatalf("migrate up failed: %v", err)
	}

	t.Run("check passes", func(t *testing.T) {
		checkCalled = false
		if err := engine.CheckRollbackSafety(0); err != nil {
			t.Errorf("check rollback safety failed: %v", err)
		}
		if !checkCalled {
			t.Error("expected RollbackCheck to be called")
		}
	})

	t.Run("target version too high", func(t *testing.T) {
		err := engine.CheckRollbackSafety(3)
		if err == nil {
			t.Fatal("expected error for target too high, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "invalid_rollback_target" {
			t.Errorf("expected error code 'invalid_rollback_target', got %q", migrationErr.Code)
		}
	})

	t.Run("target version negative", func(t *testing.T) {
		err := engine.CheckRollbackSafety(-1)
		if err == nil {
			t.Fatal("expected error for negative target, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "invalid_rollback_target" {
			t.Errorf("expected error code 'invalid_rollback_target', got %q", migrationErr.Code)
		}
	})
}

func TestEngine_RollbackSteps(t *testing.T) {
	tmpDir := t.TempDir()
	statePath := filepath.Join(tmpDir, "migrations.json")
	registry := NewRegistry(statePath)
	engine := NewEngine("test", registry, Context{RepoRoot: tmpDir})

	downCalls := []int{}
	migrations := []Migration{
		{
			Version: 1,
			Name:    "migration_1",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { downCalls = append(downCalls, 1); return nil },
		},
		{
			Version: 2,
			Name:    "migration_2",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { downCalls = append(downCalls, 2); return nil },
		},
		{
			Version: 3,
			Name:    "migration_3",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { downCalls = append(downCalls, 3); return nil },
		},
	}

	for _, m := range migrations {
		if err := engine.Register(m); err != nil {
			t.Fatalf("failed to register migration: %v", err)
		}
	}

	if err := engine.MigrateUp(0); err != nil {
		t.Fatalf("migrate up failed: %v", err)
	}

	t.Run("rollback one step", func(t *testing.T) {
		downCalls = nil
		if err := engine.RollbackSteps(1); err != nil {
			t.Fatalf("rollback steps failed: %v", err)
		}
		if len(downCalls) != 1 || downCalls[0] != 3 {
			t.Errorf("expected downCalls [3], got %v", downCalls)
		}

		version, err := engine.GetCurrentVersion()
		if err != nil {
			t.Fatalf("get current version failed: %v", err)
		}
		if version != 2 {
			t.Errorf("expected version 2, got %d", version)
		}
	})

	t.Run("rollback multiple steps", func(t *testing.T) {
		if err := engine.MigrateUp(0); err != nil {
			t.Fatalf("migrate up failed: %v", err)
		}
		downCalls = nil
		if err := engine.RollbackSteps(2); err != nil {
			t.Fatalf("rollback steps failed: %v", err)
		}
		if len(downCalls) != 2 || downCalls[0] != 3 || downCalls[1] != 2 {
			t.Errorf("expected downCalls [3, 2], got %v", downCalls)
		}

		version, err := engine.GetCurrentVersion()
		if err != nil {
			t.Fatalf("get current version failed: %v", err)
		}
		if version != 1 {
			t.Errorf("expected version 1, got %d", version)
		}
	})

	t.Run("rollback negative steps", func(t *testing.T) {
		err := engine.RollbackSteps(-1)
		if err == nil {
			t.Fatal("expected error for negative steps, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "invalid_rollback_steps" {
			t.Errorf("expected error code 'invalid_rollback_steps', got %q", migrationErr.Code)
		}
	})

	t.Run("rollback too many steps", func(t *testing.T) {
		err := engine.RollbackSteps(5)
		if err == nil {
			t.Fatal("expected error for too many steps, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "invalid_rollback_steps" {
			t.Errorf("expected error code 'invalid_rollback_steps', got %q", migrationErr.Code)
		}
	})
}

func TestContext_Clone(t *testing.T) {
	ctx := Context{
		RepoRoot:    "/tmp/repo",
		ConfigPath:  "/tmp/config",
		FromVersion: 1,
		ToVersion:   2,
		Metadata:    map[string]string{"key": "value"},
	}

	cloned := ctx.clone()
	if cloned.RepoRoot != ctx.RepoRoot {
		t.Errorf("expected RepoRoot %q, got %q", ctx.RepoRoot, cloned.RepoRoot)
	}
	if cloned.ConfigPath != ctx.ConfigPath {
		t.Errorf("expected ConfigPath %q, got %q", ctx.ConfigPath, cloned.ConfigPath)
	}
	if cloned.FromVersion != ctx.FromVersion {
		t.Errorf("expected FromVersion %d, got %d", ctx.FromVersion, cloned.FromVersion)
	}
	if cloned.ToVersion != ctx.ToVersion {
		t.Errorf("expected ToVersion %d, got %d", ctx.ToVersion, cloned.ToVersion)
	}
	if cloned.Metadata["key"] != "value" {
		t.Errorf("expected Metadata[key] = 'value', got %q", cloned.Metadata["key"])
	}

	// Verify metadata is a copy
	cloned.Metadata["key"] = "modified"
	if ctx.Metadata["key"] != "value" {
		t.Error("original Metadata should not be modified")
	}
}

func TestNormalizeSchemaName(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"config", "config"},
		{"CONFIG", "config"},
		{"  Config  ", "config"},
		{"", ""},
		{"   ", ""},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			result := normalizeSchemaName(tt.input)
			if result != tt.expected {
				t.Errorf("normalizeSchemaName(%q) = %q, want %q", tt.input, result, tt.expected)
			}
		})
	}
}

func TestVersionPath(t *testing.T) {
	tests := []struct {
		schema   string
		version  int
		expected string
	}{
		{"config", 1, "config:1"},
		{"", 1, "1"},
		{"  Config  ", 5, "config:5"},
	}

	for _, tt := range tests {
		t.Run(tt.expected, func(t *testing.T) {
			result := versionPath(tt.schema, tt.version)
			if result != tt.expected {
				t.Errorf("versionPath(%q, %d) = %q, want %q", tt.schema, tt.version, result, tt.expected)
			}
		})
	}
}

func TestMigrationError(t *testing.T) {
	t.Run("nil error", func(t *testing.T) {
		var e *Error
		if e.Error() != "" {
			t.Errorf("expected empty string, got %q", e.Error())
		}
	})

	t.Run("code only", func(t *testing.T) {
		e := &Error{Code: "test_error"}
		if e.Error() != "test_error" {
			t.Errorf("expected 'test_error', got %q", e.Error())
		}
	})

	t.Run("with path", func(t *testing.T) {
		e := &Error{Code: "test_error", Path: "config:1"}
		expected := "test_error: config:1"
		if e.Error() != expected {
			t.Errorf("expected %q, got %q", expected, e.Error())
		}
	})

	t.Run("with error", func(t *testing.T) {
		innerErr := errors.New("inner error")
		e := &Error{Code: "test_error", Err: innerErr}
		expected := "test_error: inner error"
		if e.Error() != expected {
			t.Errorf("expected %q, got %q", expected, e.Error())
		}
	})

	t.Run("full error", func(t *testing.T) {
		innerErr := errors.New("inner error")
		e := &Error{Code: "test_error", Path: "config:1", Err: innerErr}
		expected := "test_error: config:1: inner error"
		if e.Error() != expected {
			t.Errorf("expected %q, got %q", expected, e.Error())
		}
	})

	t.Run("unwrap", func(t *testing.T) {
		innerErr := errors.New("inner error")
		e := &Error{Code: "test_error", Err: innerErr}
		if e.Unwrap() != innerErr {
			t.Error("expected Unwrap to return inner error")
		}
	})

	t.Run("unwrap nil", func(t *testing.T) {
		var e *Error
		if e.Unwrap() != nil {
			t.Error("expected Unwrap to return nil")
		}
	})
}

func TestEngine_NilReceiver(t *testing.T) {
	var engine *Engine

	t.Run("register", func(t *testing.T) {
		err := engine.Register(Migration{})
		if err == nil {
			t.Fatal("expected error for nil engine, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "nil_engine" {
			t.Errorf("expected error code 'nil_engine', got %q", migrationErr.Code)
		}
	})

	t.Run("get current version", func(t *testing.T) {
		_, err := engine.GetCurrentVersion()
		if err == nil {
			t.Fatal("expected error for nil engine, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "nil_engine" {
			t.Errorf("expected error code 'nil_engine', got %q", migrationErr.Code)
		}
	})

	t.Run("validate", func(t *testing.T) {
		err := engine.Validate()
		if err == nil {
			t.Fatal("expected error for nil engine, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "nil_engine" {
			t.Errorf("expected error code 'nil_engine', got %q", migrationErr.Code)
		}
	})
}

func TestMigrationUp_Failure(t *testing.T) {
	tmpDir := t.TempDir()
	statePath := filepath.Join(tmpDir, "migrations.json")
	registry := NewRegistry(statePath)
	engine := NewEngine("test", registry, Context{RepoRoot: tmpDir})

	migrations := []Migration{
		{
			Version: 1,
			Name:    "migration_1",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { return nil },
		},
		{
			Version: 2,
			Name:    "migration_2",
			Up:      func(*Context) error { return errors.New("up failed") },
			Down:    func(*Context) error { return nil },
		},
	}

	for _, m := range migrations {
		if err := engine.Register(m); err != nil {
			t.Fatalf("failed to register migration: %v", err)
		}
	}

	err := engine.MigrateUp(0)
	if err == nil {
		t.Fatal("expected error for failed migration, got nil")
	}
	migrationErr, ok := err.(*Error)
	if !ok {
		t.Fatalf("expected *Error, got %T", err)
	}
	if migrationErr.Code != "apply_migration_failed" {
		t.Errorf("expected error code 'apply_migration_failed', got %q", migrationErr.Code)
	}

	// Should have applied version 1 but not 2
	version, err := engine.GetCurrentVersion()
	if err != nil {
		t.Fatalf("get current version failed: %v", err)
	}
	if version != 1 {
		t.Errorf("expected version 1, got %d", version)
	}
}

func TestMigrationDown_Failure(t *testing.T) {
	tmpDir := t.TempDir()
	statePath := filepath.Join(tmpDir, "migrations.json")
	registry := NewRegistry(statePath)
	engine := NewEngine("test", registry, Context{RepoRoot: tmpDir})

	migrations := []Migration{
		{
			Version: 1,
			Name:    "migration_1",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { return nil },
		},
		{
			Version: 2,
			Name:    "migration_2",
			Up:      func(*Context) error { return nil },
			Down:    func(*Context) error { return errors.New("down failed") },
		},
	}

	for _, m := range migrations {
		if err := engine.Register(m); err != nil {
			t.Fatalf("failed to register migration: %v", err)
		}
	}

	if err := engine.MigrateUp(0); err != nil {
		t.Fatalf("migrate up failed: %v", err)
	}

	err := engine.MigrateDown(0)
	if err == nil {
		t.Fatal("expected error for failed rollback, got nil")
	}
	migrationErr, ok := err.(*Error)
	if !ok {
		t.Fatalf("expected *Error, got %T", err)
	}
	if migrationErr.Code != "rollback_migration_failed" {
		t.Errorf("expected error code 'rollback_migration_failed', got %q", migrationErr.Code)
	}
}

func TestEngine_ContextTransition(t *testing.T) {
	ctx := Context{
		RepoRoot:    "/tmp/repo",
		FromVersion: 0,
		ToVersion:   0,
		Schema:      "",
	}

	transitioned := ctx.transition("config", 1, 2)
	if transitioned.Schema != "config" {
		t.Errorf("expected Schema 'config', got %q", transitioned.Schema)
	}
	if transitioned.FromVersion != 1 {
		t.Errorf("expected FromVersion 1, got %d", transitioned.FromVersion)
	}
	if transitioned.ToVersion != 2 {
		t.Errorf("expected ToVersion 2, got %d", transitioned.ToVersion)
	}
	if transitioned.RepoRoot != "/tmp/repo" {
		t.Error("expected RepoRoot to be preserved")
	}
}

func TestRegistry_Persistence(t *testing.T) {
	tmpDir := t.TempDir()
	statePath := filepath.Join(tmpDir, "migrations.json")

	// Create registry and apply migrations
	registry1 := NewRegistry(statePath)
	engine1 := NewEngine("test", registry1, Context{RepoRoot: tmpDir})

	upCalled := false
	if err := engine1.Register(Migration{
		Version: 1,
		Name:    "test_migration",
		Up:      func(*Context) error { upCalled = true; return nil },
		Down:    func(*Context) error { return nil },
	}); err != nil {
		t.Fatalf("failed to register migration: %v", err)
	}

	if err := engine1.MigrateUp(0); err != nil {
		t.Fatalf("migrate up failed: %v", err)
	}
	if !upCalled {
		t.Error("expected up to be called")
	}

	// Create new registry from same state file
	registry2 := NewRegistry(statePath)
	engine2 := NewEngine("test", registry2, Context{RepoRoot: tmpDir})
	if err := engine2.Register(Migration{
		Version: 1,
		Name:    "test_migration",
		Up:      func(*Context) error { t.Fatal("should not be called"); return nil },
		Down:    func(*Context) error { return nil },
	}); err != nil {
		t.Fatalf("failed to register migration: %v", err)
	}

	// Should not re-apply
	if err := engine2.MigrateUp(0); err != nil {
		t.Fatalf("migrate up failed: %v", err)
	}

	version, err := engine2.GetCurrentVersion()
	if err != nil {
		t.Fatalf("get current version failed: %v", err)
	}
	if version != 1 {
		t.Errorf("expected version 1, got %d", version)
	}
}

func TestRegistry_SaveLoad(t *testing.T) {
	tmpDir := t.TempDir()
	statePath := filepath.Join(tmpDir, "migrations.json")
	registry := NewRegistry(statePath)

	// Modify time for deterministic testing
	fixedTime := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	registry.now = func() time.Time { return fixedTime }

	// Initially no state file
	_, err := os.Stat(statePath)
	if !os.IsNotExist(err) {
		t.Fatal("expected state file to not exist")
	}

	// Save empty state
	if err := registry.Save(); err != nil {
		t.Fatalf("save failed: %v", err)
	}

	// State file should exist
	_, err = os.Stat(statePath)
	if err != nil {
		t.Fatalf("expected state file to exist: %v", err)
	}

	// Load and verify
	if err := registry.Load(); err != nil {
		t.Fatalf("load failed: %v", err)
	}

	// Record an applied migration
	if err := registry.RecordApplied("test", Migration{Version: 1, Name: "test_migration"}); err != nil {
		t.Fatalf("record applied failed: %v", err)
	}

	// Verify state was saved
	data, err := os.ReadFile(statePath)
	if err != nil {
		t.Fatalf("read state file failed: %v", err)
	}
	if !contains(string(data), "test_migration") {
		t.Error("expected state file to contain 'test_migration'")
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsHelper(s, substr))
}

func containsHelper(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

func TestRegistry_Available(t *testing.T) {
	registry := NewRegistry("")

	// Initially empty
	available := registry.Available("test")
	if len(available) != 0 {
		t.Errorf("expected empty available, got %d", len(available))
	}

	// Register migrations
	if err := registry.RegisterAvailable("test", Migration{Version: 2, Name: "migration_2"}); err != nil {
		t.Fatalf("register available failed: %v", err)
	}
	if err := registry.RegisterAvailable("test", Migration{Version: 1, Name: "migration_1"}); err != nil {
		t.Fatalf("register available failed: %v", err)
	}

	// Should be sorted
	available = registry.Available("test")
	if len(available) != 2 {
		t.Fatalf("expected 2 available migrations, got %d", len(available))
	}
	if available[0].Version != 1 {
		t.Errorf("expected version 1 first, got %d", available[0].Version)
	}
	if available[0].Name != "migration_1" {
		t.Errorf("expected name 'migration_1', got %q", available[0].Name)
	}
	if available[1].Version != 2 {
		t.Errorf("expected version 2 second, got %d", available[1].Version)
	}
}

func TestRegistry_DuplicateNameSameVersion(t *testing.T) {
	registry := NewRegistry("")

	// Register same version with same name - should succeed
	if err := registry.RegisterAvailable("test", Migration{Version: 1, Name: "migration_1"}); err != nil {
		t.Fatalf("first register failed: %v", err)
	}
	if err := registry.RegisterAvailable("test", Migration{Version: 1, Name: "migration_1"}); err != nil {
		t.Errorf("second register should be idempotent, got error: %v", err)
	}
}

func TestRegistry_Applied(t *testing.T) {
	tmpDir := t.TempDir()
	statePath := filepath.Join(tmpDir, "migrations.json")
	registry := NewRegistry(statePath)

	// Initially empty
	applied, err := registry.Applied("test")
	if err != nil {
		t.Fatalf("applied failed: %v", err)
	}
	if len(applied) != 0 {
		t.Errorf("expected empty applied, got %d", len(applied))
	}

	// Record applied migrations
	if err := registry.RecordApplied("test", Migration{Version: 1, Name: "migration_1"}); err != nil {
		t.Fatalf("record applied failed: %v", err)
	}
	if err := registry.RecordApplied("test", Migration{Version: 2, Name: "migration_2"}); err != nil {
		t.Fatalf("record applied failed: %v", err)
	}

	applied, err = registry.Applied("test")
	if err != nil {
		t.Fatalf("applied failed: %v", err)
	}
	if len(applied) != 2 {
		t.Fatalf("expected 2 applied migrations, got %d", len(applied))
	}
	if applied[0].Version != 1 {
		t.Errorf("expected version 1 first, got %d", applied[0].Version)
	}
	if applied[1].Version != 2 {
		t.Errorf("expected version 2 second, got %d", applied[1].Version)
	}
}

func TestRegistry_NilReceiver(t *testing.T) {
	var registry *Registry

	t.Run("path", func(t *testing.T) {
		if registry.Path() != "" {
			t.Error("expected empty path for nil registry")
		}
	})

	t.Run("available", func(t *testing.T) {
		if registry.Available("test") != nil {
			t.Error("expected nil available for nil registry")
		}
	})

	t.Run("applied", func(t *testing.T) {
		_, err := registry.Applied("test")
		if err == nil {
			t.Fatal("expected error for nil registry, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "nil_registry" {
			t.Errorf("expected error code 'nil_registry', got %q", migrationErr.Code)
		}
	})

	t.Run("current version", func(t *testing.T) {
		_, err := registry.CurrentVersion("test")
		if err == nil {
			t.Fatal("expected error for nil registry, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "nil_registry" {
			t.Errorf("expected error code 'nil_registry', got %q", migrationErr.Code)
		}
	})
}

func TestRegistry_InvalidSchemaName(t *testing.T) {
	registry := NewRegistry("")

	tests := []struct {
		name   string
		schema string
	}{
		{"empty schema", ""},
		{"whitespace only", "   "},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := registry.RegisterAvailable(tt.schema, Migration{Version: 1, Name: "test"})
			if err == nil {
				t.Fatal("expected error for invalid schema name, got nil")
			}
			migrationErr, ok := err.(*Error)
			if !ok {
				t.Fatalf("expected *Error, got %T", err)
			}
			if migrationErr.Code != "invalid_schema_name" {
				t.Errorf("expected error code 'invalid_schema_name', got %q", migrationErr.Code)
			}
		})
	}
}

func TestRegistry_RecordApplied_InvalidSequence(t *testing.T) {
	tmpDir := t.TempDir()
	statePath := filepath.Join(tmpDir, "migrations.json")
	registry := NewRegistry(statePath)

	// Record version 1
	if err := registry.RecordApplied("test", Migration{Version: 1, Name: "migration_1"}); err != nil {
		t.Fatalf("record applied failed: %v", err)
	}

	// Try to record version 3 (skipping 2)
	err := registry.RecordApplied("test", Migration{Version: 3, Name: "migration_3"})
	if err == nil {
		t.Fatal("expected error for invalid sequence, got nil")
	}
	migrationErr, ok := err.(*Error)
	if !ok {
		t.Fatalf("expected *Error, got %T", err)
	}
	if migrationErr.Code != "invalid_migration_sequence" {
		t.Errorf("expected error code 'invalid_migration_sequence', got %q", migrationErr.Code)
	}

	// Try to record version 1 again (current version is 1, so 1 != 1+1)
	err = registry.RecordApplied("test", Migration{Version: 1, Name: "migration_1"})
	if err == nil {
		t.Fatal("expected error for duplicate, got nil")
	}
	migrationErr, ok = err.(*Error)
	if !ok {
		t.Fatalf("expected *Error, got %T", err)
	}
	// When current version is 1, trying to apply version 1 fails sequence check (1 != 1+1)
	if migrationErr.Code != "invalid_migration_sequence" {
		t.Errorf("expected error code 'invalid_migration_sequence', got %q", migrationErr.Code)
	}
}

func TestRegistry_RecordRolledBack(t *testing.T) {
	tmpDir := t.TempDir()
	statePath := filepath.Join(tmpDir, "migrations.json")
	registry := NewRegistry(statePath)

	// Record applied migrations
	if err := registry.RecordApplied("test", Migration{Version: 1, Name: "migration_1"}); err != nil {
		t.Fatalf("record applied failed: %v", err)
	}
	if err := registry.RecordApplied("test", Migration{Version: 2, Name: "migration_2"}); err != nil {
		t.Fatalf("record applied failed: %v", err)
	}

	t.Run("rollback version 2", func(t *testing.T) {
		if err := registry.RecordRolledBack("test", Migration{Version: 2, Name: "migration_2"}); err != nil {
			t.Fatalf("record rolled back failed: %v", err)
		}

		version, err := registry.CurrentVersion("test")
		if err != nil {
			t.Fatalf("current version failed: %v", err)
		}
		if version != 1 {
			t.Errorf("expected version 1, got %d", version)
		}
	})

	t.Run("rollback wrong version", func(t *testing.T) {
		// Current version is 1, try to rollback version 1 with wrong name
		err := registry.RecordRolledBack("test", Migration{Version: 1, Name: "wrong_name"})
		if err == nil {
			t.Fatal("expected error for wrong name, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "rollback_state_mismatch" {
			t.Errorf("expected error code 'rollback_state_mismatch', got %q", migrationErr.Code)
		}
	})

	t.Run("rollback state mismatch", func(t *testing.T) {
		// Try to rollback version 2 when current is 1
		err := registry.RecordRolledBack("test", Migration{Version: 2, Name: "migration_2"})
		if err == nil {
			t.Fatal("expected error for state mismatch, got nil")
		}
		migrationErr, ok := err.(*Error)
		if !ok {
			t.Fatalf("expected *Error, got %T", err)
		}
		if migrationErr.Code != "rollback_state_mismatch" {
			t.Errorf("expected error code 'rollback_state_mismatch', got %q", migrationErr.Code)
		}
	})
}
