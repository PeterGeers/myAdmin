# Duplicate Invoice Detection - System Administration Guide

## Overview

This guide provides system administrators with comprehensive information for monitoring, maintaining, and troubleshooting the duplicate invoice detection system in myAdmin.

**Requirements Addressed:** All requirements (1.1-7.5)

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Installation and Setup](#installation-and-setup)
3. [Monitoring and Metrics](#monitoring-and-metrics)
4. [Performance Optimization](#performance-optimization)
5. [Database Management](#database-management)
6. [Audit Trail Management](#audit-trail-management)
7. [Troubleshooting](#troubleshooting)
8. [Maintenance Procedures](#maintenance-procedures)
9. [Security Considerations](#security-considerations)
10. [Backup and Recovery](#backup-and-recovery)

## System Architecture

### Component Overview

The duplicate invoice detection system consists of several integrated components:

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend Layer                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  DuplicateWarningDialog.tsx                          │   │
│  │  - User interface for duplicate warnings             │   │
│  │  - Decision handling (Continue/Cancel)               │   │
│  │  - Loading states and error handling                 │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓ ↑
┌─────────────────────────────────────────────────────────────┐
│                     Backend Layer                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  pdf_processor.py                                    │   │
│  │  - Integration point for duplicate checking          │   │
│  │  - Decision processing (continue/cancel)             │   │
│  │  - File cleanup coordination                         │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  duplicate_checker.py                                │   │
│  │  - Core duplicate detection logic                    │   │
│  │  - Database query execution                          │   │
│  │  - Result formatting                                 │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  file_cleanup_manager.py                             │   │
│  │  - File URL comparison                               │   │
│  │  - Atomic file deletion                              │   │
│  │  - Google Drive integration                          │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  audit_logger.py                                     │   │
│  │  - Decision logging                                  │   │
│  │  - Audit trail management                            │   │
│  │  - Compliance reporting                              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓ ↑
┌─────────────────────────────────────────────────────────────┐
│                     Database Layer                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  mutaties / mutaties_test                            │   │
│  │  - Transaction storage                               │   │
│  │  - Duplicate detection queries                       │   │
│  │  - Indexed for performance                           │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  duplicate_decision_log                              │   │
│  │  - Audit trail storage                               │   │
│  │  - Decision history                                  │   │
│  │  - Compliance reporting                              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Invoice Upload** → User uploads invoice file
2. **Data Extraction** → System extracts transaction data
3. **Duplicate Check** → Query database for matching transactions
4. **User Decision** → Display warning if duplicates found
5. **Processing** → Execute user decision (continue or cancel)
6. **Audit Logging** → Record decision in audit trail
7. **File Management** → Clean up files if cancelled

## Installation and Setup

### Prerequisites

- MySQL database with appropriate permissions
- Python 3.8+ with required packages
- Google Drive API credentials (for file management)
- Existing myAdmin installation

### Database Setup

#### 1. Apply Duplicate Detection Indexes

```bash
cd backend
python apply_duplicate_indexes.py
```

This creates the following indexes on the `mutaties` table:

- `idx_duplicate_detection` - Composite index on (ReferenceNumber, TransactionDate, TransactionAmount)
- `idx_transaction_date` - Index on TransactionDate for date range queries

#### 2. Apply Audit Logging Migration

```bash
cd backend
python apply_audit_migration.py
```

This creates the `duplicate_decision_log` table with appropriate indexes.

### Verification

Run the test suite to verify installation:

```bash
cd backend
python -m pytest test/test_duplicate_checker.py -v
python -m pytest test/test_file_cleanup_manager.py -v
python -m pytest test/test_audit_logger.py -v
python -m pytest test/test_duplicate_integration_e2e.py -v
```

All tests should pass.

## Monitoring and Metrics

### Key Performance Indicators (KPIs)

Monitor these metrics to ensure system health:

| Metric                        | Target      | Alert Threshold | Description                                                 |
| ----------------------------- | ----------- | --------------- | ----------------------------------------------------------- |
| Duplicate Check Response Time | < 2 seconds | > 3 seconds     | Time to complete duplicate detection query                  |
| False Positive Rate           | < 5%        | > 10%           | Percentage of legitimate transactions flagged as duplicates |
| User Decision Rate            | N/A         | N/A             | Ratio of Continue vs Cancel decisions                       |
| File Cleanup Success Rate     | > 99%       | < 95%           | Percentage of successful file deletions                     |
| Audit Log Coverage            | 100%        | < 100%          | Percentage of decisions logged                              |

### Monitoring Queries

#### Check Duplicate Detection Performance

```sql
-- Average response time for duplicate checks (from application logs)
SELECT
    DATE(timestamp) as date,
    AVG(response_time_ms) as avg_response_time,
    MAX(response_time_ms) as max_response_time,
    COUNT(*) as check_count
FROM performance_logs
WHERE operation = 'duplicate_check'
GROUP BY DATE(timestamp)
ORDER BY date DESC
LIMIT 30;
```

#### Monitor Duplicate Detection Rate

```sql
-- Duplicate detection statistics
SELECT
    DATE(timestamp) as date,
    COUNT(*) as total_checks,
    SUM(CASE WHEN decision = 'continue' THEN 1 ELSE 0 END) as continued,
    SUM(CASE WHEN decision = 'cancel' THEN 1 ELSE 0 END) as cancelled,
    ROUND(SUM(CASE WHEN decision = 'continue' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as continue_percentage
FROM duplicate_decision_log
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(timestamp)
ORDER BY date DESC;
```

#### Top Duplicate Vendors

```sql
-- Vendors with most duplicate detections
SELECT
    reference_number,
    COUNT(*) as duplicate_count,
    SUM(CASE WHEN decision = 'continue' THEN 1 ELSE 0 END) as continued,
    SUM(CASE WHEN decision = 'cancel' THEN 1 ELSE 0 END) as cancelled
FROM duplicate_decision_log
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 90 DAY)
GROUP BY reference_number
ORDER BY duplicate_count DESC
LIMIT 20;
```

### Application Logging

The system logs important events to help with monitoring:

```python
# Log levels and their uses
INFO    - Normal operations (duplicate found, decision made)
WARNING - Potential issues (slow queries, file cleanup failures)
ERROR   - Failures (database errors, file system errors)
DEBUG   - Detailed information for troubleshooting
```

#### Key Log Messages

- `Duplicate check completed in X ms` - Performance monitoring
- `Duplicate found: X matching transactions` - Detection events
- `User decision: continue/cancel` - Decision tracking
- `File cleanup: success/failure` - File management
- `Audit log entry created` - Audit trail confirmation

### Monitoring Dashboard Recommendations

Create a monitoring dashboard with:

1. **Real-time Metrics**

   - Current duplicate check response time
   - Active duplicate warnings
   - Recent decisions (last hour)

2. **Daily Statistics**

   - Total duplicate checks
   - Continue vs Cancel ratio
   - Top duplicate vendors
   - File cleanup success rate

3. **Trends**

   - Duplicate detection rate over time
   - Performance trends
   - User decision patterns

4. **Alerts**
   - Slow query alerts (> 3 seconds)
   - File cleanup failures
   - Audit log gaps
   - Database connection issues

## Performance Optimization

### Database Optimization

#### Index Maintenance

Regularly check index health:

```sql
-- Check index usage
SHOW INDEX FROM mutaties WHERE Key_name LIKE 'idx_duplicate%';

-- Analyze table for optimization
ANALYZE TABLE mutaties;

-- Check index cardinality
SELECT
    INDEX_NAME,
    CARDINALITY,
    SEQ_IN_INDEX,
    COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_NAME = 'mutaties'
AND INDEX_NAME LIKE 'idx_duplicate%';
```

#### Query Optimization

The duplicate detection query is optimized for performance:

```sql
-- Optimized duplicate detection query
SELECT * FROM mutaties
WHERE ReferenceNumber = ?
AND TransactionDate = ?
AND TransactionAmount = ?
AND TransactionDate > DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
ORDER BY ID DESC;
```

**Optimization Features:**

- Uses composite index for fast lookups
- Limits search to 2-year window
- Returns results in descending ID order

#### Performance Testing

Run performance tests to verify optimization:

```bash
cd backend
python -m pytest test/test_duplicate_performance.py -v
```

Expected results:

- Single duplicate check: < 100ms
- 100 concurrent checks: < 2 seconds average
- 1000 transaction dataset: < 500ms

### Application Optimization

#### Connection Pooling

Ensure database connection pooling is configured:

```python
# In database.py
POOL_SIZE = 10
MAX_OVERFLOW = 20
POOL_TIMEOUT = 30
```

#### Caching Strategy

Consider implementing caching for:

- Recent duplicate checks (5-minute TTL)
- Vendor-specific patterns
- User decision history

### File System Optimization

#### Google Drive API Optimization

- Use batch operations when possible
- Implement retry logic for transient failures
- Cache folder IDs to reduce API calls
- Monitor API quota usage

## Database Management

### Schema Management

#### Mutaties Table

Ensure the following indexes exist:

```sql
-- Composite index for duplicate detection
CREATE INDEX idx_duplicate_detection
ON mutaties(ReferenceNumber, TransactionDate, TransactionAmount);

-- Date range index
CREATE INDEX idx_transaction_date
ON mutaties(TransactionDate);
```

#### Duplicate Decision Log Table

```sql
CREATE TABLE IF NOT EXISTS duplicate_decision_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reference_number VARCHAR(255) NOT NULL,
    transaction_date DATE NOT NULL,
    transaction_amount DECIMAL(10,2) NOT NULL,
    decision VARCHAR(20) NOT NULL,
    existing_transaction_id INT NOT NULL,
    new_file_url VARCHAR(500),
    user_id VARCHAR(100),
    session_id VARCHAR(100),
    operation_id VARCHAR(100),
    INDEX idx_reference_number (reference_number),
    INDEX idx_transaction_date (transaction_date),
    INDEX idx_decision (decision),
    INDEX idx_timestamp (timestamp),
    INDEX idx_user_id (user_id)
);
```

### Data Retention

#### Transaction Data

- **Production Table (mutaties):** Retain indefinitely
- **Test Table (mutaties_test):** Clean up monthly
- **Duplicate Search Window:** 2 years (configurable)

#### Audit Logs

- **Default Retention:** 2 years (730 days)
- **Compliance Requirement:** Adjust based on regulations
- **Cleanup Schedule:** Monthly automated cleanup

```bash
# Manual cleanup
cd backend
python -c "
from audit_logger import AuditLogger
from database import DatabaseManager
db = DatabaseManager()
audit = AuditLogger(db)
success, count = audit.cleanup_old_logs(retention_days=730)
print(f'Cleaned up {count} old audit logs')
"
```

### Backup Procedures

#### Database Backup

```bash
# Backup mutaties table
mysqldump -u username -p database_name mutaties > mutaties_backup_$(date +%Y%m%d).sql

# Backup audit logs
mysqldump -u username -p database_name duplicate_decision_log > audit_backup_$(date +%Y%m%d).sql
```

#### Restore Procedures

```bash
# Restore mutaties table
mysql -u username -p database_name < mutaties_backup_20241215.sql

# Restore audit logs
mysql -u username -p database_name < audit_backup_20241215.sql
```

## Audit Trail Management

### Accessing Audit Logs

#### Via API

```bash
# Get recent audit logs
curl http://localhost:5000/api/audit/logs?limit=100

# Get logs for specific vendor
curl http://localhost:5000/api/audit/logs?reference_number=Booking.com

# Get logs for date range
curl "http://localhost:5000/api/audit/logs?start_date=2024-01-01&end_date=2024-12-31"

# Generate compliance report
curl "http://localhost:5000/api/audit/reports/compliance?start_date=2024-01-01&end_date=2024-12-31"
```

#### Via Database

```sql
-- Recent decisions
SELECT * FROM duplicate_decision_log
ORDER BY timestamp DESC
LIMIT 100;

-- Decisions by vendor
SELECT
    reference_number,
    COUNT(*) as total,
    SUM(CASE WHEN decision = 'continue' THEN 1 ELSE 0 END) as continued,
    SUM(CASE WHEN decision = 'cancel' THEN 1 ELSE 0 END) as cancelled
FROM duplicate_decision_log
GROUP BY reference_number
ORDER BY total DESC;

-- User activity
SELECT
    user_id,
    COUNT(*) as decisions,
    DATE(timestamp) as date
FROM duplicate_decision_log
WHERE user_id IS NOT NULL
GROUP BY user_id, DATE(timestamp)
ORDER BY date DESC, decisions DESC;
```

### Compliance Reporting

#### Monthly Compliance Report

```python
from audit_logger import AuditLogger
from database import DatabaseManager
from datetime import datetime, timedelta

db = DatabaseManager()
audit = AuditLogger(db)

# Generate monthly report
end_date = datetime.now()
start_date = end_date - timedelta(days=30)

report = audit.generate_compliance_report(
    start_date=start_date.strftime('%Y-%m-%d'),
    end_date=end_date.strftime('%Y-%m-%d'),
    include_details=True
)

print(f"Total Decisions: {report['summary']['total_decisions']}")
print(f"Continue: {report['summary']['continue_count']} ({report['summary']['continue_percentage']}%)")
print(f"Cancel: {report['summary']['cancel_count']} ({report['summary']['cancel_percentage']}%)")
```

#### Export to CSV

```bash
# Export audit logs to CSV
curl "http://localhost:5000/api/audit/export/csv?start_date=2024-01-01&end_date=2024-12-31" > audit_export.csv
```

## Troubleshooting

### Common Issues

#### 1. Slow Duplicate Detection

**Symptoms:**

- Duplicate check takes > 3 seconds
- User interface becomes unresponsive
- Timeout errors

**Diagnosis:**

```sql
-- Check query execution plan
EXPLAIN SELECT * FROM mutaties
WHERE ReferenceNumber = 'Booking.com'
AND TransactionDate = '2024-12-15'
AND TransactionAmount = 121.00
AND TransactionDate > DATE_SUB(CURDATE(), INTERVAL 2 YEAR);

-- Check index usage
SHOW INDEX FROM mutaties WHERE Key_name LIKE 'idx_duplicate%';

-- Check table statistics
SHOW TABLE STATUS LIKE 'mutaties';
```

**Solutions:**

1. Verify indexes exist and are being used
2. Run `ANALYZE TABLE mutaties` to update statistics
3. Check database server load
4. Consider increasing connection pool size
5. Review slow query log

#### 2. False Positives

**Symptoms:**

- Legitimate transactions flagged as duplicates
- Users frequently choosing "Continue"
- Complaints about unnecessary warnings

**Diagnosis:**

```sql
-- Check for patterns in continued duplicates
SELECT
    reference_number,
    transaction_date,
    transaction_amount,
    COUNT(*) as occurrences
FROM duplicate_decision_log
WHERE decision = 'continue'
GROUP BY reference_number, transaction_date, transaction_amount
HAVING COUNT(*) > 5
ORDER BY occurrences DESC;
```

**Solutions:**

1. Review vendor-specific patterns (e.g., Booking.com multiple properties)
2. Consider adding additional matching criteria (e.g., invoice number)
3. Adjust detection logic for specific vendors
4. Document common legitimate duplicate scenarios

#### 3. File Cleanup Failures

**Symptoms:**

- Orphaned files in Google Drive
- File deletion errors in logs
- Storage quota issues

**Diagnosis:**

```python
# Check file cleanup logs
grep "File cleanup" backend/logs/error.log

# Test Google Drive connectivity
from google_drive_service import GoogleDriveService
drive = GoogleDriveService()
result = drive.test_connection()
print(result)
```

**Solutions:**

1. Verify Google Drive API credentials
2. Check file permissions
3. Ensure sufficient API quota
4. Review file URL format
5. Implement retry logic for transient failures

#### 4. Audit Log Gaps

**Symptoms:**

- Missing audit log entries
- Incomplete compliance reports
- Decision count mismatches

**Diagnosis:**

```sql
-- Check for gaps in audit logs
SELECT
    DATE(timestamp) as date,
    COUNT(*) as log_count
FROM duplicate_decision_log
GROUP BY DATE(timestamp)
ORDER BY date DESC
LIMIT 30;

-- Compare with actual duplicate checks
SELECT COUNT(*) FROM mutaties
WHERE TransactionDate >= DATE_SUB(NOW(), INTERVAL 30 DAY);
```

**Solutions:**

1. Check database connectivity during decision time
2. Review error logs for audit logging failures
3. Verify audit_logger.py is being called
4. Check database permissions for INSERT operations
5. Implement retry logic for audit logging

#### 5. Database Connection Issues

**Symptoms:**

- "Database connection failed" errors
- Duplicate check timeouts
- Intermittent failures

**Diagnosis:**

```bash
# Test database connectivity
cd backend
python -c "
from database import DatabaseManager
db = DatabaseManager()
result = db.test_connection()
print(f'Connection: {result}')
"

# Check connection pool
# Review logs for connection pool exhaustion
grep "connection pool" backend/logs/error.log
```

**Solutions:**

1. Verify database credentials in .env file
2. Check database server status
3. Increase connection pool size
4. Implement connection retry logic
5. Monitor connection pool usage

### Error Log Analysis

#### Key Error Patterns

```bash
# Search for duplicate detection errors
grep -i "duplicate" backend/logs/error.log | tail -50

# Search for file cleanup errors
grep -i "cleanup" backend/logs/error.log | tail -50

# Search for audit logging errors
grep -i "audit" backend/logs/error.log | tail -50

# Search for database errors
grep -i "database" backend/logs/error.log | tail -50
```

## Maintenance Procedures

### Daily Maintenance

1. **Monitor Performance**

   - Check duplicate detection response times
   - Review error logs
   - Verify audit log coverage

2. **Check System Health**
   ```bash
   curl http://localhost:5000/api/audit/health
   ```

### Weekly Maintenance

1. **Review Duplicate Patterns**

   ```sql
   -- Top duplicate vendors this week
   SELECT
       reference_number,
       COUNT(*) as duplicates,
       SUM(CASE WHEN decision = 'continue' THEN 1 ELSE 0 END) as continued
   FROM duplicate_decision_log
   WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
   GROUP BY reference_number
   ORDER BY duplicates DESC
   LIMIT 10;
   ```

2. **Check File Cleanup Success Rate**

   ```bash
   grep "File cleanup" backend/logs/error.log | grep -c "success"
   grep "File cleanup" backend/logs/error.log | grep -c "failed"
   ```

3. **Review User Decision Patterns**
   ```sql
   -- User decision summary
   SELECT
       user_id,
       COUNT(*) as decisions,
       SUM(CASE WHEN decision = 'continue' THEN 1 ELSE 0 END) as continued,
       SUM(CASE WHEN decision = 'cancel' THEN 1 ELSE 0 END) as cancelled
   FROM duplicate_decision_log
   WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
   AND user_id IS NOT NULL
   GROUP BY user_id;
   ```

### Monthly Maintenance

1. **Database Optimization**

   ```sql
   ANALYZE TABLE mutaties;
   ANALYZE TABLE duplicate_decision_log;
   OPTIMIZE TABLE duplicate_decision_log;
   ```

2. **Audit Log Cleanup**

   ```bash
   cd backend
   python -c "
   from audit_logger import AuditLogger
   from database import DatabaseManager
   db = DatabaseManager()
   audit = AuditLogger(db)
   success, count = audit.cleanup_old_logs(retention_days=730)
   print(f'Cleaned up {count} old audit logs')
   "
   ```

3. **Generate Compliance Report**

   ```bash
   curl "http://localhost:5000/api/audit/reports/compliance?start_date=2024-01-01&end_date=2024-12-31&include_details=true" > monthly_compliance_report.json
   ```

4. **Review Performance Metrics**
   - Average duplicate check response time
   - False positive rate
   - File cleanup success rate
   - User satisfaction feedback

### Quarterly Maintenance

1. **System Review**

   - Review duplicate detection accuracy
   - Analyze user decision patterns
   - Identify improvement opportunities
   - Update documentation

2. **Performance Tuning**

   - Review and optimize database indexes
   - Analyze slow queries
   - Adjust connection pool settings
   - Optimize file cleanup operations

3. **Security Audit**
   - Review access controls
   - Check audit log integrity
   - Verify data protection measures
   - Update security policies

## Security Considerations

### Access Control

1. **API Endpoints**

   - Implement authentication for all duplicate detection endpoints
   - Use role-based access control (RBAC)
   - Log all API access attempts

2. **Database Access**

   - Use least privilege principle
   - Separate read and write permissions
   - Audit database access logs

3. **File System Access**
   - Restrict file deletion permissions
   - Validate file paths before operations
   - Log all file operations

### Data Protection

1. **Sensitive Data**

   - Transaction amounts
   - Vendor information
   - User decisions
   - File URLs

2. **Encryption**

   - Use HTTPS for all API communications
   - Encrypt sensitive data at rest
   - Secure database connections (SSL/TLS)

3. **Audit Trail Integrity**
   - Audit logs should be immutable
   - Implement tamper detection
   - Regular backup of audit data

### Compliance

1. **GDPR Compliance**

   - Data retention policies
   - Right to deletion
   - Data export capabilities
   - Privacy by design

2. **SOX Compliance**

   - Complete audit trail
   - Access controls
   - Change management
   - Regular audits

3. **Internal Policies**
   - Document all procedures
   - Regular security reviews
   - Incident response plan
   - User training

## Backup and Recovery

### Backup Strategy

#### Database Backups

```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d)
BACKUP_DIR="/backups/myAdmin"

# Backup mutaties table
mysqldump -u username -p database_name mutaties | gzip > $BACKUP_DIR/mutaties_$DATE.sql.gz

# Backup audit logs
mysqldump -u username -p database_name duplicate_decision_log | gzip > $BACKUP_DIR/audit_$DATE.sql.gz

# Keep last 30 days
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
```

#### Application Backups

```bash
# Backup application code
tar -czf myAdmin_backup_$(date +%Y%m%d).tar.gz backend/ frontend/

# Backup configuration
cp backend/.env backend/.env.backup_$(date +%Y%m%d)
```

### Recovery Procedures

#### Database Recovery

```bash
# Restore mutaties table
gunzip < mutaties_20241215.sql.gz | mysql -u username -p database_name

# Restore audit logs
gunzip < audit_20241215.sql.gz | mysql -u username -p database_name

# Verify restoration
mysql -u username -p database_name -e "SELECT COUNT(*) FROM mutaties;"
mysql -u username -p database_name -e "SELECT COUNT(*) FROM duplicate_decision_log;"
```

#### Application Recovery

```bash
# Restore application code
tar -xzf myAdmin_backup_20241215.tar.gz

# Restore configuration
cp backend/.env.backup_20241215 backend/.env

# Restart services
cd backend
python src/app.py
```

### Disaster Recovery

1. **Recovery Time Objective (RTO):** 4 hours
2. **Recovery Point Objective (RPO):** 24 hours
3. **Backup Frequency:** Daily
4. **Backup Retention:** 30 days
5. **Off-site Backup:** Weekly to cloud storage

## Support and Escalation

### Support Levels

1. **Level 1 - User Support**

   - User questions about duplicate warnings
   - How to make decisions
   - Basic troubleshooting

2. **Level 2 - System Administration**

   - Performance issues
   - Configuration problems
   - Database maintenance

3. **Level 3 - Development Team**
   - Bug fixes
   - Feature enhancements
   - System architecture changes

### Escalation Criteria

Escalate to Level 3 if:

- Duplicate detection accuracy < 90%
- Response time consistently > 5 seconds
- File cleanup failure rate > 5%
- Audit log gaps detected
- Security incidents

### Contact Information

- **User Support:** support@example.com
- **System Administration:** sysadmin@example.com
- **Development Team:** dev@example.com
- **Emergency:** emergency@example.com

## Appendix

### Configuration Reference

#### Environment Variables

```bash
# Database Configuration
DB_HOST=localhost
DB_PORT=3306
DB_NAME=myAdmin
DB_USER=admin
DB_PASSWORD=secure_password

# Duplicate Detection Settings
DUPLICATE_SEARCH_WINDOW_YEARS=2
DUPLICATE_CHECK_TIMEOUT_SECONDS=5

# File Cleanup Settings
FILE_CLEANUP_ENABLED=true
FILE_CLEANUP_RETRY_COUNT=3

# Audit Logging Settings
AUDIT_LOG_ENABLED=true
AUDIT_LOG_RETENTION_DAYS=730
```

#### Performance Tuning

```python
# Database connection pool
POOL_SIZE = 10
MAX_OVERFLOW = 20
POOL_TIMEOUT = 30

# Query timeout
QUERY_TIMEOUT = 5

# File operation timeout
FILE_OPERATION_TIMEOUT = 10
```

### API Reference

See `backend/src/openapi_spec.yaml` for complete API documentation.

### Version History

- **v1.0** (2024-12-17): Initial implementation
  - Core duplicate detection
  - File cleanup management
  - Audit logging system
  - Performance optimization
  - Integration with existing workflows

---

**Document Version:** 1.0  
**Last Updated:** December 17, 2024  
**Next Review:** March 17, 2025
