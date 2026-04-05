# Tasks — End-User Documentation

## Phase 1: MkDocs Setup (2 hours)

- [x] 1.1 Create `docs/` folder with `mkdocs.yml` configuration (including i18n plugin)
- [x] 1.2 Install MkDocs Material theme, print-site plugin, and `mkdocs-static-i18n`
- [x] 1.3 Create folder structure for all modules (empty `index.md` + `index.en.md` files)
- [x] 1.4 Verify `mkdocs serve` works locally with language switcher
- [x] 1.5 Add Flask route to serve built docs at `/docs/`
- [x] 1.6 Add `REACT_APP_DOCS_URL` to frontend `.env` and `.env.example`

## Phase 2: Getting Started & Supporting Pages (4 hours)

Each page written in Dutch first (`.md`), then English (`.en.md`).

- [x] 2.1 Write `index.md` + `index.en.md` — homepage with module overview
- [x] 2.2 Write `getting-started/overview.md` + `.en.md` — what is myAdmin
- [x] 2.3 Write `getting-started/first-login.md` + `.en.md` — login and navigation
- [x] 2.4 Write `getting-started/test-vs-production.md` + `.en.md` — mode explanation
- [x] 2.5 Write `getting-started/common-workflows.md` + `.en.md` — quick task overview
- [x] 2.6 Write `glossary.md` + `glossary.en.md` — Dutch financial terms (NL→EN and EN→NL)
- [x] 2.7 Write `faq.md` + `faq.en.md` — common questions (10-15 entries)
- [x] 2.8 Write `changelog.md` + `changelog.en.md` — initial version entry

## Phase 3: Module Documentation (16-20 hours)

Each task = Dutch (`.md`) + English (`.en.md`) version. Write Dutch first, then translate.

### Banking

- [x] 3.1 Write `banking/index.md` — overview
- [x] 3.2 Write `banking/importing-statements.md`
- [x] 3.3 Write `banking/reviewing-transactions.md`
- [x] 3.4 Write `banking/pattern-matching.md`
- [x] 3.5 Write `banking/handling-duplicates.md`

### Invoices

- [x] 3.6 Write `invoices/index.md` — overview
- [x] 3.7 Write `invoices/uploading-invoices.md`
- [x] 3.8 Write `invoices/ai-extraction.md`
- [x] 3.9 Write `invoices/editing-approving.md`
- [x] 3.10 Write `invoices/google-drive.md`

### STR

- [x] 3.11 Write `str/index.md` — overview
- [x] 3.12 Write `str/importing-bookings.md`
- [x] 3.13 Write `str/realized-vs-planned.md`
- [x] 3.14 Write `str/revenue-summaries.md`

### STR Pricing

- [x] 3.15 Write `str-pricing/index.md` — overview
- [x] 3.16 Write `str-pricing/viewing-recommendations.md`
- [x] 3.17 Write `str-pricing/event-pricing.md`
- [x] 3.18 Write `str-pricing/applying-suggestions.md`

### Reports

- [x] 3.19 Write `reports/index.md` — overview
- [x] 3.20 Write `reports/dashboards.md`
- [x] 3.21 Write `reports/pnl-balance-sheets.md`
- [x] 3.22 Write `reports/exporting-excel.md`

### Tax

- [x] 3.23 Write `tax/index.md` — overview
- [x] 3.24 Write `tax/btw.md`
- [x] 3.25 Write `tax/income-tax-ib.md`
- [x] 3.26 Write `tax/toeristenbelasting.md`

### PDF Validation

- [x] 3.27 Write `pdf-validation/index.md` — overview
- [x] 3.28 Write `pdf-validation/checking-fixing-links.md`

## Phase 4: Admin Documentation (7 hours)

Each task = Dutch + English version. Two separate sections matching the codebase architecture.

### SysAdmin (Platform Management — `admin/`)

- [x] 4.1 Write `admin/index.md` + `.en.md` — SysAdmin overview (platform-level responsibilities)
- [x] 4.2 Write `admin/tenant-management.md` — create/configure/delete tenants, enable modules, invite first tenant admin
- [x] 4.3 Write `admin/docker-deployment.md` — Docker setup, containers, maintenance
- [x] 4.4 Write `admin/database-admin.md` — MySQL administration, migrations, backups
- [x] 4.5 Write `admin/troubleshooting.md` — common platform issues and solutions

### Tenant Admin (Organization Management — `tenant-admin/`)

- [x] 4.6 Write `tenant-admin/index.md` + `.en.md` — Tenant Admin overview (organization-level responsibilities)
- [x] 4.7 Write `tenant-admin/tenant-settings.md` — tenant configuration, templates, account management
- [x] 4.8 Write `tenant-admin/user-management.md` — add users to tenant, assign/remove roles
- [x] 4.9 Write `tenant-admin/audit-logging.md` — audit trail, monitoring activity

## Phase 5: In-App Help Components (3 hours)

### Help Components

- [x] 5.1 Create `helpLinks.ts` — PageType-to-docs mapping (uses `currentPage` state, not URL routes)
- [x] 5.2 Create `HelpButton.tsx` — question mark icon component (receives `page` prop)
- [x] 5.3 Create `HelpDrawer.tsx` — slide-out panel with Markdown rendering + fallback to new tab
- [x] 5.4 Create `FieldHelp.tsx` — info icon with tooltip + "Learn more" link
- [x] 5.5 Create `index.ts` — barrel export
- [x] 5.6 Add `react-markdown` dependency to frontend

### Header Integration (single change covers all pages)

- [x] 5.7 Add `HelpButton` to the shared page header in `App.tsx` (next to TenantSelector and UserMenu)
- [x] 5.8 Extract `renderPageHeader()` helper function to reduce header duplication across pages

### Field-Level Help

- [x] 5.9 Add FieldHelp tooltips to key actions (Apply Patterns, Check Duplicates, AI Extract, Test/Production toggle)

## Phase 6: Build & Deploy (2 hours)

- [x] 6.1 Add `mkdocs build` to Docker build process
- [x] 6.2 Configure Flask to serve `docs/site/` at `/docs/`
- [x] 6.3 Test in-app help drawer fetches docs correctly
- [x] 6.4 Test fallback (new tab) when drawer fetch fails
- [x] 6.5 Add print-site plugin verification
- [x] 6.6 Delete old `Manuals/` HTML files

## Notes

- Phase 3 is the biggest effort — can be done module by module
- Phases 1-2 and 5 can run in parallel
- Each doc page follows the page template from design.md
- Screenshots can be added incrementally
- Write Dutch (`.md`) first, then translate to English (`.en.md`)
- i18n plugin: `mkdocs-static-i18n` handles language switching automatically
- Total estimated time: 34-38 hours (roughly doubled due to bilingual content)
