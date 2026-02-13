# Railway Documentation Findings

## Key Discoveries

### 1. Waitress --call Flag

From Railway's Flask guide and community help, the correct Waitress syntax for WSGI apps is:

```bash
waitress-serve --host=0.0.0.0 --port=$PORT --call src.wsgi:app
```

The `--call` flag tells Waitress that `app` is a callable object, not a module path.

### 2. Railway.toml Priority

Configuration priority (from docs):

1. Environment-specific config in code
2. Base config in code
3. Service settings (UI)

**Config in code ALWAYS overrides UI settings.**

### 3. Pre-deploy vs Start Command

- **Pre-deploy**: Runs once before deployment (good for validation, migrations)
- **Start command**: Runs to start the container (should only start the server)

We correctly separated these.

### 4. Working Directory

When using Dockerfile, the WORKDIR is already set to `/app`, so:

- No need for `cd /app`
- No need for `PYTHONPATH=/app` if Dockerfile sets it correctly

### 5. Common Flask Deployment Pattern

Railway's recommended pattern:

```toml
[build]
builder = "DOCKERFILE"

[deploy]
startCommand = "waitress-serve --host=0.0.0.0 --port=$PORT --call app:app"
```

## What We Changed

### Updated backend/railway.toml

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"
watchPatterns = ["/backend/**"]

[deploy]
startCommand = "waitress-serve --host=0.0.0.0 --port=$PORT --call src.wsgi:app"
healthcheckPath = "/api/health"
healthcheckTimeout = 100
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

### Key Changes

1. **Added `--call` flag** - This is critical for WSGI apps
2. **Removed `cd /app`** - Not needed with Dockerfile WORKDIR
3. **Removed `PYTHONPATH`** - Dockerfile should handle this
4. **Removed validation** - Already in pre-deploy
5. **Simplified command** - Just start the server

## Why This Should Work

1. **--call flag**: Tells Waitress to call `app` as a function/callable
2. **Dockerfile sets WORKDIR**: Already in `/app`
3. **Pre-deploy validates**: Validation runs before start
4. **Clean separation**: Build → Validate → Start

## Next Steps

1. Clear the "Custom Start Command" in Railway UI (let railway.toml control it)
2. Redeploy
3. Check logs for Waitress output

## References

- [Railway Flask Guide](https://docs.railway.com/guides/flask)
- [Railway Config as Code](https://docs.railway.com/reference/config-as-code)
- [Railway Community: Waitress](https://station.railway.com/questions/help-please-a6fa2a68)
