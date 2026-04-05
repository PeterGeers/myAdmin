# Requirements — End-User Documentation

## Guiding Principle

All documentation must be task-oriented, written from the user's perspective. "How do I import my bank statements?" — not "The system processes CSV files using pandas with Latin-1 encoding." No column mappings, no code snippets, no database schemas in user-facing docs. Technical details belong in sysadmin docs only.

## 1. Documentation Site

### 1.1 Searchable Documentation Portal

**As a** myAdmin user, **I want** a searchable documentation site, **so that** I can quickly find help for any feature.

**Acceptance Criteria:**

- [ ] Full-text search across all documentation
- [ ] Sidebar navigation with module grouping
- [ ] Mobile-responsive layout
- [ ] Fast page loads (static site)

### 1.2 Getting Started Guide

**As a** new user, **I want** a getting started guide, **so that** I can learn the basics quickly.

**Acceptance Criteria:**

- [ ] Overview of what myAdmin does (in plain language)
- [ ] First-time login and navigation
- [ ] Common workflows: import transactions, view reports, manage invoices
- [ ] Test mode vs production mode (when to use which)

### 1.3 Module Documentation (Task-Oriented)

**As a** user, **I want** documentation that tells me how to accomplish tasks, **so that** I can get work done without understanding the technical internals.

**Acceptance Criteria:**

- [ ] Banking — How to import bank statements, review transactions, fix account assignments, handle duplicates
- [ ] Invoices — How to upload invoices, review AI extraction results, edit and approve, find invoices in Google Drive
- [ ] STR — How to import Airbnb/Booking.com data, view realized vs planned bookings, check revenue summaries
- [ ] STR Pricing — How to view pricing recommendations, understand event-based pricing, apply suggestions
- [ ] Reports — How to view dashboards, generate P&L and balance sheets, export to Excel
- [ ] Tax — How to prepare BTW, IB, and Toeristenbelasting declarations
- [ ] PDF Validation — How to check and fix broken Google Drive links

### 1.4 SysAdmin Documentation (Separate Section)

**As a** system administrator, **I want** admin-specific docs, **so that** I can manage the platform.

**Acceptance Criteria:**

- [ ] Tenant management (create, configure, credentials)
- [ ] User management (roles, permissions)
- [ ] Docker deployment and maintenance
- [ ] Database administration
- [ ] Audit logging and monitoring
- [ ] Troubleshooting guide

## 2. Documentation Quality

### 2.1 Consistent Page Structure

**As a** user, **I want** every page to follow the same structure, **so that** docs are predictable and easy to scan.

**Acceptance Criteria:**

- [ ] Every module page: Overview → What you'll need → Step-by-step → Tips → Troubleshooting
- [ ] Consistent callouts (info, warning, tip)
- [ ] Screenshots for complex workflows
- [ ] No technical jargon without explanation

### 2.2 Maintainability

**As a** developer, **I want** docs that are easy to update, **so that** they stay current.

**Acceptance Criteria:**

- [ ] Written in Markdown
- [ ] Lives in the repo (versioned with code)
- [ ] Build/deploy automated
- [ ] Clear contribution guidelines

## 3. In-App Help (Core Feature)

### 3.1 Help Button Per Page

**As a** user, **I want** a help button on every page that opens the relevant documentation, **so that** I get help exactly where I need it.

**Acceptance Criteria:**

- [ ] Help icon (question mark) visible in the top-right of every module page
- [ ] Clicking opens the relevant docs section in a slide-out drawer (not a new tab)
- [ ] Docs content rendered inline from Markdown
- [ ] Fallback: if drawer fails, open docs site in new tab
- [ ] Route-to-docs mapping covers all modules:
  - `/banking` → Banking docs
  - `/invoices` → Invoice docs
  - `/str` → STR docs
  - `/str/pricing` → STR Pricing docs
  - `/reports` → Reports docs
  - `/tax` → Tax docs
  - `/pdf-validation` → PDF Validation docs
  - `/admin` → SysAdmin docs

### 3.2 Contextual Field Help

**As a** user, **I want** small info icons next to complex fields and buttons, **so that** I understand what they do without reading the full manual.

**Acceptance Criteria:**

- [ ] Info icon (ℹ) next to key actions: "Apply Patterns", "Check Duplicates", "AI Extract", "Test/Production toggle"
- [ ] Hover or click shows a short tooltip explaining the action in plain language
- [ ] Tooltip includes "Learn more" link to the full docs section
- [ ] Tooltips are consistent in style (Chakra UI Tooltip or Popover)

### 3.3 Reusable Help Component

**As a** developer, **I want** a reusable help component, **so that** adding help to new pages is trivial.

**Acceptance Criteria:**

- [ ] `<HelpButton section="banking/importing-statements" />` — renders the help icon, handles drawer
- [ ] `<FieldHelp tooltip="Explains what this does" docsLink="banking/patterns" />` — renders info icon with tooltip
- [ ] Components live in `frontend/src/components/help/`
- [ ] Docs base URL configurable via environment variable

## 4. Supporting Content

### 4.1 What's New / Changelog

**As a** user, **I want** to see what changed after an update, **so that** I know about new features and fixes.

**Acceptance Criteria:**

- [ ] Changelog page listing changes per release
- [ ] Grouped by: New Features, Improvements, Bug Fixes
- [ ] Most recent release at the top
- [ ] Updated with each deployment

### 4.2 FAQ

**As a** user, **I want** answers to common questions, **so that** I can solve problems without contacting support.

**Acceptance Criteria:**

- [ ] Covers common questions per module (e.g., "Why are my transactions showing as duplicates?", "What's the difference between Test and Production mode?")
- [ ] Searchable alongside other docs
- [ ] Updated based on actual user questions

### 4.3 Glossary

**As a** non-Dutch user, **I want** a glossary of Dutch financial terms, **so that** I understand domain-specific terminology.

**Acceptance Criteria:**

- [ ] Maps Dutch terms to English explanations (mutaties, toeristenbelasting, BTW, aangifte IB, etc.)
- [ ] Linked from pages where terms are used
- [ ] Alphabetically sorted

### 4.4 Print-Friendly Pages

**As a** user, **I want** to print workflow pages, **so that** I can follow steps on paper.

**Acceptance Criteria:**

- [ ] Print button on each page (MkDocs Material built-in)
- [ ] Clean print layout without navigation chrome

## Non-Functional Requirements

- Static site, < 1s page load
- Readable on all devices
- Bilingual: English (`/en/`) and Dutch (`/nl/`) via MkDocs i18n plugin
- Language switcher in the navigation bar
- Dutch is the primary language (most users are Dutch-speaking)
- English version for international users
- Write Dutch first, then translate to English
- Glossary available in both languages

## Out of Scope

- Video tutorials
- Interactive walkthroughs
- API reference (covered by Swagger/Flasgger)
- Developer documentation (covered by specs and steering files)
