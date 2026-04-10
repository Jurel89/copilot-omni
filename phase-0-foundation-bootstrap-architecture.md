{
  "product": "Copilot Omni",
  "generatedAt": "2026-04-10T12:23:52.507466Z",
  "phases": [
    {
      "id": "phase-0",
      "slug": "foundation-bootstrap",
      "title": "Foundation, Packaging, and Bootstrap",
      "dependsOn": [],
      "deliverables": [
        "Plugin repository skeleton",
        "Sidecar bootstrap binary skeleton",
        "Config schema and profile schema",
        "Init/bootstrap generator",
        "Doctor diagnostics engine",
        "Compatibility matrix and install docs"
      ],
      "metrics": [
        "Installation success rate in clean test VMs: >= 95%",
        "Doctor false-positive rate: < 2%",
        "Bootstrap re-run drift: zero unmanaged file corruption across 50 re-runs"
      ],
      "acceptance": [
        "Plugin installs successfully from `copilot plugin install ./PATH/TO/PLUGIN` on macOS, Linux, and Windows test environments.",
        "The sidecar starts through the plugin MCP definition and returns a successful health response.",
        "`omni init` creates the expected instruction and config files and preserves manual edits outside managed blocks on repeat runs.",
        "`omni doctor` catches all intentionally injected packaging faults in the test harness."
      ],
      "workPackages": [
        "Packaging and manifest implementation",
        "Sidecar bootstrap and health protocol",
        "Config precedence and profile packs",
        "Init/bootstrap file generation",
        "Doctor diagnostics and test harness"
      ]
    },
    {
      "id": "phase-1",
      "slug": "spec-driven-workflow-core",
      "title": "Spec-Driven Workflow Core",
      "dependsOn": [
        "phase-0"
      ],
      "deliverables": [
        "Run state machine",
        "Spec and plan schemas",
        "Conductor/planner/reviewer/verifier agents",
        "Phase transcript export and summary generation",
        "CLI entry points for run, plan, and resume"
      ],
      "metrics": [
        "Plan acceptance rate by reviewers during pilot: >= 80% without manual rewrite",
        "Unplanned file touches during later execution: < 5% of modified files",
        "Resume success after interrupted planning run: >= 95%"
      ],
      "acceptance": [
        "A feature prompt produces a complete spec, plan, and decisions artifact set with stable IDs and machine-readable status.",
        "Execution is blocked if the plan lacks required verification steps or if review finds unresolved blocking issues.",
        "Interrupted runs can be resumed without duplicate artifact creation or lost decisions.",
        "Every task in the plan names intended files, expected verification commands, and a rollback note."
      ],
      "workPackages": [
        "Run state model and artifact layout",
        "Spec and plan schema design",
        "Agent prompt contracts",
        "Programmatic Copilot phase runner",
        "Resume and artifact hydration"
      ]
    },
    {
      "id": "phase-2",
      "slug": "guarded-execution-verification",
      "title": "Guarded Execution and Verification Engine",
      "dependsOn": [
        "phase-0",
        "phase-1"
      ],
      "deliverables": [
        "Guarded execution engine",
        "MCP tools for patching, verification, and repo map",
        "Hooks-based policy layer",
        "Execution journal and rollback metadata",
        "Reviewer/verifier gating"
      ],
      "metrics": [
        "Unsafe command escape rate in adversarial tests: 0",
        "Verification failure attribution completeness: >= 95% of failed runs name the failing command and artifact",
        "Resume-after-crash success during execution: >= 90%"
      ],
      "acceptance": [
        "Attempted writes outside the current plan are blocked in strict and standard profiles.",
        "Injected malicious text in planning artifacts is detected or sanitized before execution continues.",
        "Each completed task has a verification report and independent review outcome.",
        "Adversarial tests confirm that deny rules override allow rules and that protected paths cannot be edited without explicit policy."
      ],
      "workPackages": [
        "Task executor and journal",
        "Policy engine and profiles",
        "Hooks integration",
        "Guarded MCP tools",
        "Verification orchestration",
        "Adversarial security tests"
      ]
    },
    {
      "id": "phase-3",
      "slug": "local-memory-resumability",
      "title": "Local Memory, Retrieval, and Deep Resumability",
      "dependsOn": [
        "phase-0",
        "phase-1",
        "phase-2"
      ],
      "deliverables": [
        "Memory schema and storage engine",
        "Artifact and summary ingestion pipeline",
        "Memory search and capture commands",
        "Retention and privacy controls",
        "Deep resume context hydrator"
      ],
      "metrics": [
        "Recall precision on curated benchmark queries: >= 85%",
        "Incorrect source attribution: 0 tolerance",
        "Warm-query p95 latency: <= 150 ms"
      ],
      "acceptance": [
        "A previous decision can be retrieved with explicit source references to the originating run and artifact.",
        "Project memory can be wiped completely and independently of global memory.",
        "Resume after a week-long pause reconstructs task context without requiring manual browsing of old transcripts.",
        "Memory search remains fast on seeded repositories with at least 50 runs worth of artifacts."
      ],
      "workPackages": [
        "Schema design and migrations",
        "Ingestion boundaries and summarization rules",
        "Search ranking implementation",
        "Resume hydrator",
        "Privacy controls and tests"
      ]
    },
    {
      "id": "phase-4",
      "slug": "research-subagents-parallelism",
      "title": "Research, Subagents, and Parallel Workflows",
      "dependsOn": [
        "phase-0",
        "phase-1",
        "phase-2",
        "phase-3"
      ],
      "deliverables": [
        "Research workflow and report format",
        "Subtask scheduler",
        "Isolated workspace strategy",
        "Merge and review pipeline",
        "Intent and capability router"
      ],
      "metrics": [
        "Planning time reduction on large benchmark tasks: >= 25%",
        "Conflict-free subtask merge rate on targeted task classes: >= 80%",
        "Research report citation/source completeness: >= 95%"
      ],
      "acceptance": [
        "Parallel read-only research runs complete without modifying the main worktree.",
        "Write-capable subtasks run in isolated workspaces and can be discarded independently on failure.",
        "Merged outputs retain parent-child lineage and pass the same review and verification gates as serial tasks.",
        "Research reports explicitly tag external findings, repository evidence, prior-memory evidence, and open questions."
      ],
      "workPackages": [
        "Research flow design",
        "Subtask schema and scheduler",
        "Workspace isolation implementation",
        "Merge/review pipeline",
        "Performance and correctness benchmarking"
      ]
    },
    {
      "id": "phase-5",
      "slug": "enterprise-offline-distribution",
      "title": "Enterprise Policy, Offline Distribution, and Operability",
      "dependsOn": [
        "phase-0",
        "phase-1",
        "phase-2",
        "phase-3",
        "phase-4"
      ],
      "deliverables": [
        "Release bundle format",
        "Policy packs and validator",
        "Offline installation guides and scripts",
        "Audit export tools",
        "Enterprise diagnostics and compatibility matrix"
      ],
      "metrics": [
        "Air-gapped install success rate: >= 95%",
        "Policy validation false-negative rate: 0 on seeded policy test corpus",
        "Support time to diagnose packaging/config issues: reduced by >= 50% versus baseline"
      ],
      "acceptance": [
        "The product installs from a local marketplace root added via `copilot plugin marketplace add /PATH/TO/MARKETPLACE`.",
        "Strict profile disables or warns on features that rely on experimental or weakly enforced enterprise controls.",
        "Audit exports contain sufficient data to reconstruct run status, verification state, and policy decisions without exposing secrets.",
        "Offline install tests pass on macOS, Linux, and Windows images with no package-manager access."
      ],
      "workPackages": [
        "Bundle format and signing",
        "Policy pack design",
        "Offline install tooling",
        "Audit export implementation",
        "Enterprise acceptance test matrix"
      ]
    },
    {
      "id": "phase-6",
      "slug": "ga-hardening-ux-performance",
      "title": "GA Hardening, Performance, UX Polish, and v1 Launch",
      "dependsOn": [
        "phase-0",
        "phase-1",
        "phase-2",
        "phase-3",
        "phase-4",
        "phase-5"
      ],
      "deliverables": [
        "Performance budgets and benchmark harness",
        "Migration engine and rollback tooling",
        "Support bundle generator",
        "Polished UX and help surfaces",
        "GA release checklist and operator docs"
      ],
      "metrics": [
        "Cold start p95: <= 1.5 s on target dev hardware",
        "Memory search warm p95: <= 150 ms",
        "Regression escape rate from benchmark suite: 0 critical regressions",
        "Support bundle usefulness in seeded incidents: >= 90% issue triage success"
      ],
      "acceptance": [
        "All prior phase exit criteria continue to pass under the GA test matrix.",
        "Performance budgets are met on representative repositories and developer machines.",
        "Upgrade and rollback scenarios succeed on supported pre-GA versions.",
        "Red-team and adversarial suites pass with no unresolved critical findings.",
        "User-facing docs and operator docs are complete and version-matched."
      ],
      "workPackages": [
        "Performance instrumentation",
        "Benchmark corpus and CI gates",
        "Schema migration tooling",
        "Support bundle implementation",
        "Docs and release readiness"
      ]
    }
  ],
  "globalPrinciples": [
    {
      "name": "Hybrid runtime",
      "description": "Use a native GitHub Copilot CLI plugin for user-facing integration and a bundled local sidecar binary for memory, policy, orchestration state, and guarded tools."
    },
    {
      "name": "Artifact-first execution",
      "description": "Every run must produce durable artifacts: spec, plan, decisions, execution log, verification report, and state metadata. Artifacts are the source of truth, not the live chat transcript."
    },
    {
      "name": "Fresh-context phases",
      "description": "Run discuss, plan, execute, and verify as separate bounded contexts. Use programmatic Copilot invocations for phase transitions to reduce context drift."
    },
    {
      "name": "Local-first and enterprise-safe",
      "description": "Default to local storage, local binaries, and offline-capable installation. External registries, cloud memory, and experimental features are optional accelerators, not core dependencies."
    },
    {
      "name": "Security as a product feature",
      "description": "Treat enterprise GitHub policy as advisory. Enforce policy in the sidecar and hooks, with path validation, prompt-injection scanning, command allowlists, protected paths, and audit trails."
    },
    {
      "name": "Copilot-native where possible",
      "description": "Use plugins, agents, skills, hooks, MCP, plan mode, /research, /fleet, and session persistence where they fit. Do not fight built-ins when composition is enough."
    },
    {
      "name": "Namespaced everything",
      "description": "Prefix agents, skills, commands, servers, and files to avoid precedence collisions with project-level or personal configurations."
    },
    {
      "name": "Strict phase gates",
      "description": "No phase advances until installability, correctness, UX, and rollback gates pass. Each phase must be independently shippable and diagnosable."
    },
    {
      "name": "Minimal install burden",
      "description": "No npm, PyPI, Docker, or system Python requirement at install time for the plugin itself. Ship static sidecar binaries and plain files."
    },
    {
      "name": "Stable UX over feature count",
      "description": "Prefer one coherent entry flow with predictable artifacts and diagnostics over a broad command surface that users need to memorize."
    }
  ]
}