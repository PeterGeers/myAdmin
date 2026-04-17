# Field Mappings JSON Structure Documentation

**Last Updated**: January 2026
**Status**: Complete

---

## 📋 Overview

This document defines the JSON structure for `field_mappings` in the `tenant_template_config` table. Field mappings enable flexible, tenant-specific template customization by mapping data fields to template placeholders.

**Purpose**:

- Map database fields to template variables
- Support conditional rendering logic
- Enable tenant-specific field customization
- Provide formatting rules for data presentation

---

## 🏗️ Schema Definition

### Base Structure

```json
{
  "fields": {
    "field_name": {
      "source": "string",
      "path": "string",
      "format": "string",
      "default": "any",
      "required": boolean,
      "transform": "string"
    }
  },
  "conditionals": [
    {
      "field": "string",
      "operator": "string",
      "value": "any",
      "action": "string"
    }
  ],
  "formatting": {
    "currency": "string",
    "date_format": "string",
    "number_decimals": integer,
    "locale": "string"
  },
  "metadata": {
    "version": "string",
    "last_updated": "string",
    "tenant_customizations": {}
  }
}
```

---

## 📚 Field Definitions

### 1. Fields Object

Maps template variables to data sources.

**Structure**:

```json
"fields": {
  "template_variable_name": {
    "source": "database|calculation|static",
    "path": "data.path.to.value",
    "format": "currency|date|number|text",
    "default": "default_value",
    "required": true|false,
    "transform": "abs|round|uppercase|lowercase"
  }
}
```

**Properties**:

| Property    | Type    | Required | Description                                                       |
| ----------- | ------- | -------- | ----------------------------------------------------------------- |
| `source`    | string  | Yes      | Data source type: `database`, `calculation`, `static`             |
| `path`      | string  | Yes      | Dot-notation path to data field (e.g., `booking.amountGross`)     |
| `format`    | string  | No       | Output format: `currency`, `date`, `number`, `text`               |
| `default`   | any     | No       | Default value if field is missing or null                         |
| `required`  | boolean | No       | Whether field must have a value (default: false)                  |
| `transform` | string  | No       | Transformation function: `abs`, `round`, `uppercase`, `lowercase` |

**Example**:

```json
"fields": {
  "invoice_total": {
    "source": "database",
    "path": "booking.amountGross",
    "format": "currency",
    "default": 0,
    "required": true,
    "transform": "round"
  },
  "guest_name": {
    "source": "database",
    "path": "booking.guestName",
    "format": "text",
    "default": "Guest",
    "required": true,
    "transform": "uppercase"
  }
}
```

---

### 2. Conditionals Array

Defines conditional rendering logic for template sections.

**Structure**:

```json
"conditionals": [
  {
    "field": "field_name",
    "operator": "gt|lt|eq|ne|gte|lte|contains",
    "value": "comparison_value",
    "action": "show|hide|replace"
  }
]
```

**Properties**:

| Property   | Type   | Required | Description                                                           |
| ---------- | ------ | -------- | --------------------------------------------------------------------- |
| `field`    | string | Yes      | Field name to evaluate                                                |
| `operator` | string | Yes      | Comparison operator: `gt`, `lt`, `eq`, `ne`, `gte`, `lte`, `contains` |
| `value`    | any    | Yes      | Value to compare against                                              |
| `action`   | string | Yes      | Action to take: `show`, `hide`, `replace`                             |

**Operators**:

- `gt`: Greater than
- `lt`: Less than
- `eq`: Equal to
- `ne`: Not equal to
- `gte`: Greater than or equal to
- `lte`: Less than or equal to
- `contains`: String contains substring

**Example**:

```json
"conditionals": [
  {
    "field": "tourist_tax",
    "operator": "gt",
    "value": 0,
    "action": "show"
  },
  {
    "field": "vat_amount",
    "operator": "eq",
    "value": 0,
    "action": "hide"
  }
]
```

---

### 3. Formatting Object

Global formatting rules for the template.

**Structure**:

```json
"formatting": {
  "currency": "EUR|USD|GBP",
  "date_format": "DD-MM-YYYY|YYYY-MM-DD|MM/DD/YYYY",
  "number_decimals": 2,
  "locale": "nl-NL|en-US|en-GB"
}
```

**Properties**:

| Property          | Type    | Required | Description                          |
| ----------------- | ------- | -------- | ------------------------------------ |
| `currency`        | string  | No       | Currency code (ISO 4217)             |
| `date_format`     | string  | No       | Date format pattern                  |
| `number_decimals` | integer | No       | Number of decimal places for numbers |
| `locale`          | string  | No       | Locale for formatting (BCP 47)       |

**Example**:

```json
"formatting": {
  "currency": "EUR",
  "date_format": "DD-MM-YYYY",
  "number_decimals": 2,
  "locale": "nl-NL"
}
```

---

### 4. Metadata Object

Template metadata and tenant customizations.

**Structure**:

```json
"metadata": {
  "version": "1.0.0",
  "last_updated": "2026-01-30",
  "tenant_customizations": {
    "logo_url": "string",
    "company_name": "string",
    "custom_fields": {}
  }
}
```

**Properties**:

| Property                | Type   | Required | Description                           |
| ----------------------- | ------ | -------- | ------------------------------------- |
| `version`               | string | No       | Mapping version (semantic versioning) |
| `last_updated`          | string | No       | Last update date (ISO 8601)           |
| `tenant_customizations` | object | No       | Tenant-specific customizations        |

---

## 📝 Template Type Examples

### 1. STR Invoice Template

**Template Type**: `str_invoice`

**Field Mappings**:

```json
{
  "fields": {
    "reservationCode": {
      "source": "database",
      "path": "booking.reservationCode",
      "format": "text",
      "required": true
    },
    "guestName": {
      "source": "database",
      "path": "booking.guestName",
      "format": "text",
      "required": true,
      "transform": "uppercase"
    },
    "checkinDate": {
      "source": "database",
      "path": "booking.checkinDate",
      "format": "date",
      "required": true
    },
    "checkoutDate": {
      "source": "database",
      "path": "booking.checkoutDate",
      "format": "date",
      "required": true
    },
    "nights": {
      "source": "database",
      "path": "booking.nights",
      "format": "number",
      "default": 1
    },
    "guests": {
      "source": "database",
      "path": "booking.guests",
      "format": "number",
      "default": 1
    },
    "net_amount": {
      "source": "database",
      "path": "booking.amountNett",
      "format": "currency",
      "required": true
    },
    "tourist_tax": {
      "source": "database",
      "path": "booking.amountTouristTax",
      "format": "currency",
      "default": 0
    },
    "vat_amount": {
      "source": "database",
      "path": "booking.amountVat",
      "format": "currency",
      "default": 0
    },
    "amountGross": {
      "source": "database",
      "path": "booking.amountGross",
      "format": "currency",
      "required": true
    },
    "invoice_date": {
      "source": "calculation",
      "path": "booking.checkinDate",
      "format": "date",
      "required": true
    },
    "billing_name": {
      "source": "database",
      "path": "booking.guestName",
      "format": "text",
      "default": "Guest"
    },
    "billing_address": {
      "source": "database",
      "path": "booking.channel",
      "format": "text",
      "default": "Via booking platform"
    }
  },
  "conditionals": [
    {
      "field": "tourist_tax",
      "operator": "gt",
      "value": 0,
      "action": "show"
    },
    {
      "field": "vat_amount",
      "operator": "gt",
      "value": 0,
      "action": "show"
    }
  ],
  "formatting": {
    "currency": "EUR",
    "date_format": "DD-MM-YYYY",
    "number_decimals": 2,
    "locale": "nl-NL"
  },
  "metadata": {
    "version": "1.0.0",
    "last_updated": "2026-01-30",
    "tenant_customizations": {
      "logo_url": "https://drive.google.com/file/d/...",
      "company_name": "Property Management Co."
    }
  }
}
```

---

### 2. BTW Aangifte Template

**Template Type**: `btw_aangifte`

**Field Mappings**:

```json
{
  "fields": {
    "administration": {
      "source": "database",
      "path": "report.administration",
      "format": "text",
      "required": true
    },
    "year": {
      "source": "database",
      "path": "report.year",
      "format": "number",
      "required": true
    },
    "quarter": {
      "source": "database",
      "path": "report.quarter",
      "format": "number",
      "required": true
    },
    "end_date": {
      "source": "database",
      "path": "report.quarter_end_date",
      "format": "date",
      "required": true
    },
    "total_balance": {
      "source": "calculation",
      "path": "calculations.total_balance",
      "format": "currency",
      "required": true
    },
    "received_btw": {
      "source": "calculation",
      "path": "calculations.received_btw",
      "format": "currency",
      "transform": "abs"
    },
    "prepaid_btw": {
      "source": "calculation",
      "path": "calculations.prepaid_btw",
      "format": "currency"
    },
    "payment_instruction": {
      "source": "calculation",
      "path": "calculations.payment_instruction",
      "format": "text",
      "required": true
    },
    "balance_data": {
      "source": "database",
      "path": "report.balance_data",
      "format": "table"
    },
    "quarter_data": {
      "source": "database",
      "path": "report.quarter_data",
      "format": "table"
    }
  },
  "conditionals": [],
  "formatting": {
    "currency": "EUR",
    "date_format": "YYYY-MM-DD",
    "number_decimals": 2,
    "locale": "nl-NL"
  },
  "metadata": {
    "version": "1.0.0",
    "last_updated": "2026-01-30",
    "tenant_customizations": {
      "author": "Peter Geers",
      "belastingdienst_url": "https://mijnzakelijk.belastingdienst.nl/GTService/#/inloggen"
    }
  }
}
```

---

### 3. Toeristenbelasting Template

**Template Type**: `toeristenbelasting`

**Field Mappings**:

```json
{
  "fields": {
    "year": {
      "source": "database",
      "path": "report.year",
      "format": "number",
      "required": true
    },
    "functie": {
      "source": "static",
      "path": "report.functie",
      "format": "text",
      "default": "DGA"
    },
    "telefoonnummer": {
      "source": "static",
      "path": "report.telefoonnummer",
      "format": "text",
      "required": true
    },
    "email": {
      "source": "static",
      "path": "report.email",
      "format": "text",
      "required": true
    },
    "aantal_kamers": {
      "source": "static",
      "path": "report.aantal_kamers",
      "format": "number",
      "default": 3
    },
    "aantal_slaapplaatsen": {
      "source": "static",
      "path": "report.aantal_slaapplaatsen",
      "format": "number",
      "default": 8
    },
    "totaal_verhuurde_nachten": {
      "source": "calculation",
      "path": "report.totaal_verhuurde_nachten",
      "format": "number",
      "required": true
    },
    "cancelled_nachten": {
      "source": "calculation",
      "path": "report.cancelled_nachten",
      "format": "number",
      "default": 0
    },
    "totaal_belastbare_nachten": {
      "source": "calculation",
      "path": "report.totaal_belastbare_nachten",
      "format": "number",
      "required": true
    },
    "kamerbezettingsgraad": {
      "source": "calculation",
      "path": "report.kamerbezettingsgraad",
      "format": "number",
      "transform": "round"
    },
    "saldo_toeristenbelasting": {
      "source": "calculation",
      "path": "report.saldo_toeristenbelasting",
      "format": "currency",
      "transform": "abs"
    },
    "belastbare_omzet_logies": {
      "source": "calculation",
      "path": "report.belastbare_omzet_logies",
      "format": "currency",
      "required": true
    },
    "naam": {
      "source": "static",
      "path": "report.naam",
      "format": "text",
      "required": true
    },
    "plaats": {
      "source": "static",
      "path": "report.plaats",
      "format": "text",
      "required": true
    }
  },
  "conditionals": [],
  "formatting": {
    "currency": "EUR",
    "date_format": "DD-MM-YYYY",
    "number_decimals": 2,
    "locale": "nl-NL"
  },
  "metadata": {
    "version": "1.0.0",
    "last_updated": "2026-01-30",
    "tenant_customizations": {
      "contact_person": "Peter Geers",
      "property_details": {
        "rooms": 3,
        "beds": 8
      }
    }
  }
}
```

---

### 4. Financial Report Template

**Template Type**: `financial_report`

**Field Mappings**:

```json
{
  "fields": {
    "date_from": {
      "source": "database",
      "path": "report.date_from",
      "format": "date",
      "required": true
    },
    "date_to": {
      "source": "database",
      "path": "report.date_to",
      "format": "date",
      "required": true
    },
    "administration": {
      "source": "database",
      "path": "report.administration",
      "format": "text",
      "required": true
    },
    "category": {
      "source": "database",
      "path": "report.category",
      "format": "text",
      "default": "all"
    },
    "summary_data": {
      "source": "database",
      "path": "report.summary_data",
      "format": "table"
    },
    "total_revenue": {
      "source": "calculation",
      "path": "report.total_revenue",
      "format": "currency"
    },
    "total_expenses": {
      "source": "calculation",
      "path": "report.total_expenses",
      "format": "currency"
    },
    "net_profit": {
      "source": "calculation",
      "path": "report.net_profit",
      "format": "currency"
    }
  },
  "conditionals": [
    {
      "field": "category",
      "operator": "eq",
      "value": "income",
      "action": "show"
    },
    {
      "field": "category",
      "operator": "eq",
      "value": "expense",
      "action": "show"
    }
  ],
  "formatting": {
    "currency": "EUR",
    "date_format": "DD-MM-YYYY",
    "number_decimals": 2,
    "locale": "nl-NL"
  },
  "metadata": {
    "version": "1.0.0",
    "last_updated": "2026-01-30",
    "tenant_customizations": {
      "report_title": "Financial Summary Report",
      "company_logo": "https://drive.google.com/file/d/..."
    }
  }
}
```

---

## 🔧 Implementation Guidelines

### 1. Storing Field Mappings

Field mappings are stored as JSON in the `field_mappings` column of `tenant_template_config`:

```sql
INSERT INTO tenant_template_config (
    administration,
    template_type,
    template_file_id,
    field_mappings,
    is_active
) VALUES (
    'GoodwinSolutions',
    'str_invoice',
    '1a2b3c4d5e6f7g8h9i0j',
    '{"fields": {...}, "conditionals": [...], "formatting": {...}}',
    TRUE
);
```

### 2. Retrieving Field Mappings

```python
def get_template_metadata(administration, template_type):
    """Get template metadata including field mappings"""
    query = """
        SELECT template_file_id, field_mappings, is_active
        FROM tenant_template_config
        WHERE administration = %s AND template_type = %s AND is_active = TRUE
        LIMIT 1
    """
    result = execute_query(query, (administration, template_type))

    if result:
        field_mappings = json.loads(result['field_mappings'])
        return {
            'template_file_id': result['template_file_id'],
            'field_mappings': field_mappings,
            'is_active': result['is_active']
        }
    return None
```

### 3. Applying Field Mappings

```python
def apply_field_mappings(template_xml, data, mappings):
    """Apply field mappings to template"""
    fields = mappings.get('fields', {})
    conditionals = mappings.get('conditionals', [])
    formatting = mappings.get('formatting', {})

    # Apply field mappings
    for field_name, field_config in fields.items():
        value = get_field_value(data, field_config)
        value = format_value(value, field_config, formatting)
        template_xml = template_xml.replace(f"{{{{ {field_name} }}}}", str(value))

    # Apply conditionals
    for conditional in conditionals:
        field_value = get_field_value(data, fields[conditional['field']])
        if evaluate_conditional(field_value, conditional):
            apply_conditional_action(template_xml, conditional)

    return template_xml
```

---

## 📊 Database Schema

### tenant_template_config Table

```sql
CREATE TABLE tenant_template_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    template_type VARCHAR(50) NOT NULL,
    template_file_id VARCHAR(255) NOT NULL,
    field_mappings JSON,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_tenant_template (administration, template_type),
    INDEX idx_tenant (administration)
);
```

**Column Descriptions**:

| Column             | Type         | Description                                         |
| ------------------ | ------------ | --------------------------------------------------- |
| `id`               | INT          | Primary key                                         |
| `administration`   | VARCHAR(100) | Tenant identifier                                   |
| `template_type`    | VARCHAR(50)  | Template type (e.g., `str_invoice`, `btw_aangifte`) |
| `template_file_id` | VARCHAR(255) | Google Drive file ID for template                   |
| `field_mappings`   | JSON         | Field mappings JSON (this document)                 |
| `is_active`        | BOOLEAN      | Whether template is active                          |
| `created_at`       | TIMESTAMP    | Creation timestamp                                  |
| `updated_at`       | TIMESTAMP    | Last update timestamp                               |

---

## ✅ Validation Rules

### 1. Required Fields

- `fields` object must contain at least one field
- Each field must have `source` and `path` properties
- `template_type` must match one of: `str_invoice`, `btw_aangifte`, `toeristenbelasting`, `financial_report`, `ib_aangifte`

### 2. Field Source Validation

- `source` must be one of: `database`, `calculation`, `static`
- `path` must be a valid dot-notation string
- `format` must be one of: `currency`, `date`, `number`, `text`, `table`

### 3. Conditional Validation

- `operator` must be one of: `gt`, `lt`, `eq`, `ne`, `gte`, `lte`, `contains`
- `action` must be one of: `show`, `hide`, `replace`
- `field` must reference an existing field in `fields` object

### 4. Formatting Validation

- `currency` must be a valid ISO 4217 code
- `locale` must be a valid BCP 47 locale code
- `number_decimals` must be a non-negative integer

---

## 🔍 Example Queries

### Get All Templates for Tenant

```sql
SELECT template_type, template_file_id, field_mappings, is_active
FROM tenant_template_config
WHERE administration = 'GoodwinSolutions'
ORDER BY template_type;
```

### Update Field Mappings

```sql
UPDATE tenant_template_config
SET field_mappings = '{"fields": {...}, "conditionals": [...]}',
    updated_at = NOW()
WHERE administration = 'GoodwinSolutions'
  AND template_type = 'str_invoice';
```

### Get Active Template

```sql
SELECT template_file_id, field_mappings
FROM tenant_template_config
WHERE administration = 'GoodwinSolutions'
  AND template_type = 'str_invoice'
  AND is_active = TRUE
LIMIT 1;
```

---

## 📚 Related Documentation

- **Master Plan**: `IMPACT_ANALYSIS_SUMMARY.md`
- **Implementation Tasks**: `TASKS.md`
- **Credentials**: `CREDENTIALS_IMPLEMENTATION.md`

---

## 🆘 Troubleshooting

### Issue: Field mapping not applied

**Solution**:

1. Verify field name matches template placeholder exactly
2. Check `path` points to correct data location
3. Ensure `source` type is correct

### Issue: Conditional not working

**Solution**:

1. Verify `field` references existing field in `fields` object
2. Check `operator` and `value` are correct
3. Ensure field value type matches comparison value type

### Issue: Formatting not applied

**Solution**:

1. Verify `format` is specified in field config
2. Check `formatting` object has correct global settings
3. Ensure locale and currency codes are valid

---

## 📝 Notes

- Field mappings are tenant-specific and stored per template type
- Mappings can be updated without changing template files
- Conditional logic is evaluated at render time
- All currency values default to EUR unless specified
- Date formats default to DD-MM-YYYY for Dutch locale
