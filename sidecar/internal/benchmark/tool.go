package benchmark

import (
	"context"
	"encoding/json"
	"fmt"
)

// Tool implements the omni_benchmark MCP tool
type Tool struct {
	harness *Harness
}

// NewTool creates a new benchmark tool
func NewTool(historyDir string) *Tool {
	return &Tool{
		harness: NewHarness(historyDir),
	}
}

// Name returns the tool name
func (t *Tool) Name() string {
	return "omni_benchmark"
}

// Description returns the tool description
func (t *Tool) Description() string {
	return "Run performance benchmarks and generate reports"
}

// Parameters returns the JSON schema for parameters
func (t *Tool) Parameters() map[string]interface{} {
	return map[string]interface{}{
		"type": "object",
		"properties": map[string]interface{}{
			"action": map[string]interface{}{
				"type":        "string",
				"enum":        []string{"run", "list", "report", "compare"},
				"description": "Action to perform",
			},
			"category": map[string]interface{}{
				"type":        "string",
				"enum":        []string{"startup", "memory", "execution", "verification", "all"},
				"description": "Benchmark category to run",
			},
			"benchmark": map[string]interface{}{
				"type":        "string",
				"description": "Specific benchmark name to run",
			},
			"iterations": map[string]interface{}{
				"type":        "integer",
				"description": "Number of iterations (default: benchmark default)",
			},
			"output_format": map[string]interface{}{
				"type":        "string",
				"enum":        []string{"json", "markdown"},
				"description": "Output format for reports",
			},
		},
		"required": []string{"action"},
	}
}

// Execute runs the benchmark tool
func (t *Tool) Execute(ctx context.Context, params json.RawMessage) (interface{}, error) {
	var args struct {
		Action       string `json:"action"`
		Category     string `json:"category,omitempty"`
		Benchmark    string `json:"benchmark,omitempty"`
		Iterations   int    `json:"iterations,omitempty"`
		OutputFormat string `json:"output_format,omitempty"`
	}

	if err := json.Unmarshal(params, &args); err != nil {
		return nil, fmt.Errorf("invalid parameters: %w", err)
	}

	switch args.Action {
	case "run":
		return t.runBenchmark(ctx, args.Benchmark, args.Category, args.Iterations)
	case "list":
		return t.listBenchmarks(), nil
	case "report":
		return t.generateReport(args.OutputFormat)
	case "compare":
		return t.compareBenchmarks()
	default:
		return nil, fmt.Errorf("unknown action: %s", args.Action)
	}
}

func (t *Tool) runBenchmark(ctx context.Context, name, category string, iterations int) (interface{}, error) {
	var results []*BenchmarkResult
	var err error

	if name != "" {
		results = make([]*BenchmarkResult, 0, 1)
		result, err := t.harness.Run(ctx, name)
		if err != nil {
			return nil, err
		}
		results = append(results, result)
	} else if category != "" && category != "all" {
		results, err = t.harness.RunCategory(ctx, category)
		if err != nil {
			return nil, err
		}
	} else {
		results, err = t.harness.RunAll(ctx)
		if err != nil {
			return nil, err
		}
	}

	if err := t.harness.SaveResults(results); err != nil {
		return nil, fmt.Errorf("failed to save results: %w", err)
	}

	summary := map[string]interface{}{
		"benchmarks_run": len(results),
		"results":        results,
	}

	return summary, nil
}

func (t *Tool) listBenchmarks() interface{} {
	return map[string]interface{}{
		"benchmarks": []map[string]string{
			{"name": "cold_start", "category": "startup", "description": "Cold start latency"},
			{"name": "memory_search", "category": "memory", "description": "Memory search latency"},
			{"name": "policy_check", "category": "execution", "description": "Policy evaluation latency"},
			{"name": "artifact_load", "category": "execution", "description": "Artifact loading latency"},
			{"name": "plan_parse", "category": "execution", "description": "Plan parsing latency"},
		},
	}
}

func (t *Tool) generateReport(format string) (interface{}, error) {
	results := t.harness.GetResults()
	if len(results) == 0 {
		return nil, fmt.Errorf("no benchmark results available")
	}

	report := GenerateReport(results, t.harness.GetBudgets())

	switch format {
	case "markdown":
		return report.ToMarkdown(), nil
	default:
		return report.ToJSON()
	}
}

func (t *Tool) compareBenchmarks() (interface{}, error) {
	history, err := t.harness.LoadHistory()
	if err != nil {
		return nil, fmt.Errorf("failed to load history: %w", err)
	}

	return map[string]interface{}{
		"historical_runs": len(history),
		"comparison":      "not implemented yet",
	}, nil
}
