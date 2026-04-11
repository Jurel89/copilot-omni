package schema

import (
	"fmt"
	"strings"
)

type MigrationManifest struct {
	Version         string            `json:"version"`
	GeneratedAt     string            `json:"generated_at"`
	CurrentVersions []SchemaVersion   `json:"current_versions"`
	TargetVersions  []SchemaVersion   `json:"target_versions"`
	Records         []MigrationRecord `json:"records"`
}

type SchemaVersion struct {
	Component     string `json:"component"`
	Version       string `json:"version"`
	MinCompatible string `json:"min_compatible,omitempty"`
}

type MigrationRecord struct {
	ID                string `json:"id"`
	Component         string `json:"component"`
	FromVersion       string `json:"from_version"`
	ToVersion         string `json:"to_version"`
	Direction         string `json:"direction"`
	Status            string `json:"status"`
	RollbackSupported bool   `json:"rollback_supported"`
	AppliedAt         string `json:"applied_at,omitempty"`
	Notes             string `json:"notes,omitempty"`
}

func ValidateMigrationManifest(manifest map[string]any) ([]string, error) {
	warnings := make([]string, 0)
	validationErrors := make([]string, 0)

	if len(manifest) == 0 {
		validationErrors = append(validationErrors, "migration manifest payload must not be empty")
		return warnings, &ValidationError{Code: "invalid_migration_manifest", Messages: validationErrors}
	}

	if _, ok := getRequiredString(manifest, "version"); !ok {
		validationErrors = append(validationErrors, "version must be a non-empty string")
	}

	if _, ok := getOptionalString(manifest, "generated_at"); !ok {
		warnings = append(warnings, "generated_at should be a string when provided")
	} else if strings.TrimSpace(reportStringValue(manifest, "generated_at")) == "" {
		warnings = append(warnings, "generated_at is missing")
	}

	rawCurrentVersions, ok := manifest["current_versions"].([]interface{})
	if !ok || len(rawCurrentVersions) == 0 {
		validationErrors = append(validationErrors, "current_versions must be a non-empty array")
	}

	rawTargetVersions, ok := manifest["target_versions"].([]interface{})
	if !ok || len(rawTargetVersions) == 0 {
		validationErrors = append(validationErrors, "target_versions must be a non-empty array")
	}

	rawRecords, ok := manifest["records"].([]interface{})
	if !ok {
		validationErrors = append(validationErrors, "records must be an array")
	}

	currentVersions := validateSchemaVersionSet(rawCurrentVersions, "current_versions", &warnings, &validationErrors)
	targetVersions := validateSchemaVersionSet(rawTargetVersions, "target_versions", &warnings, &validationErrors)

	recordIDs := make(map[string]struct{}, len(rawRecords))
	for index, rawRecord := range rawRecords {
		record, ok := rawRecord.(map[string]any)
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("records[%d] must be an object", index))
			continue
		}

		recordID, ok := getRequiredString(record, "id")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("records[%d].id must be a non-empty string", index))
		} else if _, exists := recordIDs[recordID]; exists {
			validationErrors = append(validationErrors, fmt.Sprintf("records[%d].id %q is duplicated", index, recordID))
		} else {
			recordIDs[recordID] = struct{}{}
		}

		component, ok := getRequiredString(record, "component")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("records[%d].component must be a non-empty string", index))
		} else if _, exists := currentVersions[component]; !exists {
			if _, targetExists := targetVersions[component]; !targetExists {
				validationErrors = append(validationErrors, fmt.Sprintf("records[%d].component %q is not declared in current_versions or target_versions", index, component))
			}
		}

		fromVersion, ok := getRequiredString(record, "from_version")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("records[%d].from_version must be a non-empty string", index))
		}

		toVersion, ok := getRequiredString(record, "to_version")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("records[%d].to_version must be a non-empty string", index))
		}

		direction, ok := getRequiredString(record, "direction")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("records[%d].direction must be a non-empty string", index))
		} else if direction != "upgrade" && direction != "downgrade" && direction != "noop" {
			validationErrors = append(validationErrors, fmt.Sprintf("records[%d].direction must be one of: upgrade, downgrade, noop", index))
		}

		status, ok := getRequiredString(record, "status")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("records[%d].status must be a non-empty string", index))
		} else if status != "pending" && status != "applied" && status != "skipped" && status != "failed" && status != "rolled_back" {
			validationErrors = append(validationErrors, fmt.Sprintf("records[%d].status must be one of: pending, applied, skipped, failed, rolled_back", index))
		}

		rollbackSupported, ok := getRequiredBool(record, "rollback_supported")
		if !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("records[%d].rollback_supported must be a boolean", index))
		} else if !rollbackSupported {
			warnings = append(warnings, fmt.Sprintf("records[%d].rollback_supported is false", index))
		}

		if _, ok := getOptionalString(record, "applied_at"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("records[%d].applied_at must be a string", index))
		} else if status == "applied" && strings.TrimSpace(reportStringValue(record, "applied_at")) == "" {
			warnings = append(warnings, fmt.Sprintf("records[%d].applied_at is missing for an applied migration", index))
		}

		if _, ok := getOptionalString(record, "notes"); !ok {
			validationErrors = append(validationErrors, fmt.Sprintf("records[%d].notes must be a string", index))
		}

		if fromVersion != "" && toVersion != "" {
			if fromVersion == toVersion && direction != "noop" {
				validationErrors = append(validationErrors, fmt.Sprintf("records[%d].direction must be noop when from_version and to_version match", index))
			}
			if fromVersion != toVersion && direction == "noop" {
				validationErrors = append(validationErrors, fmt.Sprintf("records[%d].direction must not be noop when from_version and to_version differ", index))
			}
		}
	}

	if len(rawRecords) == 0 {
		if versionSetsDiffer(currentVersions, targetVersions) {
			validationErrors = append(validationErrors, "records must describe the changes between current_versions and target_versions")
		} else {
			warnings = append(warnings, "records is empty")
		}
	}

	return warnings, finalizeArtifactValidation("invalid_migration_manifest", validationErrors)
}

func validateSchemaVersionSet(rawVersions []any, fieldName string, warnings *[]string, validationErrors *[]string) map[string]string {
	versions := make(map[string]string, len(rawVersions))

	for index, rawVersion := range rawVersions {
		version, ok := rawVersion.(map[string]any)
		if !ok {
			*validationErrors = append(*validationErrors, fmt.Sprintf("%s[%d] must be an object", fieldName, index))
			continue
		}

		component, ok := getRequiredString(version, "component")
		if !ok {
			*validationErrors = append(*validationErrors, fmt.Sprintf("%s[%d].component must be a non-empty string", fieldName, index))
		}

		componentVersion, ok := getRequiredString(version, "version")
		if !ok {
			*validationErrors = append(*validationErrors, fmt.Sprintf("%s[%d].version must be a non-empty string", fieldName, index))
		}

		if _, ok := getOptionalString(version, "min_compatible"); !ok {
			*validationErrors = append(*validationErrors, fmt.Sprintf("%s[%d].min_compatible must be a string", fieldName, index))
		}

		if component == "" {
			continue
		}

		if _, exists := versions[component]; exists {
			*validationErrors = append(*validationErrors, fmt.Sprintf("%s[%d].component %q is duplicated", fieldName, index, component))
			continue
		}

		versions[component] = componentVersion
		if strings.TrimSpace(componentVersion) == "" {
			continue
		}

		if minCompatible, _ := getOptionalString(version, "min_compatible"); minCompatible == "" {
			*warnings = append(*warnings, fmt.Sprintf("%s[%d].min_compatible is missing", fieldName, index))
		}
	}

	return versions
}

func versionSetsDiffer(currentVersions map[string]string, targetVersions map[string]string) bool {
	if len(currentVersions) != len(targetVersions) {
		return true
	}

	for component, currentVersion := range currentVersions {
		targetVersion, ok := targetVersions[component]
		if !ok || targetVersion != currentVersion {
			return true
		}
	}

	return false
}
