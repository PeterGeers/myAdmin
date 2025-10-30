# myAdmin Test Plan

## Banking Processor Tests

### Process Files Tab
- [ ] **File Selection**: Select CSV/TSV files, verify file list displays
- [ ] **Mode Toggle**: Switch between TEST/PRODUCTION modes
- [ ] **Process Revolut TSV**: Upload Revolut file, verify transactions parsed
- [ ] **Process Rabobank CSV**: Upload Rabobank file, verify transactions parsed
- [ ] **Apply Patterns**: Click Apply Patterns, verify historical patterns applied
- [ ] **Save Transactions**: Save to database, verify success message
- [ ] **Duplicate Detection**: Upload same file twice, verify duplicates filtered

### Mutaties Tab
- [ ] **Year Filter**: Select multiple years, verify data filtered
- [ ] **Administration Filter**: Select administration, verify data filtered
- [ ] **Column Filters**: Use regex filters on columns, verify results
- [ ] **Display Limit**: Change display limit (50/100/250/500/1000)
- [ ] **Edit Record**: Click ID to edit, modify fields, save changes
- [ ] **Copy Functions**: Click fields to copy to clipboard

### Check Account Balances Tab
- [ ] **Check Balances**: Click button, verify account balances displayed
- [ ] **End Date Filter**: Set end date, verify balances as of date
- [ ] **Expand Rows**: Click arrow to expand transaction details
- [ ] **Check Sequence**: Select account and date, verify sequence check
- [ ] **Sequence Gaps**: Test with account having gaps, verify gap detection

### Check Reference Numbers Tab
- [ ] **Administration Filter**: Select administration, verify ledger dropdown updates
- [ ] **Ledger Filter**: Select ledger, verify cascading filter works
- [ ] **Check References**: Click button, verify reference summary displays
- [ ] **Reference Details**: Click Details button, verify transaction details
- [ ] **Non-zero Filter**: Verify only references with non-zero amounts shown
- [ ] **Date Format**: Verify dates display as yyyy-mm-dd
- [ ] **Transaction Number**: Verify TransactionNumber column shows data

## myAdmin Reports Tests

### BNB Violins Tab
- [ ] **Metric Selection**: Switch between Price per Night/Days per Stay
- [ ] **Year Filter**: Select multiple years, verify data filtered
- [ ] **Listing Filter**: Select listings, verify data filtered
- [ ] **Channel Filter**: Select channels, verify data filtered
- [ ] **Box Plot Display**: Verify statistical measures (min, Q1, median, mean, Q3, max)
- [ ] **Summary Statistics**: Verify statistics table displays correctly

### BNB Terugkerend Tab
- [ ] **Returning Guests**: Verify only guests with multiple bookings shown
- [ ] **Expand Details**: Click row to expand booking details
- [ ] **Sort Order**: Verify sorted by count and guest name
- [ ] **Summary Stats**: Verify booking count and guest name display

### Aangifte IB Tab
- [ ] **Year Selection**: Select year, verify data filtered
- [ ] **Administration Filter**: Select administration, verify data filtered
- [ ] **VW Logic**: Verify VW=N uses cumulative data, VW=Y uses year data
- [ ] **Hierarchical Display**: Verify Parent/Aangifte grouping
- [ ] **Expand Accounts**: Click row to show underlying accounts
- [ ] **Color Coding**: Verify red for positive, green for negative amounts
- [ ] **Grand Total**: Verify total calculation
- [ ] **HTML Export**: Export to HTML, verify formatting
- [ ] **XLSX Export**: Export to Excel, verify R script logic applied

### View ReferenceNumber Tab
- [ ] **Administration Filter**: Select administration, verify data filtered
- [ ] **Year Filter**: Select multiple years, verify data filtered
- [ ] **Reference Search**: Use regex search, verify results
- [ ] **Account Filter**: Select accounts, verify data filtered
- [ ] **Trend Chart**: Verify quarterly trend line displays
- [ ] **Transaction Table**: Verify transaction details table

## PDF Transaction Processor Tests

### PDF Upload
- [ ] **Google Drive Upload**: Upload PDF to Google Drive, verify success
- [ ] **Local Upload**: Upload PDF locally, verify success
- [ ] **Transaction Extraction**: Verify transactions extracted from PDF
- [ ] **Edit Transactions**: Modify extracted transactions
- [ ] **Save to Database**: Save transactions, verify in mutaties table

### PDF Validation
- [ ] **Year Selection**: Select year for validation
- [ ] **Progress Tracking**: Verify real-time progress bar
- [ ] **File URL Validation**: Verify Google Drive file URLs validated
- [ ] **Folder URL Validation**: Verify folder URLs processed
- [ ] **Missing Files Table**: Verify missing files displayed
- [ ] **Manual Update**: Update missing file references
- [ ] **Filter by Administration**: Verify filtering works

## STR Processor Tests

### File Processing
- [ ] **Airbnb Upload**: Upload Airbnb file, verify processing
- [ ] **Booking.com Upload**: Upload Booking.com file, verify processing
- [ ] **Realized vs Planned**: Verify separation of booking types
- [ ] **Future Revenue**: Verify future revenue calculations
- [ ] **Multi-platform Support**: Test multiple platform files

## System Tests

### Database Operations
- [ ] **Test Mode**: Verify operations use mutaties_test table
- [ ] **Production Mode**: Verify operations use mutaties table
- [ ] **Data Integrity**: Verify no data corruption during operations
- [ ] **Backup/Restore**: Test database backup and restore procedures

### Performance Tests
- [ ] **Large File Processing**: Test with large CSV/PDF files
- [ ] **Multiple Users**: Test concurrent user operations
- [ ] **Memory Usage**: Monitor memory during large operations
- [ ] **Response Times**: Verify acceptable response times

### Error Handling
- [ ] **Invalid Files**: Test with corrupted/invalid files
- [ ] **Network Errors**: Test with network connectivity issues
- [ ] **Database Errors**: Test with database connection issues
- [ ] **User Input Validation**: Test with invalid user inputs

### Browser Compatibility
- [ ] **Chrome**: Test all functionality in Chrome
- [ ] **Firefox**: Test all functionality in Firefox
- [ ] **Edge**: Test all functionality in Edge
- [ ] **Mobile**: Test responsive design on mobile devices

## Integration Tests

### API Endpoints
- [ ] **Banking Routes**: Test all banking API endpoints
- [ ] **Reporting Routes**: Test all reporting API endpoints
- [ ] **BNB Routes**: Test all BNB API endpoints
- [ ] **PDF Routes**: Test all PDF processing endpoints

### External Services
- [ ] **Google Drive API**: Test file upload/download operations
- [ ] **Gmail API**: Test email URL validation
- [ ] **MySQL Connection**: Test database connectivity and operations

## Security Tests

### Authentication
- [ ] **Access Control**: Verify proper access restrictions
- [ ] **Session Management**: Test session timeout and renewal
- [ ] **Input Sanitization**: Test SQL injection prevention
- [ ] **File Upload Security**: Test malicious file upload prevention

### Data Protection
- [ ] **Sensitive Data**: Verify PII is properly handled
- [ ] **Backup Security**: Verify backup files are secured
- [ ] **Audit Trail**: Verify user actions are logged
- [ ] **Data Encryption**: Verify sensitive data encryption

## Deployment Tests

### Environment Setup
- [ ] **Development**: Verify dev environment setup
- [ ] **Testing**: Verify test environment setup
- [ ] **Production**: Verify production deployment
- [ ] **Configuration**: Verify environment-specific configs

### Monitoring
- [ ] **Application Logs**: Verify logging functionality
- [ ] **Error Tracking**: Verify error reporting
- [ ] **Performance Monitoring**: Verify performance metrics
- [ ] **Health Checks**: Verify system health monitoring

## Test Data Requirements

### Sample Files
- [ ] Rabobank CSV files (various formats)
- [ ] Revolut TSV files
- [ ] PDF invoices (multiple vendor formats)
- [ ] Airbnb revenue files
- [ ] Booking.com revenue files

### Database States
- [ ] Empty database for fresh testing
- [ ] Database with sample transactions
- [ ] Database with duplicate transactions
- [ ] Database with missing references

## Test Environment Setup

### Prerequisites
- [ ] Node.js and npm installed
- [ ] Python and required packages
- [ ] MySQL database running
- [ ] Google Drive API credentials
- [ ] Gmail API credentials

### Configuration
- [ ] .env file with correct settings
- [ ] Database connection verified
- [ ] API credentials configured
- [ ] Test data loaded

## Acceptance Criteria

### Functionality
- [ ] All features work as specified
- [ ] Data accuracy verified
- [ ] Performance meets requirements
- [ ] Error handling works properly

### Usability
- [ ] Interface is intuitive
- [ ] Response times are acceptable
- [ ] Error messages are clear
- [ ] Help documentation is available

### Reliability
- [ ] System handles errors gracefully
- [ ] Data integrity is maintained
- [ ] Backup/recovery procedures work
- [ ] System is stable under load