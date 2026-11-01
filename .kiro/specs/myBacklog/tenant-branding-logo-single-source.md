# SPEC CANDIDATE: One tenant branding logo, reused by every feature

**Problem (observed 2026-10-30 while trying to put h-dcn's logo on the member application form):**
a tenant's logo is configured in THREE disconnected places, so the same logo does not appear across
features and a tenant would have to set it up three times. The user's ask is simple — "one logo on
all features (public / internal / …)" — but today there is no single source.

## The three fragmented logo configs (the evidence)

| Config | Where it lives | Who reads it | Serving |
| --- | --- | --- | --- |
| `branding.company_logo_s3_key` | param (tenant), object in `myadmin-shared-production/<tenant>/branding/…` | (nothing today — a resolver gap) | shared bucket (not public) |
| `str_branding` / `zzp_branding.company_logo_s3_key` | param (tenant) | `services/logo_resolver.py` → invoice PDF + email signature (inline base64 data URI) | shared bucket, resolved server-side |
| `landing_page.logo_url` | param (tenant), object in `myadmin-public-pages-production/<tenant>/landing-pages/…` | landing page publish → `landing.json` → public pages | public-pages bucket via CloudFront |

Concrete symptom: h-dcn HAS a logo at `branding.company_logo_s3_key`
(`h-dcn/branding/ast_01M5F88KBRXM0KEM49BKCQJDSY_company_logo.jpg`, verified in S3), but NO feature
shows it: the invoice resolver reads `str_/zzp_branding` (different namespace → miss), and the
landing/application-form path reads `landing_page.logo_url` (not set; different bucket). The logo is
uploaded but orphaned.

## Goal

ONE tenant branding logo, ONE source of truth, resolved by ONE reusable helper that every feature
calls: the member application form, public landing pages, the internal UI, invoices/email, PDFs.
A tenant uploads/sets the logo ONCE; it appears everywhere.

## Direction (to design in the spec)

- **Single source:** the tenant branding logo = `branding.company_logo_s3_key` (consolidate the
  `str_/zzp_branding` copies onto it; keep `logo_resolver`'s provider-aware S3/Google-Drive logic).
- **Single resolver:** one `resolve_tenant_logo(tenant)` that reads the ONE source and returns the
  logo in the shape each consumer needs (inline data URI for server-rendered PDFs/email/public
  reads; a served URL where a public bucket/CDN is appropriate). No per-feature namespace.
- **Public exposure:** a small public, tenant-addressed read so unauthenticated surfaces (the member
  application form, public pages) can show the logo WITHOUT depending on a published landing page.
  Inline data URI avoids the "logo is in the non-public shared bucket" serving gap entirely.
- **Migration:** fold existing `str_/zzp_branding.company_logo_*` and `landing_page.logo_url` onto
  the single `branding` source; keep back-compat reads during the transition
  (expand → migrate → contract), per the SAM-plane migration-framework thinking.

## Why a spec, not a quick fix

It spans the Flask branding resolver, the landing-page publish pipeline, the SAM member application
form (spec 13 R5), invoice/email rendering, and per-tenant param migration. Converging a live logo
path carelessly would break invoices/landing pages. Scope it deliberately; land spec 13's R5 first
consuming the single `branding` source so the application form is already aligned.

## Relates to
- `.kiro/specs/Members/13 - application-form-rendering-polish/` R5 (consumes the single source).
- `services/logo_resolver.py`, `landing_page_publish_service.py`, `parameter_schema.py`
  (`str_/zzp_branding`), the landing-page image upload (`image_endpoints.py`).
- The S3 bucket split (shared vs public-pages) in `infrastructure/` — the serving caveat.
