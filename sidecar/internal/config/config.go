package config

import "encoding/json"

type Config struct {
	Version    string           `json:"version"`
	Profile    string           `json:"profile,omitempty"`
	Policy     PolicyConfig     `json:"policy"`
	Memory     MemoryConfig     `json:"memory"`
	Sidecar    SidecarConfig    `json:"sidecar"`
	Research   ResearchConfig   `json:"research"`
	Enterprise EnterpriseConfig `json:"enterprise"`

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
	Enabled       bool   `json:"enabled"`
	DBPath        string `json:"db_path,omitempty"`
	MaxSizeMB     int    `json:"max_size_mb"`
	RetentionDays int    `json:"retention_days"`
	AutoIngest    bool   `json:"auto_ingest"`

	enabledSet       bool
	dbPathSet        bool
	maxSizeMBSet     bool
	retentionDaysSet bool
	autoIngestSet    bool
}

type SidecarConfig struct {
	LogPath string `json:"log_path,omitempty"`
	Debug   bool   `json:"debug"`

	logPathSet bool
	debugSet   bool
}

type ResearchConfig struct {
	MaxSubtasks   int  `json:"max_subtasks"`
	ParallelRead  bool `json:"parallel_read"`
	ParallelWrite bool `json:"parallel_write"`

	maxSubtasksSet   bool
	parallelReadSet  bool
	parallelWriteSet bool
}

type EnterpriseConfig struct {
	OfflineMode    bool `json:"offline_mode"`
	AuditRetention int  `json:"audit_retention_days"`
	SigningEnabled bool `json:"signing_enabled"`

	offlineModeSet    bool
	auditRetentionSet bool
	signingEnabledSet bool
}

type configJSON struct {
	Version    *string               `json:"version"`
	Profile    *string               `json:"profile"`
	Policy     *policyConfigJSON     `json:"policy"`
	Memory     *memoryConfigJSON     `json:"memory"`
	Sidecar    *sidecarConfigJSON    `json:"sidecar"`
	Research   *researchConfigJSON   `json:"research"`
	Enterprise *enterpriseConfigJSON `json:"enterprise"`
}

type policyConfigJSON struct {
	StrictMode        *bool     `json:"strict_mode"`
	ProtectedPaths    *[]string `json:"protected_paths"`
	DeniedCommands    *[]string `json:"denied_commands"`
	MaxAutopilotTurns *int      `json:"max_autopilot_turns"`
}

type memoryConfigJSON struct {
	Enabled       *bool   `json:"enabled"`
	DBPath        *string `json:"db_path"`
	MaxSizeMB     *int    `json:"max_size_mb"`
	RetentionDays *int    `json:"retention_days"`
	AutoIngest    *bool   `json:"auto_ingest"`
}

type sidecarConfigJSON struct {
	LogPath *string `json:"log_path"`
	Debug   *bool   `json:"debug"`
}

type researchConfigJSON struct {
	MaxSubtasks   *int  `json:"max_subtasks"`
	ParallelRead  *bool `json:"parallel_read"`
	ParallelWrite *bool `json:"parallel_write"`
}

type enterpriseConfigJSON struct {
	OfflineMode    *bool `json:"offline_mode"`
	AuditRetention *int  `json:"audit_retention_days"`
	SigningEnabled *bool `json:"signing_enabled"`
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

	if payload.Research != nil {
		payload.Research.apply(&c.Research)
	}

	if payload.Enterprise != nil {
		payload.Enterprise.apply(&c.Enterprise)
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

	if payload.RetentionDays != nil {
		target.RetentionDays = *payload.RetentionDays
		target.retentionDaysSet = true
	}

	if payload.AutoIngest != nil {
		target.AutoIngest = *payload.AutoIngest
		target.autoIngestSet = true
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

func (payload *researchConfigJSON) apply(target *ResearchConfig) {
	if payload.MaxSubtasks != nil {
		target.MaxSubtasks = *payload.MaxSubtasks
		target.maxSubtasksSet = true
	}

	if payload.ParallelRead != nil {
		target.ParallelRead = *payload.ParallelRead
		target.parallelReadSet = true
	}

	if payload.ParallelWrite != nil {
		target.ParallelWrite = *payload.ParallelWrite
		target.parallelWriteSet = true
	}
}

func (payload *enterpriseConfigJSON) apply(target *EnterpriseConfig) {
	if payload.OfflineMode != nil {
		target.OfflineMode = *payload.OfflineMode
		target.offlineModeSet = true
	}

	if payload.AuditRetention != nil {
		target.AuditRetention = *payload.AuditRetention
		target.auditRetentionSet = true
	}

	if payload.SigningEnabled != nil {
		target.SigningEnabled = *payload.SigningEnabled
		target.signingEnabledSet = true
	}
}
