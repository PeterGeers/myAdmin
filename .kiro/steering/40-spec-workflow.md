---
inclusion: auto
---

# Spec-Driven Development

This project uses formal specifications for feature development. Specs provide structured documentation from requirements through implementation.

## Spec Organization

Specs are in `.kiro/specs/` organized by domain: `Common/` (cross-cutting, incl. `Common/Serverless-applications/` for the SAM plane — SAM apps, SNS/SES, and the `multi-tenant/` platform-evolution tree), `FIN/` (financial), `STR/` (short-term rental), `ZZP/`, and `Members/` (the Members SAM-backed module — the first app migrated onto the SAM plane; see `35-sam-module-architecture-sam.md`).

> **Module domains vs. the SAM plane.** `Members` (like `FIN` / `STR` / `ZZP`) is a *module/domain* spec tree — it holds that module's feature specs (e.g. `Members/application-app/`, `Members/member-field-search/`). The *platform/SAM-plane* capabilities those features rely on (the handler edge, tenancy, SNS/SES, public intake) live under `Common/Serverless-applications/` and are governed by steering `35-sam-module-architecture-sam.md`. A module feature spec therefore CONSUMES SAM-plane capabilities and references their specs, rather than redefining them.

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
- **Reference relevant reusable patterns and frameworks NOTE when applicable**:
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
- Include use of shell commands see steering [text](41-shell-environment.md)
- **Include the CI/CD tasks per `43-cicd-deploys.md`.** Every spec's `tasks.md` MUST make the
  CI/CD surface explicit — it is part of the work, not an afterthought:
  - the **quality gates** the change must pass (the per-PR CodeQL + GitGuardian today; the
    nightly Full Test Suite; Backend/Frontend CI when re-enabled);
  - the **branch→env deploy** path it rides (`test`→TEST, `main`→PRODUCTION) and WHICH deploy
    workflow(s) its paths trigger (`deploy-sam-*`, `deploy-frontend`), deployed via the codified
    `samconfig.toml` / OIDC pipeline — never a hand-typed deploy;
  - any **new or changed workflow / `samconfig.toml` / IAM-OIDC wiring** the feature needs (a new
    stack, a new deploy path, a new usage plan) as its own task;
  - the **promote `test`→`main`** step as the production-release gate.
  A spec that ships code but names no CI/CD task is incomplete.

### All-planes delivery (no half-shipped features)

A feature is NOT delivered until EVERY plane a user or operator touches reflects the change — not just the backend or the data. That means all of: the SAM module plane (`sam/**`), the Flask/MySQL plane (`backend/src/**`), the React frontend (`frontend/src/**`), the stored DATA / migrations, AND the admin-facing UI. "Backend done" is not "feature done".

- **Enumerate the planes, then write a task per plane.** When a behavior change is planned, list which planes it touches and create a corresponding task for each affected one. A backend/data change that alters what a field *is* — its vocabulary source, its type semantics, a retired-status flag — REQUIRES the matching frontend editor/display change in the SAME spec. Never "backend now, UI later".
- **The trap this prevents:** shipping a model or data change while an admin screen still tells the user to manage the thing the old way — e.g. a field-config modal pointing the admin at a catalog that the very same change is deleting. That mismatch is a defect in the current spec, not a follow-up item for a future one.
- **Definition-of-done for a spec includes:** every affected plane updated, paired tests per plane (change-with-tests), and an explicit check that no UI anywhere still reflects the pre-change model.
- **Cross-reference:** `32-frontend-ui.md`, `30-backend-api-flask-mysql.md`, `35-sam-module-architecture-sam.md`, `39-backend-data-access-sam-dynamodb.md`, `38-sam-module-field-config.md`.
