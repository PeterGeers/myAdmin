---
inclusion: auto
---

# System Architecture

> Current phase/status of the platform evolution lives in `00-index.md` (single source)
> and `.kiro/specs/multi-tenant/Analysis/overall_roadmap.md`. This file describes the
> architecture *as it is*, not step status.

## The Transaction-Centric Model (finance app)

The table `mutaties` is the backbone of the financial administration. Every data-entry workflow ultimately produces transactions; every report consumes them via the view `vw_mutaties`.

```
                    ┌─────────────────────────┐
                    │     mutaties table       │
                    │  (financial transactions)│
                    └────────────┬────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
    PRODUCERS                    │                  CONSUMERS
    (write to mutaties)          │             (read from vw_mutaties)
         │                       │                       │
  ┌──────┴──────┐               │              ┌────────┴────────┐
  │  Banking    │  CSV import   │              │  P&L Report     │
  │  Invoices   │  AI extract   │              │  BTW Report     │
  │  Assets     │  depreciation │              │  Balance        │
  │  ZZP        │  invoice gen  │              │  Aangifte IB    │
  └─────────────┘               │              │  Mutaties Report│
                                │              │  Toeristenbelast│
                                │              └─────────────────┘
                                │
                           Budget references
                           mutaties for actuals
```

## Module Boundaries (finance app)

### FIN — Financial Administration (transaction-centric)

Everything in FIN revolves around `mutaties`:

- **Banking**: imports CSV bank statements → writes transactions
- **Invoices**: AI-powered PDF extraction → writes transactions
- **Assets**: manages fixed assets, generates depreciation → writes transactions
- **Budget**: planning layer, compares against actual transactions
- **Reports**: all read from `vw_mutaties` (P&L, Balance, BTW, Aangifte IB, etc.)

### ZZP — Freelance Administration (transaction-centric)

ZZP is a domain-specific UI on top of `mutaties`. Supporting entities (contacts, products, time-tracking, debtors) feed the invoice workflow, but the end result is always transactions written to `mutaties`.

### STR — Short-Term Rental (autonomous)

STR operates independently with its own data model. It does NOT write to or read from `mutaties`. It has its own tables for bookings, pricing, and revenue. Reports in STR query STR-specific data, not `vw_mutaties`.

### Admin — System & Tenant Administration

Cross-cutting: user management, tenant configuration, system settings. Not transaction-related.

## Key Integration Points

```
AWS Cognito ──→ JWT auth ──→ @cognito_required
                                    │
                              @tenant_required
                                    │
                              administration column
                                    │
                              tenant-scoped queries
```

- **Authentication**: AWS Cognito issues JWTs, validated by `@cognito_required` (verified
  signature — `22-authentication.md`)
- **Tenant isolation**: `@tenant_required` injects tenant context; every query filters by `administration` column
- **Database access**: all through `DatabaseManager` — never raw `mysql.connector`
- **File storage**: Google Drive for invoice PDFs
- **AI extraction**: OpenRouter API for invoice parsing
- **Notifications**: AWS SNS for alerts

## Data Flow: Invoice Lifecycle

```
PDF/EML upload → AI extraction (OpenRouter) → review/approve → mutaties
                                                                  │
                                                          Google Drive (PDF stored)
                                                                  │
                                                          vw_mutaties → Reports
```

## Data Flow: Banking Lifecycle

```
CSV upload → parse (Rabobank format) → pattern matching → duplicate check → mutaties
                                              │                                │
                                      auto-assign accounts              vw_mutaties → Reports
```

## Environment Model

- **Local dev**: Docker Compose (MySQL 9.4 + Backend + DynamoDB Local)
- **Production**: Railway (MySQL native + Backend service)
- **Config**: environment variables, never hardcoded credentials
- **Modes**: `TEST_MODE` flag switches between test/production data sets

## Frontend Module Mapping

| Module | URL prefix | Role gate    | Data source                    |
| ------ | ---------- | ------------ | ------------------------------ |
| FIN    | `/fin/*`   | fin_read     | mutaties / vw_mutaties         |
| ZZP    | `/zzp/*`   | zzp_read     | mutaties (via invoices)        |
| STR    | `/str/*`   | str_read     | own tables (bookings, pricing) |
| Admin  | `/admin/*` | admin_manage | system/tenant config           |

## What Belongs Where

| Question                                   | Answer                                     |
| ------------------------------------------ | ------------------------------------------ |
| Touches `mutaties` directly?               | FIN module                                 |
| Produces invoices → `mutaties`?            | FIN (AI invoices) or ZZP (manual invoices) |
| STR bookings/pricing?                      | STR module — autonomous                    |
| Shared UI components (filters, charts)?    | `Common/` specs, `components/common/` code |
| Cross-tenant or system-wide?               | Admin module                               |
| Reusable pattern (caching, i18n, filters)? | `Common/` spec + steering doc              |

## Platform Evolution — myAdmin as the multi-tenant base

myAdmin is not only the finance application; it is the **platform base** for a
multi-tenant system that hosts additional applications as **modules**. This is a
settled direction (ADR 0003 and `.kiro/specs/multi-tenant/`), evolved **in place** —
there is no separate trunk or workspace.

### The module system (already in code)

Tenanted capability is governed by MySQL, keyed by the `administration` tenant key:

- **`tenant_modules`** — which modules each tenant has enabled (`administration`,
  `module_name`, `is_active`).
- **`MODULE_REGISTRY` / `module_registry.py`** — the registry of available modules
  and their metadata (name, description, `depends_on`, readonly).
- **Provisioning** (`tenant_provisioning_service.py`, `provision_tenant.py`) inserts
  `tenant_modules` rows when a tenant is created.
- Today's modules: **FIN, ZZP, STR, TENADMIN**.

Authorization is the **intersection** of the user's module permissions and the
tenant's enabled modules (from `tenant_modules`) — see `tenant_module_routes.py`.

### Two service planes

- **Plane A — Flask / MySQL (this codebase):** admin, finance (FIN/ZZP/STR),
  tenant governance. Scopes by the `administration` key; queries MySQL directly.
- **Plane B — AWS SAM / Lambda / DynamoDB (SAM-backed modules):** apps imported as
  modules that keep a serverless stack (e.g. the h-dcn domain — the `members`,
  `events`, `webshop` modules sharing one SAM stack). Scopes by a `tenant_id`
  partition key. Layering rule: `35-sam-module-architecture-sam.md`.

### The SAM-backed module contract

A module may be **backed by an AWS SAM app** rather than in-process Flask code. The
generic contract (the four seams):

1. **Register** the module in `MODULE_REGISTRY`.
2. **Entitle** tenants via `tenant_modules` (unchanged mechanism).
3. **Authorize** requests from the **verified** Cognito token — never from unverified
   headers. A Lambda must **not** query MySQL per request; entitlement is projected
   into the token, and tenant-level governance is projected read-only into DynamoDB.
4. **Scope** all data by `tenant_id` (partition key + IAM `LeadingKeys`).

Full reference: `.kiro/specs/multi-tenant/s1-prepare-platform/module-contract.md`.

### Governance rules for this evolution

- **Fold platform rules into this steering set; do not fork it.** New rules extend
  the existing files (or add narrowly-scoped `fileMatch` files).
- **MySQL is the tenant system of record.** `tenants`, `tenant_modules`, and
  `user_tenant_roles` are authoritative for tenant governance — which tenants exist,
  which modules each has enabled, and each user's per-tenant roles — for **all**
  tenants, including SAM-backed-module tenants. Authority does **not** move to the
  module plane and **no module owns a writable copy**: the `sam/` plane has no MySQL
  client and authorizes from the verified token only. A module's need for tenant facts
  is met one-directionally — via the token (entitlement) or the read-only DynamoDB
  projection — never a request-time MySQL query from a Lambda.
- **The MySQL→DynamoDB projection is one-directional.** Any DynamoDB copy of governance
  data is a **read-only projection**, governed by these invariants:
  - **Write-only, single writer:** the sync is the **sole** writer of the projection
    table; it makes **zero** MySQL writes. Data flows MySQL→DynamoDB only, never back.
  - **Versioned + idempotent:** each item carries a monotonic `version`; conditional
    writes make re-runs on unchanged source no-ops.
  - **Tenant-scoped:** partition key `tenant_id` (== `administration`) is the tenancy
    boundary, enforced by IAM `dynamodb:LeadingKeys`.
  - **Module reads only:** the module plane reads **only** its own `tenant_id`
    partition and **never** writes the projection or MySQL.
  - **Bounded, documented staleness:** on-change sync triggers + a periodic
    reconciliation backstop keep it converged; the read side invalidates on `version`.

  Production table `governance_projection` (region `eu-west-1`, `PAY_PER_REQUEST`,
  managed **outside** CloudFormation with retain / human-only deletion). Full detail:
  `.kiro/specs/multi-tenant/s3-claims-and-projection/`.
- **Entitlement is projected into the token at issuance, not read per request.** A
  Cognito V2 **Pre-Token-Generation Lambda** computes each user's resolved per-tenant
  entitlement (roles ∩ active modules, via the single pure resolver
  `backend/src/auth/entitlement_resolver.py`) and stamps a compact, versioned
  `custom:entitlements` claim **additively** (never touching `cognito:groups` /
  `custom:tenants`). The **token is the per-user path**; the DynamoDB projection is the
  **tenant-level path** — do not conflate. Invariants:
  - **Reads the DynamoDB projection, NOT MySQL** — keyed by the user's `custom:tenants`
    partitions, via boto3 + IAM; honors the "a module Lambda never opens a MySQL
    connection" contract; fits Cognito's ~5s budget. Empty projection → empty
    entitlement is a valid, handled outcome.
  - **Account placement (`23-aws-accounts.md`):** the Lambda runs in the **data account**
    (same-account read); **Pool A** (identity account) attaches its trigger
    **cross-account** — the *invoke* is cross-account, the *data read* is not.
  - **One rule, two carriers:** the token claim and the Flask plane's `role_cache.py`
    decision share the one resolver, so they never disagree for the same state. Bounded
    staleness = the access-token TTL (Pool A: 60 min); the sensitive-capability subset is
    re-validated server-side (three-state `has_capability` → `None` = consult).
  - **Fail-safe / additive:** a resolution failure omits the claim (login still succeeds).
  - **Adoption model:** delivered as the vendored `sam/shared` toolkit that a SAM-backed
    module adopts — **replacing** its own unverified auth while **reusing** its
    business-authz + HTTP plumbing. Detail:
    `.kiro/specs/multi-tenant/s4-token-entitlement-projection/` + ADR 0006.
- Identity uses **two audience-split Cognito pools** — see `21-identity.md`.
- Each roadmap step gets its own spec under `.kiro/specs/multi-tenant/`;
  `overall_roadmap.md` is the index.
