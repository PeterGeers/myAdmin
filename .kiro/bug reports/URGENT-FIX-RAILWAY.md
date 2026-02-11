# 🚨 URGENT: Fix Railway Deployment

## The Problem

Railway is hitting 500 logs/sec rate limit because Waitress is failing and printing help text in a crash loop.

**Root Cause**: Railway UI's "Custom Start Command" is overriding the Dockerfile CMD.

---

## The Fix (2 minutes)

### Step 1: Clear the Custom Start Command

1. Go to Railway Dashboard: https://railway.app
2. Select your **backend** service
3. Click **Settings** tab
4. Scroll to **Deploy** section
5. Find **"Custom Start Command"** field
6. **DELETE everything in that field** (make it completely empty)
7. Click **Save** or the field will auto-save

### Step 2: Verify the Field is Empty

After clearing the field, you should see:

- The "Custom Start Command" input box is completely empty
- No text in that field at all

That's it! Railway will now use the command from your Dockerfile instead.

**What this means**:

- When the "Custom Start Command" field has text → Railway uses that text
- When the "Custom Start Command" field is empty → Railway uses your Dockerfile's CMD

You can optionally verify by looking at the "Configuration" tab in your deployment - the `startCommand` line should disappear from the JSON.

### Step 3: Redeploy

Railway should automatically redeploy when you save the settings.

If not, manually trigger a redeploy:

- Click **Deployments** tab
- Click **Deploy** button

---

## Why This Works

When you clear the Custom Start Command:

- Railway will use the Dockerfile CMD instead
- The Dockerfile CMD includes proper setup:
  ```dockerfile
  CMD ["sh", "-c", "python validate_env.py && PYTHONPATH=/app python -m waitress --host=0.0.0.0 --port=${PORT:-5000} --call src.wsgi:app"]
  ```
- This sets PYTHONPATH so Waitress can find `src.wsgi:app`
- Environment validation runs first to catch config issues

---

## Expected Result

After the fix, logs should show:

```
🔍 Validating environment variables...
============================================================
✅ COGNITO_USER_POOL_ID: eu-west-1_Hdp40eWmu
✅ COGNITO_CLIENT_ID: 66tp0087h9tfbstggonnu5aghp
... (all variables)
============================================================
✅ VALIDATION PASSED: All 12 required variables are set
============================================================
INFO:waitress:Serving on http://0.0.0.0:5000
```

**No more**:

- ❌ 500 logs/sec rate limit
- ❌ Waitress help text spam
- ❌ "Messages dropped" warnings
- ❌ Module import errors

---

## If It Still Fails

If you still see issues after clearing the Custom Start Command:

1. **Verify the field is truly empty** - Go back to Settings → Deploy and check the "Custom Start Command" field has no text
2. **Check Root Directory setting** - Should be set to `backend`
3. **Check Builder setting** - Should be set to `Dockerfile`
4. **Force a new deployment** - Sometimes Railway needs a fresh deploy to pick up the change

If all settings are correct but it still fails, the issue is likely in the application code itself (not the Railway configuration).

---

## Configuration Precedence

Railway uses this order (highest to lowest priority):

1. **UI Settings** ← This was the problem
2. railway.json/railway.toml
3. Dockerfile CMD

Even though railway.json and Dockerfile were correct, the UI setting was overriding them.

---

## Files Involved

- `backend/Dockerfile` - Contains the correct CMD ✅
- `backend/railway.json` - Has NO startCommand (correct) ✅
- Railway UI Settings - Had OLD startCommand (now fixed) ✅

---

## Timeline

- **Before**: Waitress crashes → prints help text → crashes again → 500 logs/sec
- **After**: Waitress starts successfully → normal operation → minimal logging
