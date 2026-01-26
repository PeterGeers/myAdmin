# Security Analysis Scripts

This directory contains security analysis and validation scripts created during the STR Reports code review and validation process.

## Scripts Overview

### Security Analysis

- **`security_analysis.py`** - Comprehensive SQL injection vulnerability scanner
- **`manual_security_review.py`** - Focused manual security review tool
- **`error_security_analysis.py`** - Error handling security analyzer

### Error Handling Analysis

- **`error_consistency_analysis.py`** - Detailed error handling consistency analyzer
- **`simple_consistency_check.py`** - Quick consistency check tool

### Performance Analysis

- **`tenant_performance_analysis.py`** - Tenant filtering performance analyzer

### Fix Implementation

- **`secure_error_handling.py`** - Automated security fix application tool

## Usage

### Running Security Analysis

```bash
# Comprehensive SQL injection scan
python backend/scripts/security_analysis/security_analysis.py

# Manual security review
python backend/scripts/security_analysis/manual_security_review.py

# Error handling security check
python backend/scripts/security_analysis/error_security_analysis.py
```

### Running Consistency Analysis

```bash
# Detailed consistency analysis
python backend/scripts/security_analysis/error_consistency_analysis.py

# Quick consistency check
python backend/scripts/security_analysis/simple_consistency_check.py
```

### Running Performance Analysis

```bash
# Tenant filtering performance review
python backend/scripts/security_analysis/tenant_performance_analysis.py
```

### Applying Security Fixes

```bash
# Apply secure error handling fixes
python backend/scripts/security_analysis/secure_error_handling.py
```

## Output Files

These scripts generate various output files:

- `backend/docs/sql_security_report.txt` - Detailed security analysis report
- `backend/docs/code_review_summary.md` - Comprehensive review summary
- Backup files (\*.backup) - Created when applying fixes

## Requirements

- Python 3.7+
- Access to backend source files
- Write permissions for creating reports and backups

## Integration

These scripts were used during the implementation of task 15 "Code review and validation" and can be run periodically to maintain code quality and security standards.

## Related Documentation

- `backend/docs/code_review_summary.md` - Complete review results
- `backend/docs/performance_optimization_recommendations.sql` - Database optimization guide
- `.kiro/specs/STR/Reports/tasks.md` - Original task specifications
