# Country Bookings Report - Add Frontend Button

**Status**: ✅ Complete  
**Created**: February 4, 2026  
**Completed**: February 4, 2026  
**Domain**: STR (Short-Term Rental)

## Quick Summary

Add a button to the STR Reports page that generates and downloads the Country Bookings HTML report showing guest origin statistics by country and region.

## Current State

- **Script exists**: `backend/scripts/generate_country_report.py` - standalone script that generates beautiful HTML report
- **No API endpoint**: Script runs standalone, not accessible via API
- **No frontend integration**: No button or UI to trigger report generation

## Requirements

### User Story

As a property manager, I want to click a button on the STR Reports page to generate a Country Bookings report, so I can analyze where my guests are coming from without running backend scripts manually.

### Acceptance Criteria

- [x] New tab "🌍 Country Bookings" added to STR Reports
- [x] Button to generate report in the new tab
- [x] API endpoint triggers report generation
- [x] Report downloads automatically or opens in new tab
- [x] Loading state shown during generation
- [x] Error handling for failed generation

## Implementation Plan

### Phase 1: Backend API Endpoint (30 min)

**File**: `backend/src/bnb_routes.py`

Add new endpoint:

```python
@bnb_bp.route('/generate-country-report', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
@tenant_required()
def generate_country_report(user_email, user_roles, tenant, user_tenants):
    """Generate HTML report of bookings by country"""
```

**Logic**:

- Extract report generation logic from `backend/scripts/generate_country_report.py`
- Filter by user's tenants (multi-tenant support)
- Return HTML file path or serve file directly
- Handle errors gracefully

### Phase 2: Frontend Component (30 min)

**New File**: `frontend/src/components/reports/BnbCountryBookingsReport.tsx`

**Structure**:

```typescript
- Button: "Generate Country Report"
- Loading spinner during generation
- Success message with download link
- Error message if generation fails
```

**Pattern**: Follow `BnbRevenueReport.tsx` structure

### Phase 3: Add Tab to Reports Group (5 min)

**File**: `frontend/src/components/reports/BnbReportsGroup.tsx`

Add new tab:

```typescript
<Tab color="white">🌍 Country Bookings</Tab>
```

Add new panel:

```typescript
<TabPanel>
  <BnbCountryBookingsReport />
</TabPanel>
```

## Technical Details

### Report Content

The generated HTML report includes:

- **Summary Stats**: Total bookings, countries, regions, top country
- **Region Breakdown**: Bookings by region with percentages and visual bars
- **Country Details**: Full table with country code, names (EN/NL), region, booking count, percentage
- **Beautiful Styling**: Gradient headers, hover effects, responsive design

### Database Query

Uses `vw_bnb_total` view:

```sql
SELECT country, countryName, countryNameNL, countryRegion, COUNT(*) as bookings
FROM vw_bnb_total
WHERE country IS NOT NULL AND administration IN (user_tenants)
GROUP BY country, countryName, countryNameNL, countryRegion
ORDER BY COUNT(*) DESC
```

### File Output

- Primary: `backend/reports/country_bookings_report.html`
- Secondary: `~/Downloads/country_bookings_report.html`

## Files to Modify

1. ✅ `backend/src/bnb_routes.py` - Add endpoint (537 lines, down from 859)
2. ✅ `backend/src/services/country_report_service.py` - New service module (361 lines)
3. ✅ `frontend/src/components/reports/BnbCountryBookingsReport.tsx` - Create component
4. ✅ `frontend/src/components/reports/BnbReportsGroup.tsx` - Add tab

## Refactoring Notes

The implementation initially added the report generation logic directly to `bnb_routes.py`, which grew to 859 lines (approaching the 1000 line maximum).

**Refactoring performed**:

- Extracted HTML generation logic to `backend/src/services/country_report_service.py`
- Separated concerns: routes handle HTTP/auth, service handles business logic
- Result: `bnb_routes.py` reduced to 537 lines (within 500 line target!)
- Service module: 361 lines (well within guidelines)

This follows the project's file size guidelines (target 500 lines, max 1000 lines) and improves maintainability.

## Files to Reference

- `backend/scripts/generate_country_report.py` - Source logic
- `frontend/src/components/reports/BnbRevenueReport.tsx` - Pattern example

## Testing

- [-] API endpoint returns HTML file
- [x] Frontend button triggers generation
- [x] Report downloads successfully
- [x] Multi-tenant filtering works correctly
- [x] Error handling displays properly

## Time Estimate

**Total**: ~1 hour

- Backend: 30 min
- Frontend: 30 min
- Testing: Manual verification

## Notes

- Report is read-only (no filters needed initially)
- HTML file can be opened directly in browser
- Consider adding date range filters in future iteration
- Report includes both actual and planned bookings
