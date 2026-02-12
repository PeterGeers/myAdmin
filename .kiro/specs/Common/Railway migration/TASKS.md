# Railway Migration - Implementation Tasks

**Status**: Backend Complete ✅ | Frontend & Database Pending ⏳  
**Last Updated**: February 12, 2026

---

## ✅ COMPLETED TASKS

### Phase 5: Railway Backend Deployment (COMPLETE)

- [x] 5.1 Railway account created
- [x] 5.2 MySQL service provisioned
- [x] 5.3 Environment variables configured
- [x] 5.4 Dockerfile optimized for Railway
- [x] 5.5 Fixed import path issues
- [x] 5.6 Added credential_service.py to git
- [x] 5.7 Created start_railway.py wrapper
- [x] 5.8 Fixed security middleware (health check whitelist)
- [x] 5.9 Fixed proxy header validation
- [x] 5.10 Backend deployed successfully
- [x] 5.11 Health checks passing
- [x] 5.12 Domain generated and working

**Backend URL**: https://invigorating-celebration-production.up.railway.app

---

## ⏳ PENDING TASKS

### Phase 6: Database Migration (PRIORITY: HIGH)

**Goal**: Migrate local MySQL database to Railway MySQL

**Prerequisites**:

- [x] Railway MySQL service running
- [x] Connection details available
- [ ] Local database backup created

#### 6.1 Export Local Database (30 minutes)

- [ ] Connect to local MySQL

  ```bash
  mysql -u peter -p
  ```

- [ ] Verify database size

  ```sql
  SELECT
    table_schema AS 'Database',
    ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)'
  FROM information_schema.tables
  WHERE table_schema = 'finance'
  GROUP BY table_schema;
  ```

- [ ] Export full database

  ```bash
  mysqldump -u peter -p finance > railway_migration_backup.sql
  ```

- [ ] Verify export file created

  ```bash
  ls -lh railway_migration_backup.sql
  ```

- [ ] Create compressed backup (optional, if file is large)
  ```bash
  gzip railway_migration_backup.sql
  ```

**Deliverable**: `railway_migration_backup.sql` file

---

#### 6.2 Get Railway MySQL Connection Details (5 minutes)

- [ ] Go to Railway Dashboard → MySQL service
- [ ] Click **Connect** tab
- [ ] Copy connection details:
  - [ ] Host: `_____________________`
  - [ ] Port: `_____________________`
  - [ ] Username: `_____________________`
  - [ ] Password: `_____________________`
  - [ ] Database: `_____________________`

- [ ] Test connection from local machine
  ```bash
  mysql -h <host> -P <port> -u <username> -p<password> -e "SELECT 1;"
  ```

**Deliverable**: Working connection to Railway MySQL

---

#### 6.3 Import Database to Railway (30-60 minutes)

- [ ] Import database

  ```bash
  mysql -h <host> -P <port> -u <username> -p<password> <database> < railway_migration_backup.sql
  ```

- [ ] Monitor import progress (if large database)

  ```bash
  # In another terminal, watch file size being processed
  watch -n 5 'mysql -h <host> -P <port> -u <username> -p<password> <database> -e "SHOW TABLES;"'
  ```

- [ ] Handle errors if any:
  - [ ] Check for character encoding issues
  - [ ] Verify MySQL version compatibility
  - [ ] Check for storage space on Railway

**Deliverable**: Database imported to Railway

---

#### 6.4 Verify Database Import (15 minutes)

- [ ] Connect to Railway MySQL

  ```bash
  mysql -h <host> -P <port> -u <username> -p<password> <database>
  ```

- [ ] Verify tables exist

  ```sql
  SHOW TABLES;
  ```

- [ ] Check row counts match local database

  ```sql
  SELECT 'mutaties' AS table_name, COUNT(*) AS row_count FROM mutaties
  UNION ALL
  SELECT 'bnb', COUNT(*) FROM bnb
  UNION ALL
  SELECT 'bnbplanned', COUNT(*) FROM bnbplanned
  UNION ALL
  SELECT 'bnbfuture', COUNT(*) FROM bnbfuture
  UNION ALL
  SELECT 'listings', COUNT(*) FROM listings
  UNION ALL
  SELECT 'tenants', COUNT(*) FROM tenants
  UNION ALL
  SELECT 'users', COUNT(*) FROM users;
  ```

- [ ] Test sample queries

  ```sql
  -- Test mutaties table
  SELECT * FROM mutaties LIMIT 5;

  -- Test bnb table
  SELECT * FROM bnb LIMIT 5;

  -- Test views (if any)
  SELECT * FROM vw_mutaties LIMIT 5;
  ```

- [ ] Verify indexes exist

  ```sql
  SHOW INDEX FROM mutaties;
  ```

- [ ] Check for any import warnings
  ```sql
  SHOW WARNINGS;
  ```

**Deliverable**: Verified database with all data

---

#### 6.5 Test Backend with Database (15 minutes)

- [ ] Restart Railway backend service (to pick up database)
- [ ] Test health check still works

  ```bash
  curl https://invigorating-celebration-production.up.railway.app/api/health
  ```

- [ ] Test database-dependent endpoint (with auth token)

  ```bash
  curl -H "Authorization: Bearer <token>" \
       https://invigorating-celebration-production.up.railway.app/api/reports/
  ```

- [ ] Check Railway logs for database connection
- [ ] Verify no database errors in logs

**Deliverable**: Backend successfully connected to Railway database

---

### Phase 7: Frontend Deployment (PRIORITY: HIGH)

**Goal**: Deploy React frontend to Railway or Vercel

**Prerequisites**:

- [x] Backend deployed and working
- [ ] Database migrated
- [ ] Backend URL known

#### 7.1 Update Frontend Configuration (10 minutes)

- [ ] Navigate to frontend directory

  ```bash
  cd frontend
  ```

- [ ] Update `.env` file

  ```bash
  # Create/update .env file
  REACT_APP_API_URL=https://invigorating-celebration-production.up.railway.app
  ```

- [ ] Copy all other environment variables from `.env.example`
  - [ ] AWS Cognito configuration
  - [ ] Any other REACT*APP*\* variables

- [ ] Test build locally

  ```bash
  npm run build
  ```

- [ ] Verify build succeeds with no errors

**Deliverable**: Updated frontend configuration

---

#### 7.2 Deploy Frontend to Railway (30 minutes)

**Option A: Railway (Recommended)**

- [ ] Go to Railway Dashboard
- [ ] Click **+ New** in myAdmin project
- [ ] Select **GitHub Repo**
- [ ] Choose **PeterGeers/myAdmin** repository
- [ ] Railway detects React app

- [ ] Configure service settings:
  - [ ] Root Directory: `frontend`
  - [ ] Build Command: `npm run build`
  - [ ] Start Command: `npx serve -s build -l $PORT`
  - [ ] Install Command: `npm install`

- [ ] Add environment variables in Railway UI:
  - [ ] `REACT_APP_API_URL=https://invigorating-celebration-production.up.railway.app`
  - [ ] Copy all other `REACT_APP_*` variables

- [ ] Deploy and wait for build
- [ ] Check deployment logs for errors

- [ ] Generate domain:
  - [ ] Go to Settings → Networking
  - [ ] Click **Generate Domain**
  - [ ] Note frontend URL: `_____________________`

**Deliverable**: Frontend deployed to Railway

---

**Option B: Vercel (Alternative)**

- [ ] Install Vercel CLI

  ```bash
  npm install -g vercel
  ```

- [ ] Login to Vercel

  ```bash
  vercel login
  ```

- [ ] Create `.env.production` file

  ```bash
  echo "REACT_APP_API_URL=https://invigorating-celebration-production.up.railway.app" > .env.production
  ```

- [ ] Deploy to Vercel

  ```bash
  cd frontend
  vercel --prod
  ```

- [ ] Add environment variables in Vercel Dashboard:
  - [ ] Go to project settings
  - [ ] Add all `REACT_APP_*` variables
  - [ ] Redeploy

- [ ] Note frontend URL: `_____________________`

**Deliverable**: Frontend deployed to Vercel

---

#### 7.3 Update CORS Configuration (10 minutes)

- [ ] Update backend CORS to allow frontend domain

  ```python
  # backend/src/app.py
  CORS(app, origins=[
      "https://frontend-production-xxxx.up.railway.app",  # Railway
      # OR
      "https://your-app.vercel.app",  # Vercel
      "http://localhost:3000"  # Local development
  ])
  ```

- [ ] Commit and push changes

  ```bash
  git add backend/src/app.py
  git commit -m "Update CORS for frontend domain"
  git push origin main
  ```

- [ ] Wait for Railway to redeploy backend

**Deliverable**: CORS configured for frontend

---

#### 7.4 Test Frontend (30 minutes)

- [ ] Open frontend URL in browser
- [ ] Verify page loads without errors
- [ ] Check browser console for errors
- [ ] Test login flow:
  - [ ] Click login
  - [ ] Redirected to Cognito
  - [ ] Login with credentials
  - [ ] Redirected back to app
  - [ ] JWT token received

- [ ] Test tenant selection:
  - [ ] Tenant dropdown appears
  - [ ] Can select tenant
  - [ ] Tenant context switches

- [ ] Test basic navigation:
  - [ ] Dashboard loads
  - [ ] Menu items work
  - [ ] Pages load without errors

**Deliverable**: Working frontend application

---

### Phase 8: End-to-End Testing (PRIORITY: MEDIUM)

**Goal**: Verify all features work in production

#### 8.1 Test Invoice Management (30 minutes)

- [ ] Upload invoice (PDF)
- [ ] Verify AI extraction works
- [ ] Edit invoice details
- [ ] Save invoice
- [ ] Verify stored in Google Drive
- [ ] View invoice in list

**Deliverable**: Invoice management working

---

#### 8.2 Test Banking Processor (20 minutes)

- [ ] Upload bank statement (CSV)
- [ ] Verify transactions parsed
- [ ] Check duplicate detection
- [ ] Verify pattern matching
- [ ] Save transactions
- [ ] View in transaction list

**Deliverable**: Banking processor working

---

#### 8.3 Test STR Processor (20 minutes)

- [ ] Upload STR file (Airbnb/Booking.com)
- [ ] Verify bookings parsed
- [ ] Check realized vs planned separation
- [ ] View future revenue summary
- [ ] Verify data in database

**Deliverable**: STR processor working

---

#### 8.4 Test Reports (30 minutes)

- [ ] Generate Aangifte IB report
- [ ] Generate BTW report
- [ ] Generate Toeristenbelasting report
- [ ] Generate P&L statement
- [ ] Export to Excel
- [ ] Verify charts render correctly

**Deliverable**: Reports working

---

#### 8.5 Test Tenant Admin Features (20 minutes)

- [ ] Access Tenant Admin page
- [ ] View template management
- [ ] Upload new template
- [ ] Preview template
- [ ] Test template validation
- [ ] Verify template saved

**Deliverable**: Tenant admin working

---

### Phase 9: Optimization & Monitoring (PRIORITY: LOW)

**Goal**: Set up monitoring and optimize performance

#### 9.1 Set Up Monitoring (30 minutes)

- [ ] Configure Railway alerts:
  - [ ] Deployment failures
  - [ ] Service crashes
  - [ ] High memory usage

- [ ] Configure AWS SNS alerts:
  - [ ] Application errors
  - [ ] Database issues
  - [ ] Authentication failures

- [ ] Set up error tracking (optional):
  - [ ] Sentry account
  - [ ] Install Sentry SDK
  - [ ] Configure error reporting

**Deliverable**: Monitoring configured

---

#### 9.2 Performance Optimization (1 hour)

- [ ] Review Railway metrics:
  - [ ] CPU usage
  - [ ] Memory usage
  - [ ] Response times

- [ ] Optimize database queries:
  - [ ] Add missing indexes
  - [ ] Optimize slow queries
  - [ ] Enable query caching

- [ ] Optimize frontend:
  - [ ] Enable code splitting
  - [ ] Optimize images
  - [ ] Enable caching

**Deliverable**: Performance optimized

---

#### 9.3 Documentation (30 minutes)

- [ ] Update README.md:
  - [ ] Add Railway URLs
  - [ ] Update deployment instructions
  - [ ] Add troubleshooting section

- [ ] Document environment variables:
  - [ ] Backend variables
  - [ ] Frontend variables
  - [ ] Required vs optional

- [ ] Create deployment checklist
- [ ] Document backup procedures

**Deliverable**: Documentation updated

---

## Summary

### Total Estimated Time

- **Database Migration**: 1.5-2 hours
- **Frontend Deployment**: 1-1.5 hours
- **Testing**: 2-3 hours
- **Optimization**: 2 hours
- **Total**: 6.5-8.5 hours

### Critical Path

1. Database Migration (blocks everything)
2. Frontend Deployment (blocks testing)
3. End-to-End Testing (validates everything)
4. Optimization (nice to have)

### Success Criteria

- [ ] Backend running on Railway ✅
- [ ] Database migrated to Railway
- [ ] Frontend deployed and accessible
- [ ] Users can login
- [ ] All core features working
- [ ] No critical errors in logs

---

## Notes

- Backend is already deployed and working ✅
- Focus on database migration first (highest priority)
- Frontend deployment is straightforward
- Most time will be spent on testing and verification
- Keep local database backup until everything is verified

---

## Quick Start for Tomorrow

1. **Start with database migration** (highest priority)
2. **Deploy frontend** (once database is working)
3. **Test end-to-end** (verify everything works)
4. **Optimize later** (not critical for launch)

**Remember**: The hard part (backend deployment) is done! The rest is configuration and testing.
