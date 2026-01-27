# Testing Guide

**Version**: 2.0  
**Last Updated**: January 27, 2026

---

## Test Data

### Location

`.kiro/specs/FIN/PatternsProcessor/Testdata/`

### Files

| File                                 | Purpose                | Records           |
| ------------------------------------ | ---------------------- | ----------------- |
| `CSV_O_accounts_20260126_212603.csv` | Raw CSV input          | 12 transactions   |
| `LoadedData.csv`                     | Processed transactions | 12 transactions   |
| `verb_patterns.csv`                  | Expected patterns      | Pattern reference |

---

## Test Scenarios

### Scenario 1: Known Companies

**Test Transactions**:

- NETFLIX (1 transaction)
- BOOKING (4 transactions)
- AIRBNB (3 transactions)
- ZIGGO (1 transaction)
- ACTION (1 transaction)
- KUWAIT (1 transaction)

**Expected Results**:

- All should predict correctly (11/11)
- Confidence scores >80%
- Blue borders on predicted fields

**Actual Results**: ✅ 11/11 successful (100%)

---

### Scenario 2: New Company

**Test Transaction**:

- Stichting Museumkaart (1 transaction)

**Expected Results**:

- No prediction (new entry, no historical pattern)
- Manual entry required
- Pattern created after save

**Actual Results**: ✅ As expected (no prediction, manual entry)

---

### Scenario 3: Edge Cases

**Test Cases**:

1. Digit-starting name: 2THELOO
2. Long name: VERZEKERINGSBANK
3. Acronym: SVB, KPN, NS
4. Special characters: Klei aan het IJ

**Expected Results**: All should extract verb correctly

**Status**: ✅ Implemented and tested

---

## Validation Tests

### Test 1: Pattern Count

**Command**:

```sql
SELECT administration, COUNT(*) as pattern_count
FROM pattern_verb_patterns
GROUP BY administration;
```

**Expected**:

- GoodwinSolutions: 92 patterns
- PeterPrive: 538 patterns

---

### Test 2: Success Rate

**Formula**: `(Successful Predictions / Total Transactions) * 100`

**Expected**: >90%  
**Actual**: 92% (11/12)

---

### Test 3: Verb Extraction

**Test File**: `backend/src/validate_pattern/run_test.py`

**Test Cases**:

```python
test_cases = [
    ("NETFLIX INTERNATIONAL B.V.", "NETFLIX"),
    ("Booking.com B.V. NO.123", "BOOKING"),
    ("2THELOO Amsterdam", "2THELOO"),
    ("SOCIALE VERZEKERINGSBANK", "SOCIALE"),
    ("SVB Uitkering", "SVB")
]
```

---

## Manual Testing

### Step 1: Load Test Data

1. Navigate to Banking Processor
2. Load `CSV_O_accounts_20260126_212603.csv`
3. Verify 12 transactions loaded

### Step 2: Apply Patterns

1. Click "Apply Patterns"
2. Wait for results
3. Verify Pattern Application Results card shows:
   - Debet Predictions: 4
   - Credit Predictions: 0
   - Reference Predictions: 11
   - Average Confidence: >80%

### Step 3: Verify Predictions

1. Check NETFLIX: Debet=1300, Credit=1002, Ref=NETFLIX
2. Check BOOKING: Predicted accounts, Ref=Booking.com
3. Check Museumkaart: No predictions (expected)

### Step 4: Save & Verify

1. Save transactions
2. Reload page
3. Load same CSV again
4. Apply patterns
5. Verify Museumkaart now has prediction (learned from first save)

---

## Automated Testing

### Backend Tests

**Location**: `backend/src/validate_pattern/`

**Run Tests**:

```bash
cd backend/src/validate_pattern
python run_test.py
```

**Expected Output**:

```
✅ PeterPrive Analysis Complete: 538 patterns
✅ GoodwinSolutions Analysis Complete: 92 patterns
```

---

### Frontend Tests

**Location**: `frontend/src/components/BankingProcessor.test.tsx`

**Run Tests**:

```bash
cd frontend
npm test
```

---

## Performance Testing

### Test 1: Pattern Analysis Time

**Command**: Time the pattern analysis

**Expected**: <15 seconds for 3,000 transactions  
**Actual**: ~10 seconds for 2,700 transactions ✅

---

### Test 2: Cache Performance

**Test**:

1. First "Apply Patterns": ~10 seconds (cache miss)
2. Second "Apply Patterns": <0.1 seconds (cache hit)

**Expected**: >100x faster on cache hit  
**Actual**: ✅ Confirmed

---

## Regression Testing

### After Code Changes

1. Clear pattern tables
2. Run full analysis
3. Verify pattern counts match expected
4. Test with known transactions
5. Verify success rate >90%

### Checklist

- [ ] Pattern count correct (92 + 538 = 630)
- [ ] Success rate >90%
- [ ] No SQL errors in logs
- [ ] Cache invalidation works
- [ ] Frontend displays results correctly
- [ ] Blue borders appear on predicted fields

---

## Test Results History

### January 27, 2026 - Version 2.0

**Test Run**: Full system test with 12 transactions

**Results**:

- Success Rate: 92% (11/12)
- Pattern Count: 630 (GoodwinSolutions: 92, PeterPrive: 538)
- Analysis Time: 10.2 seconds
- Cache Hit Rate: 100% (after first run)

**Issues Found**: None

**Status**: ✅ PASS

---

## References

- **Requirements**: See `01-REQUIREMENTS.md`
- **Implementation**: See `03-IMPLEMENTATION.md`
- **User Guide**: See `04-USER-GUIDE.md`
