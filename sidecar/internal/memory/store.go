package memory

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

type Store struct {
	db *sql.DB
}

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

func DBPath(repoRoot string, dbPathOverride string) string {
	if strings.TrimSpace(dbPathOverride) != "" {
		if filepath.IsAbs(dbPathOverride) {
			return dbPathOverride
		}
		return filepath.Join(repoRoot, dbPathOverride)
	}
	return filepath.Join(repoRoot, ".omni", "memory.db")
}

func NewStore(dbPath string) (*Store, error) {
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

	store := &Store{db: db}
	if err := store.runMigrations(); err != nil {
		_ = db.Close()
		return nil, &Error{Code: "migration_failed", Path: dbPath, Err: err}
	}

	return store, nil
}

func (s *Store) Close() error {
	if s == nil || s.db == nil {
		return nil
	}
	return s.db.Close()
}

func (s *Store) runMigrations() error {
	_, err := s.db.Exec(`
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
		return fmt.Errorf("create memory_records table: %w", err)
	}

	return nil
}

func applyRecordDefaults(record *MemoryRecord) {
	if record.Type == "" {
		record.Type = TypeNote
	}
	if record.Source == "" {
		record.Source = SourceUser
	}
	if record.Scope == "" {
		record.Scope = ScopeProject
	}
	if record.TrustLevel == "" {
		record.TrustLevel = TrustMedium
	}
	if record.Sensitivity == "" {
		record.Sensitivity = SensitivityNormal
	}
}

func validateRecord(record *MemoryRecord) error {
	if !isValidType(record.Type) {
		return &Error{Code: "invalid_type", Path: record.Type}
	}
	if !isValidSource(record.Source) {
		return &Error{Code: "invalid_source", Path: record.Source}
	}
	if !isValidScope(record.Scope) {
		return &Error{Code: "invalid_scope", Path: record.Scope}
	}
	if !isValidTrustLevel(record.TrustLevel) {
		return &Error{Code: "invalid_trust_level", Path: record.TrustLevel}
	}
	if !isValidSensitivity(record.Sensitivity) {
		return &Error{Code: "invalid_sensitivity", Path: record.Sensitivity}
	}

	return nil
}

func (s *Store) insertRecord(record *MemoryRecord, metadataJSON string) error {
	_, err := s.db.Exec(`
		INSERT INTO memory_records (id, type, source, scope, run_id, title, content, metadata, tags, trust_level, sensitivity, created_at, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		record.ID, record.Type, record.Source, record.Scope, record.RunID,
		record.Title, record.Content, metadataJSON, tagsToString(record.Tags),
		record.TrustLevel, record.Sensitivity, record.CreatedAt, record.UpdatedAt,
	)
	if err != nil {
		return &Error{Code: "insert_failed", Path: record.ID, Err: err}
	}

	return nil
}

func recordUpsertPath(record *MemoryRecord) string {
	return strings.Join([]string{record.RunID, record.Type, record.Source}, ":")
}

func (s *Store) Create(record *MemoryRecord) error {
	if s == nil {
		return &Error{Code: "nil_store"}
	}
	if record == nil {
		return &Error{Code: "nil_record"}
	}

	applyRecordDefaults(record)
	if err := validateRecord(record); err != nil {
		return err
	}

	if record.ID == "" {
		id, err := generateID()
		if err != nil {
			return &Error{Code: "generate_id_failed", Err: err}
		}
		record.ID = id
	}

	now := time.Now().UTC()
	if record.CreatedAt.IsZero() {
		record.CreatedAt = now
	}
	record.UpdatedAt = now

	metadataJSON, err := json.Marshal(record.Metadata)
	if err != nil {
		return &Error{Code: "marshal_metadata_failed", Err: err}
	}

	return s.insertRecord(record, string(metadataJSON))
}

func (s *Store) CreateOrUpdate(record *MemoryRecord) error {
	if s == nil {
		return &Error{Code: "nil_store"}
	}
	if record == nil {
		return &Error{Code: "nil_record"}
	}

	if strings.TrimSpace(record.RunID) == "" {
		return s.Create(record)
	}

	applyRecordDefaults(record)
	if err := validateRecord(record); err != nil {
		return err
	}

	now := time.Now().UTC()
	record.UpdatedAt = now

	metadataJSON, err := json.Marshal(record.Metadata)
	if err != nil {
		return &Error{Code: "marshal_metadata_failed", Err: err}
	}

	result, err := s.db.Exec(`
		UPDATE memory_records
		SET scope = ?, title = ?, content = ?, metadata = ?, tags = ?, trust_level = ?, sensitivity = ?, updated_at = ?
		WHERE run_id = ? AND type = ? AND source = ?`,
		record.Scope, record.Title, record.Content, string(metadataJSON), tagsToString(record.Tags),
		record.TrustLevel, record.Sensitivity, record.UpdatedAt,
		record.RunID, record.Type, record.Source,
	)
	if err != nil {
		return &Error{Code: "update_failed", Path: recordUpsertPath(record), Err: err}
	}

	rows, _ := result.RowsAffected()
	if rows > 0 {
		return nil
	}

	if record.ID == "" {
		id, err := generateID()
		if err != nil {
			return &Error{Code: "generate_id_failed", Err: err}
		}
		record.ID = id
	}
	if record.CreatedAt.IsZero() {
		record.CreatedAt = now
	}

	return s.insertRecord(record, string(metadataJSON))
}

func (s *Store) GetByID(id string) (*MemoryRecord, error) {
	if s == nil {
		return nil, &Error{Code: "nil_store"}
	}
	if strings.TrimSpace(id) == "" {
		return nil, &Error{Code: "invalid_id"}
	}

	row := s.db.QueryRow(`
		SELECT id, type, source, scope, run_id, title, content, metadata, tags, trust_level, sensitivity, created_at, updated_at
		FROM memory_records WHERE id = ?`, id)

	return scanRecord(row)
}

func (s *Store) Delete(id string) error {
	if s == nil {
		return &Error{Code: "nil_store"}
	}
	if strings.TrimSpace(id) == "" {
		return &Error{Code: "invalid_id"}
	}

	result, err := s.db.Exec(`DELETE FROM memory_records WHERE id = ?`, id)
	if err != nil {
		return &Error{Code: "delete_failed", Path: id, Err: err}
	}

	rows, _ := result.RowsAffected()
	if rows == 0 {
		return &Error{Code: "record_not_found", Path: id}
	}

	return nil
}

func (s *Store) DeleteByScope(scope string) error {
	if s == nil {
		return &Error{Code: "nil_store"}
	}
	if !isValidScope(scope) {
		return &Error{Code: "invalid_scope", Path: scope}
	}

	_, err := s.db.Exec(`DELETE FROM memory_records WHERE scope = ?`, scope)
	if err != nil {
		return &Error{Code: "wipe_scope_failed", Err: err}
	}

	return nil
}

func (s *Store) DeleteByRunID(runID string) error {
	if s == nil {
		return &Error{Code: "nil_store"}
	}
	if strings.TrimSpace(runID) == "" {
		return &Error{Code: "invalid_run_id"}
	}

	_, err := s.db.Exec(`DELETE FROM memory_records WHERE run_id = ?`, runID)
	if err != nil {
		return &Error{Code: "delete_by_run_failed", Err: err}
	}

	return nil
}

func (s *Store) DeleteByAge(olderThan time.Duration) (int, error) {
	if s == nil {
		return 0, &Error{Code: "nil_store"}
	}

	cutoff := time.Now().UTC().Add(-olderThan)
	result, err := s.db.Exec(`DELETE FROM memory_records WHERE created_at < ?`, cutoff)
	if err != nil {
		return 0, &Error{Code: "prune_by_age_failed", Err: err}
	}

	rows, _ := result.RowsAffected()
	return int(rows), nil
}

func (s *Store) Export(scope string) ([]MemoryRecord, error) {
	if s == nil {
		return nil, &Error{Code: "nil_store"}
	}

	var rows *sql.Rows
	var err error

	if scope != "" {
		rows, err = s.db.Query(`
			SELECT id, type, source, scope, run_id, title, content, metadata, tags, trust_level, sensitivity, created_at, updated_at
			FROM memory_records WHERE scope = ? ORDER BY created_at DESC`, scope)
	} else {
		rows, err = s.db.Query(`
			SELECT id, type, source, scope, run_id, title, content, metadata, tags, trust_level, sensitivity, created_at, updated_at
			FROM memory_records ORDER BY created_at DESC`)
	}
	if err != nil {
		return nil, &Error{Code: "export_query_failed", Err: err}
	}
	defer rows.Close()

	return scanRecords(rows)
}

func (s *Store) RecordCount(scope string) (int, error) {
	if s == nil {
		return 0, &Error{Code: "nil_store"}
	}

	var count int
	var err error
	if scope != "" {
		err = s.db.QueryRow(`SELECT COUNT(*) FROM memory_records WHERE scope = ?`, scope).Scan(&count)
	} else {
		err = s.db.QueryRow(`SELECT COUNT(*) FROM memory_records`).Scan(&count)
	}
	if err != nil {
		return 0, &Error{Code: "count_failed", Err: err}
	}

	return count, nil
}

func (s *Store) DeleteOldest(limit int, scope string) (int, error) {
	if s == nil {
		return 0, &Error{Code: "nil_store"}
	}

	scopeFilter := ""
	args := []interface{}{}
	if scope != "" {
		scopeFilter = " AND scope = ?"
		args = append(args, scope)
	}
	args = append(args, limit)

	query := fmt.Sprintf(`
		DELETE FROM memory_records WHERE id IN (
			SELECT id FROM memory_records WHERE 1=1 %s ORDER BY created_at ASC LIMIT ?
		)`, scopeFilter)

	result, err := s.db.Exec(query, args...)
	if err != nil {
		return 0, &Error{Code: "delete_oldest_failed", Err: err}
	}

	rows, _ := result.RowsAffected()
	return int(rows), nil
}

func scanRecord(row *sql.Row) (*MemoryRecord, error) {
	var r MemoryRecord
	var metadataJSON string
	var tagsStr string

	err := row.Scan(
		&r.ID, &r.Type, &r.Source, &r.Scope, &r.RunID,
		&r.Title, &r.Content, &metadataJSON, &tagsStr,
		&r.TrustLevel, &r.Sensitivity, &r.CreatedAt, &r.UpdatedAt,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, &Error{Code: "record_not_found"}
		}
		return nil, &Error{Code: "scan_failed", Err: err}
	}

	r.Metadata = parseMetadata(metadataJSON)
	r.Tags = stringToTags(tagsStr)

	return &r, nil
}

func scanRecords(rows *sql.Rows) ([]MemoryRecord, error) {
	records := make([]MemoryRecord, 0)
	for rows.Next() {
		var r MemoryRecord
		var metadataJSON string
		var tagsStr string

		err := rows.Scan(
			&r.ID, &r.Type, &r.Source, &r.Scope, &r.RunID,
			&r.Title, &r.Content, &metadataJSON, &tagsStr,
			&r.TrustLevel, &r.Sensitivity, &r.CreatedAt, &r.UpdatedAt,
		)
		if err != nil {
			return nil, &Error{Code: "scan_records_failed", Err: err}
		}

		r.Metadata = parseMetadata(metadataJSON)
		r.Tags = stringToTags(tagsStr)
		records = append(records, r)
	}

	return records, rows.Err()
}

func parseMetadata(data string) map[string]string {
	if strings.TrimSpace(data) == "" || data == "{}" {
		return nil
	}
	var m map[string]string
	if err := json.Unmarshal([]byte(data), &m); err != nil || len(m) == 0 {
		return nil
	}
	return m
}
