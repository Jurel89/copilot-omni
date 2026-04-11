package benchmark

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// Phase6TargetBudgets defines the performance budgets from Phase 6 PRD
var Phase6TargetBudgets = BudgetSet{
	ColdStartP95:    1500 * time.Millisecond, // 1.5s
	MemorySearchP95: 150 * time.Millisecond,  // 150ms
	PolicyCheckP95:  50 * time.Millisecond,
	ArtifactLoadP95: 100 * time.Millisecond,
	PlanParseP95:    200 * time.Millisecond,
	VerificationP95: 5000 * time.Millisecond, // 5s for command execution
}

// BudgetSet defines performance budgets for various operations
type BudgetSet struct {
	ColdStartP95    time.Duration `json:"cold_start_p95_ms"`
	MemorySearchP95 time.Duration `json:"memory_search_p95_ms"`
	PolicyCheckP95  time.Duration `json:"policy_check_p95_ms"`
	ArtifactLoadP95 time.Duration `json:"artifact_load_p95_ms"`
	PlanParseP95    time.Duration `json:"plan_parse_p95_ms"`
	VerificationP95 time.Duration `json:"verification_p95_ms"`
}

// BudgetStatus indicates whether a metric is within budget
type BudgetStatus string

const (
	BudgetPass BudgetStatus = "pass"
	BudgetWarn BudgetStatus = "warn"
	BudgetFail BudgetStatus = "fail"
)

// BenchmarkResult contains metrics for a single benchmark run
type BenchmarkResult struct {
	Name        string            `json:"name"`
	Description string            `json:"description"`
	StartTime   time.Time         `json:"start_time"`
	EndTime     time.Time         `json:"end_time"`
	Duration    time.Duration     `json:"duration_ms"`
	Iterations  int               `json:"iterations"`
	Metrics     map[string]Metric `json:"metrics"`
	Status      BudgetStatus      `json:"status"`
	Errors      []string          `json:"errors,omitempty"`
	Metadata    map[string]string `json:"metadata,omitempty"`
}

// Metric represents a single measured value with statistics
type Metric struct {
	Name   string        `json:"name"`
	Unit   string        `json:"unit"`
	Values []float64     `json:"values,omitempty"`
	Min    float64       `json:"min"`
	Max    float64       `json:"max"`
	Mean   float64       `json:"mean"`
	P50    float64       `json:"p50"`
	P95    float64       `json:"p95"`
	P99    float64       `json:"p99"`
	StdDev float64       `json:"stddev"`
	Budget time.Duration `json:"budget,omitempty"`
	Status BudgetStatus  `json:"status"`
}

// Benchmark defines a single benchmark test
type Benchmark struct {
	Name        string
	Description string
	Category    string // "startup", "memory", "execution", "verification"
	Budget      time.Duration
	Iterations  int
	Setup       func(ctx context.Context) error
	Teardown    func(ctx context.Context) error
	Run         func(ctx context.Context) (map[string]float64, error)
}

// Harness manages benchmark execution
type Harness struct {
	mu         sync.RWMutex
	benchmarks map[string]*Benchmark
	results    []*BenchmarkResult
	budgets    BudgetSet
	historyDir string
}

// NewHarness creates a new benchmark harness
func NewHarness(historyDir string) *Harness {
	if historyDir == "" {
		historyDir = filepath.Join(os.TempDir(), "copilot-omni", "benchmarks")
	}

	return &Harness{
		benchmarks: make(map[string]*Benchmark),
		budgets:    Phase6TargetBudgets,
		historyDir: historyDir,
	}
}

// Register adds a benchmark to the harness
func (h *Harness) Register(b *Benchmark) error {
	h.mu.Lock()
	defer h.mu.Unlock()

	if _, exists := h.benchmarks[b.Name]; exists {
		return fmt.Errorf("benchmark %q already registered", b.Name)
	}

	if b.Iterations <= 0 {
		b.Iterations = 10 // default
	}

	h.benchmarks[b.Name] = b
	return nil
}

// Run executes a single benchmark by name
func (h *Harness) Run(ctx context.Context, name string) (*BenchmarkResult, error) {
	h.mu.RLock()
	b, exists := h.benchmarks[name]
	h.mu.RUnlock()

	if !exists {
		return nil, fmt.Errorf("benchmark %q not found", name)
	}

	return h.runBenchmark(ctx, b)
}

// RunAll executes all registered benchmarks
func (h *Harness) RunAll(ctx context.Context) ([]*BenchmarkResult, error) {
	h.mu.RLock()
	benchmarks := make([]*Benchmark, 0, len(h.benchmarks))
	for _, b := range h.benchmarks {
		benchmarks = append(benchmarks, b)
	}
	h.mu.RUnlock()

	results := make([]*BenchmarkResult, 0, len(benchmarks))
	for _, b := range benchmarks {
		result, err := h.runBenchmark(ctx, b)
		if err != nil {
			return nil, fmt.Errorf("benchmark %q failed: %w", b.Name, err)
		}
		results = append(results, result)
	}

	return results, nil
}

// RunCategory executes all benchmarks in a category
func (h *Harness) RunCategory(ctx context.Context, category string) ([]*BenchmarkResult, error) {
	h.mu.RLock()
	var benchmarks []*Benchmark
	for _, b := range h.benchmarks {
		if b.Category == category {
			benchmarks = append(benchmarks, b)
		}
	}
	h.mu.RUnlock()

	results := make([]*BenchmarkResult, 0, len(benchmarks))
	for _, b := range benchmarks {
		result, err := h.runBenchmark(ctx, b)
		if err != nil {
			return nil, fmt.Errorf("benchmark %q failed: %w", b.Name, err)
		}
		results = append(results, result)
	}

	return results, nil
}

// runBenchmark executes a single benchmark and collects metrics
func (h *Harness) runBenchmark(ctx context.Context, b *Benchmark) (*BenchmarkResult, error) {
	result := &BenchmarkResult{
		Name:        b.Name,
		Description: b.Description,
		StartTime:   time.Now(),
		Iterations:  b.Iterations,
		Metrics:     make(map[string]Metric),
		Status:      BudgetPass,
	}

	// Run setup if provided
	if b.Setup != nil {
		if err := b.Setup(ctx); err != nil {
			result.Status = BudgetFail
			result.Errors = append(result.Errors, fmt.Sprintf("setup failed: %v", err))
			return result, nil
		}
	}

	// Ensure teardown runs
	if b.Teardown != nil {
		defer b.Teardown(ctx)
	}

	// Collect raw measurements
	measurements := make(map[string][]float64)

	for i := 0; i < b.Iterations; i++ {
		metrics, err := b.Run(ctx)
		if err != nil {
			result.Errors = append(result.Errors, fmt.Sprintf("iteration %d failed: %v", i, err))
			continue
		}

		for name, value := range metrics {
			measurements[name] = append(measurements[name], value)
		}
	}

	// Calculate statistics for each metric
	for name, values := range measurements {
		if len(values) == 0 {
			continue
		}

		metric := calculateMetric(name, values, b.Budget)
		result.Metrics[name] = metric

		// Update overall status based on metric status
		if metric.Status == BudgetFail && result.Status != BudgetFail {
			result.Status = BudgetFail
		} else if metric.Status == BudgetWarn && result.Status == BudgetPass {
			result.Status = BudgetWarn
		}
	}

	result.EndTime = time.Now()
	result.Duration = result.EndTime.Sub(result.StartTime)

	// Store result
	h.mu.Lock()
	h.results = append(h.results, result)
	h.mu.Unlock()

	return result, nil
}

// GetResults returns all benchmark results
func (h *Harness) GetResults() []*BenchmarkResult {
	h.mu.RLock()
	defer h.mu.RUnlock()

	results := make([]*BenchmarkResult, len(h.results))
	copy(results, h.results)
	return results
}

// GetBudgets returns the current performance budgets
func (h *Harness) GetBudgets() BudgetSet {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return h.budgets
}

// SetBudgets updates the performance budgets
func (h *Harness) SetBudgets(budgets BudgetSet) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.budgets = budgets
}

// SaveResults persists benchmark results to disk
func (h *Harness) SaveResults(results []*BenchmarkResult) error {
	if err := os.MkdirAll(h.historyDir, 0755); err != nil {
		return fmt.Errorf("failed to create history directory: %w", err)
	}

	filename := fmt.Sprintf("benchmark-%s.json", time.Now().Format("20060102-150405"))
	filepath := filepath.Join(h.historyDir, filename)

	data, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal results: %w", err)
	}

	if err := os.WriteFile(filepath, data, 0644); err != nil {
		return fmt.Errorf("failed to write results: %w", err)
	}

	return nil
}

// LoadHistory loads historical benchmark results
func (h *Harness) LoadHistory() ([]*BenchmarkResult, error) {
	entries, err := os.ReadDir(h.historyDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to read history directory: %w", err)
	}

	var allResults []*BenchmarkResult
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}

		filepath := filepath.Join(h.historyDir, entry.Name())
		data, err := os.ReadFile(filepath)
		if err != nil {
			continue // skip unreadable files
		}

		var results []*BenchmarkResult
		if err := json.Unmarshal(data, &results); err != nil {
			continue // skip invalid files
		}

		allResults = append(allResults, results...)
	}

	return allResults, nil
}

// calculateMetric computes statistics from raw values
func calculateMetric(name string, values []float64, budget time.Duration) Metric {
	if len(values) == 0 {
		return Metric{Name: name}
	}

	m := Metric{
		Name:   name,
		Unit:   "ms",
		Values: values,
		Min:    values[0],
		Max:    values[0],
	}

	var sum float64
	for _, v := range values {
		if v < m.Min {
			m.Min = v
		}
		if v > m.Max {
			m.Max = v
		}
		sum += v
	}

	m.Mean = sum / float64(len(values))

	// Sort for percentile calculation
	sorted := make([]float64, len(values))
	copy(sorted, values)
	for i := 0; i < len(sorted)-1; i++ {
		for j := i + 1; j < len(sorted); j++ {
			if sorted[i] > sorted[j] {
				sorted[i], sorted[j] = sorted[j], sorted[i]
			}
		}
	}

	// Calculate percentiles
	m.P50 = percentile(sorted, 0.50)
	m.P95 = percentile(sorted, 0.95)
	m.P99 = percentile(sorted, 0.99)

	// Calculate standard deviation
	var varianceSum float64
	for _, v := range values {
		diff := v - m.Mean
		varianceSum += diff * diff
	}
	m.StdDev = varianceSum / float64(len(values))

	// Check budget
	if budget > 0 {
		m.Budget = budget
		budgetMs := float64(budget.Milliseconds())
		if m.P95 > budgetMs*1.2 {
			m.Status = BudgetFail
		} else if m.P95 > budgetMs {
			m.Status = BudgetWarn
		} else {
			m.Status = BudgetPass
		}
	}

	return m
}

// percentile calculates the p-th percentile from sorted data
func percentile(sorted []float64, p float64) float64 {
	if len(sorted) == 0 {
		return 0
	}
	if len(sorted) == 1 {
		return sorted[0]
	}

	index := p * float64(len(sorted)-1)
	lower := int(index)
	upper := lower + 1

	if upper >= len(sorted) {
		return sorted[lower]
	}

	fraction := index - float64(lower)
	return sorted[lower] + fraction*(sorted[upper]-sorted[lower])
}
