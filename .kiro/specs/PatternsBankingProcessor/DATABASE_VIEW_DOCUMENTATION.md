# Database View Documentation

## Overview

This document provides comprehensive documentation for all database views in the myAdmin Banking Processor system, with a focus on the `vw_readreferences` view used for pattern analysis and transaction processing.

---

## vw_readreferences

### Purpose

The `vw_readreferences` view is the **primary data source for pattern analysis** in the banking processor system. It provides historical transaction patterns that are used to predict missing account numbers (Debet/Credit) and reference numbers for new banking transactions.

### Business Context

When processing banking transactions, users often need to categorize transactions by assigning:

- **Debet account**: The account being debited
- **Credit account**: The account being credited
- **Reference number**: A categorization code for the transaction type

The `vw_readreferences` view contains historical patterns learned from past transactions, enabling the system to suggest these values automatically based on transaction descriptions and other attributes.

### Structure

| Column Name       | Data Type | Description                                                |
| ----------------- | --------- | ---------------------------------------------------------- |
| `debet`           | VARCHAR   | Debet account number (typically < 1300 for bank accounts)  |
| `credit`          | VARCHAR   | Credit account number (typically < 1300 for bank accounts) |
| `administration`  | VARCHAR   | Administration/company identifier for multi-tenant support |
| `referenceNumber` | VARCHAR   | Transaction reference/category code                        |
| `Date`            | DATE      | Transaction date (used for filtering recent patterns)      |

### Usage

#### Primary Use Case: Pattern Matching

The view is queried by the `get_patterns()` method in `database.py` to retrieve historical patterns for a specific administration:

```python
def get_patterns(self, administration):
    """Get patterns from vw_readreferences view with date filtering"""
    return self.execute_query("""
        SELECT debet, credit, administration, referenceNumber, Date
        FROM vw_readreferences
        WHERE administration = %s
        AND (debet < '1300' OR credit < '1300')
        AND Date >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)
        ORDER BY Date DESC
    """, (administration,))
```

#### Query Filters

1. **Administration Filter**: `WHERE administration = %s`

   - Ensures patterns are specific to each company/administration
   - Supports multi-tenant architecture

2. **Bank Account Filter**: `AND (debet < '1300' OR credit < '1300')`

   - Focuses on patterns involving bank accounts
   - Account numbers < 1300 are typically bank accounts in the chart of accounts
   - Ensures at least one side of the transaction is a bank account

3. **Date Filter**: `AND Date >= DATE_SUB(CURDATE(), INTERVAL 2 YEAR)`

   - Limits patterns to the last 2 years
   - Ensures patterns are recent and relevant
   - Improves performance by reducing result set
   - Addresses requirement REQ-DATA-001

4. **Sorting**: `ORDER BY Date DESC`
   - Most recent patterns appear first
   - Prioritizes current business practices over historical ones

### Pattern Matching Logic

The banking processor uses patterns from this view to predict missing values:

1. **When Debet is a bank account** (< 1300):

   - System looks up patterns where `debet` matches the bank account
   - Suggests the corresponding `credit` account from historical patterns
   - Suggests the `referenceNumber` associated with this pattern

2. **When Credit is a bank account** (< 1300):

   - System looks up patterns where `credit` matches the bank account
   - Suggests the corresponding `debet` account from historical patterns
   - Suggests the `referenceNumber` associated with this pattern

3. **Matching Criteria**:
   - Transaction description similarity
   - Same administration
   - Same bank account (debet or credit)
   - Recent patterns (within 2 years)

### Data Quality

- **Record Count**: Approximately 1,511 records (as of consolidation)
- **Date Range**: Contains transactions from 2021-12-24 to 2028-12-31
- **Active Range**: Filtered to last 2 years in queries (currently 2023-12-21 to 2025-12-18)
- **Data Source**: Derived from the `mutaties` (transactions) table

### Performance Considerations

1. **Indexing**: The view should have indexes on:

   - `administration` (for filtering)
   - `Date` (for date range filtering)
   - `debet` and `credit` (for pattern lookups)

2. **Query Optimization**:

   - Date filtering reduces result set significantly
   - Bank account filter (< 1300) further limits results
   - Sorting by date DESC prioritizes recent patterns

3. **Caching**: Pattern results can be cached per administration to reduce database load (see REQ-PAT-006)

### Historical Context

#### Consolidation History

- **Before December 2025**: Two duplicate views existed

  - `vw_ReadReferences` (capital R): 5,214 records, no Date column
  - `vw_readreferences` (lowercase): 1,511 records, with Date column

- **After Consolidation**: Single view retained
  - `vw_readreferences` (lowercase) was chosen
  - Reasons: Has Date column, follows naming conventions, appears to be curated dataset
  - Old view `vw_ReadReferences` was dropped

#### Code Updates

- Updated `database.py` to use `vw_readreferences`
- Added Date column to SELECT statements
- Added 2-year date filtering
- Added ORDER BY Date DESC for recency

### Requirements Addressed

- **REQ-DB-001**: View identification and selection completed
- **REQ-DB-002**: Case sensitivity determined (lowercase preferred)
- **REQ-DB-004**: Purpose and structure documented (this document)
- **REQ-DB-005**: Consolidated to single view with documentation
- **REQ-DATA-001**: 2-year historical data filtering implemented
- **REQ-DATA-002**: Administration filtering for multi-tenant support
- **REQ-PAT-001**: Supports analysis of last 2 years of transactions
- **REQ-PAT-002**: Supports filtering by Administration, ReferenceNumber, Debet/Credit, and Date

### Related Files

- **Implementation**: `backend/src/database.py` - `get_patterns()` method
- **Consolidation Script**: `backend/consolidate_database_views.py`
- **Verification Script**: `backend/verify_consolidation.py`
- **Documentation**: `backend/DATABASE_VIEW_CONSOLIDATION_SUMMARY.md`
- **Naming Convention**: `backend/VIEW_NAMING_CONVENTION_COMPLETION.md`

### Future Enhancements

1. **Pattern Effectiveness Tracking** (REQ-PAT-008):

   - Track which patterns are used most frequently
   - Measure prediction accuracy per pattern
   - Identify patterns that need review or updating

2. **Pattern Management Interface** (REQ-PAT-007):

   - Allow administrators to review patterns
   - Enable manual pattern editing or removal
   - Add new patterns manually

3. **Confidence Scoring** (REQ-UI-006):

   - Calculate confidence scores based on pattern frequency
   - Show confidence levels to users
   - Allow users to accept/reject suggestions

4. **Machine Learning Integration**:
   - Use ML to improve pattern matching accuracy
   - Learn from user corrections
   - Adapt to changing business practices

---

## Other Database Views

### vw_mutaties

**Purpose**: Provides a view of all transactions (mutaties) with calculated fields and joins.

**Usage**: General transaction queries and reporting.

### vw_debetmutaties

**Purpose**: Filtered view showing only debet-side transactions.

**Usage**: Debet-specific reporting and analysis.

### vw_creditmutaties

**Purpose**: Filtered view showing only credit-side transactions.

**Usage**: Credit-specific reporting and analysis.

### vw_rekeningschema

**Purpose**: Chart of accounts view with account hierarchy and descriptions.

**Usage**: Account lookups, validation, and reporting.

### vw_rekeningnummers

**Purpose**: Account numbers with additional metadata.

**Usage**: Account validation and lookup operations.

### vw_beginbalans

**Purpose**: Opening balance view for accounts.

**Usage**: Balance sheet calculations and reporting.

### vw_reservationcode

**Purpose**: Reservation codes for short-term rental (STR) processing.

**Usage**: STR invoice generation and booking management.

### bnbtotal

**Purpose**: Aggregated Airbnb/booking data.

**Usage**: STR reporting and analytics.

### lookupbankaccounts_r

**Purpose**: Bank account lookup table with reference data.

**Usage**: Bank account validation and pattern matching.

---

## Naming Conventions

All database views follow these conventions:

1. **Lowercase naming**: All view names use lowercase letters
2. **Underscore separators**: Use underscores for word separation (e.g., `vw_read_references`)
3. **Prefix convention**: Most views use `vw_` prefix to indicate they are views
4. **Descriptive names**: Names clearly indicate the view's purpose

---

## Maintenance

### Regular Tasks

1. **Monitor view performance**: Check query execution times
2. **Review data quality**: Ensure patterns are accurate and relevant
3. **Update documentation**: Keep this document current with any changes
4. **Verify indexes**: Ensure proper indexing for optimal performance

### Change Management

When modifying views:

1. **Create backup**: Always backup current view definition
2. **Test in staging**: Test changes in non-production environment
3. **Update documentation**: Update this document with changes
4. **Update dependent code**: Ensure all code using the view is updated
5. **Verify functionality**: Run end-to-end tests after changes

---

**Document Version**: 1.0  
**Last Updated**: December 19, 2025  
**Maintained By**: Development Team  
**Review Schedule**: Quarterly or after significant changes
