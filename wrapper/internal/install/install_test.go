package install

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/Jurel89/copilot-omni/wrapper/internal/assets"
)

func TestInstallBundleRoundTripLayout(t *testing.T) {
	t.Parallel()

	testCases := []struct {
		name     string
		platform string
	}{
		{name: "linux", platform: "linux/amd64"},
		{name: "windows", platform: "windows/amd64"},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			t.Parallel()

			bundleDir := t.TempDir()
			bundle := writeValidBundle(t, bundleDir, testCase.platform)
			targetDir := t.TempDir()

			result, err := Install(Options{BundleDir: bundleDir, Target: targetDir})
			if err != nil {
				t.Fatalf("Install() error = %v", err)
			}

			assertInstalledFileContent(t, filepath.Join(targetDir, "bin", bundle.wrapperBinaryName), "wrapper-binary")
			assertInstalledMode(t, filepath.Join(targetDir, "bin", bundle.wrapperBinaryName), 0o111, true)
			assertInstalledFileContent(t, filepath.Join(targetDir, "bin", bundle.sidecarBinaryName), "sidecar-binary")
			assertInstalledMode(t, filepath.Join(targetDir, "bin", bundle.sidecarBinaryName), 0o111, true)

			shareDir := filepath.Join(targetDir, "share", shareDirName)
			assertInstalledFileContent(t, filepath.Join(shareDir, "plugin", "plugin.json"), `{"name":"copilot-omni"}`)
			assertInstalledMode(t, filepath.Join(shareDir, "plugin", "plugin.json"), 0o111, false)
			assertInstalledFileContent(t, filepath.Join(shareDir, "templates", "workflow", "init", "prompt.md"), "# init\n")
			assertInstalledFileContent(t, filepath.Join(shareDir, "policies", "standard.json"), `{"profile":"standard"}`)
			assertInstalledFileContent(t, filepath.Join(shareDir, "marketplace.json"), `{"plugins":[{"name":"copilot-omni"}]}`)
			assertInstalledFileContent(t, filepath.Join(shareDir, "scripts", "install-offline.sh"), "#!/bin/sh\n")
			assertInstalledMode(t, filepath.Join(shareDir, "scripts", "install-offline.sh"), 0o111, true)
			assertFileExists(t, filepath.Join(shareDir, manifestFileName))
			assertFileExists(t, filepath.Join(shareDir, checksumsFileName))
			assertFileExists(t, filepath.Join(shareDir, sbomFileName))

			location, err := assets.ResolveFromExecutable(filepath.Join(targetDir, "bin", bundle.wrapperBinaryName))
			if err != nil {
				t.Fatalf("assets.ResolveFromExecutable() error = %v", err)
			}
			if got, want := location.Mode, assets.ModeInstalled; got != want {
				t.Fatalf("location.Mode = %q, want %q", got, want)
			}
			if got, want := location.AssetRoot, result.ShareDir; got != want {
				t.Fatalf("location.AssetRoot = %q, want %q", got, want)
			}

			if got, want := result.BundleDir, bundleDir; got != want {
				t.Fatalf("result.BundleDir = %q, want %q", got, want)
			}
			if got, want := result.TargetDir, targetDir; got != want {
				t.Fatalf("result.TargetDir = %q, want %q", got, want)
			}
			if len(result.ValidationWarning) != 0 {
				t.Fatalf("result.ValidationWarning = %v, want no warnings", result.ValidationWarning)
			}
		})
	}
}

func TestInstallRejectsTraversalBundlePaths(t *testing.T) {
	t.Parallel()

	bundleDir := t.TempDir()
	manifest := Manifest{
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
	writeBundleMetadata(t, bundleDir, manifest)

	checksumsPath := filepath.Join(bundleDir, checksumsFileName)
	checksumsData, err := os.ReadFile(checksumsPath)
	if err != nil {
		t.Fatalf("ReadFile(%q) error = %v", checksumsPath, err)
	}
	checksumsData = append(checksumsData, []byte("deadbeef  ..\\escape.txt\n")...)
	if err := os.WriteFile(checksumsPath, checksumsData, 0o644); err != nil {
		t.Fatalf("WriteFile(%q) error = %v", checksumsPath, err)
	}

	targetDir := filepath.Join(t.TempDir(), "prefix")
	_, err = Install(Options{BundleDir: bundleDir, Target: targetDir})
	if err == nil {
		t.Fatal("Install() error = nil, want traversal rejection")
	}
	if !strings.Contains(err.Error(), "path escapes bundle directory") {
		t.Fatalf("Install() error = %v, want traversal rejection", err)
	}
	if _, statErr := os.Stat(filepath.Join(targetDir, "bin")); !os.IsNotExist(statErr) {
		t.Fatalf("expected install target to remain untouched, stat error = %v", statErr)
	}
}

func TestInstallRejectsInvalidBundleValidation(t *testing.T) {
	t.Parallel()

	t.Run("tampered component checksum", func(t *testing.T) {
		t.Parallel()

		bundleDir := t.TempDir()
		writeValidBundle(t, bundleDir, "linux/amd64")
		if err := os.WriteFile(filepath.Join(bundleDir, "plugin", "plugin.json"), []byte(`{"tampered":true}`), 0o644); err != nil {
			t.Fatalf("WriteFile(plugin.json) error = %v", err)
		}

		_, err := Install(Options{BundleDir: bundleDir, Target: t.TempDir()})
		if err == nil {
			t.Fatal("Install() error = nil, want checksum failure")
		}
		if !strings.Contains(err.Error(), "checksum mismatch") {
			t.Fatalf("Install() error = %v, want checksum mismatch", err)
		}
	})

	t.Run("manifest metadata missing", func(t *testing.T) {
		t.Parallel()

		bundleDir := t.TempDir()
		bundle := writeValidBundle(t, bundleDir, "linux/amd64")
		bundle.manifest.ReleaseTag = ""
		writeBundleMetadata(t, bundleDir, bundle.manifest)

		_, err := Install(Options{BundleDir: bundleDir, Target: t.TempDir()})
		if err == nil {
			t.Fatal("Install() error = nil, want manifest validation failure")
		}
		if !strings.Contains(err.Error(), "manifest release_tag is empty") {
			t.Fatalf("Install() error = %v, want manifest release tag failure", err)
		}
	})
}

type bundleFixture struct {
	manifest          Manifest
	wrapperBinaryName string
	sidecarBinaryName string
}

func writeValidBundle(t *testing.T, bundleDir, platform string) bundleFixture {
	t.Helper()

	wrapperBinaryName := binaryNameForPlatform("omni", platform)
	sidecarBinaryName := binaryNameForPlatform("omni-sidecar", platform)
	files := map[string]string{
		wrapperBinaryName:                   "wrapper-binary",
		sidecarBinaryName:                   "sidecar-binary",
		"plugin/plugin.json":                `{"name":"copilot-omni"}`,
		"templates/workflow/init/prompt.md": "# init\n",
		"policies/standard.json":            `{"profile":"standard"}`,
		"marketplace.json":                  `{"plugins":[{"name":"copilot-omni"}]}`,
		"scripts/install-offline.sh":        "#!/bin/sh\n",
	}

	components := []Component{
		newComponent(t, bundleDir, "omni-wrapper", wrapperBinaryName, "binary"),
		newComponent(t, bundleDir, "omni-sidecar", sidecarBinaryName, "binary"),
		newComponent(t, bundleDir, "plugin/plugin.json", "plugin/plugin.json", "file"),
		newComponent(t, bundleDir, "templates/workflow/init/prompt.md", "templates/workflow/init/prompt.md", "file"),
		newComponent(t, bundleDir, "policies/standard.json", "policies/standard.json", "file"),
		newComponent(t, bundleDir, "marketplace.json", "marketplace.json", "file"),
		newComponent(t, bundleDir, "scripts/install-offline.sh", "scripts/install-offline.sh", "file"),
	}

	for relativePath, content := range files {
		writeFixtureFile(t, bundleDir, relativePath, content)
	}

	manifestChecksums := make(map[string]string, len(components))
	sbom := make([]SBOMEntry, 0, len(components))
	for index := range components {
		componentPath := filepath.Join(bundleDir, filepath.FromSlash(components[index].Path))
		checksum, err := fileChecksum(componentPath)
		if err != nil {
			t.Fatalf("fileChecksum(%q) error = %v", componentPath, err)
		}
		components[index].Checksum = checksum
		manifestChecksums[components[index].Path] = checksum
		sbom = append(sbom, SBOMEntry{Name: components[index].Name, Type: components[index].Type, Hash: checksum})
	}

	manifest := Manifest{
		Version:    "1",
		Product:    "copilot-omni",
		ReleaseTag: "v1.0.0",
		BuildDate:  time.Now().UTC().Format(time.RFC3339),
		Platform:   platform,
		Components: components,
		Checksums:  manifestChecksums,
		Provenance: Provenance{Builder: "test"},
		SBOM:       sbom,
	}
	writeBundleMetadata(t, bundleDir, manifest)

	return bundleFixture{
		manifest:          manifest,
		wrapperBinaryName: wrapperBinaryName,
		sidecarBinaryName: sidecarBinaryName,
	}
}

func writeBundleMetadata(t *testing.T, bundleDir string, manifest Manifest) {
	t.Helper()

	manifestPath := filepath.Join(bundleDir, manifestFileName)
	sbomPath := filepath.Join(bundleDir, sbomFileName)
	writeJSONFile(t, manifestPath, manifest)
	writeJSONFile(t, sbomPath, manifest.SBOM)

	manifestChecksum, err := fileChecksum(manifestPath)
	if err != nil {
		t.Fatalf("fileChecksum(%q) error = %v", manifestPath, err)
	}
	sbomChecksum, err := fileChecksum(sbomPath)
	if err != nil {
		t.Fatalf("fileChecksum(%q) error = %v", sbomPath, err)
	}

	keys := make([]string, 0, len(manifest.Checksums))
	for relativePath := range manifest.Checksums {
		keys = append(keys, relativePath)
	}
	sort.Strings(keys)

	lines := []string{
		manifestChecksum + "  " + manifestFileName,
		sbomChecksum + "  " + sbomFileName,
	}
	for _, relativePath := range keys {
		lines = append(lines, manifest.Checksums[relativePath]+"  "+relativePath)
	}
	if err := os.WriteFile(filepath.Join(bundleDir, checksumsFileName), []byte(strings.Join(lines, "\n")+"\n"), 0o644); err != nil {
		t.Fatalf("WriteFile(%q) error = %v", filepath.Join(bundleDir, checksumsFileName), err)
	}
}

func newComponent(t *testing.T, bundleDir, name, relativePath, componentType string) Component {
	t.Helper()

	writeFixtureFile(t, bundleDir, relativePath, "")
	return Component{Name: name, Path: relativePath, Type: componentType}
}

func writeFixtureFile(t *testing.T, rootDir, relativePath, content string) {
	t.Helper()

	filePath := filepath.Join(rootDir, filepath.FromSlash(relativePath))
	if err := os.MkdirAll(filepath.Dir(filePath), 0o755); err != nil {
		t.Fatalf("MkdirAll(%q) error = %v", filepath.Dir(filePath), err)
	}
	if err := os.WriteFile(filePath, []byte(content), 0o755); err != nil {
		t.Fatalf("WriteFile(%q) error = %v", filePath, err)
	}
}

func writeJSONFile(t *testing.T, filePath string, value any) {
	t.Helper()

	payload, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		t.Fatalf("json.MarshalIndent() error = %v", err)
	}
	if err := os.MkdirAll(filepath.Dir(filePath), 0o755); err != nil {
		t.Fatalf("MkdirAll(%q) error = %v", filepath.Dir(filePath), err)
	}
	if err := os.WriteFile(filePath, payload, 0o644); err != nil {
		t.Fatalf("WriteFile(%q) error = %v", filePath, err)
	}
}

func binaryNameForPlatform(baseName, platform string) string {
	if strings.HasPrefix(platform, "windows/") {
		return baseName + ".exe"
	}
	return baseName
}

func assertInstalledFileContent(t *testing.T, filePath, want string) {
	t.Helper()

	data, err := os.ReadFile(filePath)
	if err != nil {
		t.Fatalf("ReadFile(%q) error = %v", filePath, err)
	}
	if got := string(data); got != want {
		t.Fatalf("file %q = %q, want %q", filePath, got, want)
	}
}

func assertInstalledMode(t *testing.T, filePath string, mask os.FileMode, want bool) {
	t.Helper()

	info, err := os.Stat(filePath)
	if err != nil {
		t.Fatalf("Stat(%q) error = %v", filePath, err)
	}
	if runtime.GOOS == "windows" {
		return
	}
	got := info.Mode().Perm()&mask != 0
	if got != want {
		t.Fatalf("file %q execute mode = %t, want %t (mode %v)", filePath, got, want, info.Mode().Perm())
	}
}

func assertFileExists(t *testing.T, filePath string) {
	t.Helper()

	if _, err := os.Stat(filePath); err != nil {
		t.Fatalf("Stat(%q) error = %v", filePath, err)
	}
}
