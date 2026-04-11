package benchmark

import (
	"context"
	"testing"
	"time"
)

func TestHarnessRegister(t *testing.T) {
	h := NewHarness("")
	b := &Benchmark{
		Name:        "test_benchmark",
		Description: "Test benchmark",
		Category:    "test",
		Budget:      100 * time.Millisecond,
		Iterations:  3,
		Run: func(ctx context.Context) (map[string]float64, error) {
			return map[string]float64{"duration_ms": 1.0}, nil
		},
	}

	if err := h.Register(b); err != nil {
		t.Fatalf("register benchmark: %v", err)
	}

	if len(h.benchmarks) != 1 {
		t.Errorf("expected 1 benchmark, got %d", len(h.benchmarks))
	}
}

func TestHarnessRun(t *testing.T) {
	h := NewHarness("")
	b := &Benchmark{
		Name:        "test_benchmark",
		Description: "Test benchmark",
		Category:    "test",
		Budget:      100 * time.Millisecond,
		Iterations:  3,
		Run: func(ctx context.Context) (map[string]float64, error) {
			return map[string]float64{"duration_ms": 1.0}, nil
		},
	}

	if err := h.Register(b); err != nil {
		t.Fatalf("register benchmark: %v", err)
	}

	result, err := h.Run(context.Background(), "test_benchmark")
	if err != nil {
		t.Fatalf("run benchmark: %v", err)
	}

	if result.Name != "test_benchmark" {
		t.Errorf("expected name 'test_benchmark', got %s", result.Name)
	}

	if result.Status != BudgetPass {
		t.Errorf("expected status pass, got %s", result.Status)
	}
}

func TestCalculateMetric(t *testing.T) {
	values := []float64{1.0, 2.0, 3.0, 4.0, 5.0}
	m := calculateMetric("test", values, 10*time.Millisecond)

	if m.Name != "test" {
		t.Errorf("expected name 'test', got %s", m.Name)
	}

	if m.Min != 1.0 {
		t.Errorf("expected min 1.0, got %f", m.Min)
	}

	if m.Max != 5.0 {
		t.Errorf("expected max 5.0, got %f", m.Max)
	}

	if m.Status != BudgetPass {
		t.Errorf("expected status pass, got %s", m.Status)
	}
}
