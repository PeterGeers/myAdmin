# Year-End Closure - Feature Tasks

**Status**: Not Started  
**Related**: design-closure.md, requirements.md, `.kiro/specs/FIN/README.md`  
**Purpose**: User-facing year-end closure feature

## Overview

Build the year-end closure feature that allows users to close fiscal years, creating year-end closure and opening balance transactions.

**IMPORTANT**: Before implementing any task, read `.kiro/specs/FIN/README.md` to understand:

- Double-entry bookkeeping principles (Debet + Credit in every transaction)
- TransactionAmount format (always positive)
- VW classification ('Y' = P&L, 'N' = Balance Sheet)
- Transaction structure and reference field patterns
- Code organization guidelines (500 lines target, 1000 max)

## Phase 1: Database & Configuration (2-3 days)

### Database Schema

- [x] Create `year_closure_status` table
- [x] Add indexes (administration, year)
- [x] Document schema

### Account Configuration

- [x] Ensure `parameters` JSON column exists in `rekeningschema`
- [x] Create helper function `get_account_by_purpose()`
- [x] Document configuration approach

### Configuration UI (Tenant Admin)

- [x] Add "Purpose" column to Chart of Accounts management
- [x] Create Year-End Settings screen (purpose-centric)
- [x] Add validation for account purposes
- [x] Add role-based access control (Tenant_Admin)

**Phase 1 Implementation Complete** - Ready for testing

### Phase 1 Testing (1-2 hours)

**Reference**: See `PHASE1_TESTING_GUIDE.md` for detailed testing instructions

#### Database Testing

- [x] Run migration in dry-run mode
- [x] Run actual migration
- [x] Verify `year_closure_status` table created
- [x] Verify `parameters` column added to `rekeningschema` (already existed)
- [x] Verify indexes created
- [x] Fix transaction references to use TransactionNumber instead of IDs

#### Backend Service Testing

- [x] Test `YearEndConfigService` initialization
- [x] Test `REQUIRED_PURPOSES` contains 3 purposes
- [x] Test `validate_configuration()` with no config (should fail)
- [x] Test `get_available_accounts()` with VW filter
- [x] Test `set_account_purpose()` updates database
- [x] Test `get_configured_purposes()` returns correct data

#### Backend API Testing

- [x] Test `GET /api/tenant-admin/year-end-config/validate`
- [x] Test `GET /api/tenant-admin/year-end-config/purposes`
- [x] Test `GET /api/tenant-admin/year-end-config/available-accounts?vw=N`
- [x] Test `GET /api/tenant-admin/year-end-config/available-accounts?vw=Y`
- [x] Test `POST /api/tenant-admin/year-end-config/accounts` (set purpose)
- [x] Test `DELETE /api/tenant-admin/year-end-config/accounts/{code}` (clear purpose)
- [x] Test authentication required (401 without token)
- [x] Test authorization required (403 without Tenant_Admin role)

#### Frontend Chart of Accounts Testing

- [x] Verify "Purpose" column displays
- [x] Verify configured purposes show as green badges
- [x] Verify unconfigured accounts show "-"
- [x] Test purpose filter (type "equity")
- [x] Test clear all filters includes purpose filter
- [x] Verify column uses correct terminology ("Purpose" not "Role")

#### Frontend Year-End Settings Testing

- [x] Navigate to Year-End Settings screen
- [x] Verify access control (Tenant_Admin only)
- [x] Test with non-admin user (should show "Access Denied")
- [x] Verify initial state shows "Configuration Incomplete"
- [x] Verify 3 purpose configuration boxes display
- [x] Test Equity Result dropdown (VW='N' accounts only)
- [x] Test P&L Closing dropdown (VW='Y' accounts only)
- [x] Test Interim Opening Balance dropdown (VW='N' accounts only)
- [x] Configure all 3 purposes
- [x] Click Save Configuration
- [x] Verify success message displays
- [x] Verify validation shows "Configuration Complete"
- [x] Refresh page and verify configuration persists

#### Integration Testing

- [x] Clear all configuration in database
- [x] Open Year-End Settings (should show incomplete)
- [x] Configure all 3 purposes and save
- [x] Verify Chart of Accounts shows purpose badges
- [x] Test purpose filter in Chart of Accounts
- [x] Verify validation API returns `valid: true`
- [x] Verify database has 3 accounts with purposes

#### Error Handling Testing

- [x] Test invalid purpose name (should return 400)
- [x] Test wrong VW classification (should return 400)
- [x] Test duplicate purpose assignment (should return 400)
- [x] Test non-existent account (should return 400)
- [x] Verify all errors have clear messages
- [x] Verify no 500 errors occur

#### Quick Smoke Test (5 minutes)

- [x] Run migration
- [x] Open Year-End Settings
- [x] Configure all 3 purposes
- [x] Save configuration
- [x] Check Chart of Accounts shows badges
- [x] Refresh page - configuration persists

**Phase 1 Testing Complete**: All tests must pass before proceeding to Phase 2

## Phase 2: Backend Core Logic (3-4 days)

**Phase 2 Implementation Complete** - All methods tested and working

### Service Class Structure

- [x] Create `backend/src/services/year_end_service.py`
- [x] Create `YearEndClosureService` class
- [x] Implement `__init__()` with database connection
- [x] Keep file under 500 lines (currently 298 lines)

### Available Years

- [x] Implement `get_available_years()` method
- [x] Query years with transactions
- [x] Exclude already closed years
- [x] Test with sample data (19 years found, 2010-2028)

### Validation Logic

- [x] Implement `validate_year_closure()` method (in year_end_service.py)
- [x] Check if year already closed
- [x] Check if previous year is closed
- [x] Check required accounts configured
- [x] Calculate net P&L result
- [x] Count balance sheet accounts
- [x] Return validation result object

### Calculate Net P&L Result

- [x] Implement `_calculate_net_pl_result()` method
- [x] Query mutaties with rekeningschema for VW='Y' accounts
- [x] Sum amounts for the year
- [x] Test with profit and loss scenarios

### Create Closure Transaction

- [x] Implement `_create_closure_transaction()` method
- [x] Get equity and P&L closing accounts
- [x] Determine debit/credit based on profit/loss
- [x] Insert transaction into mutaties table
- [x] Return transaction number
- [x] Test with profit and loss scenarios

### Create Opening Balances

- [x] Implement `_create_opening_balances()` method
- [x] Get ending balances from previous year
- [x] Get interim account from configuration
- [x] Create transaction records with proper debit/credit
- [x] Return transaction number
- [x] Test with sample balances

### Close Year Method

- [x] Implement `close_year()` method
- [x] Validate year can be closed
- [x] Create closure transaction
- [x] Create opening balances
- [x] Record closure status
- [x] Use database transaction (rollback on error)
- [x] Return success result

### Helper Methods

- [x] Implement `_get_ending_balances()`
- [x] Implement `_is_year_closed()`
- [x] Implement `_get_first_year()`
- [x] Implement `_count_balance_sheet_accounts()`
- [x] Implement `_record_closure_status()`

### Query Methods

- [x] Implement `get_closed_years()`
- [x] Implement `get_year_status()`
- [x] Test all query methods

## Phase 3: Backend API (2 days)

### API Routes

- [ ] Create `backend/src/routes/year_end_routes.py`
- [ ] Create `year_end_bp` Blueprint
- [ ] Keep file under 200 lines

### Endpoints

- [ ] Implement `GET /api/year-end/available-years`
- [ ] Implement `POST /api/year-end/validate`
- [ ] Implement `POST /api/year-end/close`
- [ ] Implement `GET /api/year-end/closed-years`
- [ ] Implement `GET /api/year-end/status/<year>`

### Authentication & Authorization

- [ ] Add `@cognito_required` decorators
- [ ] Add `@tenant_required` decorators
- [ ] Require `year_end_close` permission for close endpoint
- [ ] Test permission enforcement

### Error Handling

- [ ] Handle validation errors
- [ ] Handle database errors
- [ ] Return appropriate HTTP status codes
- [ ] Return user-friendly error messages

## Phase 4: Frontend UI (3-4 days)

### Main Page

- [ ] Create `frontend/src/pages/YearEndClosure.tsx`
- [ ] Load available years
- [ ] Load closed years
- [ ] Show "Close Fiscal Year" button
- [ ] Keep file under 200 lines

### Year Closure Wizard

- [ ] Create `frontend/src/components/YearClosureWizard.tsx`
- [ ] Implement step 1: Select year
- [ ] Implement step 2: Validation & confirmation
- [ ] Show validation errors/warnings
- [ ] Show net P&L result
- [ ] Show balance sheet account count
- [ ] Add notes field
- [ ] Handle close year action
- [ ] Keep file under 300 lines

### Closed Years Table

- [ ] Create `frontend/src/components/ClosedYearsTable.tsx`
- [ ] Display closed years in table
- [ ] Show closure date, user, notes
- [ ] Show status badge
- [ ] Keep file under 150 lines

### UI Polish

- [ ] Add loading spinners
- [ ] Add success/error toasts
- [ ] Add confirmation dialogs
- [ ] Responsive design
- [ ] Accessibility (ARIA labels)

## Phase 5: Testing (3-4 days)

### Backend Unit Tests

- [ ] Create `backend/tests/unit/test_year_end_service.py`
- [ ] Test `calculate_net_pl_result()`
- [ ] Test `validate_year_closure()` - success case
- [ ] Test `validate_year_closure()` - already closed
- [ ] Test `validate_year_closure()` - previous not closed
- [ ] Test `validate_year_closure()` - missing configuration
- [ ] Test `_create_closure_transaction()` - profit
- [ ] Test `_create_closure_transaction()` - loss
- [ ] Test `_create_opening_balances()`
- [ ] Test helper methods

### Backend Integration Tests

- [ ] Create `backend/tests/integration/test_year_end_integration.py`
- [ ] Test full year closure process
- [ ] Test rollback on error
- [ ] Test with multiple years
- [ ] Test idempotent behavior

### Backend API Tests

- [ ] Create `backend/tests/api/test_year_end_routes.py`
- [ ] Test GET /api/year-end/available-years
- [ ] Test POST /api/year-end/validate
- [ ] Test POST /api/year-end/close
- [ ] Test GET /api/year-end/closed-years
- [ ] Test permission enforcement
- [ ] Test error responses

### Frontend Tests

- [ ] Create `frontend/src/__tests__/YearEndClosure.test.tsx`
- [ ] Test page rendering
- [ ] Test wizard flow
- [ ] Test validation display
- [ ] Test error handling
- [ ] Test closed years table

### End-to-End Tests

- [ ] Create Playwright test for full workflow
- [ ] Test selecting year
- [ ] Test validation
- [ ] Test closing year
- [ ] Test viewing closed years

## Phase 6: Integration & Polish (2-3 days)

### Report Updates

- [ ] Update `mutaties_cache.py` to use opening balances
- [ ] Update `financial_report_generator.py` to use opening balances
- [ ] Update `xlsx_export.py` to use opening balances
- [ ] Test reports with closed years
- [ ] Verify performance improvement

### Permissions Setup

- [ ] Add `year_end_close` permission to system
- [ ] Document permission assignment
- [ ] Test with different roles
- [ ] Update permission documentation

### Documentation

- [ ] Update user documentation
- [ ] Create admin guide for configuration
- [ ] Document troubleshooting steps
- [ ] Add screenshots to docs

### Code Review

- [ ] Review all code for quality
- [ ] Check file sizes (< 500 lines target)
- [ ] Verify error handling
- [ ] Check security
- [ ] Verify test coverage

## Phase 7: Deployment (1-2 days)

### Pre-Deployment

- [ ] Run all tests on staging
- [ ] Test full workflow on staging
- [ ] Review with stakeholders
- [ ] Get approval to deploy

### Deployment

- [ ] Deploy database schema changes
- [ ] Deploy backend code
- [ ] Deploy frontend code
- [ ] Verify deployment successful

### Post-Deployment

- [ ] Monitor error logs
- [ ] Test first year closure
- [ ] Verify report performance
- [ ] Gather user feedback
- [ ] Document any issues

## Acceptance Criteria

- [ ] Users can view available years to close
- [ ] Users can validate year readiness
- [ ] Users can close fiscal years
- [ ] Users can view closed years
- [ ] Validation prevents premature closure
- [ ] Year-end closure transaction created correctly
- [ ] Opening balance transactions created correctly
- [ ] Closure status recorded in database
- [ ] Permissions enforced correctly
- [ ] All tests pass
- [ ] Reports use opening balances
- [ ] Reports run faster (10x improvement)
- [ ] UI is intuitive and responsive
- [ ] Documentation complete

## Estimated Timeline

- Phase 1: 2-3 days
- Phase 2: 3-4 days
- Phase 3: 2 days
- Phase 4: 3-4 days
- Phase 5: 3-4 days
- Phase 6: 2-3 days
- Phase 7: 1-2 days

**Total: 16-22 days**

## Dependencies

- Migration script completed (TASKS-migration.md)
- Chart of Accounts management exists
- Tenant Admin UI exists
- Permission system supports custom permissions

## Risks

- **Complex validation logic**: Mitigated by thorough testing
- **UI complexity**: Mitigated by step-by-step wizard
- **Permission confusion**: Mitigated by clear documentation
- **Report integration**: Mitigated by careful testing

## Notes

- This is an ongoing feature used repeatedly
- Focus on user experience and clear error messages
- Ensure proper audit trail
- Consider adding year-end checklist in future
- Consider adding reopen year functionality in future
