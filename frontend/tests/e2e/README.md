# End-to-End Tests for Template Management

This directory contains comprehensive E2E tests for the Template Management feature using Playwright.

## Overview

The E2E tests cover the complete workflow from UI to database:

1. **Template Upload** - File selection, validation, and upload
2. **Template Validation** - HTML syntax, placeholders, security checks
3. **Template Preview** - Rendering with sample data
4. **AI Assistance** - Getting help and applying fixes
5. **Template Approval/Rejection** - Saving to Google Drive and database
6. **Error Handling** - Network errors, service failures, edge cases
7. **Browser Compatibility** - Chrome, Firefox, Safari
8. **Responsive Design** - Desktop, tablet, mobile viewports

## Test Files

### `template-management.spec.ts`

Core workflow tests:

- Complete upload → validate → preview → approve workflow
- Invalid template handling
- Malformed HTML handling
- Template rejection
- File size validation
- File type validation
- AI assistance workflow
- Multiple template types

### `template-error-scenarios.spec.ts`

Error handling tests:

- No sample data available
- AI service unavailable
- Google Drive upload failures
- Network timeouts
- Database connection errors
- Invalid JSON responses
- Authentication expiration
- Concurrent uploads
- Security violations

### `template-real-data.spec.ts`

Real template tests:

- Real STR invoice templates (NL/EN)
- Real BTW aangifte template
- Real Aangifte IB template
- Real Toeristenbelasting template
- Complex styling and tables
- AI assistance with real OpenRouter API
- Rate limiting handling

### `browser-compatibility.spec.ts`

Cross-browser tests:

- Chromium/Chrome workflow
- Firefox workflow
- WebKit/Safari workflow
- Responsive design (desktop, tablet, mobile)
- Keyboard navigation
- ARIA labels and accessibility
- Performance benchmarks

## Prerequisites

### 1. Install Playwright

```bash
npm install
npm run playwright:install
```

This will install Playwright and download the necessary browser binaries.

### 2. Environment Setup

Create a `.env.test` file in the frontend directory:

```env
# Test user credentials
TEST_USER_EMAIL=test@example.com
TEST_USER_PASSWORD=TestPassword123!

# Backend API URL
PLAYWRIGHT_BASE_URL=http://localhost:3000

# OpenRouter API key (for AI assistance tests)
OPENROUTER_API_KEY=your_api_key_here
```

### 3. Start Backend Server

The E2E tests require the backend API to be running:

```bash
cd backend
python src/app.py
```

### 4. Start Frontend Dev Server

The tests will automatically start the frontend dev server, but you can also start it manually:

```bash
cd frontend
npm start
```

## Running Tests

### Run All E2E Tests

```bash
npm run test:e2e
```

### Run Tests in UI Mode (Interactive)

```bash
npm run test:e2e:ui
```

This opens the Playwright Test UI where you can:

- See all tests
- Run individual tests
- Watch tests execute
- Debug failures

### Run Tests in Headed Mode (See Browser)

```bash
npm run test:e2e:headed
```

### Run Tests for Specific Browser

```bash
# Chrome/Chromium only
npm run test:e2e:chromium

# Firefox only
npm run test:e2e:firefox

# Safari/WebKit only
npm run test:e2e:webkit
```

### Run Specific Test File

```bash
npx playwright test template-management.spec.ts
```

### Run Specific Test

```bash
npx playwright test -g "should complete full workflow"
```

### Debug Tests

```bash
npm run test:e2e:debug
```

This opens the Playwright Inspector for step-by-step debugging.

### View Test Report

After running tests, view the HTML report:

```bash
npm run test:e2e:report
```

## Test Configuration

The tests are configured in `playwright.config.ts`:

- **Timeout**: 60 seconds per test
- **Retries**: 2 retries in CI, 0 locally
- **Workers**: 1 (sequential execution for database consistency)
- **Screenshots**: On failure
- **Videos**: On failure
- **Traces**: On first retry

## Test Data

### Test Users

The tests use a test user account:

- Email: `test@example.com`
- Password: `TestPassword123!`
- Role: Tenant Administrator
- Tenant: GoodwinSolutions

### Test Templates

The tests use both:

1. **Generated templates** - Created programmatically for specific test scenarios
2. **Real templates** - Loaded from `backend/templates/html/`

## CI/CD Integration

### GitHub Actions

Add to `.github/workflows/e2e-tests.yml`:

```yaml
name: E2E Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: "18"

      - name: Install dependencies
        run: |
          cd frontend
          npm ci

      - name: Install Playwright browsers
        run: |
          cd frontend
          npx playwright install --with-deps

      - name: Start backend
        run: |
          cd backend
          python -m venv venv
          source venv/bin/activate
          pip install -r requirements.txt
          python src/app.py &
          sleep 10

      - name: Run E2E tests
        run: |
          cd frontend
          npm run test:e2e
        env:
          CI: true
          TEST_USER_EMAIL: ${{ secrets.TEST_USER_EMAIL }}
          TEST_USER_PASSWORD: ${{ secrets.TEST_USER_PASSWORD }}
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: playwright-report
          path: frontend/playwright-report/
          retention-days: 30
```

## Troubleshooting

### Tests Fail with "Timeout"

- Increase timeout in `playwright.config.ts`
- Check if backend is running
- Check if frontend dev server started
- Check network connectivity

### Tests Fail with "Element not found"

- Check if selectors match the actual UI
- Use `--headed` mode to see what's happening
- Use `--debug` mode to step through the test

### Tests Fail with "Authentication error"

- Verify test user exists in Cognito
- Check credentials in `.env.test`
- Verify user has Tenant Administrator role

### Tests Fail with "Database error"

- Check if database is running
- Verify database connection in backend
- Check if test data exists

### Browser Installation Issues

```bash
# Reinstall browsers
npx playwright install --force

# Install system dependencies (Linux)
npx playwright install-deps
```

## Best Practices

### 1. Test Isolation

Each test should be independent:

- Don't rely on test execution order
- Clean up test data after each test
- Use unique identifiers for test data

### 2. Selectors

Use accessible selectors:

- Prefer `getByRole`, `getByLabel`, `getByText`
- Use `data-testid` for complex elements
- Avoid CSS selectors when possible

### 3. Waiting

Use explicit waits:

- `waitForSelector` for elements
- `waitForURL` for navigation
- `waitForResponse` for API calls
- Avoid `waitForTimeout` unless necessary

### 4. Assertions

Use meaningful assertions:

- Check for visible elements, not just existence
- Verify content, not just structure
- Test user-facing behavior, not implementation

### 5. Error Handling

Test error scenarios:

- Network failures
- Service unavailability
- Invalid input
- Edge cases

## Coverage

The E2E tests cover:

- ✅ Complete upload → validate → preview → approve workflow
- ✅ Invalid template handling
- ✅ Malformed HTML handling
- ✅ Template rejection
- ✅ File validation (size, type)
- ✅ AI assistance (with and without real API)
- ✅ Error scenarios (network, service, database)
- ✅ Browser compatibility (Chrome, Firefox, Safari)
- ✅ Responsive design (desktop, tablet, mobile)
- ✅ Accessibility (keyboard, screen readers)
- ✅ Performance benchmarks

## Next Steps

1. **Add more template types** - Test all template types
2. **Add field mapping tests** - Test custom field mappings
3. **Add multi-tenant tests** - Test tenant isolation
4. **Add performance tests** - Load testing, stress testing
5. **Add visual regression tests** - Screenshot comparison

## Resources

- [Playwright Documentation](https://playwright.dev/)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Playwright API Reference](https://playwright.dev/docs/api/class-playwright)
- [Testing Library Principles](https://testing-library.com/docs/guiding-principles/)
