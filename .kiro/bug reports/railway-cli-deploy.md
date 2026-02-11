# Railway CLI Deployment Steps

## Current Status

- Railway CLI installed via npm
- Logged in via GitHub
- Need to link and deploy from backend directory

## Manual Steps to Run in Your Terminal

Open PowerShell and run these commands:

```powershell
# Navigate to backend directory
cd C:\Users\peter\aws\myAdmin\backend

# Link to your Railway project (will show interactive menu)
railway link

# Select your myAdmin project from the list
# Then select the backend service

# Deploy using Dockerfile
railway up

# Check deployment status
railway status

# View logs
railway logs
```

## What Should Happen

1. `railway link` - Shows list of projects, select "myAdmin", then select backend service
2. `railway up` - Builds and deploys using your Dockerfile
3. Should see build progress and deployment URL

## If It Works

The CLI deployment should respect your Dockerfile and deploy correctly, bypassing the Railpack issue we've been having with the web UI.

## Alternative: Force Dockerfile Build

If `railway up` still uses Railpack, try:

```powershell
# Set builder explicitly
railway variables set RAILWAY_DOCKERFILE_PATH=Dockerfile

# Deploy
railway up --dockerfile Dockerfile
```
