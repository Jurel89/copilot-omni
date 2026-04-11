package policypack

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type PolicyPack struct {
	Name        string            `json:"name"`
	Version     string            `json:"version"`
	Profile     string            `json:"profile"`
	Description string            `json:"description,omitempty"`
	Rules       []PolicyRule      `json:"rules"`
	Metadata    map[string]string `json:"metadata,omitempty"`
}

type PolicyRule struct {
	ID          string   `json:"id"`
	Category    string   `json:"category"`
	Severity    string   `json:"severity"`
	Description string   `json:"description"`
	CheckType   string   `json:"check_type"`
	Values      []string `json:"values,omitempty"`
	Enabled     bool     `json:"enabled"`
}

type ValidationResult struct {
	Valid       bool         `json:"valid"`
	Errors      []string     `json:"errors,omitempty"`
	Warnings    []string     `json:"warnings,omitempty"`
	RuleResults []RuleResult `json:"rule_results"`
	PackName    string       `json:"pack_name"`
}

type RuleResult struct {
	RuleID  string `json:"rule_id"`
	Status  string `json:"status"`
	Message string `json:"message,omitempty"`
}

func LoadPolicyPack(path string) (*PolicyPack, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read policy pack: %w", err)
	}

	var pack PolicyPack
	if err := json.Unmarshal(data, &pack); err != nil {
		return nil, fmt.Errorf("decode policy pack: %w", err)
	}
	return &pack, nil
}

func ValidatePolicyPack(pack *PolicyPack) (*ValidationResult, error) {
	if pack == nil {
		return nil, fmt.Errorf("policy pack is nil")
	}

	result := &ValidationResult{
		Valid:       true,
		Errors:      make([]string, 0),
		Warnings:    make([]string, 0),
		RuleResults: make([]RuleResult, 0),
		PackName:    pack.Name,
	}

	if strings.TrimSpace(pack.Name) == "" {
		result.Errors = append(result.Errors, "policy pack name is required")
		result.Valid = false
	}

	if strings.TrimSpace(pack.Version) == "" {
		result.Errors = append(result.Errors, "policy pack version is required")
		result.Valid = false
	}

	validProfiles := map[string]bool{"strict": true, "standard": true, "permissive": true}
	if !validProfiles[pack.Profile] {
		result.Errors = append(result.Errors, fmt.Sprintf("invalid profile %q; must be strict, standard, or permissive", pack.Profile))
		result.Valid = false
	}

	if len(pack.Rules) == 0 {
		result.Warnings = append(result.Warnings, "policy pack has no rules defined")
	}

	validCategories := map[string]bool{
		"commands": true, "tools": true, "network": true,
		"paths": true, "memory": true, "updates": true,
	}
	validSeverities := map[string]bool{"critical": true, "high": true, "medium": true, "low": true, "info": true}
	validCheckTypes := map[string]bool{
		"deny_list": true, "allow_list": true, "max_value": true,
		"must_exist": true, "must_not_exist": true, "pattern": true,
	}

	ruleIDs := make(map[string]bool, len(pack.Rules))
	for i, rule := range pack.Rules {
		if strings.TrimSpace(rule.ID) == "" {
			result.Errors = append(result.Errors, fmt.Sprintf("rules[%d].id is required", i))
			result.Valid = false
			continue
		}
		if ruleIDs[rule.ID] {
			result.Errors = append(result.Errors, fmt.Sprintf("duplicate rule id: %s", rule.ID))
			result.Valid = false
		}
		ruleIDs[rule.ID] = true

		if !validCategories[rule.Category] {
			result.Errors = append(result.Errors, fmt.Sprintf("rule %s has invalid category %q", rule.ID, rule.Category))
			result.Valid = false
		}
		if !validSeverities[rule.Severity] {
			result.Warnings = append(result.Warnings, fmt.Sprintf("rule %s has non-standard severity %q", rule.ID, rule.Severity))
		}
		if !validCheckTypes[rule.CheckType] {
			result.Errors = append(result.Errors, fmt.Sprintf("rule %s has invalid check_type %q", rule.ID, rule.CheckType))
			result.Valid = false
		}

		result.RuleResults = append(result.RuleResults, RuleResult{
			RuleID:  rule.ID,
			Status:  "validated",
			Message: "ok",
		})
	}

	return result, nil
}

func WritePolicyPack(path string, pack *PolicyPack) error {
	if pack == nil {
		return fmt.Errorf("policy pack is nil")
	}

	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("create directory: %w", err)
	}

	payload, err := json.MarshalIndent(pack, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal policy pack: %w", err)
	}

	return os.WriteFile(path, payload, 0o644)
}

func ValidatePolicyPackFile(path string) (*ValidationResult, error) {
	pack, err := LoadPolicyPack(path)
	if err != nil {
		return nil, err
	}
	return ValidatePolicyPack(pack)
}
