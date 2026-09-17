---
inclusion: auto
---

# Project Structure

The repo holds both platform planes (see `20-platform-architecture.md`): the Flask/MySQL
app (`backend/`, `frontend/`) and the SAM-backed module plane (`sam/`).

## Root Directory

```
myAdmin/
├── backend/              # Python Flask backend (Plane A — MySQL)
├── frontend/             # React TypeScript frontend
├── sam/                  # SAM-backed module plane (Plane B — Lambda + DynamoDB)
├── infrastructure/       # Terraform IaC (incl. cognito.tf)
├── mysql_data/           # MySQL data directory (Docker volume)
├── scripts/              # Utility scripts (incl. scripts/local/ DynamoDB seed/teardown)
├── manualsSysAdm/        # System admin documentation
├── .kiro/                # Kiro AI configuration (specs, steering, hooks, prompts)
├── docker-compose.yml    # Docker orchestration (MySQL 9.4 + backend + dynamodb-local)
└── .env                  # Root environment config
```

## Backend — Flask / MySQL plane (high-level)

```
backend/
├── src/                  # app.py, config.py, database.py
│   ├── auth/             # Cognito, JWT verify, tenant context, role_cache, pool_registry,
│   │                     #   entitlement_resolver / entitlement_claim_codec / entitlement_reader (S4)
│   ├── routes/           # Blueprint route modules
│   ├── services/         # Business logic services (incl. module_registry, dynamodb_client)
│   ├── migrations/       # Migration JSON files (run manually)
│   └── report_generators/# Report generation
├── tests/                # unit/, api/, integration/, database/, patterns/
│   ├── unit/conftest.py  # Connection guard + isolation fixtures (mock_db, mock_env, etc.)
│   └── reports/          # Scanner JSON/Markdown reports (timestamped)
├── scripts/              # analysis/, database/, data/, test_maintenance/
└── requirements.txt
```

## SAM module plane (high-level)

```
sam/
├── shared/               # vendored verified-JWT + entitlement toolkit (auth_utils,
│                         #   entitlement_claim) — adopted once per module
├── pretokengen/          # V2 Pre-Token-Generation Lambda (handler + governance readers)
├── tests/                # pytest suite for the module plane
├── conftest.py
├── pytest.ini            # sam test config (run tests from sam/)
└── README.md
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

## Specs (`.kiro/specs/`)

Organized by domain (see `40-spec-workflow.md`): `Common/`, `FIN/`, `STR/`, and
`multi-tenant/` (the platform evolution).

```
.kiro/specs/multi-tenant/
├── Analysis/                          # reasoning docs — start at overall_roadmap.md
├── s0-transfer-and-brief/
├── s1-prepare-platform/               # module-contract.md (the four seams)
├── s2-jwt-verification/
├── s3-claims-and-projection/
├── s4-token-entitlement-projection/
└── s5-members-first-migration/        # the active app migration pilot
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

### Backend (Flask plane)

- Blueprint-based routing with service layer pattern
- Repository pattern for database operations
- Multi-tenancy via tenant context middleware (`administration` key)
- JWT authentication with AWS Cognito
- Caching layer for performance

### Module plane (SAM)

- Layered: handler (thin adapter) → domain service → repository → DynamoDB
  (`35-sam-module-architecture-sam.md`)
- Tenant scoping by `tenant_id` partition key + IAM `LeadingKeys`

### Frontend

- Component composition with custom hooks
- Context API for global state
- Service layer abstracting API calls
- Comprehensive TypeScript types
