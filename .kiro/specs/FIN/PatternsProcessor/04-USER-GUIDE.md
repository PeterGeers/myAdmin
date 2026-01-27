# User Guide

**Version**: 2.0  
**Last Updated**: January 27, 2026

---

## Getting Started

### Step 1: Load CSV File

1. Click "Select CSV Files" button
2. Choose one or more CSV files from your downloads folder
3. Files are parsed and displayed in the transaction table

### Step 2: Apply Patterns

1. Click "Apply Patterns" button
2. System analyzes transaction descriptions
3. Predictions appear with blue borders
4. Review the Pattern Application Results card

### Step 3: Review & Edit

1. Check auto-filled fields (blue borders)
2. Manually edit any incorrect predictions
3. Fill in fields that couldn't be predicted
4. Verify all required fields are complete

### Step 4: Save Transactions

1. Click "Save to Database" button
2. System filters duplicates automatically
3. Confirmation message shows saved count
4. Patterns automatically update for next use

---

## Understanding Pattern Results

### Pattern Application Results Card

**Patterns Found**: Number of historical patterns available  
**Debet Predictions**: Count of Debet accounts predicted  
**Credit Predictions**: Count of Credit accounts predicted  
**Reference Predictions**: Count of ReferenceNumbers predicted  
**Average Confidence**: Overall confidence score (0-100%)

### Field Indicators

**Blue Border**: Field was auto-filled by pattern matching  
**No Border**: Field requires manual entry  
**Confidence Score**: Hidden metadata (used internally)

---

## Pattern Learning

### How Patterns Are Created

1. You manually enter transaction data
2. Save transactions to database
3. Next time you click "Apply Patterns"
4. System analyzes ALL transactions (last 2 years)
5. Creates/updates patterns automatically

### What Makes a Good Pattern

- Complete transaction (ReferenceNumber + Accounts)
- Clear company/vendor name in description
- One side is a bank account
- Consistent naming across transactions

---

## Troubleshooting

### No Predictions Shown

**Cause**: No historical patterns exist  
**Solution**: Manually enter first transaction, save, then patterns will work for future

### Wrong Predictions

**Cause**: Similar company names or outdated patterns  
**Solution**: Manually correct and save - system learns from corrections

### Low Confidence Scores

**Cause**: Pattern only seen once or conflicting patterns  
**Solution**: More occurrences increase confidence over time

### Slow Performance

**Cause**: First use after saving transactions (cache miss)  
**Solution**: Normal - subsequent uses are fast (cached)

---

## Best Practices

### Data Entry

- Use consistent naming for companies
- Fill in ReferenceNumber when possible
- Verify bank account numbers
- Save regularly to update patterns

### Pattern Management

- Review predictions before saving
- Correct errors to improve learning
- Don't skip manual review
- Save complete batches together

### Performance

- Process similar transactions together
- Save after each CSV file
- Clear cache if patterns seem stale
- Monitor success rate over time

---

## FAQ

**Q: When do patterns update?**  
A: Automatically on next "Apply Patterns" click after saving transactions.

**Q: Can I delete bad patterns?**  
A: Not through UI currently. Contact admin for database cleanup.

**Q: Why did prediction change?**  
A: Patterns update with new data. More recent transactions have higher weight.

**Q: How many transactions needed for pattern?**  
A: Just 1! System learns from first occurrence.

**Q: What if company name changes?**  
A: System treats as new pattern. Manually link if needed.

---

## Keyboard Shortcuts

- **Tab**: Move to next field
- **Shift+Tab**: Move to previous field
- **Enter**: Submit form (save)
- **Esc**: Cancel/close dialogs

---

## References

- **Requirements**: See `01-REQUIREMENTS.md`
- **Architecture**: See `02-ARCHITECTURE.md`
- **Implementation**: See `03-IMPLEMENTATION.md`
- **API Reference**: See `05-API-REFERENCE.md`
- **Testing**: See `06-TESTING.md`
