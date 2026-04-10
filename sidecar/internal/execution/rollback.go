package execution

import (
	"fmt"
	"sort"
	"strings"
)

type RollbackRecommendation struct {
	RunID             string   `json:"run_id"`
	TaskID            string   `json:"task_id"`
	FilesAffected     []string `json:"files_affected"`
	CommandsRun       []string `json:"commands_run"`
	RollbackNote      string   `json:"rollback_note"`
	RecommendedAction string   `json:"recommended_action"`
	Reason            string   `json:"reason"`
}

func RecommendRollback(taskInfo TaskInfo, journal *ExecutionJournal) *RollbackRecommendation {
	entries := journal.EntriesForTask(taskInfo.ID)
	filesAffected := collectAffectedFiles(entries)
	commandsRun := collectCommandsRun(entries)
	downstreamTasks := findCompletedDownstreamTasks(taskInfo.ID, journal)

	recommendation := &RollbackRecommendation{
		RunID:             detectRunID(taskInfo.ID, entries, journal),
		TaskID:            strings.TrimSpace(taskInfo.ID),
		FilesAffected:     filesAffected,
		CommandsRun:       commandsRun,
		RollbackNote:      strings.TrimSpace(taskInfo.RollbackNote),
		RecommendedAction: "manual_rollback",
		Reason:            "task changed files and should be rolled back carefully",
	}

	if len(downstreamTasks) > 0 {
		recommendation.RecommendedAction = "manual_rollback"
		recommendation.Reason = fmt.Sprintf("downstream tasks already completed and may depend on task %q: %s", strings.TrimSpace(taskInfo.ID), strings.Join(downstreamTasks, ", "))
		return recommendation
	}

	if len(filesAffected) == 0 {
		recommendation.RecommendedAction = "rerun_verification"
		recommendation.Reason = fmt.Sprintf("no file changes were recorded for task %q", strings.TrimSpace(taskInfo.ID))
		return recommendation
	}

	if recommendation.RollbackNote != "" {
		recommendation.RecommendedAction = "git_revert"
		recommendation.Reason = "task recorded file changes and includes a rollback note"
		return recommendation
	}

	recommendation.Reason = "task recorded file changes but has no rollback note"
	return recommendation
}

func collectAffectedFiles(entries []JournalEntry) []string {
	files := make(map[string]struct{})
	for _, entry := range entries {
		for _, filePath := range entry.FilesBefore {
			if trimmed := strings.TrimSpace(filePath); trimmed != "" {
				files[trimmed] = struct{}{}
			}
		}
		for _, filePath := range entry.FilesAfter {
			if trimmed := strings.TrimSpace(filePath); trimmed != "" {
				files[trimmed] = struct{}{}
			}
		}
	}

	return sortedStringSet(files)
}

func collectCommandsRun(entries []JournalEntry) []string {
	commands := make(map[string]struct{})
	for _, entry := range entries {
		for _, record := range entry.CommandsRun {
			if trimmed := strings.TrimSpace(record.Command); trimmed != "" {
				commands[trimmed] = struct{}{}
			}
		}
	}

	return sortedStringSet(commands)
}

func findCompletedDownstreamTasks(taskID string, journal *ExecutionJournal) []string {
	if journal == nil {
		return nil
	}

	normalizedTaskID := strings.TrimSpace(taskID)
	if normalizedTaskID == "" {
		return nil
	}

	downstream := make(map[string]struct{})
	for _, entry := range journal.Entries() {
		if strings.TrimSpace(entry.TaskID) == normalizedTaskID {
			continue
		}
		if strings.TrimSpace(entry.Action) != "task_completed" {
			continue
		}
		if !entryDependsOnTask(entry, normalizedTaskID) {
			continue
		}

		downstream[strings.TrimSpace(entry.TaskID)] = struct{}{}
	}

	return sortedStringSet(downstream)
}

func entryDependsOnTask(entry JournalEntry, taskID string) bool {
	dependencyKeys := []string{"dependencies", "dependency_ids", "depends_on", "completed_dependencies"}
	for _, key := range dependencyKeys {
		dependencyIDs, ok := stringSliceFromDetails(entry.Details, key)
		if !ok {
			continue
		}
		for _, dependencyID := range dependencyIDs {
			if dependencyID == taskID {
				return true
			}
		}
	}

	return false
}

func stringSliceFromDetails(details map[string]interface{}, key string) ([]string, bool) {
	if len(details) == 0 {
		return nil, false
	}

	rawValue, ok := details[key]
	if !ok || rawValue == nil {
		return nil, false
	}

	switch typed := rawValue.(type) {
	case []string:
		return cloneTrimmedStrings(typed), true
	case []interface{}:
		values := make([]string, 0, len(typed))
		for _, item := range typed {
			value, ok := item.(string)
			if !ok {
				return nil, false
			}
			if trimmed := strings.TrimSpace(value); trimmed != "" {
				values = append(values, trimmed)
			}
		}
		return values, true
	default:
		return nil, false
	}
}

func detectRunID(taskID string, entries []JournalEntry, journal *ExecutionJournal) string {
	for _, entry := range entries {
		if strings.TrimSpace(entry.RunID) != "" {
			return strings.TrimSpace(entry.RunID)
		}
	}

	if journal == nil {
		return ""
	}

	normalizedTaskID := strings.TrimSpace(taskID)
	for _, entry := range journal.Entries() {
		if strings.TrimSpace(entry.TaskID) != normalizedTaskID {
			continue
		}
		if strings.TrimSpace(entry.RunID) != "" {
			return strings.TrimSpace(entry.RunID)
		}
	}

	return ""
}

func sortedStringSet(values map[string]struct{}) []string {
	if len(values) == 0 {
		return nil
	}

	items := make([]string, 0, len(values))
	for value := range values {
		items = append(items, value)
	}
	sort.Strings(items)
	return items
}
