# Ledger Account Hardcode Fix — Bugfix Design

## Overview

Multiple backend files use hardcoded ledger account numbers, hardcoded account ranges, and grouping/display fields (`Parent`, `Belastingaangifte`) as business logic to categorize accounts, determine VAT rates, and create fallback transactions. These hardcoded values are brittle and factually incorrect even for the standard Dutch chart of accounts. The fix replaces all hardcoded account resolution with lookups against three authoritative data sources:

1. **`rekeningschema.parameters`** JSON column — single source of truth for which ledger account serves which business role
2. **`TaxRateService`** — single source of truth for VAT rates and their associated ledger accounts
3. **`VW` column** (Y/N) — the only legitimate business field for P&L vs Balance sheet classification

Dead code using these incorrect patterns is removed entirely. Silent fallbacks to hardcoded defaults are replaced with explicit error messages.

## Glossary

- **Bug_Condition (C)**: Any code path that resolves a ledger account via a hardcoded number, hardcoded range, `Parent` prefix check, or silent fallback to hardcoded defaults
- **Property (P)**: All account resolution uses `rekeningschema.parameters` flags, `TaxRateService`, or the `VW` field — or fails explicitly with an error message
- **Preservation**: For tenants whose `rekeningschema.parameters` flags and `TaxRateService` rates resolve to the same accounts as the old hardcoded values, the system produces identical results
- **`rekeningschema.parameters`**: JSON column on the chart of accounts table storing account-level flags (e.g., `$.bank_account`, `$.str_revenue_account`, `$.btw_rate`)
- **`TaxRateService`**: Service class that looks up time-versioned tax rates with tenant → `_system_` fallback from the `tax_rates` table
- **`VW`**: Column on `rekeningschema` — `'Y'` = Profit & Loss account, `'N'` = Balance sheet account. Legitimate business field.
- **`Parent`**: Grouping/display column on `rekeningschema`. NOT for business logic.
- **Singleton flag**: A `rekeningschema.parameters` flag where exactly one account per tenant should have it (e.g., `$.str_revenue_account`). Query uses `LIMIT 1`.
- **Set flag**: A `rekeningschema.parameters` flag where multiple accounts per tenant can have it (e.g., `$.revenue_account`, `$.expense_account`). Query returns all matching.

## Bug Details

### Bug Condition

The bug manifests across 6 active source files and 2 dead code files. Each file resolves ledger accounts or account categories using hardcoded values instead of the authoritative data sources. The dead code files additionally contain factually incorrect categorizations (labelling `4xxx` as 'Revenue' when those are expense accounts).

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type AccountResolutionInput (file, function, resolution_method)
  OUTPUT: boolean

  RETURN input.resolution_method = 'hardcoded_account_number'
         OR input.resolution_method = 'hardcoded_account_range'
         OR input.resolution_method = 'parent_prefix_as_business_logic'
         OR input.resolution_method = 'hardcoded_date_branching_for_vat'
         OR input.resolution_method = 'silent_fallback_to_hardcoded_defaults'
         OR input.resolution_method = 'dead_code_with_hardcoded_ranges'
END FUNCTION
```

### Examples

- **STR routes**: `Credit: '8003'` hardcoded for revenue → should query `rekeningschema WHERE JSON_EXTRACT(parameters, '$.str_revenue_account') = true`
- **STR routes**: `date(2026, 1, 1)` branching for 21%/9% VAT → should call `TaxRateService.get_tax_rate(tenant, 'btw', 'accommodation', transaction_date)`
- **transaction_logic.py**: `Debet = '2010'` when only 1 transaction found → should resolve VAT account from `TaxRateService`; `"Gamma"` fallback when 0 found → should return error; `'6200'`/`'6400'` for Coursera/Netflix → should be removed (use DB accounts as template)
- **validate_pattern/database.py**: `debet < '1300' OR credit < '1300'` for bank accounts → should query `rekeningschema WHERE JSON_EXTRACT(parameters, '$.bank_account') = true`; fallback `{'Debet': '4000', 'Credit': '1300'}` → should return error
- **aangifte_ib_generator.py**: `Parent.startswith(('4','5','6','7','8','9'))` for P&L → should use `VW = 'Y'` (already available in report data)
- **seed_system_btw_rates.py**: `'2010'`, `'2021'`, `'2020'` hardcoded in seed tuples → should resolve from `rekeningschema.parameters` flags or `nl.json` template
- **nl.json**: `"parameters": null` on bank/revenue/expense accounts → should have `$.bank_account`, `$.revenue_account`, `$.expense_account`, `$.str_revenue_account`, `$.btw_rate` flags pre-set

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- All other routes in `reporting_routes.py` (`/account-summary`, `/mutaties-table`, `/balance-data`, `/trends-data`, `/filter-options`, `/check-reference`, `/reference-analysis`, `/available-*`) continue to function unchanged
- Mouse/UI interactions with STR channel revenue calculation produce identical journal entries when the tenant's `rekeningschema.parameters` resolves to account `8003` and `TaxRateService` returns the same rates as the current hardcoded values
- Pattern validation identifies the same set of bank transactions when `$.bank_account` flags identify the same accounts as those below 1300
- Aangifte IB report calculates the same resultaat when `VW = 'Y'` matches the set of accounts previously identified by Parent prefix 4-9
- `vw_mutaties` view returns the same columns and values (view itself is not modified)
- `TaxRateService` returns the same rates with existing seed data
- `btw_processor.py` continues to function (already uses `TaxRateService`)
- Existing `rekeningschema.parameters` flag queries (`$.bank_account`, `$.zzp_*`, `$.purpose`, `$.vat_netting`, `$.vat_primary`, `$.iban`) return the same results
- Existing tenants with already-configured `parameters` values are unaffected by the template update (template only applies to newly provisioned tenants)

**Scope:**
All inputs that do NOT involve hardcoded account resolution are completely unaffected. This includes all frontend code, all authentication/authorization flows, all non-affected backend routes, and all existing `rekeningschema.parameters` flag queries.

## Hypothesized Root Cause

Based on the bug analysis, the root causes are:

1. **Legacy R-script port**: The `transaction_logic.py` and `validate_pattern/database.py` code was ported from an R script that used hardcoded account numbers for a single-tenant system. The "Gamma" fallback and vendor-specific overrides (Coursera, Netflix) were quick fixes for the original single-tenant deployment.

2. **Incorrect domain knowledge in reporting**: The `get_financial_summary()` method labels `4xxx` accounts as 'Revenue' when they are actually expense accounts in the Dutch chart of accounts. The `8xxx` revenue accounts are omitted entirely. This suggests the code was written without consulting the actual chart of accounts.

3. **Missing abstraction layer**: When `str_channel_routes.py` was written, `TaxRateService` and the `rekeningschema.parameters` flag pattern did not yet exist. The hardcoded `8003` and date-branching were the only option at the time. Now that `invoice_booking_helper.py` and `payment_check_helper.py` have established the correct patterns, the STR routes should follow them.

4. **Incomplete template**: The `nl.json` chart of accounts template was created before the `rekeningschema.parameters` flag system was established. Most accounts have `"parameters": null`, so newly provisioned tenants start without any flags configured.

5. **Display field misuse**: The `aangifte_ib_generator.py` uses `Parent.startswith()` as a proxy for P&L classification, when the `VW` field already provides this information directly and is already available in the report data from `vw_mutaties`.

## Correctness Properties

Property 1: Bug Condition — Account Resolution Uses Authoritative Sources

_For any_ input where the bug condition holds (a code path previously used hardcoded account numbers, hardcoded ranges, Parent prefix checks, hardcoded date-branching, or silent fallbacks), the fixed code SHALL resolve the account from `rekeningschema.parameters` flags, `TaxRateService`, or the `VW` field — or SHALL return an explicit error when no valid configuration exists.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10**

Property 2: Preservation — Identical Results When Config Matches Old Hardcoded Values

_For any_ input where the bug condition does NOT hold (the tenant's `rekeningschema.parameters` flags and `TaxRateService` rates resolve to the same accounts as the old hardcoded values), the fixed code SHALL produce exactly the same results as the original code, preserving all existing journal entries, report calculations, bank account identification, and seed data.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10**

Property 3: Template Completeness — New Tenants Have All Required Flags

_For any_ account in the `nl.json` template, the `parameters` field SHALL include the correct flags based on the account's business role: `$.bank_account` on bank accounts, `$.revenue_account` on revenue accounts, `$.expense_account` on expense accounts, `$.str_revenue_account` on the STR revenue account, and `$.btw_rate` on revenue accounts indicating their VAT treatment.

**Validates: Requirements 2.10**

Property 4: Explicit Error on Missing Configuration

_For any_ input where a required account flag or tax rate is not configured for a tenant, the fixed code SHALL return an explicit error message identifying the missing configuration, instead of silently falling back to hardcoded defaults.

**Validates: Requirements 2.5, 2.7**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**1. Dead Code Removal (Defects 1.1, 1.2 / Fixes 2.1, 2.2)**

**File**: `backend/src/reporting_routes.py`

- Remove the `get_financial_summary()` method from `ReportingService` class (lines ~69-140)
- Remove the `get_financial_summary()` route handler at `/financial-summary` (lines ~185-215)
- Remove associated tests in `test_reporting_routes.py` that test this method/route
- Leave all other routes and methods untouched

**File**: `backend/src/reporting_routes_tenant_example.py`

- Delete the entire file
- Verify no imports reference it (confirmed: blueprint `reporting_tenant_example_bp` is never registered in `app.py`)

**2. STR Channel Routes Fix (Defects 1.3, 1.4 / Fixes 2.3, 2.4)**

**File**: `backend/src/str_channel_routes.py`

**Function**: `calculate_str_channel_revenue()`

**Specific Changes**:

1. **Import TaxRateService**: Add `from services.tax_rate_service import TaxRateService`
2. **Resolve STR revenue account**: Replace hardcoded `'8003'` with a query:
   ```python
   # Resolve STR revenue account from rekeningschema.parameters
   str_revenue_rows = db.execute_query(
       """SELECT Account FROM rekeningschema
          WHERE administration = %s
            AND JSON_EXTRACT(parameters, '$.str_revenue_account') = true
          ORDER BY Account LIMIT 1""",
       (administration,)
   )
   if not str_revenue_rows:
       return jsonify({'success': False, 'error': 'No STR revenue account configured. Set $.str_revenue_account flag in rekeningschema.'}), 400
   str_revenue_account = str_revenue_rows[0]['Account']
   ```
3. **Replace date-branching with TaxRateService**: Replace the hardcoded `date(2026, 1, 1)` / 21% / 9% logic with:
   ```python
   tax_svc = TaxRateService(db)
   rate_info = tax_svc.get_tax_rate(administration, 'btw', 'accommodation', transaction_date)
   if not rate_info:
       return jsonify({'success': False, 'error': f'No BTW accommodation rate configured for {end_date}'}), 400
   vat_rate = rate_info['rate']
   vat_base = 100.0 + vat_rate
   vat_account = rate_info['ledger_account']
   ```
4. **Use resolved accounts in transactions**: Replace `'8003'` references with `str_revenue_account` and `vat_account`

**3. Transaction Logic Fix (Defect 1.5 / Fix 2.5)**

**File**: `backend/src/transaction_logic.py`

**Function**: `get_last_transactions()`

**Specific Changes**:

1. **Remove Gamma fallback**: Delete the entire `if not results:` block that queries for "Gamma%" transactions. When 0 results are found, return an error:
   ```python
   if not results:
       cursor.close()
       conn.close()
       return {'error': True, 'message': f'No booking history found for vendor "{transaction_number}". Manual account selection required.', 'results': []}
   ```
2. **Keep single-result VAT line creation, but resolve VAT account from TaxRateService**: The `if len(results) == 1:` block is valid — some vendors legitimately have only 1 record. Replace the hardcoded `'2010'` with a `TaxRateService` lookup:

   ```python
   if len(results) == 1:
       if transaction_number not in single_transaction_vendors:
           from services.tax_rate_service import TaxRateService
           tax_svc = TaxRateService(DatabaseManager(test_mode=self.test_mode))
           admin = administration or results[0].get('Administration', '')
           rate_info = tax_svc.get_tax_rate(admin, 'btw', 'high', datetime.now().date())
           vat_account = rate_info['ledger_account'] if rate_info else '2010'  # graceful fallback

           credit_transaction = results[0].copy()
           credit_transaction['Debet'] = vat_account
           credit_transaction['Credit'] = results[0]['Debet']
           results.append(credit_transaction)
   ```

3. **Remove vendor-specific overrides**: Delete the Coursera/Netflix `if/elif` blocks entirely — the first record's accounts from the DB are the correct template
4. **Keep the >2 results Ref3 grouping logic** — this is correct behavior for handling multiple transactions on the same day

**File**: `backend/src/services/invoice_service.py`

**Function**: `process_file()` (caller)

**Specific Changes**:

1. **Handle error result**: Check if `last_transactions` is a dict with `'error': True` and surface the message to the user instead of proceeding with empty/invalid templates

**File**: `backend/src/pdf_processor.py`

**Function**: `_format_vendor_transactions()` (caller)

**Specific Changes**:

1. **Handle error result**: Check if `last_transactions` is a dict with `'error': True` and raise/return an error instead of using hardcoded fallback accounts `'4000'`/`'1300'`/`'2010'`

**4. Pattern Validation Fix (Defects 1.6, 1.7 / Fixes 2.6, 2.7)**

**File**: `backend/src/validate_pattern/database.py`

**Function**: `get_patterns()`

**Specific Changes**:

1. **Replace `< 1300` threshold**: Replace `AND (debet < '1300' OR credit < '1300')` with a subquery using `rekeningschema.parameters`:
   ```python
   def get_patterns(self, administration):
       return self.execute_query("""
           SELECT debet, credit, administration, referenceNumber, Date
           FROM vw_readreferences
           WHERE administration = %s
           AND (debet IN (
               SELECT Account FROM rekeningschema
               WHERE administration = %s
                 AND JSON_EXTRACT(parameters, '$.bank_account') = true
           ) OR credit IN (
               SELECT Account FROM rekeningschema
               WHERE administration = %s
                 AND JSON_EXTRACT(parameters, '$.bank_account') = true
           ))
           AND Date >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
           ORDER BY Date DESC
       """, (administration, administration, administration))
   ```

**Function**: `get_last_transactions()`

**Specific Changes**:

1. **Remove entire method**: Delete `get_last_transactions()` from `validate_pattern/database.py`
2. **Update callers**: Callers (e.g., `pdf_processor.py`) should use `transaction_logic.py`'s version instead, which will also fail explicitly per fix 2.5

**5. Aangifte IB Generator Fix (Defect 1.8 / Fix 2.8)**

**File**: `backend/src/report_generators/aangifte_ib_generator.py`

**Function**: `generate_table_rows()`

**Specific Changes**:

1. **Replace Parent prefix check with VW field**: Change:
   ```python
   # OLD: if item.get('Parent', '').startswith(('4', '5', '6', '7', '8', '9'))
   # NEW:
   resultaat = sum(
       safe_float(item.get('Amount', 0))
       for item in report_data
       if item.get('VW', '') == 'Y'
   )
   ```
2. **Verify VW is available**: The upstream query via `vw_mutaties` already includes the `VW` column in report data — no schema changes needed

**6. Seed Script Fix (Defect 1.9 / Fix 2.9)**

**File**: `backend/src/migrations/seed_system_btw_rates.py`

**Function**: `run_seed()`

**Specific Changes**:

1. **Resolve accounts from nl.json template**: Instead of hardcoding `'2010'`, `'2021'`, `'2020'`, load the canonical account numbers from the `nl.json` template by matching `$.vat_netting` and `$.vat_primary` flags:
   ```python
   import json, os
   template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'chart_of_accounts', 'nl.json')
   with open(template_path) as f:
       accounts = json.load(f)
   vat_accounts = {a['Account']: a['parameters'] for a in accounts if a.get('parameters', {}) and a['parameters'].get('vat_netting')}
   ```
2. **Map VAT codes to accounts**: Use the `vat_primary` and account names to determine which account is zero/low/high
3. **Fallback**: If the template cannot be loaded, log a warning and use the current hardcoded values as a last resort (with a deprecation notice)

**7. Template Update (Defect 1.10 / Fix 2.10)**

**File**: `backend/src/templates/chart_of_accounts/nl.json`

**Specific Changes** — add `parameters` flags to accounts based on their business role:

| Account   | AccountName                | New Flags                                                                           |
| --------- | -------------------------- | ----------------------------------------------------------------------------------- |
| 1002      | Bankrekening 1             | `{"bank_account": true}`                                                            |
| 1003      | Bankrekening 2             | `{"bank_account": true}`                                                            |
| 1004      | Bankrekening 3             | `{"bank_account": true}`                                                            |
| 4000-4099 | All expense accounts       | `{"expense_account": true}`                                                         |
| 8000      | Opbrengsten                | `{"revenue_account": true, "btw_rate": "zero"}`                                     |
| 8001      | Omzet dienstverlening      | `{"revenue_account": true, "btw_rate": "high"}`                                     |
| 8002      | Omzet ICT                  | `{"revenue_account": true, "btw_rate": "high"}`                                     |
| 8003      | Omzet verhuur              | `{"revenue_account": true, "str_revenue_account": true, "btw_rate": "low"}`         |
| 8081      | Ontvangen Rente            | `{"revenue_account": true, "btw_rate": "zero"}`                                     |
| 8082      | Ontvangen Dividend         | `{"revenue_account": true, "btw_rate": "zero"}`                                     |
| 8098-8099 | Bijzondere baten en lasten | Preserve existing `parameters`, add `{"revenue_account": true, "btw_rate": "zero"}` |

Existing `parameters` values (e.g., `vat_netting`, `vat_primary`, `asset_account`, `roles`) are preserved — new flags are merged into the existing JSON object.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that exercise each hardcoded code path and assert that the system uses authoritative data sources. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:

1. **STR Hardcoded Revenue Account Test**: Call `calculate_str_channel_revenue()` with a mock tenant and verify the generated transactions use `'8003'` — confirming the hardcode exists (will fail on unfixed code when we assert it should use the flag)
2. **STR Hardcoded VAT Date-Branching Test**: Call with dates before and after 2026-01-01 and verify the VAT rate changes based on date comparison, not `TaxRateService` (will fail on unfixed code when we assert TaxRateService is called)
3. **Transaction Logic Gamma Fallback Test**: Call `get_last_transactions()` with a vendor that has no history and verify it falls back to "Gamma" (will fail on unfixed code when we assert it returns an error)
4. **Transaction Logic Single-Result VAT Test**: Call with a vendor that has exactly 1 transaction and verify it creates a hardcoded `'2010'` VAT line (will fail on unfixed code when we assert it returns an error)
5. **Pattern Validation Bank Threshold Test**: Call `get_patterns()` and verify the query uses `< '1300'` (will fail on unfixed code when we assert it uses `$.bank_account` flag)
6. **Aangifte IB Parent Prefix Test**: Call `generate_table_rows()` with report data and verify it uses `Parent.startswith()` (will fail on unfixed code when we assert it uses `VW = 'Y'`)

**Expected Counterexamples**:

- STR routes produce transactions with hardcoded `'8003'` regardless of tenant configuration
- Transaction logic silently creates fallback entries instead of returning errors
- Pattern validation misses bank accounts numbered >= 1300
- Aangifte IB misclassifies accounts where `VW` and `Parent` prefix disagree

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedFunction(input)
  ASSERT result.account_source IN ('rekeningschema_parameters_flag', 'tax_rate_service', 'rekeningschema_vw_field', 'explicit_error')
  IF result.account_source != 'explicit_error' THEN
    ASSERT result.account = expected_account_from_config(input.tenant, input.context, input.date)
  END IF
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalFunction(input) = fixedFunction(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many test cases automatically across the input domain (different tenant configurations, different dates, different vendor names)
- It catches edge cases that manual unit tests might miss (e.g., accounts at boundary values, unusual date ranges)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for standard tenant configurations, then write property-based tests capturing that behavior.

**Test Cases**:

1. **STR Preservation**: For any tenant whose `$.str_revenue_account` resolves to `8003` and whose `TaxRateService` returns 9%/`2021` (pre-2026) or 21%/`2020` (post-2026), verify identical journal entries
2. **Pattern Validation Preservation**: For any tenant whose `$.bank_account` flags identify accounts `1001`-`1004` (same as `< 1300`), verify identical pattern results
3. **Aangifte IB Preservation**: For any report data where `VW = 'Y'` matches exactly the accounts with `Parent` starting with 4-9, verify identical resultaat calculation
4. **Seed Data Preservation**: Verify that after the seed script fix, `TaxRateService` returns the same rates and ledger accounts as the current hardcoded seed data

### Unit Tests

- Test `str_channel_routes.py` resolves revenue account from `rekeningschema.parameters` `$.str_revenue_account` flag
- Test `str_channel_routes.py` calls `TaxRateService.get_tax_rate()` with correct parameters
- Test `str_channel_routes.py` returns error when `$.str_revenue_account` flag is not configured
- Test `transaction_logic.py` returns error dict when 0 transactions found (no Gamma fallback)
- Test `transaction_logic.py` resolves VAT account from `TaxRateService` when 1 transaction found (no hardcoded `'2010'`)
- Test `transaction_logic.py` returns normal results when >= 2 transactions found
- Test `transaction_logic.py` has no Coursera/Netflix vendor-specific overrides
- Test `transaction_logic.py` single-transaction vendors list still works (1 result returned as-is)
- Test `validate_pattern/database.py` `get_patterns()` uses `$.bank_account` flag query
- Test `validate_pattern/database.py` no longer has `get_last_transactions()` method
- Test `aangifte_ib_generator.py` uses `VW = 'Y'` instead of `Parent.startswith()`
- Test `seed_system_btw_rates.py` resolves accounts from template/rekeningschema
- Test `nl.json` template has correct flags on all accounts
- Test `reporting_routes.py` no longer has `get_financial_summary()` method or route
- Test `reporting_routes_tenant_example.py` file does not exist
- Test `invoice_service.py` handles error result from `get_last_transactions()`
- Test `pdf_processor.py` handles error result from `get_last_transactions()`

### Property-Based Tests

- Generate random tenant configurations (different account numbers for STR revenue, different VAT rates) and verify STR routes use the configured values
- Generate random transaction histories (0, 1, 2, 3+ previous transactions) and verify `get_last_transactions()` returns error for 0, resolves VAT from TaxRateService for 1, and correct results for >= 2
- Generate random report data with various `VW` and `Parent` combinations and verify `generate_table_rows()` uses `VW` exclusively
- Generate random `nl.json`-like templates and verify all accounts with `VW = 'Y'` have `$.revenue_account` or `$.expense_account` flags, and all bank accounts have `$.bank_account`

### Integration Tests

- Test full STR channel revenue calculation flow with a tenant that has `$.str_revenue_account` configured
- Test full invoice processing flow where vendor has no booking history — verify error surfaces to user
- Test full pattern validation flow with a tenant whose bank accounts are identified by `$.bank_account` flag
- Test full Aangifte IB report generation with real report data — verify resultaat matches expected
- Test tenant provisioning with updated `nl.json` — verify new tenant has all flags configured
- Test that existing routes in `reporting_routes.py` still function after dead code removal
