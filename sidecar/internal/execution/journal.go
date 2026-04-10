package execution

import (
	"strings"
	"time"
)

type JournalEntry struct {
	RunID       string                 `json:"run_id"`
	TaskID      string                 `json:"task_id"`
	Timestamp   time.Time              `json:"timestamp"`
	Action      string                 `json:"action"`
	Details     map[string]interface{} `json:"details,omitempty"`
	FilesBefore []string               `json:"files_before,omitempty"`
	FilesAfter  []string               `json:"files_after,omitempty"`
	CommandsRun []CommandRecord        `json:"commands_run,omitempty"`
	DurationMs  int64                  `json:"duration_ms,omitempty"`
	Error       string                 `json:"error,omitempty"`
}

type CommandRecord struct {
	Command    string `json:"command"`
	ExitCode   int    `json:"exit_code"`
	DurationMs int64  `json:"duration_ms"`
}

type ExecutionJournal struct {
	entries []JournalEntry
}

func NewExecutionJournal() *ExecutionJournal {
	return &ExecutionJournal{entries: make([]JournalEntry, 0)}
}

func (j *ExecutionJournal) Record(entry JournalEntry) {
	if j == nil {
		return
	}

	j.entries = append(j.entries, cloneJournalEntry(entry))
}

func (j *ExecutionJournal) Entries() []JournalEntry {
	if j == nil {
		return nil
	}

	entries := make([]JournalEntry, len(j.entries))
	for index, entry := range j.entries {
		entries[index] = cloneJournalEntry(entry)
	}

	return entries
}

func (j *ExecutionJournal) EntriesForTask(taskID string) []JournalEntry {
	if j == nil {
		return nil
	}

	normalizedTaskID := strings.TrimSpace(taskID)
	entries := make([]JournalEntry, 0)
	for _, entry := range j.entries {
		if strings.TrimSpace(entry.TaskID) != normalizedTaskID {
			continue
		}

		entries = append(entries, cloneJournalEntry(entry))
	}

	return entries
}

func (j *ExecutionJournal) Latest() JournalEntry {
	if j == nil || len(j.entries) == 0 {
		return JournalEntry{}
	}

	return cloneJournalEntry(j.entries[len(j.entries)-1])
}

func (j *ExecutionJournal) TaskCountByAction(action string) int {
	if j == nil {
		return 0
	}

	normalizedAction := strings.TrimSpace(action)
	count := 0
	for _, entry := range j.entries {
		if strings.TrimSpace(entry.Action) == normalizedAction {
			count++
		}
	}

	return count
}

func cloneJournalEntry(entry JournalEntry) JournalEntry {
	return JournalEntry{
		RunID:       strings.TrimSpace(entry.RunID),
		TaskID:      strings.TrimSpace(entry.TaskID),
		Timestamp:   entry.Timestamp,
		Action:      strings.TrimSpace(entry.Action),
		Details:     cloneDetails(entry.Details),
		FilesBefore: cloneTrimmedStrings(entry.FilesBefore),
		FilesAfter:  cloneTrimmedStrings(entry.FilesAfter),
		CommandsRun: cloneCommandRecords(entry.CommandsRun),
		DurationMs:  entry.DurationMs,
		Error:       strings.TrimSpace(entry.Error),
	}
}

func cloneCommandRecords(records []CommandRecord) []CommandRecord {
	if len(records) == 0 {
		return nil
	}

	cloned := make([]CommandRecord, 0, len(records))
	for _, record := range records {
		cloned = append(cloned, CommandRecord{
			Command:    strings.TrimSpace(record.Command),
			ExitCode:   record.ExitCode,
			DurationMs: record.DurationMs,
		})
	}

	if len(cloned) == 0 {
		return nil
	}

	return cloned
}

func cloneDetails(details map[string]interface{}) map[string]interface{} {
	if len(details) == 0 {
		return nil
	}

	cloned := make(map[string]interface{}, len(details))
	for key, value := range details {
		cloned[strings.TrimSpace(key)] = cloneDetailValue(value)
	}

	if len(cloned) == 0 {
		return nil
	}

	return cloned
}

func cloneDetailValue(value interface{}) interface{} {
	switch typed := value.(type) {
	case map[string]interface{}:
		return cloneDetails(typed)
	case []interface{}:
		cloned := make([]interface{}, len(typed))
		for index, item := range typed {
			cloned[index] = cloneDetailValue(item)
		}
		return cloned
	case []string:
		return cloneTrimmedStrings(typed)
	default:
		return typed
	}
}
