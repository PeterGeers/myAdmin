# Design Document

## Overview

The duplicate invoice detection system will integrate seamlessly into the existing PDF processing workflow to prevent duplicate transactions from being created in the accounting system. The design focuses on early detection during the import process, clear user communication, and intelligent file management.

The system will extend the existing `pdf_processor.py` workflow by adding a duplicate check step after data extraction but before database insertion, ensuring minimal impact on performance while providing comprehensive duplicate prevention.

## Architecture

### Component Structure

```
Duplicate Detection System
├── DuplicateDetector (Backend)
│   ├── duplicate_checker.py
│   └── DatabaseManager extensions
├── DuplicateWarningDialog (Frontend)
│   ├── DuplicateInfo display
│   ├── ActionButtons (Continue/Cancel)
│   └── LoadingStates
└── FileCleanupManager (Backend)
    ├── URL comparison logic
    └── File removal operations
```

### Integration Points

The system will integrate with existing components:

- **PDF Processor**: Add duplicate check in `_format_vendor_transactions()` method
- **Database Manager**: Extend with `check_duplicate_transactions()` method
- **AI Extractor**: Maintain compatibility with AI-extracted invoice data
- **File Storage**: Integrate with existing file upload and storage system
- **Frontend**: Add duplicate warning dialog component

### Workflow Integration

```
Invoice Import Flow:
1. File Upload → 2. Data Extraction → 3. **DUPLICATE CHECK** → 4. User Decision → 5. Transaction Processing
                                           ↓
                                    [If duplicate found]
                                           ↓
                                    Show Warning Dialog
                                           ↓
                                    User Choice: Continue/Cancel
                                           ↓
                                    [Continue: Process] [Cancel: Cleanup]
```

## Components and Interfaces

### DuplicateChecker Class

```python
class DuplicateChecker:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def check_for_duplicates(
        self,
        reference_number: str,
        transaction_date: str,
        transaction_amount: float,
        table_name: str = 'mutaties'
    ) -> List[Dict]:
        """Check for duplicate transactions and return matches"""

    def format_duplicate_info(self, duplicates: List[Dict]) -> Dict:
        """Format duplicate information for frontend display"""

    def log_duplicate_decision(
        self,
        decision: str,
        duplicate_info: Dict,
        user_id: str = None
    ) -> None:
        """Log user decision for audit trail"""
```

### DatabaseManager Extensions

```python
# Add to existing DatabaseManager class
def check_duplicate_transactions(
    self,
    reference_number: str,
    transaction_date: str,
    transaction_amount: float,
    table_name: str = 'mutaties'
) -> List[Dict]:
    """Check for existing transactions with matching criteria"""
    query = f"""
        SELECT * FROM {table_name}
        WHERE ReferenceNumber = %s
        AND TransactionDate = %s
        AND TransactionAmount = %s
        AND TransactionDate > (CURDATE() - INTERVAL 2 YEAR)
        ORDER BY ID DESC
    """
    return self.execute_query(query, (reference_number, transaction_date, transaction_amount))
```

### FileCleanupManager Class

```python
class FileCleanupManager:
    def __init__(self, storage_config):
        self.storage_config = storage_config

    def should_cleanup_file(self, new_url: str, existing_url: str) -> bool:
        """Determine if file cleanup is needed based on URL comparison"""

    def cleanup_uploaded_file(self, file_url: str, file_id: str) -> bool:
        """Remove uploaded file and return success status"""

    def get_file_path_from_url(self, url: str) -> str:
        """Extract local file path from Google Drive or storage URL"""
```

### Frontend DuplicateWarningDialog Component

```typescript
interface DuplicateWarningProps {
  isOpen: boolean;
  duplicateInfo: {
    existingTransaction: Transaction;
    newTransaction: Transaction;
    matchCount: number;
  };
  onContinue: () => void;
  onCancel: () => void;
  isLoading?: boolean;
}

interface Transaction {
  id: string;
  transactionDate: string;
  transactionDescription: string;
  transactionAmount: number;
  debet: string;
  credit: string;
  referenceNumber: string;
  ref1?: string;
  ref2?: string;
  ref3?: string; // File URL
  ref4?: string;
}
```

## Data Models

### Duplicate Check Request

```python
@dataclass
class DuplicateCheckRequest:
    reference_number: str
    transaction_date: str
    transaction_amount: float
    new_file_url: str
    new_file_id: str
    table_name: str = 'mutaties'
```

### Duplicate Check Response

```python
@dataclass
class DuplicateCheckResponse:
    has_duplicates: bool
    duplicate_count: int
    existing_transactions: List[Dict]
    requires_user_decision: bool
    error_message: Optional[str] = None
```

### User Decision Log

```python
@dataclass
class DuplicateDecisionLog:
    timestamp: datetime
    reference_number: str
    transaction_date: str
    transaction_amount: float
    decision: str  # 'continue' or 'cancel'
    existing_transaction_id: int
    new_file_url: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
```

## Correctness Properties

_A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees._

### Property Reflection

After analyzing the acceptance criteria, I identified several testable properties:

### Property 1: Duplicate Detection Accuracy

_For any_ valid transaction with ReferenceNumber, TransactionDate, and TransactionAmount, the duplicate checker should correctly identify all matching existing transactions within the 2-year window and return accurate match information
**Validates: Requirements 1.1, 1.3, 1.4**

### Property 2: User Decision Processing Consistency

_For any_ user decision (continue or cancel), the system should execute the appropriate workflow (normal processing for continue, cleanup for cancel) while maintaining data integrity and logging the decision appropriately
**Validates: Requirements 3.1, 3.2, 3.3, 4.1, 4.4**

### Property 3: File Management Correctness

_For any_ duplicate cancellation scenario, the file cleanup manager should correctly determine whether to remove files based on URL comparison and execute cleanup operations atomically without affecting other system files
**Validates: Requirements 4.2, 4.3, 4.4**

### Property 4: Integration Compatibility

_For any_ existing PDF processing workflow (AI extraction, vendor parsers, file types), the duplicate detection should integrate seamlessly without breaking existing functionality or significantly impacting performance
**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

### Property 5: Error Handling Robustness

_For any_ error condition (database failures, file system errors, network issues, session timeouts), the system should handle errors gracefully, provide appropriate user feedback, maintain audit trails, and prevent data corruption
**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

### Property 6: User Interface Consistency

_For any_ duplicate warning scenario, the interface should display information clearly, provide intuitive controls, maintain consistent styling with existing myAdmin components, and prevent conflicting user actions
**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 7.1, 7.2, 7.3, 7.4, 7.5**

## Error Handling

### Error Scenarios

1. **Database Connection Failures**: When duplicate check query fails
2. **File System Errors**: When file cleanup operations fail
3. **Invalid Transaction Data**: When extracted data is malformed
4. **Session Timeouts**: When user takes too long to decide
5. **Concurrent Access**: When multiple users process same invoice simultaneously

### Error Recovery Strategies

- **Graceful Degradation**: Allow import to continue with warning if duplicate check fails
- **Retry Logic**: Implement retry for transient database connection issues
- **Atomic Operations**: Ensure file cleanup is all-or-nothing
- **User Notification**: Provide clear error messages and recovery options
- **Audit Logging**: Log all errors for system monitoring and debugging

## Performance Considerations

### Database Optimization

- **Indexed Queries**: Ensure proper indexes on ReferenceNumber, TransactionDate, TransactionAmount
- **Query Limits**: Limit search to 2-year window for performance
- **Connection Pooling**: Use existing database connection pool

### File Operations

- **Async Cleanup**: Perform file cleanup operations asynchronously when possible
- **Batch Operations**: Group multiple file operations when applicable
- **Error Recovery**: Implement cleanup retry logic for failed operations

### Frontend Performance

- **Lazy Loading**: Load duplicate dialog component only when needed
- **Caching**: Cache duplicate check results during user decision process
- **Debouncing**: Prevent multiple simultaneous duplicate checks

## Security Considerations

### Data Protection

- **Input Validation**: Validate all transaction data before duplicate checking
- **SQL Injection Prevention**: Use parameterized queries for all database operations
- **File Path Validation**: Validate file paths before cleanup operations

### Access Control

- **User Authentication**: Ensure only authenticated users can make duplicate decisions
- **Audit Logging**: Log all duplicate decisions with user identification
- **Session Management**: Handle session timeouts securely

## Testing Strategy

### Unit Testing Approach

Unit tests will focus on:

- Duplicate detection logic with various transaction combinations
- File cleanup logic with different URL scenarios
- Error handling for all failure modes
- Database query correctness and performance
- Frontend component rendering and interaction

### Property-Based Testing Approach

Property-based tests will use **pytest** with **hypothesis** for backend components and **React Testing Library** with **@fast-check/jest** for frontend components.

**Backend Property Test Requirements:**

- Generate realistic transaction data with various duplicate scenarios
- Test duplicate detection across different time ranges and amounts
- Validate file cleanup logic with various URL combinations
- Test error handling with simulated failure conditions

**Frontend Property Test Requirements:**

- Generate various duplicate information scenarios
- Test user interaction flows and state management
- Validate accessibility and keyboard navigation
- Test loading states and error conditions

### Integration Testing

Integration tests will verify:

- End-to-end duplicate detection workflow
- Database integration with existing schema
- File system integration with existing storage
- Frontend-backend communication
- Performance impact on existing import workflows
