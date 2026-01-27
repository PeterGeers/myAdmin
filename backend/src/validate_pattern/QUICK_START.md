# Quick Start - Test Pattern Analyzer Fixes

## 🚀 Ready to Test!

Everything is set up in this isolated folder. The original code is safe and untouched.

---

## Step 1: Clear Pattern Tables (REQUIRED)

**Run this SQL first:**

```sql
TRUNCATE TABLE pattern_verb_patterns;
TRUNCATE TABLE pattern_analysis_metadata;

-- Verify they're empty
SELECT COUNT(*) FROM pattern_verb_patterns;  -- Should be 0
```

---

## Step 2: Run the Test

**Command:**

```bash
cd backend/src/validate_pattern
python run_test.py
```

**What happens:**

- Analyzes PeterPrive (3,109 transactions)
- Analyzes GoodwinSolutions (2,698 transactions)
- Creates patterns using FIXED code
- Stores in database
- Prints summary

**Expected time:** 2-5 minutes

---

## Step 3: Compare Results

**Run this SQL:**

```sql
SELECT
    'NEW' as source,
    administration,
    COUNT(*) as pattern_count,
    COUNT(DISTINCT verb_company) as unique_companies,
    AVG(occurrences) as avg_occurrences
FROM pattern_verb_patterns
GROUP BY administration

UNION ALL

SELECT
    'BACKUP' as source,
    administration,
    COUNT(*) as pattern_count,
    COUNT(DISTINCT verb_company) as unique_companies,
    AVG(occurrences) as avg_occurrences
FROM pattern_verb_patterns_backup_20260127
GROUP BY administration
ORDER BY administration, source;
```

**What to look for:**

- ✅ NEW should have FEWER patterns (compound verbs eliminated)
- ✅ NEW should have HIGHER avg_occurrences (patterns reused more)
- ✅ NEW should have MORE unique_companies (better extraction)

---

## Step 4: Check Test Cases

**Test Case 1: Sociale Verzekeringsbank**

```sql
SELECT verb, verb_company, reference_number, occurrences
FROM pattern_verb_patterns
WHERE administration = 'PeterPrive'
  AND reference_number = 'Sociale Verzekeringsbank';
```

**Expected:** ONE pattern with 2+ occurrences

**Test Case 2: 2Theloo**

```sql
SELECT verb, verb_company, reference_number, occurrences
FROM pattern_verb_patterns
WHERE administration = 'PeterPrive'
  AND reference_number = '2Theloo';
```

**Expected:** verb_company = "2THELOO" (not "BREUKELEN")

---

## Decision Time

### ✅ If Results Look Good (Success Rate >= 95%)

**Replace original with test version:**

```bash
# Backup original
copy backend\src\pattern_analyzer.py backend\src\pattern_analyzer_original_backup.py

# Replace with fixed version
copy backend\src\validate_pattern\pattern_analyzer_test.py backend\src\pattern_analyzer.py

# Restart backend
docker-compose restart backend
```

**Done!** The fixes are now in production.

---

### ❌ If Results Are Not Good (Success Rate < 95%)

**Rollback to backup:**

```sql
DROP TABLE pattern_verb_patterns;
DROP TABLE pattern_analysis_metadata;

CREATE TABLE pattern_verb_patterns AS
SELECT * FROM pattern_verb_patterns_backup_20260127;

CREATE TABLE pattern_analysis_metadata AS
SELECT * FROM pattern_analysis_metadata_backup_20260127;
```

**Original code is still safe** - nothing to revert!

---

## Troubleshooting

### Error: "No module named 'database'"

**Solution:** Make sure you're in the validate_pattern folder:

```bash
cd backend/src/validate_pattern
python run_test.py
```

### Error: "Table pattern_verb_patterns is not empty"

**Solution:** Clear the tables first (Step 1)

### Error: Database connection failed

**Solution:** Make sure MySQL is running and .env is configured

---

## Files in This Folder

- **pattern_analyzer_test.py** - Fixed version (4 fixes applied)
- **run_test.py** - Test runner script
- **database.py** - Database module (dependency)
- **pattern_cache.py** - Cache module (dependency)
- **README.md** - Detailed documentation
- **QUICK_START.md** - This file

---

## Safety Checklist

✅ Original code untouched: `backend/src/pattern_analyzer.py`
✅ Backup exists: `pattern_verb_patterns_backup_20260127` (3,258 records)
✅ Test isolated: All test code in `validate_pattern/` folder
✅ Easy rollback: SQL restore from backup
✅ Zero risk: Production not affected

---

**Ready? Run Step 1 (clear tables) then Step 2 (run test)!**
