# Pattern Predictor — Root Cause Analysis

**Date**: 2026-08-12  
**Tenant tested**: goodwinsolutions  
**Test data**: CSV_O_accounts_20260811_163649.csv (19 transactions, Aug 3–11 2026)  
**Result**: 0/19 predictions made despite 642 stored patterns with high confidence

---

## Executive Summary

The pattern predictor produces zero predictions due to **case-sensitivity bugs** at two levels:

1. `is_bank_account()` — bank accounts stored as `GoodwinSolutions_1002`, looked up as `goodwinsolutions_1002`
2. Pattern key lookups in `predict_debet`/`predict_credit` — pattern keys stored as `GoodwinSolutions_1002_AIRBNB`, looked up as `goodwinsolutions_1002_AIRBNB`

The `pattern_verb_patterns` table IS loaded and used correctly when the cache L2 (database) layer serves data. The table is not deleted/recreated — it uses UPSERT. The 642 existing patterns are valid. The model works.

### Verified Fix Results

With case normalization applied (administration part lowercased in keys):

| Metric             | Before fix | After fix                  |
| ------------------ | ---------- | -------------------------- |
| Predictions        | 0/19 (0%)  | 10/19 (53%)                |
| Remaining failures | all        | 9 (verb extraction issues) |

The 9 remaining failures are due to verb extraction not recognizing certain description formats. With the counter-party name (`Naam tegenpartij`) properly included in descriptions (as the frontend does), prediction would reach **16–17/19 (84–89%)**.

---

## THE Root Cause: Case-Sensitivity at Two Levels

### Level 1: `is_bank_account()` Lookup

```python
# Bank accounts stored in rekeningschema with administration = 'GoodwinSolutions'
Bank accounts cache keys: ['GoodwinSolutions_1002', 'GoodwinSolutions_1011', 'GoodwinSolutions_1012', ...]

# But tenant context passes lowercase:
is_bank_account('1002', 'goodwinsolutions') = False   # Key: 'goodwinsolutions_1002' ≠ 'GoodwinSolutions_1002'
```

### Level 2: Pattern Key Lookup in `predict_debet` / `predict_credit`

```python
# Pattern keys loaded from DB as:
'GoodwinSolutions_1002_AIRBNB', 'GoodwinSolutions_1002_BOOKING', etc.

# But predict_credit builds lookup key as:
company_key = f"{administration}_{debet}_{verb_company}"
# = 'goodwinsolutions_1002_AIRBNB'  ← doesn't match 'GoodwinSolutions_1002_AIRBNB'
```

**Both levels must be fixed.** Fixing only Level 1 still produces 0 predictions.

### Impact

Every code path that uses `is_bank_account` OR pattern key lookups fails:

1. **Pattern discovery** (`analyze_reference_patterns`): `is_bank_account` fails → skips all 1425 transactions → 0 patterns
2. **Pattern prediction** (`predict_debet`/`predict_credit`): `is_bank_account` fails AND key lookup mismatches → 0 predictions
3. **Even when both are partially fixed**: normalizing only `is_bank_account` still yields 0 because pattern keys also mismatch

### The Code

```python
# pattern_analyzer.py line 81
def is_bank_account(self, account_number: str, administration: str) -> bool:
    if not account_number:
        return False
    bank_accounts = self.get_bank_accounts()
    key = f"{administration}_{account_number}"  # ← Case-sensitive!
    return key in bank_accounts

# get_bank_accounts builds keys from rekeningschema data:
key = f"{account['administration']}_{account['Account']}"
# Result: 'GoodwinSolutions_1002' (original casing from DB)
```

### The Fix

```python
# pattern_analyzer.py — get_bank_accounts():
key = f"{account['administration']}_{account['Account']}".lower()

# pattern_analyzer.py — is_bank_account():
key = f"{administration}_{account_number}".lower()

# pattern_storage.py — load_patterns_from_database():
pattern_key = f"{row['administration'].lower()}_{row['bank_account']}_{row['verb']}"

# pattern_cache.py — _load_from_database_cache():
pattern_key = f"{row['administration'].lower()}_{row['bank_account']}_{row['verb']}"
```

---

## Test Evidence (unchanged)

### What the database contains

| Verb      | Bank | Debet | Credit | Occurrences | Confidence |
| --------- | ---- | ----- | ------ | ----------- | ---------- |
| AIRBNB    | 1002 | 1002  | 1600   | 5569        | 1.00       |
| BOOKING   | 1002 | 1002  | 1600   | 5256        | 1.00       |
| BOL       | 1002 | 1300  | 1002   | 905         | 1.00       |
| PICNIC    | 1002 | 1300  | 1002   | 386         | 1.00       |
| KOSTEN    | 1002 | 4081  | 1002   | 190         | 1.00       |
| STRIPE    | 1002 | 1300  | 1002   | 213         | 1.00       |
| HOOFDDORP | 1002 | 1300  | 1002   | 41          | 1.00       |

All these verbs appear in the test CSV. All should predict. None do.

### What the predictor does

```
🔧 Applying patterns to 19 transactions...
🔍 Cache miss - analyzing patterns for goodwinsolutions
📊 Processing 1425 transactions from last 1 year...
💾 Storing 0 verb patterns to database...
✅ Pattern analysis complete: 0 patterns discovered
✅ Pattern application complete: 0 predictions made
```

### After fix (verified)

```
✓  1  -45.99   Rabobank                   KOSTEN     → Debet: 4081  (conf 1.00)
✗  2  +509.02  Booking.com BV             None       → no verb extracted from NO.xxx/ID.xxx
✗  3  +171.47  Booking.com BV             None       → no verb extracted from NO.xxx/ID.xxx
✓  4  +392.16  AIRBNB PAYMENTS            AIRBNB     → Credit: 1600 (conf 1.00)
✗  5  -6.80    Google Cloud EMEA Limited  APPS       → wrong verb (should be GOOGLE)
✓  6  -53.78   PICNIC BY BUCKAROO         PICNIC     → Debet: 1300  (conf 1.00)
✓  7  +126.44  AIRBNB PAYMENTS            AIRBNB     → Credit: 1600 (conf 1.00)
✓  8  -7.11    Action 1169                HOOFDDORP  → Debet: 1300  (conf 1.00)
✗  9  -1.50    Q-Park via Mollie          PARK       → no matching pattern stored
✓ 10  +178.71  AIRBNB PAYMENTS            AIRBNB     → Credit: 1600 (conf 1.00)
✗ 11  +237.89  Booking.com BV             None       → no verb extracted from NO.xxx/ID.xxx
✓ 12  +783.42  AIRBNB PAYMENTS            AIRBNB     → Credit: 1600 (conf 1.00)
✗ 13  +424.88  Stripe Technology          STRIPE     → verb OK, but incoming ≠ historical outgoing
✓ 14  -41.94   Action 1169                HOOFDDORP  → Debet: 1300  (conf 1.00)
✗ 15  -298.43  Kuwait Petroleum           None       → no verb extracted from /INV/NLN...
✗ 16  +154.82  Booking.com BV             None       → no verb extracted from NO.xxx/ID.xxx
✓ 17  +390.47  AIRBNB PAYMENTS            AIRBNB     → Credit: 1600 (conf 1.00)
✗ 18  +585.90  Booking.com BV             None       → no verb extracted from NO.xxx/ID.xxx
✓ 19  -17.09   bol.com                    BOL        → Debet: 1300  (conf 1.00)

Result: 10/19 (53%) — all at 1.00 confidence, all correct assignments
```

### Remaining 9 Failures (All Recurring Transactions)

| #            | Counter Party     | Verb Extracted | Issue                                                    | Stored Pattern                                                     |
| ------------ | ----------------- | -------------- | -------------------------------------------------------- | ------------------------------------------------------------------ |
| 2,3,11,16,18 | Booking.com BV    | None           | `NO.xxx/ID.xxx` format has no company word               | BOOKING (5256 occ), BOOKING\|4392906 (113), BOOKING\|5620035 (242) |
| 5            | Google Cloud EMEA | APPS           | Extracted from "APPS COMMERCE:" instead of counter-party | GOOGLE (464 occ)                                                   |
| 9            | Q-Park via Mollie | PARK           | No PARK pattern stored                                   | MOLLIE exists (556 occ)                                            |
| 13           | Stripe Technology | STRIPE         | Pattern is outgoing (D=1300,C=1002), this is incoming    | STRIPE (213 occ, outgoing only)                                    |
| 15           | Kuwait Petroleum  | None           | `/INV/NLN0774455` has no company word                    | KUWAIT (761 occ)                                                   |

**Key insight**: 7 of 9 failures would be fixed if `Naam tegenpartij` is included in the verb extraction input. The frontend already does this — these are all high-frequency recurring transactions with excellent stored patterns.

---

## Root Causes

### 1. PRIMARY: Case-Sensitive `is_bank_account()` — Kills Everything

See section above. This is the single point of failure. With this bug, no patterns can be discovered and no predictions can be made, regardless of data quality.

### 2. Re-analysis Stores 0 Patterns to Metadata (But Doesn't Delete Pattern Rows)

**Location**: `pattern_storage.py` → `store_verb_patterns_to_database()`

When analysis discovers 0 patterns (due to the case bug), it stores `patterns_discovered = 0` in `pattern_analysis_metadata`. The actual 642 pattern rows in `pattern_verb_patterns` are NOT deleted (UPSERT with 0 rows = no change). The cache L2 layer still loads the 642 rows when the 24h freshness check passes.

**Correction from initial analysis**: The pattern table data IS used. The cache L2 (`_load_from_database_cache`) loads from `pattern_verb_patterns` when metadata is fresh. But even with patterns loaded, `predict_debet`/`predict_credit` also call `is_bank_account` — so they'd still fail.

### 3. Verb Extraction Fails on Booking.com Descriptions

**Location**: `pattern_detection.py` → `extract_company_name()`

The CSV contains 6 Booking.com transactions with descriptions like:

```
NO.6YjDoIrjTQfUMQIs/ID.4392906
NO.xmQOsrh8isiQ33jU/ID.5620035
NO.C6Hi4btcxwFnPtdy/ID.5620035
```

The verb extractor cannot extract "BOOKING" from these — it only matches when the counter-party name (`Booking.com BV`) is part of the description text. The stored patterns show historical descriptions included the counter-party name: `"Booking.com B.V. cb NO.h60DKGaEsssvNFah/"`.

**Impact**: 6/19 transactions (32%) fail at verb extraction alone.

### 4. Description Assembly Differs Between Frontend and Backend

**Frontend** (`BankingProcessor.utils.ts` → `processRabobankTransaction`):

- Builds description from: `Naam tegenpartij` + `Code` + `Omschrijving-1` + `Omschrijving-2`
- Result: `"Booking.com BV cb NO.6YjDoIrjTQfUMQIs/ID.4392906"`
- Verb extraction: **BOOKING** ✓

**Backend** (`banking_processor.py` → `read_rabo_csv`):

- Uses only column indices (col[8] + col[19]) which map to: `Tegenrekening IBAN/BBAN` + `Omschrijving-1`
- Misses the counter-party name entirely

**Impact**: When the backend processes files directly (not via frontend), it produces unrecognizable descriptions.

### 5. Prediction Logic Requires Bank Account Already Set

**Location**: `pattern_scoring.py` → `predict_debet()` / `predict_credit()`

The predictor only works when one side is already populated:

- `predict_debet`: requires `Credit` to be a known bank account
- `predict_credit`: requires `Debet` to be a known bank account

```python
# REQ-PAT-004: Only predict debet when credit is a bank account
if not is_bank_account_fn(credit, administration):
    return None
```

This means the banking processor must first assign the bank account side (e.g., `Debet=1002` for incoming). If that initial assignment fails or uses an IBAN instead of account number, all prediction stops.

---

## Architecture Flow (Corrected Understanding)

```
CSV Upload
    │
    ▼
Frontend parses CSV
    │ Sets Debet/Credit = account number (e.g., 1002)
    │ Builds description from Naam tegenpartij + Code + Omschrijving
    ▼
POST /api/banking/apply-patterns
    │
    ▼
get_filtered_patterns(administration='goodwinsolutions')
    │
    ├─ Cache L1 (memory)? → MISS (cold/expired)
    ├─ Cache L2 (database)?
    │       │ Checks pattern_analysis_metadata.last_analysis_date < 24h?
    │       │   YES → Loads 642 rows from pattern_verb_patterns → returns patterns
    │       │   NO  → returns None (stale)
    ├─ Cache L3 (file)? → Permission denied on server
    │
    └─ ALL MISS → analyze_historical_patterns('goodwinsolutions')
                       │
                       ├─ Query mutaties (1425 rows, last 12 months)
                       ├─ For each tx: is_bank_account(debet, 'goodwinsolutions')
                       │                 → builds key 'goodwinsolutions_1002'
                       │                 → looks up in cache: 'GoodwinSolutions_1002'
                       │                 → CASE MISMATCH → False
                       ├─ ALL transactions skipped → 0 patterns
                       ▼
                  store_verb_patterns_to_database(0 patterns)
                  → UPSERT does nothing (no rows to insert)
                  → metadata.patterns_discovered = 0
                       │
                       ▼
                  Returns {'reference_patterns': {}} → 0 predictions

EVEN IF CACHE L2 LOADS 642 PATTERNS:
    predict_debet(tx, patterns, 'goodwinsolutions', is_bank_account, ...)
        → is_bank_account(credit='1002', 'goodwinsolutions') → False
        → return None (no prediction)
```

**The case bug blocks BOTH the discovery path AND the prediction path.**

---

## Why It Degraded Over Time

The case sensitivity bug was likely introduced when the tenant naming was changed or when the `get_bank_account_lookups` query started returning the `administration` column from `rekeningschema` (which uses `GoodwinSolutions`) instead of the tenant context value (which uses `goodwinsolutions`). Once this happened:

1. **Pattern discovery stopped producing new patterns** — every re-analysis returns 0
2. **Existing 642 patterns still served from cache L2** — so predictions worked intermittently (when cache was warm/fresh)
3. **After 24h or cache invalidation** — predictions stop until next manual "Analyze Patterns" that populated the cache
4. **The prediction path itself also uses `is_bank_account`** — so even cached patterns can't produce predictions

This explains the gradual degradation: predictions worked when the cache was warm (second button click within 24h) but failed on first click after cache expiry.

---

## Verdict: Is the Model Viable?

**Yes.** The model and data are sound. With case normalization applied:

- 10/19 transactions predict correctly at 1.00 confidence (53%)
- With `Naam tegenpartij` in descriptions (as the frontend provides): ~16/19 (84%)
- All predictions were correct — no false positives
- Only legitimate edge cases remain (direction mismatch for Stripe, no pattern for Q-Park)

The `pattern_verb_patterns` table contains 642 valid, high-confidence patterns built from thousands of historical transactions. The pattern key structure (`Administration + BankAccount + Verb`) is the right abstraction. The table is correctly loaded and used via the cache L2 layer.

---

## Recommended Fix Strategy

### Fix 1: Case-insensitive key matching (CRITICAL — restores predictions)

Normalize the administration part of all keys to lowercase. Four locations:

**`backend/src/pattern_analyzer.py`** — `get_bank_accounts()` + `is_bank_account()`:

```python
key = f"{account['administration']}_{account['Account']}".lower()   # get_bank_accounts
key = f"{administration}_{account_number}".lower()                   # is_bank_account
```

**`backend/src/pattern_storage.py`** — `load_patterns_from_database()`:

```python
pattern_key = f"{row['administration'].lower()}_{row['bank_account']}_{row['verb']}"
```

**`backend/src/pattern_cache.py`** — `_load_from_database_cache()`:

```python
pattern_key = f"{row['administration'].lower()}_{row['bank_account']}_{row['verb']}"
```

### Fix 2 (recommended): Guard against overwriting with 0 patterns

**`backend/src/pattern_analyzer.py`** in `analyze_historical_patterns()`:

```python
if not reference_number and not debet_account and not credit_account:
    if len(reference_patterns_result) > 0:  # ← GUARD
        store_verb_patterns_to_database(...)
        self.persistent_cache.invalidate_cache(administration)
```

### Fix 3 (recommended): Expand verb extraction for recurring transaction formats

**`backend/src/pattern_detection.py`** → `extract_company_name()`:

```python
# Add to company_patterns list:
(r"\bNO\.[A-Za-z0-9]+/ID\.\d+", "BOOKING"),     # Booking.com reference format
(r"\bAPPS\s+COMMERCE:", "GOOGLE"),                 # Google Cloud billing format
(r"/INV/NLN\d+", "KUWAIT"),                        # Kuwait Petroleum invoice format
(r"\bQ-?PARK\b", "QPARK"),                         # Q-Park parking
```

---

## Files Involved

| File                                                | Role                                        | Fix needed                                                     |
| --------------------------------------------------- | ------------------------------------------- | -------------------------------------------------------------- |
| `backend/src/pattern_analyzer.py`                   | `is_bank_account()` + `get_bank_accounts()` | `.lower()` on key building                                     |
| `backend/src/pattern_storage.py`                    | `load_patterns_from_database()`             | `.lower()` on admin part of pattern key                        |
| `backend/src/pattern_cache.py`                      | `_load_from_database_cache()`               | `.lower()` on admin part when building keys                    |
| `backend/src/pattern_detection.py`                  | `extract_company_name()`                    | Add known description patterns (Booking, Google, Kuwait)       |
| `backend/src/pattern_scoring.py`                    | `predict_debet()` / `predict_credit()`      | No change needed (admin already lowercase from tenant context) |
| `frontend/src/components/BankingProcessor.utils.ts` | CSV parser                                  | No change needed — already includes Naam tegenpartij correctly |
