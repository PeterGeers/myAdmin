# Design: Budget Module Redesign

## Overview

Simplify the budget module from 4 pages + 4 tables to a single preparation page + a dashboard tab in FIN Reports, backed by only 2 tables.

## Architecture

```
Frontend:
  BudgetPage.tsx          → Single page for budget preparation (replaces Versions + Templates + Lines pages)
  BudgetDashboardTab.tsx  → New tab in FinancialReportsGroup (replaces standalone BudgetDashboard)

Backend:
  budget_routes.py        → Simplified (no template routes, no generate-draft)
  budget_service.py       → Simplified (no template methods, activate doesn't deactivate others)
  budget_ai_service.py    → Keep narrative, query, draft-suggestions; remove template-recommend

Database:
  budget_versions         → Keep (unchanged schema)
  budget_lines            → Keep (unchanged schema)
  budget_templates        → DROP
  budget_template_lines   → DROP
```

## Database Changes

### Tables to keep (no schema changes)

```sql
-- budget_versions: unchanged
-- budget_lines: unchanged
```

### Tables to drop

```sql
DROP TABLE IF EXISTS budget_template_lines;
DROP TABLE IF EXISTS budget_templates;
```

### Behavior change: activate_version

Current: activating a version deactivates all other versions for the same fiscal year.
New: activating just sets `is_active = TRUE` on the target. No side effects on other versions.

## API Changes

### Routes to KEEP (unchanged)

| Method | Endpoint                           | Description               |
| ------ | ---------------------------------- | ------------------------- |
| GET    | `/api/budget/versions`             | List all versions         |
| POST   | `/api/budget/versions`             | Create version            |
| PUT    | `/api/budget/versions/<id>/status` | Transition status         |
| DELETE | `/api/budget/versions/<id>`        | Delete draft version      |
| GET    | `/api/budget/versions/<id>/lines`  | List lines for version    |
| POST   | `/api/budget/versions/<id>/lines`  | Create line               |
| PUT    | `/api/budget/lines/<id>`           | Update line               |
| DELETE | `/api/budget/lines/<id>`           | Delete line               |
| POST   | `/api/budget/copy`                 | Copy version              |
| POST   | `/api/budget/ai/narrative`         | AI narrative              |
| POST   | `/api/budget/ai/query`             | AI natural language query |
| POST   | `/api/budget/ai/draft-suggestions` | AI draft adjustments      |

### Routes to MODIFY

| Method | Endpoint                             | Change                                                                     |
| ------ | ------------------------------------ | -------------------------------------------------------------------------- |
| PUT    | `/api/budget/versions/<id>/activate` | Toggle `is_active` without deactivating others. Also support deactivation. |
| GET    | `/api/budget/dashboard`              | Accept `version_id` param instead of `year`. Derive year from version.     |

**PUT /api/budget/versions/<id>/activate** (new behavior):

```json
Request: { "active": true }   // or { "active": false } to deactivate
Response: { "success": true, "data": { "id": 1, "is_active": true } }
```

**GET /api/budget/dashboard?version_id=3&level=parent&period=ytd**

New: `version_id` (required) replaces `year` (removed). Backend looks up version's fiscal_year internally.

### Routes to REMOVE

| Method | Endpoint                            | Reason                              |
| ------ | ----------------------------------- | ----------------------------------- |
| GET    | `/api/budget/templates`             | Templates dropped                   |
| GET    | `/api/budget/templates/<id>`        | Templates dropped                   |
| POST   | `/api/budget/templates`             | Templates dropped                   |
| PUT    | `/api/budget/templates/<id>`        | Templates dropped                   |
| DELETE | `/api/budget/templates/<id>`        | Templates dropped                   |
| POST   | `/api/budget/generate-draft`        | Replaced by AI draft in create flow |
| POST   | `/api/budget/ai/template-recommend` | Templates dropped                   |

### New route: AI Draft Proposal

| Method | Endpoint                        | Description                                         |
| ------ | ------------------------------- | --------------------------------------------------- |
| POST   | `/api/budget/ai/generate-lines` | AI proposes budget lines (not saved, just returned) |

```json
Request: {
  "fiscal_year": 2026,
  "context_notes": "Rent increases 5% in June. Drop Booking.com."
}
Response: {
  "success": true,
  "data": {
    "proposed_lines": [
      {
        "account_code": "4000",
        "account_name": "Omzet",
        "period_mode": "Monthly",
        "detail_dimension_type": null,
        "detail_dimension_value": null,
        "amounts": [1000, 1200, 1100, 950, 1300, 1250, 1400, 1350, 1200, 1150, 1050, 1500],
        "reasoning": "Based on 2025 actuals with stable revenue pattern"
      }
    ],
    "model_used": "google/gemini-flash-1.5",
    "tokens_used": 500
  }
}
```

## Frontend Design

### BudgetPage.tsx (single page)

```
┌─────────────────────────────────────────────────────────────┐
│ Budget                                                       │
│                                                              │
│ [▼ Select version...        ]  [+ New Version] [Actions ▼]  │
│                                                              │
│ Status: Draft │ Year: 2026 │ Active: No                      │
│ [Approve] [Activate] [Delete]  (contextual, based on status) │
│                                                              │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Account │ Name    │ Dimension │ Mode │ Total   │         │ │
│ │ 4000    │ Omzet   │ —         │ Mon  │ 14,450  │ [🗑]   │ │
│ │ 4100    │ Airbnb  │ platform  │ Mon  │ 3,800   │ [🗑]   │ │
│ │ 5100    │ Huur    │ —         │ Ann  │ 24,000  │ [🗑]   │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                              │
│ [+ Add Line]  [AI Suggest Adjustments]                       │
│                                                              │
│ Row click → Monthly amounts modal                            │
└─────────────────────────────────────────────────────────────┘
```

**Edit Line Modal** (on row click):

- Account code + name (read-only)
- Period mode toggle (Monthly / Annual)
- If Monthly: 12 input fields (Jan–Dec) + computed total
- If Annual: 1 input field, system shows computed monthly = annual / 12
- Save / Cancel

**New Version Modal:**

- Name (required)
- Fiscal Year (required, default: current year + 1)
- Method: radio/select
  - Empty (creates version with no lines)
  - Copy from: [version dropdown] (copies all lines)
  - AI Draft: [context notes textarea] → generates proposed lines for review
- When AI Draft is selected and submitted: shows review table with proposed lines, user can remove/accept, then "Create Version with Lines"

### BudgetDashboardTab.tsx (in FinancialReportsGroup)

Added as a new tab in the existing FIN Reports tabs:

```
Tabs: Mutaties | Balance | P&L | BTW | Reference | Aangifte IB | Pivot | Budget vs Actuals
```

The tab contains:

- Version dropdown: shows all active versions (label: "name (year)")
- Period selector: month/quarter/YTD/full
- Drill-down table with breadcrumb
- Variance coloring
- AI narrative button
- AI query input

No year selector — year comes from selected version.

## Files to Remove

### Frontend

- `pages/BudgetVersionsPage.tsx`
- `pages/BudgetTemplatesPage.tsx`
- `pages/BudgetLinesPage.tsx`
- `pages/BudgetDashboard.tsx`
- `pages/GenerateDraftModal.tsx`
- `pages/CopyBudgetModal.tsx`
- `__tests__/BudgetVersionsPage.test.tsx`
- `__tests__/BudgetLinesPage.test.tsx`

### Backend

- Template-related methods in `budget_service.py`
- Template routes in `budget_routes.py`
- `generate_draft` method in `budget_service.py`
- `template_recommend` in `budget_ai_service.py`

### Database

- `budget_templates` table
- `budget_template_lines` table

## Files to Create

### Frontend

- `pages/BudgetPage.tsx` — single preparation page
- `pages/BudgetLineEditModal.tsx` — monthly amounts editor
- `pages/BudgetNewVersionModal.tsx` — create version with method selection
- `components/reports/BudgetDashboardTab.tsx` — dashboard tab for FIN Reports

### Files to Modify

- `App.tsx` — remove 4 budget page types, add single `budget` page type
- `FinancialReportsGroup.tsx` — add Budget vs Actuals tab
- `services/budgetService.ts` — remove template functions, add `generateLines`, change dashboard params
- `types/budget.ts` — remove template types, add AI generate-lines types
- `locales/en/budget.json` + `locales/nl/budget.json` — update translation keys
- `budget_routes.py` — remove template routes, modify activate, modify dashboard
- `budget_service.py` — remove template methods, simplify activate, update dashboard
- `budget_ai_service.py` — remove template_recommend, add generate_lines

## Permissions

| Action                            | Required Permission |
| --------------------------------- | ------------------- |
| View budget versions/lines        | Finance_Read        |
| Create/edit/delete versions/lines | Finance_CRUD        |
| View dashboard                    | Finance_Read        |
| Export dashboard                  | Finance_Export      |
| Status transitions                | Finance_CRUD        |
| AI features                       | Finance_CRUD        |

## Migration Notes

1. Before dropping template tables, verify no other code references them
2. Existing `budget_versions` and `budget_lines` data is preserved unchanged
3. Existing active version logic changes (no longer single-active-per-year) — all currently active versions remain active
4. The `budget` function flag continues to gate access to the budget preparation page
5. Dashboard moves to FIN Reports (gated by Finance_Read, no function flag needed since it's part of reports)
