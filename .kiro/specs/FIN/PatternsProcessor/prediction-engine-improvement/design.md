# Technical Design — Prediction Engine Improvement (Phase 1)

## Overview

Phase 1 adds a **Reference Lookup** step between the existing `predict_reference()` and `predict_debet()`/`predict_credit()` calls. The current architecture remains intact — we insert a new prediction path that uses the predicted reference code as a key to find the counter-account, falling back to the existing verb-matching when reference lookup fails.

The key insight: the relationship between reference code and counter-account is more stable than the relationship between verb (extracted company name) and counter-account. By predicting the reference code first, then using it as a lookup key, we get better counter-account predictions.

## Architecture

```
                        ┌──────────────────────────────────────────────┐
                        │          pattern_analyzer.py                  │
                        │   apply_patterns_to_transactions() loop       │
                        └──────────────────────┬───────────────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
            ┌───────▼────────┐        ┌───────▼────────┐        ┌───────▼────────┐
            │predict_reference│        │ reference_lookup│        │predict_debet/  │
            │ (existing)      │──OK──▶ │ (NEW)           │──NONE─▶│predict_credit  │
            │ pattern_scoring │        │ pattern_scoring │        │ (existing)     │
            └────────────────┘        └────────────────┘        └────────────────┘
                                               │
                                        has result (any confidence)
                                               │
                                    ┌──────────┴──────────┐
                                    │                     │
                              conf ≥ 0.80           conf < 0.80
                                    │                     │
                              blue indicator       orange indicator
                              (confident)          (uncertain)
```

### Module Responsibilities

| Module                 | Phase 1 Changes                                                                     |
| ---------------------- | ----------------------------------------------------------------------------------- |
| `pattern_scoring.py`   | New functions `build_reference_account_index()`, `predict_account_from_reference()` |
| `pattern_analyzer.py`  | Modified `apply_patterns_to_transactions()` orchestration loop                      |
| `pattern_detection.py` | No changes                                                                          |
| `pattern_storage.py`   | No changes                                                                          |
| `pattern_cache.py`     | No changes                                                                          |

---

## Components and Interfaces

### 2.1 Sequential Prediction Flow (per transaction)

```
Transaction arrives (bank ledger account known on one side based on sign of amount, counter-account and ReferenceNumber empty)
    │
    ├─ ReferenceNumber already populated?
    │     YES → use existing ReferenceNumber as lookup key (skip step 1)
    │     NO  → Step 1
    │
    ▼
Step 1: predict_reference() [EXISTING — unchanged]
    │
    ├─ Result confidence < 0.80?
    │     YES → skip reference_lookup, go to Step 3
    │     NO  → set predicted_reference, go to Step 2
    │
    ▼
Step 2: predict_account_from_reference() [NEW]
    │   Key: administration + bank_account + reference_code
    │   Returns: counter-account + confidence
    │
    ├─ Combined confidence (ref_conf × lookup_conf) < 0.80?
    │     YES → go to Step 3
    │     NO  → use result as counter-account prediction, DONE
    │
    ▼
Step 3: predict_debet() / predict_credit() [EXISTING — unchanged]
    │   Verb-based fallback
    │
    └─ Result or None
```

### 2.2 Pattern Analysis Flow (periodic)

```
analyze_historical_patterns() called
    │
    ├─ analyze_reference_patterns() [existing — builds verb patterns]
    │     Output includes reference_number per pattern → already stored
    │
    └─ store_verb_patterns_to_database() [existing — no change needed]
          Pattern rows already contain reference_number field
          Reference lookup queries this same data by reference_number instead of verb
```

No separate analysis or storage step needed. The existing `analyze_reference_patterns()` already discovers and stores the relationship between verbs, reference codes, and accounts. Reference Lookup simply queries the same data differently — by `reference_number` instead of by `verb`.

---

## Data Models

### No New Table Required

The existing `pattern_verb_patterns` table already contains all the data needed for reference-to-account lookups:

```
pattern_verb_patterns:
- administration (PK)
- bank_account (PK)      ← the known ledger account for the bank account
- verb (PK)              ← the verb-based lookup key
- reference_number       ← the associated reference code
- debet_account          ← one side of the booking
- credit_account         ← other side of the booking
- occurrences
- confidence
- last_seen
```

For verb-matching, the lookup is: `administration + bank_account + verb` → pattern row.

For reference-lookup, the lookup is: `administration + bank_account + reference_number` → pattern row(s).

Same data, different query path. The direction (whether we need debet or credit) is always known at query time because one side is the bank account.

### Query for Reference Lookup

```sql
SELECT debet_account, credit_account, occurrences, confidence, last_seen
FROM pattern_verb_patterns
WHERE administration = %s
  AND bank_account = %s
  AND reference_number = %s
  AND confidence > 0
ORDER BY occurrences DESC
```

If the bank account is on the Credit side → we need the Debet from the result.
If the bank account is on the Debet side → we need the Credit from the result.

### Handling Multiple Results

Multiple patterns can share the same `reference_number` (e.g., different verbs that all have reference "KPN"). The prediction function aggregates:

- Group results by the target counter-account
- Sum occurrences per counter-account
- Confidence = most frequent counter-account occurrences / total occurrences
- Apply the same majority ratio logic as verb-matching

### Index Consideration

The existing primary key is `(administration, bank_account, verb)`. Lookups by `reference_number` would benefit from an index:

```sql
-- Optional: add index for reference_number lookups
CREATE INDEX idx_ref_lookup
ON pattern_verb_patterns (administration, bank_account, reference_number);
```

This is a non-breaking additive change to the existing table.

## 4. API Changes

### 4.1 No Frontend-Facing API Changes

The existing prediction metadata fields remain identical:

```python
# Transaction response — unchanged structure
{
    "Debet": "4600",
    "Credit": "1300",
    "ReferenceNumber": "KPN",
    "_debet_confidence": 0.956,
    "_credit_confidence": null,
    "_reference_confidence": 0.99,
    "_prediction_method": "reference_lookup"  # NEW field (additive, no breaking change)
}
```

### 4.2 New Metadata Fields

| Field                | Type          | Values                                          | Purpose                                                        |
| -------------------- | ------------- | ----------------------------------------------- | -------------------------------------------------------------- |
| `_prediction_method` | `str \| None` | `"reference_lookup"`, `"verb_matching"`, `None` | Indicates which method produced the counter-account prediction |
| `_uncertain`         | `bool`        | `true`, `false`                                 | When true, frontend shows orange indicator instead of blue     |

The `_uncertain` flag is set when combined confidence is below 0.80. The frontend uses this to show a different color border:

- `_uncertain = false` (or absent): blue border (confident prediction)
- `_uncertain = true`: orange border (uncertain prediction, user should verify)

### 4.3 Internal API: Pattern Analysis Endpoint

No changes to the analysis endpoint — the reference-account index is derived from existing verb patterns at prediction time, not during analysis.

---

## 5. Prerequisite: Pattern Data Hygiene

Before Phase 1 can rely on the existing `pattern_verb_patterns` data, two bugs in `store_verb_patterns_to_database()` must be fixed:

### 5.1 Fix: Replace Occurrences Instead of Accumulating

**File:** `pattern_storage.py`

**Current (buggy):**

```sql
ON DUPLICATE KEY UPDATE
occurrences = occurrences + VALUES(occurrences),
```

**Fixed:**

```sql
ON DUPLICATE KEY UPDATE
occurrences = VALUES(occurrences),
```

During full analysis, the occurrences are calculated from the full 1-year window. Accumulating them on top of the existing value doubles the count every time a full analysis runs.

For incremental analysis, the existing accumulation behavior is correct (adding new occurrences to existing total).

### 5.2 Fix: Delete Stale Patterns After Full Analysis

**File:** `pattern_storage.py` — add after the UPSERT loop in `store_verb_patterns_to_database()`:

```python
# Only during full analysis: remove patterns not seen within the analysis window
if not is_incremental:
    analysis_start = analysis_metadata.get("date_range", {}).get("from")
    if analysis_start:
        result = db.execute_query(
            """
            DELETE FROM pattern_verb_patterns
            WHERE administration = %s
              AND last_seen < %s
            """,
            (administration, analysis_start),
            fetch=False,
            commit=True,
        )
        deleted_count = result if isinstance(result, int) else 0
        if deleted_count:
            print(f"🧹 Removed {deleted_count} stale patterns (last_seen < {analysis_start})")
```

This ensures the table only contains patterns backed by recent transactions, making confidence scores and the reference-account index reliable.

---

## 6. Key Functions

### 6.1 New Function: `build_reference_account_index()`

**File:** `pattern_scoring.py`

Since the data already exists in `pattern_verb_patterns`, we just need to build a lookup index keyed by reference_number instead of verb. This is done at pattern-load time, not during analysis.

```python
def build_reference_account_index(
    reference_patterns: dict[str, dict],
) -> dict[str, dict]:
    """
    Build a reference-code-keyed index from existing verb patterns.

    The existing patterns are keyed by verb. This function re-indexes them
    by reference_number so that predict_account_from_reference() can do
    O(1) lookups by reference code.

    Args:
        reference_patterns: The existing verb patterns dict from get_filtered_patterns()

    Returns:
        Dict keyed by "{admin}_{bank_account}_{reference_number}" with value:
        {
            "counter_account": str,
            "occurrences": int,
            "confidence": float,
            "last_seen": date,
            "source_verb": str,
        }
        When multiple verb patterns share the same reference_number,
        the one with the highest occurrences wins.
    """
    ref_index = {}

    for _key, pattern in reference_patterns.items():
        ref_num = pattern.get("reference_number", "").strip()
        if not ref_num:
            continue
        if pattern.get("_ambiguous"):
            continue
        if pattern.get("confidence", 0) <= 0:
            continue

        admin = pattern.get("administration", "")
        bank_account = pattern.get("bank_account", "")

        # Derive counter-account from stored debet/credit + known bank account
        debet = pattern.get("debet_account", "")
        credit = pattern.get("credit_account", "")
        if bank_account == debet:
            other_account = credit
        elif bank_account == credit:
            other_account = debet
        else:
            continue

        if not other_account:
            continue

        index_key = f"{admin}_{bank_account}_{ref_num}"

        # Keep the pattern with highest occurrences for this reference code
        existing = ref_index.get(index_key)
        if existing and existing["occurrences"] >= pattern.get("occurrences", 0):
            continue

        ref_index[index_key] = {
            "counter_account": other_account,
            "occurrences": pattern.get("occurrences", 1),
            "confidence": pattern.get("confidence", 0.0),
            "last_seen": pattern.get("last_seen"),
            "source_verb": pattern.get("verb", ""),
        }

    return ref_index
```

---

### 6.2 New Function: `predict_account_from_reference()`

**File:** `pattern_scoring.py`

```python
CONFIDENCE_THRESHOLD_CONFIDENT = 0.80  # Blue indicator
# Below 0.80 = orange indicator (uncertain but still shown)

def predict_account_from_reference(
    reference_code: str,
    reference_confidence: float,
    bank_account: str,
    administration: str,
    reference_account_index: dict[str, dict],
) -> dict | None:
    """
    Predict counter-account using a reference code as lookup key.

    Multiplies reference_confidence × lookup_confidence for combined score.
    Always returns a result if a match exists — caller uses confidence
    to determine UI indicator (blue ≥ 0.80, orange < 0.80).

    Args:
        reference_code: The (predicted or existing) reference code
        reference_confidence: Confidence of the reference code itself (1.0 if user-supplied)
        bank_account: The identified bank account for this transaction
        administration: Tenant scope
        reference_account_index: Output from build_reference_account_index()

    Returns:
        Dict with prediction result, or None if no match found
    """
    if not reference_code or not reference_code.strip():
        return None

    # Build lookup key
    lookup_key = f"{administration}_{bank_account}_{reference_code}"

    pattern = reference_account_index.get(lookup_key)
    if not pattern:
        return None

    lookup_confidence = pattern["confidence"]

    # Combined confidence: reference prediction confidence × lookup confidence
    combined_confidence = reference_confidence * lookup_confidence

    return {
        "value": pattern["counter_account"],
        "confidence": combined_confidence,
        "lookup_confidence": lookup_confidence,
        "reference_code": reference_code,
        "method": "reference_lookup",
        "uncertain": combined_confidence < CONFIDENCE_THRESHOLD_CONFIDENT,
        "reason": (
            f'Reference lookup: "{reference_code}" → {pattern["counter_account"]} '
            f'(confidence {lookup_confidence:.1%}, via verb "{pattern["source_verb"]}")'
        ),
    }
```

---

### 6.3 Modified Function: `apply_patterns_to_transactions()`

**File:** `pattern_analyzer.py`

The orchestration loop changes from parallel predictions to a sequential pipeline:

```python
def apply_patterns_to_transactions(
    self, transactions: list[dict], administration: str
) -> tuple[list[dict], dict[str, Any]]:
    """Apply discovered patterns to predict missing values in transactions"""
    print(f"🔧 Applying patterns to {len(transactions)} transactions...")

    # Get patterns for this administration (multi-level cache)
    patterns = self.get_filtered_patterns(administration)

    # Build reference-account index from existing verb patterns (no extra DB query)
    reference_account_index = build_reference_account_index(patterns["reference_patterns"])

    results = {
        "total_transactions": len(transactions),
        "predictions_made": {"debet": 0, "credit": 0, "reference": 0},
        "prediction_methods": {"reference_lookup": 0, "verb_matching": 0},
        "confidence_scores": [],
        "failed_predictions": 0,
    }

    updated_transactions = []

    for tx in transactions:
        updated_tx = tx.copy()
        tx_predictions = []

        # ─── Step 1: Predict Reference (existing, unchanged) ───
        ref_confidence = 1.0  # Default: user-supplied reference
        if not updated_tx.get("ReferenceNumber"):
            ref_prediction = predict_reference(
                updated_tx,
                patterns["reference_patterns"],
                self.is_bank_account,
                self._extract_verb_from_description,
            )
            if ref_prediction:
                updated_tx["ReferenceNumber"] = ref_prediction["value"]
                updated_tx["_reference_confidence"] = ref_prediction["confidence"]
                ref_confidence = ref_prediction["confidence"]
                results["predictions_made"]["reference"] += 1
                tx_predictions.append(ref_prediction["confidence"])

        # ─── Step 2: Reference Lookup for counter-account (NEW) ───
        account_predicted_via_ref = False

        if updated_tx.get("ReferenceNumber") and ref_confidence >= 0.80:
            # Identify bank account for this transaction
            bank_account = None
            if self.is_bank_account(updated_tx.get("Debet", ""), administration):
                bank_account = updated_tx["Debet"]
            elif self.is_bank_account(updated_tx.get("Credit", ""), administration):
                bank_account = updated_tx["Credit"]

            if bank_account:
                ref_lookup_result = predict_account_from_reference(
                    reference_code=updated_tx["ReferenceNumber"],
                    reference_confidence=ref_confidence,
                    bank_account=bank_account,
                    administration=administration,
                    reference_account_index=reference_account_index,
                )

                if ref_lookup_result:
                    # Determine which field to set (debet or credit)
                    if bank_account == updated_tx.get("Credit", ""):
                        # Bank is credit → predict debet
                        if not updated_tx.get("Debet"):
                            updated_tx["Debet"] = ref_lookup_result["value"]
                            updated_tx["_debet_confidence"] = ref_lookup_result["confidence"]
                            updated_tx["_prediction_method"] = "reference_lookup"
                            updated_tx["_uncertain"] = ref_lookup_result["uncertain"]
                            results["predictions_made"]["debet"] += 1
                            results["prediction_methods"]["reference_lookup"] += 1
                            tx_predictions.append(ref_lookup_result["confidence"])
                            account_predicted_via_ref = True
                    elif bank_account == updated_tx.get("Debet", ""):
                        # Bank is debet → predict credit
                        if not updated_tx.get("Credit"):
                            updated_tx["Credit"] = ref_lookup_result["value"]
                            updated_tx["_credit_confidence"] = ref_lookup_result["confidence"]
                            updated_tx["_prediction_method"] = "reference_lookup"
                            updated_tx["_uncertain"] = ref_lookup_result["uncertain"]
                            results["predictions_made"]["credit"] += 1
                            results["prediction_methods"]["reference_lookup"] += 1
                            tx_predictions.append(ref_lookup_result["confidence"])
                            account_predicted_via_ref = True

        # ─── Step 3: Verb-matching fallback (existing, unchanged) ───
        if not account_predicted_via_ref:
            # Apply debet patterns (existing logic)
            if not updated_tx.get("Debet"):
                debet_prediction = predict_debet(
                    updated_tx,
                    patterns["reference_patterns"],
                    administration,
                    self.is_bank_account,
                    self._extract_verb_from_description,
                    self.get_filtered_patterns,
                )
                if debet_prediction:
                    updated_tx["Debet"] = debet_prediction["value"]
                    updated_tx["_debet_confidence"] = debet_prediction["confidence"]
                    updated_tx["_prediction_method"] = "verb_matching"
                    results["predictions_made"]["debet"] += 1
                    results["prediction_methods"]["verb_matching"] += 1
                    tx_predictions.append(debet_prediction["confidence"])

            # Apply credit patterns (existing logic)
            if not updated_tx.get("Credit"):
                credit_prediction = predict_credit(
                    updated_tx,
                    patterns["reference_patterns"],
                    administration,
                    self.is_bank_account,
                    self._extract_verb_from_description,
                    self.get_filtered_patterns,
                )
                if credit_prediction:
                    updated_tx["Credit"] = credit_prediction["value"]
                    updated_tx["_credit_confidence"] = credit_prediction["confidence"]
                    updated_tx["_prediction_method"] = "verb_matching"
                    results["predictions_made"]["credit"] += 1
                    results["prediction_methods"]["verb_matching"] += 1
                    tx_predictions.append(credit_prediction["confidence"])

        # Track confidence scores
        if tx_predictions:
            results["confidence_scores"].extend(tx_predictions)
        else:
            results["failed_predictions"] += 1

        updated_transactions.append(updated_tx)

    # Calculate average confidence
    if results["confidence_scores"]:
        results["average_confidence"] = sum(results["confidence_scores"]) / len(
            results["confidence_scores"]
        )
    else:
        results["average_confidence"] = 0.0

    print(
        f"✅ Pattern application complete: {sum(results['predictions_made'].values())} predictions made "
        f"(ref_lookup: {results['prediction_methods']['reference_lookup']}, "
        f"verb: {results['prediction_methods']['verb_matching']})"
    )
    return updated_transactions, results
```

---

### 6.4 Modified: `apply_patterns_to_transactions()` — build index at start

**File:** `pattern_analyzer.py` — at the top of the method, after loading patterns:

```python
# Build reference-account index from existing verb patterns (no extra DB query)
reference_account_index = build_reference_account_index(patterns["reference_patterns"])
```

This replaces the previous `self.get_reference_account_patterns(administration)` call. The index is built in-memory from data already loaded — zero additional database queries.

---

## 7. Cache Integration

### No Additional Caching Required

The reference-account index is built from `patterns["reference_patterns"]` which is already cached by the existing multi-level cache. When verb patterns are loaded from cache, the reference-account index is built on the fly (O(n) over patterns, ~0.1ms for 500 patterns).

No separate cache entry, no new cache methods, no changes to invalidation logic.

```
get_filtered_patterns() → loads verb patterns from cache (existing)
    │
    └── build_reference_account_index() → re-indexes by reference_number (in-memory, instant)
```

Cache invalidation on transaction save automatically invalidates verb patterns, which means the reference-account index will be rebuilt from fresh data on the next apply-patterns call.

---

## 8. Performance Considerations

### 8.1 Prediction Latency Impact

| Operation                  | Current | After Phase 1 | Notes                                                   |
| -------------------------- | ------- | ------------- | ------------------------------------------------------- |
| Per-transaction prediction | ~0.1ms  | ~0.15ms       | +1 dict lookup (reference_account_index)                |
| Pattern load (cache hit)   | ~1ms    | ~1.1ms        | +build_reference_account_index() from loaded patterns   |
| Pattern load (cache miss)  | ~50ms   | ~50ms         | No additional DB query — index built from existing data |
| Full pattern analysis      | ~2s     | ~2s           | No change — no separate analysis step                   |

### 8.2 Memory Impact

- Reference-account index is a subset of verb patterns (re-keyed by reference_number)
- Expected: 50–200 entries per administration (fewer unique ref codes than verbs)
- Memory overhead per administration: ~10KB additional (pointers into existing pattern data)

### 8.3 Database Impact

- No new table
- One optional index addition on `reference_number` column (non-breaking)
- No additional queries during prediction (index built in-memory from cached patterns)
- No impact on transaction save path

### 8.4 Optimization Strategy

1. **No additional analysis**: Reference-account index is built from already-loaded verb patterns — zero database overhead
2. **In-memory lookup**: Reference-account index is a dict — O(1) lookup per transaction
3. **Early exit**: If no reference_code was predicted, skip reference lookup entirely
4. **Confidence carried forward**: The confidence from verb-matching is multiplied into the reference lookup result

### 8.5 Threshold Constants

```python
# pattern_scoring.py — single location for all confidence thresholds
PREDICTION_CONFIDENCE_THRESHOLD = 0.80  # Minimum combined confidence to use a prediction
MIN_EVIDENCE_CAP = 0.50                 # Cap for reference codes with < 2 occurrences
```

Both `predict_account_from_reference()` and the existing verb-matching predictions use `PREDICTION_CONFIDENCE_THRESHOLD` — satisfying Requirement 7.6 (single confidence calculation location).

---

## 9. Compound Verb Handling

For reference codes containing a pipe character (e.g., `"ASR|Zorgverzekering"`):

```
predict_account_from_reference("ASR|Zorgverzekering", ...)
    │
    └─ lookup key: "{admin}_{bank_account}_ASR|Zorgverzekering"
        │
        ├─ Found? → use result (full compound match)
        │
        └─ Not found? → return None (NO company-only fallback)
                         → caller proceeds to verb-matching fallback
```

The lookup uses the full compound string as-is. No splitting on `|` — this ensures multi-product vendors (ASR with 5 insurance products) resolve to the correct counter-account per product. If the full compound key has no match, we do NOT try company-only; instead we fall through to the existing verb-matching which already handles compound/company fallback.

---

## Error Handling

| Failure Mode                                          | Behavior                                                                                  |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| No verb patterns loaded (empty cache)                 | `build_reference_account_index()` returns `{}`, prediction falls through to verb-matching |
| Reference lookup returns None                         | Transparent fallback to verb-matching                                                     |
| `build_reference_account_index()` encounters bad data | Skips malformed entries, returns partial index                                            |

---

## Correctness Properties

### Property 1: Non-regression

For any transaction where Reference_Lookup produces no result, the prediction output SHALL be identical to the output of the system before Phase 1 (verb-matching produces the same result).

**Validates: Requirements 3.1, 3.2, 3.4**

### Property 2: Confidence monotonicity

Combined confidence (ref_confidence × lookup_confidence) is always ≤ min(ref_confidence, lookup_confidence) — the system never artificially inflates confidence by combining two uncertain signals.

**Validates: Requirements 4.1, 4.3**

### Property 3: Determinism

Given the same pattern data and transaction, the prediction output is always identical regardless of cache state (cache only affects latency, not results).

**Validates: Requirements 5.3, 5.4**

### Property 4: Tenant isolation

A pattern stored for Administration A is never returned for a lookup in Administration B.

**Validates: Requirements 1.1, 5.5**

### Property 5: Idempotency

Running a full pattern analysis twice on the same data produces identical pattern table contents (UPSERT with replace semantics, stale cleanup is deterministic).

**Validates: Requirements 0.1, 5.2**

---

## Testing Strategy

### Unit Tests

| Function                                  | Test Cases                                                                                                                                                                                         |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `store_verb_patterns_to_database()` (fix) | Full analysis replaces occurrences (not accumulates); stale patterns deleted after full analysis; incremental still accumulates; log output on stale cleanup                                       |
| `build_reference_account_index()`         | Single ref→single account; multiple verbs with same ref (highest occurrences wins); ambiguous patterns skipped; empty ref skipped; bank account derivation correct                                 |
| `predict_account_from_reference()`        | Exact match returns result with confidence; no match returns None; combined confidence multiplication; compound reference lookup; empty reference returns None; uncertain flag set when below 0.80 |

### Integration Tests

1. **Full sequential flow**: Load CSV → apply patterns → verify reference predicted first, then used for counter-account lookup
2. **Fallback behavior**: Transaction where reference_lookup fails → verify verb-matching produces same result as before
3. **Pattern hygiene**: Run full analysis → verify stale patterns removed, occurrences not doubled

### Regression Test

Run existing pattern matching test suite — all tests must pass without modification (verb-matching unchanged).

---

## 11. Implementation Order

1. **`pattern_storage.py`** — Fix occurrence accumulation bug (replace `occurrences = occurrences + VALUES(occurrences)` with `occurrences = VALUES(occurrences)` for full analysis)
2. **`pattern_storage.py`** — Add stale pattern cleanup after full analysis (DELETE WHERE last_seen < analysis window start)
3. **`pattern_scoring.py`** — Add `build_reference_account_index()` + `predict_account_from_reference()` + shared threshold constant
4. **`pattern_analyzer.py`** — Modify `apply_patterns_to_transactions()` to use sequential flow (build index, try reference lookup, fall back to verb-matching)
5. **Database (optional)** — Add index on `pattern_verb_patterns.reference_number` for future direct-query use
6. **Tests** — Unit tests for new functions, integration test for full sequential flow, regression test for existing verb-matching
