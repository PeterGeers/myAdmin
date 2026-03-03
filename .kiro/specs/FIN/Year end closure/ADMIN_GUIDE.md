# Year-End Closure Admin Guide

## Overview

This guide is for system administrators who need to configure, maintain, and troubleshoot the year-end closure feature. It covers database schema, configuration, bulk operations, and advanced troubleshooting.

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Initial Configuration](#initial-configuration)
3. [Database Schema](#database-schema)
4. [Bulk Operations](#bulk-operations)
5. [Troubleshooting](#troubleshooting)
6. [Maintenance](#maintenance)
7. [Performance Optimization](#performance-optimization)

---

## System Requirements

### Backend Requirements

- Python 3.8+
- MySQL 8.0+
- Flask 2.3.3+
- Required Python packages (see `requirements.txt`)

### Frontend Requirements

- React 19.2.0+
- Node.js 16+
- TypeScript 4.9.5+

### Database Requirements

- MySQL 8.0+ with InnoDB engine
- Sufficient storage for historical transactions
- Proper indexes on mutaties table

### Permissions

- Database user needs: SELECT, INSERT, UPDATE, DELETE on mutaties and year_closure_status tables
- Application user needs: `finance_write` permission (Finance_CRUD role)
- Tenant admin needs: `Tenant_Admin` role for configuration

---

## Initial Configuration

### 1. Database Setup

The year-end closure feature requires the `year_closure_status` table:

```sql
CREATE TABLE IF NOT EXISTS year_closure_status (
    id INT AUTO_INCREMENT PRIMARY KEY,
    administration VARCHAR(100) NOT NULL,
    year INT NOT NULL,
    closed_date DATETIME NOT NULL,
    closed_by VARCHAR(255) NOT NULL,
    closure_transaction_number VARCHAR(50),
    opening_balance_transaction_number VARCHAR(50),
    notes TEXT,
    UNIQUE KEY unique_admin_year (administration, year),
    INDEX idx_administration (administration),
    INDEX idx_year (year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 2. Account Configuration

Each tenant must configure 2 required accounts in **Tenant Admin > Year-End Settings**:

#### Equity Result Account (VW=N)

- **Purpose**: Records net P&L result and balances opening balance entries
- **Example**: 3080 - Resultaatrekening
- **VW Classification**: N (Balance Sheet)

#### P&L Closing Account (VW=Y)

- **Purpose**: Temporary account used in year-end closure transaction
- **Example**: 8099 - Afsluitrekening
- **VW Classification**: Y (P&L)

### 3. Configuration Steps

1. Navigate to **Tenant Admin > Year-End Settings**
2. Select equity result account (VW=N)
3. Select P&L closing account (VW=Y)
4. Click **Save Configuration**
5. Verify configuration shows "Complete" status

### 4. Verify Configuration

Run the verification script:

```bash
cd backend
python scripts/check_year_end_setup.py
```

Expected output:

```
✅ Configuration valid
✅ All required accounts configured
✅ Ready for year-end closure
```

---

## Database Schema

### Tables

#### mutaties (Transactions)

```sql
-- Key fields for year-end closure
TransactionNumber VARCHAR(50)      -- e.g., "YearClose 2025", "OpeningBalance 2026"
TransactionDate DATE               -- Year-end: YYYY-12-31, Opening: YYYY-01-01
TransactionDescription TEXT        -- Description of transaction
TransactionAmount DECIMAL(15,2)    -- Always positive
Debet VARCHAR(10)                  -- Debit account
Credit VARCHAR(10)                 -- Credit account
ReferenceNumber VARCHAR(50)        -- "Year Closure" or "Opening Balance"
administration VARCHAR(100)        -- Tenant identifier
```

#### year_closure_status (Closure Tracking)

```sql
id INT AUTO_INCREMENT PRIMARY KEY
administration VARCHAR(100)                    -- Tenant identifier
year INT                                       -- Year that was closed
closed_date DATETIME                           -- When closure occurred
closed_by VARCHAR(255)                         -- User who closed it
closure_transaction_number VARCHAR(50)         -- "YearClose YYYY"
opening_balance_transaction_number VARCHAR(50) -- "OpeningBalance YYYY+1"
notes TEXT                                     -- Optional closure notes
```

#### rekeningschema (Chart of Accounts)

```sql
-- Account configuration uses JSON parameters field
Account VARCHAR(10)                -- Account code
AccountName VARCHAR(255)           -- Account name
VW CHAR(1)                        -- 'Y' = P&L, 'N' = Balance Sheet
parameters JSON                    -- Contains: {"purpose": "equity_result"}
administration VARCHAR(100)        -- Tenant identifier
```

### Views

#### vw_mutaties (Transaction View)

- Provides Amount column with correct sign convention
- Negative Amount = Revenue (credit accounts)
- Positive Amount = Expenses (debit accounts)
- Used for all year-end closure calculations

### Indexes

Recommended indexes for performance:

```sql
-- On mutaties table
CREATE INDEX idx_mutaties_admin_year ON mutaties(administration, YEAR(TransactionDate));
CREATE INDEX idx_mutaties_txn_number ON mutaties(TransactionNumber);
CREATE INDEX idx_mutaties_ref_number ON mutaties(ReferenceNumber);
CREATE INDEX idx_mutaties_vw ON mutaties(administration, VW, TransactionDate);

-- On year_closure_status table
CREATE INDEX idx_closure_admin_year ON year_closure_status(administration, year);
```

---

## Bulk Operations

### Bulk Close Multiple Years

Use the bulk closure script to close multiple historical years:

```bash
cd backend
python scripts/database/bulk_close_years.py
```

#### Script Features

- Closes years sequentially (oldest to newest)
- Validates each year before closing
- Skips already closed years
- Provides detailed progress output
- Handles errors gracefully

#### Example Output

```
Closing year 2010 for GoodwinSolutions...
  ✅ Year 2010 closed successfully
  Net result: €-5,234.56
  Balance sheet accounts: 12

Closing year 2011 for GoodwinSolutions...
  ✅ Year 2011 closed successfully
  Net result: €-6,789.01
  Balance sheet accounts: 15

Summary:
  Total years closed: 15
  Total years skipped: 0
  Total errors: 0
```

#### Configuration

Edit the script to specify tenants and year ranges:

```python
# In bulk_close_years.py
TENANTS_TO_CLOSE = {
    'GoodwinSolutions': {
        'start_year': 2010,
        'end_year': 2024,
        'user_email': 'system@bulk-closure',
        'notes': 'Bulk closure by script'
    },
    'PeterPrive': {
        'start_year': 1995,
        'end_year': 2024,
        'user_email': 'system@bulk-closure',
        'notes': 'Historical data migration'
    }
}
```

### Update ReferenceNumber for Historical Records

If you need to add ReferenceNumber to existing closure records:

```bash
cd backend
python scripts/database/update_year_closure_reference_numbers.py
```

This script:

- Updates OpeningBalance records with ReferenceNumber = "Opening Balance"
- Updates YearClose records with ReferenceNumber = "Year Closure"
- Provides verification output
- Supports both test and production databases

---

## Troubleshooting

### Common Issues

#### 1. "Required accounts not configured"

**Symptom**: Cannot close year, validation fails

**Solution**:

1. Go to **Tenant Admin > Year-End Settings**
2. Configure both required accounts:
   - Equity result account (VW=N)
   - P&L closing account (VW=Y)
3. Save configuration
4. Retry closure

**Verification**:

```sql
SELECT Account, AccountName, VW,
       JSON_EXTRACT(parameters, '$.purpose') as purpose
FROM rekeningschema
WHERE administration = 'YourTenant'
AND JSON_EXTRACT(parameters, '$.purpose') IS NOT NULL;
```

#### 2. "Previous year must be closed first"

**Symptom**: Cannot close year 2025 when 2024 is still open

**Solution**:

- Years must be closed sequentially
- Close year 2024 first, then 2025
- Use bulk closure script for multiple years

**Check closure status**:

```sql
SELECT year, closed_date, closed_by
FROM year_closure_status
WHERE administration = 'YourTenant'
ORDER BY year DESC;
```

#### 3. "Cannot reopen year because next year is closed"

**Symptom**: Cannot reopen 2024 when 2025 is already closed

**Solution**:

- Reopen years in reverse order (newest first)
- Reopen 2025 first, then 2024
- This prevents data integrity issues

**Why**: Opening balances for 2025 depend on 2024 being closed

#### 4. Cache not updating after closure

**Symptom**: Reports show old data after closing year

**Solution**:

- Cache is automatically invalidated after close/reopen
- If issue persists, restart backend:
  ```bash
  docker-compose restart backend
  ```

**Manual cache clear** (if needed):

```python
from mutaties_cache import invalidate_cache
invalidate_cache()
```

#### 5. Incorrect opening balances

**Symptom**: Opening balance amounts don't match expected values

**Diagnosis**:

```sql
-- Check opening balance transactions
SELECT TransactionNumber, TransactionDate,
       TransactionDescription, TransactionAmount,
       Debet, Credit, ReferenceNumber
FROM mutaties
WHERE TransactionNumber LIKE 'OpeningBalance%'
AND administration = 'YourTenant'
ORDER BY TransactionDate DESC
LIMIT 20;

-- Verify balance sheet account totals
SELECT Reknum, AccountName, SUM(Amount) as Balance
FROM vw_mutaties
WHERE administration = 'YourTenant'
AND VW = 'N'
AND YEAR(TransactionDate) = 2024
GROUP BY Reknum, AccountName
HAVING ABS(SUM(Amount)) > 0.01
ORDER BY Reknum;
```

**Solution**:

1. Reopen the year
2. Verify all transactions are correct
3. Close the year again

#### 6. Debit/Credit reversed in YearClose transaction

**Symptom**: YearClose transaction has wrong debit/credit order

**Note**: This was fixed in the latest version. The logic now correctly handles:

- Profit (negative net result): Debit P&L Closing, Credit Equity
- Loss (positive net result): Debit Equity, Credit P&L Closing

**Verification**:

```sql
SELECT TransactionNumber, TransactionDate,
       TransactionAmount, Debet, Credit
FROM mutaties
WHERE TransactionNumber LIKE 'YearClose%'
AND administration = 'YourTenant'
ORDER BY TransactionDate DESC;
```

### Database Queries for Troubleshooting

#### Check year closure status

```sql
SELECT administration, year, closed_date, closed_by, notes
FROM year_closure_status
ORDER BY administration, year DESC;
```

#### Find all year-end closure transactions

```sql
SELECT TransactionNumber, TransactionDate, ReferenceNumber,
       TransactionAmount, Debet, Credit, administration
FROM mutaties
WHERE ReferenceNumber IN ('Year Closure', 'Opening Balance')
ORDER BY administration, TransactionDate DESC;
```

#### Verify account configuration

```sql
SELECT Account, AccountName, VW,
       JSON_EXTRACT(parameters, '$.purpose') as purpose
FROM rekeningschema
WHERE JSON_EXTRACT(parameters, '$.purpose') IN ('equity_result', 'pl_closing')
ORDER BY administration, Account;
```

#### Check for orphaned opening balances

```sql
-- Opening balances without corresponding closure
SELECT ob.TransactionNumber, ob.TransactionDate, ob.administration
FROM mutaties ob
WHERE ob.TransactionNumber LIKE 'OpeningBalance%'
AND NOT EXISTS (
    SELECT 1 FROM year_closure_status ycs
    WHERE ycs.administration = ob.administration
    AND ycs.opening_balance_transaction_number = ob.TransactionNumber
);
```

#### Verify P&L accounts are closed

```sql
-- Should return 0 for closed years
SELECT YEAR(TransactionDate) as year,
       SUM(Amount) as total_pl_balance
FROM vw_mutaties
WHERE administration = 'YourTenant'
AND VW = 'Y'
AND YEAR(TransactionDate) = 2024
GROUP BY YEAR(TransactionDate);
```

---

## Maintenance

### Regular Maintenance Tasks

#### Monthly

- Review closure status for all tenants
- Verify no orphaned transactions
- Check cache performance

#### Quarterly

- Review and optimize database indexes
- Archive old closure logs
- Update documentation

#### Annually

- Bulk close previous year for all tenants
- Verify opening balances
- Performance review

### Backup Procedures

#### Before Bulk Operations

```bash
# Backup mutaties table
mysqldump -u user -p finance mutaties > mutaties_backup_$(date +%Y%m%d).sql

# Backup year_closure_status table
mysqldump -u user -p finance year_closure_status > closure_status_backup_$(date +%Y%m%d).sql
```

#### Restore from Backup

```bash
mysql -u user -p finance < mutaties_backup_20260303.sql
mysql -u user -p finance < closure_status_backup_20260303.sql
```

### Monitoring

#### Key Metrics to Monitor

- Number of closed years per tenant
- Average closure time
- Failed closure attempts
- Cache hit rate
- Database query performance

#### Health Check Script

```bash
cd backend
python scripts/check_year_end_setup.py --all-tenants
```

### Log Files

#### Backend Logs

- Location: `backend/logs/app.log`
- Contains: Closure operations, errors, validation failures

#### Audit Logs

- Table: `audit_log`
- Tracks: All closure and reopen operations with user and timestamp

---

## Performance Optimization

### Database Optimization

#### Index Optimization

```sql
-- Analyze table statistics
ANALYZE TABLE mutaties;
ANALYZE TABLE year_closure_status;

-- Check index usage
SHOW INDEX FROM mutaties;
EXPLAIN SELECT * FROM vw_mutaties
WHERE administration = 'YourTenant'
AND YEAR(TransactionDate) = 2024;
```

#### Query Optimization

Use YEAR index for better performance:

```sql
-- Good: Uses index
SELECT * FROM mutaties
WHERE administration = 'YourTenant'
AND YEAR(TransactionDate) = 2024;

-- Better: If you have a date range index
SELECT * FROM mutaties
WHERE administration = 'YourTenant'
AND TransactionDate BETWEEN '2024-01-01' AND '2024-12-31';
```

### Cache Configuration

The system uses an in-memory cache for frequently accessed data:

```python
# In mutaties_cache.py
CACHE_TTL = 3600  # 1 hour
MAX_CACHE_SIZE = 1000  # entries
```

#### Cache Invalidation

- Automatic: After close_year() and reopen_year()
- Manual: Call `invalidate_cache()` if needed

### Bulk Operation Performance

For large datasets:

1. **Batch Processing**: Process years in batches
2. **Off-Peak Hours**: Run bulk operations during low-traffic periods
3. **Progress Monitoring**: Use verbose output to track progress
4. **Error Recovery**: Script continues on errors, logs failures

#### Estimated Times

- Single year closure: 1-5 seconds
- 10 years bulk closure: 10-50 seconds
- 30 years bulk closure: 30-150 seconds

Times vary based on:

- Number of transactions per year
- Number of balance sheet accounts
- Database server performance
- Network latency

### Scaling Considerations

#### For Large Tenants (>100k transactions/year)

- Consider partitioning mutaties table by year
- Implement read replicas for reporting
- Use connection pooling
- Optimize vw_mutaties view

#### For Many Tenants (>100 tenants)

- Implement tenant-specific caching
- Use async processing for bulk operations
- Monitor database connection limits
- Consider sharding strategy

---

## Advanced Topics

### Custom Closure Logic

If you need to customize the closure logic:

1. **Extend YearEndClosureService**:

```python
class CustomYearEndClosureService(YearEndClosureService):
    def _create_closure_transaction(self, administration, year, cursor):
        # Custom logic here
        pass
```

2. **Override validation**:

```python
def validate_year_closure(self, administration, year):
    validation = super().validate_year_closure(administration, year)
    # Add custom validation
    return validation
```

### Integration with External Systems

#### Export Closure Data

```python
from services.year_end_service import YearEndClosureService

service = YearEndClosureService()
closed_years = service.get_closed_years('YourTenant')

# Export to JSON
import json
with open('closed_years.json', 'w') as f:
    json.dump(closed_years, f, indent=2, default=str)
```

#### Webhook Notifications

Add webhook calls in `close_year()` method to notify external systems.

### Disaster Recovery

#### Recovery Scenarios

**Scenario 1: Accidental Closure**

1. Use `reopen_year()` immediately
2. Verify data integrity
3. Re-close if needed

**Scenario 2: Corrupted Transactions**

1. Restore from backup
2. Verify transaction integrity
3. Re-run closure

**Scenario 3: Database Failure**

1. Restore database from backup
2. Verify year_closure_status table
3. Check for orphaned transactions
4. Re-run failed closures

---

## Security Considerations

### Access Control

- Only users with `finance_write` permission can close years
- Only `Tenant_Admin` can configure accounts
- All operations are logged in audit_log

### Data Integrity

- All closure operations use database transactions
- Rollback on any error
- Sequential closure enforced
- Validation before every closure

### Audit Trail

Every closure operation records:

- User who performed the action
- Timestamp
- Year closed
- Transaction numbers created
- Optional notes

Query audit log:

```sql
SELECT * FROM audit_log
WHERE operation IN ('close_year', 'reopen_year')
ORDER BY timestamp DESC;
```

---

## Support and Resources

### Documentation

- User Guide: `.kiro/specs/FIN/Year end closure/USER_GUIDE.md`
- Requirements: `.kiro/specs/FIN/Year end closure/requirements.md`
- Design: `.kiro/specs/FIN/Year end closure/design.md`
- Tasks: `.kiro/specs/FIN/Year end closure/TASKS-closure.md`

### Scripts

- Bulk closure: `backend/scripts/database/bulk_close_years.py`
- Configuration check: `backend/scripts/check_year_end_setup.py`
- Reference number update: `backend/scripts/database/update_year_closure_reference_numbers.py`

### API Endpoints

- `GET /api/year-end/status/{year}` - Get year status
- `GET /api/year-end/validate/{year}` - Validate year
- `POST /api/year-end/close` - Close year
- `POST /api/year-end/reopen` - Reopen year
- `GET /api/year-end/closed-years` - List closed years

### Contact

For issues or questions:

1. Check this guide first
2. Review error logs
3. Run diagnostic scripts
4. Contact development team

---

## Appendix

### Glossary

- **VW**: Classification (Y = P&L, N = Balance Sheet)
- **Debet/Credit**: Double-entry bookkeeping sides
- **TransactionNumber**: Unique identifier for transaction group
- **ReferenceNumber**: Category identifier for transaction type
- **Administration**: Tenant identifier
- **Equity Account**: Balance sheet account recording net worth
- **P&L Closing Account**: Temporary account for year-end closure

### Change Log

- **2026-03-03**: Added ReferenceNumber to closure transactions
- **2026-03-03**: Removed interim account requirement
- **2026-03-03**: Fixed debit/credit logic in YearClose
- **2026-03-03**: Updated cache to use new model
- **2026-03-03**: Added sequential reopening validation

### Known Limitations

1. Cannot close current year (must wait until year-end)
2. Cannot skip years (must close sequentially)
3. Cannot reopen if next year is closed
4. Requires manual account configuration per tenant
5. No automated year-end scheduling (manual process)

### Future Enhancements

- Automated year-end closure scheduling
- Multi-year closure in single operation
- Enhanced reporting on closure history
- Automated backup before closure
- Email notifications on closure completion
