---
inclusion: auto
---

# Tech Stack

The platform spans two planes (see `20-platform-architecture.md`): the Flask/MySQL app
and the SAM-backed module plane. Their stacks are listed separately below.

## Frontend

**Framework**: React 19.2.0 with TypeScript 5.9+

**UI Libraries**: Chakra UI 2.8.2 (primary), Material UI 7.3.4, Framer Motion 12.23.24, Recharts 3.3.0, Plotly.js 3.3.0 (via plotly.js-dist-min)

**State & Forms**: Formik 2.4.6, Yup 1.7.1, AWS Amplify 6.16.0

**Testing**: Vitest 4.x, Playwright 1.58.1, React Testing Library 16.3.0, MSW 2.11.6, fast-check 4.4.0 (via @fast-check/vitest)

**Build**: Vite 8.x with @vitejs/plugin-react, ESLint flat config (eslint.config.js)

## Backend (Flask / MySQL plane)

**Framework**: Flask 2.3.3 with Python

**Database**: MySQL 9.4 via mysql-connector-python 8.1.0

**Key Libraries**: Flask-CORS 4.0.0, Waitress 3.0.0, PyPDF2/pypdf/pdfplumber (PDF), pandas 2.2.3, numpy 1.26.4, openpyxl 3.1.2, boto3 1.42.30, PyJWT 2.10.1, python-jose 3.5.0, cryptography 41.0.7

**APIs**: Google Drive API, OpenRouter API (AI invoice extraction), AWS SNS

**Testing**: pytest 6+ with markers (unit/integration/api/e2e)

**Documentation**: Flasgger 0.9.7.1 (Swagger/OpenAPI)

## Module Plane (SAM-backed apps)

Apps imported as modules keep a serverless stack (see `20-platform-architecture.md`,
`35-sam-module-architecture-sam.md`). The code lives under `sam/` (see
`12-project-structure.md`).

**Serverless**: AWS SAM, AWS Lambda (Python), API Gateway

**Data**: DynamoDB — `PAY_PER_REQUEST` (on-demand) billing, `tenant_id` partition key +
IAM `dynamodb:LeadingKeys` scoping. DynamoDB Local for offline tests (see
`42-local-dynamodb-testing.md`).

**Shared toolkit (`sam/shared`)**: the vendored verified-JWT + entitlement library —
`get_verified_claims` / `get_groups` (S2) + `get_entitlements` / `has_capability` and the
`entitlement_claim` decoder (S4). Adopted **once** at a module's handler edge.

**Pre-Token-Generation (`sam/pretokengen`)**: the V2 Lambda that stamps the compact
versioned `custom:entitlements` claim, reading the S3 DynamoDB projection (not MySQL).

**Testing**: pytest via `sam/pytest.ini` (+ `sam/conftest.py`), property-based tests.

## Infrastructure

**Containerization**: Docker with docker-compose (MySQL 9.4, Backend, DynamoDB Local)

**Cloud Services**: AWS Cognito (auth, identity account), AWS SNS (notifications), AWS
Lambda + API Gateway + DynamoDB (module plane, data account), Google Drive (storage).
Accounts + guardrails: `23-aws-accounts.md`.

**IaC**: Terraform

## Code Style

**Frontend**: TypeScript strict mode, ESLint flat config (`eslint.config.js`), Chakra UI theme in `theme.js`, `@/` path alias for `./src/`

**Backend**: PEP 8, type hints encouraged, docstrings for public functions, pytest markers for test categorization

## File Size Guidelines

**Target: 500 lines | Maximum: 1000 lines**

- Target 500 lines in new code and refactoring
- Maximum 1000 lines — files exceeding this require refactoring
- Exceptions: test files, generated files, configuration files with extensive mappings

**Frontend**: split components, extract hooks, move utils. **Backend**: split modules, extract helpers, use service layer, separate blueprint files.
