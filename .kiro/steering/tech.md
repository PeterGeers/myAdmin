# Tech Stack

## Frontend

**Framework**: React 19.2.0 with TypeScript 4.9.5

**UI Libraries**:

- Chakra UI 2.8.2 (primary component library)
- Material UI 7.3.4
- Framer Motion 12.23.24 (animations)
- Recharts 3.3.0 (charts/visualizations)
- Plotly.js 3.3.0 (advanced visualizations)

**State & Forms**:

- Formik 2.4.6 (form management)
- Yup 1.7.1 (validation)
- AWS Amplify 6.16.0 (authentication)

**Testing**:

- Jest (unit tests)
- Playwright 1.58.1 (E2E tests)
- React Testing Library 16.3.0
- MSW 2.11.6 (API mocking)
- fast-check 4.4.0 (property-based testing)
= AGENT HOOKS API Postman Testing for endpoints

**Build**: Create React App 5.0.1

## Backend

**Framework**: Flask 2.3.3 with Python

**Database**: MySQL 8.0 via mysql-connector-python 8.1.0

**Key Libraries**:

- Flask-CORS 4.0.0 (CORS handling)
- Waitress 3.0.0 (production server)
- PyPDF2 3.0.1, pypdf 6.1.3, pdfplumber 0.9.0 (PDF processing)
- pandas 2.2.3, numpy 1.26.4 (data processing)
- openpyxl 3.1.2 (Excel export)
- boto3 1.42.30 (AWS SDK)
- PyJWT 2.10.1, python-jose 3.5.0 (JWT authentication)
- cryptography 41.0.7 (encryption)

**APIs**:

- Google Drive API (google-api-python-client 2.108.0)
- OpenRouter API (AI-powered invoice extraction)
- AWS SNS (notifications)

**Testing**: pytest 6+ with markers for unit/integration/api/e2e tests

**Documentation**: Flasgger 0.9.7.1 (Swagger/OpenAPI)

## Infrastructure

**Containerization**: Docker with docker-compose

- MySQL 8.0 container (2GB RAM, 1 CPU)
- Backend container (512MB RAM, 1.5 CPU)

**Cloud Services**:

- AWS Cognito (authentication)
- AWS SNS (notifications)
- Google Drive (file storage)

**IaC**: Terraform (infrastructure management)

## Common Commands

### Frontend

```bash
# Development
cd frontend
npm start                    # Start dev server (port 3000)

# Testing
npm test                     # Run unit tests
npm run test:e2e             # Run Playwright E2E tests
npm run test:e2e:ui          # Run E2E tests with UI
npm run lint                 # Run ESLint

# Build
npm run build                # Production build
npm run build:ci             # CI build (ESLint disabled)
```

### Backend

```bash
# Development
cd backend
.\.venv\Scripts\Activate.ps1  # Activate virtual environment (Windows)
python src/app.py             # Start Flask server (port 5000)

# Or use PowerShell script
.\powershell\start_backend.ps1

# Testing
pytest                        # Run all tests
pytest tests/unit/            # Run unit tests only
pytest tests/api/             # Run API tests only
pytest tests/integration/     # Run integration tests only
pytest --cov=src tests/       # Run with coverage

# Or use PowerShell script
.\powershell\run_tests.ps1
```

### Docker

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs
docker-compose logs -f backend
docker-compose logs -f mysql

# Rebuild
docker-compose up -d --build
```

### Database

```bash
# Connect to MySQL
mysql -u peter -p

# Run migrations
python scripts/database/fix_database_views.py
```

### Git

```bash
# Quick commit with timestamp
.\gitUpdate.ps1

# Commit with custom message
.\gitUpdate.ps1 "Your message here"
```

## Environment Configuration

Both frontend and backend use `.env` files for configuration. Copy `.env.example` to `.env` and configure:

**Backend Key Variables**:

- `TEST_MODE`: true/false (switches between test/production databases)
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`: Database connection
- `SNS_TOPIC_ARN`, `AWS_REGION`: AWS notifications
- `OPENROUTER_API_KEY`: AI invoice extraction (optional)
- `CREDENTIALS_ENCRYPTION_KEY`: Tenant credential encryption

**Frontend Key Variables**:

- `REACT_APP_API_URL`: Backend API URL
- AWS Cognito configuration variables

## Code Style

**Frontend**:

- TypeScript strict mode enabled
- ESLint with react-app configuration
- Chakra UI theme customization in `theme.js`

**Backend**:

- PEP 8 Python style guide
- Type hints encouraged
- Docstrings for public functions
- pytest markers for test categorization (unit, integration, api, e2e)

## File Size Guidelines

**Target: 500 lines | Maximum: 1000 lines**

Large files become difficult to maintain, test, and understand. Follow these guidelines:

- **Target 500 lines**: Aim for this in new code and refactoring
- **Maximum 1000 lines**: Absolute limit - files exceeding this require refactoring
- **500-1000 lines**: Acceptable for complex components, but consider splitting

When a file approaches or exceeds these limits:

**Frontend (React/TypeScript):**

- Split into smaller components
- Extract custom hooks to separate files
- Move utility functions to `utils/` directory
- Separate concerns (UI, logic, data fetching)

**Backend (Python):**

- Split into multiple modules
- Extract helper functions to separate files
- Use service layer pattern for business logic
- Move route handlers to separate blueprint files

**Exceptions:**

- Test files may exceed 1000 lines if testing complex components
- Generated files (e.g., API schemas, migrations)
- Configuration files with extensive mappings

**Refactoring Strategy:**

1. Identify logical boundaries (components, services, utilities)
2. Extract to new files with clear, descriptive names
3. Update imports and references
4. Ensure tests still pass
5. Document the new structure
