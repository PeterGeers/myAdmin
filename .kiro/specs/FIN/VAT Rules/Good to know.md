# VAT (BTW) Rules - Good to Know

**Last Updated**: February 18, 2026

---

## Overview

myAdmin's VAT (BTW - Belasting Toegevoegde Waarde) processing is **hardcoded in business logic**, not database-driven. There is no `vat_rules` table in the database.

---

## Implementation Location

**Primary Module**: `backend/src/btw_processor.py`

**Related Files**:
- `backend/src/report_generators/btw_aangifte_generator.py` - Report generation
- `backend/src/routes/tax_routes.py` - API endpoints
- `backend/templates/html/btw_aangifte_template.html` - Report template

---

## VAT Account Structure

### Balance Accounts (Cumulative)

These accounts track cumulative VAT balances:

| Account | Name | Purpose |
|---------|------|---------|
| **2010** | BTW te betalen | VAT payable (output VAT collected) |
| **2020** | BTW te vorderen | VAT receivable (input VAT paid) |
| **2021** | BTW vooruitbetaald | VAT prepaid (advance payments) |

### Revenue Accounts (Quarterly)

These accounts track quarterly revenue for VAT calculation:

| Account | Name | Purpose |
|---------|------|---------|
| **8001** | Omzet hoog tarief | Revenue at high rate (21%) |
| **8002** | Omzet laag tarief | Revenue at low rate (9%) |
| **8003** | Omzet nul tarief | Revenue at zero rate (0%) |

---

## VAT Calculation Logic

### Quarter End Date Calculation

```python
quarter_month = int(quarter) * 3
if quarter_month == 3:
    quarter_end_date = f"{year}-03-31"
elif quarter_month == 6:
    quarter_end_date = f"{year}-06-30"
elif quarter_month == 9:
    quarter_end_date = f"{year}-09-30"
elif quarter_month == 12:
    quarter_end_date = f"{year}-12-31"
```

### Balance Data Query

Uses `mutaties_cache` for performance:

```python
# Filter by date (cumulative up to quarter end)
df_filtered = df[df['TransactionDate'] <= end_date]

# Filter by administration
df_filtered = df_filtered[df_filtered['administration'].str.startswith(administration)]

# Filter by BTW accounts (2010, 2020, 2021)
df_filtered = df_filtered[df_filtered['Reknum'].isin(['2010', '2020', '2021'])]

# Sum amounts by account
grouped = df_filtered.groupby(['Reknum', 'AccountName']).agg({'Amount': 'sum'})
```

### Quarter Data Query

```python
# Filter by year and quarter (not cumulative)
df_filtered = df[(df['jaar'] == int(year)) & (df['kwartaal'] == int(quarter))]

# Filter by BTW accounts (2010, 2020, 2021) + revenue accounts (8001, 8002, 8003)
df_filtered = df_filtered[df_filtered['Reknum'].isin(['2010', '2020', '2021', '8001', '8002', '8003'])]
```

---

## VAT Rates (Hardcoded)

### Current Dutch VAT Rates

| Rate Type | Percentage | Account | Description |
|-----------|-----------|---------|-------------|
| **High Rate** | 21% | 8001 | Standard rate for most goods/services |
| **Low Rate** | 9% | 8002 | Reduced rate (food, books, hotels, etc.) |
| **Zero Rate** | 0% | 8003 | Exempt or zero-rated (exports, etc.) |

**Note**: These rates are **not configurable** in the database. Changes require code updates.

---

## Report Generation

### BTW Aangifte Report

**Template**: `backend/templates/html/btw_aangifte_template.html`

**Field Mappings**:
- `administration` - Tenant name
- `year` - Report year
- `quarter` - Quarter number (1-4)
- `end_date` - Quarter end date
- `balance_rows` - Balance account data (2010, 2020, 2021)
- `quarter_rows` - Quarter-specific data (all BTW + revenue accounts)
- `payment_instruction` - "te betalen" or "te ontvangen"
- `received_btw` - Total VAT received (account 2010)
- `prepaid_btw` - Total VAT prepaid (account 2021)

### Calculation Flow

1. **Get Balance Data**: Cumulative balances for accounts 2010, 2020, 2021 up to quarter end
2. **Get Quarter Data**: Quarter-specific transactions for BTW + revenue accounts
3. **Calculate Amounts**: Determine VAT payable/receivable
4. **Generate Report**: Populate HTML template with calculated values
5. **Prepare Transaction**: Create transaction record for saving

---

## API Endpoints

**Base Path**: `/api/btw/`

### Generate Report

```
POST /api/btw/generate-report
Body: {
  "administration": "tenant_name",
  "year": 2025,
  "quarter": 1
}
```

### Save Transaction

```
POST /api/btw/save-transaction
Body: {
  "administration": "tenant_name",
  "transaction": { ... }
}
```

### Upload Report

```
POST /api/btw/upload-report
Body: {
  "administration": "tenant_name",
  "html_content": "<html>...</html>",
  "filename": "btw_2025_Q1.html"
}
```

---

## Internationalization Notes

### Why VAT Rules Are Not Translated

1. **Hardcoded Logic**: VAT calculations are in Python code, not database
2. **No VAT Rules Table**: No database table to translate
3. **Account Numbers**: Account numbers (2010, 2020, etc.) are technical identifiers
4. **Account Names**: Account names are tenant-specific business data
5. **Report Templates**: Tenant admins create their own templates in preferred language

### What IS Translated

- **UI Labels**: Frontend labels for VAT reports (in `reports.json`)
- **Error Messages**: API error messages (in `errors.json`)
- **Report Templates**: Tenant admins can create Dutch/English templates

### What Is NOT Translated

- **Account Numbers**: Technical identifiers (2010, 2020, 2021, 8001, 8002, 8003)
- **VAT Rates**: Hardcoded percentages (21%, 9%, 0%)
- **Calculation Logic**: Python code in `btw_processor.py`
- **Database Field Names**: Technical identifiers used in queries

---

## Future Considerations

### If VAT Rules Need to Be Configurable

If VAT rates or rules need to become configurable in the future:

1. **Create `vat_rules` Table**:
   ```sql
   CREATE TABLE vat_rules (
       id INT PRIMARY KEY,
       rate_type VARCHAR(50),  -- 'high', 'low', 'zero'
       percentage DECIMAL(5,2),
       account_code VARCHAR(10),
       effective_date DATE,
       administration VARCHAR(100)
   );
   ```

2. **Create `vat_rule_translations` Table**:
   ```sql
   CREATE TABLE vat_rule_translations (
       id INT PRIMARY KEY,
       vat_rule_id INT,
       language VARCHAR(5),
       rate_name VARCHAR(100),
       description TEXT,
       FOREIGN KEY (vat_rule_id) REFERENCES vat_rules(id)
   );
   ```

3. **Update `btw_processor.py`**: Query rates from database instead of hardcoding

4. **Add Admin UI**: Allow tenant admins to configure VAT rates

**Current Status**: Not needed. Dutch VAT rates are stable and changes are infrequent.

---

## Testing

**Test Files**:
- `backend/tests/unit/test_btw_processor.py` - Unit tests for BTW processor
- `backend/tests/api/test_tax_routes.py` - API endpoint tests

**Test Data**:
- Test database has sample transactions with BTW accounts
- Test mode uses separate database to avoid affecting production data

---

## Related Documentation

- **BTW Aangifte Field Mappings**: `backend/templates/html/BTW_AANGIFTE_FIELD_MAPPINGS.md`
- **Tax Routes**: `backend/src/routes/tax_routes.py`
- **Report Generator**: `backend/src/report_generators/btw_aangifte_generator.py`
- **Internationalization Spec**: `.kiro/specs/Common/Internationalization/`

---

## Summary

- VAT rules are **hardcoded in Python**, not database-driven
- No `vat_rules` table exists (and none is needed currently)
- VAT account structure is fixed: 2010, 2020, 2021 (balance), 8001, 8002, 8003 (revenue)
- VAT rates are hardcoded: 21% (high), 9% (low), 0% (zero)
- Report templates are tenant-customizable (can be in any language)
- Internationalization applies to UI labels and error messages, not business logic
