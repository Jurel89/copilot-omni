package memory

import (
	"crypto/rand"
	"fmt"
	"strings"
	"time"
)

// MemoryRecord represents a single memory entry in the local store.
type MemoryRecord struct {
	ID          string            `json:"id"`
	Type        string            `json:"type"`
	Source      string            `json:"source"`
	Scope       string            `json:"scope"`
	RunID       string            `json:"run_id,omitempty"`
	Title       string            `json:"title"`
	Content     string            `json:"content"`
	Metadata    map[string]string `json:"metadata,omitempty"`
	Tags        []string          `json:"tags,omitempty"`
	TrustLevel  string            `json:"trust_level"`
	Sensitivity string            `json:"sensitivity"`
	CreatedAt   time.Time         `json:"created_at"`
	UpdatedAt   time.Time         `json:"updated_at"`
}

const (
	TypeSpec         = "spec"
	TypePlan         = "plan"
	TypeDecision     = "decision"
	TypeSummary      = "summary"
	TypeNote         = "note"
	TypeVerification = "verification"

	SourceUser     = "user"
	SourceSystem   = "system"
	SourceArtifact = "artifact"

	ScopeProject = "project"
	ScopeGlobal  = "global"

	TrustHigh   = "high"
	TrustMedium = "medium"
	TrustLow    = "low"

	SensitivityNormal    = "normal"
	SensitivitySensitive = "sensitive"
	SensitivitySecret    = "secret"
)

func generateID() (string, error) {
	timestamp := time.Now().UTC().UnixMilli()
	b := make([]byte, 6)
	if _, err := rand.Read(b); err != nil {
		return "", fmt.Errorf("generate random bytes: %w", err)
	}
	return fmt.Sprintf("mem-%d-%x", timestamp, b), nil
}

func isValidType(t string) bool {
	switch t {
	case TypeSpec, TypePlan, TypeDecision, TypeSummary, TypeNote, TypeVerification:
		return true
	default:
		return false
	}
}

func isValidSource(s string) bool {
	switch s {
	case SourceUser, SourceSystem, SourceArtifact:
		return true
	default:
		return false
	}
}

func isValidScope(s string) bool {
	switch s {
	case ScopeProject, ScopeGlobal:
		return true
	default:
		return false
	}
}

func isValidTrustLevel(t string) bool {
	switch t {
	case TrustHigh, TrustMedium, TrustLow:
		return true
	default:
		return false
	}
}

func isValidSensitivity(s string) bool {
	switch s {
	case SensitivityNormal, SensitivitySensitive, SensitivitySecret:
		return true
	default:
		return false
	}
}

func normalizeTags(tags []string) []string {
	if len(tags) == 0 {
		return nil
	}
	seen := make(map[string]struct{}, len(tags))
	result := make([]string, 0, len(tags))
	for _, tag := range tags {
		tag = strings.TrimSpace(strings.ToLower(tag))
		if tag == "" {
			continue
		}
		if _, exists := seen[tag]; exists {
			continue
		}
		seen[tag] = struct{}{}
		result = append(result, tag)
	}
	if len(result) == 0 {
		return nil
	}
	return result
}

func tagsToString(tags []string) string {
	if len(tags) == 0 {
		return ""
	}
	return "," + strings.Join(tags, ",") + ","
}

func stringToTags(s string) []string {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil
	}
	parts := strings.Split(s, ",")
	tags := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			tags = append(tags, part)
		}
	}
	if len(tags) == 0 {
		return nil
	}
	return tags
}

func cloneTags(tags []string) []string {
	if len(tags) == 0 {
		return nil
	}
	return append([]string(nil), tags...)
}

func cloneMetadata(m map[string]string) map[string]string {
	if len(m) == 0 {
		return nil
	}
	cloned := make(map[string]string, len(m))
	for k, v := range m {
		cloned[k] = v
	}
	return cloned
}
