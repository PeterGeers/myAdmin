# Implementation Plan: Banking Pattern Prediction Bugfixes

## Overview

Fix hardcoded tenant values throughout the banking pipeline and replace the binary ambiguity flag in pattern detection with majority voting. Two code fixes that together restore prediction for simple-verb vendors like Airbnb.

## Tasks

- [x] 1. Tenant Parameter Threading — CSV Readers
  - [x] 1.1 Add `administration: str` parameter to `read_rabo_csv()` in `banking_processor.py`, replace hardcoded `"GoodwinSolutions"` with the parameter
  - [x] 1.2 Add `administration: str` parameter to `read_generic_csv()` in `banking_processor.py`, replace hardcoded `"GoodwinSolutions"` with the parameter
  - [x] 1.3 Add `administration: str` parameter to `process_csv_files()`, pass it to both `read_rabo_csv()` and `read_generic_csv()`
  - [x] 1.4 Update `banking_service.py` `process_banking_files()` to pass `tenant` to `processor.process_csv_files(file_paths, tenant)`
    - _Requirements: 2.1, 2.2_

- [x] 2. Tenant Parameter Threading — Database & Transaction Logic
  - [x] 2.1 In `database.py` `insert_transaction()`: remove `"GoodwinSolutions"` default, raise `ValueError("Administration is required for tenant-scoped insert")` if Administration is missing
  - [x] 2.2 In `transaction_logic.py`: remove the fallback chain `template.get("Administration", "GoodwinSolutions")`, raise `ValueError` if administration is not present in `new_data` or `template`
  - [x] 2.3 Run existing test suite to identify any callers that now fail due to missing Administration
  - [x] 2.4 Fix any callers surfaced by 2.3
    - _Requirements: 2.3, 2.4_

- [x] 3. Checkpoint — Tenant threading complete
  - Run `pytest tests/unit/ tests/api/ -v -k "banking"` — all pass, no hardcoded tenant in data flow

- [x] 4. Majority Voting — Pattern Detection
  - [x] 4.1 Add `MAJORITY_VOTING_THRESHOLD = 0.90` constant to top of `pattern_detection.py`
  - [x] 4.2 Refactor `analyze_reference_patterns()` company-key logic: replace binary `_ambiguous` flag with a frequency tracker dict that counts occurrences per `(debet, credit)` pair for each company key
  - [x] 4.3 After the iteration loop, apply majority voting: if best combination ≥90% of total → store pattern with `confidence = majority_ratio`; otherwise mark as `_ambiguous = True`
  - [x] 4.4 Add log message when majority wins with minority outliers: pattern key, majority count, total count, outlier accounts
    - _Requirements: 2.8, 2.9, 2.10_

- [x] 5. Pattern Storage — Logging for Excluded Patterns
  - [x] 5.1 In `pattern_storage.py` `store_verb_patterns_to_database()`: when skipping an ambiguous pattern, log the pattern key, competing account combinations, and their occurrence counts instead of silent `continue`
    - _Requirements: 2.11_

- [x] 6. Checkpoint — Pattern prediction restored
  - Run pattern analysis for GoodwinSolutions and verify `AIRBNB` pattern is now stored in `pattern_verb_patterns` with confidence ~0.995

- [x] 7. Operational Fixes
  - [x] 7.1 Parameterize `seed_goodwin_str_rates.py`: change `run_seed(db=None)` to `run_seed(administration: str, db=None)`, replace hardcoded `"GoodwinSolutions"` in RATES array with the parameter
  - [x] 7.2 In `system_health_routes.py`: replace hardcoded tenant list `["GoodwinSolutions", "PeterPrive"]` with a database query for active tenants
  - [x] 7.3 Verify health check endpoint still returns results for all existing tenants
    - _Requirements: 2.5, 2.6_

- [x] 8. Documentation Cleanup
  - [x] 8.1 Replace `"GoodwinSolutions"` with `"ExampleTenant"` in docstring examples across 7 files:
    - `report_generators/aangifte_ib_generator.py`
    - `report_generators/btw_aangifte_generator.py`
    - `tenant_admin_routes.py`
    - `google_drive_service.py`
    - `tenant_module_routes.py`
    - `auth/tenant_context.py`
    - `pattern_detection.py`
    - _Requirements: 2.7_

- [x] 9. Testing
  - [x] 9.1 Unit test: `read_rabo_csv(file, "TenantA")` produces `Administration="TenantA"` in all rows
  - [x] 9.2 Unit test: `read_generic_csv(file, "TenantB")` produces `Administration="TenantB"` in all rows
  - [x] 9.3 Unit test: `insert_transaction({...no Administration...})` raises `ValueError`
  - [x] 9.4 Unit test: majority voting — 95% agreement → pattern stored with `confidence=0.95`, `_ambiguous=False`
  - [x] 9.5 Unit test: majority voting — 50/50 split → pattern marked `_ambiguous=True`
  - [x] 9.6 Unit test: majority voting — exactly 90% boundary → pattern stored
  - [x] 9.7 Unit test: majority voting — 89% → pattern marked ambiguous
  - [x] 9.8 Regression test: compound verbs (e.g., `BOOKING|5620035`) still produce individual patterns with confidence 1.0
  - [x] 9.9 Regression test: zero-conflict simple verbs still get confidence 1.0
  - [x] 9.10 Integration test: full pattern analysis for GoodwinSolutions produces AIRBNB pattern with Credit=1600

- [x] 10. Final Checkpoint — All tests pass
  - Run full backend test suite, verify AIRBNB prediction works for the original transaction

## Notes

- The 4 miscoded Airbnb transactions (IDs 61959, 61956, 61946, 61945) in closed year 2025 are a data issue, not a code fix — majority voting makes them irrelevant (4/927 = 0.4%)
- No transaction data is modified by this fix — algorithms interpret data, they never alter it
- The `save_transactions()` method in `banking_service.py` already forces `transaction["administration"] = tenant` at import time — this remains as a secondary defense layer

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "2.1", "2.2"] },
    { "id": 2, "tasks": ["2.3", "2.4"] },
    { "id": 3, "tasks": ["4.1", "4.2"] },
    { "id": 4, "tasks": ["4.3", "4.4", "5.1"] },
    { "id": 5, "tasks": ["7.1", "7.2", "8.1"] },
    { "id": 6, "tasks": ["7.3", "9.1", "9.2", "9.3"] },
    { "id": 7, "tasks": ["9.4", "9.5", "9.6", "9.7"] },
    { "id": 8, "tasks": ["9.8", "9.9", "9.10"] }
  ]
}
```
