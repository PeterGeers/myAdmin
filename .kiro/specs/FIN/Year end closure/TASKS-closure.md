# Year-End Closure - Feature Tasks

**Status**: Not Started  
**Related**: design-closure.md  
**Purpose**: User-facing year-end closure feature

## Overview

Build the year-end closure feature that allows users to close fiscal years, creating year-end closure and opening balance transactions.

## Phase 1: Database & Configuration (2-3 days)

### Database Schema

- [ ] Create `year_closure_status` table
- [ ] Add indexes (administration, year)
- [ ] Test table creation
- [ ] Document schema

### Account Configuration

- [ ] Ensure `parameters` JSON column exists in `rekeningschema`
- [ ] Create helper function `get_account_by_role()`
- [ ] Test JSON parameter queries
- [ ] Document configuration approach

### Configuration UI (Tenant Admin)

- [ ] Add "Role" dropdown to Chart of Accounts management
- [ ] Create Year-End Settings screen (role-centric)
- [ ] Add validation for account roles
- [ ] Test configuration UI

## Phase 2: Backend Core Logic (3-4 days)

### Service Class Structure

- [ ] Create `backend/src/services/year_end_service.py`
- [ ] Create `YearEndClosureService` class
- [ ] Implement `__init__()` with database connection
- [ ] Keep file under 500 lines

### Available Years

- [ ] Implement `get_available_years()` method
- [ ] Query years with transactions
- [ ] Exclude already closed years
- [ ] Test with sample data

### Validation Logic

- [ ] Create `backend/src/services/year_end_validator.py`
- [ ] Implement `validate_year_closure()` method
- [ ] Check if year already closed
- [ ] Check if previous year is closed
- [ ] Check required accounts configured
- [ ] Calculate net P&L result
- [ ] Count balance sheet accounts
- [ ] Return validation result object

### Calculate Net P&L Result

- [ ] Implement `_calculate_net_pl_result()` method
- [ ] Query vw_mutaties for VW='Y' accounts
- [ ] Sum amounts for the year
- [ ] Test with profit and loss scenarios

### Create Closure Transaction

- [ ] Implement `_create_closure_transaction()` method
- [ ] Get equity and P&L closing accounts
- [ ] Determine debit/credit based on profit/loss
- [ ] Insert transaction into mutaties table
- [ ] Return transaction ID
- [ ] Test with profit and loss scenarios

### Create Opening Balances

- [ ] Implement `_create_opening_balances()` method
- [ ] Get ending balances from previous year
- [ ] Get interim account from configuration
- [ ] Create transaction records with proper debit/credit
- [ ] Return list of transaction IDs
- [ ] Test with sample balances

### Close Year Method

- [ ] Implement `close_year()` method
- [ ] Validate year can be closed
- [ ] Create closure transaction
- [ ] Create opening balances
- [ ] Record closure status
- [ ] Use database transaction (rollback on error)
- [ ] Return success result

### Helper Methods

- [ ] Implement `_get_ending_balances()`
- [ ] Implement `_is_year_closed()`
- [ ] Implement `_get_first_year()`
- [ ] Implement `_count_balance_sheet_accounts()`
- [ ] Implement `_record_closure_status()`

### Query Methods

- [ ] Implement `get_closed_years()`
- [ ] Implement `get_year_status()`
- [ ] Test all query methods

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
