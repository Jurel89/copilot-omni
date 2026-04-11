package migration

import (
	"strconv"
	"strings"
)

func (e *Engine) RollbackToVersion(targetVersion int) error {
	return e.MigrateDown(targetVersion)
}

func (e *Engine) RollbackSteps(steps int) error {
	if steps < 0 {
		return &Error{Code: "invalid_rollback_steps", Path: strconv.Itoa(steps)}
	}

	currentVersion, err := e.GetCurrentVersion()
	if err != nil {
		return err
	}

	if steps > currentVersion {
		return &Error{Code: "invalid_rollback_steps", Path: strconv.Itoa(steps)}
	}

	return e.MigrateDown(currentVersion - steps)
}

func (e *Engine) CheckRollbackSafety(targetVersion int) error {
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

	applied, err := e.registry.Applied(e.name)
	if err != nil {
		return err
	}

	appliedByVersion := make(map[int]AppliedMigration, len(applied))
	for _, appliedMigration := range applied {
		appliedByVersion[appliedMigration.Version] = appliedMigration
	}

	for version := currentVersion; version > targetVersion; version-- {
		migration, err := e.getMigration(version)
		if err != nil {
			return err
		}

		appliedMigration, exists := appliedByVersion[version]
		if !exists {
			return &Error{Code: "migration_not_applied", Path: versionPath(e.name, version)}
		}

		if strings.TrimSpace(appliedMigration.Name) != strings.TrimSpace(migration.Name) {
			return &Error{Code: "rollback_state_mismatch", Path: versionPath(e.name, version)}
		}

		if migration.RollbackCheck != nil {
			if err := migration.RollbackCheck(e.context.transition(e.name, version, version-1)); err != nil {
				return &Error{Code: "rollback_safety_check_failed", Path: versionPath(e.name, version), Err: err}
			}
		}
	}

	return nil
}
