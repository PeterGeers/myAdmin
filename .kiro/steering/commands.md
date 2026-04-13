---
inclusion: manual
---

# Commands & Environment

Pull into context with `#commands` when you need build/run/test commands or environment setup.

## Frontend

```bash
cd frontend
npm start                    # Dev server (port 3000)
npm test                     # Unit tests
npm run test:e2e             # Playwright E2E tests
npm run test:e2e:ui          # E2E tests with UI
npm run lint                 # ESLint
npm run build                # Production build
npm run build:ci             # CI build (ESLint disabled)
```

## Backend

```bash
cd backend
.\.venv\Scripts\Activate.ps1  # Activate venv (Windows)
python src/app.py             # Flask server (port 5000)
.\powershell\start_backend.ps1  # Or use PowerShell script

pytest                        # All tests
pytest tests/unit/            # Unit tests only
pytest tests/api/             # API tests only
pytest tests/integration/     # Integration tests only
pytest --cov=src tests/       # With coverage
.\powershell\run_tests.ps1    # Or use PowerShell script
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

## Environment Configuration

Both frontend and backend use `.env` files. Copy `.env.example` to `.env`.

**Backend Key Variables**:

- `TEST_MODE`: true/false (switches test/production databases)
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`: Database connection
- `SNS_TOPIC_ARN`, `AWS_REGION`: AWS notifications
- `OPENROUTER_API_KEY`: AI invoice extraction (optional)
- `CREDENTIALS_ENCRYPTION_KEY`: Tenant credential encryption

**Frontend Key Variables**:

- `REACT_APP_API_URL`: Backend API URL
- AWS Cognito configuration variables
