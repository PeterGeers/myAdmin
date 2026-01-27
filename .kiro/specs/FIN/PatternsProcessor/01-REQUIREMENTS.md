# Requirements Document

**Version**: 2.0  
**Last Updated**: January 27, 2026

---

## Business Requirements

### BR-001: Automatic Transaction Processing

**Priority**: High  
**Status**: ✅ Implemented

The system shall automatically predict missing transaction fields based on historical patterns to reduce manual data entry.

**Acceptance Criteria**:

- Predict ReferenceNumber from transaction description
- Predict Debet account when Credit is a bank account
- Predict Credit account when Debet is a bank account
- Achieve >90% accuracy on known transactions

**Current Status**: 92% success rate achieved

---

### BR-002: Learning from Historical Data

**Priority**: High  
**Status**: ✅ Implemented

The system shall learn patterns from the last 2 years of transaction data.

**Acceptance Criteria**:

- Analyze transactions from last 730 days
- Create patterns from complete and valid transactions
- Update patterns when new data is added
- Preserve historical patterns (no data loss)

**Current Status**: Analyzes 2 years, UPSERT-based updates

---

### BR-003: Immediate Learning

**Priority**: Medium  
**Status**: ✅ Implemented

The system shall learn from the first occurrence of a new transaction pattern.

**Acceptance Criteria**:

- Create pattern after 1 occurrence (not 2+)
- Apply pattern to future transactions immediately
- Allow manual correction to improve patterns

**Current Status**: Minimum occurrence = 1

---

### BR-004: Multi-Administration Support

**Priority**: High  
**Status**: ✅ Implemented

The system shall maintain separate patterns for each administration.

**Acceptance Criteria**:

- Patterns isolated by administration
- No cross-contamination between administrations
- Support multiple administrations simultaneously

**Current Status**: Fully isolated by administration

---

## Technical Requirements

### TR-001: Pattern Analysis Engine

**Priority**: High  
**Status**: ✅ Implemented

**Requirements**:

- Extract company/vendor names from transaction descriptions
- Handle edge cases: digits, long names, acronyms, special characters
- Create unique pattern keys: Administration + BankAccount + Verb
- Store patterns in database with metadata

**Implementation**: `backend/src/pattern_analyzer.py`

**Key Features**:

- Verb extraction with 25-character limit
- Support for digit-starting names (2Theloo, 123Inkt)
- Acronym support without vowel requirement (SVB, KPN, NS)
- Transaction code filtering

---

### TR-002: Bank Account Logic

**Priority**: High  
**Status**: ✅ Implemented

**Requirements**:

- Identify bank accounts from lookup table
- Apply patterns only when one side is a bank account
- Predict opposite account based on bank account + verb

**Implementation**:

- `backend/src/pattern_analyzer.py` - `is_bank_account()` method
- `backend/src/database.py` - `get_bank_account_lookups()` method

**Logic**:

- If Credit = Bank Account → Predict Debet
- If Debet = Bank Account → Predict Credit
- If neither is bank account → No prediction

---

### TR-003: Pattern Storage

**Priority**: High  
**Status**: ✅ Implemented

**Requirements**:

- Store patterns in relational database
- Use UPSERT logic (no deletion)
- Track occurrence counts and confidence scores
- Maintain analysis metadata

**Implementation**:

- Database table: `pattern_verb_patterns`
- Metadata table: `pattern_analysis_metadata`
- UPSERT query: `INSERT ... ON DUPLICATE KEY UPDATE`

**Schema**:

```
pattern_verb_patterns:
- administration (PK)
- bank_account (PK)
- verb (PK)
- verb_company
- verb_reference
- is_compound
- reference_number
- debet_account
- credit_account
- occurrences
- confidence
- last_seen
- sample_description
```

---

### TR-004: Performance Optimization

**Priority**: Medium  
**Status**: ✅ Implemented

**Requirements**:

- Multi-level caching (memory, database, file)
- Cache invalidation on data changes
- Fast pattern lookup (<100ms)
- Efficient bulk processing

**Implementation**:

- `backend/src/pattern_cache.py` - Persistent cache
- Cache invalidation on transaction save
- Database indexing on pattern keys

**Performance**:

- Cache hit: <0.1 seconds
- Cache miss: ~10 seconds (full analysis)
- Pattern application: <1 second for 50 transactions

---

### TR-005: Pattern Matching Algorithm

**Priority**: High  
**Status**: ✅ Implemented

**Requirements**:

- Exact verb matching (primary)
- Confidence scoring based on occurrences
- Conflict resolution for multiple matches
- Minimum confidence threshold (80%)

**Implementation**: `backend/src/pattern_analyzer.py`

**Matching Strategy**:

1. Extract verb from transaction description
2. Build pattern key: `{administration}_{bank_account}_{verb}`
3. Lookup in pattern table
4. Return prediction with confidence score

**Conflict Resolution**:

1. Most recent pattern (last_seen date)
2. Highest frequency (occurrences)
3. Amount similarity
4. Account number descending

---

### TR-006: Frontend Integration

**Priority**: High  
**Status**: ✅ Implemented

**Requirements**:

- Display pattern predictions in UI
- Show confidence scores
- Highlight auto-filled fields (blue borders)
- Allow manual override

**Implementation**: `frontend/src/components/BankingProcessor.tsx`

**UI Features**:

- Pattern Application Results card
- Prediction counts (Debet, Credit, Reference)
- Average confidence percentage
- Blue borders on predicted fields
- Manual edit capability

---

## Functional Requirements

### FR-001: Verb Extraction

**Priority**: High  
**Status**: ✅ Implemented

Extract company/vendor names from transaction descriptions.

**Rules**:

- Remove banking noise words (BETAALVERZOEK, INCASSOOPDRACHT, etc.)
- Remove transaction codes (IBANs, dates, times)
- Extract meaningful words (3-25 characters)
- Support digits at start (2Theloo)
- Support acronyms (SVB, KPN, NS)
- Filter transaction IDs

**Implementation**: `backend/src/pattern_analyzer.py` - `_extract_company_name()`

---

### FR-002: Pattern Creation

**Priority**: High  
**Status**: ✅ Implemented

Create patterns from complete transactions.

**Rules**:

- Require: ReferenceNumber, Debet OR Credit, Bank Account
- Pattern key: Administration + BankAccount + Verb (company only)
- Store: reference_number, debet_account, credit_account
- Track: occurrences, confidence, last_seen

**Implementation**: `backend/src/pattern_analyzer.py` - `_analyze_reference_patterns()`

---

### FR-003: Pattern Application

**Priority**: High  
**Status**: ✅ Implemented

Apply patterns to predict missing fields.

**Rules**:

- Only predict empty fields (don't overwrite)
- Require minimum 80% confidence
- Use most recent pattern for conflicts
- Return prediction with confidence score

**Implementation**: `backend/src/pattern_analyzer.py` - `apply_patterns_to_transactions()`

---

### FR-004: Pattern Updates

**Priority**: High  
**Status**: ✅ Implemented

Update patterns when new transactions are saved.

**Rules**:

- Invalidate cache on transaction save
- Re-analyze on next "Apply Patterns" click
- UPSERT patterns (update existing, add new)
- Increment occurrence counts

**Implementation**:

- `backend/src/app.py` - `banking_save_transactions()` - Cache invalidation
- `backend/src/pattern_analyzer.py` - `analyze_historical_patterns()` - Re-analysis

---

## Non-Functional Requirements

### NFR-001: Performance

- Pattern analysis: <15 seconds for 3,000 transactions
- Pattern application: <2 seconds for 100 transactions
- Cache hit: <100ms
- Database queries: <500ms

**Status**: ✅ Met (10 seconds for 2,700 transactions)

---

### NFR-002: Reliability

- 99% uptime for pattern service
- No data loss on updates (UPSERT)
- Graceful degradation on errors
- Transaction rollback on failures

**Status**: ✅ Implemented

---

### NFR-003: Scalability

- Support 10,000+ transactions per administration
- Support 10+ administrations
- Handle 1,000+ patterns per administration
- Concurrent user access

**Status**: ✅ Tested with 2,700 transactions, 630 patterns

---

### NFR-004: Maintainability

- Clean code structure
- Comprehensive documentation
- Unit tests for core functions
- API versioning

**Status**: ✅ Documented, tests in progress

---

### NFR-005: Security

- Authentication required for all endpoints
- Tenant isolation (no cross-administration access)
- SQL injection prevention (parameterized queries)
- Input validation

**Status**: ✅ Implemented with Cognito authentication

---

## Success Criteria

### Accuracy

- ✅ >90% success rate on known transactions (Current: 92%)
- ✅ <10% false positives
- ✅ Confidence scores >80% for predictions

### Performance

- ✅ Pattern analysis <15 seconds
- ✅ Pattern application <2 seconds
- ✅ Cache hit <100ms

### Usability

- ✅ Auto-fill reduces manual entry by >80%
- ✅ Clear visual indicators (blue borders)
- ✅ Confidence scores displayed

### Reliability

- ✅ No data loss on updates
- ✅ Patterns persist across restarts
- ✅ Graceful error handling

---

## Future Enhancements

### Phase 2 (Planned)

- [ ] Machine learning for verb extraction
- [ ] Pattern confidence tuning based on feedback
- [ ] Manual pattern creation UI
- [ ] Pattern review and edit interface
- [ ] Export/import patterns between administrations

### Phase 3 (Proposed)

- [ ] Multi-language support
- [ ] Advanced analytics dashboard
- [ ] Pattern recommendation engine
- [ ] Automated pattern cleanup (remove obsolete)

---

## Compliance & Standards

### Data Privacy

- GDPR compliant (no PII in patterns)
- Data retention: 2 years for analysis
- User consent for pattern learning

### Code Standards

- Python PEP 8 style guide
- TypeScript ESLint rules
- SQL best practices (parameterized queries)

### Testing Standards

- Unit test coverage >80%
- Integration tests for critical paths
- Manual testing for UI workflows

---

## References

- **Architecture**: See `02-ARCHITECTURE.md`
- **Implementation**: See `03-IMPLEMENTATION.md`
- **API Reference**: See `05-API-REFERENCE.md`
- **Testing**: See `06-TESTING.md`
