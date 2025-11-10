# PDF Invoice Parser Template
Use this template to create new PDF invoice parsers for the myAdmin system.
(using pdf_processor and vendor_parser)

## Invoice Information
**Type**: pdf
**Folder**: [VENDOR_NAME]
**File**: [SAMPLE_FILENAME.pdf]

## Extraction Requirements

### Date
**Pattern**: [VAT Invoice Date: November 1, 2025]
**Example**: `date_line: VAT Invoice Date: November 1, 2025`
**Target Format**: YYYY-MM-DD

### Amount
**Pattern**: [DESCRIBE_HOW_TOTAL_AMOUNT_APPEARS]
**Example**: `TOTAL AMOUNT EUR 20.13`
**Target**: Extract numeric value (e.g., 20.13)

### VAT (if applicable)
**Pattern**: [TOTAL VAT EUR]
**Example**: `TOTAL VAT EUR 3.49`
**Target**: Extract numeric value (e.g., 3.49) or set to 0.0 if no VAT

### Description
List all text elements needed for the description:
**Component 1**: [FIELD_NAME]
- **Pattern**: [HOW_TO_FIND_IT]
- **Example**: `* Account number: 344561557829`

**Component 2**: [FIELD_NAME]
- **Pattern**: [HOW_TO_FIND_IT]
- **Example**: `* VAT Invoice Number: EUINNL25-643000`


### Final Description
**Result**: [SHOW_EXPECTED_CONCATENATED_RESULT]
**Example**: `Account: 344561557829 Invoice: EUINNL25-643000 billing period October 1 - October 31, 2025`

## PDF Text Sample
See PDF Retrieved.md

## Special Notes
- Line-specific extraction (e.g., "amount is 3 lines after 'Total'")
- Case sensitivity requirements
- Multiple occurrences handling
- Any vendor-specific parsing rules