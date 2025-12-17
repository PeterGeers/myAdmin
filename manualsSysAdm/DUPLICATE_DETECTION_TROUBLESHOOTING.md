# Duplicate Invoice Detection - Troubleshooting Guide

## Overview

This guide provides detailed troubleshooting procedures for common issues with the duplicate invoice detection system. It's designed for system administrators and support personnel.

**Requirements Addressed:** 6.1, 6.2, 6.3, 6.4, 6.5

## Table of Contents

1. [Quick Diagnostic Checklist](#quick-diagnostic-checklist)
2. [Performance Issues](#performance-issues)
3. [False Positives and False Negatives](#false-positives-and-false-negatives)
4. [File Cleanup Issues](#file-cleanup-issues)
5. [Database Connection Problems](#database-connection-problems)
6. [Audit Logging Issues](#audit-logging-issues)
7. [User Interface Problems](#user-interface-problems)
8. [Integration Issues](#integration-issues)
9. [Common Error Messages](#common-error-messages)
10. [Advanced Diagnostics](#advanced-diagnostics)

## Quick Diagnostic Checklist

When troubleshooting duplicate detection issues, start with this checklist:

### System Health Check

```bash
# 1. Check database connectivity
cd backend
python -c "from database import DatabaseManager; db = DatabaseManager(); print('DB OK' if db.test_connection() else 'DB FAIL')"

# 2. Check audit system health
curl http://localhost:5000/api/audit/health

# 3. Check recent error logs
tail -50 backend/logs/error.log | grep -i "duplicate\|cleanup\|audit"

# 4. Verify indexes exist
mysql -u username -p database_name -e "SHOW INDEX FROM mutaties WHERE Key_name LIKE 'idx_duplicate%';"

# 5. Check Google Drive connectivity
python -c "from google_drive_service import GoogleDriveService; drive = GoogleDriveService(); print('Drive OK' if drive.test_connection() else 'Drive FAIL')"
```

### Quick Status Check

```sql
-- Check recent duplicate detections
SELECT COUNT(*) as recent_duplicates
FROM duplicate_decision_log
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR);

-- Check decision distribution
SELECT
    decision,
    COUNT(*) as count
FROM duplicate_decision_log
WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY decision;
```

## Performance Issues

### Issue 1: Slow Duplicate Detection (> 3 seconds)

**Symptoms:**

- Duplicate check takes longer than expected
- User interface becomes unresponsive
- Timeout errors in logs

**Diagnostic Steps:**

```sql
-- 1. Check if indexes are being used
EXPLAIN SELECT * FROM mutaties
WHERE ReferenceNumber = 'Booking.com'
AND TransactionDate = '2024-12-15'
AND TransactionAmount = 121.00
AND TransactionDate > DATE_SUB(CURDATE(), INTERVAL 2 YEAR);

-- Look for "Using index" in the Extra column
-- If you see "Using filesort" or "Using temporary", indexes aren't being used properly

-- 2. Check index statistics
SHOW INDEX FROM mutaties WHERE Key_name LIKE 'idx_duplicate%';

-- 3. Check table size
SELECT
    COUNT(*) as total_rows,
    COUNT(CASE WHEN TransactionDate > DATE_SUB(CURDATE(), INTERVAL 2 YEAR) THEN 1 END) as recent_rows
FROM mutaties;

-- 4. Check for table fragmentation
SHOW TABLE STATUS LIKE 'mutaties';
```

**Solutions:**

1. **Rebuild Indexes**

   ```sql
   ALTER TABLE mutaties DROP INDEX idx_duplicate_detection;
   ALTER TABLE mutaties ADD INDEX idx_duplicate_detection (ReferenceNumber, TransactionDate, TransactionAmount);
   ANALYZE TABLE mutaties;
   ```

2. **Update Table Statistics**

   ```sql
   ANALYZE TABLE mutaties;
   ```

3. **Check Database Server Load**

   ```bash
   # Check MySQL process list
   mysql -u username -p -e "SHOW PROCESSLIST;"

   # Check slow query log
   mysql -u username -p -e "SHOW VARIABLES LIKE 'slow_query%';"
   ```

4. **Increase Connection Pool**

   ```python
   # In database.py
   POOL_SIZE = 20  # Increase from 10
   MAX_OVERFLOW = 40  # Increase from 20
   ```

5. **Optimize Query**
   ```python
   # Add query timeout
   cursor.execute(query, params, timeout=5)
   ```

### Issue 2: High Memory Usage

**Symptoms:**

- Server memory usage increases during duplicate checks
- Out of memory errors
- System slowdown

**Diagnostic Steps:**

```bash
# Check Python process memory
ps aux | grep python | awk '{print $6/1024 " MB\t" $11}'

# Monitor memory during duplicate check
watch -n 1 'ps aux | grep python'
```

**Solutions:**

1. **Limit Result Set Size**

   ```python
   # Add LIMIT to query
   query = """
       SELECT * FROM mutaties
       WHERE ReferenceNumber = %s
       AND TransactionDate = %s
       AND TransactionAmount = %s
       AND TransactionDate > DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
       ORDER BY ID DESC
       LIMIT 100
   """
   ```

2. **Use Cursor Iteration**

   ```python
   # Instead of fetchall(), use cursor iteration
   for row in cursor:
       process_row(row)
   ```

3. **Clear Cache Regularly**
   ```python
   # Clear database connection cache
   db.clear_cache()
   ```

## False Positives and False Negatives

### Issue 3: Legitimate Transactions Flagged as Duplicates

**Symptoms:**

- Users frequently choose "Continue" on duplicate warnings
- Multiple legitimate transactions with same date/amount
- Complaints about unnecessary warnings

**Diagnostic Steps:**

```sql
-- Find patterns in continued duplicates
SELECT
    reference_number,
    transaction_date,
    transaction_amount,
    COUNT(*) as occurrences,
    GROUP_CONCAT(existing_transaction_id) as transaction_ids
FROM duplicate_decision_log
WHERE decision = 'continue'
AND timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY reference_number, transaction_date, transaction_amount
HAVING COUNT(*) > 3
ORDER BY occurrences DESC;

-- Check specific vendor patterns
SELECT
    m1.ID,
    m1.TransactionDate,
    m1.TransactionAmount,
    m1.Ref1 as accommodation,
    m1.Ref2 as invoice_number
FROM mutaties m1
WHERE m1.ReferenceNumber = 'Booking.com'
AND EXISTS (
    SELECT 1 FROM mutaties m2
    WHERE m2.ReferenceNumber = m1.ReferenceNumber
    AND m2.TransactionDate = m1.TransactionDate
    AND m2.TransactionAmount = m1.TransactionAmount
    AND m2.ID != m1.ID
)
ORDER BY m1.TransactionDate DESC, m1.ID;
```

**Solutions:**

1. **For Booking.com Multiple Properties**

   ```python
   # Enhance duplicate check to include Ref1 (accommodation)
   def check_for_duplicates_enhanced(self, reference_number, transaction_date,
                                     transaction_amount, ref1=None):
       query = """
           SELECT * FROM mutaties
           WHERE ReferenceNumber = %s
           AND TransactionDate = %s
           AND TransactionAmount = %s
           AND TransactionDate > DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
       """
       params = [reference_number, transaction_date, transaction_amount]

       # Add Ref1 check for Booking.com
       if reference_number.lower() == 'booking.com' and ref1:
           query += " AND Ref1 = %s"
           params.append(ref1)

       return self.db.execute_query(query, params)
   ```

2. **Document Common Patterns**

   - Create a knowledge base of legitimate duplicate scenarios
   - Train users on when to continue vs cancel
   - Add tooltips in UI explaining common cases

3. **Adjust Detection Logic**
   ```python
   # Add vendor-specific rules
   VENDOR_RULES = {
       'Booking.com': {
           'check_ref1': True,  # Check accommodation name
           'check_ref2': True,  # Check invoice number
       },
       'Netflix': {
           'check_ref2': True,  # Check receipt number
       }
   }
   ```

### Issue 4: Actual Duplicates Not Detected

**Symptoms:**

- Duplicate transactions in database
- No warning shown during import
- Users report seeing duplicates after import

**Diagnostic Steps:**

```sql
-- Find actual duplicates in database
SELECT
    ReferenceNumber,
    TransactionDate,
    TransactionAmount,
    COUNT(*) as duplicate_count,
    GROUP_CONCAT(ID) as transaction_ids
FROM mutaties
WHERE TransactionDate > DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
GROUP BY ReferenceNumber, TransactionDate, TransactionAmount
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, TransactionDate DESC;

-- Check if these were logged
SELECT * FROM duplicate_decision_log
WHERE reference_number = 'VendorName'
AND transaction_date = '2024-12-15'
AND transaction_amount = 121.00;
```

**Solutions:**

1. **Check Date Format Consistency**

   ```python
   # Ensure consistent date format
   from datetime import datetime

   def normalize_date(date_str):
       # Handle various date formats
       formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']
       for fmt in formats:
           try:
               dt = datetime.strptime(date_str, fmt)
               return dt.strftime('%Y-%m-%d')
           except ValueError:
               continue
       raise ValueError(f"Unable to parse date: {date_str}")
   ```

2. **Check Amount Precision**

   ```python
   # Ensure consistent amount precision
   def normalize_amount(amount):
       return round(float(amount), 2)
   ```

3. **Verify Detection is Called**

   ```python
   # Add logging to verify duplicate check is executed
   logger.info(f"Checking for duplicates: {reference_number}, {transaction_date}, {transaction_amount}")
   duplicates = duplicate_checker.check_for_duplicates(...)
   logger.info(f"Found {len(duplicates)} duplicates")
   ```

4. **Check Search Window**
   ```sql
   -- Verify transaction is within 2-year window
   SELECT
       TransactionDate,
       DATEDIFF(CURDATE(), TransactionDate) as days_ago,
       CASE
           WHEN DATEDIFF(CURDATE(), TransactionDate) <= 730 THEN 'Within Window'
           ELSE 'Outside Window'
       END as status
   FROM mutaties
   WHERE ID = 12345;
   ```

## File Cleanup Issues

### Issue 5: Files Not Being Deleted

**Symptoms:**

- Orphaned files in Google Drive
- Storage quota warnings
- Files remain after cancel decision

**Diagnostic Steps:**

```bash
# Check file cleanup logs
grep "File cleanup" backend/logs/error.log | tail -50

# Check Google Drive API status
python -c "
from google_drive_service import GoogleDriveService
drive = GoogleDriveService()
print('Connected' if drive.test_connection() else 'Failed')
"

# List recent file operations
grep "file.*delete\|file.*remove" backend/logs/error.log | tail -20
```

**Solutions:**

1. **Verify Google Drive Credentials**

   ```bash
   # Check credentials file exists
   ls -la backend/credentials.json
   ls -la backend/token.json

   # Re-authenticate if needed
   cd backend
   python -c "from google_drive_service import GoogleDriveService; GoogleDriveService().authenticate()"
   ```

2. **Check File Permissions**

   ```python
   # Test file deletion
   from file_cleanup_manager import FileCleanupManager

   cleanup = FileCleanupManager()
   result = cleanup.cleanup_uploaded_file(
       file_url='https://drive.google.com/file/d/FILE_ID',
       file_id='FILE_ID'
   )
   print(f"Cleanup result: {result}")
   ```

3. **Implement Retry Logic**

   ```python
   def cleanup_with_retry(file_url, file_id, max_retries=3):
       for attempt in range(max_retries):
           try:
               result = cleanup_uploaded_file(file_url, file_id)
               if result:
                   return True
               time.sleep(2 ** attempt)  # Exponential backoff
           except Exception as e:
               logger.error(f"Cleanup attempt {attempt + 1} failed: {e}")
       return False
   ```

4. **Manual Cleanup Script**

   ```python
   # cleanup_orphaned_files.py
   from google_drive_service import GoogleDriveService
   from database import DatabaseManager

   drive = GoogleDriveService()
   db = DatabaseManager()

   # Get all file IDs from database
   query = "SELECT DISTINCT Ref3 FROM mutaties WHERE Ref3 LIKE '%drive.google.com%'"
   db_files = set([extract_file_id(row['Ref3']) for row in db.execute_query(query)])

   # Get all files from Google Drive
   drive_files = drive.list_all_files()

   # Find orphaned files
   orphaned = [f for f in drive_files if f['id'] not in db_files]

   print(f"Found {len(orphaned)} orphaned files")
   for file in orphaned:
       print(f"  - {file['name']} ({file['id']})")
   ```

### Issue 6: Wrong Files Being Deleted

**Symptoms:**

- Files referenced by existing transactions are deleted
- Users report missing invoice files
- Broken file links in database

**Diagnostic Steps:**

```sql
-- Find transactions with missing files
SELECT
    ID,
    ReferenceNumber,
    TransactionDate,
    Ref3 as file_url
FROM mutaties
WHERE Ref3 LIKE '%drive.google.com%'
AND TransactionDate > DATE_SUB(CURDATE(), INTERVAL 90 DAY)
ORDER BY TransactionDate DESC;

-- Check audit log for file cleanup decisions
SELECT * FROM duplicate_decision_log
WHERE decision = 'cancel'
AND new_file_url IS NOT NULL
ORDER BY timestamp DESC
LIMIT 50;
```

**Solutions:**

1. **Verify URL Comparison Logic**

   ```python
   def should_cleanup_file(new_url, existing_url):
       # Extract file IDs for comparison
       new_id = extract_file_id(new_url)
       existing_id = extract_file_id(existing_url)

       # Only cleanup if URLs are different
       if new_id and existing_id:
           return new_id != existing_id

       # If we can't determine, don't cleanup (safe default)
       return False
   ```

2. **Add Safety Checks**

   ```python
   def cleanup_uploaded_file(file_url, file_id):
       # Check if file is referenced by any transaction
       query = "SELECT COUNT(*) as count FROM mutaties WHERE Ref3 LIKE %s"
       result = db.execute_query(query, [f"%{file_id}%"])

       if result[0]['count'] > 0:
           logger.warning(f"File {file_id} is referenced by {result[0]['count']} transactions. Skipping cleanup.")
           return False

       # Proceed with cleanup
       return drive_service.delete_file(file_id)
   ```

3. **Implement Soft Delete**

   ```python
   # Move to trash instead of permanent delete
   def soft_delete_file(file_id):
       return drive_service.trash_file(file_id)

   # Permanent delete only after confirmation period
   def permanent_delete_old_trash(days=30):
       return drive_service.empty_trash(older_than_days=days)
   ```

## Database Connection Problems

### Issue 7: Connection Timeouts

**Symptoms:**

- "Database connection timeout" errors
- Intermittent duplicate check failures
- Connection pool exhaustion

**Diagnostic Steps:**

```bash
# Check active connections
mysql -u username -p -e "SHOW PROCESSLIST;"

# Check connection pool status
python -c "
from database import DatabaseManager
db = DatabaseManager()
print(f'Pool size: {db.pool.size()}')
print(f'Checked out: {db.pool.checkedout()}')
"

# Check for connection leaks
grep "connection" backend/logs/error.log | grep -i "timeout\|leak\|exhaust"
```

**Solutions:**

1. **Increase Connection Pool**

   ```python
   # In database.py
   POOL_SIZE = 20
   MAX_OVERFLOW = 40
   POOL_TIMEOUT = 60
   ```

2. **Implement Connection Retry**

   ```python
   def execute_with_retry(query, params, max_retries=3):
       for attempt in range(max_retries):
           try:
               return db.execute_query(query, params)
           except OperationalError as e:
               if attempt < max_retries - 1:
                   logger.warning(f"Connection failed, retrying... ({attempt + 1}/{max_retries})")
                   time.sleep(2 ** attempt)
               else:
                   raise
   ```

3. **Close Connections Properly**

   ```python
   # Use context manager
   with DatabaseManager() as db:
       result = db.execute_query(query, params)
   # Connection automatically closed
   ```

4. **Monitor Connection Health**
   ```python
   def check_connection_health():
       try:
           db.execute_query("SELECT 1")
           return True
       except Exception as e:
           logger.error(f"Connection health check failed: {e}")
           return False
   ```

### Issue 8: Deadlocks

**Symptoms:**

- "Deadlock detected" errors
- Transactions failing intermittently
- Slow duplicate checks during high load

**Diagnostic Steps:**

```sql
-- Check for deadlocks
SHOW ENGINE INNODB STATUS;

-- Look for "LATEST DETECTED DEADLOCK" section

-- Check transaction isolation level
SELECT @@transaction_isolation;

-- Monitor lock waits
SELECT * FROM information_schema.INNODB_LOCKS;
SELECT * FROM information_schema.INNODB_LOCK_WAITS;
```

**Solutions:**

1. **Use Consistent Lock Order**

   ```python
   # Always lock tables in the same order
   # 1. mutaties
   # 2. duplicate_decision_log
   ```

2. **Reduce Transaction Scope**

   ```python
   # Keep transactions short
   with db.transaction():
       # Only critical operations here
       result = db.execute_query(query, params)
   # Transaction committed automatically
   ```

3. **Implement Deadlock Retry**
   ```python
   def execute_with_deadlock_retry(query, params, max_retries=3):
       for attempt in range(max_retries):
           try:
               return db.execute_query(query, params)
           except OperationalError as e:
               if "deadlock" in str(e).lower() and attempt < max_retries - 1:
                   logger.warning(f"Deadlock detected, retrying... ({attempt + 1}/{max_retries})")
                   time.sleep(0.1 * (2 ** attempt))
               else:
                   raise
   ```

## Audit Logging Issues

### Issue 9: Missing Audit Log Entries

**Symptoms:**

- Gaps in audit trail
- Decision count mismatches
- Incomplete compliance reports

**Diagnostic Steps:**

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
SELECT
    DATE(TransactionDate) as date,
    COUNT(*) as transaction_count
FROM mutaties
WHERE TransactionDate >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(TransactionDate)
ORDER BY date DESC;

-- Check for failed audit log inserts
SELECT * FROM error_log
WHERE error_message LIKE '%audit%'
ORDER BY timestamp DESC
LIMIT 50;
```

**Solutions:**

1. **Verify Audit Logger is Called**

   ```python
   # Add explicit logging
   logger.info("Logging duplicate decision to audit trail")
   success = audit_logger.log_decision(...)
   if not success:
       logger.error("Failed to log decision to audit trail")
   ```

2. **Implement Audit Log Retry**

   ```python
   def log_decision_with_retry(self, *args, **kwargs):
       max_retries = 3
       for attempt in range(max_retries):
           try:
               return self.log_decision(*args, **kwargs)
           except Exception as e:
               if attempt < max_retries - 1:
                   logger.warning(f"Audit log failed, retrying... ({attempt + 1}/{max_retries})")
                   time.sleep(1)
               else:
                   logger.error(f"Audit log failed after {max_retries} attempts: {e}")
                   return False
   ```

3. **Queue Failed Logs**

   ```python
   # Store failed logs in queue for retry
   failed_logs_queue = []

   def log_decision_with_queue(self, *args, **kwargs):
       try:
           return self.log_decision(*args, **kwargs)
       except Exception as e:
           logger.error(f"Audit log failed, adding to queue: {e}")
           failed_logs_queue.append({
               'args': args,
               'kwargs': kwargs,
               'timestamp': datetime.now()
           })
           return False

   def retry_failed_logs():
       while failed_logs_queue:
           log_data = failed_logs_queue.pop(0)
           try:
               audit_logger.log_decision(*log_data['args'], **log_data['kwargs'])
           except Exception as e:
               logger.error(f"Retry failed: {e}")
               failed_logs_queue.append(log_data)
               break
   ```

4. **Monitor Audit Log Health**
   ```python
   def check_audit_log_health():
       # Check recent log entries
       query = """
           SELECT COUNT(*) as count
           FROM duplicate_decision_log
           WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
       """
       result = db.execute_query(query)

       if result[0]['count'] == 0:
           logger.warning("No audit log entries in the last hour")
           return False
       return True
   ```

## User Interface Problems

### Issue 10: Dialog Not Appearing

**Symptoms:**

- Duplicate warning dialog doesn't show
- Import proceeds without warning
- Users report not seeing warnings

**Diagnostic Steps:**

```javascript
// Check browser console for errors
console.log("Duplicate check response:", response);

// Verify API response
fetch("/api/check-duplicate", {
  method: "POST",
  body: JSON.stringify(transactionData),
})
  .then((res) => res.json())
  .then((data) => console.log("Duplicate data:", data));

// Check component state
console.log("Dialog state:", {
  isOpen: this.state.isDialogOpen,
  duplicateInfo: this.state.duplicateInfo,
});
```

**Solutions:**

1. **Verify API Response**

   ```python
   # Ensure proper response format
   return jsonify({
       'has_duplicates': True,
       'duplicate_count': len(duplicates),
       'existing_transactions': duplicates,
       'requires_user_decision': True
   })
   ```

2. **Check Frontend State Management**

   ```javascript
   // Ensure state is updated correctly
   if (response.has_duplicates) {
     this.setState({
       isDialogOpen: true,
       duplicateInfo: response,
     });
   }
   ```

3. **Add Error Handling**
   ```javascript
   try {
     const response = await checkForDuplicates(transactionData);
     if (response.has_duplicates) {
       showDuplicateDialog(response);
     }
   } catch (error) {
     console.error("Duplicate check failed:", error);
     showErrorMessage("Unable to check for duplicates. Please try again.");
   }
   ```

### Issue 11: Dialog Freezing or Unresponsive

**Symptoms:**

- Dialog appears but buttons don't work
- Cannot close or interact with dialog
- Browser becomes unresponsive

**Diagnostic Steps:**

```javascript
// Check for JavaScript errors
console.error = (function (originalError) {
  return function (message) {
    console.log("Error captured:", message);
    originalError.apply(console, arguments);
  };
})(console.error);

// Check event listeners
console.log(
  "Continue button listeners:",
  getEventListeners(document.getElementById("continue-button"))
);

// Monitor performance
console.time("Dialog render");
// Render dialog
console.timeEnd("Dialog render");
```

**Solutions:**

1. **Optimize Dialog Rendering**

   ```javascript
   // Use React.memo to prevent unnecessary re-renders
   const DuplicateWarningDialog = React.memo(
     ({ isOpen, duplicateInfo, onContinue, onCancel }) => {
       // Component code
     }
   );
   ```

2. **Add Loading States**

   ```javascript
   const [isProcessing, setIsProcessing] = useState(false);

   const handleContinue = async () => {
     setIsProcessing(true);
     try {
       await processContinueDecision();
     } finally {
       setIsProcessing(false);
     }
   };
   ```

3. **Implement Timeout Protection**

   ```javascript
   const DECISION_TIMEOUT = 300000; // 5 minutes

   useEffect(() => {
     if (isOpen) {
       const timeout = setTimeout(() => {
         showWarning("Session timeout. Please refresh and try again.");
         onCancel();
       }, DECISION_TIMEOUT);

       return () => clearTimeout(timeout);
     }
   }, [isOpen]);
   ```

## Integration Issues

### Issue 12: Vendor Parser Compatibility

**Symptoms:**

- Duplicate detection fails for specific vendors
- Incorrect data extraction
- Missing reference fields

**Diagnostic Steps:**

```python
# Test vendor parser
from vendor_parsers import parse_vendor_data

test_data = {
    'vendor': 'Booking.com',
    'text_lines': [...],
    'file_path': 'test.pdf'
}

result = parse_vendor_data(test_data)
print(f"Parsed data: {result}")

# Check required fields
required_fields = ['date', 'total_amount', 'reference_number']
missing_fields = [f for f in required_fields if f not in result or not result[f]]
if missing_fields:
    print(f"Missing fields: {missing_fields}")
```

**Solutions:**

1. **Enhance Vendor Parser**

   ```python
   # Add fallback extraction
   def parse_booking_com(text_lines):
       data = {}

       # Primary extraction
       data['date'] = extract_date_primary(text_lines)

       # Fallback if primary fails
       if not data['date']:
           data['date'] = extract_date_fallback(text_lines)

       return data
   ```

2. **Add Validation**

   ```python
   def validate_parsed_data(data, vendor):
       required_fields = VENDOR_REQUIRED_FIELDS.get(vendor, [])

       for field in required_fields:
           if field not in data or not data[field]:
               raise ValueError(f"Missing required field: {field}")

       return True
   ```

3. **Log Parser Issues**

   ```python
   logger.info(f"Parsing {vendor} invoice")
   parsed_data = parse_vendor_data(vendor, text_lines)
   logger.info(f"Parsed fields: {list(parsed_data.keys())}")

   if not validate_parsed_data(parsed_data, vendor):
       logger.error(f"Validation failed for {vendor}")
   ```

## Common Error Messages

### Error: "Database connection failed during duplicate check"

**Cause:** Database server is unreachable or credentials are incorrect

**Solution:**

```bash
# Check database connectivity
mysql -u username -p -h hostname database_name -e "SELECT 1;"

# Verify credentials in .env file
cat backend/.env | grep DB_

# Test connection from Python
python -c "from database import DatabaseManager; print(DatabaseManager().test_connection())"
```

### Error: "Duplicate check timeout"

**Cause:** Query is taking too long (> 5 seconds)

**Solution:**

```sql
-- Check query performance
EXPLAIN SELECT * FROM mutaties
WHERE ReferenceNumber = 'Vendor'
AND TransactionDate = '2024-12-15'
AND TransactionAmount = 121.00
AND TransactionDate > DATE_SUB(CURDATE(), INTERVAL 2 YEAR);

-- Rebuild indexes if needed
ALTER TABLE mutaties DROP INDEX idx_duplicate_detection;
ALTER TABLE mutaties ADD INDEX idx_duplicate_detection (ReferenceNumber, TransactionDate, TransactionAmount);
ANALYZE TABLE mutaties;
```

### Error: "File cleanup failed: Permission denied"

**Cause:** Insufficient permissions to delete file from Google Drive

**Solution:**

```python
# Re-authenticate with Google Drive
from google_drive_service import GoogleDriveService
drive = GoogleDriveService()
drive.authenticate()

# Check file permissions
file_info = drive.get_file_info(file_id)
print(f"File permissions: {file_info.get('permissions', [])}")
```

### Error: "Audit log insert failed"

**Cause:** Database permissions or table doesn't exist

**Solution:**

```sql
-- Check if table exists
SHOW TABLES LIKE 'duplicate_decision_log';

-- Check permissions
SHOW GRANTS FOR 'username'@'hostname';

-- Re-apply migration if needed
SOURCE backend/src/migrations/20251217130000_duplicate_decision_audit_log.sql;
```

## Advanced Diagnostics

### Enable Debug Logging

```python
# In app.py or config.py
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backend/logs/debug.log'),
        logging.StreamHandler()
    ]
)

# Enable SQL query logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

### Performance Profiling

```python
# Profile duplicate check performance
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Run duplicate check
duplicate_checker.check_for_duplicates(...)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

### Database Query Analysis

```sql
-- Enable slow query log
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 1;
SET GLOBAL slow_query_log_file = '/var/log/mysql/slow-query.log';

-- Analyze slow queries
SELECT * FROM mysql.slow_log
WHERE sql_text LIKE '%mutaties%'
ORDER BY query_time DESC
LIMIT 10;
```

### Network Diagnostics

```bash
# Test API endpoint response time
time curl -X POST http://localhost:5000/api/check-duplicate \
  -H "Content-Type: application/json" \
  -d '{"reference_number":"Booking.com","transaction_date":"2024-12-15","transaction_amount":121.00}'

# Monitor network traffic
tcpdump -i any port 3306 -w mysql_traffic.pcap

# Analyze with Wireshark
wireshark mysql_traffic.pcap
```

## Getting Help

If you've tried the troubleshooting steps and still have issues:

1. **Collect Diagnostic Information**

   - Error logs (last 100 lines)
   - Database query explain plans
   - System resource usage
   - Recent audit log entries

2. **Document the Issue**

   - What were you trying to do?
   - What happened instead?
   - What troubleshooting steps did you try?
   - Can you reproduce the issue?

3. **Contact Support**
   - Email: support@example.com
   - Include diagnostic information
   - Provide steps to reproduce
   - Specify urgency level

---

**Document Version:** 1.0  
**Last Updated:** December 17, 2024  
**Next Review:** March 17, 2025
