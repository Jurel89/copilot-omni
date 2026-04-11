package version

import (
	"regexp"
	"testing"
)

func TestVersionContract(t *testing.T) {
	t.Parallel()

	semverPattern := regexp.MustCompile(`^\d+\.\d+\.\d+$`)

	tests := []struct {
		name  string
		check func(t *testing.T, got string)
	}{
		{
			name: "matches the expected wrapper release",
			check: func(t *testing.T, got string) {
				t.Helper()
				if got != "0.1.0" {
					t.Fatalf("Version = %q, want %q", got, "0.1.0")
				}
			},
		},
		{
			name: "uses a three-part semantic version",
			check: func(t *testing.T, got string) {
				t.Helper()
				if !semverPattern.MatchString(got) {
					t.Fatalf("Version = %q, want semantic version format major.minor.patch", got)
				}
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			tt.check(t, Version)
		})
	}
}
