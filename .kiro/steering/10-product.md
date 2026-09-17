---
inclusion: auto
---

# Product Overview

myAdmin is a **multi-tenant platform base** that hosts distinct application domains for
many tenant organizations under one shared identity. It is evolved **in place** (ADR
0003) — apps are imported as **modules**, including ones **backed by AWS SAM apps**
(Lambda + DynamoDB). Its first and primary app is the finance / administration domain,
but the product is best understood by its building blocks: **modules** (what a tenant
can do), **tenants** (who uses it), and **cross-cutting capabilities** (shared features
and integrations any module can draw on).

> Platform shape, planes, and how apps plug in as modules: `20-platform-architecture.md`.
> Current phase/status: `00-index.md`.

## Modules (what a tenant can enable)

A **module** is a unit of capability a tenant is entitled to via `tenant_modules`. Each
is enabled per tenant independently. Modules are either **Flask-backed** (in-process,
MySQL) or **SAM-backed** (Lambda + DynamoDB) — same registry, same entitlement
(`20-platform-architecture.md`). The registry (`services/module_registry.py`) is the
authoritative list.

### Flask-backed modules (MySQL plane)

- **FIN — Financial Administration.** Bookkeeping built around financial transactions:
  invoice management, banking import, assets/depreciation, budget, and reporting
  (P&L, balance, BTW, Aangifte IB). The transaction model is detailed in
  `20-platform-architecture.md`.
- **ZZP — Freelancer Administration** (depends on FIN). A freelance-invoicing UI over
  the same transaction backbone: contacts, products, time-tracking, debtors → invoices.
- **STR — Short-Term Rental Management.** Autonomous domain (own data, not the finance
  ledger): Airbnb/Booking.com revenue processing, realized-vs-planned bookings, and an
  AI-assisted pricing optimizer.
- **TENADMIN — Tenant Administration.** Cross-cutting user/tenant/system configuration.

### SAM-backed modules (Lambda + DynamoDB plane)

- **members / events / webshop** (the h-dcn domain) — member management, events, and
  webshop / self-service, currently sharing one SAM stack, each entitled per tenant for
  tenants that want end-user capability. Members is the first app being migrated onto
  the platform (`.kiro/specs/multi-tenant/s5-members-first-migration/`).

## Tenants and users (not the same thing)

A **tenant is an organization** using the platform — the membership club, the
bookkeeping firm. It is the isolation boundary (`administration` on the Flask plane,
`tenant_id` on the module plane), never a person.

**Users are the people** who access what a tenant has enabled. They come in two
**audiences**, each in its own Cognito pool (`21-identity.md`):

- **Admins / staff** (Pool A) — operate the tenant (configure it, do the bookkeeping,
  manage members). Every tenant has these.
- **End-users** (Pool B) — members / webshop customers of a tenant. Present **only** for
  tenants that enable end-user-facing modules.

So a tenant is not "admin" or "end-user" — its **enabled modules** determine which
audiences of users it has:

- A tenant with only Flask admin modules (FIN/ZZP/STR/TENADMIN) has **admin users only**
  (e.g. a bookkeeping firm — a few admins, no members).
- A tenant that also enables SAM-backed end-user modules (members/webshop) has **admin
  users plus an end-user population** (e.g. a membership club — staff who run it, and the
  members who log in). One tenant, both audiences.

Whether a tenant has end-users is therefore an outcome of its module set, not a separate
tenant type. Tenant isolation is enforced regardless of audience.

## Cross-cutting capabilities (shared across modules)

Features and integrations that are **not** owned by one module — any module can use
them, and they are configured per tenant where noted.

### Document intake & processing

- **AI extraction (OpenRouter).** Universal invoice/document extraction and image
  parsing via the OpenRouter API, with a model-fallback registry and per-tenant usage
  tracking. Also powers budget AI and STR pricing. A platform capability, not a FIN
  feature.
- **CSV import.** Structured-file ingestion — bank statements (e.g. Rabobank format)
  and declarative CSV aggregation rules for platform files (e.g. Airbnb), with duplicate
  detection.
- **PDF / EML / MHTML processing.** File parsing for document intake, plus a PDF
  validation system (link/URL validation with progress tracking).

### Storage (pluggable per tenant)

Storage provider is a **per-tenant setting** (`invoice_provider`), not a fixed choice:

- **Google Drive** (`google_drive`) — folder-based document storage.
- **S3 shared bucket** (`s3_shared`) — platform-shared bucket.
- **S3 tenant bucket** (`s3_tenant`) — per-tenant bucket.

The storage resolver abstracts these so modules write documents without knowing the
backend. (Consolidating the AWS footprint into the shared account is roadmap S6.)

### Platform services

- **Authentication & entitlement:** AWS Cognito (two audience pools) + verified-JWT
  everywhere (`22-authentication.md`), module entitlement via `tenant_modules`.
- **Notifications:** AWS SNS for alerts; SES for email where configured.
- **Real-time updates:** Server-Sent Events for progress tracking.
- **Reporting/export:** interactive dashboards (Recharts) and Excel/XLSX export.
- **Audit logging:** audit trail across operations.
- **Test/Production mode:** environment-based data-set switching via `.env`.

## Platform rules

- **Two audiences:** admins/staff vs end-users, in separate identity pools
  (`21-identity.md`).
- **Tenant isolation:** every record and request is scoped to a tenant; a user only
  sees data for tenants they belong to. Flask plane scopes by `administration`; module
  plane scopes by `tenant_id`.
- **Tenant-neutral platform:** do not bake one tenant's assumptions into
  platform-level code, naming, or config.
- **Capabilities are shared, entitlement is per-tenant:** a cross-cutting feature
  (AI, storage, notifications) is platform code; whether a tenant *uses* it follows from
  its enabled modules and per-tenant config, never hardcoded.
