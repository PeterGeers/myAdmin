# myAdmin Development Guardrails

## 🚨 Critical Rules - NEVER VIOLATE

### **API URL Policy**
- **ALWAYS use relative URLs**: `/api/...` 
- **NEVER use hardcoded localhost**: `http://localhost:5000/api/...`
- **Reason**: Breaks production deployment where React is served by Flask

### **Database Operations**
- **ALWAYS use test mode** during development: `test_mode=True`
- **NEVER modify production database** without explicit confirmation
- **ALWAYS validate transactions** before saving to database
- **Use transaction rollback** for failed operations

### **Environment Management**
- **Test Mode**: Uses `testfinance` database and `testFacturen` folder
- **Production Mode**: Uses `finance` database and `Facturen` folder
- **ALWAYS check mode** before database operations
- **Environment variables** control mode switching via `.env`

## 🔒 Security Requirements

### **Data Protection**
- **NO hardcoded credentials** in source code
- **Use .env files** for sensitive configuration
- **Validate all user inputs** before database operations
- **Sanitize file uploads** and validate file types

### **API Security**
- **Validate request parameters** in all API endpoints
- **Use proper error handling** - don't expose internal errors
- **Log security events** for audit trails
- **Rate limiting** for API endpoints (future consideration)

## 📊 Financial Data Integrity

### **Transaction Processing**
- **ALWAYS validate amounts** are non-zero before processing
- **Check for duplicates** using sequence numbers (Ref2)
- **Maintain audit trail** with Ref1, Ref2, Ref3, Ref4 fields
- **Round financial amounts** to 2 decimal places

### **STR Channel Revenue**
- **VAT calculation**: Currently 9% (changes to 21% on 2026-01-01)
- **Formula**: `(amount / 109) * 9` for 9% VAT
- **Future formula**: `(amount / 121) * 21` for 21% VAT
- **ALWAYS preview transactions** before saving to database

### **Account Mapping**
- **Revenue transactions**: Debet=1600, Credit=8003
- **VAT transactions**: Debet=8003, Credit=2021
- **Validate account codes** exist before creating transactions

## 🏗️ Architecture Principles

### **Frontend-Backend Communication**
- **Use TypeScript interfaces** for API data structures
- **Handle loading states** and error conditions
- **Implement proper error messages** for user feedback
- **Use React hooks** for state management

### **Database Schema**
- **Follow existing patterns** in mutaties table structure
- **Use consistent field naming**: TransactionDate, TransactionAmount, etc.
- **Maintain referential integrity** with Administration field
- **Use views (vw_mutaties)** for complex queries

### **File Processing**
- **Support multiple formats**: PDF, CSV, TSV, XLSX
- **Validate file contents** before processing
- **Use temporary storage** for uploaded files
- **Clean up temporary files** after processing

## 🧪 Testing Requirements

### **Test Coverage**
- **Unit tests** for all business logic functions
- **Integration tests** for API endpoints
- **Mock external services** (Google Drive, Gmail, MySQL)
- **Test both success and failure scenarios**
- **Test with special characters** in URLs and form data to prevent encoding errors
- **Test console output handling** on Windows systems

### **Test Data Management**
- **Use test database** for all automated tests
- **Create realistic test data** that matches production patterns
- **Clean up test data** after test execution
- **Isolate tests** to prevent interference

## 🚀 Deployment Guidelines

### **Production Readiness**
- **Build React frontend** before production deployment
- **Use production database** only after thorough testing
- **Validate all environment variables** are set correctly
- **Test API alignment** between frontend and backend

### **Monitoring**
- **Log all API requests** for debugging
- **Monitor database performance** and connection pooling
- **Track file processing errors** and success rates
- **Alert on critical failures** (database connection, file processing)

## 📝 Code Quality Standards

### **Code Organization**
- **Separate concerns**: Routes, business logic, database operations
- **Use descriptive function names** and variable names
- **Add comments** for complex business logic
- **Follow existing code patterns** and conventions

### **Error Handling**
- **Catch and handle exceptions** at appropriate levels
- **Provide meaningful error messages** to users
- **Log detailed errors** for debugging
- **Use try-catch blocks** for external service calls
- **Use logging module instead of print()** for production code
- **Handle console encoding errors** on Windows (OSError: Invalid argument)

### **Performance**
- **Use database connection pooling** for efficiency
- **Implement pagination** for large data sets
- **Cache frequently accessed data** when appropriate
- **Optimize database queries** to avoid N+1 problems

## 🔄 Change Management

### **Configuration Changes**
- **Document all parameter changes** (VAT rates, patterns, etc.)
- **Use configuration files** instead of hardcoded values
- **Test configuration changes** in test environment first
- **Maintain backward compatibility** when possible

### **Database Schema Changes**
- **Create migration scripts** for schema changes
- **Test migrations** on test database first
- **Backup production data** before schema changes
- **Document all schema modifications**

## 🎯 Business Logic Rules

### **STR Channel Processing**
- **Supported channels**: AirBnB, Booking.com, dfDirect, Stripe, VRBO
- **Account filtering**: Only process account 1600 transactions
- **Date filtering**: Use end-of-month date for calculations
- **Reference format**: "BnB YYYYMM" (e.g., "BnB 202511")

### **Banking Processor**
- **Support formats**: Rabobank CSV, Revolut TSV
- **Duplicate detection**: Use IBAN + sequence number
- **Pattern matching**: Apply historical patterns for account assignment
- **Validation**: Require all mandatory fields before saving

### **PDF Processing**
- **Vendor detection**: Based on folder selection and content analysis
- **Transaction extraction**: Parse amounts, dates, descriptions
- **Google Drive integration**: Upload files and store URLs
- **Template matching**: Use previous transactions as templates

## ⚠️ Common Pitfalls to Avoid

1. **Hardcoded localhost URLs** - Always use relative URLs
2. **Missing error handling** - Always wrap external calls in try-catch
3. **Unvalidated user input** - Validate all form data and API parameters
4. **Production database access** - Always use test mode during development
5. **Missing transaction validation** - Check amounts, dates, accounts before saving
6. **Inconsistent date formats** - Use ISO format (YYYY-MM-DD) consistently
7. **Memory leaks** - Close database connections and clean up resources
8. **Missing loading states** - Always show loading indicators for async operations
9. **Console encoding errors** - Wrap print() statements in try-catch for Windows compatibility
10. **Logging in production** - Use Python logging module instead of print() statements

## 📋 Pre-Deployment Checklist

- [ ] All tests passing (300+ backend tests)
- [ ] API alignment validated (frontend-backend routes match)
- [ ] Environment variables configured correctly
- [ ] Database connections tested
- [ ] File upload/processing tested
- [ ] Error handling verified
- [ ] Performance tested with realistic data volumes
- [ ] Security review completed
- [ ] Documentation updated
- [ ] Backup procedures verified