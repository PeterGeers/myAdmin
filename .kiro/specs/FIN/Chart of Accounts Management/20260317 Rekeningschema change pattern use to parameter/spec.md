# Refactoring: Migrate Pattern Column to Parameters JSON

**Date:** March 17, 2026  
**Status:** Complete  
**Type:** Refactoring (not a bug fix)  
**Priority:** Low (no functional issue, consistency improvement)

## Summary

Migrate the `Pattern` column and `AccountLookup` column usage in `rekeningschema` to the `parameters` JSON column, consistent with how `$.purpose`, `$.vat_netting`, and `$.vat_primary` are already stored:

- `Pattern = 1` → `$.bank_account: true`
- `AccountLookup` (IBAN) → `$.iban: "NL44RABO0123456789"`

The IBAN is the core identifier of a bank account. Moving both together keeps the bank account configuration self-contained in parameters.

## Current Situation

The `Pattern` column (integer, 1 or NULL) identifies bank accounts eligible for:

- Banking import (which accounts can receive CSV imports)
- Pattern analysis (which accounts get verb pattern matching)
- Bank account lookups (mapping IBAN → internal account number)

The `parameters` JSON column already stores:

- `$.purpose` → year-end closure (equity_result, pl_closing)
- `$.vat_netting` → VAT netting flag
- `$.vat_primary` → primary VAT account flag

## Proposed Change

Replace both `Pattern` and `AccountLookup` columns with parameters JSON fields:

- `Pattern = 1` → `$.bank_account: true`
- `AccountLookup` (IBAN) → `$.iban: "NL44RABO0123456789"`

### Parameters JSON Example

```json
{
  "bank_account": true,
  "iban": "NL44RABO0123456789"
}
```

### Before

```sql
-- vw_rekeningnummers view
SELECT AccountLookup AS rekeningNummer, Account, administration
FROM rekeningschema
WHERE Pattern IS NOT NULL
```

### After

```sql
-- vw_rekeningnummers view
SELECT JSON_UNQUOTE(JSON_EXTRACT(parameters, '$.iban')) AS rekeningNummer,
       Account, administration
FROM rekeningschema
WHERE JSON_EXTRACT(parameters, '$.bank_account') = true
AND JSON_EXTRACT(parameters, '$.iban') IS NOT NULL
```

## Impact Analysis

### Database

- `vw_rekeningnummers` view → rewrite to use `$.bank_account` and `$.iban`
- Migration script: copy `Pattern=1` → `$.bank_account: true` AND `AccountLookup` → `$.iban`
- Keep `Pattern` and `AccountLookup` columns temporarily for rollback safety

### Backend Files Affected

| File                                             | What Changes                                                                             |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| `backend/src/routes/chart_of_accounts_routes.py` | CRUD: read/write `$.bank_account` and `$.iban` instead of `Pattern`/`AccountLookup`      |
| `backend/src/database.py`                        | `get_bank_account_lookups()` uses `vw_rekeningnummers` (no code change, view handles it) |
| `backend/src/banking_processor.py`               | Uses `vw_rekeningnummers` (no code change, view handles it)                              |
| `backend/src/pattern_analyzer.py`                | Uses `vw_rekeningnummers` indirectly (no code change)                                    |
| `backend/src/validate_pattern/database.py`       | Uses `vw_rekeningnummers` (no code change)                                               |

### Why `is_bank_account()` Needs No Changes

The heavily-used `PatternAnalyzer.is_bank_account()` method is safe because the entire call chain is abstracted by the view:

```
is_bank_account(account, administration)
  → get_bank_accounts()                          # builds cache keyed by "{administration}_{Account}"
    → db.get_bank_account_lookups()               # SELECT rekeningNummer, Account, administration FROM vw_rekeningnummers
      → vw_rekeningnummers                        # ← only this changes (reads $.iban instead of AccountLookup)
```

The cache key uses `Account` (e.g. "1022"), not `AccountLookup`/IBAN. The IBAN is stored as data inside the cache entry (`account['rekeningNummer']`). As long as `vw_rekeningnummers` keeps returning the same three column aliases (`rekeningNummer`, `Account`, `administration`), the entire chain works unchanged. This includes:

- `is_bank_account()` — cache lookup by account number (unchanged)
- `get_bank_accounts()` — cache population (unchanged)
- `get_bank_account_lookups()` — SQL query against view (unchanged)
- `_analyze_reference_patterns()` — uses `is_bank_account()` (unchanged)
- `banking_processor.py` — uses view results (unchanged)

### Frontend Files Affected

| File                                                      | What Changes                                                                  |
| --------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `frontend/src/components/TenantAdmin/ChartOfAccounts.tsx` | Display: read `bank_account` and `iban` from parameters instead of columns    |
| Chart of Accounts edit/create forms                       | Toggle: write `$.bank_account` and input `$.iban` instead of separate columns |

### Views Affected

| View                 | What Changes                                                                                                                                                                    |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `vw_rekeningnummers` | SELECT: `JSON_UNQUOTE(JSON_EXTRACT(parameters, '$.iban'))` instead of `AccountLookup`; WHERE: `$.bank_account = true` and `$.iban IS NOT NULL` instead of `Pattern IS NOT NULL` |

## Migration Strategy

### Phase 1: Data Migration (backward compatible)

1. Write migration script that:
   - Copies `Pattern=1` → `parameters = JSON_SET(parameters, '$.bank_account', true)`
   - Copies `AccountLookup` → `parameters = JSON_SET(parameters, '$.iban', AccountLookup)` where AccountLookup is not null/empty
2. Update `vw_rekeningnummers` to check BOTH old and new:
   - WHERE: `Pattern IS NOT NULL OR JSON_EXTRACT(parameters, '$.bank_account') = true`
   - SELECT: `COALESCE(JSON_UNQUOTE(JSON_EXTRACT(parameters, '$.iban')), AccountLookup) AS rekeningNummer`
3. Deploy and verify no breakage

### Phase 2: Code Update

1. Update `chart_of_accounts_routes.py` to read/write `$.bank_account` instead of `Pattern`
2. Update frontend ChartOfAccounts component
3. Update `vw_rekeningnummers` to only check `$.bank_account`

### Phase 3: Cleanup (later)

1. Remove `Pattern` column from `rekeningschema` (only after confirming everything works)
2. Remove Pattern references from chart_of_accounts_routes.py INSERT/UPDATE queries

## Tasks

### Phase 1: Database Migration

- [x] 1.1 Write migration SQL: copy Pattern=1 to parameters $.bank_account AND AccountLookup to $.iban
- [x] 1.2 Update vw_rekeningnummers to check both Pattern and $.bank_account (COALESCE for $.iban/AccountLookup)
- [x] 1.3 Run migration on local Docker MySQL (8 rows migrated, all parameters populated)
- [x] 1.4 Verify vw_rekeningnummers returns same results as before (identical 8 rows confirmed)
- [x] 1.5 Run migration on Railway (production) — 8 rows confirmed identical

### Phase 2: Backend Changes

- [x] 2.1 Update chart_of_accounts_routes.py: list accounts → include $.bank_account and $.iban
- [x] 2.2 Update chart_of_accounts_routes.py: get single account → include $.bank_account and $.iban
- [x] 2.3 Update chart_of_accounts_routes.py: create account → write $.bank_account and $.iban
- [x] 2.4 Update chart_of_accounts_routes.py: update account → write $.bank_account and $.iban
- [x] 2.5 Update chart_of_accounts_routes.py: import accounts → write $.bank_account and $.iban
- [x] 2.6 Update vw_rekeningnummers to only check $.bank_account (remove Pattern check) — local verified, 8 rows identical
- [x] 2.7 Test banking import still works (view returns identical data)
- [x] 2.8 Test pattern analysis still works (view returns identical data)

### Phase 3: Frontend Changes

- [x] 3.1 Update ChartOfAccounts.tsx: display bank_account flag and iban from parameters
- [x] 3.2 Update ChartOfAccounts edit form: toggle $.bank_account and input $.iban
- [x] 3.3 Update ChartOfAccounts create form: toggle $.bank_account and input $.iban
- [x] 3.4 Test Chart of Accounts UI

### Phase 4: Cleanup

- [x] 4.1 Remove Pattern column from all SELECT queries in chart_of_accounts_routes.py
- [x] 4.2 Remove Pattern from INSERT/UPDATE queries (create, update, import)
- [x] 4.3 Update export to read bank_account from parameters instead of Pattern column
- [ ] 4.4 Drop Pattern column from rekeningschema table (deferred — column is harmless, drop when confident)

## Risks

- **Low risk**: The `vw_rekeningnummers` view abstracts the change from most code
- **Rollback**: Keep Pattern column until fully verified
- **Performance**: JSON_EXTRACT is slightly slower than column check, but negligible at this scale

## Notes

- This is a consistency improvement, not a bug fix
- No user-facing behavior changes
- The Pattern column can be removed later once everything is verified

## Phase 5: Generic Parameter Editor (added during implementation)

### Problem

Parameters were managed in scattered UIs — `purpose` in Year End Settings, `bank_account`/`iban` via the Pattern column, `vat_netting`/`vat_primary` elsewhere. No single place to view or edit all parameters for an account.

### Solution

Added a generic key-value parameter editor to the Account Modal:

- Read-only view: pretty-printed JSON of all parameters (default)
- Edit mode: toggled via "Edit" button, shows key-value rows
- Known keys (`bank_account`, `iban`, `purpose`, `vat_netting`, `vat_primary`) get appropriate input types:
  - Boolean keys → toggle switch
  - String keys → text input
- Dropdown selector for known keys, with support for custom keys
- Add/remove parameter entries
- On save, the full parameters JSON is sent to the backend

### Table Display

- Renamed "Purpose" column to "Parameters"
- Shows first 30 characters of the JSON string, truncated with `...`
- Full JSON visible on hover (native tooltip)

### Files Changed

| File                                                      | What Changed                                                                                                                      |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/src/components/TenantAdmin/AccountModal.tsx`    | Added key-value parameter editor with edit toggle                                                                                 |
| `frontend/src/components/TenantAdmin/ChartOfAccounts.tsx` | Renamed Purpose column to Parameters, shows truncated JSON                                                                        |
| `frontend/src/types/chartOfAccounts.ts`                   | Added `parameters` to `Account` and `AccountFormData` interfaces                                                                  |
| `backend/src/routes/chart_of_accounts_routes.py`          | `update_account` accepts raw `parameters` JSON; returns `parameters` in response; `list_accounts` returns raw `parameters` column |

### Tasks

- [x] 5.1 Replace Purpose column with Parameters column (truncated JSON display)
- [x] 5.2 Remove Bank Account checkbox and IBAN field from modal (now managed via parameter editor)
- [x] 5.3 Add read-only parameters JSON display in modal
- [x] 5.4 Add key-value parameter editor with Edit toggle
- [x] 5.5 Known parameter keys with type-aware inputs (boolean → switch, string → text)
- [x] 5.6 Backend: accept raw parameters JSON in update endpoint
- [x] 5.7 Backend: return parameters in list and update responses
