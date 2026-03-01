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

### Basic Usage

#### Dry Run (Preview Changes)

Always start with a dry run to preview what will happen:

```bash
cd backend
source .venv/bin/activate  # Activate virtual environment
python scripts/database/migrate_opening_balances.py --dry-run
```

**Output**:

```
============================================================
Opening Balance Migration
============================================================
Mode: DRY RUN
Tenant: ALL
Start Year: AUTO
End Year: AUTO

Processing 3 tenant(s)

Processing tenant: GoodwinSolutions
  Years to process: 1995 to 2024
    Processing year 1995...
    Found 45 accounts with balances
    DRY RUN: Would create 45 opening balance transactions
    ✓ Year 1995 completed and validated
    ...
  ✓ Completed GoodwinSolutions

============================================================
Migration Summary
============================================================
Tenants processed: 3
Tenants failed: 0
Years processed: 57
Transactions created: 615
Validation errors: 0
============================================================
```

#### Full Migration (All Tenants)

After verifying dry run results:

```bash
python scripts/database/migrate_opening_balances.py
```

This will:

- Process all tenants
- Create opening balance transactions
- Validate all calculations
- Commit changes to database

### Advanced Usage

#### Migrate Specific Tenant

Process only one tenant (useful for testing or incremental migration):

```bash
python scripts/database/migrate_opening_balances.py --tenant "GoodwinSolutions"
```

#### Migrate Specific Year Range

Process only specific years:

```bash
# Process years 2020-2023 only
python scripts/database/migrate_opening_balances.py --start-year 2020 --end-year 2023

# Process from 2020 onwards
python scripts/database/migrate_opening_balances.py --start-year 2020

# Process up to 2023
python scripts/database/migrate_opening_balances.py --end-year 2023
```

#### Verbose Logging

Enable detailed debug logging:

```bash
python scripts/database/migrate_opening_balances.py --verbose
```

#### Custom Log File

Specify custom log file location:

```bash
python scripts/database/migrate_opening_balances.py --log-file /path/to/migration.log
```

#### Combined Options

Combine multiple options:

```bash
# Dry run for specific tenant with verbose logging
python scripts/database/migrate_opening_balances.py \
  --dry-run \
  --tenant "GoodwinSolutions" \
  --start-year 2020 \
  --verbose \
  --log-file test_migration.log
```

### Production Deployment Example

Complete production deployment workflow:

```bash
# 1. Backup database first
mysqldump -u peter -p myAdmin > backup_before_migration_$(date +%Y%m%d).sql

# 2. Activate virtual environment
cd backend
source .venv/bin/activate

# 3. Dry run to preview
python scripts/database/migrate_opening_balances.py --dry-run

# 4. Review output carefully
# Check for any errors or warnings

# 5. Run actual migration
python scripts/database/migrate_opening_balances.py

# 6. Verify results
# Check log file in backend/logs/migration_YYYYMMDD_HHMMSS.log
# Verify transaction counts match dry run

# 7. Test reports
# Run some reports to verify they show correct values
```

## Command-Line Options Reference

### Required Options

None - all options are optional with sensible defaults.

### Optional Arguments

| Option              | Type    | Default              | Description                                                                                |
| ------------------- | ------- | -------------------- | ------------------------------------------------------------------------------------------ |
| `--dry-run`         | flag    | false                | Preview changes without committing to database. Use this first to verify what will happen. |
| `--tenant TENANT`   | string  | all tenants          | Process only the specified tenant. Useful for testing or incremental migration.            |
| `--start-year YEAR` | integer | first year with data | Start processing from this year. Earlier years will be skipped.                            |
| `--end-year YEAR`   | integer | current year - 1     | Stop processing at this year. Later years will be skipped.                                 |
| `--verbose`         | flag    | false                | Enable verbose debug logging. Shows detailed information about each step.                  |
| `--log-file FILE`   | string  | auto-generated       | Custom log file path. Default: `logs/migration_YYYYMMDD_HHMMSS.log`                        |

### Exit Codes

| Code | Meaning                                                            |
| ---- | ------------------------------------------------------------------ |
| 0    | Success - all tenants migrated successfully                        |
| 1    | Failure - one or more tenants failed or validation errors occurred |

### Examples by Use Case

**Testing on staging**:

```bash
python scripts/database/migrate_opening_balances.py --dry-run --verbose
```

**Migrate one tenant at a time**:

```bash
python scripts/database/migrate_opening_balances.py --tenant "Tenant1"
python scripts/database/migrate_opening_balances.py --tenant "Tenant2"
```

**Re-run for new years only**:

```bash
# If you already migrated up to 2023, now migrate 2024
python scripts/database/migrate_opening_balances.py --start-year 2024
```

**Troubleshooting specific year**:

```bash
python scripts/database/migrate_opening_balances.py \
  --tenant "ProblemTenant" \
  --start-year 2020 \
  --end-year 2020 \
  --verbose
```

## Troubleshooting Guide

### Common Issues and Solutions

#### Issue: "No tenants found to process"

**Symptoms**:

```
No tenants found to process
```

**Causes**:

- Specified tenant name doesn't exist
- No data in mutaties table
- Database connection issue

**Solutions**:

1. Check tenant name spelling (case-sensitive)
2. Verify tenant exists:
   ```sql
   SELECT DISTINCT administration FROM mutaties;
   ```
3. Check database connection in `.env` file

#### Issue: "Interim account not configured"

**Symptoms**:

```
Interim account not configured for [tenant]
```

**Causes**:

- Account 2001 not configured with `interim_opening_balance` role
- Missing parameters column in rekeningschema table

**Solutions**:

1. Configure interim account:
   ```sql
   UPDATE rekeningschema
   SET parameters = JSON_OBJECT('roles', JSON_ARRAY('interim_opening_balance'))
   WHERE Account = '2001'
   AND administration = '[tenant]';
   ```
2. Verify configuration:
   ```sql
   SELECT Account, parameters
   FROM rekeningschema
   WHERE administration = '[tenant]'
   AND JSON_CONTAINS(parameters->'$.roles', '"interim_opening_balance"');
   ```

#### Issue: "Validation failed"

**Symptoms**:

```
VALIDATION FAILED: Account 1000 old=5000.00 new=5001.50
```

**Causes**:

- Data inconsistency in vw_mutaties view
- Rounding errors exceeding tolerance (0.01)
- Missing transactions in current year

**Solutions**:

1. Check for data issues:
   ```sql
   -- Verify vw_mutaties view is correct
   SELECT * FROM vw_mutaties
   WHERE administration = '[tenant]'
   AND Reknum = '1000'
   AND jaar = [year]
   ORDER BY TransactionDate;
   ```
2. Check if difference is just rounding:
   - If difference < 0.01, it's within tolerance
   - If difference > 0.01, investigate data
3. Verify opening balance transaction was created correctly:
   ```sql
   SELECT * FROM mutaties
   WHERE administration = '[tenant]'
   AND TransactionNumber = 'OpeningBalance [year]';
   ```

#### Issue: "Year already migrated"

**Symptoms**:

```
Year 2023 already migrated
```

**Causes**:

- Migration was already run for this year
- Opening balance transactions already exist

**Solutions**:

1. This is normal - migration is idempotent
2. To re-run migration, first delete existing opening balances:
   ```sql
   DELETE FROM mutaties
   WHERE administration = '[tenant]'
   AND TransactionNumber LIKE 'OpeningBalance%';
   ```
3. Then run migration again

#### Issue: "Performance is slow"

**Symptoms**:

- Migration takes > 30 seconds
- Database queries are slow

**Causes**:

- Missing database indexes
- Large dataset (> 100K transactions)
- Database server resource constraints

**Solutions**:

1. Check indexes exist:
   ```sql
   SHOW INDEX FROM mutaties;
   SHOW INDEX FROM rekeningschema;
   ```
2. Add missing indexes:
   ```sql
   CREATE INDEX idx_mutaties_admin_date ON mutaties(administration, TransactionDate);
   CREATE INDEX idx_mutaties_admin_number ON mutaties(administration, TransactionNumber);
   CREATE INDEX idx_parameters_roles ON rekeningschema((CAST(parameters->'$.roles' AS CHAR(255))));
   ```
3. Optimize database:
   ```sql
   ANALYZE TABLE mutaties;
   ANALYZE TABLE rekeningschema;
   ```

#### Issue: "Database connection lost"

**Symptoms**:

```
Error processing [tenant]: Lost connection to MySQL server
```

**Causes**:

- Long-running transaction timeout
- Network issue
- Database server restart

**Solutions**:

1. Increase MySQL timeout:
   ```sql
   SET GLOBAL wait_timeout = 600;
   SET GLOBAL interactive_timeout = 600;
   ```
2. Process tenants one at a time:
   ```bash
   python scripts/database/migrate_opening_balances.py --tenant "Tenant1"
   ```
3. Check database server logs for issues

#### Issue: "Permission denied"

**Symptoms**:

```
Access denied for user 'peter'@'localhost'
```

**Causes**:

- Insufficient database permissions
- Wrong credentials in `.env` file

**Solutions**:

1. Verify credentials in `backend/.env`:
   ```
   DB_USER=peter
   DB_PASSWORD=[correct_password]
   ```
2. Check user permissions:
   ```sql
   SHOW GRANTS FOR 'peter'@'localhost';
   ```
3. Grant necessary permissions:
   ```sql
   GRANT SELECT, INSERT, UPDATE ON myAdmin.* TO 'peter'@'localhost';
   ```

### Debugging Tips

#### Enable Verbose Logging

```bash
python scripts/database/migrate_opening_balances.py --verbose --dry-run
```

This shows:

- Each SQL query executed
- Number of rows affected
- Detailed balance calculations
- Validation comparisons

#### Check Log Files

Log files are created in `backend/logs/`:

```bash
# View latest log
ls -lt backend/logs/migration_*.log | head -1

# Tail log in real-time
tail -f backend/logs/migration_20260301_143022.log

# Search for errors
grep ERROR backend/logs/migration_*.log
```

#### Manual Validation

Verify calculations manually:

```sql
-- Old method: sum from beginning of time
SELECT Reknum, SUM(Amount) as balance
FROM vw_mutaties
WHERE administration = 'GoodwinSolutions'
AND VW = 'N'
AND TransactionDate <= '2023-12-31'
GROUP BY Reknum
HAVING ABS(SUM(Amount)) > 0.01;

-- New method: opening balance + current year
SELECT Reknum, SUM(Amount) as balance
FROM vw_mutaties
WHERE administration = 'GoodwinSolutions'
AND VW = 'N'
AND TransactionDate >= '2023-01-01'
AND TransactionDate <= '2023-12-31'
GROUP BY Reknum
HAVING ABS(SUM(Amount)) > 0.01;
```

#### Test with Single Year

Isolate issues by testing one year:

```bash
python scripts/database/migrate_opening_balances.py \
  --tenant "GoodwinSolutions" \
  --start-year 2023 \
  --end-year 2023 \
  --verbose \
  --dry-run
```

### Getting Help

If issues persist:

1. **Check logs**: Review `backend/logs/migration_*.log`
2. **Verify data**: Run manual SQL queries to check data integrity
3. **Test on staging**: Try migration on staging environment first
4. **Contact support**: Provide log files and error messages

## Rollback Procedures

### When to Rollback

Rollback if:

- Validation errors occur
- Incorrect balances detected
- Performance issues arise
- Data corruption suspected

### Automatic Rollback

The migration script includes automatic rollback:

- Each tenant is processed in a transaction
- If validation fails, tenant is automatically rolled back
- Other tenants continue processing
- No manual intervention needed

### Manual Rollback

If you need to manually rollback after successful migration:

#### Option 1: Delete Opening Balance Transactions

Remove only the opening balance transactions:

```sql
-- Preview what will be deleted
SELECT
    administration,
    TransactionNumber,
    COUNT(*) as transaction_count
FROM mutaties
WHERE TransactionNumber LIKE 'OpeningBalance%'
GROUP BY administration, TransactionNumber
ORDER BY administration, TransactionNumber;

-- Delete opening balance transactions
DELETE FROM mutaties
WHERE TransactionNumber LIKE 'OpeningBalance%';

-- Verify deletion
SELECT COUNT(*) FROM mutaties
WHERE TransactionNumber LIKE 'OpeningBalance%';
-- Should return 0
```

#### Option 2: Restore from Backup

If you have a database backup from before migration:

```bash
# Stop application
docker-compose down

# Restore database
mysql -u peter -p myAdmin < backup_before_migration_20260301.sql

# Restart application
docker-compose up -d

# Verify restoration
mysql -u peter -p myAdmin -e "
  SELECT COUNT(*) as opening_balance_count
  FROM mutaties
  WHERE TransactionNumber LIKE 'OpeningBalance%';
"
# Should return 0 if backup was from before migration
```

#### Option 3: Selective Rollback (Specific Tenant)

Rollback only one tenant:

```sql
-- Preview
SELECT
    TransactionNumber,
    COUNT(*) as count
FROM mutaties
WHERE administration = 'GoodwinSolutions'
AND TransactionNumber LIKE 'OpeningBalance%'
GROUP BY TransactionNumber;

-- Delete
DELETE FROM mutaties
WHERE administration = 'GoodwinSolutions'
AND TransactionNumber LIKE 'OpeningBalance%';
```

#### Option 4: Selective Rollback (Specific Year)

Rollback only specific years:

```sql
-- Preview
SELECT
    administration,
    TransactionNumber,
    COUNT(*) as count
FROM mutaties
WHERE TransactionNumber IN ('OpeningBalance 2023', 'OpeningBalance 2024')
GROUP BY administration, TransactionNumber;

-- Delete
DELETE FROM mutaties
WHERE TransactionNumber IN ('OpeningBalance 2023', 'OpeningBalance 2024');
```

### Post-Rollback Steps

After rollback:

1. **Verify rollback**:

   ```sql
   -- Check opening balance transactions are gone
   SELECT COUNT(*) FROM mutaties
   WHERE TransactionNumber LIKE 'OpeningBalance%';
   ```

2. **Test reports**:
   - Run reports to verify they still work
   - Check that values match pre-migration state

3. **Investigate issue**:
   - Review migration logs
   - Identify root cause
   - Fix migration script if needed

4. **Re-test on staging**:
   - Test fixed migration on staging
   - Verify no issues

5. **Re-run migration**:
   - Run migration again with fixes
   - Monitor closely

### Rollback Checklist

Before rollback:

- [ ] Document reason for rollback
- [ ] Save migration logs for analysis
- [ ] Notify stakeholders
- [ ] Create new database backup (current state)

During rollback:

- [ ] Stop application (optional, for safety)
- [ ] Execute rollback SQL or restore backup
- [ ] Verify rollback completed successfully

After rollback:

- [ ] Restart application (if stopped)
- [ ] Test reports and functionality
- [ ] Investigate root cause
- [ ] Plan re-migration

### Emergency Rollback

If critical issues arise in production:

```bash
# 1. IMMEDIATE: Stop application
docker-compose down

# 2. IMMEDIATE: Restore from backup
mysql -u peter -p myAdmin < backup_before_migration.sql

# 3. IMMEDIATE: Restart application
docker-compose up -d

# 4. Verify system is working
# Test critical reports and functionality

# 5. Investigate issue offline
# Review logs, identify problem, fix code

# 6. Test fix on staging before re-deploying
```

### Preventing Need for Rollback

Best practices to avoid rollback:

1. **Always dry-run first**:

   ```bash
   python scripts/database/migrate_opening_balances.py --dry-run
   ```

2. **Test on staging**:
   - Use copy of production data
   - Verify results thoroughly

3. **Backup before migration**:

   ```bash
   mysqldump -u peter -p myAdmin > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

4. **Migrate incrementally**:

   ```bash
   # One tenant at a time
   python scripts/database/migrate_opening_balances.py --tenant "Tenant1"
   # Verify results
   python scripts/database/migrate_opening_balances.py --tenant "Tenant2"
   ```

5. **Monitor during migration**:
   - Watch logs in real-time
   - Check for errors immediately
   - Stop if issues arise

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
