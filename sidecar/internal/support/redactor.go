package support

import (
	"os"
	"regexp"
)

type Redactor struct {
	rules map[RedactionLevel][]RedactionRule
}

func NewRedactor() *Redactor {
	r := &Redactor{
		rules: map[RedactionLevel][]RedactionRule{
			RedactionMinimal: {
				{Name: "api_key", Pattern: `(?i)(api[_-]?key\s*[=:]\s*)["']?[a-zA-Z0-9_\-]{20,}["']?`, Replacement: "${1}[REDACTED]"},
				{Name: "token", Pattern: `(?i)(token\s*[=:]\s*)["']?[a-zA-Z0-9_\-]{20,}["']?`, Replacement: "${1}[REDACTED]"},
				{Name: "password", Pattern: `(?i)(password\s*[=:]\s*)["']?[^"'\s]+["']?`, Replacement: "${1}[REDACTED]"},
			},
			RedactionStandard: {
				{Name: "api_key", Pattern: `(?i)(api[_-]?key\s*[=:]\s*)["']?[a-zA-Z0-9_\-]{20,}["']?`, Replacement: "${1}[REDACTED]"},
				{Name: "token", Pattern: `(?i)(token\s*[=:]\s*)["']?[a-zA-Z0-9_\-]{20,}["']?`, Replacement: "${1}[REDACTED]"},
				{Name: "password", Pattern: `(?i)(password\s*[=:]\s*)["']?[^"'\s]+["']?`, Replacement: "${1}[REDACTED]"},
				{Name: "home_path", Pattern: regexp.QuoteMeta(os.Getenv("HOME")), Replacement: "[HOME]"},
				{Name: "user_path", Pattern: regexp.QuoteMeta(os.Getenv("USER")), Replacement: "[USER]"},
			},
			RedactionAggressive: {
				{Name: "api_key", Pattern: `(?i)(api[_-]?key\s*[=:]\s*)["']?[a-zA-Z0-9_\-]{20,}["']?`, Replacement: "${1}[REDACTED]"},
				{Name: "token", Pattern: `(?i)(token\s*[=:]\s*)["']?[a-zA-Z0-9_\-]{20,}["']?`, Replacement: "${1}[REDACTED]"},
				{Name: "password", Pattern: `(?i)(password\s*[=:]\s*)["']?[^"'\s]+["']?`, Replacement: "${1}[REDACTED]"},
				{Name: "home_path", Pattern: regexp.QuoteMeta(os.Getenv("HOME")), Replacement: "[HOME]"},
				{Name: "user_path", Pattern: regexp.QuoteMeta(os.Getenv("USER")), Replacement: "[USER]"},
				{Name: "email", Pattern: `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`, Replacement: "[EMAIL]"},
				{Name: "ip_address", Pattern: `\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b`, Replacement: "[IP]"},
			},
		},
	}
	return r
}

func (r *Redactor) GetRules(level RedactionLevel) []RedactionRule {
	return r.rules[level]
}

func (r *Redactor) Redact(data []byte, level RedactionLevel) ([]byte, bool) {
	redacted := false
	result := string(data)

	for _, rule := range r.rules[level] {
		re := regexp.MustCompile(rule.Pattern)
		if re.MatchString(result) {
			redacted = true
			result = re.ReplaceAllString(result, rule.Replacement)
		}
	}

	return []byte(result), redacted
}
