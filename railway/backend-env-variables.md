# Backend Environment Variables for Railway

## Instructions

1. Go to Railway dashboard: https://railway.app/
2. Select your project
3. Click on the **backend** service
4. Go to the **Variables** tab
5. Add these environment variables:

## Required Variables

```
DB_HOST=<railway-internal-hostname>
DB_PORT=3306
DB_USER=<db-user>
DB_PASSWORD=<set-via-railway-dashboard>
DB_NAME=finance
```

## Optional Variables (if not already set)

```
TEST_MODE=false
FLASK_ENV=production
```

## After Setting Variables

1. The backend service should automatically redeploy
2. If not, click **Deploy** → **Redeploy** on the backend service
3. Check the deployment logs to verify the connection

## Verification

After redeployment, check the logs for:

- ✅ Should see: "Connected to database: finance"
- ❌ Should NOT see: "Can't connect to MySQL server on 'mysql:3306'"

## Current Issue

The backend is trying to connect to `mysql:3306` (Docker Compose hostname) instead of `devoted-contentment.railway.internal:3306` (Railway internal hostname).

Setting these environment variables will override the Docker Compose defaults and make the backend connect to the Railway MySQL service.
