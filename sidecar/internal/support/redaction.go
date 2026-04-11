package support

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

type RedactionRule struct {
	Name        string `json:"name"`
	Pattern     string `json:"pattern"`
	Replacement string `json:"replacement"`
}

type RedactionLevel string

const (
	RedactionMinimal    RedactionLevel = "minimal"
	RedactionStandard   RedactionLevel = "standard"
	RedactionAggressive RedactionLevel = "aggressive"
)

type compiledRule struct {
	definition RedactionRule
	regexp     *regexp.Regexp
}

type Redactor struct {
	rules map[RedactionLevel][]compiledRule
}

func NewRedactor() *Redactor {
	return &Redactor{
		rules: map[RedactionLevel][]compiledRule{
			RedactionMinimal:  compileRules(baseRules(false)...),
			RedactionStandard: compileRules(baseRules(true)...),
			RedactionAggressive: compileRules(append(baseRules(true), []RedactionRule{
				{Name: "email", Pattern: `(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b`, Replacement: "[REDACTED_EMAIL]"},
				{Name: "ipv4", Pattern: `\b(?:\d{1,3}\.){3}\d{1,3}\b`, Replacement: "[REDACTED_IP]"},
			}...)...),
		},
	}
}

func (r *Redactor) GetRules(level RedactionLevel) []RedactionRule {
	compiled := r.rules[r.normalizeLevel(level)]
	rules := make([]RedactionRule, 0, len(compiled))
	for _, rule := range compiled {
		rules = append(rules, rule.definition)
	}
	return rules
}

func (r *Redactor) RedactString(value string, level RedactionLevel) (string, bool) {
	result := value
	redacted := false
	for _, rule := range r.rules[r.normalizeLevel(level)] {
		updated := rule.regexp.ReplaceAllString(result, rule.definition.Replacement)
		if updated != result {
			redacted = true
			result = updated
		}
	}
	return result, redacted
}

func (r *Redactor) Redact(data []byte, level RedactionLevel) ([]byte, bool) {
	result, redacted := r.RedactString(string(data), level)
	return []byte(result), redacted
}

func (r *Redactor) RedactPath(path string, level RedactionLevel) (string, bool) {
	if strings.TrimSpace(path) == "" {
		return path, false
	}
	result := filepath.Clean(path)
	redacted := false

	if homeDir, err := os.UserHomeDir(); err == nil && strings.TrimSpace(homeDir) != "" {
		if rel, relErr := filepath.Rel(homeDir, result); relErr == nil && rel != "." && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
			result = filepath.Join("[HOME]", rel)
			redacted = true
		}
	}

	if level == RedactionAggressive {
		segments := strings.Split(filepath.ToSlash(result), "/")
		for i := range segments {
			if segments[i] == "Users" || segments[i] == "home" {
				if i+1 < len(segments) && segments[i+1] != "" {
					segments[i+1] = "[USER]"
					redacted = true
				}
			}
		}
		result = filepath.FromSlash(strings.Join(segments, "/"))
	}

	return result, redacted
}

func (r *Redactor) normalizeLevel(level RedactionLevel) RedactionLevel {
	switch level {
	case RedactionMinimal, RedactionStandard, RedactionAggressive:
		return level
	default:
		return RedactionStandard
	}
}

func compileRules(rules ...RedactionRule) []compiledRule {
	compiled := make([]compiledRule, 0, len(rules))
	for _, rule := range rules {
		compiled = append(compiled, compiledRule{
			definition: rule,
			regexp:     regexp.MustCompile(rule.Pattern),
		})
	}
	return compiled
}

func baseRules(includePaths bool) []RedactionRule {
	rules := []RedactionRule{
		{Name: "api_key_quoted", Pattern: `(?im)(api[_-]?key\s*[=:]\s*["'])[^"'\r\n]+["']`, Replacement: `${1}[REDACTED]`},
		{Name: "api_key_unquoted", Pattern: `(?im)(api[_-]?key\s*[=:]\s*)[^"'\s\r\n]+`, Replacement: `${1}[REDACTED]`},
		{Name: "token_quoted", Pattern: `(?im)(token\s*[=:]\s*["'])[^"'\r\n]+["']`, Replacement: `${1}[REDACTED]`},
		{Name: "token_unquoted", Pattern: `(?im)(token\s*[=:]\s*)[^"'\s\r\n]+`, Replacement: `${1}[REDACTED]`},
		{Name: "password_quoted", Pattern: `(?im)(password\s*[=:]\s*["'])[^"'\r\n]+["']`, Replacement: `${1}[REDACTED]`},
		{Name: "password_unquoted", Pattern: `(?im)(password\s*[=:]\s*)[^"'\s\r\n]+`, Replacement: `${1}[REDACTED]`},
		{Name: "bearer", Pattern: `(?i)bearer\s+[a-z0-9._\-]+`, Replacement: "Bearer [REDACTED]"},
		{Name: "github_pat", Pattern: `\bgh[pousr]_[A-Za-z0-9_]{20,}\b`, Replacement: "[REDACTED_TOKEN]"},
	}

	if !includePaths {
		return rules
	}

	if homeDir, err := os.UserHomeDir(); err == nil && strings.TrimSpace(homeDir) != "" {
		rules = append(rules, RedactionRule{Name: "home_dir", Pattern: regexp.QuoteMeta(homeDir), Replacement: "[HOME]"})
	}

	if user := strings.TrimSpace(os.Getenv("USER")); user != "" {
		rules = append(rules, RedactionRule{Name: "username", Pattern: fmt.Sprintf(`(?i)(/Users/|/home/)%s\b`, regexp.QuoteMeta(user)), Replacement: "/$1/[USER]"})
	}

	return rules
}
