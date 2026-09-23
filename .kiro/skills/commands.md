---
inclusion: auto
---

# Commands & Environment

Pull into context with `#commands` when you need build/run/test commands or environment setup.

## Frontend

```bash
cd frontend
npm start                    # Vite dev server (port 3000)
npm test                     # Vitest (watch mode)
npm run test:run             # Vitest (single run, CI)
npm run test:e2e             # Playwright E2E tests
npm run test:e2e:ui          # E2E tests with UI
npm run lint                 # ESLint (flat config)
npm run build                # tsc + Vite production build
npm run build:ci             # Vite build (skip tsc)
npm run preview              # Serve production build locally
```

## Backend

```bash
cd backend
source .venv/bin/activate     # Activate venv (WSL/Linux)
python src/app.py             # Flask server (port 5000)

pytest                        # All tests
pytest tests/unit/            # Unit tests only
pytest tests/unit/test_maintenance/ -v  # Test maintenance framework tests
pytest tests/api/             # API tests only
pytest tests/integration/     # Integration tests only
pytest --cov=src tests/       # With coverage
```

## Test Maintenance Tools

Run from the project root (not `backend/`):

```bash
# Health scan — detect mock violations, drift, compliance issues
python -m backend.scripts.test_maintenance.scanner

# Maintenance session — prioritised fix list grouped by root cause
python -m backend.scripts.test_maintenance.scanner --maintenance-session

# Baseline snapshot — record current failing tests
python -m backend.scripts.test_maintenance.scanner --baseline

# Frontend-only scan
python -m backend.scripts.test_maintenance.scanner --frontend-only

# Scoped test runner — run only tests affected by changes
python -m backend.scripts.test_maintenance.scoped_runner --git-diff
python -m backend.scripts.test_maintenance.scoped_runner backend/src/services/my_service.py
python -m backend.scripts.test_maintenance.scoped_runner --full
```

## Docker

```bash
docker-compose up -d          # Start all services
docker-compose down           # Stop all services
docker-compose logs -f backend  # View backend logs
docker-compose up -d --build  # Rebuild
```

## Database

```bash
mysql -u <LOCAL_DB_USER> -p             # Connect to local MySQL
python scripts/database/fix_database_views.py  # Run migrations
```

> For Railway DB connections and migration details, use `#database` skill.

## Railway (Production)

Railway backend: `https://<RAILWAY_APP>.up.railway.app`

> For Railway MySQL connection details, use `#database` skill.

### Railway operations (bash / WSL)

Use `backend/scripts/railway-db.sh` — it maps the `RAILWAY_DB_*` keys from `.env`
onto `DB_*` for one command, so local Docker config is untouched. See the
`#database` skill for full details.

```bash
# Run a Python script/command against Railway:
PYTHONPATH=backend/src backend/scripts/railway-db.sh python backend/scripts/verify_schema.py

# Run raw SQL (query or .sql file):
backend/scripts/railway-db.sh -q "SELECT COUNT(*) FROM mutaties"
backend/scripts/railway-db.sh -f backend/sql/migration.sql
```

> Replaced the retired `railway-sql.ps1` / `railway-run.ps1` (project migrated
> off Windows PowerShell to Linux/WSL). `connect-railway-backend.ps1` (local
> frontend → Railway backend API) is the last remaining PowerShell helper.

## Environment Configuration

Both frontend and backend use `.env` files. Copy `.env.example` to `.env`.

**Backend Key Variables**:

- `TEST_MODE`: true/false (switches test/production databases)
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`: Database connection
- `SNS_TOPIC_ARN`, `AWS_REGION`: AWS notifications
- `OPENROUTER_API_KEY`: AI invoice extraction (optional)
- `CREDENTIALS_ENCRYPTION_KEY`: Tenant credential encryption

**Frontend Key Variables** (Vite uses `VITE_` prefix, accessed via `import.meta.env`):

- `VITE_API_URL`: Backend API URL
- `VITE_COGNITO_USER_POOL_ID`, `VITE_COGNITO_CLIENT_ID`, `VITE_COGNITO_DOMAIN`, `VITE_AWS_REGION`: AWS Cognito
- `VITE_REDIRECT_SIGN_IN`, `VITE_REDIRECT_SIGN_OUT`: OAuth redirect URLs
- `VITE_DOCS_URL`: Documentation URL
