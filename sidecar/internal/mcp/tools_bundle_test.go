package mcp

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestWriteBundleMarketplaceFileUsesPlatformBinaryNames(t *testing.T) {
	repoRoot := t.TempDir()
	marketplacePath := filepath.Join(repoRoot, "marketplace.json")
	if err := os.WriteFile(marketplacePath, []byte(`{
  "name": "copilot-omni-marketplace",
  "version": "1",
  "description": "Local marketplace",
  "plugins": [{"name":"copilot-omni","version":"0.1.0","description":"desc","path":"./plugin","sidecar":"./omni-sidecar","wrapper":"./omni"}]
}`), 0o644); err != nil {
		t.Fatalf("WriteFile(marketplace.json) error = %v", err)
	}

	generatedPath, err := writeBundleMarketplaceFile(repoRoot, "windows/amd64")
	if err != nil {
		t.Fatalf("writeBundleMarketplaceFile() error = %v", err)
	}
	defer os.Remove(generatedPath)

	content, err := os.ReadFile(generatedPath)
	if err != nil {
		t.Fatalf("ReadFile(generated marketplace) error = %v", err)
	}

	var payload struct {
		Plugins []struct {
			Sidecar string `json:"sidecar"`
			Wrapper string `json:"wrapper"`
		} `json:"plugins"`
	}
	if err := json.Unmarshal(content, &payload); err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}
	if got, want := payload.Plugins[0].Sidecar, "./omni-sidecar.exe"; got != want {
		t.Fatalf("sidecar = %q, want %q", got, want)
	}
	if got, want := payload.Plugins[0].Wrapper, "./omni.exe"; got != want {
		t.Fatalf("wrapper = %q, want %q", got, want)
	}
}
