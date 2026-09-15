---
inclusion: auto
---

# System Architecture

## The Transaction-Centric Model

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

## Module Boundaries

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

- **Authentication**: AWS Cognito issues JWTs, validated by `@cognito_required`
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

- **Local dev**: Docker Compose (MySQL 8.0 + Backend)
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
settled direction (see ADR 0003 and `.kiro/specs/multi-tenant/`), and it is evolved
**in place** — there is no separate trunk or workspace.

### The module system (already in code)

Tenanted capability is governed by MySQL, keyed by the `administration` tenant key:

- **`tenant_modules`** — which modules each tenant has enabled (`administration`,
  `module_name`, `is_active`).
- **`MODULE_REGISTRY` / `module_registry.py`** — the registry of available modules
  and their metadata (name, description, `depends_on`, readonly).
- **Provisioning** (`tenant_provisioning_service.py`, `provision_tenant.py`) inserts
  `tenant_modules` rows when a tenant is created.
- Today's modules: **FIN, ZZP, STR, TENADMIN**.

Authorization is the **intersection** of the user's module permissions (from the
token) and the tenant's enabled modules (from `tenant_modules`) — see
`tenant_module_routes.py`.

### Two service planes

- **Plane A — Flask / MySQL (this codebase):** admin, finance (FIN/ZZP/STR),
  tenant governance. Scopes by the `administration` key; queries MySQL directly.
- **Plane B — AWS SAM / Lambda / DynamoDB (SAM-backed modules):** apps imported as
  modules that keep a serverless stack (e.g. the h-dcn domain — the `members`,
  `events`, `webshop` modules sharing one SAM stack). Scopes by a `tenant_id`
  partition key.

### The SAM-backed module contract (roadmap S1)

A module may be **backed by an AWS SAM app** rather than in-process Flask code. The
generic contract:

1. **Register** the module in `MODULE_REGISTRY`.
2. **Entitle** tenants via `tenant_modules` (unchanged mechanism).
3. **Authorize** requests from the **verified** Cognito token — never from unverified
   headers. A Lambda must **not** query MySQL per request; entitlement is projected
   into the token (roadmap S4), and tenant-level governance is projected read-only
   into DynamoDB (roadmap S3, one-directional MySQL→DynamoDB).
4. **Scope** all data by `tenant_id` (partition key + IAM `LeadingKeys`).

The full reference a module author follows — the four seams in detail, with the
registry accessors, the no-request-time-MySQL rule, and the enabling dependencies — is
`.kiro/specs/multi-tenant/s1-prepare-platform/module-contract.md`.

### Governance rules for this evolution

- **Fold platform rules into this steering set; do not fork it.** New rules extend
  the existing `.kiro/steering` files (or add narrowly-scoped `fileMatch` files).
- MySQL is the **system of record** for tenant governance (`tenants`,
  `tenant_modules`, `user_tenant_roles`); any DynamoDB copy is a **read-only
  projection**, never written back.
- Identity uses **two audience-split Cognito pools** (Pool A admin/staff, Pool B
  optional per-tenant end-users). See `.kiro/specs/multi-tenant/Analysis/`.
- Each roadmap step (S1…S10) gets its own spec under `.kiro/specs/multi-tenant/`
  before execution; `overall_roadmap.md` is the index.
