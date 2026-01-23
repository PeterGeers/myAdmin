# Environment Files Strategy

## Overview

We maintain **separate `.env` files** for each environment instead of using symbolic links because:

1. **Different configurations needed**: Docker uses `DB_HOST=mysql`, local uses `DB_HOST=localhost`
2. **Backend-specific variables**: Backend needs SNS configuration, frontend doesn't
3. **Windows compatibility**: Symbolic links require admin privileges on Windows
4. **Clarity**: Each environment has its own clear configuration

## File Structure

```
myAdmin/
├── .env.shared          # Reference file (shared values)
├── .env                 # Docker Compose (DB_HOST=mysql)
├── backend/.env         # Python/Flask (DB_HOST=localhost + SNS)
└── frontend/.env        # React (DB_HOST=localhost)
```

## Key Differences

| Variable              | Root (.env) | Backend     | Frontend    |
| --------------------- | ----------- | ----------- | ----------- |
| **DB_HOST**           | `mysql`     | `localhost` | `localhost` |
| **SNS_TOPIC_ARN**     | ❌          | ✅          | ❌          |
| **All other secrets** | ✅ Same     | ✅ Same     | ✅ Same     |

## Why Not Symbolic Links?

### Problems with Symlinks:

1. **Windows requires admin**: Creating symlinks needs elevated privileges
2. **Git issues**: Symlinks can cause problems in git repositories
3. **Different values needed**: We need different `DB_HOST` values
4. **Deployment complexity**: Railway/Docker handle files differently

### Our Solution:

- Keep separate files with clear documentation
- Use `.env.shared` as reference for common values
- Use `sync-env-files.ps1` to verify consistency

## Maintenance Workflow

### When Updating Secrets

1. **Update all three files**:

   ```powershell
   # Edit each file
   notepad .env
   notepad backend/.env
   notepad frontend/.env
   ```

2. **Verify consistency**:

   ```powershell
   .\scripts\setup\sync-env-files.ps1
   ```

3. **Update .env.shared** (optional reference):
   ```powershell
   notepad .env.shared
   ```

### Quick Update Script

For common secrets (Cognito, API keys), you can use PowerShell:

```powershell
# Example: Update OpenRouter API key in all files
$newKey = "sk-or-v1-new-key-here"

(Get-Content .env) -replace 'OPENROUTER_API_KEY=.*', "OPENROUTER_API_KEY=$newKey" | Set-Content .env
(Get-Content backend/.env) -replace 'OPENROUTER_API_KEY=.*', "OPENROUTER_API_KEY=$newKey" | Set-Content backend/.env
(Get-Content frontend/.env) -replace 'OPENROUTER_API_KEY=.*', "OPENROUTER_API_KEY=$newKey" | Set-Content frontend/.env

# Verify
.\scripts\setup\sync-env-files.ps1
```

## File Purposes

### `.env.shared` (Reference Only)

- Contains common values
- Used as reference when updating
- Not loaded by any application
- Helps maintain consistency

### `.env` (Root - Docker Compose)

- Loaded by `docker-compose.yml`
- Uses `DB_HOST=mysql` (Docker service name)
- Used when running: `docker-compose up`

### `backend/.env` (Python/Flask)

- Loaded by Python backend
- Uses `DB_HOST=localhost` (local MySQL)
- Includes SNS configuration
- Used when running: `python backend/src/app.py`

### `frontend/.env` (React)

- Loaded by React frontend
- Uses `DB_HOST=localhost` (local MySQL)
- No SNS configuration needed
- Used when running: `npm start` in frontend/

## Verification Tool

Use the sync utility to check consistency:

```powershell
.\scripts\setup\sync-env-files.ps1
```

**Output shows**:

- ✓ File existence and line counts
- ✓ DB_HOST differences (expected)
- ✓ SNS configuration (backend only)
- ✓ Secret consistency across files

## Best Practices

### DO:

✅ Keep all three `.env` files in sync for common secrets
✅ Use `sync-env-files.ps1` to verify consistency
✅ Update `.env.shared` as reference
✅ Document any environment-specific changes

### DON'T:

❌ Use symbolic links (Windows compatibility issues)
❌ Commit any `.env` files to git
❌ Forget to update all three files when changing secrets
❌ Use same `DB_HOST` for Docker and local

## Railway Deployment

When deploying to Railway, set environment variables in Railway dashboard:

```bash
# Railway uses its own environment variables
# Don't upload .env files to Railway
# Set each variable individually in Railway UI
```

Railway will provide its own database connection:

```bash
DB_HOST=<railway-provided-host>
DB_USER=<railway-provided-user>
DB_PASSWORD=<railway-provided-password>
```

## Security

All `.env` files are protected:

```gitignore
# .gitignore
.env
.env.shared
.secrets
*.env
.env.*
```

GitGuardian is configured to skip `.env` files:

```yaml
# .gitguardian.yaml
ignored_paths:
  - ".env"
  - "**/.env"
  - ".env.shared"
```

## Summary

**Why separate files?**

- Different `DB_HOST` values needed (mysql vs localhost)
- Backend needs SNS, frontend doesn't
- Windows symlink issues
- Clearer configuration per environment

**How to maintain?**

- Update all three files when changing secrets
- Use `sync-env-files.ps1` to verify
- Keep `.env.shared` as reference

**Result:**

- ✅ Clear configuration per environment
- ✅ Easy to maintain
- ✅ Windows compatible
- ✅ Git protected
- ✅ GitGuardian protected
