package release

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type Manifest struct {
	Version    string            `json:"version"`
	Product    string            `json:"product"`
	ReleaseTag string            `json:"release_tag"`
	BuildDate  string            `json:"build_date"`
	CommitHash string            `json:"commit_hash,omitempty"`
	Platform   string            `json:"platform"`
	Components []Component       `json:"components"`
	Checksums  map[string]string `json:"checksums"`
	Provenance Provenance        `json:"provenance"`
	SBOM       []SBOMEntry       `json:"sbom"`
}

type Component struct {
	Name     string `json:"name"`
	Path     string `json:"path"`
	Type     string `json:"type"`
	Arch     string `json:"arch,omitempty"`
	Checksum string `json:"checksum"`

	sourcePath string
}

type Provenance struct {
	Builder    string `json:"builder"`
	Signature  string `json:"signature,omitempty"`
	Workflow   string `json:"workflow,omitempty"`
	Repository string `json:"repository,omitempty"`
}

type SBOMEntry struct {
	Name    string `json:"name"`
	Version string `json:"version"`
	Type    string `json:"type"`
	Hash    string `json:"hash,omitempty"`
}

func NewManifest(releaseTag, platform, commitHash string) *Manifest {
	return &Manifest{
		Version:    "1",
		Product:    "copilot-omni",
		ReleaseTag: releaseTag,
		BuildDate:  time.Now().UTC().Format(time.RFC3339),
		CommitHash: commitHash,
		Platform:   platform,
		Components: make([]Component, 0),
		Checksums:  make(map[string]string),
		SBOM:       make([]SBOMEntry, 0),
		Provenance: Provenance{
			Builder: "copilot-omni-release",
		},
	}
}

func (m *Manifest) AddComponent(name, srcPath, componentType, arch string) error {
	checksum, err := FileChecksum(srcPath)
	if err != nil {
		return fmt.Errorf("checksum %s: %w", name, err)
	}

	relPath := filepath.Base(srcPath)
	m.Components = append(m.Components, Component{
		Name:       name,
		Path:       relPath,
		Type:       componentType,
		Arch:       arch,
		Checksum:   checksum,
		sourcePath: srcPath,
	})
	m.Checksums[relPath] = checksum
	m.SBOM = append(m.SBOM, SBOMEntry{
		Name:    name,
		Version: "",
		Type:    componentType,
		Hash:    checksum,
	})
	return nil
}

func (m *Manifest) AddDirectoryComponent(name, srcDir string) error {
	entries, err := os.ReadDir(srcDir)
	if err != nil {
		return fmt.Errorf("read directory %s: %w", name, err)
	}

	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		filePath := filepath.Join(srcDir, entry.Name())
		checksum, err := FileChecksum(filePath)
		if err != nil {
			continue
		}
		relPath := filepath.Join("plugin", entry.Name())
		m.Components = append(m.Components, Component{
			Name:       fmt.Sprintf("%s/%s", name, entry.Name()),
			Path:       relPath,
			Type:       "file",
			Checksum:   checksum,
			sourcePath: filePath,
		})
		m.Checksums[relPath] = checksum
		m.SBOM = append(m.SBOM, SBOMEntry{
			Name: entry.Name(),
			Type: "plugin-file",
			Hash: checksum,
		})
	}
	return nil
}

func (m *Manifest) WriteBundle(outputDir string) (string, error) {
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		return "", fmt.Errorf("create bundle directory: %w", err)
	}

	for _, comp := range m.Components {
		if comp.sourcePath == "" {
			continue
		}
		dest := filepath.Join(outputDir, comp.Path)
		if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
			return "", fmt.Errorf("create component directory for %s: %w", comp.Name, err)
		}
		srcData, err := os.ReadFile(comp.sourcePath)
		if err != nil {
			return "", fmt.Errorf("read component %s: %w", comp.Name, err)
		}
		if err := os.WriteFile(dest, srcData, 0o755); err != nil {
			return "", fmt.Errorf("write component %s: %w", comp.Name, err)
		}
	}

	payload, err := json.MarshalIndent(m, "", "  ")
	if err != nil {
		return "", fmt.Errorf("marshal manifest: %w", err)
	}

	manifestPath := filepath.Join(outputDir, "release-manifest.json")
	if err := os.WriteFile(manifestPath, payload, 0o644); err != nil {
		return "", fmt.Errorf("write manifest: %w", err)
	}

	manifestChecksum, err := FileChecksum(manifestPath)
	if err != nil {
		return "", fmt.Errorf("checksum manifest: %w", err)
	}

	checksumsPath := filepath.Join(outputDir, "checksums.txt")
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("%s  %s\n", manifestChecksum, "release-manifest.json"))
	for relPath, checksum := range m.Checksums {
		sb.WriteString(fmt.Sprintf("%s  %s\n", checksum, relPath))
	}
	if err := os.WriteFile(checksumsPath, []byte(sb.String()), 0o644); err != nil {
		return "", fmt.Errorf("write checksums: %w", err)
	}

	sbomPayload, err := json.MarshalIndent(m.SBOM, "", "  ")
	if err != nil {
		return "", fmt.Errorf("marshal SBOM: %w", err)
	}
	sbomPath := filepath.Join(outputDir, "sbom.json")
	if err := os.WriteFile(sbomPath, sbomPayload, 0o644); err != nil {
		return "", fmt.Errorf("write SBOM: %w", err)
	}

	return manifestPath, nil
}

func ReadManifest(bundleDir string) (*Manifest, error) {
	path := filepath.Join(bundleDir, "release-manifest.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read manifest: %w", err)
	}

	var manifest Manifest
	if err := json.Unmarshal(data, &manifest); err != nil {
		return nil, fmt.Errorf("decode manifest: %w", err)
	}
	return &manifest, nil
}

func ValidateBundle(bundleDir string) ([]string, error) {
	warnings := make([]string, 0)
	errors := make([]string, 0)

	manifest, err := ReadManifest(bundleDir)
	if err != nil {
		return nil, fmt.Errorf("read manifest: %w", err)
	}

	if strings.TrimSpace(manifest.Product) == "" {
		errors = append(errors, "manifest product is empty")
	}
	if strings.TrimSpace(manifest.ReleaseTag) == "" {
		errors = append(errors, "manifest release_tag is empty")
	}
	if strings.TrimSpace(manifest.BuildDate) == "" {
		warnings = append(warnings, "manifest build_date is empty")
	}
	if len(manifest.Components) == 0 {
		errors = append(errors, "manifest has no components")
	}

	for _, comp := range manifest.Components {
		compPath := filepath.Join(bundleDir, comp.Path)
		if _, err := os.Stat(compPath); err != nil {
			errors = append(errors, fmt.Sprintf("component %s file missing: %s", comp.Name, comp.Path))
			continue
		}
		actualChecksum, err := FileChecksum(compPath)
		if err != nil {
			errors = append(errors, fmt.Sprintf("component %s checksum failed: %v", comp.Name, err))
			continue
		}
		if actualChecksum != comp.Checksum {
			errors = append(errors, fmt.Sprintf("component %s checksum mismatch: expected %s got %s", comp.Name, comp.Checksum, actualChecksum))
		}
	}

	if len(errors) > 0 {
		return warnings, fmt.Errorf("bundle validation failed: %s", strings.Join(errors, "; "))
	}

	return warnings, nil
}

func FileChecksum(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()

	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
