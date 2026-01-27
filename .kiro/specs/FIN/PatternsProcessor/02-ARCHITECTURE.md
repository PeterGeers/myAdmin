# Architecture Document

**Version**: 2.0  
**Last Updated**: January 27, 2026

---

## System Overview

The Pattern Processor is a three-tier architecture system consisting of:

1. **Frontend** - React-based UI for transaction processing
2. **Backend** - Python Flask API with pattern analysis engine
3. **Database** - MySQL for transaction and pattern storage

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  BankingProcessor.tsx                                   │ │
│  │  - CSV Upload                                           │ │
│  │  - Pattern Application UI                               │ │
│  │  - Transaction Review & Edit                            │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS/REST API
┌──────────────────────────┴──────────────────────────────────┐
│                         Backend                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Flask API (app.py)                                     │ │
│  │  - /api/banking/apply-patterns                          │ │
│  │  - /api/banking/save-transactions                       │ │
│  │  - /api/patterns/*                                      │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Pattern Analyzer (pattern_analyzer.py)                │ │
│  │  - Verb Extraction                                      │ │
│  │  - Pattern Discovery                                    │ │
│  │  - Pattern Matching                                     │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Pattern Cache (pattern_cache.py)                      │ │
│  │  - Multi-level Caching                                  │ │
│  │  - Cache Invalidation                                   │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │ MySQL Protocol
┌──────────────────────────┴──────────────────────────────────┐
│                        Database                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  mutaties (Transactions)                                │ │
│  │  pattern_verb_patterns (Patterns)                       │ │
│  │  pattern_analysis_metadata (Metadata)                   │ │
│  │  bank_account_lookups (Bank Accounts)                   │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Architecture

### 1. Frontend Layer

#### BankingProcessor Component

**Location**: `frontend/src/components/BankingProcessor.tsx`

**Responsibilities**:

- CSV file upload and parsing
- Transaction display and editing
- Pattern application trigger
- Results visualization
- Transaction save to database

**Key Features**:

- Formik-based form handling
- Real-time validation
- Blue border highlighting for auto-filled fields
- Confidence score display
- Manual override capability

**State Management**:

- `transactions`: Current transaction list
- `patternResults`: Pattern application results
- `patternSuggestions`: Suggested values
- `loading`: Loading state
- `message`: User feedback messages

**API Integration**:

- `POST /api/banking/apply-patterns` - Apply patterns
- `POST /api/banking/save-transactions` - Save to database
- `GET /api/banking/lookups` - Get account lookups

---

### 2. Backend Layer

#### 2.1 Flask API Layer

**Location**: `backend/src/app.py`

**Endpoints**:

##### Pattern Application

```
POST /api/banking/apply-patterns
- Applies patterns to transactions
- Returns updated transactions with predictions
- Includes confidence scores
```

##### Transaction Save

```
POST /api/banking/save-transactions
- Saves transactions to database
- Filters duplicates
- Invalidates pattern cache
```

##### Pattern Analysis

```
POST /api/patterns/analyze/<administration>
- Triggers pattern analysis
- Supports full and incremental modes
- Returns analysis results
```

**Authentication**: Cognito-based JWT authentication  
**Authorization**: Role-based permissions (banking_process, transactions_create)

---

#### 2.2 Pattern Analyzer

**Location**: `backend/src/pattern_analyzer.py`

**Core Classes**:

##### PatternAnalyzer

Main class for pattern analysis and application.

**Key Methods**:

```python
analyze_historical_patterns(administration, filters)
# Analyzes last 2 years of transactions
# Returns discovered patterns

apply_patterns_to_transactions(transactions, administration)
# Applies patterns to predict missing fields
# Returns updated transactions and results

get_filtered_patterns(administration, filters)
# Retrieves patterns with caching
# Returns cached or fresh patterns
```

**Pattern Discovery Flow**:

1. Query transactions from last 2 years
2. Extract verbs from descriptions
3. Create pattern keys (admin + bank + verb)
4. Store patterns with metadata
5. Calculate confidence scores

**Pattern Application Flow**:

1. Load patterns from cache/database
2. For each transaction:
   - Extract verb from description
   - Match against patterns
   - Predict missing fields
   - Calculate confidence
3. Return updated transactions

---

#### 2.3 Verb Extraction Engine

**Location**: `backend/src/pattern_analyzer.py` - `_extract_company_name()`

**Algorithm**:

```
Input: Transaction Description
    ↓
1. Convert to uppercase
    ↓
2. Check known company patterns (BOOKING, AIRBNB, etc.)
    ↓
3. Remove banking noise words
    ↓
4. Remove transaction codes (IBANs, dates, etc.)
    ↓
5. Extract words (3-25 chars, alphanumeric)
    ↓
6. Filter noise words (THE, AND, VAN, etc.)
    ↓
7. Filter transaction IDs (long alphanumeric codes)
    ↓
8. Validate word patterns:
   - Acronyms (3-5 chars, no vowels): PASS
   - Regular words: Must have vowels
    ↓
9. Return first meaningful word
    ↓
Output: Verb (Company/Vendor name)
```

**Edge Cases Handled**:

- Digit-starting names: `2THELOO`, `123INKT`
- Long names: `VERZEKERINGSBANK` (25 char limit)
- Acronyms: `SVB`, `KPN`, `NS` (no vowel requirement)
- Transaction codes: Filtered out by pattern matching

---

#### 2.4 Pattern Cache

**Location**: `backend/src/pattern_cache.py`

**Multi-Level Caching**:

```
Level 1: Memory Cache (Python dict)
    ↓ (miss)
Level 2: Database Cache (pattern_verb_patterns table)
    ↓ (miss)
Level 3: File Cache (cache/*.json)
    ↓ (miss)
Full Analysis (10 seconds)
```

**Cache Invalidation**:

- Triggered on transaction save
- Clears memory and file cache
- Forces re-analysis on next pattern application

**Cache Warming**:

- Loads patterns from database on startup
- Populates memory cache
- Reduces first-request latency

---

### 3. Database Layer

#### Schema Design

##### mutaties (Transactions)

```sql
CREATE TABLE mutaties (
    id INT PRIMARY KEY AUTO_INCREMENT,
    administration VARCHAR(50),
    TransactionDate DATE,
    TransactionDescription TEXT,
    ReferenceNumber VARCHAR(255),
    Debet VARCHAR(20),
    Credit VARCHAR(20),
    TransactionAmount DECIMAL(10,2),
    Ref1 VARCHAR(50),  -- IBAN
    Ref2 VARCHAR(50),  -- Sequence
    INDEX idx_admin_date (administration, TransactionDate),
    INDEX idx_ref1_ref2 (Ref1, Ref2)
);
```

##### pattern_verb_patterns (Patterns)

```sql
CREATE TABLE pattern_verb_patterns (
    administration VARCHAR(50),
    bank_account VARCHAR(20),
    verb VARCHAR(100),
    verb_company VARCHAR(100),
    verb_reference VARCHAR(100),
    is_compound BOOLEAN,
    reference_number VARCHAR(255),
    debet_account VARCHAR(20),
    credit_account VARCHAR(20),
    occurrences INT DEFAULT 1,
    confidence DECIMAL(3,2),
    last_seen DATE,
    sample_description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (administration, bank_account, verb),
    INDEX idx_admin (administration),
    INDEX idx_verb (verb)
);
```

##### pattern_analysis_metadata (Metadata)

```sql
CREATE TABLE pattern_analysis_metadata (
    administration VARCHAR(50) PRIMARY KEY,
    last_analysis_date TIMESTAMP,
    transactions_analyzed INT,
    patterns_discovered INT,
    date_range_from DATE,
    date_range_to DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

---

## Data Flow

### Pattern Discovery Flow

```
1. User saves transactions
    ↓
2. Cache invalidated
    ↓
3. User loads new CSV
    ↓
4. User clicks "Apply Patterns"
    ↓
5. Backend checks cache (MISS)
    ↓
6. Query last 2 years of transactions
    ↓
7. For each transaction:
   - Extract verb
   - Create pattern key
   - Store/update in memory
    ↓
8. UPSERT patterns to database
   - Existing: Update occurrences
   - New: Insert pattern
    ↓
9. Update metadata table
    ↓
10. Cache patterns in memory/file
    ↓
11. Return patterns to application logic
```

### Pattern Application Flow

```
1. User clicks "Apply Patterns"
    ↓
2. Frontend sends transactions to backend
    ↓
3. Backend loads patterns (from cache)
    ↓
4. For each transaction:
   a. Extract verb from description
   b. Build pattern key
   c. Lookup in patterns
   d. If found:
      - Check confidence (>80%)
      - Predict missing fields
      - Add confidence score
    ↓
5. Return updated transactions
    ↓
6. Frontend displays:
   - Blue borders on predicted fields
   - Confidence scores
   - Prediction counts
    ↓
7. User reviews and edits
    ↓
8. User saves to database
```

---

## Design Patterns

### 1. Repository Pattern

**Pattern Cache** acts as a repository for patterns, abstracting storage details.

**Benefits**:

- Decouples business logic from storage
- Enables multi-level caching
- Simplifies testing

### 2. Strategy Pattern

**Verb Extraction** uses multiple strategies (known patterns, word extraction, filtering).

**Benefits**:

- Flexible extraction logic
- Easy to add new strategies
- Handles edge cases

### 3. UPSERT Pattern

**Pattern Storage** uses INSERT ... ON DUPLICATE KEY UPDATE.

**Benefits**:

- No data loss
- Atomic operations
- Incremental updates

### 4. Cache-Aside Pattern

**Pattern Cache** loads on-demand and invalidates on changes.

**Benefits**:

- Reduces database load
- Fast repeated access
- Automatic refresh

---

## Scalability Considerations

### Horizontal Scaling

- **Frontend**: Stateless, can scale with load balancer
- **Backend**: Stateless API, can add more instances
- **Database**: Master-slave replication for read scaling

### Vertical Scaling

- **Pattern Analysis**: CPU-intensive, benefits from more cores
- **Database**: Memory-intensive, benefits from more RAM
- **Cache**: Memory-intensive, benefits from more RAM

### Performance Optimization

- **Indexing**: Database indexes on pattern keys
- **Caching**: Multi-level cache reduces database hits
- **Batch Processing**: Bulk UPSERT for pattern storage
- **Connection Pooling**: Reuse database connections

---

## Security Architecture

### Authentication

- **Cognito JWT**: Token-based authentication
- **Token Validation**: Every API request validated
- **Token Expiry**: Automatic refresh

### Authorization

- **Role-Based**: Permissions per endpoint
- **Tenant Isolation**: Administration-based filtering
- **SQL Injection Prevention**: Parameterized queries

### Data Protection

- **HTTPS**: Encrypted transport
- **No PII in Patterns**: Only account numbers and verbs
- **Audit Logging**: Track pattern changes

---

## Monitoring & Observability

### Metrics

- Pattern analysis time
- Pattern application time
- Cache hit rate
- Success rate (predictions)
- Error rate

### Logging

- Pattern discovery events
- Cache invalidation events
- API request/response
- Error stack traces

### Alerts

- Analysis time >15 seconds
- Success rate <90%
- Cache hit rate <80%
- Database connection errors

---

## Deployment Architecture

### Docker Containers

```
┌─────────────────────────────────────┐
│  myadmin-backend-1                  │
│  - Flask API                        │
│  - Pattern Analyzer                 │
│  - Port: 5000                       │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  myadmin-mysql-1                    │
│  - MySQL 8.0                        │
│  - Port: 3306                       │
│  - Volume: ./mysql_data             │
└─────────────────────────────────────┘
```

### File Structure

```
backend/
├── src/
│   ├── app.py                    # Flask API
│   ├── pattern_analyzer.py      # Core engine
│   ├── pattern_cache.py         # Caching
│   ├── banking_processor.py     # Transaction processing
│   ├── database.py              # Database manager
│   └── pattern_storage_routes.py # Pattern API
├── cache/                        # File cache
└── requirements.txt

frontend/
├── src/
│   └── components/
│       └── BankingProcessor.tsx # Main UI
└── build/                        # Production build
```

---

## Technology Stack

### Frontend

- **React** 18.x - UI framework
- **TypeScript** - Type safety
- **Chakra UI** - Component library
- **Formik** - Form handling
- **Axios** - HTTP client

### Backend

- **Python** 3.9+ - Programming language
- **Flask** - Web framework
- **MySQL Connector** - Database driver
- **Pandas** - Data processing

### Database

- **MySQL** 8.0 - Relational database
- **InnoDB** - Storage engine

### DevOps

- **Docker** - Containerization
- **Docker Compose** - Multi-container orchestration

---

## References

- **Requirements**: See `01-REQUIREMENTS.md`
- **Implementation**: See `03-IMPLEMENTATION.md`
- **User Guide**: See `04-USER-GUIDE.md`
- **API Reference**: See `05-API-REFERENCE.md`
