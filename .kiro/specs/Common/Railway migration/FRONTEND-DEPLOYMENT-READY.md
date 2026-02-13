# Frontend Deployment - Ready to Deploy

**Date**: February 13, 2026  
**Status**: Configuration complete - waiting for Railway dashboard access  
**Backend**: ✅ Running at https://invigorating-celebration-production.up.railway.app

---

## Current Situation

- ✅ Backend deployed and running on Railway
- ✅ Database migrated and connected
- ✅ Frontend configuration prepared
- ⏳ Waiting for Railway dashboard access (passkey issue)

---

## Frontend Configuration Prepared

### Production Environment Variables

Created `frontend/.env.production` with:

```bash
# Backend API
REACT_APP_API_URL=https://invigorating-celebration-production.up.railway.app

# AWS Cognito (already configured)
REACT_APP_COGNITO_USER_POOL_ID=eu-west-1_Hdp40eWmu
REACT_APP_COGNITO_CLIENT_ID=66tp0087h9tfbstggonnu5aghp
REACT_APP_COGNITO_DOMAIN=myadmin-6x2848jl.auth.eu-west-1.amazoncognito.com
REACT_APP_AWS_REGION=eu-west-1

# OAuth Redirects (will update after deployment)
REACT_APP_REDIRECT_SIGN_IN=https://your-frontend-url.railway.app/
REACT_APP_REDIRECT_SIGN_OUT=https://your-frontend-url.railway.app/
```

---

## Deployment Steps (Once You Have Dashboard Access)

### Option 1: Deploy via Railway Dashboard (Easiest)

**On your phone** (where you're logged in):

1. **Go to Railway Dashboard**:
   - Open https://railway.app
   - Navigate to your myAdmin project

2. **Add New Service**:
   - Click **+ New**
   - Select **GitHub Repo**
   - Choose **PeterGeers/myAdmin**

3. **Configure Frontend Service**:
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Start Command**: `npx serve -s build -l $PORT`
   - **Install Command**: `npm install`

4. **Add Environment Variables**:
   - Click **Variables** tab
   - Add all variables from `frontend/.env.production`:
     ```
     REACT_APP_API_URL=https://invigorating-celebration-production.up.railway.app
     REACT_APP_COGNITO_USER_POOL_ID=eu-west-1_Hdp40eWmu
     REACT_APP_COGNITO_CLIENT_ID=66tp0087h9tfbstggonnu5aghp
     REACT_APP_COGNITO_DOMAIN=myadmin-6x2848jl.auth.eu-west-1.amazoncognito.com
     REACT_APP_AWS_REGION=eu-west-1
     ```

5. **Generate Domain**:
   - Go to **Settings** → **Networking**
   - Click **Generate Domain**
   - Note the URL (e.g., `https://myadmin-frontend.up.railway.app`)

6. **Update OAuth Redirects**:
   - Go back to **Variables**
   - Update:
     ```
     REACT_APP_REDIRECT_SIGN_IN=https://your-actual-url.railway.app/
     REACT_APP_REDIRECT_SIGN_OUT=https://your-actual-url.railway.app/
     ```
   - Redeploy

### Option 2: Deploy via Railway CLI (Alternative)

Once Railway CLI authentication works:

```bash
# Navigate to frontend
cd frontend

# Login to Railway (if needed)
railway login

# Link to project
railway link

# Set environment variables
railway variables set REACT_APP_API_URL=https://invigorating-celebration-production.up.railway.app
railway variables set REACT_APP_COGNITO_USER_POOL_ID=eu-west-1_Hdp40eWmu
railway variables set REACT_APP_COGNITO_CLIENT_ID=66tp0087h9tfbstggonnu5aghp
railway variables set REACT_APP_COGNITO_DOMAIN=myadmin-6x2848jl.auth.eu-west-1.amazoncognito.com
railway variables set REACT_APP_AWS_REGION=eu-west-1

# Deploy
railway up
```

---

## Post-Deployment Steps

### 1. Update Backend CORS

Once frontend is deployed, update backend CORS to allow the frontend domain:

**File**: `backend/src/app.py`

```python
CORS(app, origins=[
    "https://your-frontend-url.railway.app",  # Add this
    "http://localhost:3000"  # Keep for local dev
])
```

Commit and push to trigger backend redeployment.

### 2. Update AWS Cognito Callback URLs

Add the frontend URL to Cognito:

1. Go to AWS Cognito Console
2. Select User Pool: `eu-west-1_Hdp40eWmu`
3. Go to **App Integration** → **App clients**
4. Select your app client
5. Add to **Callback URLs**:
   ```
   https://your-frontend-url.railway.app/
   ```
6. Add to **Sign out URLs**:
   ```
   https://your-frontend-url.railway.app/
   ```

### 3. Test the Deployment

```bash
# Test frontend loads
curl https://your-frontend-url.railway.app

# Test API connection (from browser console)
fetch('https://invigorating-celebration-production.up.railway.app/api/health')
  .then(r => r.json())
  .then(console.log)
```

---

## Files Ready for Deployment

- ✅ `frontend/.env.production` - Production environment variables
- ✅ `frontend/package.json` - Build scripts configured
- ✅ `frontend/build/` - Can be generated with `npm run build`

---

## What's Blocking Deployment

**Railway Dashboard Access**: Passkey authentication issue

**Solutions in Progress**:

1. ✅ Support email sent to Railway
2. ⏳ Waiting for passkey removal
3. 📱 Can deploy from phone once passkey is fixed

---

## Alternative: Deploy from Phone

Since you're logged into Railway on your phone:

1. **Open Railway app/website on phone**
2. **Navigate to myAdmin project**
3. **Add new service** (GitHub repo)
4. **Configure as described above**
5. **Deploy!**

The Railway mobile interface should allow you to:

- Add new services
- Configure environment variables
- Generate domains
- View deployment logs

---

## Estimated Time

Once you have dashboard access:

- **Configuration**: 5 minutes
- **First deployment**: 3-5 minutes
- **CORS update**: 2 minutes
- **Cognito update**: 3 minutes
- **Testing**: 5 minutes

**Total**: 15-20 minutes

---

## Next Steps

1. **Wait for Railway support** to fix passkey issue
2. **Or deploy from phone** using Railway mobile interface
3. **Follow deployment steps** above
4. **Update CORS and Cognito** after deployment
5. **Test end-to-end** functionality

---

## Summary

Everything is ready for frontend deployment. The only blocker is Railway dashboard access. Once you can log in (via phone or after support fixes the passkey), you can deploy the frontend in about 15-20 minutes.

**Backend Status**: ✅ Running  
**Database Status**: ✅ Connected  
**Frontend Status**: ⏳ Ready to deploy (waiting for dashboard access)
