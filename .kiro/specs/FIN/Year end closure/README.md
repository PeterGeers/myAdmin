# Year-End Closure Feature

**Status**: ✅ Complete and Deployed  
**Last Updated**: March 3, 2026

## Documentation

This folder contains all documentation for the Year-End Closure feature:

### For End Users

- **[USER_GUIDE.md](USER_GUIDE.md)** - Complete user documentation with step-by-step instructions for closing and reopening years

### For System Administrators

- **[ADMIN_GUIDE.md](ADMIN_GUIDE.md)** - System configuration, bulk operations, database queries, and troubleshooting

### For Developers

- **[requirements.md](requirements.md)** - Business requirements and acceptance criteria
- **[design-closure.md](design-closure.md)** - Technical design, architecture, and API specifications
- **[TASKS-closure.md](TASKS-closure.md)** - Implementation tasks and completion checklist
- **[Performance Issues.md](Performance%20Issues.md)** - Cache optimization implementation and results

## Overview

The Year-End Closure feature allows formal closing of fiscal years, creating opening balance transactions for the next year and improving report performance.

## Key Features

- Sequential year closure with validation
- Automatic opening balance creation
- VAT account netting support
- Performance optimization (94% reduction in cached data)
- Integration with Aangifte IB report
- Comprehensive audit trail

## Access

**Location**: FIN Rapporten → Aangifte IB → Jaarafsluiting section (bottom of report)

**Permissions**:

- View: Finance_Read
- Close/Reopen: Finance_CRUD

## Configuration

Required accounts per tenant (configured in Tenant Admin):

1. Equity Result Account (VW=N) - e.g., 3080
2. P&L Closing Account (VW=Y) - e.g., 8099

Optional: VAT netting configuration for accounts 2010, 2020, 2021

## Documentation Structure

The Year-End Closure documentation has been streamlined to 7 essential files:

1. **README.md** (this file) - Overview and navigation guide
2. **USER_GUIDE.md** - End user documentation with step-by-step instructions
3. **ADMIN_GUIDE.md** - Administrator guide for configuration and troubleshooting
4. **requirements.md** - Business requirements and acceptance criteria
5. **design-closure.md** - Technical design, architecture, and API specifications
6. **TASKS-closure.md** - Implementation tasks and completion checklist
7. **Performance Issues.md** - Cache optimization implementation and results

All phase summaries, bug fix documents, and historical analysis files have been removed. Essential information has been consolidated into the core documents above.

## Recent Changes (March 3, 2026)

1. **Documentation Cleanup**: Removed 25 redundant files, consolidated to 7 core documents
2. Fixed year selector to show all years (not just cached years)
3. Fixed VAT netting boolean type handling
4. Added pagination to Mutaties query (1000 records default)
5. Optimized cache to load only open years + last closed year (94% reduction)
6. Fixed BTW report to show current year only with opening balance

## Support

For issues or questions:

1. Check USER_GUIDE.md or ADMIN_GUIDE.md
2. Review Performance Issues.md for cache-related questions
3. Check TASKS-closure.md for implementation status
4. Contact system administrator

## Version History

- **v1.0** (March 2026) - Initial release with full feature set
- **v1.1** (March 3, 2026) - Performance optimizations and bug fixes
