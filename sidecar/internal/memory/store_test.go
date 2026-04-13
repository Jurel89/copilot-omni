package memory

import (
	"database/sql"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"
)

type schemaColumn struct {
	Type         string
	NotNull      bool
	DefaultValue string
	PrimaryKey   bool
}

func TestNewStore(t *testing.T) {
	t.Run("valid path", func(t *testing.T) {
		rootDir := t.TempDir()
		dbPath := filepath.Join(rootDir, "nested", "memory", "memory.db")

		store, err := NewStore(dbPath)
		if err != nil {
			t.Fatalf("NewStore() error = %v", err)
		}
		t.Cleanup(func() {
			if closeErr := store.Close(); closeErr != nil {
				t.Errorf("Close() error = %v", closeErr)
			}
		})

		info, err := os.Stat(dbPath)
		if err != nil {
			t.Fatalf("os.Stat(%q) error = %v", dbPath, err)
		}
		if info.IsDir() {
			t.Fatalf("database path %q is a directory", dbPath)
		}

		if pingErr := store.db.Ping(); pingErr != nil {
			t.Fatalf("store.db.Ping() error = %v", pingErr)
		}
	})

	t.Run("empty path", func(t *testing.T) {
		store, err := NewStore(" \t ")
		if store != nil {
			t.Fatalf("NewStore() store = %#v, want nil", store)
		}

		requireMemoryErrorCode(t, err, "invalid_db_path")
	})

	t.Run("creates expected schema", func(t *testing.T) {
		store := newTestStore(t)

		var tableName string
		err := store.db.QueryRow(`SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memory_records'`).Scan(&tableName)
		if err != nil {
			t.Fatalf("query memory_records table error = %v", err)
		}
		if tableName != "memory_records" {
			t.Fatalf("table name = %q, want %q", tableName, "memory_records")
		}

		rows, err := store.db.Query(`PRAGMA table_info(memory_records)`)
		if err != nil {
			t.Fatalf("PRAGMA table_info error = %v", err)
		}
		defer func() {
			if closeErr := rows.Close(); closeErr != nil {
				t.Errorf("rows.Close() error = %v", closeErr)
			}
		}()

		columns := make(map[string]schemaColumn)
		for rows.Next() {
			var cid int
			var name string
			var columnType string
			var notNull int
			var defaultValue sql.NullString
			var primaryKey int

			if scanErr := rows.Scan(&cid, &name, &columnType, &notNull, &defaultValue, &primaryKey); scanErr != nil {
				t.Fatalf("rows.Scan() error = %v", scanErr)
			}

			columns[name] = schemaColumn{
				Type:         columnType,
				NotNull:      notNull == 1,
				DefaultValue: defaultValue.String,
				PrimaryKey:   primaryKey == 1,
			}
		}
		if err := rows.Err(); err != nil {
			t.Fatalf("rows.Err() error = %v", err)
		}

		expectedColumns := map[string]schemaColumn{
			"id":          {Type: "TEXT", NotNull: false, DefaultValue: "", PrimaryKey: true},
			"type":        {Type: "TEXT", NotNull: true, DefaultValue: "", PrimaryKey: false},
			"source":      {Type: "TEXT", NotNull: true, DefaultValue: "", PrimaryKey: false},
			"scope":       {Type: "TEXT", NotNull: true, DefaultValue: "", PrimaryKey: false},
			"run_id":      {Type: "TEXT", NotNull: true, DefaultValue: "''", PrimaryKey: false},
			"title":       {Type: "TEXT", NotNull: true, DefaultValue: "", PrimaryKey: false},
			"content":     {Type: "TEXT", NotNull: true, DefaultValue: "", PrimaryKey: false},
			"metadata":    {Type: "TEXT", NotNull: true, DefaultValue: "'{}'", PrimaryKey: false},
			"tags":        {Type: "TEXT", NotNull: true, DefaultValue: "''", PrimaryKey: false},
			"trust_level": {Type: "TEXT", NotNull: true, DefaultValue: "'medium'", PrimaryKey: false},
			"sensitivity": {Type: "TEXT", NotNull: true, DefaultValue: "'normal'", PrimaryKey: false},
			"created_at":  {Type: "DATETIME", NotNull: true, DefaultValue: "", PrimaryKey: false},
			"updated_at":  {Type: "DATETIME", NotNull: true, DefaultValue: "", PrimaryKey: false},
		}

		if len(columns) != len(expectedColumns) {
			t.Fatalf("column count = %d, want %d", len(columns), len(expectedColumns))
		}

		for name, want := range expectedColumns {
			got, ok := columns[name]
			if !ok {
				t.Fatalf("missing column %q", name)
			}
			if !strings.EqualFold(got.Type, want.Type) {
				t.Errorf("column %q type = %q, want %q", name, got.Type, want.Type)
			}
			if got.NotNull != want.NotNull {
				t.Errorf("column %q notNull = %v, want %v", name, got.NotNull, want.NotNull)
			}
			if got.DefaultValue != want.DefaultValue {
				t.Errorf("column %q default = %q, want %q", name, got.DefaultValue, want.DefaultValue)
			}
			if got.PrimaryKey != want.PrimaryKey {
				t.Errorf("column %q primaryKey = %v, want %v", name, got.PrimaryKey, want.PrimaryKey)
			}
		}

		indexRows, err := store.db.Query(`SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'memory_records'`)
		if err != nil {
			t.Fatalf("query indexes error = %v", err)
		}
		defer func() {
			if closeErr := indexRows.Close(); closeErr != nil {
				t.Errorf("indexRows.Close() error = %v", closeErr)
			}
		}()

		indexes := make(map[string]bool)
		for indexRows.Next() {
			var indexName string
			if scanErr := indexRows.Scan(&indexName); scanErr != nil {
				t.Fatalf("indexRows.Scan() error = %v", scanErr)
			}
			indexes[indexName] = true
		}
		if err := indexRows.Err(); err != nil {
			t.Fatalf("indexRows.Err() error = %v", err)
		}

		for _, wantIndex := range []string{"idx_memory_type", "idx_memory_scope", "idx_memory_run_id", "idx_memory_created_at"} {
			if !indexes[wantIndex] {
				t.Errorf("missing index %q", wantIndex)
			}
		}
	})
}

func TestStoreCreate(t *testing.T) {
	t.Run("happy path with generated id and defaults", func(t *testing.T) {
		store := newTestStore(t)

		record := &MemoryRecord{
			Title:    "A note",
			Content:  "Useful context",
			Metadata: map[string]string{"kind": "test"},
			Tags:     []string{"alpha", "beta"},
		}

		if err := store.Create(record); err != nil {
			t.Fatalf("Create() error = %v", err)
		}

		if record.ID == "" {
			t.Fatal("Create() did not assign an ID")
		}
		if !strings.HasPrefix(record.ID, "mem-") {
			t.Fatalf("generated ID = %q, want prefix %q", record.ID, "mem-")
		}
		if record.Type != TypeNote {
			t.Fatalf("record.Type = %q, want %q", record.Type, TypeNote)
		}
		if record.Source != SourceUser {
			t.Fatalf("record.Source = %q, want %q", record.Source, SourceUser)
		}
		if record.Scope != ScopeProject {
			t.Fatalf("record.Scope = %q, want %q", record.Scope, ScopeProject)
		}
		if record.TrustLevel != TrustMedium {
			t.Fatalf("record.TrustLevel = %q, want %q", record.TrustLevel, TrustMedium)
		}
		if record.Sensitivity != SensitivityNormal {
			t.Fatalf("record.Sensitivity = %q, want %q", record.Sensitivity, SensitivityNormal)
		}
		if record.CreatedAt.IsZero() {
			t.Fatal("record.CreatedAt was not set")
		}
		if record.UpdatedAt.IsZero() {
			t.Fatal("record.UpdatedAt was not set")
		}

		saved := mustGetRecord(t, store, record.ID)
		if saved.Title != record.Title {
			t.Errorf("saved.Title = %q, want %q", saved.Title, record.Title)
		}
		if saved.Content != record.Content {
			t.Errorf("saved.Content = %q, want %q", saved.Content, record.Content)
		}
		if !reflect.DeepEqual(saved.Metadata, record.Metadata) {
			t.Errorf("saved.Metadata = %#v, want %#v", saved.Metadata, record.Metadata)
		}
		if !reflect.DeepEqual(saved.Tags, record.Tags) {
			t.Errorf("saved.Tags = %#v, want %#v", saved.Tags, record.Tags)
		}
	})

	t.Run("nil record", func(t *testing.T) {
		store := newTestStore(t)
		requireMemoryErrorCode(t, store.Create(nil), "nil_record")
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store
		requireMemoryErrorCode(t, store.Create(validRecord()), "nil_store")
	})

	t.Run("invalid fields", func(t *testing.T) {
		tests := []struct {
			name    string
			mutate  func(*MemoryRecord)
			errCode string
			errPath string
		}{
			{
				name: "invalid type",
				mutate: func(record *MemoryRecord) {
					record.Type = "unknown"
				},
				errCode: "invalid_type",
				errPath: "unknown",
			},
			{
				name: "invalid source",
				mutate: func(record *MemoryRecord) {
					record.Source = "external"
				},
				errCode: "invalid_source",
				errPath: "external",
			},
			{
				name: "invalid scope",
				mutate: func(record *MemoryRecord) {
					record.Scope = "session"
				},
				errCode: "invalid_scope",
				errPath: "session",
			},
		}

		for _, tt := range tests {
			t.Run(tt.name, func(t *testing.T) {
				store := newTestStore(t)
				record := validRecord()
				tt.mutate(record)

				memoryErr := requireMemoryErrorCode(t, store.Create(record), tt.errCode)
				if memoryErr.Path != tt.errPath {
					t.Fatalf("error path = %q, want %q", memoryErr.Path, tt.errPath)
				}
				if got := countRecordsInDB(t, store, "", nil); got != 0 {
					t.Fatalf("record count = %d, want 0", got)
				}
			})
		}
	})
}

func TestStoreGetByID(t *testing.T) {
	t.Run("found", func(t *testing.T) {
		store := newTestStore(t)
		record := validRecord()
		record.Metadata = map[string]string{"owner": "test"}
		record.Tags = []string{"alpha", "beta"}
		mustCreateRecord(t, store, record)

		got, err := store.GetByID(record.ID)
		if err != nil {
			t.Fatalf("GetByID() error = %v", err)
		}
		if got.ID != record.ID {
			t.Fatalf("got.ID = %q, want %q", got.ID, record.ID)
		}
		if !reflect.DeepEqual(got.Metadata, record.Metadata) {
			t.Errorf("got.Metadata = %#v, want %#v", got.Metadata, record.Metadata)
		}
		if !reflect.DeepEqual(got.Tags, record.Tags) {
			t.Errorf("got.Tags = %#v, want %#v", got.Tags, record.Tags)
		}
	})

	t.Run("not found", func(t *testing.T) {
		store := newTestStore(t)
		_, err := store.GetByID("missing-id")
		requireMemoryErrorCode(t, err, "record_not_found")
	})

	t.Run("empty id", func(t *testing.T) {
		store := newTestStore(t)
		_, err := store.GetByID("   ")
		requireMemoryErrorCode(t, err, "invalid_id")
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store
		record, err := store.GetByID("anything")
		if record != nil {
			t.Fatalf("GetByID() record = %#v, want nil", record)
		}
		requireMemoryErrorCode(t, err, "nil_store")
	})
}

func TestStoreDelete(t *testing.T) {
	t.Run("found", func(t *testing.T) {
		store := newTestStore(t)
		record := mustCreateRecord(t, store, validRecord())

		if err := store.Delete(record.ID); err != nil {
			t.Fatalf("Delete() error = %v", err)
		}

		if got := countRecordsInDB(t, store, "", nil); got != 0 {
			t.Fatalf("record count = %d, want 0", got)
		}

		_, err := store.GetByID(record.ID)
		requireMemoryErrorCode(t, err, "record_not_found")
	})

	t.Run("not found", func(t *testing.T) {
		store := newTestStore(t)
		memoryErr := requireMemoryErrorCode(t, store.Delete("missing-id"), "record_not_found")
		if memoryErr.Path != "missing-id" {
			t.Fatalf("error path = %q, want %q", memoryErr.Path, "missing-id")
		}
	})

	t.Run("empty id", func(t *testing.T) {
		store := newTestStore(t)
		requireMemoryErrorCode(t, store.Delete(" \n "), "invalid_id")
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store
		requireMemoryErrorCode(t, store.Delete("any-id"), "nil_store")
	})
}

func TestStoreDeleteByScope(t *testing.T) {
	t.Run("valid scope", func(t *testing.T) {
		store := newTestStore(t)

		projectRecordOne := validRecord()
		projectRecordOne.Title = "project one"
		mustCreateRecord(t, store, projectRecordOne)

		projectRecordTwo := validRecord()
		projectRecordTwo.Title = "project two"
		mustCreateRecord(t, store, projectRecordTwo)

		globalRecord := validRecord()
		globalRecord.Scope = ScopeGlobal
		globalRecord.Title = "global record"
		mustCreateRecord(t, store, globalRecord)

		if err := store.DeleteByScope(ScopeProject); err != nil {
			t.Fatalf("DeleteByScope() error = %v", err)
		}

		if got := countRecordsInDB(t, store, "scope = ?", []any{ScopeProject}); got != 0 {
			t.Fatalf("project record count = %d, want 0", got)
		}
		if got := countRecordsInDB(t, store, "scope = ?", []any{ScopeGlobal}); got != 1 {
			t.Fatalf("global record count = %d, want 1", got)
		}
	})

	t.Run("invalid scope", func(t *testing.T) {
		store := newTestStore(t)
		memoryErr := requireMemoryErrorCode(t, store.DeleteByScope("session"), "invalid_scope")
		if memoryErr.Path != "session" {
			t.Fatalf("error path = %q, want %q", memoryErr.Path, "session")
		}
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store
		requireMemoryErrorCode(t, store.DeleteByScope(ScopeProject), "nil_store")
	})
}

func TestStoreDeleteByRunID(t *testing.T) {
	t.Run("valid run id", func(t *testing.T) {
		store := newTestStore(t)

		runOneNote := validRecord()
		runOneNote.RunID = "run-1"
		runOneNote.Title = "run one note"
		mustCreateRecord(t, store, runOneNote)

		runOnePlan := validRecord()
		runOnePlan.RunID = "run-1"
		runOnePlan.Type = TypePlan
		runOnePlan.Title = "run one plan"
		mustCreateRecord(t, store, runOnePlan)

		runTwoRecord := validRecord()
		runTwoRecord.RunID = "run-2"
		runTwoRecord.Title = "run two record"
		mustCreateRecord(t, store, runTwoRecord)

		noRunRecord := validRecord()
		noRunRecord.Title = "no run record"
		mustCreateRecord(t, store, noRunRecord)

		if err := store.DeleteByRunID("run-1"); err != nil {
			t.Fatalf("DeleteByRunID() error = %v", err)
		}

		if got := countRecordsInDB(t, store, "run_id = ?", []any{"run-1"}); got != 0 {
			t.Fatalf("run-1 record count = %d, want 0", got)
		}
		if got := countRecordsInDB(t, store, "", nil); got != 2 {
			t.Fatalf("total record count = %d, want 2", got)
		}
	})

	t.Run("empty run id", func(t *testing.T) {
		store := newTestStore(t)
		requireMemoryErrorCode(t, store.DeleteByRunID("  "), "invalid_run_id")
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store
		requireMemoryErrorCode(t, store.DeleteByRunID("run-1"), "nil_store")
	})
}

func TestStoreDeleteByAge(t *testing.T) {
	t.Run("deletes old records and keeps recent", func(t *testing.T) {
		store := newTestStore(t)

		oldRecord := validRecord()
		oldRecord.Title = "old"
		oldRecord.CreatedAt = time.Now().UTC().Add(-2 * time.Hour)
		mustCreateRecord(t, store, oldRecord)

		recentRecord := validRecord()
		recentRecord.Title = "recent"
		recentRecord.CreatedAt = time.Now().UTC().Add(-10 * time.Minute)
		mustCreateRecord(t, store, recentRecord)

		deleted, err := store.DeleteByAge(time.Hour)
		if err != nil {
			t.Fatalf("DeleteByAge() error = %v", err)
		}
		if deleted != 1 {
			t.Fatalf("DeleteByAge() deleted = %d, want 1", deleted)
		}

		if got := countRecordsInDB(t, store, "", nil); got != 1 {
			t.Fatalf("remaining record count = %d, want 1", got)
		}

		_, err = store.GetByID(oldRecord.ID)
		requireMemoryErrorCode(t, err, "record_not_found")

		savedRecent := mustGetRecord(t, store, recentRecord.ID)
		if savedRecent.Title != recentRecord.Title {
			t.Fatalf("savedRecent.Title = %q, want %q", savedRecent.Title, recentRecord.Title)
		}
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store
		deleted, err := store.DeleteByAge(time.Hour)
		if deleted != 0 {
			t.Fatalf("DeleteByAge() deleted = %d, want 0", deleted)
		}
		requireMemoryErrorCode(t, err, "nil_store")
	})
}

func TestStoreExport(t *testing.T) {
	t.Run("with scope filter", func(t *testing.T) {
		store := newTestStore(t)

		projectOld := validRecord()
		projectOld.Title = "project old"
		projectOld.CreatedAt = time.Now().UTC().Add(-3 * time.Hour)
		mustCreateRecord(t, store, projectOld)

		globalMiddle := validRecord()
		globalMiddle.Scope = ScopeGlobal
		globalMiddle.Title = "global middle"
		globalMiddle.CreatedAt = time.Now().UTC().Add(-2 * time.Hour)
		mustCreateRecord(t, store, globalMiddle)

		projectNew := validRecord()
		projectNew.Title = "project new"
		projectNew.CreatedAt = time.Now().UTC().Add(-1 * time.Hour)
		projectNew.Metadata = map[string]string{"owner": "qa"}
		projectNew.Tags = []string{"alpha", "beta"}
		mustCreateRecord(t, store, projectNew)

		records, err := store.Export(ScopeProject)
		if err != nil {
			t.Fatalf("Export() error = %v", err)
		}
		if len(records) != 2 {
			t.Fatalf("len(records) = %d, want 2", len(records))
		}
		if records[0].ID != projectNew.ID || records[1].ID != projectOld.ID {
			t.Fatalf("project export order = [%q %q], want [%q %q]", records[0].ID, records[1].ID, projectNew.ID, projectOld.ID)
		}
		if !reflect.DeepEqual(records[0].Metadata, projectNew.Metadata) {
			t.Errorf("records[0].Metadata = %#v, want %#v", records[0].Metadata, projectNew.Metadata)
		}
		if !reflect.DeepEqual(records[0].Tags, projectNew.Tags) {
			t.Errorf("records[0].Tags = %#v, want %#v", records[0].Tags, projectNew.Tags)
		}
	})

	t.Run("without scope", func(t *testing.T) {
		store := newTestStore(t)

		oldest := validRecord()
		oldest.Title = "oldest"
		oldest.CreatedAt = time.Now().UTC().Add(-3 * time.Hour)
		mustCreateRecord(t, store, oldest)

		middle := validRecord()
		middle.Scope = ScopeGlobal
		middle.Title = "middle"
		middle.CreatedAt = time.Now().UTC().Add(-2 * time.Hour)
		mustCreateRecord(t, store, middle)

		newest := validRecord()
		newest.Title = "newest"
		newest.CreatedAt = time.Now().UTC().Add(-1 * time.Hour)
		mustCreateRecord(t, store, newest)

		records, err := store.Export("")
		if err != nil {
			t.Fatalf("Export() error = %v", err)
		}
		if len(records) != 3 {
			t.Fatalf("len(records) = %d, want 3", len(records))
		}
		wantOrder := []string{newest.ID, middle.ID, oldest.ID}
		for index, wantID := range wantOrder {
			if records[index].ID != wantID {
				t.Fatalf("records[%d].ID = %q, want %q", index, records[index].ID, wantID)
			}
		}
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store
		records, err := store.Export("")
		if records != nil {
			t.Fatalf("Export() records = %#v, want nil", records)
		}
		requireMemoryErrorCode(t, err, "nil_store")
	})
}

func TestStoreRecordCount(t *testing.T) {
	t.Run("with and without scope", func(t *testing.T) {
		store := newTestStore(t)

		projectOne := validRecord()
		projectOne.Title = "project one"
		mustCreateRecord(t, store, projectOne)

		projectTwo := validRecord()
		projectTwo.Title = "project two"
		mustCreateRecord(t, store, projectTwo)

		globalRecord := validRecord()
		globalRecord.Scope = ScopeGlobal
		globalRecord.Title = "global"
		mustCreateRecord(t, store, globalRecord)

		projectCount, err := store.RecordCount(ScopeProject)
		if err != nil {
			t.Fatalf("RecordCount(project) error = %v", err)
		}
		if projectCount != 2 {
			t.Fatalf("RecordCount(project) = %d, want 2", projectCount)
		}

		totalCount, err := store.RecordCount("")
		if err != nil {
			t.Fatalf("RecordCount(all) error = %v", err)
		}
		if totalCount != 3 {
			t.Fatalf("RecordCount(all) = %d, want 3", totalCount)
		}
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store
		count, err := store.RecordCount("")
		if count != 0 {
			t.Fatalf("RecordCount() = %d, want 0", count)
		}
		requireMemoryErrorCode(t, err, "nil_store")
	})
}

func TestStoreCreateOrUpdate(t *testing.T) {
	t.Run("insert when no match exists", func(t *testing.T) {
		store := newTestStore(t)

		record := &MemoryRecord{
			RunID:       "run-1",
			Type:        TypePlan,
			Source:      SourceArtifact,
			Scope:       ScopeProject,
			Title:       "Initial plan",
			Content:     "First version",
			Metadata:    map[string]string{"version": "1"},
			Tags:        []string{"plan", "artifact"},
			TrustLevel:  TrustMedium,
			Sensitivity: SensitivityNormal,
		}

		if err := store.CreateOrUpdate(record); err != nil {
			t.Fatalf("CreateOrUpdate() error = %v", err)
		}
		if record.ID == "" {
			t.Fatal("CreateOrUpdate() did not assign an ID")
		}
		if got := countRecordsInDB(t, store, "", nil); got != 1 {
			t.Fatalf("record count = %d, want 1", got)
		}

		saved := mustGetRecord(t, store, record.ID)
		if saved.RunID != record.RunID {
			t.Fatalf("saved.RunID = %q, want %q", saved.RunID, record.RunID)
		}
		if !reflect.DeepEqual(saved.Metadata, record.Metadata) {
			t.Errorf("saved.Metadata = %#v, want %#v", saved.Metadata, record.Metadata)
		}
		if !reflect.DeepEqual(saved.Tags, record.Tags) {
			t.Errorf("saved.Tags = %#v, want %#v", saved.Tags, record.Tags)
		}
	})

	t.Run("update when match exists", func(t *testing.T) {
		store := newTestStore(t)

		existing := &MemoryRecord{
			RunID:       "run-42",
			Type:        TypeDecision,
			Source:      SourceArtifact,
			Scope:       ScopeProject,
			Title:       "Original decision",
			Content:     "Original content",
			Metadata:    map[string]string{"version": "1"},
			Tags:        []string{"decision", "artifact"},
			TrustLevel:  TrustMedium,
			Sensitivity: SensitivityNormal,
			CreatedAt:   time.Now().UTC().Add(-2 * time.Hour),
		}
		mustCreateRecord(t, store, existing)
		originalUpdatedAt := existing.UpdatedAt
		originalCreatedAt := existing.CreatedAt

		time.Sleep(10 * time.Millisecond)

		updated := &MemoryRecord{
			RunID:       existing.RunID,
			Type:        existing.Type,
			Source:      existing.Source,
			Scope:       ScopeGlobal,
			Title:       "Updated decision",
			Content:     "Updated content",
			Metadata:    map[string]string{"version": "2", "status": "final"},
			Tags:        []string{"updated", "decision"},
			TrustLevel:  TrustHigh,
			Sensitivity: SensitivitySensitive,
		}

		if err := store.CreateOrUpdate(updated); err != nil {
			t.Fatalf("CreateOrUpdate() error = %v", err)
		}
		if got := countRecordsInDB(t, store, "", nil); got != 1 {
			t.Fatalf("record count = %d, want 1", got)
		}

		saved := mustGetRecord(t, store, existing.ID)
		if saved.ID != existing.ID {
			t.Fatalf("saved.ID = %q, want %q", saved.ID, existing.ID)
		}
		if !saved.CreatedAt.Equal(originalCreatedAt) {
			t.Fatalf("saved.CreatedAt = %v, want %v", saved.CreatedAt, originalCreatedAt)
		}
		if !saved.UpdatedAt.After(originalUpdatedAt) {
			t.Fatalf("saved.UpdatedAt = %v, want after %v", saved.UpdatedAt, originalUpdatedAt)
		}
		if saved.Scope != updated.Scope {
			t.Errorf("saved.Scope = %q, want %q", saved.Scope, updated.Scope)
		}
		if saved.Title != updated.Title {
			t.Errorf("saved.Title = %q, want %q", saved.Title, updated.Title)
		}
		if saved.Content != updated.Content {
			t.Errorf("saved.Content = %q, want %q", saved.Content, updated.Content)
		}
		if !reflect.DeepEqual(saved.Metadata, updated.Metadata) {
			t.Errorf("saved.Metadata = %#v, want %#v", saved.Metadata, updated.Metadata)
		}
		if !reflect.DeepEqual(saved.Tags, updated.Tags) {
			t.Errorf("saved.Tags = %#v, want %#v", saved.Tags, updated.Tags)
		}
		if saved.TrustLevel != updated.TrustLevel {
			t.Errorf("saved.TrustLevel = %q, want %q", saved.TrustLevel, updated.TrustLevel)
		}
		if saved.Sensitivity != updated.Sensitivity {
			t.Errorf("saved.Sensitivity = %q, want %q", saved.Sensitivity, updated.Sensitivity)
		}
	})

	t.Run("nil record", func(t *testing.T) {
		store := newTestStore(t)
		requireMemoryErrorCode(t, store.CreateOrUpdate(nil), "nil_record")
	})

	t.Run("nil store", func(t *testing.T) {
		var store *Store
		requireMemoryErrorCode(t, store.CreateOrUpdate(validRecord()), "nil_store")
	})
}

func TestStoreClose(t *testing.T) {
	t.Run("nil store", func(t *testing.T) {
		var store *Store
		if err := store.Close(); err != nil {
			t.Fatalf("Close() error = %v, want nil", err)
		}
	})

	t.Run("double close", func(t *testing.T) {
		rootDir := t.TempDir()
		dbPath := filepath.Join(rootDir, "memory.db")
		store, err := NewStore(dbPath)
		if err != nil {
			t.Fatalf("NewStore() error = %v", err)
		}

		if err := store.Close(); err != nil {
			t.Fatalf("first Close() error = %v", err)
		}
		if err := store.Close(); err != nil {
			t.Fatalf("second Close() error = %v", err)
		}
	})
}

func TestDBPath(t *testing.T) {
	repoRoot := t.TempDir()
	absOverride := filepath.Join(t.TempDir(), "memory-override.db")

	tests := []struct {
		name       string
		repoRoot   string
		override   string
		wantDBPath string
	}{
		{
			name:       "with absolute override",
			repoRoot:   repoRoot,
			override:   absOverride,
			wantDBPath: absOverride,
		},
		{
			name:       "without override",
			repoRoot:   repoRoot,
			override:   "",
			wantDBPath: filepath.Join(repoRoot, ".omni", "memory.db"),
		},
		{
			name:       "with relative override",
			repoRoot:   repoRoot,
			override:   filepath.Join("custom", "memory.db"),
			wantDBPath: filepath.Join(repoRoot, "custom", "memory.db"),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := DBPath(tt.repoRoot, tt.override)
			if got != tt.wantDBPath {
				t.Fatalf("DBPath() = %q, want %q", got, tt.wantDBPath)
			}
		})
	}
}

func TestErrorType(t *testing.T) {
	var nilErr *Error
	if got := nilErr.Error(); got != "" {
		t.Fatalf("nil Error(). = %q, want empty string", got)
	}
	if nilErr.Unwrap() != nil {
		t.Fatal("nil Error.Unwrap() != nil")
	}

	inner := errors.New("boom")
	tests := []struct {
		name       string
		err        *Error
		wantText   string
		wantUnwrap error
	}{
		{
			name:       "code only",
			err:        &Error{Code: "invalid_db_path"},
			wantText:   "invalid_db_path",
			wantUnwrap: nil,
		},
		{
			name:       "with path",
			err:        &Error{Code: "open_db_failed", Path: "/tmp/memory.db"},
			wantText:   "open_db_failed: /tmp/memory.db",
			wantUnwrap: nil,
		},
		{
			name:       "with inner error",
			err:        &Error{Code: "open_db_failed", Err: inner},
			wantText:   "open_db_failed: boom",
			wantUnwrap: inner,
		},
		{
			name:       "with path and inner error",
			err:        &Error{Code: "open_db_failed", Path: "/tmp/memory.db", Err: inner},
			wantText:   "open_db_failed: /tmp/memory.db: boom",
			wantUnwrap: inner,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := tt.err.Error(); got != tt.wantText {
				t.Fatalf("Error() = %q, want %q", got, tt.wantText)
			}
			if tt.err.Unwrap() != tt.wantUnwrap {
				t.Fatalf("Unwrap() = %v, want %v", tt.err.Unwrap(), tt.wantUnwrap)
			}
			if tt.wantUnwrap != nil && !errors.Is(tt.err, tt.wantUnwrap) {
				t.Fatalf("errors.Is(%v, %v) = false, want true", tt.err, tt.wantUnwrap)
			}
		})
	}
}

func TestApplyRecordDefaults(t *testing.T) {
	tests := []struct {
		name   string
		record *MemoryRecord
		want   *MemoryRecord
	}{
		{
			name:   "applies missing defaults",
			record: &MemoryRecord{},
			want: &MemoryRecord{
				Type:        TypeNote,
				Source:      SourceUser,
				Scope:       ScopeProject,
				TrustLevel:  TrustMedium,
				Sensitivity: SensitivityNormal,
			},
		},
		{
			name: "preserves existing values",
			record: &MemoryRecord{
				Type:        TypeDecision,
				Source:      SourceArtifact,
				Scope:       ScopeGlobal,
				TrustLevel:  TrustHigh,
				Sensitivity: SensitivitySecret,
			},
			want: &MemoryRecord{
				Type:        TypeDecision,
				Source:      SourceArtifact,
				Scope:       ScopeGlobal,
				TrustLevel:  TrustHigh,
				Sensitivity: SensitivitySecret,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			applyRecordDefaults(tt.record)
			if tt.record.Type != tt.want.Type {
				t.Fatalf("Type = %q, want %q", tt.record.Type, tt.want.Type)
			}
			if tt.record.Source != tt.want.Source {
				t.Fatalf("Source = %q, want %q", tt.record.Source, tt.want.Source)
			}
			if tt.record.Scope != tt.want.Scope {
				t.Fatalf("Scope = %q, want %q", tt.record.Scope, tt.want.Scope)
			}
			if tt.record.TrustLevel != tt.want.TrustLevel {
				t.Fatalf("TrustLevel = %q, want %q", tt.record.TrustLevel, tt.want.TrustLevel)
			}
			if tt.record.Sensitivity != tt.want.Sensitivity {
				t.Fatalf("Sensitivity = %q, want %q", tt.record.Sensitivity, tt.want.Sensitivity)
			}
		})
	}
}

func TestValidateRecord(t *testing.T) {
	tests := []struct {
		name    string
		record  *MemoryRecord
		errCode string
		errPath string
	}{
		{
			name:    "valid record",
			record:  validRecord(),
			errCode: "",
		},
		{
			name: "invalid type",
			record: &MemoryRecord{
				Type:        "invalid",
				Source:      SourceUser,
				Scope:       ScopeProject,
				TrustLevel:  TrustMedium,
				Sensitivity: SensitivityNormal,
			},
			errCode: "invalid_type",
			errPath: "invalid",
		},
		{
			name: "invalid source",
			record: &MemoryRecord{
				Type:        TypeNote,
				Source:      "invalid",
				Scope:       ScopeProject,
				TrustLevel:  TrustMedium,
				Sensitivity: SensitivityNormal,
			},
			errCode: "invalid_source",
			errPath: "invalid",
		},
		{
			name: "invalid scope",
			record: &MemoryRecord{
				Type:        TypeNote,
				Source:      SourceUser,
				Scope:       "invalid",
				TrustLevel:  TrustMedium,
				Sensitivity: SensitivityNormal,
			},
			errCode: "invalid_scope",
			errPath: "invalid",
		},
		{
			name: "invalid trust level",
			record: &MemoryRecord{
				Type:        TypeNote,
				Source:      SourceUser,
				Scope:       ScopeProject,
				TrustLevel:  "invalid",
				Sensitivity: SensitivityNormal,
			},
			errCode: "invalid_trust_level",
			errPath: "invalid",
		},
		{
			name: "invalid sensitivity",
			record: &MemoryRecord{
				Type:        TypeNote,
				Source:      SourceUser,
				Scope:       ScopeProject,
				TrustLevel:  TrustMedium,
				Sensitivity: "invalid",
			},
			errCode: "invalid_sensitivity",
			errPath: "invalid",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateRecord(tt.record)
			if tt.errCode == "" {
				if err != nil {
					t.Fatalf("validateRecord() error = %v, want nil", err)
				}
				return
			}

			memoryErr := requireMemoryErrorCode(t, err, tt.errCode)
			if memoryErr.Path != tt.errPath {
				t.Fatalf("error path = %q, want %q", memoryErr.Path, tt.errPath)
			}
		})
	}
}

func TestTagsToString(t *testing.T) {
	tests := []struct {
		name string
		tags []string
		want string
	}{
		{name: "nil", tags: nil, want: ""},
		{name: "empty", tags: []string{}, want: ""},
		{name: "values", tags: []string{"alpha", "beta"}, want: ",alpha,beta,"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := tagsToString(tt.tags); got != tt.want {
				t.Fatalf("tagsToString() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestStringToTags(t *testing.T) {
	tests := []struct {
		name string
		text string
		want []string
	}{
		{name: "blank", text: "   ", want: nil},
		{name: "comma wrapped", text: ",alpha,beta,", want: []string{"alpha", "beta"}},
		{name: "trims whitespace and empties", text: " alpha, , beta ,, ", want: []string{"alpha", "beta"}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := stringToTags(tt.text)
			if !reflect.DeepEqual(got, tt.want) {
				t.Fatalf("stringToTags() = %#v, want %#v", got, tt.want)
			}
		})
	}
}

func TestNormalizeTags(t *testing.T) {
	tests := []struct {
		name string
		tags []string
		want []string
	}{
		{name: "nil", tags: nil, want: nil},
		{name: "all empty", tags: []string{" ", ""}, want: nil},
		{name: "normalizes and deduplicates", tags: []string{" Alpha ", "beta", "ALPHA", "", " beta "}, want: []string{"alpha", "beta"}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := normalizeTags(tt.tags)
			if !reflect.DeepEqual(got, tt.want) {
				t.Fatalf("normalizeTags() = %#v, want %#v", got, tt.want)
			}
		})
	}
}

func TestCloneTags(t *testing.T) {
	if got := cloneTags(nil); got != nil {
		t.Fatalf("cloneTags(nil) = %#v, want nil", got)
	}
	if got := cloneTags([]string{}); got != nil {
		t.Fatalf("cloneTags(empty) = %#v, want nil", got)
	}

	original := []string{"alpha", "beta"}
	cloned := cloneTags(original)
	if !reflect.DeepEqual(cloned, original) {
		t.Fatalf("cloneTags() = %#v, want %#v", cloned, original)
	}
	cloned[0] = "changed"
	if original[0] != "alpha" {
		t.Fatalf("original tags mutated = %#v", original)
	}
}

func TestCloneMetadata(t *testing.T) {
	if got := cloneMetadata(nil); got != nil {
		t.Fatalf("cloneMetadata(nil) = %#v, want nil", got)
	}
	if got := cloneMetadata(map[string]string{}); got != nil {
		t.Fatalf("cloneMetadata(empty) = %#v, want nil", got)
	}

	original := map[string]string{"owner": "alice", "status": "draft"}
	cloned := cloneMetadata(original)
	if !reflect.DeepEqual(cloned, original) {
		t.Fatalf("cloneMetadata() = %#v, want %#v", cloned, original)
	}
	cloned["owner"] = "bob"
	if original["owner"] != "alice" {
		t.Fatalf("original metadata mutated = %#v", original)
	}
}

func TestStoreDeleteOldest_NilStore(t *testing.T) {
	var store *Store
	deleted, err := store.DeleteOldest(1, ScopeProject)
	if deleted != 0 {
		t.Fatalf("DeleteOldest() deleted = %d, want 0", deleted)
	}
	requireMemoryErrorCode(t, err, "nil_store")
}

func newTestStore(t *testing.T) *Store {
	t.Helper()

	rootDir := t.TempDir()
	dbPath := filepath.Join(rootDir, "memory.db")
	store, err := NewStore(dbPath)
	if err != nil {
		t.Fatalf("NewStore(%q) error = %v", dbPath, err)
	}
	t.Cleanup(func() {
		if closeErr := store.Close(); closeErr != nil {
			t.Errorf("Close() error = %v", closeErr)
		}
	})

	return store
}

func validRecord() *MemoryRecord {
	return &MemoryRecord{
		Type:        TypeNote,
		Source:      SourceUser,
		Scope:       ScopeProject,
		Title:       "Test title",
		Content:     "Test content",
		TrustLevel:  TrustMedium,
		Sensitivity: SensitivityNormal,
	}
}

func mustCreateRecord(t *testing.T, store *Store, record *MemoryRecord) *MemoryRecord {
	t.Helper()
	if err := store.Create(record); err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	return record
}

func mustGetRecord(t *testing.T, store *Store, id string) *MemoryRecord {
	t.Helper()
	record, err := store.GetByID(id)
	if err != nil {
		t.Fatalf("GetByID(%q) error = %v", id, err)
	}
	return record
}

func requireMemoryErrorCode(t *testing.T, err error, wantCode string) *Error {
	t.Helper()
	if err == nil {
		t.Fatalf("expected error code %q, got nil", wantCode)
	}
	memoryErr, ok := err.(*Error)
	if !ok {
		t.Fatalf("expected *Error, got %T", err)
	}
	if memoryErr.Code != wantCode {
		t.Fatalf("error code = %q, want %q", memoryErr.Code, wantCode)
	}
	return memoryErr
}

func countRecordsInDB(t *testing.T, store *Store, where string, args []any) int {
	t.Helper()

	query := `SELECT COUNT(*) FROM memory_records`
	if where != "" {
		query += ` WHERE ` + where
	}

	var count int
	if err := store.db.QueryRow(query, args...).Scan(&count); err != nil {
		t.Fatalf("QueryRow(%q) error = %v", query, err)
	}
	return count
}
