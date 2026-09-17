---
inclusion: auto
---

# Steering Index — how the governance set fits together

This folder is myAdmin's active governance. Files are grouped by a numeric prefix so
the flat folder sorts into layers. Read this first to see the shape; each file owns
its topic and nothing else (facts live in exactly one place).

## The four layers

| Prefix | Layer | Files |
| --- | --- | --- |
| `0x` | **Index / meta** | `00-index.md` (this file) |
| `1x` | **Product & structure** | `10-product.md`, `11-tech-stack.md`, `12-project-structure.md` |
| `2x` | **Platform architecture** | `20-platform-architecture.md`, `21-identity.md`, `22-authentication.md`, `23-aws-accounts.md` |
| `3x` | **Coding conventions** | `30-backend-api-flask-mysql.md`, `31-backend-database-flask-mysql.md`, `32-frontend-ui.md`, `33-frontend-testing.md`, `34-backend-testing.md`, `35-sam-module-architecture-sam.md` |
| `4x` | **Process & environment** | `40-spec-workflow.md`, `41-shell-environment.md`, `42-local-dynamodb-testing.md` |

## Load behavior (when each file is in context)

Kiro loads steering three ways. Each file declares its mode in front-matter.

| Mode | Meaning | Files |
| --- | --- | --- |
| `auto` | Always in context | `00`, `10`, `11`, `12`, `20`, `21`, `22`, `23`, `35`, `40`, `41` |
| `fileMatch` | Loaded only when editing matching files | `30` (backend routes/services), `31` (backend `*.py`), `32` (frontend `*.ts[x]`), `33` (frontend tests), `34` (`test_*.py`) |
| `manual` | Loaded on explicit request | `42` (local DynamoDB work) |

Rationale for the non-obvious modes:
- `35-sam-module-architecture-sam.md` is **auto** — the layering rule governs the active
  S5 app migration, so it should always be present, not opt-in.
- `42-local-dynamodb-testing.md` is **manual** — only relevant while actually running
  local DynamoDB; keeping it out of every context avoids noise.

## Reading order for a new contributor

1. `10-product.md` — what the platform is and why.
2. `20-platform-architecture.md` — the two planes and how apps plug in as modules.
3. `21-identity.md` + `22-authentication.md` — who a request is, and how that's trusted.
4. `12-project-structure.md` + `11-tech-stack.md` — where code lives and what it's built with.
5. The relevant `3x` convention file for whatever you're about to edit.
6. `40-spec-workflow.md` before starting any non-trivial change.

## The one-paragraph model

myAdmin is a Flask/MySQL finance app being evolved **in place** into a multi-tenant
**platform base** (ADR 0003). Apps are hosted as **modules**. Two planes: **Plane A**
(Flask/MySQL — admin/finance; scopes by the `administration` key) and **Plane B**
(AWS SAM / Lambda / DynamoDB — imported apps like h-dcn's `members`/`events`/`webshop`;
scopes by `tenant_id`). Identity is shared via **two Cognito pools split by audience**
(Pool A admin/staff, Pool B optional per-tenant end-users). **MySQL is the system of
record** for tenant governance; facts reach the module plane one-directionally — via a
**token entitlement claim** (per-user, S4) or a **read-only DynamoDB projection**
(tenant-level, S3), never a request-time MySQL query from a Lambda. Every backend trusts
identity **only** from a verified JWT (ADR 0004).

## Platform status (single source; authoritative detail in the roadmap)

Point-in-time status lives **only here** and in the roadmap — not scattered through the
platform files. Authoritative source of truth:
`.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`.

| Step | State |
| --- | --- |
| S1 — prepare platform for SAM-backed modules | ✅ Done (ADR 0003) |
| S2 — verify JWT on both planes | ✅ Done (ADR 0004); Flask plane live in prod |
| S3 — claims + MySQL system-of-record + →DynamoDB projection | ✅ Done (ADR 0005); prod `governance_projection` table exists, empty until S5 registers real modules |
| S4 — entitlement projected into the token | ✅ Functions built + tested (ADR 0006); **live Pool A trigger deferred to S5** |
| S5 — first app migration (Members) → Go/No-Go | 🔜 In progress (spec written; build gated on user approval) |
| S6–S10 — AWS move, frontend merge, decommission | ⏳ Not started |

Cognito pools (detail in `23-aws-accounts.md`):
- **Pool A** (`myAdmin`, `eu-west-1_Hdp40eWmu`) — production admin pool, kept as-is.
- **Test pool** (`myAdmin-test`, `eu-west-1_xyrlzfqbl`) — standing Essentials pool; all
  identity work validated here before prod.
- **Pool B** — deferred; addable config-only via the S2 issuer registry.
- **Legacy** `_OAT3oPCIm` + `_VtKQHhXGN` — decommissioned (deleted). `_fcUkvwjH5`
  (nonprofit H-DCN) — **kept while h-dcn runs**.

## Governance discipline

- **Fold platform rules into these files; never fork the set.** New rules extend an
  existing file or add a narrowly-scoped `fileMatch` file.
- **A step isn't done until the steering it changes is updated** (roadmap's
  definition-of-done clause).
- **ADRs are append-only** — one per material decision; supersede, never rewrite.
  ADRs are the decision log; steering is the active-rules layer that tracks current truth.
