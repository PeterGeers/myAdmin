# PDF Invoice Parser Template

Use this template to create new PDF invoice parsers for the myAdmin system.
(using pdf_processor and vendor_parser)

## Invoice Information
**Type**: pdf
**Folder**: [VENDOR_NAME]
**File**: [SAMPLE_FILENAME.pdf]

## Extraction Requirements

### Date Line
**Pattern**: [DESCRIBE_HOW_DATE_APPEARS]
**Example**: `date_line: VAT Invoice Date: November 1, 2025`
**Target Format**: YYYY-MM-DD

### Amount Line
**Pattern**: [DESCRIBE_HOW_TOTAL_AMOUNT_APPEARS]
**Example**: `Amount_line: TOTAL AMOUNT EUR 20.13`
**Target**: Extract numeric value (e.g., 20.13)

### VAT Line (if applicable)
**Pattern**: [DESCRIBE_HOW_VAT_APPEARS]
**Example**: `Vat_line: TOTAL VAT EUR 3.49`
**Target**: Extract numeric value (e.g., 3.49) or set to 0.0 if no VAT

### Description Components
List all text elements needed for the description:
**Component 1**: [FIELD_NAME]
- **Pattern**: [HOW_TO_FIND_IT]
- **Example**: `* Account number: 344561557829`

**Component 2**: [FIELD_NAME]
- **Pattern**: [HOW_TO_FIND_IT]
- **Example**: `* VAT Invoice Number: EUINNL25-643000`

**Component 3**: [FIELD_NAME]
- **Pattern**: [HOW_TO_FIND_IT]
- **Example**: `* billing period October 1 - October 31, 2025`

### Final Description Format
**Result**: [SHOW_EXPECTED_CONCATENATED_RESULT]
**Example**: `Account: 344561557829 Invoice: EUINNL25-643000 billing period October 1 - October 31, 2025`

## PDF Text Sample
See PDF Retrieved.md or
Provide the first 20-30 lines of extracted PDF text:
```
[PASTE_EXTRACTED_TEXT_HERE]
```

## Special Notes
- Line-specific extraction (e.g., "amount is 3 lines after 'Total'")
- Case sensitivity requirements
- Multiple occurrences handling
- Any vendor-specific parsing rules

## Implementation Checklist
- [ ] Add folder check in `pdf_processor.py` 
- [ ] Create `parse_[vendor]` method in `vendor_parsers.py`
- [ ] Test date extraction
- [ ] Test amount extraction  
- [ ] Test description building
- [ ] Verify Ref1/Ref2 are NULL
- [ ] Test with actual PDF file