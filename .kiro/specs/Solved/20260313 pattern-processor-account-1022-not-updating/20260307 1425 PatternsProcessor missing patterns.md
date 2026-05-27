# Bug Report: PatternsProcessor Missing Patterns for Account 1022

**Date**: 2026-03-07 14:25  
**Status**: ✅ RESOLVED  
**Fixed**: 2026-03-07

## Problem Description

The pattern processor does not resolve "Hoogvliet" and "TMC" for general ledger account 1022 (Revolut). These verbs have existed in the data for over a year but are not loaded in the `pattern_verb_patterns` table. They are only visible/loaded for account 1003.

## Root Cause Analysis

**Bug Location**: `backend/src/pattern_analyzer.py` - `_extract_company_name()` method (line ~496)

**Root Cause**: The transaction ID filter was incorrectly identifying "HOOGVLIET" as a transaction ID and filtering it out.

The problematic regex pattern was:

```python
if (re.match(r'^[A-Z0-9]{8,}$', word) or  # Long alphanumeric codes
```

This pattern matches ANY string of 8+ uppercase letters or digits, including pure alphabetic company names like "HOOGVLIET" (9 characters, all uppercase).

## Diagnostic Evidence

Running `backend/scripts/analysis/diagnose_pattern_issue.py` showed:

1. **109 Hoogvliet/TMC transactions exist** for account 1022 dating back to March 2025
2. **Verb extraction failed** for "Hoogvliet": returned `None` instead of `'HOOGVLIET'`
3. **Verb extraction worked** for "TMC": correctly returned `'TMC'` (3 chars, treated as acronym)
4. **No patterns in database** for "HOOGVLIET" on account 1022 (but 228 other patterns exist)
5. **Pattern exists for TMC** on account 1003 (155 occurrences)

## Solution

Modified the transaction ID filter to only skip strings that contain BOTH letters AND numbers (actual transaction IDs), not pure alphabetic company names:

```python
# FIX: Only skip alphanumeric codes that contain BOTH letters AND numbers
# Pure alphabetic words (like "HOOGVLIET") should NOT be filtered
has_letters = bool(re.search(r'[A-Z]', word))
has_digits = bool(re.search(r'\d', word))

if ((has_letters and has_digits and len(word) >= 8) or  # Long mixed alphanumeric codes
    re.match(r'^[A-Z]{2}\d+[A-Z]+\d+$', word) or  # Mixed letter-number patterns
    # ... other patterns
```

## Verification

After the fix:

- ✅ `'Hoogvliet' → 'HOOGVLIET'` (extraction now works)
- ✅ `'TMC' → 'TMC'` (still works)
- ✅ `'Albert Heijn' → 'ALBERT'` (still works)
- ✅ `'Cupido Gebakskramen' → 'CUPIDO'` (still works)

## Next Steps

To populate the missing patterns in the database:

1. **Option A - Automatic**: Next time you use the Banking Processor and click "Apply Patterns", the system will re-analyze historical transactions and create the missing patterns automatically.

2. **Option B - Manual**: Run pattern analysis via API:

   ```bash
   POST /api/patterns/analyze/PeterPrive
   ```

3. **Option C - Script**: Run the pattern analysis directly:
   ```python
   from pattern_analyzer import PatternAnalyzer
   analyzer = PatternAnalyzer(test_mode=False)
   result = analyzer.analyze_historical_patterns('PeterPrive', {})
   ```

Once patterns are regenerated, "Hoogvliet" transactions will be automatically recognized and assigned the correct accounts (Debet: 4001, Credit: 1022, Reference: "Hoogvliet").

## Related Files

- **Fix**: `backend/src/pattern_analyzer.py` (line ~496-510)
- **Diagnostic Script**: `backend/scripts/analysis/diagnose_pattern_issue.py`
- **Test Script**: `backend/scripts/analysis/test_hoogvliet_extraction.py`
- **Test Data**: `.kiro/specs/FIN/PatternsProcessor/Testdata/account-statement_2026-01-01_2026-01-26_nl-nl_2f0361.csv`
- **Spec**: `.kiro/specs/FIN/PatternsProcessor/`

## Impact

- **Affected**: All company names with 8+ characters that are pure alphabetic (no numbers)
- **Examples**: HOOGVLIET, GEBAKSKRAMEN, VERZEKERINGSBANK, etc.
- **Not Affected**: Short names (< 8 chars), names with numbers, acronyms (3-5 chars)

## Prevention

Added comment in code explaining the logic to prevent future regressions:

```python
# FIX: Only skip alphanumeric codes that contain BOTH letters AND numbers
# Pure alphabetic words (like "HOOGVLIET") should NOT be filtered
```
