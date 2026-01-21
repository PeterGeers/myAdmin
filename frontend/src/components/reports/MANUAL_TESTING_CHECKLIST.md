# Manual Testing Checklist for Reports Refactoring

## Overview

This checklist should be completed before deploying the refactored reports to production. Each item should be tested in a development or staging environment.

**Tester:** ******\_\_\_******  
**Date:** ******\_\_\_******  
**Environment:** ******\_\_\_******

## Pre-Testing Setup

- [ ] Backend server is running
- [ ] Database is accessible
- [ ] Test data is available
- [ ] Browser console is open for error monitoring
- [ ] Network tab is open for API monitoring

## Component Loading Tests

### Main Entry Point

- [ ] MyAdminReportsNew component loads without errors
- [ ] Both main tabs are visible (BNB Reports, Financial Reports)
- [ ] Default tab (BNB Reports) is selected on load
- [ ] No console errors on initial load

### BNB Reports Group

- [ ] BNB Reports tab displays 6 sub-tabs
- [ ] All tab labels are correct:
  - [ ] 🏠 Revenue
  - [ ] 🏡 Actuals
  - [ ] 🎻 Violins
  - [ ] 🔄 Terugkerend
  - [ ] 📈 Future
  - [ ] 🏨 Toeristenbelasting
- [ ] Default sub-tab (Revenue) loads correctly

### Financial Reports Group

- [ ] Financial Reports tab displays 5 sub-tabs
- [ ] All tab labels are correct:
  - [ ] 💸 Mutaties
  - [ ] 📊 Actuals
  - [ ] 🧾 BTW
  - [ ] 🔍 Reference Analysis
  - [ ] 📋 Aangifte IB
- [ ] Default sub-tab (Mutaties) loads correctly

## Navigation Tests

### BNB Reports Navigation

- [ ] Can switch to Revenue report
- [ ] Can switch to Actuals report
- [ ] Can switch to Violins report
- [ ] Can switch to Terugkerend report
- [ ] Can switch to Future report
- [ ] Can switch to Toeristenbelasting report
- [ ] No errors when switching between reports
- [ ] Selected tab is visually highlighted

### Financial Reports Navigation

- [ ] Can switch to Mutaties report
- [ ] Can switch to Actuals report
- [ ] Can switch to BTW report
- [ ] Can switch to Reference Analysis report
- [ ] Can switch to Aangifte IB report
- [ ] No errors when switching between reports
- [ ] Selected tab is visually highlighted

### Cross-Group Navigation

- [ ] Can switch from BNB Reports to Financial Reports
- [ ] Can switch from Financial Reports to BNB Reports
- [ ] Sub-tab state is maintained when switching groups
- [ ] No data loss when switching between groups
- [ ] No memory leaks (check browser memory usage)

## Data Loading Tests

### BNB Revenue Report

- [ ] Data loads correctly
- [ ] Date filter works
- [ ] Amount selection works
- [ ] CSV export works
- [ ] Loading spinner displays during data fetch
- [ ] Error message displays if data fetch fails

### BNB Actuals Report

- [ ] Data loads correctly
- [ ] Year/quarter/month views work
- [ ] Listing/channel toggle works
- [ ] Trend charts render correctly
- [ ] Distribution pie charts render correctly
- [ ] Expandable sections work

### BNB Violins Report

- [ ] Plotly violin charts render correctly
- [ ] Price distribution displays
- [ ] Nights distribution displays
- [ ] Statistics table shows quartiles
- [ ] Charts are interactive (hover, zoom)

### BNB Returning Guests Report

- [ ] Guest data loads correctly
- [ ] Expandable booking details work
- [ ] Guest history displays
- [ ] Sorting works
- [ ] Filtering works

### BNB Future Report

- [ ] Future bookings load correctly
- [ ] Stacked area chart renders
- [ ] Year filter works
- [ ] Channel filter works
- [ ] Listing filter works

### Toeristenbelasting Report

- [ ] Tourist tax data loads correctly
- [ ] Declaration form works
- [ ] HTML export works
- [ ] Calculations are correct

### Mutaties Report

- [ ] Transaction data loads correctly
- [ ] Date filtering works
- [ ] Sorting works
- [ ] Search works
- [ ] CSV export works

### Actuals Report (Financial)

- [ ] P&L data loads correctly
- [ ] Hierarchical drill-down works
- [ ] Balance sheet displays
- [ ] Pie charts render correctly
- [ ] Data is accurate

### BTW Report

- [ ] BTW declaration data loads correctly
- [ ] Transaction saving works
- [ ] File upload works
- [ ] Calculations are correct

### Reference Analysis Report

- [ ] Reference data loads correctly
- [ ] Filtering works
- [ ] Trend charts render correctly
- [ ] Account selection works

### Aangifte IB Report

- [ ] Income tax data loads correctly
- [ ] Expandable details work
- [ ] XLSX export works
- [ ] Progress indicator displays during export
- [ ] Downloaded file is valid

## UI/UX Tests

### Visual Consistency

- [ ] All reports use consistent styling
- [ ] Colors match the design system
- [ ] Fonts are consistent
- [ ] Spacing is consistent
- [ ] Icons are appropriate and visible

### Responsive Design

- [ ] Layout works on desktop (1920x1080)
- [ ] Layout works on laptop (1366x768)
- [ ] Layout works on tablet (768x1024)
- [ ] Tabs are accessible on smaller screens
- [ ] Charts scale appropriately

### Loading States

- [ ] Loading spinners display during data fetch
- [ ] Loading text is clear
- [ ] UI doesn't freeze during loading
- [ ] User can cancel long-running operations

### Error States

- [ ] Error messages are clear and helpful
- [ ] Error messages don't expose sensitive info
- [ ] User can retry after error
- [ ] Errors are logged to console

## Performance Tests

### Initial Load

- [ ] Page loads in < 3 seconds
- [ ] No unnecessary API calls
- [ ] No console warnings
- [ ] No console errors

### Navigation Performance

- [ ] Tab switching is instant (< 100ms)
- [ ] No lag when switching reports
- [ ] No memory leaks over time
- [ ] Browser remains responsive

### Data Loading Performance

- [ ] API calls complete in reasonable time
- [ ] Large datasets don't freeze UI
- [ ] Charts render smoothly
- [ ] Export operations complete successfully

## Accessibility Tests

### Keyboard Navigation

- [ ] Can navigate tabs with keyboard
- [ ] Tab key moves focus correctly
- [ ] Enter/Space activates tabs
- [ ] Focus indicators are visible

### Screen Reader

- [ ] Tab labels are announced correctly
- [ ] Report content is accessible
- [ ] Charts have alt text or descriptions
- [ ] Error messages are announced

### Color Contrast

- [ ] Text is readable on backgrounds
- [ ] Selected tabs are clearly visible
- [ ] Charts use accessible colors
- [ ] Links are distinguishable

## Browser Compatibility

### Chrome

- [ ] All features work correctly
- [ ] No console errors
- [ ] Performance is acceptable

### Firefox

- [ ] All features work correctly
- [ ] No console errors
- [ ] Performance is acceptable

### Edge

- [ ] All features work correctly
- [ ] No console errors
- [ ] Performance is acceptable

### Safari (if applicable)

- [ ] All features work correctly
- [ ] No console errors
- [ ] Performance is acceptable

## Integration Tests

### API Integration

- [ ] All API endpoints respond correctly
- [ ] Error handling works for failed requests
- [ ] Authentication is maintained
- [ ] CORS issues are resolved

### State Management

- [ ] State persists across navigation
- [ ] No state conflicts between reports
- [ ] State resets appropriately
- [ ] No stale data issues

## Regression Tests

### Existing Functionality

- [ ] Old myAdminReports still works (if not removed)
- [ ] Other parts of the app still work
- [ ] No breaking changes to API
- [ ] No breaking changes to data structures

## Security Tests

### Data Security

- [ ] Sensitive data is not exposed in console
- [ ] API keys are not visible in network tab
- [ ] User data is properly sanitized
- [ ] XSS vulnerabilities are prevented

### Authentication

- [ ] Unauthorized users cannot access reports
- [ ] Session timeout works correctly
- [ ] Re-authentication works after timeout

## Final Checks

### Code Quality

- [ ] No console.log statements in production code
- [ ] No commented-out code
- [ ] No TODO comments
- [ ] Code follows project conventions

### Documentation

- [ ] README is updated
- [ ] TESTING_GUIDE is accurate
- [ ] TEST_RESULTS is current
- [ ] Comments are clear and helpful

### Deployment Readiness

- [ ] All tests pass
- [ ] No known critical bugs
- [ ] Rollback plan is in place
- [ ] Monitoring is configured

## Issues Found

| Issue # | Description | Severity | Status | Notes |
| ------- | ----------- | -------- | ------ | ----- |
| 1       |             |          |        |       |
| 2       |             |          |        |       |
| 3       |             |          |        |       |

## Sign-Off

**Tester Signature:** ******\_\_\_******  
**Date:** ******\_\_\_******  
**Approved for Deployment:** [ ] Yes [ ] No

**Notes:**

---

---

---

## Next Steps

After completing this checklist:

1. [ ] Document any issues found
2. [ ] Fix critical issues
3. [ ] Re-test fixed issues
4. [ ] Get approval from stakeholders
5. [ ] Schedule deployment
6. [ ] Prepare rollback plan
7. [ ] Deploy to production
8. [ ] Monitor for issues
9. [ ] Gather user feedback

## Contact

For questions about this checklist, contact the development team or refer to TESTING_GUIDE.md.
