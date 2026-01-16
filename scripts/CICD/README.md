# CI/CD Pipeline

Complete CI/CD pipeline for myAdmin application with database safety, container management, and automated deployment.

## 📖 Full Documentation

**See [DOCUMENTATION.md](DOCUMENTATION.md) for complete documentation.**

---

## ⚡ Quick Commands

```powershell
# Deploy with auto-commit (testing/development)
.\scripts\cicd\pipeline.ps1

# Deploy with custom commit message
.\scripts\cicd\pipeline.ps1 -CommitMessage "Feature: Added new report"

# Production deployment with git tag
.\scripts\cicd\pipeline.ps1 -Environment production -Tag "v1.2.0"

# Skip git operations
.\scripts\cicd\pipeline.ps1 -SkipGit

# Fix container issues
.\scripts\cicd\check-containers.ps1 -Fix

# Deep clean (before laptop restart!)
.\scripts\cicd\deep-clean.ps1

# Rollback database
.\scripts\cicd\rollback.ps1 -ListBackups
```

---

## 📚 What's Included

### Scripts

- **build.ps1** - Build and validate application
- **deploy.ps1** - Safe deployment with database backup
- **pipeline.ps1** - Complete git → build → deploy → verify
- **rollback.ps1** - Database rollback from backup
- **check-containers.ps1** - Container health diagnostics
- **deep-clean.ps1** - Deep clean and Docker restart

### Features

- ✅ **Git integration** - Auto-commit and tag releases
- ✅ Automatic database backups before deployment
- ✅ Container health checks and auto-recovery
- ✅ Code linting and testing
- ✅ Smoke tests and health checks
- ✅ Comprehensive logging
- ✅ Quick rollback capability

---

## 🆘 Container Issues?

Most common problem with Docker on Windows:

```powershell
# Step 1: Quick fix
.\scripts\cicd\check-containers.ps1 -Fix

# Step 2: Deep clean (if quick fix doesn't work)
.\scripts\cicd\deep-clean.ps1

# Step 3: Laptop restart (last resort)
# Restart → docker-compose up -d
```

---

## 📖 Documentation Structure

The complete documentation includes:

1. **Quick Start** - Get started in minutes
2. **Overview** - Understanding the pipeline
3. **Scripts Reference** - Detailed script documentation
4. **Database Safety** - Backup and rollback procedures
5. **Deployment Workflows** - Common deployment scenarios
6. **Container Troubleshooting** - Fix Docker issues
7. **Best Practices** - Recommended workflows
8. **Advanced Usage** - Power user features

**Read the full documentation:** [DOCUMENTATION.md](DOCUMENTATION.md)

---

## 🎯 Common Scenarios

| Scenario               | Command                                               |
| ---------------------- | ----------------------------------------------------- |
| Regular deployment     | `.\scripts\cicd\pipeline.ps1`                         |
| Production deployment  | `.\scripts\cicd\pipeline.ps1 -Environment production` |
| Containers won't start | `.\scripts\cicd\deep-clean.ps1`                       |
| Rollback database      | `.\scripts\cicd\rollback.ps1`                         |
| Check container health | `.\scripts\cicd\check-containers.ps1`                 |
| Build only             | `.\scripts\cicd\build.ps1`                            |

---

For complete documentation with examples, troubleshooting, and best practices, see **[DOCUMENTATION.md](DOCUMENTATION.md)**.
