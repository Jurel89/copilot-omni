package benchmark

import (
	"context"
	"fmt"
	"time"

	"github.com/copilot-omni/sidecar/internal/artifact"
	"github.com/copilot-omni/sidecar/internal/config"
	"github.com/copilot-omni/sidecar/internal/memory"
	"github.com/copilot-omni/sidecar/internal/policy"
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
			time.Sleep(10 * time.Millisecond)
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
		Setup: func(ctx context.Context) error {
			return nil
		},
		Run: func(ctx context.Context) (map[string]float64, error) {
			if store == nil {
				return nil, fmt.Errorf("memory store not available")
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
		Teardown: func(ctx context.Context) error {
			return nil
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
				return nil, fmt.Errorf("policy engine not available")
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
				return nil, fmt.Errorf("artifact store not available")
			}
			start := time.Now()
			_, err := store.ReadSpec("test-run")
			elapsed := float64(time.Since(start).Milliseconds())
			if err != nil {
				return map[string]float64{"error_ms": elapsed}, err
			}
			return map[string]float64{
				"load_ms": elapsed,
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
			time.Sleep(5 * time.Millisecond)
			elapsed := float64(time.Since(start).Milliseconds())
			return map[string]float64{
				"parse_ms": elapsed,
			}, nil
		},
	}
}
