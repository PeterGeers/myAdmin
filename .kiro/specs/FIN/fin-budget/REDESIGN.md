# Budget Module Redesign

## Problem Statement

The current budget implementation is over-engineered. It has 4 tables, 4 frontend pages, complex template machinery, and a rigid "single active budget per year" constraint — all for what should be a straightforward tool.

## Redesign Principles

1. **Dashboard = Fin Reports item** — Budget vs Actuals comparison moves to the existing FIN Reports section
2. **Budget Preparation = single page** under the Budget function flag
3. **Drop template tables** — templates are unnecessary; AI draft generation doesn't need a stored template
4. **Multiple active budgets** — any Approved/Revised budget can be selected in the dashboard dropdown
5. **Year is implied** — the budget version carries its fiscal year; no separate year picker needed in dashboard

## New Architecture

### Database (simplified)

**Keep:**

- `budget_versions` — unchanged (id, administration, name, fiscal_year, status, is_active, timestamps)
- `budget_lines` — unchanged (version_id, administration, account_code, period_mode, dimension fields, 12 months)

**Drop:**

- `budget_templates` — remove table
- `budget_template_lines` — remove table

**Schema change to `budget_versions`:**

- `is_active` changes meaning: multiple versions can be active simultaneously (it just means "available for dashboard selection")
- Remove the application logic that deactivates other versions when one is activated

### Frontend

**Budget Preparation page** (single page, replaces Versions + Templates + Lines):

```
┌─────────────────────────────────────────────────────────┐
│ Budget                                                   │
│                                                          │
│ Version: [▼ First test 2026 (Approved)]  [+ New Version]│
│                                                          │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ Account │ Dimension │ Mode │ Jan │ Feb │...│ Total  │ │
│ │ 4000    │ —         │ Mon  │ 100 │ 120 │...│ 1400   │ │
│ │ 4100    │ Airbnb    │ Mon  │ 300 │ 310 │...│ 3800   │ │
│ │ 5100    │ —         │ Ann  │ 200 │ 200 │...│ 2400   │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                          │
│ [+ Add Line]  [AI Suggest Adjustments]                   │
│                                                          │
│ Row click → Edit modal (monthly amounts or annual)       │
└─────────────────────────────────────────────────────────┘
```

**Create New Version modal:**

- Name, Fiscal Year
- Options: Empty / Copy from existing version / AI-generated draft
- AI option: user provides context notes, AI returns proposed lines (shown as editable budget lines, not auto-saved)

**Edit Line modal (for monthly entry):**

- Shows account code, dimension info
- 12 month fields (or 1 annual field with toggle)
- Save / Cancel

**Budget Dashboard** (moves to FIN Reports):

- Dropdown: select any active budget version (replaces year + "which active version" logic)
- Selected version implies the year → actuals are fetched for that year
- Rest stays: drill-down Parent → SubParent → Account, variance display, period filter (month/quarter/ytd/full)
- AI narrative + natural language query features remain

### Backend Changes

**Routes to keep (simplified):**

- `GET /api/budget/versions` — list all versions (no year filter needed, show all)
- `POST /api/budget/versions` — create version
- `PUT /api/budget/versions/<id>/status` — transition status
- `PUT /api/budget/versions/<id>/activate` — toggle active (no longer deactivates others)
- `DELETE /api/budget/versions/<id>` — delete draft
- `GET /api/budget/versions/<id>/lines` — list lines for version
- `POST /api/budget/versions/<id>/lines` — create line
- `PUT /api/budget/lines/<id>` — update line
- `DELETE /api/budget/lines/<id>` — delete line
- `GET /api/budget/dashboard?version_id=X&level=...&period=...` — dashboard (version_id instead of year)
- `POST /api/budget/ai/narrative` — keep
- `POST /api/budget/ai/query` — keep
- `POST /api/budget/ai/draft-suggestions` — keep (becomes the "AI draft" option)
- `POST /api/budget/copy` — keep (copy from existing version)

**Routes to remove:**

- `GET /api/budget/templates` — drop
- `GET /api/budget/templates/<id>` — drop
- `POST /api/budget/templates` — drop
- `PUT /api/budget/templates/<id>` — drop
- `DELETE /api/budget/templates/<id>` — drop
- `POST /api/budget/generate-draft` — drop (replaced by AI suggestions shown as lines)
- `POST /api/budget/ai/template-recommend` — drop

**Service changes:**

- Remove all template methods from `budget_service.py`
- Remove `generate_draft` method (the template-based generation)
- Simplify `activate_version` to just toggle `is_active` without deactivating others
- Dashboard: accept `version_id` parameter instead of `year` (derive year from version)

### AI Draft Generation (new approach)

Instead of templates + generate_draft, the "AI draft" option when creating a version works like:

1. User clicks "New Version" → selects "AI-generated draft"
2. User provides: fiscal year, version name, optional context notes
3. Backend calls AI with: chart of accounts + prior-year actuals summary
4. AI returns proposed budget lines (account, period_mode, 12 amounts, reasoning)
5. Frontend shows proposed lines in a review table
6. User accepts/modifies/removes individual lines
7. User clicks "Save" → version + lines are created

This is simpler, doesn't need templates, and gives the user full control.

## Migration Plan

1. Create new simplified Budget Preparation page
2. Update dashboard to accept version_id and move to FIN Reports
3. Update activate_version to allow multiple active versions
4. Drop template-related routes, service methods, and frontend pages
5. Drop `budget_templates` and `budget_template_lines` tables (after confirming no data loss)
6. Update tests

## What Stays Unchanged

- `budget_versions` table structure
- `budget_lines` table structure
- Budget line CRUD logic
- Version status transitions (Draft → Approved → Revised)
- Copy budget functionality
- AI narrative and query features
- Dashboard rollup/hierarchy logic
- Tenant isolation pattern
- All correctness properties (rounding, rollups, isolation)
