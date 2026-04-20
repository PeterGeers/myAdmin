# Implementation Plan

- [x] 1. Add `_get_opening_balance_date` helper to `banking_processor.py`
  - **File**: `backend/src/banking_processor.py`
  - Create a module-level helper function `_get_opening_balance_date(db, administration)` following the pattern from `_get_closed_years` in `backend/src/actuals_routes.py`
  - Query `SELECT MAX(year) as last_closed_year FROM year_closure_status WHERE administration = %s`
  - If a closed year exists, return `f"{last_closed_year + 1}-01-01"` (opening balance date)
  - If no closed year exists, return `None`
  - Use parameterized query with `%s` placeholder (per database-patterns steering)
  - Wrap in try/except, log warning on failure, return `None` as safe fallback
  - _Requirements: 2.1, 2.3_

- [x] 2. Fix `check_banking_accounts` to scope transactions to post-closure period
  - **File**: `backend/src/banking_processor.py`, function `check_banking_accounts` (~line 222)
  - At the start of the function (after getting cursor), call `_get_opening_balance_date(self.db, administration)`
  - If `opening_balance_date` is not None, add `AND TransactionDate >= %s` to the SUM query on `vw_mutaties` (both `end_date` and non-`end_date` branches)
  - Add the same `TransactionDate >= %s` filter to the "last transaction" subqueries that find the most recent transaction per account
  - Append `opening_balance_date` to the `params` list for each modified query
  - When `opening_balance_date` is None (no closure), queries remain unchanged — preservation guaranteed
  - _Requirements: 2.1, 2.3, 3.1, 3.3_

- [x] 3. Fix `check_sequence_numbers` to use closure-derived start date
  - **File**: `backend/src/banking_processor.py`, function `check_sequence_numbers` (~line 355)
  - At the start of the function (after getting cursor), call `_get_opening_balance_date(self.db, administration)`
  - If `opening_balance_date` is not None, override `start_date = opening_balance_date` regardless of the parameter value
  - When `opening_balance_date` is None, keep the existing `start_date` parameter behavior unchanged
  - The existing query `WHERE Ref1 = %s AND TransactionDate >= %s` already uses `start_date` — no query changes needed, just the value override
  - _Requirements: 2.2, 2.3, 3.2, 3.4_

- [x] 4. Create new API endpoint `GET /api/banking/opening-balance-date`
  - **File**: `backend/src/routes/banking_routes.py`
  - Add new route `@banking_bp.route('/api/banking/opening-balance-date', methods=['GET'])`
  - Use `@cognito_required(required_permissions=['banking_read'])` and `@tenant_required()` decorators (per api-conventions steering)
  - Inside the handler, instantiate `BankingProcessor` (or use `DatabaseManager` directly) and call `_get_opening_balance_date`
  - Return `{ success: true, opening_balance_date: "YYYY-01-01", last_closed_year: NNNN }` when closure exists
  - Return `{ success: true, opening_balance_date: null, last_closed_year: null }` when no closure exists
  - Wrap in try/except with standard error response pattern
  - _Requirements: 2.1, 2.4, 2.5_

- [x] 5. Update frontend to fetch and use opening balance date
  - [x] 5.1 Add state and fetch logic for opening balance date
    - **File**: `frontend/src/components/BankingProcessor.tsx`
    - Add state: `const [openingBalanceDate, setOpeningBalanceDate] = useState<string | null>(null)`
    - Add a `useEffect` (or extend existing `fetchLookupData`) to call `GET /api/banking/opening-balance-date` on mount and when `currentTenant` changes
    - On success: set `openingBalanceDate` from response, and if non-null, also set `sequenceStartDate` to the opening balance date value
    - On failure or null response: keep `openingBalanceDate` as null, keep existing default `sequenceStartDate`
    - _Requirements: 2.4, 2.5_

  - [x] 5.2 Make start date field read-only when closure exists
    - **File**: `frontend/src/components/BankingProcessor.tsx`, date input (~line 1457)
    - Add `isReadOnly={openingBalanceDate !== null}` to the `<Input type="date">` for sequence start date
    - When read-only: show the opening balance date value, prevent user edits
    - When not read-only (no closure): keep current editable behavior with default `'2025-01-01'`
    - Optionally add a small label or tooltip indicating "Set by annual closure" when read-only
    - _Requirements: 2.4, 2.5, 3.2_

- [x] 6. Write backend unit tests
  - **File**: `backend/tests/unit/test_banking_balance_closure.py`
  - Test `_get_opening_balance_date` with:
    - Single closure (year 2024) → returns `'2025-01-01'`
    - Multiple closures (2023, 2024) → returns `'2025-01-01'` (uses max year)
    - No closures → returns `None`
    - Database error → returns `None` (graceful fallback)
  - Test `check_banking_accounts` with mocked DB:
    - With closure: verify query includes `TransactionDate >= '2025-01-01'`
    - Without closure: verify query has no lower date bound (preservation)
    - With closure + end_date: verify both bounds applied
  - Test `check_sequence_numbers` with mocked DB:
    - With closure: verify start_date is overridden to opening_balance_date
    - Without closure: verify start_date parameter is used as-is (preservation)
  - Test `/api/banking/opening-balance-date` endpoint:
    - With closure → returns opening_balance_date and last_closed_year
    - Without closure → returns nulls
  - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4_

- [x] 7. Checkpoint — Verify all tests pass and review
  - Run backend tests: `cd backend && python -m pytest tests/unit/test_banking_balance_closure.py -v`
  - Verify no regressions in existing banking tests: `cd backend && python -m pytest tests/ -k banking -v`
  - Manually verify with a test administration that has a year closure:
    - Balance check only includes post-closure transactions
    - Sequence check uses the correct start date
    - Frontend shows read-only date field with correct value
  - Manually verify with a no-closure administration:
    - Balance check includes all transactions (unchanged)
    - Sequence check uses default/editable start date (unchanged)
  - Ask the user if questions arise
