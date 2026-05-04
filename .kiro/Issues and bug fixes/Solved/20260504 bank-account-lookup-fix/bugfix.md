# Bugfix Requirements Document

## Introduction

The Banking Processor's "Check Accounts", "Check Sequence", and "Select Account" features no longer display bank accounts belonging to the current tenant. The account selection dropdown is empty or shows incorrect accounts. This is caused by two issues: (1) the `get_lookups` method was trapped inside a string literal (dead code — already fixed), and (2) the data sources used to resolve bank accounts still rely on outdated views (`vw_rekeningnummers`, `vw_lookup_accounts`) that use the old `Pattern IS NOT NULL` / `AccountLookup IS NOT NULL` approach instead of querying the `rekeningschema.parameters` JSON column with the `$.bank_account` flag. The `check_banking_accounts` method in `banking_processor.py` also queries `vw_rekeningnummers` directly with raw cursor access instead of going through the `DatabaseManager` abstraction layer.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user opens the Banking Processor and the "Check Accounts" tab loads THEN the system queries `vw_rekeningnummers` (which uses `WHERE Pattern IS NOT NULL`) and may return no accounts or wrong accounts for the current tenant because accounts flagged only via `$.bank_account = true` in the `parameters` JSON column are missed

1.2 WHEN a user selects an account in the "Check Sequence" or "Select Account" dropdown THEN the dropdown is empty or incomplete because `get_lookups()` returns bank accounts from `get_bank_account_lookups()` which now correctly uses `$.bank_account`, but `check_banking_accounts()` in `banking_processor.py` still queries `vw_rekeningnummers` directly, creating an inconsistency between the two code paths

1.3 WHEN the `processFiles` function validates IBANs against `lookupData.bank_accounts` THEN the validation may incorrectly reject valid files because the bank account list was previously empty (due to the dead code bug in `get_lookups`) and the data source inconsistency means the IBAN-to-tenant mapping can be incomplete

1.4 WHEN `validate_iban_tenant()` checks whether an IBAN belongs to the current tenant THEN the system queries `vw_lookup_accounts` (which uses `WHERE AccountLookup IS NOT NULL`) instead of using the `$.bank_account` parameter flag, creating yet another inconsistent data source for bank account resolution

1.5 WHEN `check_banking_accounts()` in `banking_processor.py` accesses the database THEN it uses raw `conn.cursor()` calls instead of the `DatabaseManager` abstraction layer, violating the project's database access patterns

1.6 WHEN a Revolut file (TSV or CSV starting with "account-statement") is processed THEN the frontend hardcodes the IBAN `NL08REVO7549383472` in `processRevolutTransaction()` and in the `processFiles()` IBAN validation, instead of looking up the Revolut bank account from `lookupData.bank_accounts` using the `$.bank_account` flag like any other bank account. This means: (a) the Revolut IBAN for a different tenant (e.g. `NL05REVO8814090866`) is never used, (b) transactions are always assigned to the wrong tenant/account if the Revolut account differs, and (c) the file processing validation incorrectly matches against a hardcoded IBAN instead of the tenant's actual Revolut account

1.7 WHEN a Rabobank CSV file is processed THEN `processRabobankTransaction()` uses hardcoded fallback account code `'1002'` and administration `'GoodwinSolutions'` when the IBAN is not found in `lookupData.bank_accounts`, instead of using the current tenant from context

1.8 WHEN Revolut transactions are created THEN `processRevolutTransaction()` uses hardcoded fallback account code `'1023'` and administration `'PeterPrive'` when `bankLookup` is not found, instead of using the current tenant from context

### Expected Behavior (Correct)

2.1 WHEN a user opens the Banking Processor and the "Check Accounts" tab loads THEN the system SHALL query `rekeningschema` using `JSON_EXTRACT(parameters, '$.bank_account') = true` filtered by the current tenant's administration, returning all bank accounts that have the `$.bank_account` flag set

2.2 WHEN a user selects an account in the "Check Sequence" or "Select Account" dropdown THEN the dropdown SHALL show all bank accounts for the current tenant resolved from the `$.bank_account` parameter flag, consistent with the accounts shown in "Check Accounts"

2.3 WHEN the `processFiles` function validates IBANs against `lookupData.bank_accounts` THEN the validation SHALL use the bank account list populated from the `$.bank_account` parameter flag, correctly identifying which IBANs belong to the current tenant

2.4 WHEN `validate_iban_tenant()` checks whether an IBAN belongs to the current tenant THEN the system SHALL query `rekeningschema` using `JSON_EXTRACT(parameters, '$.bank_account') = true` (or the equivalent `get_bank_account_lookups()` method) instead of querying `vw_lookup_accounts`

2.5 WHEN `check_banking_accounts()` in `banking_processor.py` accesses the database THEN it SHALL use the `DatabaseManager` abstraction layer (`execute_query`, `get_cursor`, or `transaction` context managers) instead of raw `conn.cursor()` calls

2.6 WHEN a Revolut file is processed THEN the system SHALL look up the Revolut bank account from `lookupData.bank_accounts` (populated via the `$.bank_account` parameter flag) by matching the IBAN found in the file or by identifying Revolut accounts (IBAN containing "REVO") in the tenant's bank account list. The hardcoded IBAN `NL08REVO7549383472` SHALL be removed from `processRevolutTransaction()`, the `processFiles()` validation, and the bank account lookup in file processing. Each tenant's Revolut account (with its own IBAN stored in `rekeningschema.parameters.$.iban`) SHALL be used for that tenant's Revolut file processing

2.7 WHEN any bank file (Rabobank or Revolut) is processed and the IBAN is not found in `lookupData.bank_accounts` THEN the system SHALL show a clear error message (e.g. "Bank account [IBAN] is not configured for this tenant. Please add it in Chart of Accounts with the bank_account flag.") and stop processing — no hardcoded fallback tenant names or account codes

2.8 All hardcoded fallback values for Rabobank and Revolut processing SHALL be removed entirely: no fallback IBANs (`NL08REVO7549383472`), no fallback account codes (`'1002'`, `'1023'`), no fallback tenant names (`'PeterPrive'`, `'GoodwinSolutions'`). If the bank account lookup fails, the system SHALL fail with a descriptive error rather than silently using wrong defaults

**Out of scope**: Credit card file processing (`CSV_CC_*`) with its hardcoded account codes (`'4002'`, `'2001'`) and IBAN-to-tenant mapping (`NL71RABO0148034454`) — this requires a separate `$.credit_card` parameter flag or similar identifier and will be addressed in a future spec

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user uploads a CSV bank statement file for a valid IBAN belonging to the current tenant THEN the system SHALL CONTINUE TO accept and process the file successfully

3.2 WHEN a user uploads a CSV bank statement file for an IBAN belonging to a different tenant THEN the system SHALL CONTINUE TO reject the file with an appropriate access denied message

3.3 WHEN the "Check Accounts" tab calculates balances from `vw_mutaties` THEN the system SHALL CONTINUE TO return correct calculated balances, last transaction dates, and last transaction details for each bank account

3.4 WHEN `get_patterns()` resolves bank accounts for pattern matching THEN the system SHALL CONTINUE TO use the `$.bank_account` flag query (this was already fixed in a prior spec and must not regress)

3.5 WHEN the Chart of Accounts management displays bank account flags THEN the system SHALL CONTINUE TO correctly show `$.bank_account` parameter values from the `parameters` JSON column

3.6 WHEN a Revolut file is processed for a tenant that has a Revolut bank account (with `$.bank_account = true` and an IBAN containing "REVO") THEN the system SHALL use that tenant's Revolut IBAN from `rekeningschema.parameters.$.iban` for Ref1, account code resolution, and tenant validation — not a hardcoded IBAN

## Test Health Scan Findings

Related issues from `backend/tests/reports/scan_20260503_110730.json` that must be addressed as part of this bugfix:

### Test Drift (will break or become stale after fix)

4.1 **`test_database.py` ↔ `database.py`** — `test_get_bank_account_lookups` tests the old `vw_rekeningnummers` query. After changing `get_bank_account_lookups()` to use `JSON_EXTRACT(parameters, '$.bank_account') = true`, this test must be updated to mock and assert the new query.

4.2 **`test_banking_processor.py` ↔ `banking_processor.py`** — 15 drift issues (severity: low). Test mock data is missing keys `Administration`, `ReferenceNumber`, `Ref1`–`Ref4`, `start_date`, `account_code`. When `check_banking_accounts()` is changed from `vw_rekeningnummers` to the `$.bank_account` flag query, these tests need updated mocks.

4.3 **`chart_of_accounts_routes.py` tests** — 4 drift issues where tests don't reference the `bank_account` key from source response dicts (lines 361, 1177). Tests should validate the `$.bank_account` parameter flag since the bugfix relies on it being correctly set.

### Compliance Violations (required severity)

4.4 **`test_database.py`** — 13 BU001 violations (severity: **required**). Uses `mysql.connector` directly and `DatabaseManager(test_mode=...)` instead of the `mock_db` fixture. Since we're modifying `get_bank_account_lookups()`, the test should be rewritten to use `mock_db` per project conventions.

4.5 **`test_database.py`** — 1 BU003 violation (severity: **required**). Uses `sys.path.append` instead of `conftest.py` for path setup.

### Dead Code

4.6 **`banking_processor.py` lines 928–1086** — Contains an entire standalone Flask app with duplicate route handlers (`scan_files`, `process_files`, `save_transactions`, `check_banking_accounts`, `check_sequence_numbers`, `analyze_patterns`, `get_pattern_summary`) that were superseded by `banking_routes.py` during the blueprint refactoring. These dead routes also contain hardcoded values (`'GoodwinSolutions'`, `'NL80RABO0107936917'`). The entire block from `app = Flask(__name__)` through `if __name__ == '__main__'` should be removed.

4.7 **`banking_processor.py` hardcoded method defaults** — Several class methods use hardcoded default parameter values that should be required arguments instead:

- `analyze_patterns_for_administration(administration='GoodwinSolutions')` (line 844)
- `apply_enhanced_patterns(transactions, administration='GoodwinSolutions')` (line 887)
- `get_pattern_summary(administration='GoodwinSolutions')` (line 919)
- `check_revolut_balance_gaps(iban='NL08REVO7549383472', account_code='1022')` (line 636)
