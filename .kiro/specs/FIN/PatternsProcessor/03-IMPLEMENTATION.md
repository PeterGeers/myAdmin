# Implementation Guide

**Version**: 2.0  
**Last Updated**: January 27, 2026

---

## Code Structure

### Backend Implementation

#### Core Files

| File                                    | Purpose                 | Key Functions                                                                                  |
| --------------------------------------- | ----------------------- | ---------------------------------------------------------------------------------------------- |
| `backend/src/pattern_analyzer.py`       | Pattern analysis engine | `analyze_historical_patterns()`, `apply_patterns_to_transactions()`, `_extract_company_name()` |
| `backend/src/app.py`                    | Flask API endpoints     | `banking_apply_patterns()`, `banking_save_transactions()`                                      |
| `backend/src/pattern_cache.py`          | Multi-level caching     | `get_patterns()`, `store_patterns()`, `invalidate_cache()`                                     |
| `backend/src/banking_processor.py`      | Transaction processing  | `apply_enhanced_patterns()`, `save_approved_transactions()`                                    |
| `backend/src/database.py`               | Database operations     | `execute_query()`, `get_bank_account_lookups()`                                                |
| `backend/src/pattern_storage_routes.py` | Pattern API routes      | Pattern analysis and storage endpoints                                                         |

---

### Frontend Implementation

#### Core Files

| File                                           | Purpose           | Key Components                                         |
| ---------------------------------------------- | ----------------- | ------------------------------------------------------ |
| `frontend/src/components/BankingProcessor.tsx` | Main UI component | Transaction form, pattern application, results display |

---

## Key Implementation Details

### 1. Verb Extraction

**File**: `backend/src/pattern_analyzer.py`  
**Method**: `_extract_company_name(description: str) -> Optional[str]`

**Implementation Highlights**:

- Line ~420: Known company patterns (BOOKING, AIRBNB, etc.)
- Line ~450: Banking noise word removal
- Line ~490: Word extraction with regex `r'\b[A-Z0-9][A-Z0-9]{2,}\b'`
- Line ~500: Length validation (3-25 characters)
- Line ~510: Acronym support (3-5 chars, no vowels required)
- Line ~520: Vowel validation for regular words

**Edge Cases**:

- Digit-starting names: Regex allows `[A-Z0-9]` at start
- Long names: 25-character limit (increased from 15)
- Acronyms: Special case for 3-5 uppercase letters
- Transaction codes: Filtered by pattern matching

---

### 2. Pattern Creation

**File**: `backend/src/pattern_analyzer.py`  
**Method**: `_analyze_reference_patterns(transactions: List[Dict], administration: str) -> Dict[str, Any]`

**Implementation Highlights**:

- Line ~340: Iterate through transactions
- Line ~360: Identify bank account (debet or credit)
- Line ~370: Extract verb from description
- Line ~380: Parse compound verb (company|reference)
- Line ~390: Create pattern key: `{administration}_{bank_account}_{verb_company}`
- Line ~400: Store pattern with metadata

**Pattern Key Structure**:

```python
pattern_key = f"{administration}_{bank_account}_{verb_company}"
# Example: "GoodwinSolutions_1002_NETFLIX"
```

**Pattern Data**:

```python
{
    'administration': 'GoodwinSolutions',
    'bank_account': '1002',
    'verb': 'NETFLIX',
    'verb_company': 'NETFLIX',
    'verb_reference': None,
    'is_compound': False,
    'reference_number': 'NETFLIX',
    'debet_account': '1300',
    'credit_account': '1002',
    'occurrences': 1,
    'confidence': 1.0,
    'last_seen': '2026-01-27',
    'sample_description': 'NETFLIX INTERNATIONAL B.V. Netflix Monthly Subscription'
}
```

---

### 3. Pattern Storage

**File**: `backend/src/pattern_analyzer.py`  
**Method**: `_store_verb_patterns_to_database(administration: str, verb_patterns: Dict, analysis_metadata: Dict, is_incremental: bool = False)`

**Implementation Highlights**:

- Line ~1050: UPSERT query with `INSERT ... ON DUPLICATE KEY UPDATE`
- Line ~1070: Occurrence accumulation: `occurrences = occurrences + VALUES(occurrences)`
- Line ~1080: Metadata update with transaction count

**UPSERT Logic**:

```sql
INSERT INTO pattern_verb_patterns (...)
VALUES (...)
ON DUPLICATE KEY UPDATE
    occurrences = occurrences + VALUES(occurrences),
    confidence = VALUES(confidence),
    last_seen = VALUES(last_seen),
    ...
```

**Benefits**:

- No data loss (existing patterns preserved)
- Atomic operation (no race conditions)
- Incremental updates (occurrence counts accumulate)

---

### 4. Pattern Matching

**File**: `backend/src/pattern_analyzer.py`  
**Methods**:

- `_predict_debet(transaction: Dict, debet_patterns: Dict, administration: str) -> Optional[Dict]`
- `_predict_credit(transaction: Dict, credit_patterns: Dict, administration: str) -> Optional[Dict]`
- `_predict_reference(transaction: Dict, reference_patterns: Dict) -> Optional[Dict]`

**Implementation Highlights**:

#### Debet Prediction (Line ~770)

```python
# 1. Check if credit is bank account
if not self.is_bank_account(credit, administration):
    return None

# 2. Extract verb from description
verb = self._extract_verb_from_description(description, ref_num)

# 3. Parse compound verb to get company only
verb_company = verb.split('|', 1)[0] if '|' in verb else verb

# 4. Build pattern key
pattern_key = f"{administration}_{credit}_{verb_company}"

# 5. Lookup in patterns
if pattern_key in reference_patterns:
    pattern = reference_patterns[pattern_key]
    return {
        'value': pattern.get('debet_account'),
        'confidence': pattern.get('confidence', 1.0),
        'pattern_key': pattern_key,
        'reason': f'Exact match: Verb "{verb}" with bank credit {credit}',
        'verb': verb
    }
```

#### Credit Prediction (Line ~850)

Similar logic but checks if debet is bank account.

#### Reference Prediction (Line ~920)

```python
# 1. Extract verb
verb = self._extract_verb_from_description(description, ref_num)

# 2. Identify bank account
bank_account = debet if is_bank_account(debet) else credit

# 3. Parse compound verb
verb_company = verb.split('|', 1)[0] if '|' in verb else verb

# 4. Build pattern key
pattern_key = f"{administration}_{bank_account}_{verb_company}"

# 5. Lookup and return
if pattern_key in reference_patterns:
    return {
        'value': pattern.get('reference_number'),
        'confidence': pattern.get('confidence', 1.0),
        ...
    }
```

---

### 5. Cache Management

**File**: `backend/src/pattern_cache.py`  
**Class**: `PatternCache`

**Implementation Highlights**:

- Line ~50: Multi-level cache (memory → database → file)
- Line ~100: Cache warming on startup
- Line ~150: Cache invalidation on data changes

**Cache Flow**:

```python
def get_patterns(self, administration):
    # Level 1: Memory cache
    if administration in self.memory_cache:
        return self.memory_cache[administration]

    # Level 2: Database cache
    patterns = self._load_from_database(administration)
    if patterns:
        self.memory_cache[administration] = patterns
        return patterns

    # Level 3: File cache
    patterns = self._load_from_file(administration)
    if patterns:
        self.memory_cache[administration] = patterns
        return patterns

    # Cache miss - trigger analysis
    return None
```

---

### 6. Frontend Integration

**File**: `frontend/src/components/BankingProcessor.tsx`  
**Function**: `applyPatterns()`

**Implementation Highlights**:

- Line ~910: API call to `/api/banking/apply-patterns`
- Line ~930: Extract results from `enhanced_results` object
- Line ~940: Update transaction state with predictions
- Line ~950: Display pattern results

**Data Mapping Fix** (Line ~927):

```typescript
// Extract results from enhanced_results or fallback to legacy format
const results = data.enhanced_results || data;

const patternData = {
  patterns_found: data.patterns_found || results.total_transactions || 0,
  predictions_made: results.predictions_made || {
    debet: 0,
    credit: 0,
    reference: 0,
  },
  confidence_scores: results.confidence_scores || [],
  average_confidence: results.average_confidence || 0,
  enhanced_results: data.enhanced_results,
};
```

---

## Configuration

### Minimum Occurrence Threshold

**File**: `backend/src/pattern_analyzer.py`  
**Lines**: 232, 296, 826, 903, 995

**Current Value**: 1 (learn from first occurrence)

**Change History**:

- Original: 2 (required 2+ occurrences)
- Updated: 1 (January 27, 2026)

**Rationale**: System should learn immediately from first manual entry, not wait for second occurrence.

---

### Word Length Limits

**File**: `backend/src/pattern_analyzer.py`  
**Line**: ~500

**Current Value**: 3-25 characters

**Change History**:

- Original: 3-15 characters
- Updated: 3-25 characters (January 27, 2026)

**Rationale**: Support long company names like "VERZEKERINGSBANK" (17 chars).

---

### Confidence Threshold

**File**: `backend/src/pattern_analyzer.py`  
**Lines**: ~835, ~910, ~1000

**Current Value**: 80% (0.8)

**Usage**: Minimum confidence required for pattern matching with multiple candidates.

---

## Database Queries

### Pattern Retrieval

**File**: `backend/src/pattern_analyzer.py`  
**Method**: `_load_patterns_from_database()`  
**Line**: ~1150

```sql
SELECT administration, bank_account, verb, verb_company, verb_reference,
       is_compound, reference_number, debet_account, credit_account,
       occurrences, confidence, last_seen, sample_description
FROM pattern_verb_patterns
WHERE administration = %s
ORDER BY last_seen DESC, occurrences DESC
```

---

### Transaction Query

**File**: `backend/src/pattern_analyzer.py`  
**Method**: `analyze_historical_patterns()`  
**Line**: ~95

```sql
SELECT TransactionDescription, Debet, Credit, ReferenceNumber,
       TransactionDate, TransactionAmount, Ref1, administration
FROM mutaties
WHERE administration = %s
  AND TransactionDate >= %s
  AND (Debet IS NOT NULL OR Credit IS NOT NULL)
ORDER BY TransactionDate DESC
```

---

### Pattern UPSERT

**File**: `backend/src/pattern_analyzer.py`  
**Method**: `_store_verb_patterns_to_database()`  
**Line**: ~1053

```sql
INSERT INTO pattern_verb_patterns
(administration, bank_account, verb, verb_company, verb_reference, is_compound,
 reference_number, debet_account, credit_account, occurrences, confidence,
 last_seen, sample_description)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
verb_company = VALUES(verb_company),
verb_reference = VALUES(verb_reference),
is_compound = VALUES(is_compound),
reference_number = VALUES(reference_number),
debet_account = VALUES(debet_account),
credit_account = VALUES(credit_account),
occurrences = occurrences + VALUES(occurrences),
confidence = VALUES(confidence),
last_seen = VALUES(last_seen),
sample_description = VALUES(sample_description),
updated_at = CURRENT_TIMESTAMP
```

---

## Testing

### Test Files

| File          | Purpose                | Location                                                                        |
| ------------- | ---------------------- | ------------------------------------------------------------------------------- |
| Test data CSV | Sample transactions    | `.kiro/specs/FIN/PatternsProcessor/Testdata/CSV_O_accounts_20260126_212603.csv` |
| Loaded data   | Processed transactions | `.kiro/specs/FIN/PatternsProcessor/Testdata/LoadedData.csv`                     |
| Pattern data  | Expected patterns      | `.kiro/specs/FIN/PatternsProcessor/Testdata/verb_patterns.csv`                  |

### Test Validation

**File**: `backend/src/validate_pattern/run_test.py`

**Test Cases**:

1. NETFLIX → Debet: 1300, Credit: 1002, Ref: NETFLIX
2. BOOKING → Predicted accounts, Ref: Booking.com
3. AIRBNB → Predicted accounts, Ref: AIRBNB
4. ZIGGO → Predicted accounts, Ref: ZIGGO
5. ACTION → Predicted accounts, Ref: ACTION
6. KUWAIT → Predicted accounts, Ref: Kuwait

**Success Criteria**: 11/12 transactions (92%)

---

## Deployment

### Docker Commands

```bash
# Restart backend
docker restart myadmin-backend-1

# View logs
docker logs myadmin-backend-1 --tail 100

# Clear cache
rm cache/*.json

# Database access
docker exec -i myadmin-mysql-1 mysql -uroot -p<password> finance
```

### Frontend Build

```bash
cd frontend
npm run build
```

Build output: `frontend/build/` (served by backend)

---

## Performance Optimization

### Database Indexes

```sql
-- Pattern lookup
CREATE INDEX idx_admin_bank_verb ON pattern_verb_patterns(administration, bank_account, verb);

-- Transaction query
CREATE INDEX idx_admin_date ON mutaties(administration, TransactionDate);

-- Duplicate check
CREATE INDEX idx_ref1_ref2 ON mutaties(Ref1, Ref2);
```

### Query Optimization

- Use parameterized queries (prevent SQL injection)
- Limit result sets (ORDER BY + LIMIT)
- Index foreign keys
- Connection pooling

### Caching Strategy

- Cache patterns in memory (fast access)
- Invalidate on data changes (consistency)
- Warm cache on startup (reduce latency)
- File cache for persistence (survive restarts)

---

## Error Handling

### Pattern Analysis Errors

**File**: `backend/src/pattern_analyzer.py`

```python
try:
    patterns = self.analyze_historical_patterns(administration)
except Exception as e:
    print(f"❌ Error analyzing patterns: {e}")
    return {
        'patterns_discovered': 0,
        'error': str(e)
    }
```

### Database Errors

**File**: `backend/src/database.py`

```python
try:
    result = cursor.execute(query, params)
except mysql.connector.Error as e:
    print(f"Database error: {e}")
    raise
```

### Frontend Errors

**File**: `frontend/src/components/BankingProcessor.tsx`

```typescript
try {
  const response = await authenticatedPost("/api/banking/apply-patterns", data);
  // ... handle response
} catch (error) {
  setMessage(`❌ Error applying patterns: ${error}`);
  setPatternResults(null);
}
```

---

## Logging

### Backend Logging

```python
# Pattern analysis
print(f"🔍 Analyzing historical patterns for {administration}...")
print(f"📊 Processing {len(transactions)} transactions from last 2 years...")
print(f"✅ Pattern analysis complete: {result['patterns_discovered']} patterns discovered")

# Pattern application
print(f"🔧 Applying patterns to {len(transactions)} transactions...")
print(f"✅ Pattern application complete: {sum(results['predictions_made'].values())} predictions made")

# Cache operations
print(f"[CACHE] Invalidated cache after saving {saved_count} transactions")
print(f"🔥 Warming up persistent pattern cache...")
print(f"✅ Cache warmed up in {time:.3f}s with {count} entries")
```

### Log Locations

- Backend: `docker logs myadmin-backend-1`
- Application: `backend/logs/app.log`
- Database: MySQL error log

---

## References

- **Requirements**: See `01-REQUIREMENTS.md`
- **Architecture**: See `02-ARCHITECTURE.md`
- **User Guide**: See `04-USER-GUIDE.md`
- **API Reference**: See `05-API-REFERENCE.md`
- **Testing**: See `06-TESTING.md`
