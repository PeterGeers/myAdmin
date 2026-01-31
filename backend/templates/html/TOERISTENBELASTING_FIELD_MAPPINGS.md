# Toeristenbelasting (Tourist Tax) Report Field Mappings

This document describes all field mappings and placeholders used in the Toeristenbelasting HTML template.

## Template File

- **Location**: `backend/templates/html/toeristenbelasting_template.html`
- **Generator**: `backend/src/report_generators/toeristenbelasting_generator.py`
- **Processor**: `backend/src/toeristenbelasting_processor.py`

## Report Overview

The Toeristenbelasting report is a tourist tax declaration for short-term rental properties in the Netherlands. It calculates taxable revenue, occupancy rates, and tourist tax amounts based on booking data and financial records.

## Field Categories

### 1. Basic Information

| Placeholder       | Description                 | Data Type | Example      | Source                    |
| ----------------- | --------------------------- | --------- | ------------ | ------------------------- |
| `{{ year }}`      | Report year                 | String    | "2025"       | Input parameter           |
| `{{ next_year }}` | Next year (for projections) | String    | "2026"       | Calculated: year + 1      |
| `{{ datum }}`     | Report generation date      | String    | "31-01-2026" | Current date (DD-MM-YYYY) |

### 2. Contact Information

| Placeholder            | Description   | Data Type | Example           | Source        |
| ---------------------- | ------------- | --------- | ----------------- | ------------- |
| `{{ functie }}`        | Function/role | String    | "DGA"             | Configuration |
| `{{ telefoonnummer }}` | Phone number  | String    | "06921893861"     | Configuration |
| `{{ email }}`          | Email address | String    | "peter@pgeers.nl" | Configuration |
| `{{ naam }}`           | Name          | String    | "Peter Geers"     | Configuration |
| `{{ plaats }}`         | City/location | String    | "Hoofddorp"       | Configuration |

### 3. Period and Accommodation

| Placeholder                  | Description       | Data Type | Example      | Source                       |
| ---------------------------- | ----------------- | --------- | ------------ | ---------------------------- |
| `{{ periode_van }}`          | Period start date | String    | "1-1-2025"   | Calculated: 1st Jan of year  |
| `{{ periode_tm }}`           | Period end date   | String    | "31-12-2025" | Calculated: 31st Dec of year |
| `{{ aantal_kamers }}`        | Number of rooms   | String    | "3"          | Configuration                |
| `{{ aantal_slaapplaatsen }}` | Number of beds    | String    | "8"          | Configuration                |

### 4. Rental Statistics

| Placeholder                       | Description                | Data Type | Example | Source                                |
| --------------------------------- | -------------------------- | --------- | ------- | ------------------------------------- |
| `{{ totaal_verhuurde_nachten }}`  | Total rented nights        | String    | "365"   | Sum of nights from all bookings       |
| `{{ cancelled_nachten }}`         | Cancelled nights           | String    | "12"    | Sum of nights from cancelled bookings |
| `{{ verhuurde_kamers_inwoners }}` | Nights rented to residents | String    | "0"     | Always 0 (per requirements)           |
| `{{ totaal_belastbare_nachten }}` | Total taxable nights       | String    | "353"   | Total - Cancelled                     |
| `{{ kamerbezettingsgraad }}`      | Room occupancy rate        | String    | "85.50" | (Realised nights / Max nights) \* 100 |
| `{{ bedbezettingsgraad }}`        | Bed occupancy rate         | String    | "76.95" | Room occupancy \* 0.90                |

### 5. Financial Data

| Placeholder                                          | Description                       | Data Type          | Example      | Source                                                  |
| ---------------------------------------------------- | --------------------------------- | ------------------ | ------------ | ------------------------------------------------------- |
| `{{ saldo_toeristenbelasting }}`                     | Total tourist tax collected       | String (formatted) | "€ 1.234,56" | Account 8003: (sum / 106.2) \* 6.2                      |
| `{{ ontvangsten_excl_btw_excl_toeristenbelasting }}` | Revenue excl. VAT and tourist tax | String (formatted) | "15.678,90"  | Account 8003 total - tourist tax                        |
| `{{ ontvangsten_logies_inwoners }}`                  | Revenue from residents            | String (formatted) | "0,00"       | Always 0 (per requirements)                             |
| `{{ kortingen_provisie_commissie }}`                 | Service fees/commissions          | String (formatted) | "1.234,56"   | Account 4007 (absolute value)                           |
| `{{ no_show_omzet }}`                                | No-show revenue                   | String (formatted) | "567,89"     | Sum of (amountGross - amountVat) for cancelled bookings |

### 6. Taxable Revenue Calculation

| Placeholder                                     | Description                   | Data Type          | Example     | Source                             |
| ----------------------------------------------- | ----------------------------- | ------------------ | ----------- | ---------------------------------- |
| `{{ totaal_2_3_4 }}`                            | Total of items 2, 3, 4        | String (formatted) | "1,802.45"  | Sum of: residents + fees + no-show |
| `{{ belastbare_omzet_logies }}`                 | Taxable accommodation revenue | String (formatted) | "13,876.45" | Item [1] - Item [5]                |
| `{{ verwachte_belastbare_omzet_volgend_jaar }}` | Expected next year revenue    | String (formatted) | "14,570.27" | Taxable revenue \* 1.05            |

## Data Sources

### BNB Cache (Booking Data)

- **Source**: `bnb_cache.query_by_year()`, `query_cancelled_by_year()`, `query_realised_by_year()`
- **Fields Used**: `nights`, `amountGross`, `amountVat`
- **Purpose**: Calculate rental statistics and no-show revenue

### Mutaties Cache (Financial Data)

- **Source**: `cache.get_data(db)` filtered by year and account
- **Accounts Used**:
  - **8003**: Total revenue (includes VAT and tourist tax)
  - **4007**: Service fees from booking sites
- **Purpose**: Calculate tourist tax and revenue components

## Calculation Logic

### Tourist Tax Calculation

```
Account 8003 Total = Sum of all transactions in account 8003 for the year
Tourist Tax = (Account 8003 Total / 106.2) * 6.2
```

**Explanation**: Account 8003 contains revenue including 21% VAT and 6.2% tourist tax. The formula extracts the tourist tax component.

### Revenue Calculation

```
Revenue excl. VAT and Tourist Tax = Account 8003 Total - Tourist Tax
```

### Taxable Revenue Calculation

```
[1] Revenue excl. VAT and Tourist Tax
[2] Revenue from residents (always 0)
[3] Service fees/commissions (Account 4007)
[4] No-show revenue (cancelled bookings: amountGross - amountVat)
[5] Total of [2] + [3] + [4]
[6] Taxable accommodation revenue = [1] - [5]
```

### Occupancy Rates

```
Max Nights = Number of Rooms * 365
Room Occupancy = (Realised Nights / Max Nights) * 100
Bed Occupancy = Room Occupancy * 0.90
```

## Formatting Rules

### Currency Formatting

- **Format**: `€ X.XXX,XX` (Dutch format with period as thousands separator, comma as decimal separator)
- **Applied to**: All financial amounts
- **Function**: `format_currency()` from `common_formatters`

### Number Formatting

- **Format**: `X.XXX,XX` (no currency symbol, Dutch format)
- **Applied to**: Revenue calculations in table
- **Function**: `format_amount()` from `common_formatters`

### Percentage Formatting

- **Format**: `XX.XX%` (2 decimal places)
- **Applied to**: Occupancy rates
- **Example**: `85.50%`

### Date Formatting

- **Format**: `DD-MM-YYYY` (Dutch format)
- **Applied to**: Period dates and generation date
- **Example**: `31-01-2026`

## HTML Escaping

All text fields are HTML-escaped using `escape_html()` from `common_formatters` to prevent XSS attacks:

- Contact information (name, email, phone)
- Period dates
- Configuration values

## Template Structure

The template is organized into sections:

1. **Header**: Title with year
2. **Contactgegevens**: Contact information section
3. **Periode en Accommodatie**: Period and accommodation details
4. **Verhuurgegevens**: Rental statistics
5. **Financiële Gegevens**: Financial data summary
6. **Berekening Belastbare Omzet**: Taxable revenue calculation table
7. **Ondertekening**: Signature section

## Usage Example

```python
from report_generators import toeristenbelasting_generator
from services.template_service import TemplateService

# Generate report data
report_result = toeristenbelasting_generator.generate_toeristenbelasting_report(
    cache=cache,
    bnb_cache=bnb_cache,
    db=db,
    year=2025
)

# Get template data
template_data = report_result['template_data']

# Load template
with open('backend/templates/html/toeristenbelasting_template.html', 'r') as f:
    template_content = f.read()

# Apply template
template_service = TemplateService()
html_output = template_service.apply_template(
    template_content=template_content,
    data=template_data
)
```

## Notes

- **Fixed Configuration**: Contact information and accommodation details are currently hardcoded in the generator. In a multi-tenant system, these should be retrieved from tenant configuration.
- **Residents Revenue**: Always 0 per business requirements (no rentals to local residents).
- **Service Fees**: Account 4007 contains negative values (expenses), so absolute value is used.
- **No-show Revenue**: Calculated from cancelled bookings to exclude from taxable revenue.
- **Next Year Projection**: Simple 5% increase calculation for planning purposes.

## Related Files

- **Template**: `backend/templates/html/toeristenbelasting_template.html`
- **Generator**: `backend/src/report_generators/toeristenbelasting_generator.py`
- **Processor**: `backend/src/toeristenbelasting_processor.py`
- **Common Formatters**: `backend/src/report_generators/common_formatters.py`
- **Template Service**: `backend/src/services/template_service.py`
