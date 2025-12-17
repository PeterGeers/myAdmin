# Audit Logging System for Duplicate Invoice Detection

## Overview

The audit logging system provides comprehensive tracking and reporting capabilities for duplicate invoice detection decisions. It ensures 100% audit trail coverage for all duplicate detection events, supporting compliance requirements and system monitoring.

**Requirements Addressed:** 3.2, 6.4, 6.5

## Components

### 1. Database Schema

**Table:** `duplicate_decision_log`

The audit log table stores all duplicate detection decisions with the following structure:

| Column                  | Type                     | Description                                       |
| ----------------------- | ------------------------ | ------------------------------------------------- |
| id                      | INT (PK, AUTO_INCREMENT) | Unique identifier for each log entry              |
| timestamp               | TIMESTAMP                | When the decision was made (auto-generated)       |
| reference_number        | VARCHAR(255)             | Reference number (folder name) of the transaction |
| transaction_date        | DATE                     | Date of the transaction                           |
| transaction_amount      | DECIMAL(10,2)            | Amount of the transaction                         |
| decision                | VARCHAR(20)              | User decision ('continue' or 'cancel')            |
| existing_transaction_id | INT                      | ID of the existing duplicate transaction          |
| new_file_url            | VARCHAR(500)             | URL of the new file being imported                |
| user_id                 | VARCHAR(100)             | User who made the decision (optional)             |
| session_id              | VARCHAR(100)             | Session identifier for tracking (optional)        |
| operation_id            | VARCHAR(100)             | Operation identifier for correlation (optional)   |

**Indexes:**

- `idx_reference_number` on `reference_number`
- `idx_transaction_date` on `transaction_date`
- `idx_decision` on `decision`
- `idx_timestamp` on `timestamp`
- `idx_user_id` on `user_id`

### 2. AuditLogger Class

**Location:** `backend/src/audit_logger.py`

The `AuditLogger` class provides the core audit logging functionality:

#### Key Methods:

- **`log_decision()`** - Log a duplicate invoice decision
- **`query_logs()`** - Query audit logs with flexible filtering
- **`get_decision_count()`** - Get count of audit log entries
- **`generate_compliance_report()`** - Generate comprehensive compliance reports
- **`get_user_activity_report()`** - Generate user-specific activity reports
- **`cleanup_old_logs()`** - Clean up logs based on retention policy
- **`export_logs_to_csv()`** - Export logs to CSV for external analysis
- **`get_audit_trail_for_transaction()`** - Get complete audit trail for a transaction

### 3. API Endpoints

**Location:** `backend/src/audit_routes.py`

The audit system provides REST API endpoints for accessing logs and reports:

#### Endpoints:

| Endpoint                            | Method | Description                       |
| ----------------------------------- | ------ | --------------------------------- |
| `/api/audit/logs`                   | GET    | Get audit logs with filtering     |
| `/api/audit/logs/count`             | GET    | Get count of audit log entries    |
| `/api/audit/reports/compliance`     | GET    | Generate compliance report        |
| `/api/audit/reports/user/<user_id>` | GET    | Get user activity report          |
| `/api/audit/transaction-trail`      | GET    | Get audit trail for a transaction |
| `/api/audit/export/csv`             | GET    | Export logs to CSV                |
| `/api/audit/cleanup`                | POST   | Clean up old logs                 |
| `/api/audit/health`                 | GET    | Health check endpoint             |

## Installation

### 1. Apply Database Migration

Run the migration script to create the audit log table:

```bash
cd backend
python apply_audit_migration.py
```

The script will:

- Check if the migration has already been applied
- Create the `duplicate_decision_log` table
- Set up all required indexes
- Verify the table structure

### 2. Verify Installation

Run the test suite to verify the audit logging system:

```bash
cd backend
python -m pytest test/test_audit_logger.py -v
```

All tests should pass, confirming:

- Basic logging functionality
- Query capabilities
- Report generation
- Data retention
- Error handling

## Usage

### Logging Decisions

The audit logging is automatically integrated into the duplicate detection workflow. When a user makes a decision about a duplicate invoice, it's logged automatically:

```python
from audit_logger import AuditLogger
from database import DatabaseManager

# Initialize
db = DatabaseManager()
audit_logger = AuditLogger(db)

# Log a decision
success = audit_logger.log_decision(
    reference_number='Vendor123',
    transaction_date='2025-01-15',
    transaction_amount=100.50,
    decision='continue',  # or 'cancel'
    existing_transaction_id=12345,
    new_file_url='https://drive.google.com/file/abc123',
    user_id='user_001',
    session_id='session_xyz',
    operation_id='op_12345'
)
```

### Querying Logs

Query audit logs with flexible filtering:

```python
# Query by reference number
logs = audit_logger.query_logs(reference_number='Vendor123')

# Query by date range
logs = audit_logger.query_logs(
    start_date='2025-01-01',
    end_date='2025-01-31'
)

# Query by decision type
logs = audit_logger.query_logs(decision='continue')

# Query by user
logs = audit_logger.query_logs(user_id='user_001')

# Combine filters with pagination
logs = audit_logger.query_logs(
    reference_number='Vendor',
    start_date='2025-01-01',
    end_date='2025-01-31',
    decision='continue',
    limit=50,
    offset=0
)
```

### Generating Reports

#### Compliance Report

Generate a comprehensive compliance report for a date range:

```python
report = audit_logger.generate_compliance_report(
    start_date='2025-01-01',
    end_date='2025-01-31',
    include_details=True
)

# Report includes:
# - Summary statistics (total, continue, cancel counts and percentages)
# - Detailed transaction list (if include_details=True)
# - Statistics by reference number
# - Top duplicate vendors
# - Daily breakdown
```

#### User Activity Report

Generate a report for a specific user:

```python
report = audit_logger.get_user_activity_report(
    user_id='user_001',
    start_date='2025-01-01',
    end_date='2025-01-31'
)

# Report includes:
# - User summary (total decisions, continue/cancel counts)
# - Percentage of all decisions
# - Recent decisions list
```

### API Usage

#### Get Audit Logs

```bash
# Get all logs
GET /api/audit/logs

# Filter by reference number
GET /api/audit/logs?reference_number=Vendor123

# Filter by date range
GET /api/audit/logs?start_date=2025-01-01&end_date=2025-01-31

# Filter by decision type
GET /api/audit/logs?decision=continue

# Pagination
GET /api/audit/logs?limit=50&offset=100
```

#### Generate Compliance Report

```bash
GET /api/audit/reports/compliance?start_date=2025-01-01&end_date=2025-01-31&include_details=true
```

#### Get User Activity Report

```bash
GET /api/audit/reports/user/user_001?start_date=2025-01-01&end_date=2025-01-31
```

#### Export to CSV

```bash
GET /api/audit/export/csv?start_date=2025-01-01&end_date=2025-01-31
```

#### Get Transaction Audit Trail

```bash
GET /api/audit/transaction-trail?reference_number=Vendor123&transaction_date=2025-01-15&transaction_amount=100.50
```

## Data Retention

### Automatic Cleanup

The audit logging system supports automatic cleanup of old logs based on a retention policy:

```python
# Clean up logs older than 2 years (730 days)
success, deleted_count = audit_logger.cleanup_old_logs(retention_days=730)

print(f"Deleted {deleted_count} old audit log entries")
```

### API Cleanup

```bash
POST /api/audit/cleanup
Content-Type: application/json

{
  "retention_days": 730
}
```

### Recommended Retention Policy

- **Default:** 730 days (2 years)
- **Compliance:** Adjust based on regulatory requirements
- **Storage:** Monitor database size and adjust as needed

## Monitoring

### Health Check

Check the health of the audit logging system:

```bash
GET /api/audit/health
```

Response:

```json
{
  "success": true,
  "status": "healthy",
  "total_logs": 12345,
  "timestamp": "2025-01-15T10:30:00"
}
```

### Metrics to Monitor

1. **Log Volume:** Track the number of audit log entries over time
2. **Decision Ratios:** Monitor continue vs. cancel decision percentages
3. **Top Duplicate Vendors:** Identify vendors with frequent duplicates
4. **User Activity:** Track which users are making decisions
5. **System Health:** Monitor API response times and error rates

## Security Considerations

### Access Control

- Audit log endpoints should be protected with authentication
- Only authorized users should access audit reports
- User IDs should be captured for all decisions

### Data Protection

- Audit logs contain sensitive transaction information
- Implement appropriate access controls
- Consider encryption for sensitive fields
- Follow data privacy regulations (GDPR, etc.)

### Audit Trail Integrity

- Audit logs should be immutable (no updates or deletes except for retention)
- All access to audit logs should be logged
- Regular backups of audit data should be maintained

## Troubleshooting

### Migration Issues

If the migration fails:

1. Check database connectivity
2. Verify user has CREATE TABLE permissions
3. Check if table already exists
4. Review migration logs for specific errors

### Logging Failures

If audit logging fails:

1. Check database connectivity
2. Verify table exists and has correct structure
3. Check for disk space issues
4. Review application logs for errors

### Query Performance

If queries are slow:

1. Verify indexes are created correctly
2. Use date range filters to limit results
3. Implement pagination for large result sets
4. Consider archiving old logs

## Testing

### Unit Tests

Run the comprehensive test suite:

```bash
cd backend
python -m pytest test/test_audit_logger.py -v
```

Test coverage includes:

- Basic logging functionality
- Query operations with various filters
- Report generation
- Data retention
- Error handling
- Edge cases

### Integration Tests

Test the complete workflow:

1. Create a duplicate invoice scenario
2. Make a decision (continue or cancel)
3. Verify the decision is logged
4. Query the audit log
5. Generate a report
6. Verify all data is correct

## Compliance

The audit logging system supports compliance with:

- **SOX (Sarbanes-Oxley):** Complete audit trail of financial transactions
- **GDPR:** Data retention and deletion capabilities
- **ISO 27001:** Security and access control
- **Internal Audit Requirements:** Comprehensive reporting and querying

## Future Enhancements

Potential improvements for the audit logging system:

1. **Real-time Alerts:** Notify administrators of unusual patterns
2. **Advanced Analytics:** Machine learning for duplicate detection patterns
3. **Dashboard:** Visual interface for audit log analysis
4. **Automated Reports:** Scheduled report generation and distribution
5. **Integration:** Connect with external audit systems
6. **Blockchain:** Immutable audit trail using blockchain technology

## Support

For issues or questions about the audit logging system:

1. Check this documentation
2. Review test cases for usage examples
3. Check application logs for errors
4. Contact the development team

## Version History

- **v1.0** (2025-01-15): Initial implementation
  - Basic audit logging
  - Query capabilities
  - Compliance reporting
  - Data retention
  - API endpoints
