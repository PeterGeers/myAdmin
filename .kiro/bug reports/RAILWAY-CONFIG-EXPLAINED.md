# Railway Configuration Files Explained

## Your Current Setup

You have Railway configured with:

- **Root Directory**: `backend`
- **Builder**: Dockerfile

This means Railway looks for files inside the `backend/` folder.

---

## Which railway.json File to Use?

Since your Root Directory is `backend`, Railway uses:

**`/backend/railway.json`** ✅ (This is the one Railway reads)

The root `/railway.json` is ignored because Railway is scoped to the `backend/` directory.

---

## What Should Be in Each File?

### `/backend/railway.json` (ACTIVE - Railway uses this)

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile",
    "watchPatterns": ["**"]
  },
  "deploy": {
    "healthcheckPath": "/api/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

**Key points:**

- ✅ NO `startCommand` field - lets Dockerfile CMD be used
- ✅ `dockerfilePath: "Dockerfile"` - relative to backend/ directory
- ✅ `watchPatterns: ["**"]` - watch all files in backend/

### `/railway.json` (IGNORED - but should match for consistency)

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile",
    "watchPatterns": ["**"]
  },
  "deploy": {
    "healthcheckPath": "/api/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

**Note**: This file is not used by Railway (because Root Directory = backend), but I've updated it to match the backend one for consistency.

---

## Configuration Priority

Railway uses this order (highest to lowest):

1. **Railway UI Settings** (Settings → Deploy)
2. **railway.json** (in the Root Directory)
3. **Dockerfile CMD**

So the priority is:

1. UI "Custom Start Command" field ← **MUST BE EMPTY**
2. `/backend/railway.json` ← **No startCommand field** ✅
3. `/backend/Dockerfile` CMD ← **Has the correct command** ✅

---

## What NOT to Include

**DO NOT add `startCommand` to railway.json**

❌ Bad:

```json
{
  "deploy": {
    "startCommand": "waitress-serve ...",  // Don't do this!
    ...
  }
}
```

✅ Good:

```json
{
  "deploy": {
    // No startCommand field at all
    "healthcheckPath": "/api/health",
    ...
  }
}
```

**Why?** Because:

- The Dockerfile CMD already has the correct command
- Adding `startCommand` here would override the Dockerfile
- The Dockerfile CMD includes environment validation and PYTHONPATH setup

---

## Summary

**Answer to "What should be in the Config-as-code Railway Config File?"**

Use **`/backend/railway.json`** with:

- Build settings (builder, dockerfilePath, watchPatterns)
- Deploy settings (healthcheck, restart policy)
- **NO startCommand field** (let Dockerfile handle it)

**And make sure:**

- Railway UI "Custom Start Command" field is EMPTY
- This lets your Dockerfile CMD run with proper setup

---

## Current Status

✅ `/backend/railway.json` - Correct (no startCommand)
✅ `/railway.json` - Fixed to match (though not used by Railway)
❌ Railway UI "Custom Start Command" - **NEEDS TO BE CLEARED**

Once you clear the UI field, everything will work correctly!
