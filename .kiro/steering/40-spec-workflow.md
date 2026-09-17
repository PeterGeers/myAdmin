---
inclusion: auto
---

# Spec-Driven Development

This project uses formal specifications for feature development. Specs provide structured documentation from requirements through implementation.

## Spec Organization

Specs are in `.kiro/specs/` organized by domain: `Common/` (cross-cutting), `FIN/` (financial), `STR/` (short-term rental), and `multi-tenant/` (platform evolution — turning myAdmin into the multi-tenant base that hosts SAM-backed modules).

The `multi-tenant/` tree has its own shape: `Analysis/` holds the reasoning docs (start at `overall_roadmap.md`), and each roadmap step gets its own step folder (e.g. `s2-jwt-verification/`) with requirements/design/tasks. See ADR 0003 for the settled model (myAdmin is the base; evolve in place; import apps as SAM-backed modules).

## Typical Spec Structure

Each spec folder contains a requirements/design/tasks trio; supporting docs are added as needed.

1. **requirements.md** — user stories, acceptance criteria, success metrics, out of scope
2. **design.md** — architecture, API contracts, data model, correctness properties, error handling, testing strategy
3. **tasks.md** — phased task breakdown with checkboxes, dependencies

Optional/supporting docs when useful: a `README.md` navigation guide, `analysis.md`,
`OPEN_ISSUES.md`, companion design docs. Note the actual convention in this repo:

- The task file is **`tasks.md`** (lowercase). A `README.md` is optional, not required —
  most `multi-tenant/` step specs do not have one; the roadmap is the index instead.

## Spec Workflow

1. **Analysis** — Understand problem, document options, make decisions
2. **Requirements** — User stories, acceptance criteria, constraints
3. **Design** — Technical approach, APIs, data model, security
4. **Implementation** — Break into phases/tasks, track with checkboxes
5. **Completion** — Mark done, update status, document lessons learned

## When to Use Specs

**Create**: new features, major architecture changes, complex multi-phase work
**Update**: modifying existing features, completing tasks
**Skip**: bug fixes, minor tweaks, config changes, doc updates

## AI Assistant Guidelines

- Check `.kiro/specs/` for existing specs before starting work
- Read the requirements/design first, then review decisions in analysis/ADR docs
- Follow `tasks.md` as the checklist, check off completed tasks
- Update `design.md` if the approach changes; track open items in `OPEN_ISSUES.md`
- When creating specs: choose domain, include requirements/design/tasks, cross-reference
- **Governance definition-of-done:** a step is not complete until any steering/ADRs it
  changes are updated to match (see `00-index.md` governance discipline).

## Best Practices

### Writing Requirements

- User story format: "As a [role], I want [feature], so that [benefit]"
- Clear acceptance criteria, success metrics, out-of-scope items

### Writing Design

- Start with architecture overview and data flow
- Specify API contracts (request/response schemas)
- Document security, performance, and key technical decisions
- **Reference reusable patterns and frameworks**:
  - Generic filter framework (`.kiro/specs/Common/Filters a generic approach/`)
  - Authentication patterns (`backend/src/auth/`, `22-authentication.md`)
  - Multi-tenant patterns (`tenant_context.py`; module plane: `35-sam-module-architecture-sam.md`)
  - Action buttons: BankingProcessor pattern — row-click opens modal, no inline buttons.
    See `32-frontend-ui.md`.
  - Table & modal layout, translation (i18n): `32-frontend-ui.md`
  - End-user documentation: every feature needs a manual section per
    `.kiro/specs/Common/end-user-documentation/`

### Writing Tasks

- Chunks < 1 day, grouped in phases, with dependencies
- Include testing requirements per phase
