# Year-End Closure - Development Workflow

**Purpose**: Define the development, testing, and deployment approach for year-end closure

## Development Strategy

### Branch Strategy

```
main (production)
  └── feature/year-end-closure (development branch)
       ├── Work on all tasks here
       ├── Test in container environment
       └── Merge to main only when complete
```

**Key Points**:

- Create feature branch: `git checkout -b feature/year-end-closure`
- All development happens on this branch
- Regular commits with descriptive messages
- Merge to main only after full testing and approval

### Environment Setup

**Container Test Environment**:

- Use Docker container with TEST_MODE=false
- Separate test database (not production data)
- Safe environment for experimentation
- Can be reset/rebuilt as needed

**Configuration**:

```bash
# backend/.env
TEST_MODE=true
DB_HOST=mysql
DB_NAME=myAdmin_test
DB_USER=peter
DB_PASSWORD=[test_password]
```

## Development Phases

### Phase 1: Migration Script (First)

**Why First**: The migration script establishes the foundation. It's a one-time operation that can be tested thoroughly before building the user-facing feature.

**Workflow**:

1. Create feature branch
2. Implement migration script (TASKS-migration.md)
3. Test in container with test data
4. Validate results
5. Commit to feature branch
6. DO NOT merge to main yet

**Testing Approach**:

```bash
# In container
cd backend
source .venv/bin/activate

# Test with dry-run
python scripts/database/migrate_opening_balances.py --dry-run

# Test with single tenant
python scripts/database/migrate_opening_balances.py --tenant "Test Tenant"

# Test full migration
python scripts/database/migrate_opening_balances.py

# Validate results
pytest tests/integration/test_migration_integration.py
```

### Phase 2: Closure Feature (Second)

**Why Second**: The feature depends on the migration being complete. Users will use this repeatedly after the one-time migration.

**Workflow**:

1. Continue on same feature branch
2. Implement closure feature (TASKS-closure.md)
3. Test in container with test data
4. Test integration with migration results
5. Commit to feature branch
6. DO NOT merge to main yet

**Testing Approach**:

```bash
# Backend tests
pytest tests/unit/test_year_end_service.py
pytest tests/api/test_year_end_routes.py
pytest tests/integration/test_year_end_integration.py

# Frontend tests
cd frontend
npm test

# E2E tests
npm run test:e2e
```

### Phase 3: Integration Testing (Third)

**Why Third**: Verify everything works together in the container environment before touching production.

**Workflow**:

1. Still on feature branch
2. Test complete workflow:
   - Run migration script
   - Use closure feature to close a year
   - Verify reports work correctly
   - Check performance improvements
3. Test edge cases and error scenarios
4. Document any issues found
5. Fix issues and retest

**Test Scenarios**:

- [ ] Migration creates opening balances correctly
- [ ] Closure feature validates properly
- [ ] Year-end closure transaction created correctly
- [ ] Opening balances for next year created correctly
- [ ] Reports show correct values
- [ ] Reports run faster (measure before/after)
- [ ] Permissions work correctly
- [ ] Error handling works
- [ ] Can't close year twice
- [ ] Can't close year before previous year

### Phase 4: Staging Deployment (Fourth)

**Why Fourth**: Test with production-like data before actual production deployment.

**Workflow**:

1. Still on feature branch
2. Deploy to staging environment
3. Copy production database to staging
4. Run migration script on staging with --dry-run
5. Review results carefully
6. Run migration script on staging (for real)
7. Test closure feature on staging
8. Get stakeholder approval

**Staging Checklist**:

- [ ] Database backup created
- [ ] Migration script runs without errors
- [ ] Validation passes for all tenants
- [ ] Reports show same values as before
- [ ] Reports run significantly faster
- [ ] Closure feature works correctly
- [ ] UI is intuitive
- [ ] No errors in logs
- [ ] Stakeholder approval obtained

### Phase 5: Production Deployment (Final)

**Why Final**: Only deploy to production after everything is proven to work.

**Workflow**:

1. Merge feature branch to main
2. Deploy to production
3. Run migration script on production
4. Monitor closely
5. Verify success

**Production Deployment Steps**:

```bash
# 1. Merge to main
git checkout main
git merge feature/year-end-closure
git push origin main

# 2. Backup production database
# (Use your backup procedure)

# 3. Deploy code
# (Use your deployment procedure - Railway, Docker, etc.)

# 4. Run migration script
# SSH into production container or use Railway CLI
python scripts/database/migrate_opening_balances.py --dry-run
# Review output carefully
python scripts/database/migrate_opening_balances.py
# Monitor execution

# 5. Verify
# - Check logs for errors
# - Test reports
# - Test closure feature
# - Monitor performance
```

## Container Development Workflow

### Daily Development Cycle

```bash
# 1. Start containers
docker-compose up -d

# 2. Check containers are running
docker-compose ps

# 3. Work on code in your IDE
# - Edit files in backend/ or frontend/
# - Changes are reflected in container via volumes

# 4. Test backend changes
docker-compose exec backend bash
cd /app
source .venv/bin/activate
pytest tests/unit/test_year_end_service.py

# 5. Test frontend changes
cd frontend
npm start
# Test in browser at http://localhost:3000

# 6. Commit changes
git add .
git commit -m "Implement year-end validation logic"
git push origin feature/year-end-closure

# 7. Stop containers (optional)
docker-compose down
```

### Database Management in Container

```bash
# Connect to MySQL in container
docker-compose exec mysql mysql -u peter -p myAdmin_test

# Reset test database (if needed)
docker-compose exec mysql mysql -u peter -p -e "DROP DATABASE myAdmin_test; CREATE DATABASE myAdmin_test;"

# Run database scripts
docker-compose exec backend python scripts/database/migrate_opening_balances.py

# View logs
docker-compose logs -f backend
docker-compose logs -f mysql
```

### Testing in Container

```bash
# Backend unit tests
docker-compose exec backend pytest tests/unit/

# Backend integration tests
docker-compose exec backend pytest tests/integration/

# Backend API tests
docker-compose exec backend pytest tests/api/

# All backend tests
docker-compose exec backend pytest

# Frontend tests (run on host, not in container)
cd frontend
npm test
npm run test:e2e
```

## Git Workflow

### Feature Branch Commits

**Commit Often**:

- Commit after completing each task
- Use descriptive commit messages
- Reference task numbers if helpful

**Example Commits**:

```bash
git commit -m "Add parameters column to rekeningschema table"
git commit -m "Implement OpeningBalanceMigrator class"
git commit -m "Add validation logic for year closure"
git commit -m "Create YearClosureWizard component"
git commit -m "Add unit tests for year-end service"
```

### Before Merging to Main

**Checklist**:

- [ ] All tasks completed
- [ ] All tests passing
- [ ] Code reviewed
- [ ] Documentation updated
- [ ] Tested in container
- [ ] Tested on staging
- [ ] Stakeholder approval
- [ ] No merge conflicts with main

**Merge Process**:

```bash
# Update feature branch with latest main
git checkout feature/year-end-closure
git fetch origin
git merge origin/main
# Resolve any conflicts
git push origin feature/year-end-closure

# Merge to main
git checkout main
git merge feature/year-end-closure
git push origin main
```

## Migration Timing

### When to Run Migration Script

**NOT in Development**:

- Don't run on production data during development
- Use test data in container only

**NOT Immediately After Code Deploy**:

- Deploy code first
- Test the feature with existing data
- Verify everything works

**ONLY After Full Testing**:

- All tests pass
- Staging deployment successful
- Stakeholder approval obtained
- Production deployment complete
- Feature verified working

**Production Migration**:

```bash
# 1. Code is deployed and working
# 2. Feature is tested and approved
# 3. NOW run migration:

# Dry-run first
python scripts/database/migrate_opening_balances.py --dry-run
# Review output carefully

# Real migration
python scripts/database/migrate_opening_balances.py
# Monitor execution
# Verify results
```

## Rollback Strategy

### If Migration Fails

**Before Migration**:

- Database backup exists
- Can restore from backup

**During Migration**:

- Script uses transactions
- Automatic rollback on error
- Check logs for details

**After Migration**:

- If issues found, restore from backup
- Fix issues in code
- Retest in container
- Try again

### If Feature Has Issues

**Before Merge to Main**:

- Just fix on feature branch
- No impact to production

**After Merge to Main**:

- Revert merge commit
- Fix issues on feature branch
- Retest and merge again

## Summary

**Development Flow**:

1. Create feature branch
2. Develop in container with TEST_MODE=true
3. Implement migration script first
4. Implement closure feature second
5. Test thoroughly in container
6. Deploy to staging
7. Test on staging with production-like data
8. Get approval
9. Merge to main
10. Deploy to production
11. Run migration script on production
12. Monitor and verify

**Key Principles**:

- Feature branch for all development
- Container for safe testing
- Migration script runs AFTER code deployment
- Test thoroughly before production
- Always have database backups
- Monitor production deployment closely
