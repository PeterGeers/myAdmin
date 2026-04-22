# Bugfix Requirements Document

## Introduction

Multiple backend files use hardcoded ledger account numbers and ranges for categorization (e.g., `4000-4999` labelled as 'Revenue' when `4xxx` are actually expenses, `8xxx` revenue accounts omitted entirely, `2010` assumed as the only VAT account). This is brittle and **factually incorrect** even for the standard Dutch chart of accounts — if the chart of accounts changes or a tenant uses different numbering, the system silently produces wrong categorizations, wrong VAT calculations, and broken reports.

The fix replaces all hardcoded account numbers and ranges with lookups against three authoritative data sources, each with a distinct responsibility:

1. **`rekeningschema` table with `parameters` JSON column** — the chart of accounts. This is the **primary mechanism for resolving which ledger account serves which business role**. The `parameters` JSON column stores account-level flags and metadata that tag individual accounts with their role. The `VW` column (Y/N) indicates whether an account is a Profit & Loss account (`VW = 'Y'`) or a Balance sheet account (`VW = 'N'`), and IS appropriate to use as business logic. However, `Parent` and `Belastingaangifte` are grouping/display columns only and must NOT drive business logic.

   **Existing `rekeningschema.parameters` flags (proven patterns already in use):**
   - `$.bank_account` (boolean) — flags bank accounts. Used in `payment_check_helper.py`: `JSON_EXTRACT(parameters, '$.bank_account') = true`
   - `$.zzp_debtor_account`, `$.zzp_creditor_account`, `$.zzp_revenue_ledger` (boolean) — ZZP booking accounts. Used in `invoice_booking_helper.py` via `LEDGER_FLAG_MAP` and validated in `zzp_routes.py`
   - `$.purpose` (string) — account purpose. Used in `year_end_config.py`: `JSON_EXTRACT(parameters, '$.purpose') = %s`
   - `$.vat_netting` (boolean), `$.vat_primary` (string — account number, e.g., `"2010"`) — VAT account flags. Used in `year_end_config.py` and `year_end_service.py`
   - `$.iban` (string) — IBAN for bank accounts. Exposed in `chart_of_accounts_routes.py`
   - `$.roles` (array) — account roles

   **New flags to be introduced by this fix** (following the same proven pattern):

   _Set flags_ — multiple accounts per tenant can have this flag (used for categorization/filtering):
   - `$.revenue_account` (boolean) — flags all revenue accounts. Query returns the full set. Useful for future reporting features and validation.
   - `$.expense_account` (boolean) — flags all operating expense accounts. Query returns the full set. Useful for future reporting features and validation.
   - `$.btw_rate` (string: `"high"`, `"low"`, or `"zero"`) — on revenue accounts, indicates the associated VAT rate. Used by the Aangifte IB report to associate revenue lines with their VAT treatment. Multiple revenue accounts can have the same `btw_rate` value.

   _Singleton flags_ — exactly one account per tenant should have this flag (used for transaction generation, query uses `LIMIT 1`):
   - `$.str_revenue_account` (boolean) — flags the single STR revenue account. Used when generating STR journal entries in `str_channel_routes.py`

   The query pattern is `JSON_EXTRACT(parameters, '$.flag_name') = true`. For set flags, the query returns all matching accounts. For singleton flags, the query uses `ORDER BY Account LIMIT 1` and the system should log a warning if more than one account is flagged. This column is the **single source of truth** for "which ledger account serves which role".

2. **`parameters` table** (via `ParameterService`) — for **generic tenant/system configuration only**. This stores non-ledger settings such as folder paths, download paths, and other system-level configuration. This table is **NOT** the right place for resolving which account is the bank account, revenue account, etc. — that belongs in `rekeningschema.parameters`.

3. **`tax_rates` table** (via `TaxRateService`) — the single source of truth for VAT rates and their associated ledger accounts, replacing hardcoded VAT accounts (`2010`, `2020`, `2021`) and date-branching logic.

**Key principle:** `rekeningschema.parameters` JSON column is the single source of truth for "which ledger account serves which role". The generic `parameters` table is for non-ledger configuration only.

**Affected files (active code — to be fixed):**

1. `backend/src/str_channel_routes.py` — Hardcoded revenue account `8003`, VAT accounts `2020`/`2021`, and date-branching for 2026 VAT rate change. **Active**: registered in `app.py`, called from frontend.
2. `backend/src/transaction_logic.py` — Vendor-specific hardcoded accounts (`6200`, `6400`, `1600`, `2010`). **Active**: called from `invoice_service.py` for invoice processing.
3. `backend/src/validate_pattern/database.py` — Bank threshold `< 1300`, fallback accounts `4000`/`1300`/`2010`. **Active**: called from `pdf_processor.py`. Also contains a duplicate `get_last_transactions()` that duplicates `transaction_logic.py`.
4. `backend/src/report_generators/aangifte_ib_generator.py` — P&L detection via `startswith(('4','5','6','7','8','9'))` instead of `VW` field. **Active**: used for IB report generation.
5. `backend/src/migrations/seed_system_btw_rates.py` — Hardcodes ledger accounts `2010`, `2021`, `2020` in seed data.
6. `backend/src/templates/chart_of_accounts/nl.json` — Default chart of accounts template has `"parameters": null` on most accounts, missing the new flags that should be set at onboarding.

**Dead code (to be removed, not fixed):**

7. `backend/src/reporting_routes.py` — `get_financial_summary()` with hardcoded CASE/WHERE ranges. The blueprint is registered in `app.py` at `/api/reports/financial-summary`, but **no frontend code calls this endpoint**. The hardcoded ranges are also factually incorrect (labels `4xxx` as 'Revenue' when those are expense accounts). **Action: remove the `get_financial_summary()` method and its route handler.** The other routes in `reporting_routes.py` (`/account-summary`, `/mutaties-table`, `/balance-data`, `/trends-data`, `/filter-options`, `/check-reference`, `/reference-analysis`, `/available-*`) are active and do NOT use hardcoded account ranges — they use `vw_mutaties` columns correctly.
8. `backend/src/reporting_routes_tenant_example.py` — Entire file is dead code. The blueprint `reporting_tenant_example_bp` is **never registered in `app.py`** and **never imported anywhere**. Contains a copy of the same incorrect hardcoded ranges. **Action: delete the entire file.**

## Bug Analysis

### Current Behavior (Defect)

1.1 **DEAD CODE**: `get_financial_summary()` in `reporting_routes.py` uses hardcoded CASE statements with account ranges (`4000-4999` = 'Revenue', `6000-6999` = 'Operating Expenses', etc.) that are **factually incorrect** — `4xxx` are actually expense accounts, `8xxx` revenue accounts are omitted, `1xxx` are activa, `2xxx` are tussenrekeningen, `3xxx` are passiva. No frontend code calls the `/api/reports/financial-summary` endpoint. **Action: remove the dead method and route.**

1.2 **DEAD CODE**: `reporting_routes_tenant_example.py` is an entire dead file — the blueprint is never registered in `app.py` and never imported. Contains a copy of the same incorrect hardcoded ranges. **Action: delete the file.**

1.3 WHEN STR revenue transactions are generated in `str_channel_routes.py` THEN the system hardcodes revenue account `8003` and VAT accounts `2020`/`2021` instead of resolving the revenue account from `rekeningschema.parameters` (via `$.str_revenue_account = true` flag) and VAT accounts from `TaxRateService`, producing incorrect journal entries for tenants with different account numbering

1.4 WHEN STR VAT rate is determined in `str_channel_routes.py` THEN the system uses hardcoded date-branching (`date(2026, 1, 1)` → 21% / 9%) instead of calling `TaxRateService.get_tax_rate()` with the transaction date, which will break for tenants whose accommodation VAT rate change date differs

1.5 WHEN `get_last_transactions()` in `transaction_logic.py` finds exactly 1 previous transaction for a vendor (edge case — normally the DB returns a debet/credit pair) THEN the system creates a second VAT line with hardcoded `Debet = '2010'` and overrides accounts for specific vendors (`6200`/`1600` for Coursera, `6400`/`1600` for Netflix) instead of resolving the VAT account from `TaxRateService`. The single-result VAT line creation itself is valid (some vendors legitimately have only 1 record in the DB and need a VAT line generated), but the hardcoded `'2010'` and vendor-specific overrides are wrong. Separately, when no transactions are found at all, the system silently falls back to "Gamma" transactions — masking the fact that the vendor has no booking history

1.6 WHEN pattern validation queries bank transactions in `validate_pattern/database.py` THEN the system uses hardcoded threshold `< 1300` to identify bank accounts instead of querying `rekeningschema` for accounts where `JSON_EXTRACT(parameters, '$.bank_account') = true` (the proven pattern already used in `payment_check_helper.py`), missing bank accounts numbered above 1300

1.7 WHEN pattern validation creates fallback transaction records in `validate_pattern/database.py` THEN the system silently hardcodes default accounts `4000`/`1300`/`2010` instead of failing with a clear error message when no valid transaction template exists. This masks data quality issues and produces incorrect entries. Additionally, `validate_pattern/database.py` contains a duplicate `get_last_transactions()` method that duplicates logic in `transaction_logic.py` — this duplication should be consolidated

1.8 WHEN `aangifte_ib_generator.py` calculates the P&L resultaat THEN the system identifies P&L accounts by checking if `Parent` starts with `('4','5','6','7','8','9')` — using the `Parent` grouping/display field instead of the `VW` field which is already available in the report data (the upstream query in `vw_mutaties` already filters by `VW`). Additionally, the revenue accounts (`8001`-`8003`) have no `rekeningschema.parameters` flags indicating their associated BTW rate (high/low/zero), so the report cannot properly associate revenue lines with their VAT treatment. The 3 VAT accounts (`2010` paid, `2020` received high, `2021` received low) already have `vat_netting` flags but the revenue accounts lack a corresponding `$.btw_rate` indicator

1.9 WHEN `seed_system_btw_rates.py` seeds system default BTW rates THEN the system hardcodes ledger accounts `2010`, `2021`, `2020` directly in the seed data instead of resolving them from `rekeningschema.parameters` flags, meaning the seed data is disconnected from the chart of accounts and will be wrong if a tenant's VAT accounts use different numbers

1.10 WHEN a new tenant is provisioned via `tenant_provisioning_service.py` THEN the system loads the `nl.json` chart of accounts template which has `"parameters": null` on most accounts, meaning the new tenant has no `rekeningschema.parameters` flags set (no `$.bank_account`, `$.revenue_account`, `$.expense_account`, `$.default_debtor_account`, etc.), so all flag-based lookups will fail until an admin manually configures them

### Expected Behavior (Correct)

2.1 **DEAD CODE REMOVAL**: The `get_financial_summary()` method in `ReportingService` and its route handler `get_financial_summary()` at `/financial-summary` SHALL be removed from `reporting_routes.py`. The associated tests in `test_reporting_routes.py` that test this method/route SHALL also be removed. Other routes in the same file are unaffected.

2.2 **DEAD CODE REMOVAL**: The entire file `reporting_routes_tenant_example.py` SHALL be deleted. No other code references it.

2.3 WHEN STR revenue transactions are generated in `str_channel_routes.py` THEN the system SHALL resolve the STR revenue account by querying `rekeningschema` WHERE `JSON_EXTRACT(parameters, '$.str_revenue_account') = true` for the tenant, and resolve the VAT account from `TaxRateService.get_tax_rate()`, so that journal entries use the correct tenant-configured accounts

2.4 WHEN STR VAT rate is determined in `str_channel_routes.py` THEN the system SHALL call `TaxRateService.get_tax_rate(administration, 'btw', 'accommodation', transaction_date)` to retrieve the applicable rate and ledger account, so that the correct rate is applied regardless of when the rate change occurs per tenant

2.5 WHEN `get_last_transactions()` in `transaction_logic.py` finds exactly 1 previous transaction for a vendor THEN the system SHALL keep the VAT line creation logic (creating a second record from the first) but SHALL resolve the VAT account from `TaxRateService` instead of hardcoding `'2010'`. The Coursera/Netflix vendor-specific account overrides SHALL be removed — the first record's accounts from the DB are the correct template. WHEN no transactions are found at all (0 results), the Gamma fallback SHALL be removed and the system SHALL return an error result indicating no booking history exists. The caller (e.g., `invoice_service.py`) SHALL handle this error by informing the user that manual account selection is required

2.6 WHEN pattern validation queries bank transactions in `validate_pattern/database.py` THEN the system SHALL query `rekeningschema` WHERE `JSON_EXTRACT(parameters, '$.bank_account') = true` AND `administration = %s` to resolve the list of bank accounts for the tenant (following the proven pattern already used in `payment_check_helper.py`), instead of the hardcoded `< 1300` threshold

2.7 WHEN pattern validation in `validate_pattern/database.py` cannot find a valid transaction template (0 or 1 results) THEN the system SHALL return an error result instead of silently creating fallback entries with hardcoded accounts. The duplicate `get_last_transactions()` in `validate_pattern/database.py` SHALL be removed and consolidated to use `transaction_logic.py`'s version (which will also fail explicitly per 2.5)

2.8 WHEN `aangifte_ib_generator.py` calculates the P&L resultaat THEN the system SHALL use `VW = 'Y'` from the report data (already available from `vw_mutaties`) to identify P&L accounts, instead of checking Parent prefix digits. Additionally, revenue accounts SHALL have a `$.btw_rate` flag in `rekeningschema.parameters` indicating their associated VAT rate (`high`, `low`, or `zero`), so the report can associate each revenue line with its VAT treatment. The `nl.json` template SHALL set `$.btw_rate` on revenue accounts (e.g., `"btw_rate": "high"` on `8001`/`8002`, `"btw_rate": "low"` on `8003` for STR revenue)

2.9 WHEN `seed_system_btw_rates.py` seeds system default BTW rates THEN the system SHALL resolve the ledger accounts from `TaxRateService` or by querying `rekeningschema` for accounts with existing `$.vat_netting = true` and `$.vat_primary` flags for the `_system_` administration, or if no `_system_` rekeningschema exists, use the accounts defined in the `nl.json` template as the canonical defaults. The seed script SHALL NOT hardcode account numbers `2010`, `2021`, `2020` directly

2.10 WHEN a new tenant is provisioned via `tenant_provisioning_service.py` THEN the `nl.json` chart of accounts template SHALL include the correct `rekeningschema.parameters` flags pre-configured on the appropriate accounts, so that the tenant works correctly from day one without manual flag configuration. The flags SHALL be set per account based on the account's actual business role in the chart of accounts — not based on account number ranges. At minimum, the template SHALL set: `$.bank_account = true` on bank accounts, `$.revenue_account = true` on revenue accounts, `$.expense_account = true` on operating expense accounts, `$.str_revenue_account = true` on the STR revenue account, and `$.btw_rate` (`"high"`, `"low"`, or `"zero"`) on revenue accounts to indicate their associated VAT rate

### Unchanged Behavior (Regression Prevention)

3.1 WHEN `get_financial_summary()` and its route are removed THEN no other routes in `reporting_routes.py` SHALL be affected — `/account-summary`, `/mutaties-table`, `/balance-data`, `/trends-data`, `/filter-options`, `/check-reference`, `/reference-analysis`, and `/available-*` SHALL CONTINUE TO function unchanged

3.2 WHEN `reporting_routes_tenant_example.py` is deleted THEN no other code SHALL be affected, since the file was never imported or registered

3.3 WHEN STR revenue transactions are generated for a tenant whose `rekeningschema.parameters` `$.str_revenue_account` flag resolves to account `8003` and whose `TaxRateService` returns the same rates as the current hardcoded values (9% low / 21% high with matching ledger accounts) THEN the system SHALL CONTINUE TO produce identical journal entries with the same amounts and account numbers

3.4 WHEN pattern validation processes transactions for a tenant whose `rekeningschema.parameters` `$.bank_account` flags identify the same accounts as those below 1300 THEN the system SHALL CONTINUE TO identify the same set of bank transactions as before

3.5 WHEN `aangifte_ib_generator.py` processes report data for a tenant whose `rekeningschema` P&L accounts (identified by `VW = 'Y'`) match the set of accounts previously identified by the Parent prefix 4-9 check THEN the system SHALL CONTINUE TO calculate the same resultaat total as before

3.6 WHEN the `vw_mutaties` view is queried THEN the system SHALL CONTINUE TO return the same columns (`Aangifte`, `Parent`, `VW`, `Reknum`, `AccountName`, etc.) with the same values, since the view itself is not modified

3.7 WHEN `TaxRateService` is called with existing seed data (BTW zero/low/high rates) THEN the system SHALL CONTINUE TO return the same rates and ledger accounts as currently seeded

3.8 WHEN the `btw_processor.py` module processes VAT declarations THEN the system SHALL CONTINUE TO function correctly, since it already uses `TaxRateService` with fallback defaults

3.9 WHEN existing code queries `rekeningschema.parameters` for `$.bank_account`, `$.zzp_debtor_account`, `$.zzp_creditor_account`, `$.zzp_revenue_ledger`, `$.purpose`, `$.vat_netting`, `$.vat_primary`, or `$.iban` flags THEN the system SHALL CONTINUE TO return the same results, since existing flags are not modified

3.10 WHEN an existing tenant already has `rekeningschema` rows with `parameters` values set (e.g., from manual configuration or previous provisioning) THEN the template update SHALL NOT affect those tenants — the template only applies to newly provisioned tenants

---

## Bug Condition

### Bug Condition Function

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type AccountResolutionInput (tenant, account_number, transaction_date, resolution_context)
  OUTPUT: boolean

  // Returns true when the system uses a hardcoded account number, hardcoded
  // account range, a grouping/display field (Parent, Belastingaangifte)
  // as business logic, or silently falls back to hardcoded defaults instead
  // of failing explicitly.
  // Note: VW (Y/N) is a legitimate business field indicating P&L vs Balance
  // and is NOT considered a bug when used as business logic.

  RETURN X.account_source = 'hardcoded_number'
         OR X.account_source = 'hardcoded_range'
         OR X.account_source = 'parent_field_as_logic'
         OR X.account_source = 'belastingaangifte_field_as_logic'
         OR X.account_source = 'silent_fallback_to_hardcoded'
END FUNCTION
```

### Fix Checking Property

```pascal
// Property: Fix Checking — All account resolution uses rekeningschema.parameters flags, TaxRateService, or fails explicitly
FOR ALL X WHERE isBugCondition(X) DO
  result ← resolve_account'(X)
  ASSERT result.account_source IN ('rekeningschema_parameters_flag', 'tax_rate_service', 'rekeningschema_vw_field', 'explicit_error')
  IF result.account_source != 'explicit_error' THEN
    ASSERT result.account = expected_account_from_config(X.tenant, X.resolution_context, X.transaction_date)
  END IF
END FOR
```

### Preservation Checking Property

```pascal
// Property: Preservation Checking — Non-buggy inputs unchanged
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
  // Tenants whose rekeningschema.parameters flags / tax_rates / VW values
  // resolve to the same accounts as the old hardcoded values get identical results
END FOR
```
