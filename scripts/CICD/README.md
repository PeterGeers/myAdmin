# CI/CD Pipeline Scripts

Automated build, test, and deployment pipeline for myAdmin application.

## 📁 Folder Structure

```
scripts/CICD/
├── pipeline.ps1              # Main pipeline orchestrator
├── build.ps1                 # Build and test stage
├── deploy.ps1                # Deployment stage
├── rollback.ps1              # Rollback to previous version
├── check-containers.ps1      # Docker container health checks
├── recover-containers.ps1    # Container recovery utilities
├── deep-clean.ps1            # Deep cleanup of Docker resources
├── docs/                     # Documentation
│   ├── BACKUP_STRATEGY.md    # Database backup best practices
│   ├── DOCUMENTATION.md      # Detailed pipeline documentation
│   └── SECURITY_FIX_COMPLETED.md  # Security incident log
├── archive/                  # One-time use scripts (historical)
└── logs/                     # Pipeline execution logs
```

## 🚀 Quick Start

### Run Full Pipeline

```powershell
.\scripts\CICD\pipeline.ps1
```

This executes:

1. Build stage (linting, testing)
2. Deploy stage (Docker containers)
3. Health checks

### Individual Stages

```powershell
# Build and test only
.\scripts\CICD\build.ps1

# Deploy only (after successful build)
.\scripts\CICD\deploy.ps1

# Rollback to previous version
.\scripts\CICD\rollback.ps1
```

## 📋 Pipeline Stages

### 1. Build Stage (`build.ps1`)

**Backend:**

- Python linting (flake8)
- Backend tests (pytest with parallel execution)
- Minimum 95% pass rate required

**Frontend:**

- ESLint checks
- Frontend tests (Jest/React Testing Library)

**Duration:** ~8-10 minutes (with parallel testing)

### 2. Deploy Stage (`deploy.ps1`)

- Creates MySQL backup to OneDrive
- Stops existing containers
- Builds new Docker images
- Starts containers (MySQL, Backend, Frontend)
- Runs health checks

**Duration:** ~2-3 minutes

### 3. Health Checks

- Container status verification
- Service availability checks
- Automatic rollback on failure

## 🔧 Utility Scripts

### Container Management

```powershell
# Check container health
.\scripts\CICD\check-containers.ps1

# Recover failed containers
.\scripts\CICD\recover-containers.ps1

# Deep clean (removes all containers, images, volumes)
.\scripts\CICD\deep-clean.ps1
```

## 📊 Test Configuration

### Backend Tests

- **Location:** `backend/tests/`
- **Config:** `backend/pytest.ini`
- **Parallel:** 4 workers (`pytest-xdist`)
- **Pass Rate:** ≥95% required for deployment

### Frontend Tests

- **Location:** `frontend/tests/`
- **Config:** `frontend/.eslintrc.json`
- **Framework:** Jest + React Testing Library

## 📝 Logs

Pipeline logs are stored in `scripts/CICD/logs/`:

- `pipeline-YYYYMMDD-HHMMSS.log` - Full pipeline execution
- `build-YYYYMMDD-HHMMSS.log` - Build stage details
- `deploy-YYYYMMDD-HHMMSS.log` - Deployment details

Logs older than 7 days are automatically cleaned up.

## 🔒 Security

### Database Backups

- **Location:** `C:\Users\peter\OneDrive\MariaDB\finance`
- **Never** commit SQL backups to Git
- See `docs/BACKUP_STRATEGY.md` for details

### Credentials

- Stored in `.env` files (not in Git)
- Use environment variables for sensitive data

## 🐛 Troubleshooting

### Pipeline Fails at Build Stage

```powershell
# Check test results
Get-Content scripts/CICD/logs/build-*.log | Select-String "FAILED"

# Run tests manually
cd backend
.venv\Scripts\activate
pytest tests/ -v
```

### Pipeline Fails at Deploy Stage

```powershell
# Check container status
docker ps -a

# View container logs
docker logs myadmin-backend
docker logs myadmin-frontend
docker logs myadmin-mysql

# Recover containers
.\scripts\CICD\recover-containers.ps1
```

### Rollback Deployment

```powershell
# Automatic rollback (if deployment fails)
# Manual rollback
.\scripts\CICD\rollback.ps1
```

## 📚 Documentation

Detailed documentation available in `docs/`:

- **BACKUP_STRATEGY.md** - Database backup procedures
- **DOCUMENTATION.md** - Complete pipeline documentation
- **SECURITY_FIX_COMPLETED.md** - Security incident history

## ⚙️ Configuration

### Environment Variables

Required in `.env` files:

- `DATABASE_URL` - MySQL connection string
- `JWT_SECRET` - Authentication secret
- `AWS_REGION` - AWS region for SNS
- `SNS_TOPIC_ARN` - SNS topic for notifications

### Docker Configuration

- `docker-compose.yml` - Container orchestration
- Port mappings:
  - Frontend: 3000
  - Backend: 5000
  - MySQL: 3306

## 🔄 CI/CD Workflow

```
┌─────────────┐
│   Commit    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    Build    │  ← Lint + Test (8-10 min)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Deploy    │  ← Docker + Health Checks (2-3 min)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Success ✓  │
└─────────────┘
```

## 📈 Performance

- **Total Pipeline:** ~10-13 minutes
- **Parallel Testing:** 4 workers (2.5x speedup)
- **Pass Rate:** 97% (470/485 tests)

## 🆘 Support

For issues or questions:

1. Check logs in `scripts/CICD/logs/`
2. Review documentation in `docs/`
3. Run health checks: `.\scripts\CICD\check-containers.ps1`

---

**Last Updated:** January 21, 2026  
**Status:** ✅ Active and Optimized
