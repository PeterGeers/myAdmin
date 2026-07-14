# Bugfix Requirements Document

## Introduction

Balance sheet accounts (VW='N') are double-counted or under-counted in multiple reporting code paths because year filtering does not account for the fiscal year closure state. When a year is closed, an OpeningBalance record is created for the following year that carries forward all prior history. Code paths that cumulate raw transactions across years that include both the last closed year's data AND the OpeningBalance that summarizes it produce inflated totals. Conversely, code paths that only look at the target year miss accumulated history when no OpeningBalance exists for that year.

The fix requires all balance calculation code paths to use a shared closure-aware start year: `start_year = last_closed_year + 1`. This ensures cumulation begins from the year that has OpeningBalance records (carrying forward all prior history) without also including the raw transactions those records summarize.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN querying an open year's balance sheet via `/actuals-balance?per_year=true` and a prior year is closed THEN the system uses `jaar <= target_year` which includes the last closed year's raw transactions alongside the OpeningBalance that already summarizes them, resulting in double-counted balances

1.2 WHEN querying balance sheet totals via `/actuals-balance` (non-per_year mode) and a prior year is closed THEN the system uses `jaar <= max_year` on cached data that includes the last closed year, resulting in double-counted balances

1.3 WHEN querying Aangifte IB balance sheet accounts via `query_aangifte_ib()` for a year whose prior year is NOT closed THEN the system uses `jaar == target_year` only, missing all accumulated history from unclosed prior years, resulting in under-counted balances

1.4 WHEN generating an XLSX financial report via `make_ledgers()` in `financial_report_generator.py` or `xlsx_export.py` and a prior year is closed THEN the system uses `jaar < target_year` to compute beginning balance which includes raw transactions from years before the closure alongside OpeningBalance records that summarize them, resulting in double-counted beginning balances

### Expected Behavior (Correct)

2.1 WHEN querying an open year's balance sheet via `/actuals-balance?per_year=true` and a prior year is closed THEN the system SHALL filter balance sheet data with `jaar >= start_year AND jaar <= target_year` where `start_year = last_closed_year + 1`, cumulating only from the year that carries the OpeningBalance forward

2.2 WHEN querying balance sheet totals via `/actuals-balance` (non-per_year mode) and a prior year is closed THEN the system SHALL filter with `jaar >= start_year AND jaar <= max_year` where `start_year = last_closed_year + 1`

2.3 WHEN querying Aangifte IB balance sheet accounts via `query_aangifte_ib()` for a year whose prior year is NOT closed THEN the system SHALL cumulate with `jaar >= start_year AND jaar <= target_year` where `start_year = last_closed_year + 1`, falling back to `jaar <= target_year` if no years are closed

2.4 WHEN generating an XLSX financial report via `make_ledgers()` and a prior year is closed THEN the system SHALL compute beginning balance using `jaar >= start_year AND jaar < target_year` where `start_year = last_closed_year + 1`, avoiding double-counting with OpeningBalance records

2.5 WHEN no years are closed for the administration THEN the system SHALL cumulate balance sheet accounts from the beginning (`jaar <= target_year`) since no OpeningBalance records exist to carry forward history

2.6 WHEN the target year itself is closed THEN the system SHALL use `jaar == target_year` only, since the closed year's data is self-contained

2.7 WHEN future year data exists (e.g., depreciation entries for 2027/2028) and the target year is 2026 THEN the system SHALL NOT include data with `jaar > target_year` in the balance calculation

2.8 _(Moved to separate feature spec: balance-verification-audit)_ Full recalculation mode — reading all years while excluding OpeningBalance records — is an audit/verification feature that should be wired into tenant administration as a separate deliverable

### Unchanged Behavior (Regression Prevention)

3.1 WHEN querying P&L accounts (VW='Y') THEN the system SHALL CONTINUE TO use date-range filtering (start_date to end_date) regardless of closure state, as P&L accounts never cumulate across years — a year is the most common range but quarter, month, or arbitrary date ranges are also valid

3.2 WHEN the target year is a closed year THEN the system SHALL CONTINUE TO return `jaar == target_year` data only, identical to current closed-year behavior

3.3 WHEN querying balance sheet data with administration filter THEN the system SHALL CONTINUE TO apply exact tenant matching (`administration = %s`) for tenant isolation

3.4 WHEN the cache loads data for years to display THEN the system SHALL CONTINUE TO load the last closed year and all open years into cache (the cache loading logic itself is not changed)

3.5 WHEN the year_closure_status table is empty or unreachable THEN the system SHALL CONTINUE TO fall back to cumulative behavior (`jaar <= target_year`) as the safe default, matching current behavior for administrations with no closures
