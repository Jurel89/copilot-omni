package support

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/Jurel89/copilot-omni/sidecar/internal/doctor"
)

type Manifest struct {
	Version        string              `json:"version"`
	BundleID       string              `json:"bundle_id"`
	GeneratedAt    string              `json:"generated_at"`
	RepoRoot       string              `json:"repo_root,omitempty"`
	RunID          string              `json:"run_id,omitempty"`
	Format         string              `json:"format"`
	Status         string              `json:"status"`
	RedactionLevel string              `json:"redaction_level"`
	SystemInfo     SystemInfo          `json:"system_info"`
	MemoryStore    MemoryStoreStats    `json:"memory_store"`
	Diagnostics    []doctor.Diagnostic `json:"diagnostics"`
	Items          []CollectedItem     `json:"items"`
	Errors         []string            `json:"errors,omitempty"`
	Checksum       string              `json:"checksum"`
}

func NewManifest(bundle *Bundle) (*Manifest, error) {
	manifest := &Manifest{
		Version:        bundle.Version,
		BundleID:       bundle.BundleID,
		GeneratedAt:    bundle.GeneratedAt.Format(time.RFC3339),
		RepoRoot:       bundle.RepoRoot,
		RunID:          bundle.RunID,
		Format:         bundle.Format,
		Status:         bundle.Status,
		RedactionLevel: string(bundle.RedactionLevel),
		SystemInfo:     bundle.SystemInfo,
		MemoryStore:    bundle.MemoryStore,
		Diagnostics:    append([]doctor.Diagnostic(nil), bundle.Diagnostics...),
		Items:          append([]CollectedItem(nil), bundle.Items...),
		Errors:         append([]string(nil), bundle.Errors...),
	}

	sort.Slice(manifest.Items, func(i, j int) bool { return manifest.Items[i].Path < manifest.Items[j].Path })
	checksum, err := manifest.computeChecksum()
	if err != nil {
		return nil, err
	}
	manifest.Checksum = checksum
	return manifest, nil
}

func (m *Manifest) JSON() ([]byte, error) {
	return json.MarshalIndent(m, "", "  ")
}

func (m *Manifest) computeChecksum() (string, error) {
	type manifestChecksum struct {
		Version        string              `json:"version"`
		BundleID       string              `json:"bundle_id"`
		GeneratedAt    string              `json:"generated_at"`
		RepoRoot       string              `json:"repo_root,omitempty"`
		RunID          string              `json:"run_id,omitempty"`
		Format         string              `json:"format"`
		Status         string              `json:"status"`
		RedactionLevel string              `json:"redaction_level"`
		SystemInfo     SystemInfo          `json:"system_info"`
		MemoryStore    MemoryStoreStats    `json:"memory_store"`
		Diagnostics    []doctor.Diagnostic `json:"diagnostics"`
		Items          []CollectedItem     `json:"items"`
		Errors         []string            `json:"errors,omitempty"`
	}

	payload, err := json.Marshal(manifestChecksum{
		Version:        m.Version,
		BundleID:       m.BundleID,
		GeneratedAt:    m.GeneratedAt,
		RepoRoot:       m.RepoRoot,
		RunID:          m.RunID,
		Format:         m.Format,
		Status:         m.Status,
		RedactionLevel: m.RedactionLevel,
		SystemInfo:     m.SystemInfo,
		MemoryStore:    m.MemoryStore,
		Diagnostics:    m.Diagnostics,
		Items:          m.Items,
		Errors:         m.Errors,
	})
	if err != nil {
		return "", fmt.Errorf("marshal manifest checksum payload: %w", err)
	}
	hash := sha256.Sum256(payload)
	return hex.EncodeToString(hash[:]), nil
}

func checksumBytes(data []byte) string {
	hash := sha256.Sum256(data)
	return hex.EncodeToString(hash[:])
}

func statusFromDiagnostics(diagnostics []doctor.Diagnostic) string {
	status := "healthy"
	for _, diagnostic := range diagnostics {
		switch strings.ToLower(strings.TrimSpace(diagnostic.Status)) {
		case "fail":
			return "unhealthy"
		case "warn":
			status = "degraded"
		}
	}
	return status
}
