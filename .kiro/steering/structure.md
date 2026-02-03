# Project Structure

## Root Directory

```
myAdmin/
├── backend/              # Python Flask backend
├── frontend/             # React TypeScript frontend
├── infrastructure/       # Terraform IaC
├── mysql_data/          # MySQL data directory (Docker volume)
├── scripts/             # Utility scripts
├── Manuals/             # User documentation (HTML)
├── manualsSysAdm/       # System admin documentation
├── .kiro/               # Kiro AI assistant configuration
│   ├── specs/           # Feature specifications
│   ├── steering/        # AI guidance documents
│   ├── hooks/           # Event-driven automation
│   └── prompts/         # Custom prompts
├── docker-compose.yml   # Docker orchestration
└── .env                 # Root environment config
```

## Backend Structure

```
backend/
├── src/                          # Main application code
│   ├── app.py                    # Flask application entry point
│   ├── config.py                 # Configuration management
│   ├── database.py               # Database connection manager
│   ├── auth/                     # Authentication (Cognito, JWT)
│   ├── routes/                   # API route modules
│   ├── services/                 # Business logic services
│   ├── report_generators/        # Report generation logic
│   ├── migrations/               # Database migrations
│   ├── storage/                  # File storage
│   ├── uploads/                  # Uploaded files
│   ├── logs/                     # Application logs
│   └── validate_pattern/         # Pattern validation
│
├── tests/                        # Test suite (69 tests)
│   ├── unit/                     # Unit tests
│   ├── api/                      # API endpoint tests
│   ├── database/                 # Database tests
│   ├── patterns/                 # Pattern analysis tests
│   ├── integration/              # Integration tests
│   └── conftest.py               # Pytest fixtures
│
├── scripts/                      # Utility scripts (33 scripts)
│   ├── analysis/                 # Analysis & debugging
│   ├── database/                 # Database migrations & fixes
│   └── data/                     # Data analysis & validation
│
├── docs/                         # Documentation
│   ├── guides/                   # Setup & user guides
│   └── summaries/                # Investigation summaries
│
├── powershell/                   # PowerShell automation scripts
├── sql/                          # SQL scripts
├── data/                         # Data files (credentials, tokens)
├── templates/                    # HTML templates
├── static/                       # Static assets
├── requirements.txt              # Python dependencies
├── pytest.ini                    # Pytest configuration
└── .env                          # Backend environment config
```

### Backend Key Modules

**Core Processors**:

- `pdf_processor.py`: PDF parsing and extraction
- `banking_processor.py`: Bank statement processing
- `str_processor.py`: STR revenue processing
- `btw_processor.py`: VAT processing
- `toeristenbelasting_processor.py`: Tourist tax processing

**AI & Intelligence**:

- `ai_extractor.py`: AI-powered invoice extraction
- `pattern_analyzer.py`: Transaction pattern analysis
- `hybrid_pricing_optimizer.py`: STR pricing optimization
- `business_pricing_model.py`: Business logic for pricing

**Data Management**:

- `database.py`: Database connection and query management
- `str_database.py`: STR-specific database operations
- `duplicate_checker.py`: Duplicate detection logic
- `mutaties_cache.py`: Transaction caching
- `bnb_cache.py`: BNB data caching

**Services**:

- `google_drive_service.py`: Google Drive integration
- `aws_notifications.py`: AWS SNS notifications
- `template_service.py`: Template management

**Routes** (Blueprint-based):

- `reporting_routes.py`: Report generation endpoints
- `bnb_routes.py`: BNB-specific endpoints
- `str_channel_routes.py`: STR channel management
- `str_invoice_routes.py`: STR invoice management
- `admin_routes.py`: Admin operations
- `audit_routes.py`: Audit logging
- `tenant_admin_routes.py`: Tenant administration
- `tenant_module_routes.py`: Tenant module management

**Security & Performance**:

- `auth/cognito_utils.py`: AWS Cognito authentication
- `auth/tenant_context.py`: Multi-tenant context
- `security_audit.py`: Security auditing
- `performance_optimizer.py`: Performance monitoring
- `scalability_manager.py`: Scalability management
- `audit_logger.py`: Audit trail logging

## Frontend Structure

```
frontend/
├── src/
│   ├── App.tsx                   # Main application component
│   ├── index.tsx                 # Application entry point
│   ├── theme.js                  # Chakra UI theme customization
│   ├── config.ts                 # Frontend configuration
│   ├── aws-exports.ts            # AWS Amplify configuration
│   │
│   ├── components/               # Reusable UI components
│   ├── pages/                    # Page-level components
│   ├── services/                 # API service layer
│   ├── hooks/                    # Custom React hooks
│   ├── context/                  # React context providers
│   ├── types/                    # TypeScript type definitions
│   ├── utils/                    # Utility functions
│   │
│   ├── tests/                    # Test files
│   ├── __tests__/                # Additional test files
│   └── test-utils.tsx            # Testing utilities
│
├── public/                       # Static assets
├── build/                        # Production build output
├── tests/                        # E2E tests (Playwright)
├── playwright.config.ts          # Playwright configuration
├── tsconfig.json                 # TypeScript configuration
├── package.json                  # Dependencies and scripts
└── .env                          # Frontend environment config
```

## Infrastructure Structure

```
infrastructure/
├── main.tf                       # Main Terraform configuration
├── cognito.tf                    # AWS Cognito setup
├── notifications.tf              # AWS SNS setup
├── variables.tf                  # Terraform variables
├── *.ps1                         # PowerShell setup scripts
└── templates/                    # CloudFormation templates
```

## Naming Conventions

### Backend

- **Files**: `snake_case.py` (e.g., `banking_processor.py`)
- **Classes**: `PascalCase` (e.g., `BankingProcessor`)
- **Functions**: `snake_case` (e.g., `process_transaction`)
- **Routes**: Blueprint-based with `_bp` suffix (e.g., `reporting_bp`)
- **Tests**: `test_*.py` in `tests/` directory

### Frontend

- **Files**: `PascalCase.tsx` for components, `camelCase.ts` for utilities
- **Components**: `PascalCase` (e.g., `BankingProcessor.tsx`)
- **Hooks**: `use` prefix (e.g., `useAuth.ts`)
- **Services**: `camelCase` with `Service` suffix (e.g., `apiService.ts`)
- **Types**: `PascalCase` with `Type` or `Interface` suffix

## Key Architectural Patterns

### Backend

- **Blueprint-based routing**: Modular route organization
- **Service layer pattern**: Business logic separated from routes
- **Repository pattern**: Database operations abstracted
- **Caching layer**: Redis-style caching for performance
- **Multi-tenancy**: Tenant context middleware for data isolation
- **Authentication**: JWT-based with AWS Cognito integration

### Frontend

- **Component composition**: Reusable UI components
- **Custom hooks**: Shared logic extraction
- **Context API**: Global state management
- **Service layer**: API calls abstracted from components
- **Type safety**: Comprehensive TypeScript types

## Database Schema

**Main Tables**:

- `mutaties`: Financial transactions
- `bnb`: BNB realized bookings
- `bnbplanned`: BNB planned bookings
- `bnbfuture`: BNB future revenue
- `pricing_recommendations`: AI pricing suggestions
- `pricing_events`: Event-based pricing rules
- `listings`: Property listings
- `tenants`: Multi-tenant data
- `users`: User accounts
- `audit_log`: Audit trail

**Views**:

- `vw_mutaties`: Reporting view with VW logic

## Test Organization

### Backend Tests (pytest)

- **Markers**: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.api`, `@pytest.mark.e2e`
- **Fixtures**: Defined in `conftest.py`
- **Coverage**: Run with `pytest --cov=src tests/`

### Frontend Tests

- **Unit**: Jest with React Testing Library
- **E2E**: Playwright tests in `tests/` directory
- **Property-based**: fast-check for generative testing
- **Accessibility**: jest-axe for a11y testing

## Configuration Files

- `.env`: Environment-specific configuration (never commit)
- `.env.example`: Template for environment variables
- `docker-compose.yml`: Container orchestration
- `pytest.ini`: Pytest configuration
- `tsconfig.json`: TypeScript compiler options
- `playwright.config.ts`: E2E test configuration
- `.gitignore`: Git exclusions
