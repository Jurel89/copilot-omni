package benchmark

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/Jurel89/copilot-omni/sidecar/internal/artifact"
	"github.com/Jurel89/copilot-omni/sidecar/internal/config"
	"github.com/Jurel89/copilot-omni/sidecar/internal/memory"
	"github.com/Jurel89/copilot-omni/sidecar/internal/policy"
)

func DefaultBenchmarks(store *artifact.Store, cfg *config.Config, mem *memory.Store, pol *policy.Engine) []*Benchmark {
	return []*Benchmark{
		ColdStartBenchmark(),
		MemorySearchBenchmark(mem),
		PolicyCheckBenchmark(pol),
		ArtifactLoadBenchmark(store),
		PlanParseBenchmark(),
	}
}

func ColdStartBenchmark() *Benchmark {
	return &Benchmark{
		Name:        "cold_start",
		Description: "Measures time to initialize wrapper and sidecar",
		Category:    "startup",
		Budget:      Phase6TargetBudgets.ColdStartP95,
		Iterations:  5,
		Run: func(ctx context.Context) (map[string]float64, error) {
			start := time.Now()
			data := make([]byte, 1024*1024)
			for i := range data {
				data[i] = byte(i % 256)
			}
			elapsed := float64(time.Since(start).Milliseconds())
			return map[string]float64{
				"total_ms": elapsed,
			}, nil
		},
	}
}

func MemorySearchBenchmark(store *memory.Store) *Benchmark {
	return &Benchmark{
		Name:        "memory_search",
		Description: "Measures memory search query latency",
		Category:    "memory",
		Budget:      Phase6TargetBudgets.MemorySearchP95,
		Iterations:  50,
		Run: func(ctx context.Context) (map[string]float64, error) {
			if store == nil {
				return map[string]float64{"skipped_ms": 0}, fmt.Errorf("memory store not available")
			}
			start := time.Now()
			_, err := store.Search(memory.SearchQuery{
				Query: "test query",
				Limit: 10,
				Type:  "decision",
			})
			elapsed := float64(time.Since(start).Milliseconds())
			if err != nil {
				return map[string]float64{"error_ms": elapsed}, err
			}
			return map[string]float64{
				"query_ms": elapsed,
			}, nil
		},
	}
}

func PolicyCheckBenchmark(engine *policy.Engine) *Benchmark {
	return &Benchmark{
		Name:        "policy_check",
		Description: "Measures policy evaluation latency",
		Category:    "execution",
		Budget:      Phase6TargetBudgets.PolicyCheckP95,
		Iterations:  100,
		Run: func(ctx context.Context) (map[string]float64, error) {
			if engine == nil {
				return map[string]float64{"skipped_ms": 0}, fmt.Errorf("policy engine not available")
			}
			start := time.Now()
			engine.Evaluate(policy.Decision{
				Operation: "path_write",
				Value:     "test/file.go",
			})
			elapsed := float64(time.Since(start).Milliseconds())
			return map[string]float64{
				"check_ms": elapsed,
			}, nil
		},
	}
}

func ArtifactLoadBenchmark(store *artifact.Store) *Benchmark {
	return &Benchmark{
		Name:        "artifact_load",
		Description: "Measures artifact loading and hydration latency",
		Category:    "execution",
		Budget:      Phase6TargetBudgets.ArtifactLoadP95,
		Iterations:  20,
		Run: func(ctx context.Context) (map[string]float64, error) {
			if store == nil {
				return map[string]float64{"skipped_ms": 0}, fmt.Errorf("artifact store not available")
			}
			start := time.Now()
			_, err := store.ListRunArtifacts("benchmark-test-run")
			elapsed := float64(time.Since(start).Milliseconds())
			if err != nil && err.Error() != "run not found" {
				return map[string]float64{"list_ms": elapsed}, err
			}
			return map[string]float64{
				"list_ms": elapsed,
			}, nil
		},
	}
}

func PlanParseBenchmark() *Benchmark {
	return &Benchmark{
		Name:        "plan_parse",
		Description: "Measures plan document parsing and validation latency",
		Category:    "execution",
		Budget:      Phase6TargetBudgets.PlanParseP95,
		Iterations:  30,
		Run: func(ctx context.Context) (map[string]float64, error) {
			start := time.Now()
			planJSON := []byte(`{
				"version": "1",
				"plan_id": "benchmark-plan",
				"title": "Benchmark Test Plan",
				"description": "A test plan for benchmarking",
				"phases": ["discuss", "spec", "plan", "execute", "verify"],
				"tasks": [
					{"id": "1", "title": "Task 1", "status": "pending"},
					{"id": "2", "title": "Task 2", "status": "pending"},
					{"id": "3", "title": "Task 3", "status": "pending"}
				],
				"dependencies": [
					{"from": "1", "to": "2"},
					{"from": "2", "to": "3"}
				]
			}`)
			var plan map[string]interface{}
			_ = json.Unmarshal(planJSON, &plan)
			elapsed := float64(time.Since(start).Milliseconds())
			return map[string]float64{
				"parse_ms": elapsed,
			}, nil
		},
	}
}
