---
inclusion: auto
---

# Product Overview

myAdmin is a comprehensive financial transaction processing and administrative tooling system for managing invoices, banking transactions, and short-term rental (STR) operations.

## Core Modules

### Invoice Management

- AI-powered universal invoice extraction via OpenRouter API
- Declarative CSV aggregation rules for structured files (e.g., Airbnb)
- PDF/EML/MHTML file processing
- Google Drive integration for storage
- Manual edit and approval workflow

### Banking Processor

- CSV bank statement processing (Rabobank format)
- Pattern-based automatic account assignment
- Duplicate detection and filtering
- Bulk transaction import

### STR (Short-Term Rental) Processor

- Airbnb/Booking.com revenue file processing
- Realized vs planned booking separation
- Future revenue summaries
- Multi-platform support

### STR Pricing Optimizer

- AI-powered pricing recommendations with business logic
- Historical vs recommended ADR comparison
- Event-based pricing uplifts
- 14-month pricing strategy generation

### Reports & Analytics

- Interactive dashboards with Recharts
- P&L statements and balance sheets
- BNB revenue analytics (violin/box plots)
- Aangifte IB (Income Tax) declarations
- Excel/XLSX export capabilities

### PDF Validation System

- Google Drive URL validation in transaction records
- Real-time progress tracking
- Automatic file/folder URL resolution
- Manual update for broken links

## Key Features

- **Test/Production Mode**: Environment-based switching via `.env` configuration
- **Multi-tenant Support**: Tenant-based data isolation with AWS Cognito authentication
- **AWS Integration**: SNS notifications for alerts
- **Real-time Updates**: Server-Sent Events for progress tracking
- **Audit Logging**: Comprehensive audit trail for all operations

## Platform Direction — myAdmin as a multi-tenant base

Beyond the finance application, myAdmin is the **base of a multi-tenant platform**
that hosts distinct application domains for many tenant organizations under one shared
identity. It is evolved **in place** (ADR 0003) — additional apps are imported as
**modules**, including ones **backed by AWS SAM apps** (Lambda + DynamoDB).

### Tenants

A tenant is an organization using the platform. Tenants differ in shape:

- **Admin-only tenants** (e.g. finance/bookkeeping orgs): a handful of admin users, no
  end-users. Only the Flask/MySQL plane is used.
- **End-user tenants** (e.g. a membership club with a webshop): admins plus a large
  end-user population. Both planes are used.

Whether a tenant has end-users is an optional capability (a tenant module), not a
platform-wide given.

### Domains hosted as modules

- **Admin / finance domain** (myAdmin itself): bookkeeping, invoicing, banking,
  reporting — for admin-only tenants and admin users of any tenant.
- **Portal-style domains** (e.g. the h-dcn domain): member management, events, and
  webshop / self-service — hosted as **SAM-backed modules** (`members`, `events`,
  `webshop`, currently sharing one SAM stack), each enabled per tenant via
  `tenant_modules` for tenants that want end-user capability.

### Platform rules

- **Two audiences:** admins/staff vs end-users, in separate identity pools (see
  `identity.md`).
- **Tenant isolation:** every record and request is scoped to a tenant; a user only
  sees data for tenants they belong to. Flask plane scopes by `administration`; module
  plane scopes by `tenant_id`.
- **Tenant-neutral platform:** do not bake one tenant's assumptions into
  platform-level code, naming, or config.
