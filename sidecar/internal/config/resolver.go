package config

import (
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

const defaultProfileName = "standard"

// Phase 0 uses JSON config files instead of TOML so the sidecar can stay
// dependency-free while still exposing a structured, machine-readable format.

//go:embed profiles/*/config.json
var embeddedProfiles embed.FS

func Resolve(repoRoot string) (*Config, error) {
	defaultConfig := DefaultConfig()

	globalConfig, err := loadOptionalConfig(globalConfigPath())
	if err != nil {
		return nil, err
	}

	repoConfig, err := loadOptionalConfig(repoConfigPath(repoRoot))
	if err != nil {
		return nil, err
	}

	profileName := resolveProfileName(defaultConfig.Profile, globalConfig, repoConfig)
	profileConfig, err := loadProfile(profileName)
	if err != nil {
		return nil, err
	}

	resolved := Merge(defaultConfig, profileConfig)
	resolved = Merge(resolved, globalConfig)
	resolved = Merge(resolved, repoConfig)
	resolved = ApplyEnvVars(resolved)

	return resolved, nil
}

func DefaultConfig() *Config {
	return &Config{
		Version: "1",
		Profile: defaultProfileName,
		Policy: PolicyConfig{
			StrictMode:        false,
			ProtectedPaths:    []string{"src/"},
			DeniedCommands:    []string{"sudo", "rm -rf /", "mkfs", "dd"},
			MaxAutopilotTurns: 15,
		},
		Memory: MemoryConfig{
			Enabled:       true,
			MaxSizeMB:     200,
			RetentionDays: 90,
			AutoIngest:    true,
		},
		Sidecar: SidecarConfig{
			Debug: false,
		},
	}
}

func LoadFromFile(path string) (*Config, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config %s: %w", path, err)
	}

	var cfg Config
	if err := json.Unmarshal(content, &cfg); err != nil {
		return nil, fmt.Errorf("parse config %s: %w", path, err)
	}

	return &cfg, nil
}

func Merge(base, overlay *Config) *Config {
	if base == nil && overlay == nil {
		return &Config{}
	}

	if base == nil {
		copied := cloneConfig(overlay)
		return &copied
	}

	merged := cloneConfig(base)
	if overlay == nil {
		return &merged
	}

	if overlay.versionSet {
		merged.Version = overlay.Version
	}

	if overlay.profileSet {
		merged.Profile = overlay.Profile
	}

	if overlay.Policy.strictModeSet {
		merged.Policy.StrictMode = overlay.Policy.StrictMode
	}

	if overlay.Policy.protectedPathsSet {
		merged.Policy.ProtectedPaths = append([]string(nil), overlay.Policy.ProtectedPaths...)
	}

	if overlay.Policy.deniedCommandsSet {
		merged.Policy.DeniedCommands = append([]string(nil), overlay.Policy.DeniedCommands...)
	}

	if overlay.Policy.maxAutopilotTurnsSet {
		merged.Policy.MaxAutopilotTurns = overlay.Policy.MaxAutopilotTurns
	}

	if overlay.Memory.enabledSet {
		merged.Memory.Enabled = overlay.Memory.Enabled
	}

	if overlay.Memory.dbPathSet {
		merged.Memory.DBPath = overlay.Memory.DBPath
	}

	if overlay.Memory.maxSizeMBSet {
		merged.Memory.MaxSizeMB = overlay.Memory.MaxSizeMB
	}

	if overlay.Memory.retentionDaysSet {
		merged.Memory.RetentionDays = overlay.Memory.RetentionDays
	}

	if overlay.Memory.autoIngestSet {
		merged.Memory.AutoIngest = overlay.Memory.AutoIngest
	}

	if overlay.Sidecar.logPathSet {
		merged.Sidecar.LogPath = overlay.Sidecar.LogPath
	}

	if overlay.Sidecar.debugSet {
		merged.Sidecar.Debug = overlay.Sidecar.Debug
	}

	return &merged
}

func ApplyEnvVars(cfg *Config) *Config {
	resolved := cloneConfig(cfg)

	if profile := strings.TrimSpace(os.Getenv("COPILOT_OMNI_PROFILE")); profile != "" {
		resolved.Profile = profile
	}

	if strictValue, ok, err := parseEnvBool("COPILOT_OMNI_STRICT"); err == nil && ok {
		resolved.Policy.StrictMode = strictValue
	}

	if debugValue, ok, err := parseEnvBool("COPILOT_OMNI_DEBUG"); err == nil && ok {
		resolved.Sidecar.Debug = debugValue
	}

	return &resolved
}

func cloneConfig(cfg *Config) Config {
	if cfg == nil {
		return Config{}
	}

	cloned := *cfg
	cloned.Policy.ProtectedPaths = append([]string(nil), cfg.Policy.ProtectedPaths...)
	cloned.Policy.DeniedCommands = append([]string(nil), cfg.Policy.DeniedCommands...)
	return cloned
}

func resolveProfileName(defaultProfile string, globalConfig, repoConfig *Config) string {
	profileName := strings.TrimSpace(defaultProfile)

	if globalConfig != nil && globalConfig.profileSet && strings.TrimSpace(globalConfig.Profile) != "" {
		profileName = strings.TrimSpace(globalConfig.Profile)
	}

	if repoConfig != nil && repoConfig.profileSet && strings.TrimSpace(repoConfig.Profile) != "" {
		profileName = strings.TrimSpace(repoConfig.Profile)
	}

	if envProfile := strings.TrimSpace(os.Getenv("COPILOT_OMNI_PROFILE")); envProfile != "" {
		profileName = envProfile
	}

	if profileName == "" {
		return defaultProfileName
	}

	return profileName
}

func loadProfile(name string) (*Config, error) {
	if strings.TrimSpace(name) == "" {
		return nil, nil
	}

	profile, err := loadEmbeddedProfile(name)
	if err != nil {
		return nil, err
	}

	return profile, nil
}

func loadEmbeddedProfile(name string) (*Config, error) {
	path := filepath.ToSlash(filepath.Join("profiles", name, "config.json"))
	content, err := embeddedProfiles.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read embedded profile %s: %w", name, err)
	}

	var cfg Config
	if err := json.Unmarshal(content, &cfg); err != nil {
		return nil, fmt.Errorf("parse embedded profile %s: %w", name, err)
	}

	return &cfg, nil
}

func loadOptionalConfig(path string) (*Config, error) {
	if path == "" {
		return nil, nil
	}

	cfg, err := LoadFromFile(path)
	if err == nil {
		return cfg, nil
	}

	if errors.Is(err, os.ErrNotExist) {
		return nil, nil
	}

	return nil, err
}

func globalConfigPath() string {
	if xdgConfigHome := strings.TrimSpace(os.Getenv("XDG_CONFIG_HOME")); xdgConfigHome != "" {
		return filepath.Join(xdgConfigHome, "copilot-omni", "config.json")
	}

	homeDir, err := os.UserHomeDir()
	if err != nil || strings.TrimSpace(homeDir) == "" {
		return ""
	}

	return filepath.Join(homeDir, ".copilot-omni", "config.json")
}

func repoConfigPath(repoRoot string) string {
	repoRoot = strings.TrimSpace(repoRoot)
	if repoRoot == "" {
		return ""
	}

	return filepath.Join(repoRoot, ".omni", "config.json")
}

func parseEnvBool(key string) (bool, bool, error) {
	rawValue, ok := os.LookupEnv(key)
	if !ok || strings.TrimSpace(rawValue) == "" {
		return false, false, nil
	}

	parsed, err := strconv.ParseBool(strings.TrimSpace(rawValue))
	if err != nil {
		return false, true, fmt.Errorf("parse %s: %w", key, err)
	}

	return parsed, true, nil
}
