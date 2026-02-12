# Railway Migration - Next Steps

**Current Status**: Backend deployed and running ✅  
**Next Phase**: Frontend deployment and database migration

---

## Phase 1: Database Migration (Priority: HIGH)

### Why First?

The backend is running but has no data. Without the database, the frontend can't function properly.

### Steps

#### 1.1 Export Local Database

```bash
# From your local machine
cd C:\Users\peter\aws\myAdmin

# Export the database
mysqldump -u peter -p finance > railway_migration_backup.sql

# Or export specific tables if database is large
mysqldump -u peter -p finance mutaties bnb bnbplanned bnbfuture > railway_migration_backup.sql
```

#### 1.2 Get Railway MySQL Connection Details

1. Go to Railway Dashboard
2. Click on **MySQL** service
3. Go to **Connect** tab
4. Copy connection details:
   - Host
   - Port
   - Username
   - Password
   - Database name

#### 1.3 Import to Railway MySQL

```bash
# Option A: Direct import (if Railway allows external connections)
mysql -h <railway-host> -P <port> -u <username> -p<password> <database> < railway_migration_backup.sql

# Option B: Use Railway CLI (if working)
railway run mysql -u <username> -p < railway_migration_backup.sql
```

#### 1.4 Verify Import

```bash
# Connect to Railway MySQL
mysql -h <railway-host> -P <port> -u <username> -p<password> <database>

# Check tables
SHOW TABLES;

# Check row counts
SELECT COUNT(*) FROM mutaties;
SELECT COUNT(*) FROM bnb;
```

**Estimated Time**: 30-60 minutes  
**Complexity**: Medium

---

## Phase 2: Frontend Deployment (Priority: HIGH)

### Option A: Deploy to Railway (Recommended - Same Platform)

#### 2.1 Update Frontend Environment

```bash
cd frontend

# Update .env file
REACT_APP_API_URL=https://invigorating-celebration-production.up.railway.app
```

#### 2.2 Create Railway Service for Frontend

1. Go to Railway Dashboard
2. Click **+ New** in your myAdmin project
3. Select **GitHub Repo**
4. Choose **PeterGeers/myAdmin**
5. Railway will detect it's a React app

#### 2.3 Configure Frontend Service

**Settings**:

- Root Directory: `frontend`
- Build Command: `npm run build`
- Start Command: `npx serve -s build -l $PORT`
- Install Command: `npm install`

**Environment Variables**:

```
REACT_APP_API_URL=https://invigorating-celebration-production.up.railway.app
# Add other REACT_APP_* variables from frontend/.env
```

#### 2.4 Generate Domain

1. Go to frontend service **Settings**
2. Scroll to **Networking**
3. Click **Generate Domain**
4. Get URL like: `frontend-production-xxxx.up.railway.app`

**Estimated Time**: 20-30 minutes  
**Complexity**: Low

---

### Option B: Deploy to Vercel (Alternative - Optimized for React)

#### 2.1 Install Vercel CLI

```bash
npm install -g vercel
```

#### 2.2 Deploy Frontend

```bash
cd frontend

# Update .env.production
echo "REACT_APP_API_URL=https://invigorating-celebration-production.up.railway.app" > .env.production

# Deploy
vercel --prod
```

#### 2.3 Configure Environment Variables in Vercel

1. Go to Vercel Dashboard
2. Select your project
3. Go to **Settings** → **Environment Variables**
4. Add all `REACT_APP_*` variables

**Estimated Time**: 15-20 minutes  
**Complexity**: Low

---

## Phase 3: Testing & Verification (Priority: MEDIUM)

### 3.1 Test Backend API

```bash
# Health check
curl https://invigorating-celebration-production.up.railway.app/api/health

# Test authenticated endpoint (need Cognito token)
curl -H "Authorization: Bearer <token>" https://invigorating-celebration-production.up.railway.app/api/reports/
```

### 3.2 Test Frontend

1. Open frontend URL in browser
2. Test login with Cognito
3. Verify tenant selection works
4. Test key features:
   - Invoice upload
   - Banking processor
   - STR processor
   - Reports generation

### 3.3 Test End-to-End Workflows

- Upload invoice → Process → View in reports
- Upload bank statement → Process → View transactions
- Upload STR file → Process → View bookings
- Generate reports → Export to Excel

**Estimated Time**: 1-2 hours  
**Complexity**: Medium

---

## Phase 4: Configuration & Optimization (Priority: LOW)

### 4.1 Custom Domain (Optional)

If you want to use pgeers.nl:

1. Add CNAME record: `@ → 3hinare9.up.railway.app`
2. Wait for DNS propagation (5-60 minutes)
3. Verify domain works

### 4.2 CORS Configuration

Verify CORS allows frontend domain:

```python
# backend/src/app.py
CORS(app, origins=[
    "https://frontend-production-xxxx.up.railway.app",
    "https://pgeers.nl"  # if using custom domain
])
```

### 4.3 Monitoring Setup

- Set up Railway alerts for deployment failures
- Configure AWS SNS for application alerts
- Set up error tracking (Sentry, optional)

**Estimated Time**: 30-60 minutes  
**Complexity**: Low

---

## Phase 5: Cleanup & Documentation (Priority: LOW)

### 5.1 Update Documentation

- Update README.md with Railway URLs
- Document deployment process
- Update environment variable documentation

### 5.2 Remove Local Dependencies

- Stop local Docker containers
- Archive local database backup
- Update local .env to point to Railway (for development)

### 5.3 Git Cleanup

- Remove debug files
- Clean up bug reports folder
- Tag release: `git tag v1.0-railway`

**Estimated Time**: 30 minutes  
**Complexity**: Low

---

## Troubleshooting Guide

### Database Connection Issues

- Verify Railway MySQL is running
- Check connection details are correct
- Ensure IP whitelist allows connections (if applicable)
- Check Railway logs for connection errors

### Frontend Build Failures

- Verify all dependencies in package.json
- Check Node.js version compatibility
- Review build logs in Railway/Vercel
- Ensure environment variables are set

### Authentication Issues

- Verify Cognito configuration
- Check JWT token expiration
- Ensure CORS allows frontend domain
- Review backend logs for auth errors

### API Errors

- Check backend logs in Railway
- Verify database has data
- Test endpoints with curl/Postman
- Check security middleware isn't blocking requests

---

## Success Criteria

### Backend ✅

- [x] Deployed to Railway
- [x] Health checks passing
- [x] Environment variables configured
- [x] Database connected

### Database ⏳

- [ ] Data exported from local
- [ ] Data imported to Railway
- [ ] Tables verified
- [ ] Sample queries work

### Frontend ⏳

- [ ] Deployed to Railway/Vercel
- [ ] Environment variables configured
- [ ] Can access backend API
- [ ] Login works

### End-to-End ⏳

- [ ] User can login
- [ ] User can upload files
- [ ] User can view reports
- [ ] All features functional

---

## Timeline Estimate

**Tomorrow (Day 1)**:

- Database migration: 1-2 hours
- Frontend deployment: 30-60 minutes
- Basic testing: 30 minutes
  **Total**: 2-3.5 hours

**Day 2** (if needed):

- Troubleshooting: 1-2 hours
- Comprehensive testing: 1-2 hours
- Documentation: 30 minutes
  **Total**: 2.5-4.5 hours

**Total Project Time**: 4.5-8 hours to complete migration

---

## Support Resources

- **Railway Docs**: https://docs.railway.com
- **Railway Discord**: https://discord.gg/railway
- **Vercel Docs**: https://vercel.com/docs
- **MySQL Import Guide**: https://dev.mysql.com/doc/refman/8.0/en/mysqldump.html

---

## Contact Points

If you encounter issues:

1. Check Railway deployment logs
2. Review backend application logs
3. Check database connection
4. Verify environment variables
5. Test with curl/Postman before frontend

**Remember**: The backend is working! Most issues will be configuration-related.
