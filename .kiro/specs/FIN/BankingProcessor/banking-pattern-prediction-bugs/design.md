# Design: Banking Pattern Prediction Bugfixes

## Overview

Two code fixes to the banking pattern prediction pipeline:

1. Thread tenant through CSV readers and eliminate all hardcoded administration values
2. Replace binary ambiguity flag with majority-voting in pattern detection

The 4 miscoded Airbnb transactions in the closed year 2025 are a data issue, not a code issue. Once fix 2 is in place, they become irrelevant (4 out of 927 = 0.4%, well below the 10% minority threshold).

---

## Fix 1: Tenant Parameter Threading

### Root Cause

Multiple files hardcode `"GoodwinSolutions"` as the administration value. This is a leftover from the single-tenant era (Oct 2025) that was never cleaned up during the Jan 2026 multi-tenancy implementation.

### Approach

1. **CSV readers**: Add `administration` parameter — no fallback, must be explicitly provided
2. **Database insert**: Remove the default fallback, raise `ValueError` if missing
3. **Transaction logic**: Remove the fallback chain, raise if missing
4. **Seed script**: Parameterize the administration
5. **Health check**: Query tenants from database
6. **Docstrings**: Replace with `"ExampleTenant"`

### Changes

**`backend/src/banking_processor.py`** — CSV readers

```python
# Before
def read_rabo_csv(self, file_path):
    ...
    "Administration": "GoodwinSolutions",

# After
def read_rabo_csv(self, file_path, administration: str):
    ...
    "Administration": administration,
```

```python
# Before
def read_generic_csv(self, file_path):
    ...
    "Administration": "GoodwinSolutions",

# After
def read_generic_csv(self, file_path, administration: str):
    ...
    "Administration": administration,
```

```python
# Before
def process_csv_files(self, file_paths):
    ...
    df = self.read_rabo_csv(file_path)
    ...
    df = self.read_generic_csv(file_path)

# After
def process_csv_files(self, file_paths, administration: str):
    ...
    df = self.read_rabo_csv(file_path, administration)
    ...
    df = self.read_generic_csv(file_path, administration)
```

**`backend/src/services/banking_service.py`** — Pass tenant through

```python
# Before (process_banking_files)
df = processor.process_csv_files(file_paths)

# After
df = processor.process_csv_files(file_paths, tenant)
```

**`backend/src/database.py`** — No silent default

```python
# Before
transaction.get("Administration", "GoodwinSolutions"),

# After
administration = transaction.get("Administration") or transaction.get("administration")
if not administration:
    raise ValueError("Administration is required for tenant-scoped insert into mutaties")
```

**`backend/src/transaction_logic.py`** — No fallback chain

```python
# Before
"Administration": new_data.get(
    "administration", template.get("Administration", "GoodwinSolutions")
),

# After
administration = new_data.get("administration") or template.get("Administration")
if not administration:
    raise ValueError("Administration is required — neither new_data nor template provides it")
...
"Administration": administration,
```

**`backend/src/migrations/seed_goodwin_str_rates.py`** — Parameterize

```python
# Before
def run_seed(db=None):

# After
def run_seed(administration: str, db=None):
    # Replace hardcoded "GoodwinSolutions" in RATES with the parameter
```

**`backend/src/routes/system_health_routes.py`** — Query tenants dynamically

```python
# Before
tenants = ["GoodwinSolutions", "PeterPrive"]

# After
tenants_result = db.execute_query(
    "SELECT DISTINCT administration FROM rekeningschema WHERE administration IS NOT NULL"
)
tenants = [r["administration"] for r in tenants_result] if tenants_result else []
```

**Docstrings** — Replace all `"GoodwinSolutions"` examples with `"ExampleTenant"` in:

- `report_generators/aangifte_ib_generator.py`
- `report_generators/btw_aangifte_generator.py`
- `tenant_admin_routes.py`
- `google_drive_service.py`
- `tenant_module_routes.py`
- `auth/tenant_context.py`
- `pattern_detection.py`

### Safety

- The IBAN tenant validation (`validate_iban_tenant`) runs after CSV processing — it remains a secondary defense.
- `save_transactions()` in banking_service.py still forces `transaction["administration"] = tenant` at import time — this is a tertiary defense layer.
- The `ValueError` in `insert_transaction()` will surface any remaining code paths that fail to provide a tenant.

---

## Fix 2: Majority Voting in Pattern Detection

### Root Cause

In `analyze_reference_patterns()` (pattern_detection.py, lines 666-671), when a transaction for the same company-level verb has different accounts than the existing pattern, the code immediately sets `_ambiguous = True` and `confidence = 0.0`. This binary decision means 4 outliers out of 927 transactions kill the entire AIRBNB pattern.

### Approach

Replace the binary ambiguity flag with a **frequency tracker** that counts occurrences per account combination. After all transactions are processed, apply majority voting:

- If one combination has ≥90% of occurrences → store as the pattern with confidence = majority_ratio
- If no combination reaches 90% → mark as genuinely ambiguous (existing behavior preserved)

### Algorithm

```python
# Instead of storing a single pattern with _ambiguous flag,
# track all account combinations seen for this company key:

company_variants[company_key] = {
    (debet, credit): {
        "occurrences": count,
        "last_seen": date,
        "reference_number": ref_num,
        "sample_description": description,
    }
}

# After iteration, apply majority voting:
total = sum(v["occurrences"] for v in variants.values())
best = max(variants.items(), key=lambda x: x[1]["occurrences"])
best_accounts, best_data = best
majority_ratio = best_data["occurrences"] / total

if majority_ratio >= MAJORITY_THRESHOLD:  # 0.90
    # Store pattern with majority accounts
    pattern["debet_account"] = best_accounts[0]
    pattern["credit_account"] = best_accounts[1]
    pattern["confidence"] = majority_ratio
    pattern["_ambiguous"] = False
    pattern["_minority_count"] = total - best_data["occurrences"]
else:
    # Genuinely ambiguous — preserve existing behavior
    pattern["_ambiguous"] = True
    pattern["confidence"] = 0.0
```

### Configuration

```python
# Threshold constant at module level in pattern_detection.py
MAJORITY_VOTING_THRESHOLD = 0.90  # 90% agreement required
```

### Why 90%?

- The Airbnb case is 923/927 = 99.6% — well above any reasonable threshold
- Genuine multi-product vendors (like ASR with 5 different insurance products) would have ~20% per product — clearly below 90%
- 90% leaves room for occasional mis-codings while still requiring overwhelming agreement

### Regression Safety

- Compound verb patterns are unaffected — they each have their own key and never hit the company-level ambiguity check
- Patterns with 100% agreement continue to get confidence 1.0 (majority_ratio = 1.0)
- Patterns with genuine ambiguity (<90%) continue to get `_ambiguous = True`

---

## Note on the 4 Miscoded Transactions (Not a Code Fix)

4 Airbnb bank transactions imported in December 2025 (IDs: 61959, 61956, 61946, 61945) were recorded with `Credit=8003` instead of `Credit=1600`. The year 2025 is closed. With Fix 2 (majority voting) in place, these 4 records are irrelevant — they're 4 out of 927, well below the 10% threshold. The algorithm handles this automatically; no data correction or code is needed.

---

## Impact Analysis

| Component                   | Change Type                                               | Risk                                   |
| --------------------------- | --------------------------------------------------------- | -------------------------------------- |
| `banking_processor.py`      | Add parameter to 3 methods                                | Low — additive change, no logic change |
| `banking_service.py`        | Pass tenant to `process_csv_files`                        | Low — value already available          |
| `database.py`               | Remove default, raise ValueError                          | Medium — will surface hidden bugs      |
| `transaction_logic.py`      | Remove fallback, raise ValueError                         | Medium — same as above                 |
| `pattern_detection.py`      | Rewrite company-key logic in `analyze_reference_patterns` | Medium — core prediction logic         |
| `pattern_storage.py`        | Add logging for skipped patterns                          | Low — observability only               |
| `seed_goodwin_str_rates.py` | Parameterize administration                               | Low — migration script                 |
| `system_health_routes.py`   | Query tenants dynamically                                 | Low — read-only health check           |
| Docstrings (7 files)        | Replace examples                                          | None — documentation only              |

### Files Modified

**Critical (data flow):**

1. `backend/src/banking_processor.py` — lines 57-135 (CSV readers + process_csv_files)
2. `backend/src/services/banking_service.py` — line 131 (process_banking_files call)
3. `backend/src/database.py` — line 454 (insert_transaction fallback)
4. `backend/src/transaction_logic.py` — line 224 (invoice transaction creation)
5. `backend/src/pattern_detection.py` — lines 640-700 (analyze_reference_patterns)
6. `backend/src/pattern_storage.py` — line 72 (silent continue → logged exclusion)

**Operational:** 7. `backend/src/migrations/seed_goodwin_str_rates.py` — parameterize tenant 8. `backend/src/routes/system_health_routes.py` — dynamic tenant list

**Documentation (7 files):**
9-15. Replace `"GoodwinSolutions"` with `"ExampleTenant"` in docstrings

### Testing Strategy

- Unit tests for `read_rabo_csv` and `read_generic_csv` with explicit administration parameter
- Unit test: `insert_transaction` without Administration raises ValueError
- Unit test: `transaction_logic` without administration raises ValueError
- Unit test for majority voting: 90%+ agreement → stored, <90% → ambiguous
- Unit test for edge case: exactly 90% threshold boundary
- Unit test: ambiguous pattern exclusion produces log output
- Integration test: run pattern analysis for GoodwinSolutions and verify AIRBNB pattern is produced
- Regression test: verify Booking.com compound patterns still work unchanged
- Regression test: verify zero-conflict patterns still get confidence 1.0
