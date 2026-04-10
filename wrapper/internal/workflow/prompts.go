package workflow

import "fmt"

func DiscussPrompt(userPrompt string) string {
	return fmt.Sprintf(`You are running the bounded discuss phase for Copilot Omni.

User request:
%s

Your job:
- Clarify the feature, constraints, assumptions, and scope implied by the request.
- Focus on requirements discovery, not implementation details.
- Call out explicit constraints, non-goals, and open questions that materially affect scope.

Output format:
- Return only a concise requirements summary in markdown.
- Include sections named: Objective, Requirements, Constraints, Open Questions, Scope Notes.
- Do not produce code, task plans, or JSON.
`, userPrompt)
}

func SpecPrompt(userPrompt, discussOutput string) string {
	return fmt.Sprintf(`You are running the bounded spec phase for Copilot Omni.

Original user request:
%s

Discussion summary:
%s

Write a formal specification in markdown.

Requirements:
- Include the headings: Objective, Requirements, Acceptance Criteria, Constraints.
- Keep the spec concrete, reviewable, and faithful to the request and discussion summary.
- Prefer precise statements over brainstorming.

Output format:
- Return only markdown.
- Do not wrap the markdown in code fences.
- Do not output JSON.
`, userPrompt, discussOutput)
}

func PlanPrompt(specContent string) string {
	return fmt.Sprintf(`You are running the bounded plan phase for Copilot Omni.

Specification:
%s

Generate an implementation plan as valid JSON.

Requirements:
- Return a single JSON object with fields: run_id, version, tasks.
- tasks must be an array.
- Each task object must contain: id, title, description, dependencies, file_targets, verification_cmd, rollback_note.
- dependencies and file_targets must be JSON arrays.
- verification_cmd and rollback_note must be non-empty strings.
- Keep tasks atomic, ordered by dependency, and directly traceable to the spec.

Output format:
- Return only raw JSON.
- Do not wrap the JSON in markdown code fences.
- Do not add commentary before or after the JSON.
`, specContent)
}

func ReviewPrompt(specContent, planContent string) string {
	return fmt.Sprintf(`You are running the bounded review phase for Copilot Omni.

Specification:
%s

Plan:
%s

Review the plan against the specification.

Checks:
- Confirm every spec requirement is covered by one or more plan tasks.
- Confirm every task includes a verification command.
- Confirm every task includes a rollback note.
- Flag gaps, ambiguity, risky sequencing, or missing coverage.

Output format:
- Return structured plain text.
- Prefix each finding line with either BLOCKING: or WARNING:.
- End with a SUMMARY: line that states whether execution should proceed.
- Do not output JSON.
`, specContent, planContent)
}
