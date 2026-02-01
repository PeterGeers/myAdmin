# Test Organization Strategy

## Overview

Clear separation of test types ensures:

- Fast feedback loops for developers
- Reliable CI/CD pipelines
- Easy test maintenance
- Appropriate test coverage at each level

**Document Structure**:

- **Part 1: Common Principles** - Apply to both backend and frontend
- **Part 2: Backend Testing** - Python/Flask specific guidelines
- **Part 3: Frontend Testing** - React/TypeScript specific guidelines
- \*\* SUMMARY

---

# PART 1: COMMON PRINCIPLES

## Common Test Categories

### 1. Unit Tests

**Purpose**: Test individual functions/classes/components in isolation
**Speed**: Fast (< 1 second per test)
**Dependencies**: None (mocked)
**Run**: On every commit, pre-commit hooks

**Common Characteristics**:

- No database connections
- No external API calls
- No file system operations (except temp files)
- All dependencies mocked
- Deterministic (same input = same output)

### 2. Integration Tests

**Purpose**: Test component interactions with real dependencies
**Speed**: Medium (1-10 seconds per test)
**Dependencies**: Real internal services (database, context, routing)
**Run**: On PR, before merge

**Common Characteristics**:

- Test multiple components working together
- Use real internal dependencies (not external APIs)
- May require test data setup
- Should be idempotent (can run multiple times)

### 3. End-to-End (E2E) Tests

**Purpose**: Test complete user workflows
**Speed**: Slow (10-60 seconds per test)
**Dependencies**: Full stack (frontend + backend + database)
**Run**: Nightly, before release

**Common Characteristics**:

- Browser automation (Playwright/Cypress)
- Full application stack running
- Real user scenarios
- Tests critical business flows

### 4. Performance Tests

**Purpose**: Measure and validate performance metrics
**Speed**: Variable
**Dependencies**: Production-like environment
**Run**: On-demand, before release

**Common Characteristics**:

- Load testing, stress testing, benchmarks
- Should not block CI pipeline (too flaky)
- Informational, not pass/fail

## Common CI Pipeline Stages

### Stage 1: Unit Tests (Required)

- **Run**: On every commit
- **Timeout**: 2 minutes
- **Pass Rate**: 100% required

### Stage 2: Integration Tests (Required)

- **Run**: On PR
- **Timeout**: 10 minutes
- **Pass Rate**: 95% required

### Stage 3: E2E Tests (Optional)

- **Run**: Nightly or pre-release
- **Timeout**: 30 minutes
- **Pass Rate**: 90% required (can warn)

### Stage 4: Performance Tests (Manual)

- **Run**: On-demand or weekly
- **Timeout**: 60 minutes
- **Pass Rate**: N/A (informational)

---

# PART 2: BACKEND TESTING (Python/Flask)

## Backend Test Categories

### 1. Backend Unit Tests

**Location**: `backend/tests/unit/`

**Examples**:

- `test_auth.py` - Auth logic without real Cognito
- `test_validators.py` - Input validation functions
- `test_utils.py` - Utility functions
- `test_models.py` - Data model logic

**Characteristics**:

- No database connections
- No external API calls
- All dependencies mocked
- Pure Python logic testing

### 2. Backend Integration Tests

**Location**: `backend/tests/integration/`

**Examples**:

- `test_database_operations.py` - Real DB queries
- `test_file_processing.py` - PDF parsing with real files
- `test_pattern_analysis.py` - Pattern detection with test data
- `test_tenant_filtering.py` - Multi-tenant data isolation

**Characteristics**:

- Real database connections (test database)
- Real file system operations
- Internal service calls
- May require test data setup

### 3. Backend API Tests

**Location**: `backend/tests/api/`

**Examples**:

- `test_reporting_routes.py` - Report endpoints
- `test_duplicate_api.py` - Duplicate detection API
- `test_str_routes.py` - STR booking endpoints

**Characteristics**:

- Requires running Flask application
- Real HTTP requests
- Authentication/authorization testing
- May require mock external services (Cognito, S3)

## Backend Pytest Markers

```python
# Unit test (default - no marker needed)
def test_calculate_total():
    assert calculate_total([1, 2, 3]) == 6

# Integration test
@pytest.mark.integration
def test_database_query():
    db = DatabaseManager()
    result = db.execute_query("SELECT * FROM users")
    assert len(result) > 0

# API test
@pytest.mark.api
def test_login_endpoint(client):
    response = client.post('/api/login', json={'email': 'test@example.com'})
    assert response.status_code == 200

# Slow test
@pytest.mark.slow
def test_large_dataset_processing():
    # Takes > 30 seconds
    pass
```

## Backend Directory Structure

```
backend/
├── tests/
│   ├── unit/                    # Unit tests (fast, isolated)
│   │   ├── test_auth.py
│   │   ├── test_validators.py
│   │   ├── test_utils.py
│   │   └── test_models.py
│   │
│   ├── integration/             # Integration tests (medium speed)
│   │   ├── test_database_operations.py
│   │   ├── test_file_processing.py
│   │   ├── test_pattern_analysis.py
│   │   └── test_tenant_filtering.py
│   │
│   ├── api/                     # API tests (requires running app)
│   │   ├── test_reporting_routes.py
│   │   ├── test_duplicate_api.py
│   │   └── test_str_routes.py
│   │
│   ├── e2e/                     # End-to-end tests (full stack)
│   │   ├── test_invoice_workflow.py
│   │   └── test_report_generation.py
│   │
│   ├── performance/             # Performance tests (manual/nightly)
│   │   ├── test_scalability.py
│   │   └── test_query_performance.py
│   │
│   ├── fixtures/                # Shared test fixtures
│   │   ├── conftest.py
│   │   └── database_fixtures.py
│   │
│   └── conftest.py              # Root conftest with markers
```

## Backend pytest.ini Configuration

```ini
[pytest]
# Test discovery
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Markers
markers =
    unit: Unit tests (fast, isolated, no external dependencies)
    integration: Integration tests (database, file system)
    api: API tests (requires running Flask app)
    e2e: End-to-end tests (full stack, browser automation)
    performance: Performance tests (load, stress, benchmarks)
    slow: Tests that take > 10 seconds
    skip_ci: Skip in CI pipeline (manual testing only)

# Test output
addopts =
    -v
    --strict-markers
    --tb=short
    --disable-warnings

# Coverage
testpaths = tests
```

## Running Backend Tests

```bash
# Run only unit tests (fast feedback)
pytest tests/unit/

# Run unit + integration tests
pytest tests/unit/ tests/integration/

# Run specific marker
pytest -m integration
pytest -m api

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=html
```

## Backend Test Examples

### Backend Unit Test

```python
# tests/unit/test_validators.py
import pytest
from src.validators import validate_email

class TestEmailValidator:
    """Unit tests for email validation"""

    def test_valid_email(self):
        assert validate_email("user@example.com") is True

    def test_invalid_email_no_at(self):
        assert validate_email("userexample.com") is False

    @pytest.mark.parametrize("email", [
        "user@example.com",
        "user.name@example.co.uk",
        "user+tag@example.com"
    ])
    def test_valid_email_formats(self, email):
        assert validate_email(email) is True
```

### Backend Integration Test

```python
# tests/integration/test_database_operations.py
import pytest
from src.database import DatabaseManager

@pytest.mark.integration
class TestDatabaseOperations:
    """Integration tests for database operations"""

    @pytest.fixture
    def db(self):
        """Create test database connection"""
        db = DatabaseManager(test_mode=True)
        yield db
        db.close()

    def test_insert_and_retrieve_user(self, db):
        # Insert test user
        user_id = db.execute_query(
            "INSERT INTO users (email, name) VALUES (%s, %s)",
            ("test@example.com", "Test User"),
            commit=True
        )

        # Retrieve user
        result = db.execute_query(
            "SELECT * FROM users WHERE email = %s",
            ("test@example.com",)
        )

        assert len(result) == 1
        assert result[0]['email'] == "test@example.com"
```

### Backend API Test

```python
# tests/api/test_auth_endpoints.py
import pytest

@pytest.mark.api
class TestAuthEndpoints:
    """API tests for authentication endpoints"""

    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()

    def test_login_success(self, client, mock_cognito):
        """Test successful login"""
        response = client.post('/api/login', json={
            'email': 'user@example.com',
            'password': 'password123'
        })

        assert response.status_code == 200
        data = response.get_json()
        assert 'token' in data
```

## Backend Best Practices

### ✅ DO:

- Test one thing at a time
- Use descriptive test names
- Mock all external dependencies
- Keep unit tests under 1 second
- Use test database for integration tests
- Clean up after each test

### ❌ DON'T:

- Access production database in tests
- Make real external API calls
- Rely on specific data (create test data)
- Test implementation details
- Leave tests dependent on each other

---

# PART 3: FRONTEND TESTING (React/TypeScript)

## Frontend Test Categories

### 1. Frontend Component Unit Tests

**Location**: `frontend/src/components/**/__tests__/`

**Examples**:

- `TemplateUpload.test.tsx` - File upload component
- `ValidationResults.test.tsx` - Validation display component
- `AIHelpButton.test.tsx` - Help button component

**Characteristics**:

- Test component rendering
- Test user interactions (clicks, typing, etc.)
- Test prop handling
- Test state management
- Mock all external dependencies (API calls, context, etc.)
- **Mock UI libraries (Chakra UI, Material-UI, etc.)**

### 2. Frontend Integration Tests

**Location**: `frontend/src/tests/`

**Examples**:

- `authentication-flow.test.tsx` - Login flow with context
- `routing.test.tsx` - Navigation between pages
- `form-validation.test.tsx` - Form with multiple components

**Characteristics**:

- Test multiple components working together
- Test React context providers
- Test routing behavior
- Test form submissions with validation
- May use real state management (Redux, Context API)

### 3. Frontend E2E Tests

**Location**: `frontend/tests/e2e/`

**Examples**:

- `login.spec.ts` - Complete login workflow
- `invoice-workflow.spec.ts` - Upload and process invoice

**Characteristics**:

- Browser automation (Playwright, Cypress)
- Test critical user journeys
- Test across different browsers
- Test responsive design

## Frontend Testing Tools

- **React Testing Library**: Component testing (preferred)
- **Jest**: Test runner and assertions
- **@testing-library/user-event**: Simulate user interactions
- **MSW (Mock Service Worker)**: Mock API calls (optional)
- **Playwright/Cypress**: E2E testing

## Frontend Directory Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ComponentName/
│   │   │   ├── ComponentName.tsx
│   │   │   └── __tests__/
│   │   │       └── ComponentName.test.tsx
│   │   └── TenantAdmin/
│   │       └── TemplateManagement/
│   │           ├── TemplateUpload.tsx
│   │           ├── ValidationResults.tsx
│   │           └── __tests__/
│   │               ├── TemplateUpload.test.tsx
│   │               └── ValidationResults.test.tsx
│   │
│   ├── tests/                    # Integration tests
│   │   ├── authentication-flow.test.tsx
│   │   ├── routing.test.tsx
│   │   └── form-validation.test.tsx
│   │
│   └── test-utils.tsx            # Shared test utilities
│
└── tests/
    └── e2e/                      # E2E tests
        ├── login.spec.ts
        └── invoice-workflow.spec.ts
```

## Running Frontend Tests

```bash
# Run all tests
npm test

# Run tests in watch mode
npm test -- --watch

# Run specific test file
npm test -- TemplateUpload.test.tsx

# Run with coverage
npm test -- --coverage --watchAll=false

# Run tests matching pattern
npm test -- --testNamePattern="File Upload"
```

## Frontend-Specific: Chakra UI Mocking

**CRITICAL**: Always mock Chakra UI components to avoid dependency issues.

### The Proven Pattern

```typescript
// Mock Chakra UI components - filter out Chakra-specific props
jest.mock('@chakra-ui/react', () => ({
  Box: ({ children, ...props }: any) => {
    const { bg, p, spacing, borderRadius, boxShadow, minH, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  VStack: ({ children, ...props }: any) => {
    const { spacing, w, align, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  HStack: ({ children, ...props }: any) => {
    const { spacing, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  Button: ({ children, onClick, ...props }: any) => {
    const { colorScheme, isLoading, loadingText, isDisabled, variant, size, ...domProps } = props;
    return (
      <button onClick={onClick} disabled={isDisabled || isLoading} {...domProps}>
        {isLoading && loadingText ? loadingText : children}
      </button>
    );
  },
  Input: ({ ...props }: any) => {
    const { display, ...domProps } = props;
    return <input {...domProps} style={display === 'none' ? { display: 'none' } : undefined} />;
  },
  Select: ({ children, ...props }: any) => {
    const { isDisabled, ...domProps } = props;
    return <select disabled={isDisabled} {...domProps}>{children}</select>;
  },
  Textarea: ({ ...props }: any) => {
    const { fontFamily, fontSize, bg, isDisabled, ...domProps } = props;
    return <textarea disabled={isDisabled} {...domProps} />;
  },
  FormControl: ({ children }: any) => <div>{children}</div>,
  FormLabel: ({ children, ...props }: any) => {
    const { fontSize, ...domProps } = props;
    return <label {...domProps}>{children}</label>;
  },
  FormErrorMessage: ({ children }: any) => <div role="alert">{children}</div>,
  FormHelperText: ({ children, ...props }: any) => {
    const { color, fontSize, ...domProps } = props;
    return <div {...domProps}>{children}</div>;
  },
  Collapse: ({ children }: any) => <div>{children}</div>,
  useDisclosure: () => ({
    isOpen: true,  // Always open in tests
    onOpen: jest.fn(),
    onClose: jest.fn(),
    onToggle: jest.fn(),
  }),
}));
```

### Key Principles for Chakra Mocking

1. **Filter out Chakra-specific props** (colorScheme, spacing, bg, etc.)
2. **Pass through DOM props** (...domProps)
3. **Keep mocks simple** - don't replicate complex Chakra behavior
4. **Always render children** - don't conditionally hide content
5. **Map Chakra props to HTML** (isDisabled → disabled, isLoading → disabled)

## Frontend-Specific: File Upload Testing

**CRITICAL**: Use `fireEvent` for file inputs, not `userEvent.upload`:

```typescript
import { fireEvent } from "@testing-library/react";

// ❌ DON'T: userEvent.upload doesn't work well with hidden inputs
await user.upload(input, file);

// ✅ DO: Use fireEvent for file inputs
const input = screen.getByLabelText(/upload file/i) as HTMLInputElement;
const file = new File(["content"], "test.pdf", { type: "application/pdf" });
Object.defineProperty(input, "files", { value: [file], writable: false });
fireEvent.change(input);
```

## Frontend-Specific: JSON Input Testing

**CRITICAL**: Use `fireEvent` for JSON/complex text input:

```typescript
// ❌ DON'T: userEvent.type fails with curly braces
await user.type(textarea, '{"key": "value"}');

// ✅ DO: Use fireEvent for JSON input
fireEvent.change(textarea, { target: { value: '{"key": "value"}' } });
```

## Frontend Component Test Example

```typescript
/**
 * TemplateUpload Component Unit Tests
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TemplateUpload } from '../TemplateUpload';

// Mock Chakra UI (see pattern above)
jest.mock('@chakra-ui/react', () => ({
  // ... Chakra mocks
}));

describe('TemplateUpload', () => {
  const mockOnUpload = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Rendering', () => {
    it('renders template type selector', () => {
      render(<TemplateUpload onUpload={mockOnUpload} />);
      expect(screen.getByRole('combobox', { name: /template type/i })).toBeInTheDocument();
    });
  });

  describe('File Upload', () => {
    it('accepts HTML file selection', () => {
      render(<TemplateUpload onUpload={mockOnUpload} />);

      const file = new File(['<html></html>'], 'template.html', { type: 'text/html' });
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;

      // Use fireEvent for file inputs
      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);

      expect(screen.getByText('template.html')).toBeInTheDocument();
    });

    it('rejects non-HTML files', async () => {
      render(<TemplateUpload onUpload={mockOnUpload} />);

      const file = new File(['content'], 'document.pdf', { type: 'application/pdf' });
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;

      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent(/only html files/i);
      });
    });
  });

  describe('User Interactions', () => {
    it('enables upload button when all fields are filled', async () => {
      const user = userEvent.setup();
      render(<TemplateUpload onUpload={mockOnUpload} />);

      // Use userEvent for simple interactions
      const select = screen.getByRole('combobox', { name: /template type/i });
      await user.selectOptions(select, 'str_invoice_nl');

      // Use fireEvent for file input
      const file = new File(['<html></html>'], 'template.html', { type: 'text/html' });
      const input = screen.getByLabelText(/upload html template file/i) as HTMLInputElement;
      Object.defineProperty(input, 'files', { value: [file], writable: false });
      fireEvent.change(input);

      const uploadButton = screen.getByRole('button', { name: /upload & preview/i });
      await waitFor(() => {
        expect(uploadButton).not.toBeDisabled();
      });
    });
  });
});
```

## Frontend Best Practices

### ✅ DO:

- Use accessible queries (`getByRole`, `getByLabelText`)
- Test user behavior, not implementation details
- Mock Chakra UI components consistently
- Use `fireEvent` for file inputs and JSON input
- Use `userEvent` for clicks, typing simple text, selections
- Add `aria-label` to components for better testability
- Test error states and validation
- Test loading states
- Test disabled states
- Clean up mocks in `beforeEach`

### ❌ DON'T:

- Test Chakra UI behavior (it's already tested)
- Use `getByTestId` unless absolutely necessary
- Test CSS styles or layout
- Test implementation details (state variable names, etc.)
- Use `userEvent.upload` for file inputs
- Use `userEvent.type` for JSON/complex input
- Make tests dependent on each other
- Leave console errors/warnings in tests

## Frontend Coverage Targets

- **Component Unit Tests**: 80%+ coverage
- **Integration Tests**: 70%+ coverage
- **Critical paths**: 90%+ coverage

## Frontend Common Pitfalls

1. **Hidden file inputs**: Use `fireEvent` not `userEvent.upload`
2. **JSON input**: Use `fireEvent.change` not `userEvent.type`
3. **Chakra UI mocks**: Always filter out Chakra-specific props
4. **useDisclosure**: Always return `isOpen: true` in tests
5. **Async updates**: Use `waitFor` for state changes
6. **Disabled buttons**: Test the disabled state, don't try to click
7. **FormErrorMessage**: Only renders when there's an error (conditional)

---

# SUMMARY

## Quick Reference

### Backend (Python/Flask)

- **Unit Tests**: `backend/tests/unit/` - Pure Python logic
- **Integration Tests**: `backend/tests/integration/` - Real database
- **API Tests**: `backend/tests/api/` - HTTP endpoints
- **Run**: `pytest tests/unit/` or `pytest -m integration`
- **Mock**: External APIs (Cognito, S3), not database in integration tests

### Frontend (React/TypeScript)

- **Unit Tests**: `frontend/src/components/**/__tests__/` - Component logic
- **Integration Tests**: `frontend/src/tests/` - Multiple components
- **E2E Tests**: `frontend/tests/e2e/` - Full workflows
- **Run**: `npm test` or `npm test -- TemplateUpload.test.tsx`
- **Mock**: Chakra UI (always), API calls, external services

### Common

- **E2E Tests**: Full stack, browser automation
- **Performance Tests**: Load testing, benchmarks
- **CI Pipeline**: Unit → Integration → E2E
- **Coverage**: 80%+ for unit tests, 70%+ for integration

## Key Differences

| Aspect            | Backend                         | Frontend                         |
| ----------------- | ------------------------------- | -------------------------------- |
| **Language**      | Python                          | TypeScript/JavaScript            |
| **Test Runner**   | pytest                          | Jest                             |
| **Mocking**       | unittest.mock, pytest fixtures  | jest.mock, React Testing Library |
| **Critical Mock** | External APIs (Cognito, S3)     | Chakra UI components             |
| **File Handling** | Real files in integration tests | fireEvent for file inputs        |
| **Special Cases** | Database fixtures               | JSON input with fireEvent        |
| **Markers**       | @pytest.mark.integration        | N/A (folder-based)               |
