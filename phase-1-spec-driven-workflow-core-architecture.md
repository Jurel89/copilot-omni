# Phase Gate Checklist

Use this checklist before promoting any phase.

## Entry gate
- The phase PRD and architecture document exist and are versioned.
- Dependencies from previous phases are accepted and released.
- Test fixtures and benchmark scenarios for this phase are defined.
- Scope for the phase is frozen.

## Build-complete gate
- All planned deliverables exist.
- All blocking bugs are triaged.
- Docs match the implemented command surface and artifact layout.
- Config schema and migrations are updated.

## Verification gate
- Unit, integration, and adversarial tests pass.
- Cross-platform packaging and install checks pass where applicable.
- Rollback and resume scenarios have been exercised.
- Performance for new hot paths is measured and recorded.

## Safety gate
- Policy and guardrail changes have explicit tests.
- Redaction, privacy, and retention changes are validated.
- New attack surfaces have a threat note and mitigation entry.
- Auditability for new actions is present.

## UX gate
- The current phase, next action, and failure remediation are visible in the UX.
- Help text, examples, and command outputs are reviewed.
- Error messages include stable reason codes and human-readable remediation.

## Promotion gate
- Acceptance criteria in the phase PRD all pass.
- Regression suite against earlier phases passes.
- Soak run on representative repositories passes.
- Remaining known defects are documented and accepted.

## Reopen criteria
Reopen the previous phase instead of advancing if:
- a blocker is “worked around” by the next phase,
- performance is outside budget on the main workflows,
- a policy or security regression is introduced,
- installability or upgrade reliability drops below target.
