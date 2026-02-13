# Railway Infrastructure as Code Guide

**Status**: Ready for Implementation  
**Last Updated**: February 13, 2026

---

## Overview

This guide explains how to deploy myAdmin to Railway using true Infrastructure as Code with Railway's "Empty Service" + Config File approach.

All Railway deployment configuration is organized in the `railway/` folder, separate from application code.

---

## Project Structure

```
myAdmin/
├── backend/              # Backend application code
│   └── Dockerfile        # Backend container (unchanged)
├── frontend/             # Frontend application code
├── infrastructure/       # Terraform (AWS Cognito, SNS, etc.)
└── railway/              # ALL Railway-specific configuration
    ├── mysql/
    │   ├── Dockerfile    # MySQL container with crash prevention
    │   └── railway.toml  # MySQL build/deploy config
    ├── backend/
    │   └── railway.toml  # Backend build/deploy config (optional)
    └── frontend/
        └── railway.toml  # Frontend build/deploy config (optional)
```

---

## How Railway Config Files Work

1. **Create "Empty Service"** in Railway Dashboard
2. **Connect to GitHub repository** (Railway clones entire repo)
3. **Set Config File Path** (e.g., `railway/mysql/railway.toml`)
4. **Railway reads config** from that path in your repo
5. **All build/deploy settings** come from the config file

**This IS Infrastructure as Code**:
- ✅ Configuration in version control
- ✅ Changes via git commits
- ✅ Reproducible deployments
- ✅ No manual Dashboard configuration

---

## MySQL Configuration

### File: `railway/mysql/railway.toml`

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "railway/mysql/Dockerfile"

[deploy]
restartPolicyType = "ALWAYS"
```

### File: `railway/mysql/Dockerfile`

Custom MySQL 8.0 image with crash prevention settings baked in:

```dockerfile
FROM mysql:8.0

# Custom MySQL configuration for Railway
# Prevents crashes due to Railway's volume system and optimizes for cloud environment

RUN echo "[mysqld]" > /etc/mysql/conf.d/railway.cnf && \
    echo "# Disable native AIO (Railway volume compatibility)" >> /etc/mysql/conf.d/railway.cnf && \
    echo "innodb_use_native_aio=0" >> /etc/mysql/conf.d/railway.cnf && \
    echo "" >> /etc/mysql/conf.d/railway.cnf && \
    echo "# Use fsync for disk writes (Railway filesystem compatibility)" >> /etc/mysql/conf.d/railway.cnf && \
    echo "innodb_flush_method=fsync" >> /etc/mysql/conf.d/railway.cnf && \
    echo "" >> /etc/mysql/conf.d/railway.cnf && \
    echo "# Optimize buffer pool for cloud (256MB)" >> /etc/mysql/conf.d/railway.cnf && \
    echo "innodb_buffer_pool_size=268435456" >> /etc/mysql/conf.d/railway.cnf && \
    echo "" >> /etc/mysql/conf.d/railway.cnf && \
    echo "# Optimize log file size (64MB)" >> /etc/mysql/conf.d/railway.cnf && \
    echo "innodb_log_file_size=67108864" >> /etc/mysql/conf.d/railway.cnf && \
    echo "" >> /etc/mysql/conf.d/railway.cnf && \
    echo "# Limit connections for cloud environment" >> /etc/mysql/conf.d/railway.cnf && \
    echo "max_connections=100" >> /etc/mysql/conf.d/railway.cnf && \
    echo "" >> /etc/mysql/conf.d/railway.cnf && \
    echo "# Optimize table cache" >> /etc/mysql/conf.d/railway.cnf && \
    echo "table_open_cache=2000" >> /etc/mysql/conf.d/railway.cnf && \
    echo "" >> /etc/mysql/conf.d/railway.cnf && \
    echo "# Windows compatibility (case-insensitive table names)" >> /etc/mysql/conf.d/railway.cnf && \
    echo "lower_case_table_names=2" >> /etc/mysql/conf.d/railway.cnf

# Use mysql_native_password for Python connector compatibility
CMD ["mysqld", "--default-authentication-plugin=mysql_native_password"]
```

**Why These Settings Prevent Crashes**:
- `innodb_use_native_aio=0` - Railway's volume system doesn't support Linux native async I/O
- `innodb_flush_method=fsync` - Compatible with Railway's filesystem
- `innodb_buffer_pool_size=268435456` - 256MB optimized for cloud (default is too large)
- `lower_case_table_names=2` - Required for importing database from Windows
- `--default-authentication-plugin=mysql_native_password` - Python connector compatibility

---

## Backend Configuration (Optional)

### File: `railway/backend/railway.toml`

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "backend/Dockerfile"

[deploy]
startCommand = "python start_railway.py"
healthcheckPath = "/api/health"
healthcheckTimeout = 300
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

**Note**: Backend is already deployed and working. This config file is optional for future IaC management.

---

## Frontend Configuration (Optional)

### File: `railway/frontend/railway.toml`

```toml
[build]
builder = "NIXPACKS"
buildCommand = "npm install && npm run build"

[deploy]
startCommand = "npx serve -s build -l $PORT"
restartPolicyType = "ON_FAILURE"
```

---

## Deployment Process

### Step 1: Commit Configuration to Git

```bash
git add railway/
git commit -m "Add Railway IaC configuration"
git push origin main
```

### Step 2: Create MySQL Empty Service

1. **In Railway Dashboard**:
   - Click "+ New" → "Empty Service"
   - Name: "mysql"

2. **Configure Source**:
   - Settings → "Source"
   - Connect to GitHub repository
   - Select `PeterGeers/myAdmin` repository

3. **Set Config File Path**:
   - Settings → "Config as Code"
   - Enable "Railway Config File"
   - File Path: `railway/mysql/railway.toml`
   - Save

4. **Add Volume**:
   - Settings → "Volumes" → "+ Add Volume"
   - Mount Path: `/var/lib/mysql`
   - Size: 5GB

5. **Add Environment Variables** (one-time):
   ```bash
   MYSQL_ROOT_PASSWORD=<strong-password>
   MYSQL_DATABASE=finance
   MYSQL_USER=peter
   MYSQL_PASSWORD=<password>
   ```

6. **Deploy**

**Railway will**:
- Clone your repository
- Read `railway/mysql/railway.toml`
- Build using `railway/mysql/Dockerfile`
- Deploy MySQL with all crash prevention settings

---

### Step 3: Update Backend Service (Optional)

Your backend is already deployed. To add IaC config:

1. **Create `railway/backend/railway.toml`** (if not exists)
2. **Commit to git**
3. **In Railway Dashboard** → Backend service:
   - Settings → "Config as Code"
   - Enable "Railway Config File"
   - File Path: `railway/backend/railway.toml`
4. **Redeploy**

---

### Step 4: Create Frontend Service (When Ready)

1. **Create Empty Service** named "frontend"
2. **Connect to GitHub repository**
3. **Set Root Directory**: `frontend`
4. **Set Config File Path**: `railway/frontend/railway.toml`
5. **Add Environment Variables**:
   ```bash
   REACT_APP_API_URL=https://${{backend.RAILWAY_PUBLIC_DOMAIN}}
   REACT_APP_COGNITO_USER_POOL_ID=<secret>
   REACT_APP_COGNITO_APP_CLIENT_ID=<secret>
   REACT_APP_COGNITO_REGION=<secret>
   REACT_APP_COGNITO_DOMAIN=<secret>
   ```
6. **Generate Domain**
7. **Deploy**

---

## Environment Variables

### MySQL Service

```bash
MYSQL_ROOT_PASSWORD=<strong-password>
MYSQL_DATABASE=finance
MYSQL_USER=peter
MYSQL_PASSWORD=<password>
```

### Backend Service

```bash
# Database (reference MySQL service)
DB_HOST=${{mysql.RAILWAY_PRIVATE_DOMAIN}}
DB_PORT=3306
DB_USER=peter
DB_PASSWORD=${{mysql.MYSQL_PASSWORD}}
DB_NAME=finance

# Flask
FLASK_DEBUG=false
DOCKER_ENV=true
PORT=5000

# AWS
AWS_ACCESS_KEY_ID=<secret>
AWS_SECRET_ACCESS_KEY=<secret>
AWS_REGION=<secret>
SNS_TOPIC_ARN=<secret>

# Cognito
COGNITO_USER_POOL_ID=<secret>
COGNITO_APP_CLIENT_ID=<secret>
COGNITO_REGION=<secret>

# Google Drive
GOOGLE_DRIVE_FOLDER_ID=<secret>

# Optional
OPENROUTER_API_KEY=<secret>

# Encryption
CREDENTIALS_ENCRYPTION_KEY=<secret>

# Test Mode
TEST_MODE=false
```

### Frontend Service

```bash
# Backend API (reference backend service)
REACT_APP_API_URL=https://${{backend.RAILWAY_PUBLIC_DOMAIN}}

# Cognito
REACT_APP_COGNITO_USER_POOL_ID=<secret>
REACT_APP_COGNITO_APP_CLIENT_ID=<secret>
REACT_APP_COGNITO_REGION=<secret>
REACT_APP_COGNITO_DOMAIN=<secret>
```

**Service References**: Use `${{service.VARIABLE}}` syntax to reference other services.

---

## Updating Infrastructure

### To Change MySQL Configuration

1. Edit `railway/mysql/Dockerfile` or `railway/mysql/railway.toml`
2. Commit and push to git
3. Railway automatically rebuilds and redeploys

### To Change Backend Configuration

1. Edit `railway/backend/railway.toml`
2. Commit and push to git
3. Railway automatically redeploys

**No Dashboard changes needed** - all configuration comes from git.

---

## Railway Config File Reference

### Available Settings

**Build Settings**:
- `builder` - "DOCKERFILE" or "NIXPACKS"
- `dockerfilePath` - Path to Dockerfile (from repo root)
- `buildCommand` - Custom build command
- `watchPatterns` - Files to watch for changes

**Deploy Settings**:
- `startCommand` - Command to start service
- `restartPolicyType` - "ON_FAILURE", "ALWAYS", or "NEVER"
- `restartPolicyMaxRetries` - Number of retries
- `healthcheckPath` - Health check endpoint
- `healthcheckTimeout` - Timeout in seconds
- `numReplicas` - Number of replicas (Pro plan)

---

## Path Conventions

**Important**: Railway uses forward slashes `/` (Unix-style) for all paths, even on Windows.

**Examples**:
- ✅ `railway/mysql/Dockerfile`
- ✅ `railway/mysql/railway.toml`
- ✅ `backend/Dockerfile`
- ❌ `railway\mysql\Dockerfile` (wrong - backslashes)

Railway clones your entire GitHub repository, so it can access any file by specifying the path from the repository root.

---

## Benefits of This Approach

1. **Version Control**: All configuration in git
2. **Code Review**: Config changes go through PR process
3. **Rollback**: Git revert to previous configuration
4. **Documentation**: Config files document infrastructure
5. **Reproducible**: Can recreate services from scratch
6. **Testable**: Test config changes in branches
7. **Organized**: All Railway config in one `railway/` folder
8. **Portable**: Move to different Railway projects easily

---

## Troubleshooting

### MySQL Still Crashing

1. **Check logs**: Railway Dashboard → MySQL service → Deployments → Logs
2. **Try different MySQL version**: Change `FROM mysql:8.0` to `FROM mysql:8.0.40`
3. **Reduce buffer pool**: Change `innodb_buffer_pool_size=134217728` (128MB)

### Config File Not Detected

1. **Verify path**: Must use forward slashes `/`
2. **Check file exists**: Ensure file is committed to git
3. **Validate TOML syntax**: Use TOML validator
4. **Redeploy**: Click "Deploy" to force rebuild

### Service Won't Build

1. **Check Dockerfile path**: Verify path is correct from repo root
2. **Check logs**: Look for specific build errors
3. **Verify files exist**: Ensure all referenced files are in git

---

## Migration Checklist

- [x] Create `railway/` folder structure
- [x] Move MySQL config to `railway/mysql/`
- [ ] Commit configuration to git
- [ ] Create MySQL empty service in Railway
- [ ] Point MySQL to `railway/mysql/railway.toml`
- [ ] Add MySQL volume
- [ ] Add MySQL environment variables
- [ ] Deploy MySQL
- [ ] Verify MySQL is running (check logs)
- [ ] Import database
- [ ] Test backend connection to MySQL
- [ ] (Optional) Add backend config file
- [ ] (Optional) Create frontend service

---

## Next Steps

1. **Commit the railway/ folder** to git
2. **Create MySQL empty service** in Railway Dashboard
3. **Configure MySQL service** to use `railway/mysql/railway.toml`
4. **Add environment variables** (one-time)
5. **Deploy and verify** MySQL is running
6. **Import database** (see IMPORT-EXISTING-BACKUP.md)
7. **Test end-to-end**

This is true Infrastructure as Code - your Railway infrastructure is defined in version-controlled configuration files.

