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
