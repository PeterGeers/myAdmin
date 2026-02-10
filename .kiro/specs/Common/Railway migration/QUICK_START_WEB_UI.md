# Railway Deployment - Quick Start (Web UI)

## Overview

Deploy myAdmin to Railway using the web interface (no CLI needed).

## Prerequisites

- ✅ Railway account created
- ✅ GitHub account linked to Railway
- ✅ myAdmin repository on GitHub

## Step-by-Step Deployment

### 1. Create New Project

1. Go to https://railway.app/dashboard
2. Click **"New Project"**
3. Select **"Empty Project"**
4. Name it: `myAdmin`

### 2. Add MySQL Database

1. In your project, click **"+ New"**
2. Select **"Database"** → **"MySQL"**
3. Railway provisions MySQL automatically
4. Click on MySQL service to view connection details
5. **Note**: Railway provides these variables automatically:
   - `MYSQL_HOST`
   - `MYSQL_PORT`
   - `MYSQL_USER`
   - `MYSQL_PASSWORD`
   - `MYSQL_DATABASE`

### 3. Add Backend Service

1. Click **"+ New"** again
2. Select **"GitHub Repo"**
3. Choose **`PeterGeers/myAdmin`**
4. Railway will start analyzing your repo

### 4. Configure Backend Service

#### A. Settings Tab

1. Click on the backend service
2. Go to **"Settings"** tab
3. Set **Root Directory**: `backend`
4. Set **Build Command**: Leave empty (uses Dockerfile)
5. Set **Start Command**: Leave empty (uses Dockerfile CMD)

#### B. Variables Tab

1. Go to **"Variables"** tab
2. Click **"+ New Variable"**
3. Add these variables:

**Database Connection** (use Railway references):

```
DB_HOST=${{MySQL.MYSQL_HOST}}
DB_PORT=${{MySQL.MYSQL_PORT}}
DB_USER=${{MySQL.MYSQL_USER}}
DB_PASSWORD=${{MySQL.MYSQL_PASSWORD}}
DB_NAME=${{MySQL.MYSQL_DATABASE}}
```

**Application Settings**:

```
TEST_MODE=false
FLASK_RUN_HOST=0.0.0.0
FLASK_RUN_PORT=5000
FLASK_DEBUG=false
```

**AWS Cognito** (get from AWS Console):

```
AWS_REGION=eu-west-1
COGNITO_USER_POOL_ID=<your-pool-id>
COGNITO_APP_CLIENT_ID=<your-client-id>
```

**Encryption**:

```
CREDENTIALS_ENCRYPTION_KEY=<generate-secure-32-char-key>
```

**Optional - AWS SNS**:

```
SNS_TOPIC_ARN=<your-topic-arn>
```

### 5. Deploy

1. Click **"Deploy"** button
2. Railway will:
   - Build Docker image from `backend/Dockerfile`
   - Start MySQL container
   - Start Backend container
   - Provide public URL

### 6. Get Public URL

1. Go to **"Settings"** tab
2. Scroll to **"Networking"**
3. Click **"Generate Domain"**
4. Railway provides: `your-app.railway.app`

### 7. Initialize Database

Once deployed, you need to initialize the database:

**Option A: Use Railway CLI** (if installed):

```bash
railway run python scripts/database/initialize_db.py
```

**Option B: Connect directly**:

1. Get MySQL connection details from Railway
2. Use MySQL Workbench or similar tool
3. Run your SQL initialization scripts from `backend/sql/`

### 8. Update Frontend

Update your frontend `.env` to point to Railway backend:

```
REACT_APP_API_URL=https://your-backend.railway.app
```

## Troubleshooting

### Build Fails

- Check **"Deployments"** tab for logs
- Verify `backend/Dockerfile` exists
- Ensure all dependencies in `requirements.txt`

### Database Connection Fails

- Verify MySQL service is running
- Check environment variables are set correctly
- Ensure `DB_HOST` uses Railway reference: `${{MySQL.MYSQL_HOST}}`

### App Won't Start

- Check **"Logs"** tab
- Verify `FLASK_RUN_PORT=5000`
- Ensure Dockerfile exposes port 5000

## Cost Estimate

- **Hobby Plan** (Free tier):
  - $5/month credit
  - Good for testing
- **Pro Plan** ($20/month):
  - More resources
  - Better for production

## Next Steps

1. ✅ Deploy backend to Railway
2. ✅ Initialize database
3. ✅ Update frontend API URL
4. ✅ Deploy frontend (separate Railway service or Vercel)
5. ✅ Test end-to-end functionality

## Support

- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
- Railway Status: https://status.railway.app
