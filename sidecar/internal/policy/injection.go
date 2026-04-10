package policy

import (
	"regexp"
	"sort"
	"strings"
)

type InjectionScanResult struct {
	Clean      bool     `json:"clean"`
	Detections []string `json:"detections,omitempty"`
	Severity   string   `json:"severity"`
	Sanitized  string   `json:"sanitized,omitempty"`
}

type injectionPattern struct {
	label    string
	severity string
	re       *regexp.Regexp
}

var injectionPatterns = []injectionPattern{
	{label: "ignore previous instructions", severity: "critical", re: regexp.MustCompile(`(?i)ignore\s+previous\s+instructions`)},
	{label: "ignore all previous", severity: "critical", re: regexp.MustCompile(`(?i)ignore\s+all\s+previous`)},
	{label: "disregard all", severity: "medium", re: regexp.MustCompile(`(?i)disregard\s+all`)},
	{label: "you are now", severity: "medium", re: regexp.MustCompile(`(?i)you\s+are\s+now`)},
	{label: "new instructions", severity: "medium", re: regexp.MustCompile(`(?i)new\s+instructions`)},
	{label: "system prompt", severity: "critical", re: regexp.MustCompile(`(?i)system\s+prompt`)},
	{label: "</system>", severity: "medium", re: regexp.MustCompile(`(?i)</system>`)},
	{label: "<system>", severity: "medium", re: regexp.MustCompile(`(?i)<system>`)},
	{label: "SYSTEM:", severity: "medium", re: regexp.MustCompile(`(?i)system:`)},
	{label: "inject", severity: "medium", re: regexp.MustCompile(`(?i)inject`)},
	{label: "injection marker", severity: "medium", re: regexp.MustCompile(`(?i)injection\s+marker`)},
}

func ScanForInjection(content string) InjectionScanResult {
	detections := make([]string, 0)
	seen := make(map[string]struct{})
	sanitized := content
	severity := "clean"

	for _, pattern := range injectionPatterns {
		if !pattern.re.MatchString(sanitized) {
			continue
		}

		if _, exists := seen[pattern.label]; !exists {
			seen[pattern.label] = struct{}{}
			detections = append(detections, pattern.label)
		}

		severity = higherSeverity(severity, pattern.severity)
		sanitized = pattern.re.ReplaceAllString(sanitized, "[REDACTED: potential injection]")
	}

	if len(detections) == 0 {
		return InjectionScanResult{
			Clean:     true,
			Severity:  "clean",
			Sanitized: content,
		}
	}

	sort.Strings(detections)

	return InjectionScanResult{
		Clean:      false,
		Detections: detections,
		Severity:   severity,
		Sanitized:  sanitized,
	}
}

func higherSeverity(current, candidate string) string {
	if severityRank(candidate) > severityRank(current) {
		return candidate
	}

	return current
}

func severityRank(value string) int {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "low":
		return 1
	case "medium":
		return 2
	case "high":
		return 3
	case "critical":
		return 4
	default:
		return 0
	}
}
