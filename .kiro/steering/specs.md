# Spec-Driven Development

This project uses formal specifications for feature development. Specs provide structured documentation from requirements through implementation.

## Spec Organization

Specs are in `.kiro/specs/` organized by domain: `Common/` (cross-cutting), `FIN/` (financial), `STR/` (short-term rental).

## Typical Spec Structure

Each spec folder contains:

1. **README.md** — Navigation guide with reading order, status, change log
2. **requirements.md** — User stories, acceptance criteria, success metrics, out of scope
3. **design.md** — Architecture, API contracts, database schema, security, performance
4. **TASKS.md** — Phased task breakdown with checkboxes, time estimates, dependencies

Supporting docs as needed: `analysis.md`, `OPEN_ISSUES.md`, `IMPACT_ANALYSIS_SUMMARY.md`, `issues.md`

## Spec Workflow

1. **Analysis** — Understand problem, document options, make decisions
2. **Requirements** — User stories, acceptance criteria, constraints
3. **Design** — Technical approach, APIs, database, security
4. **Implementation** — Break into phases/tasks, track with checkboxes
5. **Completion** — Mark done, update status, document lessons learned

## When to Use Specs

**Create**: new features, major architecture changes, complex multi-phase work
**Update**: modifying existing features, completing tasks
**Skip**: bug fixes, minor tweaks, config changes, doc updates

## AI Assistant Guidelines

- Check `.kiro/specs/` for existing specs before starting work
- Read README first, then review decisions in analysis/IMPACT docs
- Follow TASKS.md as checklist, check off completed tasks
- Update design.md if approach changes, track issues in OPEN_ISSUES.md
- When creating specs: choose domain, include README/requirements/design/tasks, cross-reference

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
  - Template management patterns (Phase 2.6)
  - Authentication patterns (`backend/src/auth/`)
  - Multi-tenant patterns (`tenant_context.py`)
  - Action buttons: BankingProcessor pattern — row-click opens modal, no inline buttons. Primary actions (Add, Export, Import) in page header. See `.kiro/specs/Common/parameter-driven-config/frontend-tasks.md`
  - Table & modal layout: Chakra UI `Table` with sortable headers, hover rows, row-click to `Modal`. Clean rows — badges and read-only data only. Modals handle CRUD.
  - Translation (i18n): `useTranslation()` with namespaced keys. Conventions: `.kiro/specs/Common/Internationalization/TRANSLATION_KEY_CONVENTIONS.md`. Guide: `.kiro/specs/Common/Internationalization/DEVELOPER_GUIDE.md`
  - End-user documentation: every feature needs a manual section per `.kiro/specs/Common/end-user-documentation/`

### Writing Tasks

- Chunks < 1 day, grouped in phases, with time estimates and dependencies
- Include testing requirements per phase
