package support

import (
	"testing"
)

func TestRedactorNoPanic(t *testing.T) {
	r := NewRedactor()

	// Test data with various secret formats
	testData := []byte(`
api_key = "secret123"
api_key: 'secret456'
api_key=secret789
token = "bearer_token_here"
password: 'my_password'
`)

	// This should not panic
	result, redacted := r.Redact(testData, RedactionStandard)

	if !redacted {
		t.Error("Expected redaction to occur")
	}

	// Verify secrets were redacted
	resultStr := string(result)
	if contains(resultStr, "secret123") {
		t.Error("api_key value should be redacted")
	}
	if contains(resultStr, "bearer_token_here") {
		t.Error("token value should be redacted")
	}
	if contains(resultStr, "my_password") {
		t.Error("password value should be redacted")
	}
}

func TestRedactorString(t *testing.T) {
	r := NewRedactor()

	input := "api_key = super_secret_value"
	result, redacted := r.RedactString(input, RedactionStandard)

	if !redacted {
		t.Error("Expected redaction to occur")
	}

	if result == input {
		t.Error("Input should be modified by redaction")
	}
}

func contains(s, substr string) bool {
	return len(substr) > 0 && len(s) >= len(substr) && indexOf(s, substr) >= 0
}

func indexOf(s, substr string) int {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return i
		}
	}
	return -1
}
