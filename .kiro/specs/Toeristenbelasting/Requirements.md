# Aangifte Toeristenbelasting - Requirements & Implementation

## Overview

This document describes the requirements and implementation for the Tourist Tax (Toeristenbelasting) declaration feature in myAdmin Reports.

## User Interface

### Location

- **Tab**: 🏨 Toeristenbelasting in myAdmin Reports
- **Filter**: Year dropdown (current year and 3 years back)
- **Auto-update**: Data refreshes automatically when year changes
- **Export**: HTML button to download formatted declaration

## Data Sources

### Primary Tables

- **vw_mutaties**: Financial transactions (cached in memory)

  - Used for: Revenue calculations, tourist tax, service fees
  - Filter: `jaar = selected_year` AND `Administration = 'GoodwinSolutions'`

- **vw_bnb_total**: BNB bookings (cached in memory)
  - Combines: `bnb` (actual bookings) + `bnbplanned` (future bookings)
  - Used for: Occupancy calculations, no-show data
  - Filter: `YEAR(checkinDate) = selected_year`

### Cache Performance

- **Mutaties cache**: ~103K rows, ~88MB, loads in ~5.7s
- **BNB cache**: ~3.2K rows, ~1.5MB, loads in ~0.18s
- **TTL**: 30 minutes for both caches

## Fixed Values (Hardcoded)

```python
functie = "DGA"
telefoonnummer = "06921893861"
email = "peter@pgeers.nl"
aantal_kamers = 3
aantal_slaapplaatsen = 8
naam = "Peter Geers"
plaats = "Hoofddorp"
```

## Calculated Fields

### Section 1: Contact Information

- **Functie**: DGA (fixed)
- **Telefoonnummer**: 06921893861 (fixed)
- **E-mailadres**: peter@pgeers.nl (fixed)

### Section 2: Period & Accommodation

- **Periode van**: `1-1-{year}`
- **Periode t/m**: `31-12-{year}`
- **Aantal kamers**: 3 (fixed)
- **Aantal beschikbare slaapplaatsen**: 8 (fixed)

### Section 3: Rental Data (Verhuurgegevens)

All calculations based on **nights**, not bookings:

```python
# Get all bookings for the year from BNB cache
all_bookings = bnb_cache.query_by_year(db, year)
cancelled_bookings = bnb_cache.query_cancelled_by_year(db, year)
realised_bookings = bnb_cache.query_realised_by_year(db, year)

# Calculate totals
totaal_verhuurde_nachten = sum(b['nights'] for b in all_bookings)
cancelled_nachten = sum(b['nights'] for b in cancelled_bookings)
verhuurde_nachten_inwoners = 0  # Always 0
totaal_belastbare_nachten = totaal_verhuurde_nachten - cancelled_nachten

# Occupancy rates
total_realised_nights = sum(b['nights'] for b in realised_bookings)
max_nights = aantal_kamers * 365
kamerbezettingsgraad = (total_realised_nights / max_nights * 100)
bedbezettingsgraad = kamerbezettingsgraad * 0.90
```

**Fields:**

- **Totaal verhuurde nachten**: Sum of all nights in bookings
- **Cancelled nachten**: Sum of nights in cancelled bookings
- **Verhuurde nachten aan inwoners**: 0 (always)
- **Totaal belastbare nachten**: totaal_verhuurde_nachten - cancelled_nachten
- **Kamerbezettingsgraad (%)**: (total_realised_nights / (3 × 365)) × 100
- **Bedbezettingsgraad (%)**: kamerbezettingsgraad × 0.90

### Section 4: Financial Data (Financiële Gegevens)

```python
# Tourist tax calculation from account 8003
# Note: Use abs() because negative values = income in accounting
total_8003 = abs(sum(vw_mutaties where Reknum='8003' and jaar=year))
saldo_toeristenbelasting = abs((total_8003 / 106.2) * 6.2)
```

**Fields:**

- **Saldo totaal ingehouden toeristenbelasting**: `abs((sum(account 8003) / 106.2) × 6.2)`
- **Logiesomzet incl./excl. BTW**: excl. BTW (fixed text)
- **Logiesomzet incl./excl. toeristenbelasting**: incl. toeristenbelasting (fixed text)

### Section 5: Taxable Revenue Calculation (Berekening Belastbare Omzet)

```python
# [1] Revenue excluding VAT and tourist tax
total_revenue_8003 = abs(sum(vw_mutaties where Reknum='8003' and jaar=year))
ontvangsten_excl_btw_excl_toeristenbelasting = total_revenue_8003 - saldo_toeristenbelasting

# [2] Revenue from residents (always 0)
ontvangsten_logies_inwoners = 0

# [3] Discounts/commissions from account 4007
kortingen_provisie_commissie = abs(sum(vw_mutaties where Reknum='4007' and jaar=year))

# [4] No-show revenue (gross minus VAT for cancelled bookings)
no_show_omzet = sum(amountGross - amountVat for cancelled_bookings)

# [5] Total deductions
totaal_2_3_4 = ontvangsten_logies_inwoners + kortingen_provisie_commissie + no_show_omzet

# [6] Taxable revenue
belastbare_omzet_logies = ontvangsten_excl_btw_excl_toeristenbelasting - totaal_2_3_4

# Expected revenue next year
verwachte_belastbare_omzet_volgend_jaar = belastbare_omzet_logies * 1.05
```

**Table Fields:**

- **[1] Ontvangsten excl. BTW en excl. Toeristenbelasting**:
  - `abs(sum(account 8003)) - saldo_toeristenbelasting`
- **[2] Ontvangsten logies inwoners excl. BTW**:
  - Always `0`
- **[3] Kortingen / provisie / commissie**:
  - `abs(sum(account 4007 - Service Fee bookingssites))`
- **[4] No-show omzet**:
  - `sum(amountGross - amountVat)` where `status = 'cancelled'`
- **[5] Totaal 2 + 3 + 4**:
  - `[2] + [3] + [4]`
- **[6] Belastbare omzet logies**:
  - `[1] - [5]`
- **Verwachte belastbare omzet {next_year}**:
  - `[6] × 1.05`

### Section 6: Signature (Ondertekening)

- **Naam**: Peter Geers (fixed)
- **Plaats**: Hoofddorp (fixed)
- **Datum**: Current date (system date)
- **Aantal bijlagen**: 0 (fixed)

## Important Notes

### Sign Conventions

⚠️ **Critical**: In the accounting system, negative values represent income. All revenue fields must use `abs()` to convert to positive values for the declaration:

- Account 8003 (revenue): negative in DB → use `abs()`
- Account 4007 (costs): positive in DB → use `abs()` for consistency

### Calculation Basis

- Use **nights** (not bookings) for all occupancy calculations
- Cancelled bookings are excluded from occupancy rates
- No-show revenue uses `amountGross - amountVat` (not the VAT calculation formula)

### Account Mapping

- **8003**: JaBaKi verhuur (rental revenue including tourist tax)
- **4007**: Service Fee bookingssites (booking platform commissions)

## API Endpoints

### Generate Report

```
POST /api/toeristenbelasting/generate-report
Body: { "year": "2024" }
Returns: { success, data, html_report }
```

### Available Years

```
GET /api/toeristenbelasting/available-years
Returns: { success, years: [current, current-1, current-2, current-3] }
```

### Cache Management

```
GET /api/bnb-cache/status
POST /api/bnb-cache/refresh
POST /api/bnb-cache/invalidate
```

## Implementation Files

### Backend

- `backend/src/toeristenbelasting_processor.py` - Main calculation logic
- `backend/src/bnb_cache.py` - BNB data caching
- `backend/src/mutaties_cache.py` - Financial data caching
- `backend/src/app.py` - API endpoints (lines ~1860-1990)
- `backend/create_bnb_total_view.sql` - Database view definition

### Frontend

- `frontend/src/components/myAdminReports.tsx` - UI component (Toeristenbelasting tab)

### Database

- **View**: `vw_bnb_total` - Combines `bnb` and `bnbplanned` tables
- **View**: `vw_mutaties` - Financial transactions view

## Example Results

### 2024

- Totaal verhuurde nachten: 991
- Cancelled nachten: 6
- Totaal belastbare nachten: 985
- Kamerbezettingsgraad: 89.95%
- No-show omzet: €477.36
- Belastbare omzet logies: €82,711.06
- Verwachte omzet 2025: €86,846.61

### 2025

- Totaal verhuurde nachten: 778
- Cancelled nachten: 7
- Totaal belastbare nachten: 771
- Kamerbezettingsgraad: 70.41%
- No-show omzet: €599.46
- Belastbare omzet logies: €70,412.95
- Verwachte omzet 2026: €73,933.60

## Future Maintenance

### To Update Fixed Values

Edit `backend/src/toeristenbelasting_processor.py` in the `generate_toeristenbelasting_report()` method:

```python
functie = "DGA"
telefoonnummer = "06921893861"
email = "peter@pgeers.nl"
aantal_kamers = 3
aantal_slaapplaatsen = 8
naam = "Peter Geers"
plaats = "Hoofddorp"
```

### To Change Calculation Logic

1. Update `backend/src/toeristenbelasting_processor.py`
2. Update this requirements document
3. Test with multiple years
4. Rebuild frontend if display changes: `npm run build` in frontend directory
5. Copy build to backend: `Copy-Item -Path frontend\build\* -Destination backend\frontend\ -Recurse -Force`
6. Restart backend: `docker restart myadmin-backend-1`

### To Add New Accounts

1. Add calculation method in `toeristenbelasting_processor.py`
2. Update the calculation section in this document
3. Update HTML template if needed
4. Update frontend display if needed

## Testing

### Manual Testing

```powershell
# Test 2024
$body = @{ year = "2024" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:5000/api/toeristenbelasting/generate-report" -Method POST -Body $body -ContentType "application/json"

# Test 2025
$body = @{ year = "2025" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:5000/api/toeristenbelasting/generate-report" -Method POST -Body $body -ContentType "application/json"

# Check cache status
Invoke-RestMethod -Uri "http://localhost:5000/api/bnb-cache/status"
```

### Validation Checklist

- [ ] All amounts are positive
- [ ] Nights calculations match database totals
- [ ] Kamerbezettingsgraad is reasonable (0-100%)
- [ ] No-show omzet matches cancelled bookings
- [ ] HTML export generates correctly
- [ ] Frontend displays all fields correctly
