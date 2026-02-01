# Template Metadata Storage - Verification Report

**Date**: January 31, 2026
**Task**: Store template metadata in `tenant_template_config` table
**Status**: ✅ Completed

---

## Overview

This document verifies that template metadata has been successfully stored in the `tenant_template_config` database table as part of the Railway migration Phase 2.

---

## Database Schema Verification

The `tenant_template_config` table has been created with the following structure:

| Field            | Type         | Null | Key | Default           | Description                          |
| ---------------- | ------------ | ---- | --- | ----------------- | ------------------------------------ |
| id               | int          | NO   | PRI | NULL              | Primary key                          |
| administration   | varchar(100) | NO   | MUL | NULL              | Tenant name                          |
| template_type    | varchar(50)  | NO   |     | NULL              | Template type identifier             |
| template_file_id | varchar(255) | NO   |     | NULL              | Google Drive file ID                 |
| field_mappings   | json         | YES  |     | NULL              | JSON field mappings                  |
| is_active        | tinyint(1)   | YES  |     | 1                 | Active status (TRUE/FALSE)           |
| created_at       | timestamp    | YES  |     | CURRENT_TIMESTAMP | Creation timestamp                   |
| updated_at       | timestamp    | YES  |     | CURRENT_TIMESTAMP | Last update timestamp (auto-updated) |

**Unique Constraint**: `(administration, template_type)` - Ensures one template per type per tenant

**Index**: `idx_tenant` on `administration` - Optimizes tenant-specific queries

---

## Data Verification

### Total Records

- **Total templates stored**: 12
- **Tenants**: 2 (GoodwinSolutions, PeterPrive)
- **Templates per tenant**: 6
- **All templates active**: ✅ Yes

### GoodwinSolutions Templates

| Template Type           | File ID                           | Status    |
| ----------------------- | --------------------------------- | --------- |
| aangifte_ib_html        | 1YDH4hYjZLYJ3bLJKwwFuwbJ8rzXex82G | ✅ Active |
| btw_aangifte_html       | 1NIXR3HnlnAcSX6TAQd7Oy5R8OVjt8FtQ | ✅ Active |
| financial_report_xlsx   | 1ZxKDNfVPDCsADel3HpWu6Xu2aeFqS63a | ✅ Active |
| str_invoice_en          | 1-4XGkuae6WhGBvD1KPLuZ9q24n1Miz5Q | ✅ Active |
| str_invoice_nl          | 1HGTjnVRDy4w6OW5H6EwmWVJI_P1vq2lK | ✅ Active |
| toeristenbelasting_html | 10SJH12oBAqJiXsLmKCwnIY9wkaiqRtIp | ✅ Active |

### PeterPrive Templates

| Template Type           | File ID                           | Status    |
| ----------------------- | --------------------------------- | --------- |
| aangifte_ib_html        | 1qE0xbsqOn02AY0RYHePASUsevsrfmGFL | ✅ Active |
| btw_aangifte_html       | 1TvIGTSMKt9VsIc6siveEhPsxYGKJs7fi | ✅ Active |
| financial_report_xlsx   | 1vDgGpBWAwjrrgqKsLxIkm4VcYZcWN4n6 | ✅ Active |
| str_invoice_en          | 1rZ0hc2yCvRQnEaEK4O_DAmt2160q375V | ✅ Active |
| str_invoice_nl          | 1-oebrBuNdCMEhQ74GyjzhlVOzqUjAG8s | ✅ Active |
| toeristenbelasting_html | 1C3SoJmhxvwUTiXBts1nnYMAdAVQsUx_X | ✅ Active |

---

## Field Mappings Verification

Field mappings are stored in JSON format in the `field_mappings` column. Example from `aangifte_ib_html`:

```json
{
  "version": "1.0",
  "template_type": "aangifte_ib_html",
  "description": "Aangifte Inkomstenbelasting (Income Tax Return) HTML Report Template",
  "output_format": "html",
  "fields": {
    "year": {
      "type": "integer",
      "path": "year",
      "description": "Report year"
    },
    "administration": {
      "type": "string",
      "path": "administration",
      "description": "Administration/tenant identifier"
    },
    "table_rows": {
      "type": "array",
      "path": "table_rows",
      "format": "pre_generated",
      "description": "Pre-generated list of row dictionaries",
      "note": "Generator returns structured data, template converts to HTML"
    },
    "generated_date": {
      "type": "string",
      "format": "datetime",
      "path": "generated_date",
      "description": "Report generation timestamp"
    }
  },
  "row_structure": {
    "description": "Each row in table_rows array is a dictionary with these fields",
    "fields": {
      "row_type": {
        "type": "string",
        "values": ["parent", "aangifte", "account", "resultaat", "grand_total"]
      },
      "parent": {
        "type": "string",
        "description": "Parent code or label"
      },
      "aangifte": {
        "type": "string",
        "description": "Aangifte name or account number"
      },
      "description": {
        "type": "string",
        "description": "Account description"
      },
      "amount": {
        "type": "string",
        "description": "Formatted amount"
      },
      "amount_raw": {
        "type": "float",
        "description": "Raw numeric amount"
      },
      "css_class": {
        "type": "string",
        "description": "CSS class for styling"
      },
      "indent_level": {
        "type": "integer",
        "values": [0, 1, 2],
        "description": "Indentation level"
      }
    }
  },
  "data_source": {
    "description": "Data comes from mutaties_cache queries",
    "queries": {
      "summary": {
        "method": "cache.query_aangifte_ib(year, administration)",
        "returns": "List of {Parent, Aangifte, Amount}"
      },
      "details": {
        "method": "cache.query_aangifte_ib_details(year, administration, parent, aangifte, user_tenants)",
        "returns": "List of {Reknum, AccountName, Amount}"
      }
    }
  },
  "calculations": {
    "resultaat": {
      "description": "Net result from P&L accounts only",
      "formula": "Sum of all amounts where Parent starts with 4, 5, 6, 7, 8, or 9",
      "note": "Balance sheet accounts (1000-3000) are excluded"
    },
    "grand_total": {
      "description": "Should be close to zero for balanced accounts",
      "formula": "0.0 (hardcoded, represents balance)",
      "note": "Not actually calculated, just displayed as verification"
    }
  },
  "formatting": {
    "locale": "nl_NL",
    "currency": "EUR",
    "date_format": "%Y-%m-%d %H:%M:%S",
    "number_decimals": 2,
    "decimal_separator": ",",
    "thousands_separator": "."
  },
  "filtering": {
    "zero_amounts": "Rows with abs(amount) < 0.01 are filtered out",
    "security": "user_tenants parameter ensures tenant isolation"
  }
}
```

**Note**: Other templates (btw_aangifte_html, toeristenbelasting_html, str_invoice_nl, str_invoice_en, financial_report_xlsx) have `field_mappings` set to `NULL` as they don't have separate field mapping files yet. These can be added later through the Tenant Admin Module.

---

## Implementation Details

### Storage Process

Template metadata is stored during the upload process by the `upload_templates_to_drive.py` script:

1. **Upload template to Google Drive** - Get file ID
2. **Load field mappings** (if available) - From JSON files in `backend/templates/html/`
3. **Store metadata in database** - Using `store_template_metadata()` method

### Code Reference

**Script**: `scripts/upload_templates_to_drive.py`

**Method**: `TemplateUploader.store_template_metadata()`

```python
def store_template_metadata(self, administration: str, template_type: str,
                            file_id: str, description: str, field_mappings: dict = None):
    """Store template metadata in tenant_template_config table"""

    # Check if template config already exists
    check_query = """
        SELECT id FROM tenant_template_config
        WHERE administration = %s AND template_type = %s
    """
    existing = self.db.execute_query(check_query, (administration, template_type))

    # Convert field_mappings to JSON string
    mappings_json = json.dumps(field_mappings) if field_mappings else None

    if existing:
        # Update existing
        update_query = """
            UPDATE tenant_template_config
            SET template_file_id = %s,
                field_mappings = %s,
                is_active = TRUE,
                updated_at = CURRENT_TIMESTAMP
            WHERE administration = %s AND template_type = %s
        """
        self.db.execute_query(
            update_query,
            (file_id, mappings_json, administration, template_type),
            fetch=False,
            commit=True
        )
    else:
        # Insert new
        insert_query = """
            INSERT INTO tenant_template_config
            (administration, template_type, template_file_id, field_mappings, is_active)
            VALUES (%s, %s, %s, %s, TRUE)
        """
        self.db.execute_query(
            insert_query,
            (administration, template_type, file_id, mappings_json),
            fetch=False,
            commit=True
        )
```

---

## Verification Scripts

### 1. Database Summary

```bash
python scripts/verify_template_uploads.py --summary-only
```

**Output**: Shows all templates in database with their status

### 2. Full Verification (includes Google Drive check)

```bash
python scripts/verify_template_uploads.py
```

**Output**: Verifies both database records and Google Drive file existence

### 3. Single Tenant Verification

```bash
python scripts/verify_template_uploads.py --tenant GoodwinSolutions
```

**Output**: Verifies templates for a specific tenant

### 4. Schema Check

```bash
python scripts/check_template_schema.py
```

**Output**: Shows table schema and sample record

---

## Query Examples

### Get all templates for a tenant

```sql
SELECT template_type, template_file_id, is_active, created_at
FROM tenant_template_config
WHERE administration = 'GoodwinSolutions'
ORDER BY template_type;
```

### Get active templates only

```sql
SELECT administration, template_type, template_file_id
FROM tenant_template_config
WHERE is_active = TRUE
ORDER BY administration, template_type;
```

### Get template with field mappings

```sql
SELECT template_type, template_file_id, field_mappings
FROM tenant_template_config
WHERE administration = 'GoodwinSolutions'
  AND template_type = 'aangifte_ib_html';
```

### Count templates per tenant

```sql
SELECT administration, COUNT(*) as template_count
FROM tenant_template_config
GROUP BY administration;
```

---

## Next Steps

1. ✅ Template metadata stored in database
2. ⏭️ Verify templates are accessible (Task 2.4 - next task)
3. ⏭️ Update report generation routes to use TemplateService (Task 2.5)
4. ⏭️ Implement template preview and validation (Task 2.6)

---

## Related Documentation

- `TEMPLATE_UPLOADS_SUMMARY.md` - Template upload summary
- `TEMPLATE_FOLDERS_CREATED.md` - Template folder creation
- `backend/templates/README.md` - Template system architecture
- `backend/templates/html/AANGIFTE_IB_FIELD_MAPPINGS.md` - Field mappings documentation
- `scripts/upload_templates_to_drive.py` - Upload script
- `scripts/verify_template_uploads.py` - Verification script

---

## Conclusion

✅ **Task Completed Successfully**

All template metadata has been successfully stored in the `tenant_template_config` table:

- ✅ Database schema created with all required fields
- ✅ 12 templates stored (6 per tenant × 2 tenants)
- ✅ All templates marked as active
- ✅ Field mappings stored in JSON format (where available)
- ✅ Unique constraint ensures data integrity
- ✅ Timestamps track creation and updates
- ✅ Verification scripts confirm data integrity

The system is now ready for the next phase: verifying template accessibility from Google Drive.
