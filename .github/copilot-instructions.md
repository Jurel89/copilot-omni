<!-- omni:managed:start -->
## Copilot Omni Integration

This repository uses Copilot Omni for artifact-driven development workflows.

### Workflow Phases
1. **Discuss** - Clarify requirements and constraints
2. **Spec** - Write a formal specification artifact
3. **Plan** - Create an implementation plan from the spec
4. **Execute** - Guarded implementation with scope enforcement
5. **Verify** - Build, test, lint, and custom verification

### Key Principles
- Every phase produces a durable artifact in `.omni/runs/<run-id>/`
- Plans must be reviewed before execution
- Verification evidence is required before marking work complete
- Protected paths cannot be modified without explicit approval

### Configuration
See `.omni/config.json` for project-specific settings.
<!-- omni:managed:end -->
