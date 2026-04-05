# End-User Documentation

**Status**: Draft
**Domain**: Common
**Created**: April 2026

## Overview

Migrate existing HTML manuals and sysadmin Markdown docs to a unified MkDocs documentation site. Add missing module documentation, a getting started guide, and set up auto-deployment. Incrementally add in-app contextual help for key workflows.

## Reading Order

1. **requirements.md** — User stories and acceptance criteria
2. **design.md** — Technical approach (MkDocs setup, structure, deployment)
3. **TASKS.md** — Implementation checklist with progress tracking

## Current State

- 5 HTML manuals in `Manuals/` (Banking, Docker, Duplicate Detection, PDF Transactions, STR)
- 9 sysadmin Markdown docs in `manualsSysAdm/`
- Two formats (HTML + Markdown), two locations, no search, no navigation

## Related

- Existing manuals: `Manuals/*.html`
- Sysadmin docs: `manualsSysAdm/*.md`
- Backend docs: `backend/docs/`
