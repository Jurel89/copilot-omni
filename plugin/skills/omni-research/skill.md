---
name: omni-research
description: Conduct structured research combining web findings, repository evidence, and memory
---

# omni-research Skill

## Purpose
Conduct structured, multi-source research on a given query and produce a research report with explicit provenance tagging.

## Usage
```
/omni-research <query>
```

## Workflow

1. **Parse Query**: Identify key concepts and search terms from the user's research question
2. **Memory Search**: Use `omni_memory_search` to find relevant prior decisions, specs, and notes
3. **Repo Exploration**: Use `omni_repo_map` to understand codebase structure relevant to the query
4. **Generate Report**: Use `omni_research` MCP tool to compile a structured report

## Research Report Format

The report includes:
- **Provenance**: Source tracking (web, repository, memory, external)
- **Findings**: Tagged as fact, inference, or open_question with confidence levels
- **Open Questions**: Explicitly listed unknowns
- **Summary**: Concise overview of research results

## Rules

- Read-only: Never modify any files during research
- Cite sources for every factual claim
- Separate facts from inferences clearly
- Mark all uncertainty as open questions
