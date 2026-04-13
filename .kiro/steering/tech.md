# Tech Stack

## Frontend

**Framework**: React 19.2.0 with TypeScript 4.9.5

**UI Libraries**: Chakra UI 2.8.2 (primary), Material UI 7.3.4, Framer Motion 12.23.24, Recharts 3.3.0, Plotly.js 3.3.0

**State & Forms**: Formik 2.4.6, Yup 1.7.1, AWS Amplify 6.16.0

**Testing**: Jest, Playwright 1.58.1, React Testing Library 16.3.0, MSW 2.11.6, fast-check 4.4.0

**Build**: Create React App 5.0.1

## Backend

**Framework**: Flask 2.3.3 with Python

**Database**: MySQL 8.0 via mysql-connector-python 8.1.0

**Key Libraries**: Flask-CORS 4.0.0, Waitress 3.0.0, PyPDF2/pypdf/pdfplumber (PDF), pandas 2.2.3, numpy 1.26.4, openpyxl 3.1.2, boto3 1.42.30, PyJWT 2.10.1, python-jose 3.5.0, cryptography 41.0.7

**APIs**: Google Drive API, OpenRouter API (AI invoice extraction), AWS SNS

**Testing**: pytest 6+ with markers (unit/integration/api/e2e)

**Documentation**: Flasgger 0.9.7.1 (Swagger/OpenAPI)

## Infrastructure

**Containerization**: Docker with docker-compose (MySQL 8.0, Backend)

**Cloud Services**: AWS Cognito (auth), AWS SNS (notifications), Google Drive (storage)

**IaC**: Terraform

## Code Style

**Frontend**: TypeScript strict mode, ESLint react-app config, Chakra UI theme in `theme.js`

**Backend**: PEP 8, type hints encouraged, docstrings for public functions, pytest markers for test categorization

## File Size Guidelines

**Target: 500 lines | Maximum: 1000 lines**

- Target 500 lines in new code and refactoring
- Maximum 1000 lines — files exceeding this require refactoring
- Exceptions: test files, generated files, configuration files with extensive mappings

**Frontend**: split components, extract hooks, move utils. **Backend**: split modules, extract helpers, use service layer, separate blueprint files.
