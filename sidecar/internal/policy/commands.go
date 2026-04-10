package policy

import (
	"path/filepath"
	"regexp"
	"strings"
)

func IsDeniedCommand(command string, deniedCommands []string) (bool, string) {
	raw := strings.TrimSpace(strings.ToLower(command))
	normalized := NormalizeCommand(command)
	if raw == "" && normalized == "" {
		return false, ""
	}

	for _, rule := range deniedCommands {
		trimmedRule := strings.TrimSpace(rule)
		if trimmedRule == "" {
			continue
		}

		alternatives := strings.Split(trimmedRule, "|")
		for _, alternative := range alternatives {
			candidate := strings.TrimSpace(strings.ToLower(alternative))
			if candidate == "" {
				continue
			}

			if matchesCommandRule(raw, normalized, candidate) {
				return true, strings.TrimSpace(alternative)
			}
		}
	}

	return false, ""
}

func NormalizeCommand(raw string) string {
	fields := strings.Fields(strings.TrimSpace(raw))
	if len(fields) == 0 {
		return ""
	}

	index := 0
	for index < len(fields) && isEnvAssignment(fields[index]) {
		index++
	}

	if index >= len(fields) {
		return ""
	}

	command := strings.TrimSpace(fields[index])
	if command == "" {
		return ""
	}

	return strings.ToLower(filepath.Base(command))
}

func matchesCommandRule(raw, normalized, candidate string) bool {
	if raw == candidate || normalized == candidate {
		return true
	}

	if strings.HasPrefix(raw, candidate+" ") || strings.HasPrefix(raw, candidate+"\t") {
		return true
	}

	if strings.HasPrefix(normalized, candidate) {
		return true
	}

	if looksLikePattern(candidate) {
		re, err := regexp.Compile(candidate)
		if err == nil && (re.MatchString(raw) || re.MatchString(normalized)) {
			return true
		}
	}

	return false
}

func isEnvAssignment(token string) bool {
	if token == "" {
		return false
	}

	equalsIndex := strings.Index(token, "=")
	if equalsIndex <= 0 {
		return false
	}

	key := token[:equalsIndex]
	return !strings.ContainsAny(key, `/\\.:`)
}

func looksLikePattern(value string) bool {
	return strings.ContainsAny(value, `.*+?[](){}^$\\`)
}
