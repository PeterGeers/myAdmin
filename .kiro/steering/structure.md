# Project Structure

## Root Directory

```
myAdmin/
├── backend/              # Python Flask backend
├── frontend/             # React TypeScript frontend
├── infrastructure/       # Terraform IaC
├── mysql_data/           # MySQL data directory (Docker volume)
├── scripts/              # Utility scripts
├── Manuals/              # User documentation (HTML)
├── manualsSysAdm/        # System admin documentation
├── .kiro/                # Kiro AI configuration (specs, steering, hooks, prompts)
├── docker-compose.yml    # Docker orchestration
└── .env                  # Root environment config
```

## Backend (high-level)

```
backend/
├── src/                  # app.py, config.py, database.py
│   ├── auth/             # Cognito, JWT, tenant context
│   ├── routes/           # Blueprint route modules
│   ├── services/         # Business logic services
│   └── report_generators/# Report generation
├── tests/                # unit/, api/, integration/, database/, patterns/
├── scripts/              # analysis/, database/, data/
├── powershell/           # PowerShell automation
└── requirements.txt
```

## Frontend (high-level)

```
frontend/
├── src/
│   ├── components/       # Reusable UI components
│   ├── pages/            # Page-level components
│   ├── services/         # API service layer
│   ├── hooks/            # Custom React hooks
│   ├── context/          # React context providers
│   ├── types/            # TypeScript type definitions
│   └── utils/            # Utility functions
├── tests/                # E2E tests (Playwright)
└── package.json
```

## Naming Conventions

### Backend

- Files: `snake_case.py` — Classes: `PascalCase` — Functions: `snake_case`
- Routes: Blueprint with `_bp` suffix — Tests: `test_*.py`

### Frontend

- Components: `PascalCase.tsx` — Utilities: `camelCase.ts`
- Hooks: `use` prefix — Services: `camelCase` + `Service` suffix
- Types: `PascalCase` with `Type` or `Interface` suffix

## Key Architectural Patterns

### Backend

- Blueprint-based routing with service layer pattern
- Repository pattern for database operations
- Multi-tenancy via tenant context middleware
- JWT authentication with AWS Cognito
- Caching layer for performance

### Frontend

- Component composition with custom hooks
- Context API for global state
- Service layer abstracting API calls
- Comprehensive TypeScript types
