Status: RESOLVED
# Duplicate Invoice Detection - Incident Report

## Issue Description

The duplicate invoice detection system is not properly preventing duplicate uploads. When a duplicate invoice is detected, the system logs the detection but continues processing the upload instead of stopping it.

## Current Behavior

1. User uploads an invoice that already exists
2. System detects duplicate: "Duplicate detected for Baderie Leen: 1 matches found"
3. System continues processing and saves the duplicate transaction
4. No warning is shown to the user

## Expected Behavior

1. User uploads an invoice
2. System checks for duplicates BEFORE processing
3. If duplicate found, system stops processing and shows warning
4. User can choose to continue or cancel

## Root Cause Analysis

1. **Duplicate detection runs but doesn't stop processing**: The `_check_for_duplicates` method in `pdf_processor.py` only adds duplicate info to transactions but doesn't prevent the upload
2. **Performance issue**: Multiple duplicate checks are running during processing
3. **Wrong reference data**: System uses `ReferenceNumber` instead of `TransactionNumber` for finding previous transactions

## Technical Issues Found

### 1. PDF Processor Issue

In `backend/src/pdf_processor.py` line 481-485:

```python
if duplicate_info and duplicate_info.get('has_duplicates', False):
    # Add duplicate information to transactions for frontend handling
    for transaction in transactions:
        transaction['duplicate_info'] = duplicate_info
    print(f"Duplicate detected for {reference_number}: {duplicate_info['duplicate_count']} matches found")
```

**Problem**: Only logs the duplicate but continues processing.

### 2. Upload Endpoint Issue

The upload endpoint in `app.py` doesn't check for duplicates before processing.

### 3. Reference Data Selection Issue

The system should use `TransactionNumber` (folder name) instead of `ReferenceNumber` for finding previous transactions.

## Proposed Solution

### Phase 1: Immediate Fix

1. **Add duplicate check in upload endpoint** before processing
2. **Return error response** when duplicates found
3. **Show duplicate warning dialog** to user

### Phase 2: Optimization

1. **Move duplicate check earlier** in the process
2. **Optimize database queries** for better performance
3. **Improve reference data selection** logic

## Implementation Plan

### Step 1: Fix Upload Endpoint

Add duplicate checking in the upload endpoint before file processing:

```python
# Check for duplicates before processing
if not flag:  # Only in production mode
    duplicate_info = check_for_duplicates_early(filename, folder_name)
    if duplicate_info['has_duplicates']:
        return jsonify({
            'success': False,
            'error': 'duplicate_detected',
            'duplicate_info': duplicate_info
        }), 409
```

### Step 2: Optimize Duplicate Detection

- Use `TransactionNumber` instead of `ReferenceNumber`
- Limit search to last 2-3 transactions per folder
- Check date and amount for better accuracy

### Step 3: Frontend Integration

- Show duplicate warning dialog
- Allow user to choose continue/cancel
- Display existing transaction details

## Files to Modify

1. `backend/src/app.py` - Upload endpoint
2. `backend/src/pdf_processor.py` - Remove duplicate processing
3. `backend/src/duplicate_checker.py` - Optimize queries
4. Frontend - Add duplicate warning dialog

## Testing Plan

1. Upload same invoice twice
2. Verify duplicate detection stops second upload
3. Test user choice to continue/cancel
4. Verify performance improvement

## Priority: HIGH

This affects data integrity and user experience.
