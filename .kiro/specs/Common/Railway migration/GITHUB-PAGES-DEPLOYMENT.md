# Frontend Deployment to GitHub Pages

**Date**: February 13, 2026  
**Status**: Ready to deploy  
**Frontend URL**: https://petergeers.github.io/myAdmin/  
**Backend URL**: https://invigorating-celebration-production.up.railway.app

---

## What Was Configured

### 1. Package.json Updates ✅

- Added `homepage`: `https://petergeers.github.io/myAdmin`
- Added `predeploy` and `deploy` scripts
- Installed `gh-pages` package

### 2. Production Environment ✅

Created `frontend/.env.production` with:

- Backend API URL (Railway)
- AWS Cognito configuration
- OAuth redirect URLs (GitHub Pages)

### 3. GitHub Actions Workflow ✅

Created `.github/workflows/deploy-frontend.yml`:

- Automatic deployment on push to main
- Builds and deploys to GitHub Pages
- Uses environment variables from workflow

---

## Deployment Options

### Option 1: Automatic Deployment (Recommended)

**Just push to GitHub** - the workflow will deploy automatically!

```bash
# Commit the changes
git add .
git commit -m "Configure frontend for GitHub Pages deployment"
git push origin main
```

The GitHub Action will:

1. Build the frontend
2. Deploy to GitHub Pages
3. Frontend will be live at: https://petergeers.github.io/myAdmin/

### Option 2: Manual Deployment

```bash
# Navigate to frontend
cd frontend

# Deploy (builds and pushes to gh-pages branch)
npm run deploy
```

---

## Enable GitHub Pages

After first deployment, enable GitHub Pages in your repository:

1. **Go to GitHub repository**: https://github.com/PeterGeers/myAdmin
2. **Settings** → **Pages**
3. **Source**: Deploy from a branch
4. **Branch**: `gh-pages` / `root`
5. **Save**

GitHub will show: "Your site is live at https://petergeers.github.io/myAdmin/"

---

## Post-Deployment Steps

### 1. Update Backend CORS ✅

Update `backend/src/app.py` to allow GitHub Pages:

```python
CORS(app, origins=[
    "https://petergeers.github.io",  # GitHub Pages
    "http://localhost:3000"  # Local development
])
```

Commit and push to trigger backend redeployment on Railway.

### 2. Update AWS Cognito Callback URLs

Add GitHub Pages URL to Cognito:

1. Go to **AWS Cognito Console**
2. Select User Pool: `eu-west-1_Hdp40eWmu`
3. **App Integration** → **App clients** → Select your client
4. Add to **Callback URLs**:
   ```
   https://petergeers.github.io/myAdmin/
   ```
5. Add to **Sign out URLs**:
   ```
   https://petergeers.github.io/myAdmin/
   ```
6. **Save changes**

### 3. Test the Deployment

```bash
# Test frontend loads
curl https://petergeers.github.io/myAdmin/

# Test in browser
# Open: https://petergeers.github.io/myAdmin/
# Check browser console for errors
# Try logging in with Cognito
```

---

## Monitoring Deployment

### GitHub Actions

1. Go to **Actions** tab in GitHub
2. Watch the "Deploy Frontend to GitHub Pages" workflow
3. Check for any errors
4. Deployment takes ~3-5 minutes

### Deployment Status

- ✅ **Success**: Green checkmark, site is live
- ❌ **Failed**: Red X, check logs for errors
- 🟡 **In Progress**: Yellow dot, building...

---

## Troubleshooting

### Build Fails

**Check GitHub Actions logs**:

1. Go to Actions tab
2. Click on failed workflow
3. Expand failed step
4. Fix errors and push again

### Site Not Loading

**Check GitHub Pages settings**:

1. Settings → Pages
2. Verify source is `gh-pages` branch
3. Wait 2-3 minutes after first deployment

### CORS Errors

**Update backend CORS**:

```python
# backend/src/app.py
CORS(app, origins=[
    "https://petergeers.github.io",
    "http://localhost:3000"
])
```

### Authentication Not Working

**Check Cognito callback URLs**:

- Must include: `https://petergeers.github.io/myAdmin/`
- Must match exactly (including trailing slash)

---

## Advantages of GitHub Pages

1. ✅ **Free hosting** - No cost
2. ✅ **Automatic deployment** - Push to deploy
3. ✅ **HTTPS by default** - Secure
4. ✅ **CDN distribution** - Fast globally
5. ✅ **No Railway dashboard needed** - Works now!
6. ✅ **Version control** - Easy rollbacks

---

## Files Modified

- ✅ `frontend/package.json` - Added homepage and deploy scripts
- ✅ `frontend/.env.production` - Production environment variables
- ✅ `.github/workflows/deploy-frontend.yml` - Automatic deployment
- ✅ `frontend/package-lock.json` - Added gh-pages dependency

---

## Next Steps

1. **Commit and push** the changes:

   ```bash
   git add .
   git commit -m "Configure frontend for GitHub Pages deployment"
   git push origin main
   ```

2. **Enable GitHub Pages** in repository settings

3. **Update backend CORS** to allow GitHub Pages origin

4. **Update Cognito** callback URLs

5. **Test the deployment** at https://petergeers.github.io/myAdmin/

---

## Estimated Time

- **Push to GitHub**: 1 minute
- **GitHub Actions build**: 3-5 minutes
- **Enable GitHub Pages**: 1 minute
- **Update CORS**: 2 minutes
- **Update Cognito**: 3 minutes
- **Testing**: 5 minutes

**Total**: 15-20 minutes

---

## Success Criteria

- ✅ Frontend accessible at https://petergeers.github.io/myAdmin/
- ✅ No CORS errors in browser console
- ✅ Can log in with Cognito
- ✅ Can access backend API
- ✅ All features working

---

## Summary

GitHub Pages provides a simple, free way to deploy the frontend without needing Railway dashboard access. The automatic deployment workflow means you just push to GitHub and the site updates automatically.

**Ready to deploy!** Just commit and push the changes.
