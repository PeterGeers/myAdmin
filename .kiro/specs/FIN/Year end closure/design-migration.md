# Year-End Closure - Historical Data Migration Design

**Status**: Draft  
**Related**: requirements.md (Task 1: Fix Historical Data)  
**Purpose**: One-time migration to generate opening balances for all historical years

## Overview

This design covers the one-time migration script that generates opening balance transactions for all historical years. After this migration, all years will use the same calculation method (opening balances + current year transactions) instead of querying from the beginning of time.

## Goals

1. Generate opening balance transactions for all historical years
2. Validate that new calculations match old calculations
3. Provide dry-run mode for testing
4. Ensure idempotent execution (can be re-run safely)
5. Complete migration in reasonable time (< 10 seconds for 10 years)

## Architecture

### Migration Script Location

```
backend/scripts/database/migrate_opening_balances.py
```

### Execution Context

- Run manually by system administrator
- Can be run in dry-run mode first
- Logs all actions for audit trail
- Transactional: all-or-nothing per tenant

### High-Level Flow

```
1. Get list of all tenants
2. For each tenant:
   a. Get list of years with transactions
   b. Identify first year (Year 0)
   c. For each subsequent year (Year 1, 2, 3...):
      - Calculate ending balance as of Dec 31 previous year
      - Generate opening balance transactions for Jan 1 current year
      - Validate calculations
   d. Commit or rollback based on validation
3. Generate summary report
```

## Detailed Design

### 1. Script Entry Point

```python
# backend/scripts/database/migrate_opening_balances.py

import argparse
from database import DatabaseManager
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(
        description='Generate opening balance transactions for historical years'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without applying them'
    )
    parser.add_argument(
        '--tenant',
        type=str,
        help='Process specific tenant only (default: all tenants)'
    )
    parser.add_argument(
        '--start-year',
        type=int,
        help='Start from specific year (default: first year with transactions)'
    )
    parser.add_argument(
        '--end-year',
        type=int,
        help='End at specific year (default: current year - 1)'
    )

    args = parser.parse_args()

    migrator = OpeningBalanceMigrator(
        dry_run=args.dry_run,
        test_mode=False
    )

    migrator.migrate(
        tenant=args.tenant,
        start_year=args.start_year,
        end_year=args.end_year
    )

if __name__ == '__main__':
    main()
```

### 2. Migration Class

```python
class OpeningBalanceMigrator:
    def __init__(self, dry_run=False, test_mode=False):
        self.dry_run = dry_run
        self.db = DatabaseManager(test_mode=test_mode)
        self.logger = self._setup_logger()
        self.validation_errors = []

    def migrate(self, tenant=None, start_year=None, end_year=None):
        """Main migration entry point"""
        self.logger.info(f"Starting migration (dry_run={self.dry_run})")

        # Get list of tenants to process
        tenants = self._get_tenants(tenant)

        summary = {
            'total_tenants': len(tenants),
            'successful': 0,
            'failed': 0,
            'transactions_created': 0
        }

        for tenant_name in tenants:
            try:
                result = self._migrate_tenant(
                    tenant_name,
                    start_year,
                    end_year
                )
                summary['successful'] += 1
                summary['transactions_created'] += result['transactions_created']

            except Exception as e:
                self.logger.error(f"Failed to migrate {tenant_name}: {e}")
                summary['failed'] += 1

        self._print_summary(summary)

        return summary

    def _migrate_tenant(self, tenant, start_year, end_year):
        """Migrate one tenant"""
        self.logger.info(f"Processing tenant: {tenant}")

        # Get year range
        years = self._get_year_range(tenant, start_year, end_year)

        if len(years) < 2:
            self.logger.info(f"Tenant {tenant} has < 2 years, skipping")
            return {'transactions_created': 0}

        # Check if already migrated
        if self._is_already_migrated(tenant, years[1]):
            self.logger.info(f"Tenant {tenant} already migrated, skipping")
            return {'transactions_created': 0}

        transactions_created = 0

        # Start transaction
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Process each year (starting from second year)
            for year in years[1:]:
                self.logger.info(f"  Processing year {year}")

                # Calculate ending balance of previous year
                ending_balances = self._calculate_ending_balances(
                    tenant,
                    year - 1,
                    cursor
                )

                # Generate opening balance transactions
                transaction_count = self._create_opening_balances(
                    tenant,
                    year,
                    ending_balances,
                    cursor
                )

                transactions_created += transaction_count

                # Validate
                if not self._validate_year(tenant, year, cursor):
                    raise Exception(f"Validation failed for year {year}")

            if self.dry_run:
                self.logger.info("DRY RUN: Rolling back changes")
                conn.rollback()
            else:
                self.logger.info("Committing changes")
                conn.commit()

            return {'transactions_created': transactions_created}

        except Exception as e:
            self.logger.error(f"Error processing {tenant}: {e}")
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()
```

### 3. Calculate Ending Balances

```python
def _calculate_ending_balances(self, tenant, year, cursor):
    """
    Calculate ending balances for all balance sheet accounts
    as of December 31st of the given year
    """
    query = """
        SELECT
            Reknum,
            AccountName,
            SUM(Amount) as balance
        FROM vw_mutaties
        WHERE VW='N'
        AND TransactionDate <= %s
        AND administration = %s
        GROUP BY Reknum, AccountName
        HAVING SUM(Amount) <> 0
        ORDER BY Reknum
    """

    end_date = f"{year}-12-31"
    cursor.execute(query, [end_date, tenant])

    balances = []
    for row in cursor.fetchall():
        balances.append({
            'account': row['Reknum'],
            'account_name': row['AccountName'],
            'balance': float(row['balance'])
        })

    self.logger.info(f"    Found {len(balances)} accounts with non-zero balances")

    return balances
```

### 4. Create Opening Balance Transactions

```python
def _create_opening_balances(self, tenant, year, ending_balances, cursor):
    """
    Create opening balance transactions for the given year
    """
    if not ending_balances:
        self.logger.info(f"    No opening balances needed for {year}")
        return 0

    # Get interim account from configuration
    interim_account = self._get_account_by_role(tenant, 'interim_opening_balance')
    if not interim_account:
        raise Exception(f"Interim account not configured for {tenant}")

    transaction_number = f"OpeningBalance {year}"
    transaction_date = f"{year}-01-01"
    description = f"Opening balance for year {year} of Administration {tenant}"

    insert_query = """
        INSERT INTO mutaties (
            TransactionNumber,
            TransactionDate,
            TransactionDescription,
            TransactionAmount,
            Debet,
            Credit,
            ReferenceNumber,
            administration
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    transaction_count = 0

    for balance_info in ending_balances:
        account = balance_info['account']
        balance = balance_info['balance']

        # Determine debit and credit based on balance sign
        if balance > 0:
            # Positive balance (debit balance)
            debet = account
            credit = interim_account
            amount = balance
        else:
            # Negative balance (credit balance)
            debet = interim_account
            credit = account
            amount = abs(balance)

        cursor.execute(insert_query, [
            transaction_number,
            transaction_date,
            description,
            amount,
            debet,
            credit,
            transaction_number,
            tenant
        ])

        transaction_count += 1

    self.logger.info(f"    Created {transaction_count} opening balance transactions")

    return transaction_count
```

### 5. Validation

```python
def _validate_year(self, tenant, year, cursor):
    """
    Validate that opening balances are correct by comparing
    old calculation method vs new calculation method
    """
    self.logger.info(f"    Validating year {year}")

    # Get all balance sheet accounts
    query = """
        SELECT DISTINCT Reknum
        FROM vw_mutaties
        WHERE VW='N'
        AND administration = %s
        AND jaar <= %s
    """
    cursor.execute(query, [tenant, year])
    accounts = [row['Reknum'] for row in cursor.fetchall()]

    validation_passed = True

    for account in accounts:
        # Old method: sum from beginning of time
        old_balance = self._calculate_balance_old_method(
            tenant, account, year, cursor
        )

        # New method: opening balance + current year
        new_balance = self._calculate_balance_new_method(
            tenant, account, year, cursor
        )

        # Compare (allow small rounding differences)
        if abs(old_balance - new_balance) > 0.01:
            self.logger.error(
                f"    VALIDATION FAILED: Account {account} "
                f"old={old_balance:.2f} new={new_balance:.2f}"
            )
            validation_passed = False
            self.validation_errors.append({
                'tenant': tenant,
                'year': year,
                'account': account,
                'old_balance': old_balance,
                'new_balance': new_balance
            })

    if validation_passed:
        self.logger.info(f"    Validation passed for year {year}")

    return validation_passed

def _calculate_balance_old_method(self, tenant, account, year, cursor):
    """Calculate balance using old method (from beginning of time)"""
    query = """
        SELECT COALESCE(SUM(Amount), 0) as balance
        FROM vw_mutaties
        WHERE Reknum = %s
        AND administration = %s
        AND TransactionDate <= %s
    """
    end_date = f"{year}-12-31"
    cursor.execute(query, [account, tenant, end_date])
    return float(cursor.fetchone()['balance'])

def _calculate_balance_new_method(self, tenant, account, year, cursor):
    """Calculate balance using new method (opening balance + current year)"""
    query = """
        SELECT COALESCE(SUM(Amount), 0) as balance
        FROM vw_mutaties
        WHERE Reknum = %s
        AND administration = %s
        AND jaar = %s
    """
    cursor.execute(query, [account, tenant, year])
    return float(cursor.fetchone()['balance'])
```

### 6. Helper Methods

```python
def _get_tenants(self, tenant_filter=None):
    """Get list of tenants to process"""
    if tenant_filter:
        return [tenant_filter]

    query = "SELECT DISTINCT administration FROM vw_mutaties ORDER BY administration"
    result = self.db.execute_query(query)
    return [row['administration'] for row in result]

def _get_year_range(self, tenant, start_year=None, end_year=None):
    """Get range of years with transactions for tenant"""
    query = """
        SELECT DISTINCT jaar
        FROM vw_mutaties
        WHERE administration = %s
        AND jaar IS NOT NULL
        ORDER BY jaar
    """
    result = self.db.execute_query(query, [tenant])
    years = [row['jaar'] for row in result]

    if start_year:
        years = [y for y in years if y >= start_year]
    if end_year:
        years = [y for y in years if y <= end_year]

    return years

def _is_already_migrated(self, tenant, year):
    """Check if opening balances already exist for this year"""
    query = """
        SELECT COUNT(*) as count
        FROM mutaties
        WHERE administration = %s
        AND TransactionNumber = %s
    """
    transaction_number = f"OpeningBalance {year}"
    result = self.db.execute_query(query, [tenant, transaction_number])
    return result[0]['count'] > 0

def _get_account_by_role(self, tenant, role):
    """Get account code by parameter role"""
    query = """
        SELECT Reknum
        FROM rekeningschema
        WHERE administration = %s
        AND JSON_EXTRACT(parameters, '$.role') = %s
    """
    result = self.db.execute_query(query, [tenant, role])
    return result[0]['Reknum'] if result else None

def _setup_logger(self):
    """Setup logging"""
    import logging
    logger = logging.getLogger('OpeningBalanceMigrator')
    logger.setLevel(logging.INFO)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler
    fh = logging.FileHandler(f'migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger

def _print_summary(self, summary):
    """Print migration summary"""
    self.logger.info("=" * 60)
    self.logger.info("MIGRATION SUMMARY")
    self.logger.info("=" * 60)
    self.logger.info(f"Total tenants: {summary['total_tenants']}")
    self.logger.info(f"Successful: {summary['successful']}")
    self.logger.info(f"Failed: {summary['failed']}")
    self.logger.info(f"Transactions created: {summary['transactions_created']}")

    if self.validation_errors:
        self.logger.error(f"\nValidation errors: {len(self.validation_errors)}")
        for error in self.validation_errors:
            self.logger.error(
                f"  {error['tenant']} {error['year']} {error['account']}: "
                f"old={error['old_balance']:.2f} new={error['new_balance']:.2f}"
            )

    self.logger.info("=" * 60)
```

## Usage Examples

### Dry Run (Preview Changes)

```bash
cd backend
python scripts/database/migrate_opening_balances.py --dry-run
```

### Migrate Specific Tenant

```bash
python scripts/database/migrate_opening_balances.py --tenant GoodwinSolutions
```

### Migrate Specific Year Range

```bash
python scripts/database/migrate_opening_balances.py --start-year 2020 --end-year 2023
```

### Full Migration

```bash
python scripts/database/migrate_opening_balances.py
```

## Testing Strategy

### Unit Tests

```python
# backend/tests/unit/test_opening_balance_migrator.py

def test_calculate_ending_balances():
    """Test ending balance calculation"""
    # Setup test data
    # Run calculation
    # Assert correct balances

def test_create_opening_balances():
    """Test opening balance transaction creation"""
    # Setup test data
    # Create opening balances
    # Assert correct transactions created

def test_validation():
    """Test validation logic"""
    # Setup test data with known balances
    # Run validation
    # Assert validation passes
```

### Integration Tests

```python
def test_full_migration_single_tenant():
    """Test complete migration for one tenant"""
    # Setup test tenant with multiple years
    # Run migration
    # Validate all years
    # Assert success

def test_idempotent_execution():
    """Test that migration can be run multiple times safely"""
    # Run migration once
    # Run migration again
    # Assert no duplicate transactions created
```

## Performance Considerations

### Optimization Strategies

1. **Batch Processing**: Process transactions in batches
2. **Indexing**: Ensure proper indexes on:
   - `vw_mutaties(administration, jaar, VW, TransactionDate)`
   - `mutaties(administration, TransactionNumber)`
   - `rekeningschema(administration, parameters)`
3. **Connection Pooling**: Reuse database connections
4. **Parallel Processing**: Process tenants in parallel (optional)

### Expected Performance

- **Single tenant, single year**: < 1 second
- **Single tenant, 10 years**: < 5 seconds
- **10 tenants, 10 years each**: < 30 seconds

## Error Handling

### Recoverable Errors

- Missing configuration: Log warning, skip tenant
- No transactions for year: Log info, skip year
- Already migrated: Log info, skip tenant

### Fatal Errors

- Database connection failure: Abort migration
- Validation failure: Rollback tenant, continue with next
- Invalid data: Rollback tenant, log error

### Rollback Strategy

- Each tenant is processed in its own transaction
- If any year fails validation, entire tenant is rolled back
- Other tenants continue processing
- Summary report shows which tenants failed

## Deployment Plan

### Pre-Deployment

1. **Backup database**: Full backup before migration
2. **Test on staging**: Run migration on staging environment
3. **Review logs**: Verify no validation errors
4. **Performance test**: Ensure migration completes in reasonable time

### Deployment Steps

1. **Deploy code**: Deploy migration script to production
2. **Dry run**: Run with `--dry-run` flag to preview
3. **Review output**: Check for any issues
4. **Execute migration**: Run without dry-run flag
5. **Verify results**: Check logs and validation
6. **Update reports**: Deploy updated report queries that use opening balances

### Post-Deployment

1. **Monitor performance**: Verify reports are faster
2. **Spot check**: Manually verify some balance calculations
3. **Archive logs**: Save migration logs for audit trail

## Rollback Plan

If migration fails or produces incorrect results:

1. **Restore database**: Restore from pre-migration backup
2. **Investigate**: Review logs to identify issue
3. **Fix code**: Correct migration script
4. **Re-test**: Test on staging again
5. **Re-deploy**: Deploy fixed version

## Success Criteria

- All tenants migrated successfully
- No validation errors
- Migration completes in < 30 seconds for typical dataset
- Reports show same values before and after migration
- Reports run significantly faster (10x improvement)

## Related Files

- `requirements.md` - Overall requirements
- `design-closure.md` - Year-end closure feature design
- `backend/scripts/database/migrate_opening_balances.py` - Migration script
- `backend/tests/unit/test_opening_balance_migrator.py` - Unit tests

## Code Organization Guidelines

### File Size Limits

**Target: 500 lines | Maximum: 1000 lines**

To maintain code quality and readability:

- **Target 500 lines**: Aim for this in new code
- **Maximum 1000 lines**: Absolute limit - files exceeding this require refactoring
- **500-1000 lines**: Acceptable for complex logic, but consider splitting

### Suggested File Structure

If `migrate_opening_balances.py` exceeds 500 lines, split into:

```
backend/scripts/database/
├── migrate_opening_balances.py (main entry point, ~200 lines)
├── opening_balance_migrator.py (core class, ~400 lines)
└── opening_balance_validator.py (validation logic, ~300 lines)
```

**Example split**:

```python
# migrate_opening_balances.py (main entry point)
from opening_balance_migrator import OpeningBalanceMigrator

def main():
    # Argument parsing
    # Call migrator
    pass

# opening_balance_migrator.py (core logic)
class OpeningBalanceMigrator:
    # Migration logic
    # Transaction creation
    pass

# opening_balance_validator.py (validation)
class OpeningBalanceValidator:
    # Validation logic
    # Comparison methods
    pass
```

This keeps each file focused and maintainable.
