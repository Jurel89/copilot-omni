package release

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
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
	return m.addDirRecursive(name, srcDir, name)
}

func (m *Manifest) addDirRecursive(name, srcDir, prefix string) error {
	entries, err := os.ReadDir(srcDir)
	if err != nil {
		return fmt.Errorf("read directory %s: %w", name, err)
	}

	for _, entry := range entries {
		fullPath := filepath.Join(srcDir, entry.Name())
		relPath := filepath.Join(prefix, entry.Name())

		if entry.IsDir() {
			if err := m.addDirRecursive(name, fullPath, relPath); err != nil {
				return err
			}
			continue
		}

		checksum, err := FileChecksum(fullPath)
		if err != nil {
			continue
		}
		m.Components = append(m.Components, Component{
			Name:       fmt.Sprintf("%s/%s", name, entry.Name()),
			Path:       relPath,
			Type:       "file",
			Checksum:   checksum,
			sourcePath: fullPath,
		})
		m.Checksums[relPath] = checksum
		m.SBOM = append(m.SBOM, SBOMEntry{
			Name: filepath.Base(fullPath),
			Type: "plugin-file",
			Hash: checksum,
		})
	}
	return nil
}

func (m *Manifest) AddExtraFile(name, srcPath, bundleRelPath string) error {
	checksum, err := FileChecksum(srcPath)
	if err != nil {
		return fmt.Errorf("checksum %s: %w", name, err)
	}
	m.Components = append(m.Components, Component{
		Name:       name,
		Path:       bundleRelPath,
		Type:       "file",
		Checksum:   checksum,
		sourcePath: srcPath,
	})
	m.Checksums[bundleRelPath] = checksum
	m.SBOM = append(m.SBOM, SBOMEntry{
		Name: name,
		Type: "metadata",
		Hash: checksum,
	})
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

	sbomPayload, err := json.MarshalIndent(m.SBOM, "", "  ")
	if err != nil {
		return "", fmt.Errorf("marshal SBOM: %w", err)
	}
	sbomPath := filepath.Join(outputDir, "sbom.json")
	if err := os.WriteFile(sbomPath, sbomPayload, 0o644); err != nil {
		return "", fmt.Errorf("write SBOM: %w", err)
	}
	sbomChecksum, err := FileChecksum(sbomPath)
	if err != nil {
		return "", fmt.Errorf("checksum SBOM: %w", err)
	}

	checksumsPath := filepath.Join(outputDir, "checksums.txt")
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("%s  %s\n", manifestChecksum, "release-manifest.json"))
	sb.WriteString(fmt.Sprintf("%s  %s\n", sbomChecksum, "sbom.json"))
	for relPath, checksum := range m.Checksums {
		sb.WriteString(fmt.Sprintf("%s  %s\n", checksum, relPath))
	}
	if err := os.WriteFile(checksumsPath, []byte(sb.String()), 0o644); err != nil {
		return "", fmt.Errorf("write checksums: %w", err)
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
	bundleErrors := make([]string, 0)

	checksumsPath := filepath.Join(bundleDir, "checksums.txt")
	checksumsData, err := os.ReadFile(checksumsPath)
	if err != nil {
		return warnings, fmt.Errorf("checksums.txt missing: %w", err)
	}

	checksumsMap := make(map[string]string)
	for _, line := range strings.Split(string(checksumsData), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		parts := strings.SplitN(line, "  ", 2)
		if len(parts) == 2 {
			checksumsMap[parts[1]] = parts[0]
		}
	}

	manifest, err := ReadManifest(bundleDir)
	if err != nil {
		return warnings, fmt.Errorf("read manifest: %w", err)
	}

	if strings.TrimSpace(manifest.Product) == "" {
		bundleErrors = append(bundleErrors, "manifest product is empty")
	}
	if strings.TrimSpace(manifest.ReleaseTag) == "" {
		bundleErrors = append(bundleErrors, "manifest release_tag is empty")
	}
	if strings.TrimSpace(manifest.BuildDate) == "" {
		warnings = append(warnings, "manifest build_date is empty")
	}
	if len(manifest.Components) == 0 {
		bundleErrors = append(bundleErrors, "manifest has no components")
	}

	sbomPath := filepath.Join(bundleDir, "sbom.json")
	if _, err := os.Stat(sbomPath); err != nil {
		bundleErrors = append(bundleErrors, "sbom.json missing from bundle")
	}

	if manifest.Provenance.Signature != "" {
		storedSig := manifest.Provenance.Signature
		if strings.HasPrefix(storedSig, "sha256-fingerprint:") {
			expected := strings.TrimPrefix(storedSig, "sha256-fingerprint:")
			fingerprintChecksums := make(map[string]string)
			for k, v := range checksumsMap {
				if k == "release-manifest.json" {
					continue
				}
				fingerprintChecksums[k] = v
			}
			fingerprint := computeFingerprintFromChecksums(fingerprintChecksums)
			if fingerprint != expected {
				bundleErrors = append(bundleErrors, "provenance signature fingerprint mismatch: manifest may have been tampered with")
			}
		}
	}

	for _, comp := range manifest.Components {
		if _, exists := checksumsMap[comp.Path]; !exists {
			bundleErrors = append(bundleErrors, fmt.Sprintf("component %s (%s) not covered by checksums.txt", comp.Name, comp.Path))
		}
	}

	for _, comp := range manifest.Components {
		compPath := filepath.Join(bundleDir, comp.Path)
		if _, err := os.Stat(compPath); err != nil {
			bundleErrors = append(bundleErrors, fmt.Sprintf("component %s file missing: %s", comp.Name, comp.Path))
			continue
		}
		actualChecksum, err := FileChecksum(compPath)
		if err != nil {
			bundleErrors = append(bundleErrors, fmt.Sprintf("component %s checksum failed: %v", comp.Name, err))
			continue
		}
		if actualChecksum != comp.Checksum {
			bundleErrors = append(bundleErrors, fmt.Sprintf("component %s checksum mismatch: expected %s got %s", comp.Name, comp.Checksum, actualChecksum))
		}
	}

	if len(bundleErrors) > 0 {
		return warnings, fmt.Errorf("bundle validation failed: %s", strings.Join(bundleErrors, "; "))
	}

	for fileName, expectedHash := range checksumsMap {
		filePath := filepath.Join(bundleDir, fileName)
		actualHash, err := FileChecksum(filePath)
		if err != nil {
			bundleErrors = append(bundleErrors, fmt.Sprintf("checksums.txt entry %s: file not found", fileName))
			continue
		}
		if actualHash != expectedHash {
			bundleErrors = append(bundleErrors, fmt.Sprintf("checksums.txt entry %s: hash mismatch expected %s got %s", fileName, expectedHash, actualHash))
		}
	}

	if len(bundleErrors) > 0 {
		return warnings, fmt.Errorf("bundle validation failed: %s", strings.Join(bundleErrors, "; "))
	}

	return warnings, nil
}

func computeComponentFingerprint(m *Manifest) string {
	h := sha256.New()
	for _, comp := range m.Components {
		h.Write([]byte(comp.Name))
		h.Write([]byte(comp.Checksum))
	}
	return hex.EncodeToString(h.Sum(nil))
}

func computeFingerprintFromChecksums(checksumsMap map[string]string) string {
	keys := make([]string, 0, len(checksumsMap))
	for k := range checksumsMap {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	h := sha256.New()
	for _, k := range keys {
		h.Write([]byte(k))
		h.Write([]byte(checksumsMap[k]))
	}
	return hex.EncodeToString(h.Sum(nil))
}

func RegenerateChecksums(outputDir string) ([]byte, error) {
	manifestPath := filepath.Join(outputDir, "release-manifest.json")
	manifestChecksum, err := FileChecksum(manifestPath)
	if err != nil {
		return nil, err
	}
	sbomChecksum, err := FileChecksum(filepath.Join(outputDir, "sbom.json"))
	if err != nil {
		sbomChecksum = ""
	}

	manifest, err := ReadManifest(outputDir)
	if err != nil {
		return nil, err
	}

	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("%s  %s\n", manifestChecksum, "release-manifest.json"))
	if sbomChecksum != "" {
		sb.WriteString(fmt.Sprintf("%s  %s\n", sbomChecksum, "sbom.json"))
	}
	for relPath, checksum := range manifest.Checksums {
		sb.WriteString(fmt.Sprintf("%s  %s\n", checksum, relPath))
	}
	return []byte(sb.String()), nil
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
