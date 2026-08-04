# Bugfix Requirements Document

## Introduction

Multiple interrelated bugs in the banking and pattern prediction system prevent correct account predictions and violate multi-tenancy isolation. These originate from the pre-multi-tenancy era (Oct 2025) when the system only served a single administration ("GoodwinSolutions"). When multi-tenancy was added in Jan 2026, several code paths were missed.

**Bug 1** — Hardcoded tenant values throughout the codebase: CSV readers, database insert fallback, transaction logic, seed scripts, health checks, and docstrings all reference "GoodwinSolutions" instead of using the authenticated tenant or parameterized values. Some silently corrupt data, others confuse developers.

**Bug 2** — The pattern detection uses a binary ambiguity flag that poisons an entire pattern when even a single conflicting transaction exists, regardless of how many correct transactions support the majority pattern.

**Bug 3** — The pattern storage silently drops any pattern marked ambiguous, with no logging or notification, causing valid high-confidence patterns to disappear.

**Impact**: For administration "GoodwinSolutions", 923 correctly-coded Airbnb transactions (Debet=1002, Credit=1600) produce no prediction because 4 outlier transactions (0.4%) trigger the binary ambiguity flag, which then causes the pattern to be silently skipped during storage. The system predicts nothing for Airbnb bank transactions.

## Bug Analysis

### Current Behavior (Defect)

**Bug 1: Hardcoded tenant — data flow (critical)**

1.1 WHEN a tenant other than "GoodwinSolutions" uploads a Rabobank CSV file THEN the system stamps all parsed transactions with `Administration = "GoodwinSolutions"` regardless of the authenticated tenant

1.2 WHEN `banking_service.process_banking_files()` is called with a `tenant` parameter THEN the system does not pass the tenant value to `BankingProcessor.read_rabo_csv()`, leaving the hardcoded value in effect

1.3 WHEN `read_generic_csv()` processes any generic CSV THEN the system hardcodes `"Administration": "GoodwinSolutions"` (same root cause as 1.2)

1.4 WHEN `database.py` `insert_transaction()` is called without an `Administration` field in the transaction dict THEN the system silently defaults to `"GoodwinSolutions"` via `.get("Administration", "GoodwinSolutions")` — this masks bugs in callers and can silently corrupt tenant data

1.5 WHEN `transaction_logic.py` creates invoice transactions and neither `new_data["administration"]` nor `template["Administration"]` is set THEN the system silently falls back to `"GoodwinSolutions"` instead of raising an error

**Bug 1: Hardcoded tenant — operational (non-data-flow but still broken)**

1.6 WHEN `seed_goodwin_str_rates.py` seeds tax rates THEN the administration is hardcoded in the data array rather than parameterized — the script cannot be reused for other tenants and creates an implicit coupling to the tenant name

1.7 WHEN `system_health_routes.py` checks Google Drive token health THEN it iterates over a hardcoded list `["GoodwinSolutions", "PeterPrive"]` instead of querying active tenants from the database — new tenants are silently excluded from health monitoring

**Bug 1: Hardcoded tenant — docstrings (confusing)**

1.8 WHEN docstrings/comments in `report_generators/aangifte_ib_generator.py`, `report_generators/btw_aangifte_generator.py`, `tenant_admin_routes.py`, `google_drive_service.py`, `tenant_module_routes.py`, and `auth/tenant_context.py` use `"GoodwinSolutions"` as example values THEN developers cannot tell if the value is dynamic or intentionally hardcoded — examples should use a generic placeholder

**Bug 2: Binary ambiguity flag**

1.9 WHEN a **simple (non-compound)** verb pattern (e.g., `GoodwinSolutions_1002_AIRBNB`) has even one historical transaction with different debet/credit accounts than the majority THEN the system sets `_ambiguous = True` and `confidence = 0.0` for the entire pattern — this only affects vendors whose descriptions lack a reference/invoice number (producing a simple verb like `AIRBNB`), not vendors like Booking.com whose descriptions contain unique IDs (producing compound verbs like `BOOKING|5615303` that each get their own key)

1.10 WHEN 923 transactions agree on Credit=1600 but 4 transactions have Credit=8003 for the same verb key THEN the system treats the pattern as completely ambiguous rather than using frequency-based resolution

**Bug 3: Silent pattern dropping**

1.11 WHEN `store_verb_patterns_to_database()` encounters a pattern with `_ambiguous = True` THEN the system silently skips it with `continue` — no logging, no admin notification, no record that a pattern was discovered and discarded

1.12 WHEN a valid high-frequency pattern is skipped during storage THEN the system produces no prediction for matching future transactions, failing silently without any indication to the user

### Expected Behavior (Correct)

**Bug 1 fixes: Tenant must flow from session, never hardcoded**

2.1 WHEN any tenant uploads a Rabobank CSV file THEN the system SHALL use the authenticated tenant from `@tenant_required()` as the `Administration` value for all parsed transactions

2.2 WHEN `banking_service.process_banking_files()` is called with a `tenant` parameter THEN the system SHALL pass the tenant value through to `BankingProcessor.process_csv_files()` → `read_rabo_csv()` / `read_generic_csv()` so it is used instead of a hardcoded value

2.3 WHEN `database.py` `insert_transaction()` is called without an `Administration` field THEN the system SHALL raise a `ValueError("Administration is required for tenant-scoped insert")` instead of silently defaulting — this forces callers to provide the tenant explicitly

2.4 WHEN `transaction_logic.py` creates invoice transactions THEN the system SHALL require the administration to be present in `new_data["administration"]` and SHALL raise an error if it is missing, rather than falling back to a hardcoded value

2.5 WHEN `seed_goodwin_str_rates.py` seeds tax rates THEN the administration SHALL be a parameter to `run_seed(administration)` so the script can be reused for any tenant

2.6 WHEN `system_health_routes.py` checks Google Drive token health THEN the system SHALL query active tenants from the database (or a tenant registry) instead of using a hardcoded list

2.7 WHEN docstrings use tenant names as examples THEN they SHALL use `"ExampleTenant"` or `"MyTenant"` as a generic placeholder to avoid confusion with production values

**Bug 2 fixes: Majority voting replaces binary ambiguity**

2.8 WHEN a company-level verb pattern has conflicting historical transactions THEN the system SHALL use majority voting (frequency-based resolution) to determine the correct accounts, rather than a binary ambiguity flag

2.9 WHEN more than 90% of occurrences for a verb key agree on the same debet/credit accounts THEN the system SHALL keep the majority pattern with a confidence score reflecting the agreement ratio (e.g., 923/927 = 0.995)

2.10 WHEN a pattern cannot be resolved by majority voting (no single account combination exceeds the 90% threshold) THEN the system SHALL mark it as genuinely ambiguous and log a warning identifying the competing account combinations and their counts

**Bug 3 fixes: Pattern exclusion must be visible**

2.11 WHEN a pattern is excluded from storage due to ambiguity THEN the system SHALL log the exclusion with pattern key, occurrence counts per account combination, and the threshold it failed to meet

2.12 WHEN a pattern that previously existed in the database is replaced by an ambiguous version on re-analysis THEN the system SHALL preserve the existing pattern rather than deleting it — patterns should only be overwritten by higher-confidence data

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a tenant with name "GoodwinSolutions" uploads a Rabobank CSV file THEN the system SHALL CONTINUE TO produce transactions with `Administration = "GoodwinSolutions"` (same end result via tenant parameter rather than hardcoding)

3.2 WHEN a compound verb pattern (e.g., `BOOKING|5620035`) has unique account mappings per reference THEN the system SHALL CONTINUE TO store each compound pattern individually with confidence 1.0

3.3 WHEN all historical transactions for a simple verb key agree on the same debet/credit accounts (no conflicts) THEN the system SHALL CONTINUE TO store the pattern with confidence 1.0

3.4 WHEN the IBAN validation in `process_banking_files()` detects a mismatch between file IBAN and tenant THEN the system SHALL CONTINUE TO reject the file with an error

3.5 WHEN a pattern has zero conflicts THEN the system SHALL CONTINUE TO store it without any ambiguity-related processing overhead

3.6 WHEN `save_transactions()` in `banking_service.py` forces `transaction["administration"] = tenant` THEN this import-time enforcement SHALL CONTINUE TO function as a secondary defense layer

3.7 WHEN a genuine multi-product vendor (e.g., ASR with multiple insurance products) has no single account combination exceeding 90% THEN the system SHALL CONTINUE TO mark the company-level pattern as ambiguous and not predict

---

## Bug Condition Derivation

### Bug 1: Hardcoded Tenant

```pascal
FUNCTION isBugCondition_Bug1(X)
  INPUT: X of type CSVImportOrInsert
  OUTPUT: boolean

  // Returns true when the code uses a hardcoded tenant instead of session tenant
  RETURN (X.type = "csv_read" AND X.administration_source = "hardcoded")
      OR (X.type = "db_insert" AND X.administration_missing AND X.uses_default)
      OR (X.type = "transaction_logic" AND X.administration_missing AND X.uses_fallback)
      OR (X.type = "seed_script" AND X.administration_source = "hardcoded")
      OR (X.type = "health_check" AND X.tenant_list_source = "hardcoded")
END FUNCTION
```

```pascal
// Property: Fix Checking — No silent defaults
FOR ALL X WHERE X.type = "db_insert" AND X.administration_missing DO
  ASSERT insert_transaction'(X) RAISES ValueError
END FOR

// Property: Fix Checking — Tenant flows from session
FOR ALL X WHERE X.type = "csv_read" DO
  result ← read_csv'(X)
  ASSERT result.Administration = X.authenticated_tenant
END FOR

// Property: Preservation Checking — Existing correct behavior unchanged
FOR ALL X WHERE NOT isBugCondition_Bug1(X) DO
  ASSERT system(X) = system'(X)
END FOR
```

### Bug 2: Binary Ambiguity Flag

```pascal
FUNCTION isBugCondition_Bug2(X)
  INPUT: X of type VerbPatternAnalysis
  OUTPUT: boolean

  // Returns true when the pattern has conflicts but the majority exceeds 90%
  RETURN X.has_conflicting_accounts AND X.majority_ratio > 0.90
END FUNCTION
```

```pascal
// Property: Fix Checking — Majority patterns are kept
FOR ALL X WHERE isBugCondition_Bug2(X) DO
  result ← analyze_reference_patterns'(X)
  pattern ← result[X.company_key]
  ASSERT pattern._ambiguous = false
  ASSERT pattern.confidence = X.majority_count / X.total_count
  ASSERT pattern.debet_account = X.majority_debet
  ASSERT pattern.credit_account = X.majority_credit
END FOR
```

```pascal
// Property: Preservation Checking — Genuinely ambiguous patterns stay ambiguous
FOR ALL X WHERE X.has_conflicting_accounts AND X.majority_ratio <= 0.90 DO
  result ← analyze_reference_patterns'(X)
  pattern ← result[X.company_key]
  ASSERT pattern._ambiguous = true
END FOR
```

### Bug 3: Silent Pattern Dropping

```pascal
FUNCTION isBugCondition_Bug3(X)
  INPUT: X of type PatternStorageInput
  OUTPUT: boolean

  // Returns true when a pattern is ambiguous (would be skipped)
  RETURN X.pattern._ambiguous = true
END FUNCTION
```

```pascal
// Property: Fix Checking — Excluded patterns are logged
FOR ALL X WHERE isBugCondition_Bug3(X) DO
  result ← store_verb_patterns_to_database'(X)
  ASSERT log_output CONTAINS X.pattern_key
  ASSERT log_output CONTAINS X.occurrence_counts
  ASSERT log_output CONTAINS "ambiguous"
END FOR

// Property: Preservation Checking — Valid patterns still stored
FOR ALL X WHERE NOT isBugCondition_Bug3(X) DO
  ASSERT store_verb_patterns_to_database(X) = store_verb_patterns_to_database'(X)
END FOR
```

---

## Affected Files

| File                                                      | Line(s) | Issue                                                                        | Severity |
| --------------------------------------------------------- | ------- | ---------------------------------------------------------------------------- | -------- |
| `backend/src/banking_processor.py`                        | 73, 133 | Hardcoded `"GoodwinSolutions"` in `read_rabo_csv()` and `read_generic_csv()` | Critical |
| `backend/src/database.py`                                 | 454     | Default fallback `"GoodwinSolutions"` in `insert_transaction()`              | Critical |
| `backend/src/transaction_logic.py`                        | 224     | Fallback chain ending in `"GoodwinSolutions"`                                | Critical |
| `backend/src/services/banking_service.py`                 | 131     | Does not pass tenant to `process_csv_files()`                                | Critical |
| `backend/src/pattern_detection.py`                        | 666-671 | Binary ambiguity flag in `analyze_reference_patterns()`                      | Critical |
| `backend/src/pattern_storage.py`                          | 72      | Silent `continue` on ambiguous patterns                                      | Medium   |
| `backend/src/migrations/seed_goodwin_str_rates.py`        | 27-62   | Hardcoded tenant in seed data                                                | Medium   |
| `backend/src/routes/system_health_routes.py`              | 254     | Hardcoded tenant list for health checks                                      | Medium   |
| `backend/src/report_generators/aangifte_ib_generator.py`  | 19      | Hardcoded in docstring                                                       | Low      |
| `backend/src/report_generators/btw_aangifte_generator.py` | 18      | Hardcoded in docstring                                                       | Low      |
| `backend/src/tenant_admin_routes.py`                      | 106     | Hardcoded in docstring                                                       | Low      |
| `backend/src/google_drive_service.py`                     | 46      | Hardcoded in docstring                                                       | Low      |
| `backend/src/tenant_module_routes.py`                     | 97, 160 | Hardcoded in docstring                                                       | Low      |
| `backend/src/auth/tenant_context.py`                      | 56, 254 | Hardcoded in comment/docstring                                               | Low      |
| `backend/src/pattern_detection.py`                        | 568     | Hardcoded in docstring                                                       | Low      |
