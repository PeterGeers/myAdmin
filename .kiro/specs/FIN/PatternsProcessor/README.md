# Pattern Processor Documentation

**Version**: 2.0  
**Last Updated**: January 27, 2026  
**Status**: Production Ready  
**Success Rate**: 92%

---

## Overview

The Pattern Processor is an intelligent system that learns from historical banking transactions to automatically predict missing account numbers and reference information. It analyzes transaction patterns over the last 2 years and applies machine learning-like pattern matching to new transactions.

---

## Quick Links

- **[Requirements](./01-REQUIREMENTS.md)** - Business and technical requirements
- **[Architecture](./02-ARCHITECTURE.md)** - System design and components
- **[Implementation](./03-IMPLEMENTATION.md)** - Technical implementation details
- **[User Guide](./04-USER-GUIDE.md)** - How to use the system
- **[API Reference](./05-API-REFERENCE.md)** - API endpoints and usage

---

## Key Features

### Automatic Pattern Learning

- Learns from historical transactions (last 2 years)
- Creates patterns after first occurrence
- Updates patterns with new data automatically

### Intelligent Predictions

- **ReferenceNumber**: Predicts based on company/vendor name
- **Debet Account**: Predicts when Credit is a bank account
- **Credit Account**: Predicts when Debet is a bank account

### High Accuracy

- 92% success rate on test data (11/12 transactions)
- Handles edge cases: digit-starting names, long names, acronyms
- Confidence scoring for predictions

### Performance Optimized

- Multi-level caching (memory, database, file)
- UPSERT-based updates (no data loss)
- Processes ~2,700 transactions in ~10 seconds

---

## System Components

### Backend

- **Pattern Analyzer** (`backend/src/pattern_analyzer.py`) - Core pattern analysis engine
- **Banking Processor** (`backend/src/banking_processor.py`) - Transaction processing
- **Database Manager** (`backend/src/database.py`) - Database operations
- **Pattern Cache** (`backend/src/pattern_cache.py`) - Multi-level caching

### Frontend

- **Banking Processor UI** (`frontend/src/components/BankingProcessor.tsx`) - Main interface
- **Pattern Display** - Shows prediction results and confidence scores

### Database

- **pattern_verb_patterns** - Stores discovered patterns
- **pattern_analysis_metadata** - Tracks analysis history
- **mutaties** - Transaction data

---

## How It Works

### 1. Pattern Discovery

```
Historical Transactions (2 years)
    ↓
Verb Extraction (Company/Vendor names)
    ↓
Pattern Creation (Administration + BankAccount + Verb)
    ↓
Database Storage (pattern_verb_patterns table)
```

### 2. Pattern Application

```
New Transaction
    ↓
Extract Verb from Description
    ↓
Match Against Patterns
    ↓
Predict Missing Fields
    ↓
Display with Confidence Score
```

### 3. Pattern Updates

```
Save Transactions
    ↓
Cache Invalidated
    ↓
Next "Apply Patterns" Click
    ↓
Re-analyze All Transactions
    ↓
UPSERT Patterns (Update existing, Add new)
```

---

## Recent Improvements (January 2026)

### Pattern Consolidation

- Reduced patterns from 3,258 to 630 (81% reduction)
- Fixed compound verb over-specificity
- Now uses company name only for pattern keys

### Verb Extraction Enhancements

- ✅ Supports digit-starting company names (2Theloo, 123Inkt)
- ✅ Increased word length limit to 25 characters (VERZEKERINGSBANK)
- ✅ Allows acronyms without vowels (SVB, KPN, NS)
- ✅ Better transaction code filtering

### Learning Improvements

- Changed minimum occurrence from 2 to 1
- System now learns from first manual entry
- Immediate pattern creation for new vendors

### Frontend Fixes

- Corrected data mapping for pattern results
- Now displays accurate prediction counts
- Shows confidence scores properly

---

## Performance Metrics

| Metric         | Value                                       |
| -------------- | ------------------------------------------- |
| Success Rate   | 92% (11/12 transactions)                    |
| Pattern Count  | 630 (GoodwinSolutions: 92, PeterPrive: 538) |
| Analysis Time  | ~10 seconds for 2,700 transactions          |
| Cache Hit Rate | >95% for repeated operations                |
| Data Reduction | 81% fewer patterns vs. old system           |

---

## Getting Started

### For Users

1. Load CSV file with transactions
2. Click "Apply Patterns" to get predictions
3. Review and edit predictions (blue borders = auto-filled)
4. Save transactions to database
5. Patterns automatically update on next use

### For Developers

1. Review [Architecture](./02-ARCHITECTURE.md) for system design
2. Check [Implementation](./03-IMPLEMENTATION.md) for code details
3. See [API Reference](./05-API-REFERENCE.md) for endpoints
4. Run tests from [Testing](./06-TESTING.md) guide

---

## Support & Maintenance

### Monitoring

- Check pattern count: Should grow gradually over time
- Monitor success rate: Should stay above 90%
- Review failed predictions: Identify new edge cases

### Troubleshooting

- **No predictions**: Check if patterns exist for administration
- **Low confidence**: May need more historical data
- **Wrong predictions**: Review and correct manually (system learns)

### Updates

- Patterns update automatically with normal usage
- Manual refresh: Call `/api/patterns/analyze/<administration>`
- Incremental update: Use `{"incremental": true}` for fast updates

---

## Documentation Structure

```
.kiro/specs/FIN/PatternsProcessor/
├── README.md (this file)
├── 01-REQUIREMENTS.md
├── 02-ARCHITECTURE.md
├── 03-IMPLEMENTATION.md
├── 04-USER-GUIDE.md
├── 05-API-REFERENCE.md
├── 06-TESTING.md
└── Testdata/
    ├── CSV_O_accounts_20260126_212603.csv
    ├── LoadedData.csv
    └── verb_patterns.csv
```

---

## Version History

### Version 2.0 (January 27, 2026)

- Fixed compound verb over-specificity
- Enhanced verb extraction (digits, long names, acronyms)
- Changed minimum occurrence to 1
- Fixed frontend data mapping
- Achieved 92% success rate

### Version 1.0 (Initial Release)

- Basic pattern analysis
- 95% success rate initially
- Degraded to <30% over 2 months due to bugs

---

## License & Contact

Part of the myAdmin Banking Processor system.

For questions or issues, refer to the detailed documentation files or contact the development team.
