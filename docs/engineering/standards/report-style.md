# Feasibility Report Style

Use this format for preliminary implementation research that needs to shape scope, architecture, tradeoffs, and decisions before a full implementation plan is written. A feasibility report is a concise bridge between an idea and a plan.

Feasibility reports must be saved under `docs/research/`.

## Purpose

A feasibility report should answer:

- What is being considered?
- What does the live project/codebase currently support?
- What do official/current external sources say?
- What implementation shapes are realistic?
- What are the tradeoffs technically and practically?
- What decisions shape planning or building?
- What does the agent recommend, and why?

The report should help form an opinion on shape and scope without pretending open decisions are settled.

## Source Rules

- Use the project codebase as source of truth for current implementation state.
- Use official, current sources for vendors, APIs, frameworks, protocols, pricing, limits, licensing, and standards.
- Do not rely on marketing copy, stale docs, prior plans, or remembered behavior when live code or official docs can be checked.
- If a current fact is drift-prone, verify it before writing the report.
- If live verification was not performed, say exactly what was checked instead.
- Cite sources directly in the report with links or local file paths.
- Clearly separate verified facts, recommendations, assumptions, and decisions.

## Report Shape

Start each report with:

- `# <Topic> Feasibility Report`
- `Date`
- `Status`
- `Request`
- `Source scope`
- `Owner`

Then include these sections in order:

1. `Executive Summary`
2. `Question Being Answered`
3. `Source Scope And Method`
4. `Current Project State`
5. `Official / External Findings`
6. `Industry Standard Shape`
7. `Implementation Options`
8. `Technical Implications`
9. `Project Implications`
10. `Risks And Constraints`
11. `Recommended Direction`
12. `Decision Points`
13. `Decision Questions For Discussion`
14. `Next Step If Accepted`
15. `Sources`

## Section Guidance

### Executive Summary

Give the direct answer first. State whether the idea is feasible, under what conditions, and what shape is recommended.

### Question Being Answered

Restate the task in precise terms. If the user used loose wording, translate it into the implementation question being evaluated.

### Source Scope And Method

List what was checked:

- local files, modules, packages, migrations, docs, tests, scripts
- official external docs, standards, APIs, pricing pages, protocol docs
- commands run
- sources intentionally not checked

### Current Project State

Describe what exists in the live codebase. Cite local paths. Treat plans,
brainstorms, and docs as implemented behavior only when the code confirms it.

### Official / External Findings

Summarize current official-source findings. Cite official sources. Note dates when pricing, API behavior, model availability, or vendor features could drift.

### Industry Standard Shape

Describe the clean, modern, conventional way this capability is usually implemented. This is the north star for judging options, not a command to copy blindly.

### Implementation Options

Provide 2-4 realistic options. For each option include:

- description
- when it fits
- technical tradeoffs
- practical/project tradeoffs
- cost or operational impact where relevant
- migration or reversibility impact

### Technical Implications

Explain effects on:

- architecture
- data model
- API/MCP/contracts
- migrations
- providers
- security
- source policy
- tests
- performance
- observability
- deployment

Only include categories that matter for the topic.

### Project Implications

Explain effects on:

- implementation scope
- sequencing
- ownership surfaces
- docs
- changelog/release behavior
- agent orchestration
- user-facing claims
- long-term maintainability

### Risks And Constraints

Call out:

- code-owned risks
- external/provider risks
- cost risks
- source/license risks
- migration risks
- verification scope
- unclear requirements
- assumptions that need confirmation

### Recommended Direction

State the recommendation plainly. Explain why this option best matches the project, codebase, long-term architecture, and industry-standard shape.

Avoid vague phrasing such as "it depends"; immediately name the concrete
dependency when a recommendation depends on another fact.

### Decision Points

Each decision point must include:

- decision name
- options
- technical tradeoffs
- practical/project implications
- recommendation
- reason for the recommendation
- what changes if the user chooses another option

### Decision Questions For Discussion

Print the short version of decision points as questions that can be discussed in chat after the report is saved.

### Next Step If Accepted

State what should happen after the report is accepted:

- write/update implementation plan
- create decision record
- update architecture docs
- run an exploratory draft
- start implementation stream
- gather missing credentials or source access

### Sources

List local and official sources used. Use local paths for code/docs and public URLs for official external sources.

## Decision Point Template

```markdown
### <Decision Name>

Options:

- Option A: <short name>
- Option B: <short name>
- Option C: <short name>

Tradeoffs:

- Option A: <technical and practical implications>
- Option B: <technical and practical implications>
- Option C: <technical and practical implications>

Recommendation: <recommended option>

Why: <reasoning tied to project goals, codebase state, and official findings>

Implication if different: <what must change if another option is chosen>
```

## Writing Rules

- Search before writing. Do not infer current code behavior from old docs.
- Prefer official vendor docs, standards, repository docs, and source code over blog posts or marketing pages.
- Use exact local paths and URLs for sources.
- Keep feasibility claims tied to credentials, quotas, source licensing, and access state.
- Distinguish local feasibility from production feasibility.
- Distinguish implementation cost from operating cost.
- Include source/license/security implications when external data or public responses are involved.
- Keep recommendations opinionated but reversible where architecture should remain provider-agnostic.
- Do not turn the report into a task checklist. The implementation plan owns tasks.
- Keep decision points explicit instead of burying them in prose.
- When report-only changes are made, validate by reading back the Markdown and running docs/changelog checks once those commands exist.

## Chat Handoff

After saving a feasibility report, print the decision questions in chat with:

- the option set
- the recommendation
- the shortest useful rationale

Summarize the report and link to the saved report path.

## Retirement

Feasibility reports are dated source reports. When a report has been consumed:

- Promote permanent decisions into `docs/decisions/` or durable architecture/operations docs.
- Convert accepted direction into `docs/roadmaps/`.
- Move obsolete dated reports to `docs/_legacy/research/` when their useful content has been promoted.
- Keep active docs focused on current operating rules.
