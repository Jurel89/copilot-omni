package router

import (
	"fmt"
	"strings"
)

type Capability string

const (
	CapSkill   Capability = "skill"
	CapAgent   Capability = "agent"
	CapSidecar Capability = "sidecar"
	CapBuiltIn Capability = "builtin"
)

type Route struct {
	Capability Capability `json:"capability"`
	Target     string     `json:"target"`
	Confidence string     `json:"confidence"`
	Reason     string     `json:"reason,omitempty"`
}

type Intent string

const (
	IntentResearch  Intent = "research"
	IntentImplement Intent = "implement"
	IntentReview    Intent = "review"
	IntentVerify    Intent = "verify"
	IntentPlan      Intent = "plan"
	IntentDiagnose  Intent = "diagnose"
	IntentExplore   Intent = "explore"
	IntentUnknown   Intent = "unknown"
)

type Router struct {
	availableSkills map[string]bool
	availableAgents map[string]bool
	availableTools  map[string]bool
}

func NewRouter() *Router {
	return &Router{
		availableSkills: map[string]bool{
			"omni-init":     true,
			"omni-run":      true,
			"omni-plan":     true,
			"omni-resume":   true,
			"omni-status":   true,
			"omni-doctor":   true,
			"omni-memory":   true,
			"omni-research": true,
		},
		availableAgents: map[string]bool{
			"omni-conductor":  true,
			"omni-planner":    true,
			"omni-reviewer":   true,
			"omni-verifier":   true,
			"omni-researcher": true,
		},
		availableTools: map[string]bool{
			"omni_health":           true,
			"omni_doctor":           true,
			"omni_config_resolve":   true,
			"omni_artifact_read":    true,
			"omni_artifact_write":   true,
			"omni_run_status":       true,
			"omni_resume_context":   true,
			"omni_guarded_patch":    true,
			"omni_verification_run": true,
			"omni_repo_map":         true,
			"omni_policy_check":     true,
			"omni_memory_search":    true,
			"omni_memory_capture":   true,
			"omni_memory_ingest":    true,
			"omni_memory_wipe":      true,
			"omni_memory_export":    true,
			"omni_memory_prune":     true,
			"omni_research":         true,
			"omni_subtask_create":   true,
			"omni_subtask_status":   true,
			"omni_merge":            true,
			"omni_intent_route":     true,
		},
	}
}

func ClassifyIntent(prompt string) Intent {
	lower := strings.ToLower(prompt)
	keywords := map[Intent][]string{
		IntentResearch:  {"research", "investigate", "find", "look up", "explore", "search", "docs", "documentation"},
		IntentImplement: {"implement", "build", "create", "add", "write", "code", "develop", "fix"},
		IntentReview:    {"review", "check", "audit", "inspect", "evaluate"},
		IntentVerify:    {"verify", "test", "validate", "run tests", "build"},
		IntentPlan:      {"plan", "design", "architect", "spec", "strategy"},
		IntentDiagnose:  {"diagnose", "debug", "troubleshoot", "error", "broken", "fix"},
		IntentExplore:   {"explore", "map", "understand", "how does", "where is", "find"},
	}

	bestMatch := IntentUnknown
	bestCount := 0
	for intent, terms := range keywords {
		count := 0
		for _, term := range terms {
			if strings.Contains(lower, term) {
				count++
			}
		}
		if count > bestCount {
			bestCount = count
			bestMatch = intent
		}
	}

	return bestMatch
}

func (r *Router) Route(intent Intent) Route {
	switch intent {
	case IntentResearch:
		return Route{
			Capability: CapAgent,
			Target:     "omni-researcher",
			Confidence: "high",
			Reason:     "research intent maps to researcher agent",
		}
	case IntentImplement:
		return Route{
			Capability: CapAgent,
			Target:     "omni-conductor",
			Confidence: "high",
			Reason:     "implementation intent maps to conductor agent",
		}
	case IntentReview:
		return Route{
			Capability: CapAgent,
			Target:     "omni-reviewer",
			Confidence: "high",
			Reason:     "review intent maps to reviewer agent",
		}
	case IntentVerify:
		return Route{
			Capability: CapSidecar,
			Target:     "omni_verification_run",
			Confidence: "high",
			Reason:     "verify intent maps to sidecar verification tool",
		}
	case IntentPlan:
		return Route{
			Capability: CapAgent,
			Target:     "omni-planner",
			Confidence: "high",
			Reason:     "plan intent maps to planner agent",
		}
	case IntentDiagnose:
		return Route{
			Capability: CapSidecar,
			Target:     "omni_doctor",
			Confidence: "medium",
			Reason:     "diagnose intent maps to doctor tool",
		}
	case IntentExplore:
		return Route{
			Capability: CapSidecar,
			Target:     "omni_repo_map",
			Confidence: "medium",
			Reason:     "explore intent maps to repo map tool",
		}
	default:
		return Route{
			Capability: CapAgent,
			Target:     "omni-conductor",
			Confidence: "low",
			Reason:     fmt.Sprintf("unknown intent routed to conductor as default"),
		}
	}
}

func (r *Router) Resolve(prompt string) Route {
	intent := ClassifyIntent(prompt)
	return r.Route(intent)
}
