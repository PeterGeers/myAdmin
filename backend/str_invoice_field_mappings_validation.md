# STR Invoice Field Mappings JSON Validation

## Issues Found

### ❌ Critical Issues

1. **Incorrect field structure** - Fields should have `source`, `path`, `format`, not `type`, `description`
2. **Missing `source` property** - Each field needs a `source` property (`database`, `calculation`, or `static`)
3. **Extra properties** - `type`, `description`, `note` are not used by TemplateService
4. **Top-level metadata** - Properties like `version`, `languages`, `data_source`, `output_format`, etc. should be in a `metadata` object or removed

### ⚠️ Minor Issues

1. **Conditionals action names** - Actions should be `show`, `hide`, or `replace`, not `show_vat_line`
2. **Extra top-level properties** - `template_location`, `output_storage` are not used by TemplateService

## Corrected JSON Structure

```json
{
  "fields": {
    "reservationCode": {
      "source": "database",
      "path": "reservationCode",
      "format": "text",
      "default": ""
    },
    "guestName": {
      "source": "database",
      "path": "guestName",
      "format": "text",
      "default": ""
    },
    "channel": {
      "source": "database",
      "path": "channel",
      "format": "text",
      "default": ""
    },
    "listing": {
      "source": "database",
      "path": "listing",
      "format": "text",
      "default": ""
    },
    "checkinDate": {
      "source": "database",
      "path": "checkinDate",
      "format": "date",
      "default": ""
    },
    "checkoutDate": {
      "source": "database",
      "path": "checkoutDate",
      "format": "date",
      "default": ""
    },
    "nights": {
      "source": "database",
      "path": "nights",
      "format": "number",
      "default": 0
    },
    "guests": {
      "source": "database",
      "path": "guests",
      "format": "number",
      "default": 0
    },
    "net_amount": {
      "source": "database",
      "path": "net_amount",
      "format": "currency",
      "transform": "round",
      "default": 0
    },
    "vat_amount": {
      "source": "database",
      "path": "vat_amount",
      "format": "currency",
      "transform": "round",
      "default": 0
    },
    "tourist_tax": {
      "source": "database",
      "path": "tourist_tax",
      "format": "currency",
      "transform": "round",
      "default": 0
    },
    "amountGross": {
      "source": "database",
      "path": "amountGross",
      "format": "currency",
      "transform": "round",
      "default": 0
    },
    "company_name": {
      "source": "static",
      "path": "company_name",
      "format": "text",
      "default": "Jabaki a Goodwin Solutions Company"
    },
    "company_address": {
      "source": "static",
      "path": "company_address",
      "format": "text",
      "default": "Beemsterstraat 3"
    },
    "company_postal_city": {
      "source": "static",
      "path": "company_postal_city",
      "format": "text",
      "default": "2131 ZA Hoofddorp"
    },
    "company_country": {
      "source": "static",
      "path": "company_country",
      "format": "text",
      "default": "Nederland"
    },
    "company_vat": {
      "source": "static",
      "path": "company_vat",
      "format": "text",
      "default": "NL812613764B02"
    },
    "company_coc": {
      "source": "static",
      "path": "company_coc",
      "format": "text",
      "default": "24352408"
    },
    "contact_email": {
      "source": "static",
      "path": "contact_email",
      "format": "text",
      "default": "peter@jabaki.nl"
    },
    "billing_name": {
      "source": "database",
      "path": "billing_name",
      "format": "text",
      "default": ""
    },
    "billing_address": {
      "source": "database",
      "path": "billing_address",
      "format": "text",
      "default": ""
    },
    "billing_city": {
      "source": "database",
      "path": "billing_city",
      "format": "text",
      "default": ""
    },
    "invoice_date": {
      "source": "database",
      "path": "invoice_date",
      "format": "date",
      "default": ""
    },
    "due_date": {
      "source": "database",
      "path": "due_date",
      "format": "date",
      "default": ""
    },
    "table_rows": {
      "source": "calculation",
      "path": "table_rows",
      "format": "text",
      "default": ""
    }
  },
  "conditionals": [
    {
      "field": "vat_amount",
      "operator": "gt",
      "value": 0,
      "action": "show"
    },
    {
      "field": "tourist_tax",
      "operator": "gt",
      "value": 0,
      "action": "show"
    }
  ],
  "formatting": {
    "locale": "nl_NL",
    "currency": "EUR",
    "date_format": "DD-MM-YYYY",
    "number_decimals": 2
  }
}
```

## Key Changes Made

1. ✅ **Added `source` property** to all fields (`database`, `static`, or `calculation`)
2. ✅ **Removed `type` and `description`** - Not used by TemplateService
3. ✅ **Simplified conditionals** - Changed action from `show_vat_line` to `show`
4. ✅ **Removed extra top-level properties** - Removed `version`, `languages`, `data_source`, `output_format`, `template_location`, `output_storage`
5. ✅ **Added `default` values** - All fields now have appropriate defaults
6. ✅ **Added `transform: "round"`** to currency fields for proper formatting

## Usage in Database

```sql
-- For Dutch template
INSERT INTO tenant_template_config (
    administration,
    template_type,
    template_file_id,
    field_mappings,
    is_active
) VALUES (
    'GoodwinSolutions',
    'str_invoice_nl',
    '<google_drive_file_id>',
    '<corrected_json_above>',
    TRUE
);

-- For English template (change locale and defaults)
INSERT INTO tenant_template_config (
    administration,
    template_type,
    template_file_id,
    field_mappings,
    is_active
) VALUES (
    'GoodwinSolutions',
    'str_invoice_en',
    '<google_drive_file_id>',
    '<corrected_json_with_en_locale>',
    TRUE
);
```

## Notes

- The `source` property is important for TemplateService to understand where data comes from
- `static` fields (company info) can have defaults that are tenant-specific
- `database` fields come from the booking data
- `calculation` fields (like `table_rows`) are pre-generated by the generator
- Conditionals are evaluated but currently only logged (not fully implemented in template rendering)
- The `formatting` section controls how currency, dates, and numbers are displayed
