package release

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestAddExtraFileNormalizesManifestPaths(t *testing.T) {
	sourceDir := t.TempDir()
	sourceFile := writeTestFile(t, sourceDir, "strict.json", `{\n  "mode": "strict"\n}`)
	addRequiredBundleBinaries(t, sourceDir)

	manifest := NewManifest("v1.0.0", "windows/amd64", "")
	addBinaryComponents(t, manifest, sourceDir, "windows/amd64")
	if err := manifest.AddExtraFile("policy", sourceFile, `policies\strict.json`); err != nil {
		t.Fatalf("AddExtraFile() error = %v", err)
	}

	if !hasComponentPath(manifest.Components, "policies/strict.json") {
		t.Fatalf("expected policies/strict.json component path to be present")
	}
	if _, exists := manifest.Checksums["policies/strict.json"]; !exists {
		t.Fatalf("expected normalized checksum entry for policies/strict.json")
	}

	bundleDir := t.TempDir()
	if _, err := manifest.WriteBundle(bundleDir); err != nil {
		t.Fatalf("WriteBundle() error = %v", err)
	}
	if _, err := os.Stat(filepath.Join(bundleDir, "policies", "strict.json")); err != nil {
		t.Fatalf("expected normalized bundle file: %v", err)
	}

	persisted, err := ReadManifest(bundleDir)
	if err != nil {
		t.Fatalf("ReadManifest() error = %v", err)
	}
	if !hasComponentPath(persisted.Components, "policies/strict.json") {
		t.Fatalf("expected persisted policies/strict.json component path to be present")
	}

	if _, err := ValidateBundle(bundleDir); err != nil {
		t.Fatalf("ValidateBundle() error = %v", err)
	}
}

func TestWriteBundleIncludesTemplatesDirectory(t *testing.T) {
	assetRoot := t.TempDir()
	templatesDir := filepath.Join(assetRoot, "templates")
	writeTestFile(t, templatesDir, filepath.Join("workflow", "init", "prompt.md"), "# init\n")
	addRequiredBundleBinaries(t, assetRoot)

	manifest := NewManifest("v1.0.0", "linux/amd64", "")
	addBinaryComponents(t, manifest, assetRoot, "linux/amd64")
	if err := manifest.AddDirectoryComponent("templates", templatesDir); err != nil {
		t.Fatalf("AddDirectoryComponent() error = %v", err)
	}

	if !hasComponentPath(manifest.Components, "templates/workflow/init/prompt.md") {
		t.Fatalf("expected templates component path to use forward slashes")
	}

	bundleDir := t.TempDir()
	if _, err := manifest.WriteBundle(bundleDir); err != nil {
		t.Fatalf("WriteBundle() error = %v", err)
	}
	if _, err := os.Stat(filepath.Join(bundleDir, "templates", "workflow", "init", "prompt.md")); err != nil {
		t.Fatalf("expected templates asset in bundle: %v", err)
	}

	if _, err := ValidateBundle(bundleDir); err != nil {
		t.Fatalf("ValidateBundle() error = %v", err)
	}
}

func TestValidateBundleRejectsBackslashTraversalPath(t *testing.T) {
	bundleDir := t.TempDir()
	manifestPath := filepath.Join(bundleDir, "release-manifest.json")
	sbomPath := filepath.Join(bundleDir, "sbom.json")

	manifest := &Manifest{
		Version:    "1",
		Product:    "copilot-omni",
		ReleaseTag: "v1.0.0",
		BuildDate:  time.Now().UTC().Format(time.RFC3339),
		Platform:   "windows/amd64",
		Components: []Component{{
			Name:     "escape",
			Path:     `..\escape.txt`,
			Type:     "file",
			Checksum: "deadbeef",
		}},
		Checksums: map[string]string{},
		Provenance: Provenance{
			Builder: "test",
		},
		SBOM: []SBOMEntry{},
	}
	writeJSONFile(t, manifestPath, manifest)
	writeJSONFile(t, sbomPath, []SBOMEntry{})

	manifestChecksum, err := FileChecksum(manifestPath)
	if err != nil {
		t.Fatalf("FileChecksum(manifest) error = %v", err)
	}
	sbomChecksum, err := FileChecksum(sbomPath)
	if err != nil {
		t.Fatalf("FileChecksum(sbom) error = %v", err)
	}

	checksums := strings.Join([]string{
		manifestChecksum + "  release-manifest.json",
		sbomChecksum + "  sbom.json",
		"deadbeef  ..\\escape.txt",
		"",
	}, "\n")
	if err := os.WriteFile(filepath.Join(bundleDir, "checksums.txt"), []byte(checksums), 0o644); err != nil {
		t.Fatalf("WriteFile(checksums.txt) error = %v", err)
	}

	_, err = ValidateBundle(bundleDir)
	if err == nil {
		t.Fatal("ValidateBundle() error = nil, want traversal rejection")
	}
	if !strings.Contains(err.Error(), "path escapes bundle directory") {
		t.Fatalf("ValidateBundle() error = %v, want traversal rejection", err)
	}
}

func TestValidateBundleRejectsTamperedFile(t *testing.T) {
	sourceDir := t.TempDir()
	sourceFile := writeTestFile(t, sourceDir, "plugin.json", `{}`)
	addRequiredBundleBinaries(t, sourceDir)

	manifest := NewManifest("v1.0.0", "linux/amd64", "")
	addBinaryComponents(t, manifest, sourceDir, "linux/amd64")
	if err := manifest.AddExtraFile("plugin", sourceFile, "plugin/plugin.json"); err != nil {
		t.Fatalf("AddExtraFile() error = %v", err)
	}

	bundleDir := t.TempDir()
	if _, err := manifest.WriteBundle(bundleDir); err != nil {
		t.Fatalf("WriteBundle() error = %v", err)
	}

	tamperedPath := filepath.Join(bundleDir, "plugin", "plugin.json")
	if err := os.WriteFile(tamperedPath, []byte(`{"tampered":true}`), 0o644); err != nil {
		t.Fatalf("WriteFile(tampered component) error = %v", err)
	}

	_, err := ValidateBundle(bundleDir)
	if err == nil {
		t.Fatal("ValidateBundle() error = nil, want checksum failure")
	}
	if !strings.Contains(err.Error(), "checksum mismatch") && !strings.Contains(err.Error(), "hash mismatch") {
		t.Fatalf("ValidateBundle() error = %v, want checksum failure", err)
	}
}

func TestFindBundleBinaryUsesPlatformSpecificNames(t *testing.T) {
	binariesDir := t.TempDir()
	windowsBinary := writeTestFile(t, binariesDir, "omni.exe", "windows")
	linuxBinary := writeTestFile(t, binariesDir, "omni-sidecar", "linux")

	if got, ok := FindBundleBinary(binariesDir, "omni", "windows/amd64"); !ok || got != windowsBinary {
		t.Fatalf("FindBundleBinary() for windows = (%q, %t), want (%q, true)", got, ok, windowsBinary)
	}
	if got, ok := FindBundleBinary(binariesDir, "omni-sidecar", "linux/amd64"); !ok || got != linuxBinary {
		t.Fatalf("FindBundleBinary() for linux = (%q, %t), want (%q, true)", got, ok, linuxBinary)
	}
}

func hasComponentPath(components []Component, wantPath string) bool {
	for _, component := range components {
		if component.Path == wantPath {
			return true
		}
	}
	return false
}

func writeJSONFile(t *testing.T, filePath string, value any) {
	t.Helper()

	payload, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		t.Fatalf("json.MarshalIndent() error = %v", err)
	}
	if err := os.WriteFile(filePath, payload, 0o644); err != nil {
		t.Fatalf("WriteFile(%s) error = %v", filePath, err)
	}
}

func writeTestFile(t *testing.T, rootDir, relativePath, content string) string {
	t.Helper()

	filePath := filepath.Join(rootDir, relativePath)
	if err := os.MkdirAll(filepath.Dir(filePath), 0o755); err != nil {
		t.Fatalf("MkdirAll(%s) error = %v", filepath.Dir(filePath), err)
	}
	if err := os.WriteFile(filePath, []byte(content), 0o644); err != nil {
		t.Fatalf("WriteFile(%s) error = %v", filePath, err)
	}
	return filePath
}

func addRequiredBundleBinaries(t *testing.T, rootDir string) {
	t.Helper()
	writeTestFile(t, rootDir, "omni-sidecar", "sidecar")
	writeTestFile(t, rootDir, "omni", "wrapper")
}

func addBinaryComponents(t *testing.T, manifest *Manifest, rootDir string, platform string) {
	t.Helper()
	if err := manifest.AddComponent("omni-sidecar", filepath.Join(rootDir, "omni-sidecar"), "binary", platform); err != nil {
		t.Fatalf("AddComponent(omni-sidecar) error = %v", err)
	}
	if err := manifest.AddComponent("omni-wrapper", filepath.Join(rootDir, "omni"), "binary", platform); err != nil {
		t.Fatalf("AddComponent(omni-wrapper) error = %v", err)
	}
}
