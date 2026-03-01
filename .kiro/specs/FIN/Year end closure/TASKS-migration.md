# Year-End Closure - Migration Tasks

**Status**: Not Started  
**Related**: design-migration.md, requirements.md, `.kiro/specs/FIN/README.md`  
**Purpose**: One-time historical data migration

## Overview

Generate opening balance transactions for all historical years so all years use the same calculation method.

**IMPORTANT**: Before implementing any task, read `.kiro/specs/FIN/README.md` to understand:

- Double-entry bookkeeping principles (Debet + Credit in every transaction)
- TransactionAmount format (always positive)
- VW classification ('Y' = P&L, 'N' = Balance Sheet)
- Transaction structure and reference field patterns
- Code organization guidelines (500 lines target, 1000 max)

## Phase 1: Core Migration Script (3-4 days)

### Database Schema

- [x] Add `parameters` JSON column to `rekeningschema` table
- [x] Test JSON_EXTRACT queries on MySQL 8.0
- [x] Create indexes for performance
- [x] Document schema changes

### Migration Script Structure

- [x] Create `backend/scripts/database/migrate_opening_balances.py`
- [x] Implement argument parsing (--dry-run, --tenant, --start-year, --end-year)
- [x] Setup logging (console + file)
- [x] Create main entry point

### Core Migration Class

- [x] Create `OpeningBalanceMigrator` class
- [x] Implement `migrate()` method (main entry point)
- [x] Implement `_migrate_tenant()` method
- [x] Implement `_get_tenants()` helper
- [x] Implement `_get_year_range()` helper
- [x] Implement `_is_already_migrated()` check

### Calculate Ending Balances

- [x] Implement `_calculate_ending_balances()` method
- [x] Query vw_mutaties for balance sheet accounts (VW='N')
- [x] Filter for non-zero balances
- [x] Test with sample data

### Create Opening Balance Transactions

- [x] Implement `_create_opening_balances()` method
- [x] Get interim account from configuration
- [x] Generate transaction records with proper debit/credit
- [x] Handle positive and negative balances correctly
- [x] Test transaction creation

### Account Configuration

- [x] Implement `_get_account_by_role()` helper
- [x] Test JSON parameter queries
- [x] Handle missing configuration gracefully

## Phase 2: Validation (2-3 days)

### Validation Logic

- [x] Implement `_validate_year()` method
- [x] Implement `_calculate_balance_old_method()` (from beginning of time)
- [x] Implement `_calculate_balance_new_method()` (opening balance + current year)
- [x] Compare old vs new calculations
- [x] Allow small rounding differences (0.01)
- [x] Collect validation errors

### Error Handling

- [x] Implement transaction rollback on validation failure
- [x] Log validation errors with details
- [x] Continue with next tenant on error
- [x] Generate summary report

### Dry-Run Mode

- [x] Implement dry-run flag handling
- [x] Preview changes without committing
- [x] Show what would be created
- [x] Test dry-run mode

## Phase 3: Testing (2-3 days)

### Unit Tests

- [ ] Create `backend/tests/unit/test_opening_balance_migrator.py`
- [ ] Test `_calculate_ending_balances()`
- [ ] Test `_create_opening_balances()`
- [ ] Test `_validate_year()`
- [ ] Test `_get_account_by_role()`
- [ ] Test error handling

### Integration Tests

- [ ] Create `backend/tests/integration/test_migration_integration.py`
- [ ] Test full migration for single tenant
- [ ] Test idempotent execution (can run multiple times)
- [ ] Test rollback on validation failure
- [ ] Test with multiple years

### Test Data Setup

- [ ] Create test tenant with multiple years
- [ ] Create test transactions with known balances
- [ ] Configure test account roles
- [ ] Verify test data integrity

## Phase 4: Performance & Polish (1-2 days)

### Performance Optimization

- [ ] Add database indexes
- [ ] Optimize SQL queries
- [ ] Test with large datasets (10 years, 10,000 transactions)
- [ ] Measure execution time
- [ ] Ensure < 30 seconds for typical dataset

### Logging & Reporting

- [ ] Implement detailed logging
- [ ] Create summary report
- [ ] Log validation errors clearly
- [ ] Add progress indicators
- [ ] Test log output

### Documentation

- [ ] Add usage examples to design-migration.md
- [ ] Document command-line options
- [ ] Create troubleshooting guide
- [ ] Document rollback procedure

## Phase 5: Deployment Preparation (1 day)

### Pre-Deployment Testing

- [ ] Test on staging environment
- [ ] Run with --dry-run on production data copy
- [ ] Review validation results
- [ ] Verify no errors
- [ ] Check performance

### Deployment Plan

- [ ] Document deployment steps
- [ ] Create database backup procedure
- [ ] Plan rollback strategy
- [ ] Schedule deployment window
- [ ] Notify stakeholders

### Post-Deployment

- [ ] Monitor first execution
- [ ] Verify results
- [ ] Check report performance improvement
- [ ] Archive migration logs
- [ ] Document lessons learned

## Acceptance Criteria

- [ ] Migration script runs successfully on all tenants
- [ ] No validation errors
- [ ] Execution time < 30 seconds for typical dataset
- [ ] Dry-run mode works correctly
- [ ] Idempotent (can be re-run safely)
- [ ] All tests pass
- [ ] Documentation complete
- [ ] Reports show same values before and after migration
- [ ] Reports run significantly faster (10x improvement)

## Estimated Timeline

- Phase 1: 3-4 days
- Phase 2: 2-3 days
- Phase 3: 2-3 days
- Phase 4: 1-2 days
- Phase 5: 1 day

**Total: 9-13 days**

## Dependencies

- MySQL 8.0 with JSON support
- Access to production database copy for testing
- Staging environment for testing

## Risks

- **Validation failures**: Mitigated by thorough testing and dry-run mode
- **Performance issues**: Mitigated by optimization and testing with large datasets
- **Data corruption**: Mitigated by transactions and rollback capability
- **Missing configuration**: Mitigated by validation and clear error messages

## Notes

- This is a one-time migration
- After successful migration, the script won't need to run again
- Keep the script for reference and potential future use
- Migration logs should be archived for audit trail
