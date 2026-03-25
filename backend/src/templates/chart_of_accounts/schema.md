# Chart of Accounts Template Format

Default chart of accounts templates for new tenant provisioning.
One JSON file per locale (`nl.json`, `en.json`).

## File format

Array of account objects matching the `rekeningschema` table columns:

```json
{
  "Account": "2001", // Account code (char 10)
  "AccountLookup": null, // IBAN or lookup code — always null in templates (tenant-specific)
  "AccountName": "Tussenrekening", // Display name
  "SubParent": "200", // Sub-parent grouping code
  "Parent": "2000", // Parent grouping code
  "VW": "N", // "Y" = P&L account, "N" = Balance sheet account
  "Belastingaangifte": "Tussenrekening", // Tax return category
  "Pattern": false, // true = used for pattern matching (bank account IBANs)
  "parameters": null // JSON object for account roles, or null
}
```

## Parameters field

Used for year-end closure and VAT netting. Most accounts have `null`.

| Role                                           | Accounts         | Purpose                           |
| ---------------------------------------------- | ---------------- | --------------------------------- |
| `{"roles": ["interim_opening_balance"]}`       | 2001             | Year-end: interim opening balance |
| `{"roles": ["equity_result"]}`                 | 3080             | Year-end: equity result account   |
| `{"roles": ["pl_closing"]}`                    | 8099             | Year-end: P&L closing account     |
| `{"vat_netting": true, "vat_primary": "2010"}` | 2010, 2020, 2021 | VAT netting group                 |

## Not in templates

- `administration` — set dynamically by the provisioning service
- `AccountID` — auto-increment primary key
- Bank account IBANs in `AccountLookup` — tenants add their own
- Personal or company-specific accounts

## Account ranges

| Range     | Category                            | VW  |
| --------- | ----------------------------------- | --- |
| 1000-1999 | Assets (Balans)                     | N   |
| 2000-2999 | Interim accounts (Tussenrekeningen) | N   |
| 3000-3999 | Fixed assets & Equity               | N   |
| 4000-4999 | Expenses (Kosten)                   | Y   |
| 8000-8999 | Revenue (Opbrengsten)               | Y   |

## Adding a new locale

1. Copy `nl.json` to `{locale}.json`
2. Translate `AccountName` and `Belastingaangifte` fields
3. Keep all other fields identical (Account codes, VW, parameters, etc.)
