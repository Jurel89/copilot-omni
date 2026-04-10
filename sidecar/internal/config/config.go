package config

import "encoding/json"

type Config struct {
	Version string        `json:"version"`
	Profile string        `json:"profile,omitempty"`
	Policy  PolicyConfig  `json:"policy"`
	Memory  MemoryConfig  `json:"memory"`
	Sidecar SidecarConfig `json:"sidecar"`

	versionSet bool
	profileSet bool
}

type PolicyConfig struct {
	StrictMode        bool     `json:"strict_mode"`
	ProtectedPaths    []string `json:"protected_paths"`
	DeniedCommands    []string `json:"denied_commands"`
	MaxAutopilotTurns int      `json:"max_autopilot_turns"`

	strictModeSet        bool
	protectedPathsSet    bool
	deniedCommandsSet    bool
	maxAutopilotTurnsSet bool
}

type MemoryConfig struct {
	Enabled   bool   `json:"enabled"`
	DBPath    string `json:"db_path,omitempty"`
	MaxSizeMB int    `json:"max_size_mb"`

	enabledSet   bool
	dbPathSet    bool
	maxSizeMBSet bool
}

type SidecarConfig struct {
	LogPath string `json:"log_path,omitempty"`
	Debug   bool   `json:"debug"`

	logPathSet bool
	debugSet   bool
}

type configJSON struct {
	Version *string            `json:"version"`
	Profile *string            `json:"profile"`
	Policy  *policyConfigJSON  `json:"policy"`
	Memory  *memoryConfigJSON  `json:"memory"`
	Sidecar *sidecarConfigJSON `json:"sidecar"`
}

type policyConfigJSON struct {
	StrictMode        *bool     `json:"strict_mode"`
	ProtectedPaths    *[]string `json:"protected_paths"`
	DeniedCommands    *[]string `json:"denied_commands"`
	MaxAutopilotTurns *int      `json:"max_autopilot_turns"`
}

type memoryConfigJSON struct {
	Enabled   *bool   `json:"enabled"`
	DBPath    *string `json:"db_path"`
	MaxSizeMB *int    `json:"max_size_mb"`
}

type sidecarConfigJSON struct {
	LogPath *string `json:"log_path"`
	Debug   *bool   `json:"debug"`
}

func (c *Config) UnmarshalJSON(data []byte) error {
	var payload configJSON
	if err := json.Unmarshal(data, &payload); err != nil {
		return err
	}

	*c = Config{}

	if payload.Version != nil {
		c.Version = *payload.Version
		c.versionSet = true
	}

	if payload.Profile != nil {
		c.Profile = *payload.Profile
		c.profileSet = true
	}

	if payload.Policy != nil {
		payload.Policy.apply(&c.Policy)
	}

	if payload.Memory != nil {
		payload.Memory.apply(&c.Memory)
	}

	if payload.Sidecar != nil {
		payload.Sidecar.apply(&c.Sidecar)
	}

	return nil
}

func (payload *policyConfigJSON) apply(target *PolicyConfig) {
	if payload.StrictMode != nil {
		target.StrictMode = *payload.StrictMode
		target.strictModeSet = true
	}

	if payload.ProtectedPaths != nil {
		target.ProtectedPaths = append([]string(nil), (*payload.ProtectedPaths)...)
		target.protectedPathsSet = true
	}

	if payload.DeniedCommands != nil {
		target.DeniedCommands = append([]string(nil), (*payload.DeniedCommands)...)
		target.deniedCommandsSet = true
	}

	if payload.MaxAutopilotTurns != nil {
		target.MaxAutopilotTurns = *payload.MaxAutopilotTurns
		target.maxAutopilotTurnsSet = true
	}
}

func (payload *memoryConfigJSON) apply(target *MemoryConfig) {
	if payload.Enabled != nil {
		target.Enabled = *payload.Enabled
		target.enabledSet = true
	}

	if payload.DBPath != nil {
		target.DBPath = *payload.DBPath
		target.dbPathSet = true
	}

	if payload.MaxSizeMB != nil {
		target.MaxSizeMB = *payload.MaxSizeMB
		target.maxSizeMBSet = true
	}
}

func (payload *sidecarConfigJSON) apply(target *SidecarConfig) {
	if payload.LogPath != nil {
		target.LogPath = *payload.LogPath
		target.logPathSet = true
	}

	if payload.Debug != nil {
		target.Debug = *payload.Debug
		target.debugSet = true
	}
}
