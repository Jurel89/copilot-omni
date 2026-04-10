package policy

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type pathError struct {
	Code string
	Err  error
}

func (e *pathError) Error() string {
	if e == nil {
		return ""
	}

	if e.Err != nil {
		return fmt.Sprintf("%s: %v", e.Code, e.Err)
	}

	return e.Code
}

func (e *pathError) Unwrap() error {
	if e == nil {
		return nil
	}

	return e.Err
}

func NormalizePath(repoRoot, inputPath string) (string, error) {
	repoRoot = strings.TrimSpace(repoRoot)
	inputPath = strings.TrimSpace(inputPath)
	if repoRoot == "" || inputPath == "" {
		return "", &pathError{Code: ReasonPathTraversal}
	}

	if filepath.IsAbs(inputPath) {
		return "", &pathError{Code: ReasonPathTraversal}
	}

	cleanedInput := filepath.Clean(inputPath)
	if cleanedInput == "." || cleanedInput == "" {
		return "", &pathError{Code: ReasonPathTraversal}
	}

	if cleanedInput == ".." || strings.HasPrefix(cleanedInput, ".."+string(filepath.Separator)) {
		return "", &pathError{Code: ReasonPathTraversal}
	}

	rootAbs, err := filepath.Abs(repoRoot)
	if err != nil {
		return "", &pathError{Code: ReasonPathTraversal, Err: err}
	}

	resolvedPath, err := resolveWithinRoot(rootAbs, filepath.Join(rootAbs, cleanedInput))
	if err != nil {
		return "", err
	}

	relPath, err := filepath.Rel(rootAbs, resolvedPath)
	if err != nil {
		return "", &pathError{Code: ReasonPathTraversal, Err: err}
	}

	relPath = filepath.Clean(relPath)
	if relPath == "." || relPath == ".." || strings.HasPrefix(relPath, ".."+string(filepath.Separator)) {
		return "", &pathError{Code: ReasonPathTraversal}
	}

	return filepath.ToSlash(relPath), nil
}

func IsProtectedPath(normalizedPath string, protectedPaths []string) bool {
	normalizedPath = normalizeMatchPath(normalizedPath)
	if normalizedPath == "" {
		return false
	}

	for _, pattern := range protectedPaths {
		normalizedPattern := normalizeMatchPath(pattern)
		if normalizedPattern == "" {
			continue
		}

		if pathMatchesPattern(normalizedPath, normalizedPattern) {
			return true
		}
	}

	return false
}

func IsWithinScope(normalizedPath string, fileTargets []string) bool {
	normalizedPath = normalizeMatchPath(normalizedPath)
	if normalizedPath == "" || len(fileTargets) == 0 {
		return false
	}

	for _, target := range fileTargets {
		normalizedTarget := normalizeMatchPath(target)
		if normalizedTarget == "" {
			continue
		}

		if pathMatchesPattern(normalizedPath, normalizedTarget) {
			return true
		}
	}

	return false
}

func resolveWithinRoot(rootAbs, pathAbs string) (string, error) {
	current := filepath.Clean(pathAbs)
	missingParts := make([]string, 0)

	for {
		_, err := os.Lstat(current)
		if err == nil {
			break
		}

		if !errors.Is(err, os.ErrNotExist) {
			return "", &pathError{Code: ReasonPathTraversal, Err: err}
		}

		parent := filepath.Dir(current)
		if parent == current {
			return "", &pathError{Code: ReasonPathTraversal, Err: err}
		}

		missingParts = append([]string{filepath.Base(current)}, missingParts...)
		current = parent
	}

	resolvedExisting, err := filepath.EvalSymlinks(current)
	if err != nil {
		return "", &pathError{Code: ReasonPathTraversal, Err: err}
	}

	resolvedPath := resolvedExisting
	if len(missingParts) > 0 {
		resolvedPath = filepath.Join(resolvedExisting, filepath.Join(missingParts...))
	}

	relPath, err := filepath.Rel(rootAbs, resolvedPath)
	if err != nil {
		return "", &pathError{Code: ReasonPathTraversal, Err: err}
	}

	if relPath == ".." || strings.HasPrefix(relPath, ".."+string(filepath.Separator)) {
		return "", &pathError{Code: ReasonPathTraversal}
	}

	return resolvedPath, nil
}

func normalizeMatchPath(value string) string {
	trimmed := strings.TrimSpace(filepath.ToSlash(filepath.Clean(value)))
	if trimmed == "." || trimmed == "" {
		return ""
	}

	if strings.HasSuffix(filepath.ToSlash(value), "/") && !strings.HasSuffix(trimmed, "/") {
		trimmed += "/"
	}

	return trimmed
}

func pathMatchesPattern(normalizedPath, normalizedPattern string) bool {
	if normalizedPath == normalizedPattern {
		return true
	}

	if strings.HasSuffix(normalizedPattern, "/") {
		return strings.HasPrefix(normalizedPath, normalizedPattern)
	}

	return strings.HasPrefix(normalizedPath, normalizedPattern+"/")
}
