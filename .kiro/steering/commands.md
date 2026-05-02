---
inclusion: manual
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
.\.venv\Scripts\Activate.ps1  # Activate venv (Windows)
python src/app.py             # Flask server (port 5000)
.\powershell\start_backend.ps1  # Or use PowerShell script

pytest                        # All tests
pytest tests/unit/            # Unit tests only
pytest tests/unit/test_maintenance/ -v  # Test maintenance framework tests
pytest tests/api/             # API tests only
pytest tests/integration/     # Integration tests only
pytest --cov=src tests/       # With coverage
.\powershell\run_tests.ps1    # Or use PowerShell script
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
mysql -u peter -p             # Connect to MySQL
python scripts/database/fix_database_views.py  # Run migrations
```

## Railway (Production)

All scripts in `backend/powershell/`. Run from the `backend/` directory.

```powershell
# Run SQL queries against Railway MySQL
.\powershell\railway-sql.ps1 -Query "SELECT COUNT(*) FROM mutaties"
.\powershell\railway-sql.ps1 -File "sql/migration.sql"
.\powershell\railway-sql.ps1 -TestDb -Query "SHOW TABLES"

# Run Python scripts against Railway MySQL (migrations, data fixes, ad-hoc testing)
.\powershell\railway-run.ps1 -Script "scripts/database/fix_database_views.py"
.\powershell\railway-run.ps1 -Script "src/app.py"        # Local backend, Railway DB
.\powershell\railway-run.ps1 -TestDb -Script "my_fix.py"  # Against testfinance

# Local frontend pointing at Railway backend
.\powershell\connect-railway-backend.ps1
```

Railway MySQL proxy: `shinkansen.proxy.rlwy.net:42375`
Railway backend: `https://invigorating-celebration-production.up.railway.app`

**Railway DB connection from Python (Kiro):**

- Get password: `railway variables` → use `DB_PASSWORD` from the backend service
- Connect to database `railway`, then `USE finance` (the data lives in `finance`)
- The `railway-run.ps1` scripts prompt for password interactively — for Kiro, set env vars directly:
  ```
  $env:DB_HOST='shinkansen.proxy.rlwy.net'; $env:DB_PORT='42375'; $env:DB_USER='root'; $env:DB_PASSWORD='<from railway variables>'; $env:DB_NAME='railway'
  ```

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
