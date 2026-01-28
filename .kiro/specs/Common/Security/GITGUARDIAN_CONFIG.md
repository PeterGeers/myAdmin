# GitGuardian Configuration Best Practices

## Overview

GitGuardian scans your code for secrets (API keys, passwords, tokens) before they get committed to Git. This document explains our configuration approach.

---

## Key Principle: GitGuardian ≠ .gitignore

**Important**: GitGuardian does **NOT** automatically respect `.gitignore` by design.

### Why?
- **Security first**: GitGuardian wants to catch secrets even in files you might have accidentally ignored
- **Different purpose**: `.gitignore` is for version control, not security
- **Catch mistakes**: If you committed a secret before adding it to `.gitignore`, GitGuardian should still find it

---

## Our Configuration Strategy

### ✅ What We Exclude

**1. Build Artifacts & Dependencies** (no secrets here)
```yaml
paths-ignore:
  - "**/node_modules/**"
  - "**/build/**"
  - "**/.venv/**"
  - "**/mysql_data/**"
```

**2. Template/Example Files** (placeholders, not real secrets)
```yaml
exclude:
  - "**/*.example"
  - "**/example.*"
  - "**/*.md"
```

### ❌ What We DON'T Exclude

**Real environment files** - These SHOULD be scanned:
- `.env` (root)
- `backend/.env`
- `frontend/.env`
- Any file with actual secrets

**Why?** If you accidentally add real secrets to these files, GitGuardian will catch them before commit!

---

## Configuration Files

### `.gitguardian.yaml` (Active Config)
- Located in repository root
- Used by pre-commit hook and manual scans
- Pattern-based exclusions (no hardcoded file paths)

### `scripts/security/install-gitguardian.ps1`
- Installation script
- Creates `.gitguardian.yaml` with same patterns
- No maintenance needed when adding new files

---

## How It Works

### Pre-Commit Hook
```bash
# Automatically runs before each commit
git commit -m "Your message"
# → GitGuardian scans staged changes
# → Blocks commit if secrets found
```

### Manual Scans
```bash
# Scan current changes
ggshield secret scan pre-commit

# Scan entire repository
ggshield secret scan repo .

# Scan specific file
ggshield secret scan path backend/.env
```

---

## Pattern Matching

### Ignored Matches (False Positives)
```yaml
ignored-matches:
  - name: "Test API Keys"
    match: "sk-test-"
  - name: "Example placeholders"
    match: "your-.*-here"
  - name: "Placeholder values"
    match: "REPLACE_ME|YOUR_.*|EXAMPLE_.*"
```

These patterns tell GitGuardian to ignore:
- Test API keys (e.g., `sk-test-1234567890`)
- Placeholder text (e.g., `your-api-key-here`)
- Example values (e.g., `REPLACE_ME`, `YOUR_SECRET`)

---

## Best Practices

### ✅ DO:
1. **Let GitGuardian scan .env files** - It's the whole point!
2. **Use pattern-based exclusions** - `**/*.example` instead of listing every file
3. **Keep placeholders obvious** - Use `YOUR_API_KEY` or `REPLACE_ME`
4. **Review GitGuardian alerts** - Don't blindly ignore them

### ❌ DON'T:
1. **Don't exclude .env files** - That defeats the purpose
2. **Don't hardcode file paths** - Use patterns instead
3. **Don't ignore all alerts** - Investigate each one
4. **Don't commit secrets** - Even if GitGuardian is disabled

---

## Maintenance

### Adding New Template Files
No action needed! Pattern `**/*.example` covers all example files.

### Adding New Directories
Only add to `paths-ignore` if it's:
- Build artifacts (e.g., `dist/`, `build/`)
- Dependencies (e.g., `node_modules/`)
- Data files (e.g., `mysql_data/`)

### Updating Ignored Patterns
Edit `.gitguardian.yaml` and add to `ignored-matches` section.

---

## Troubleshooting

### "GitGuardian found secrets in .env.example"
- **Cause**: Real secrets in example file
- **Fix**: Replace with placeholders like `YOUR_API_KEY`

### "GitGuardian blocking my commit"
- **Cause**: Real secrets detected
- **Fix**: Remove secrets, use environment variables
- **Don't**: Don't disable GitGuardian to bypass

### "Too many false positives"
- **Cause**: Legitimate values matching secret patterns
- **Fix**: Add to `ignored-matches` in `.gitguardian.yaml`

---

## Security Notes

### What GitGuardian Protects Against:
✅ Accidentally committing API keys
✅ Committing database passwords
✅ Committing AWS credentials
✅ Committing OAuth secrets
✅ Committing private keys

### What GitGuardian Doesn't Protect Against:
❌ Secrets already in Git history (use `git filter-repo` to remove)
❌ Secrets in files not tracked by Git
❌ Secrets shared via other channels (email, Slack)
❌ Weak passwords (use strong passwords!)

---

## Related Documentation

- [CREDENTIALS_FILE_STRUCTURE.md](../../Railway%20migration/CREDENTIALS_FILE_STRUCTURE.md) - Where secrets are stored
- [SECURITY_INCIDENT_REMEDIATION.md](./SECURITY_INCIDENT_REMEDIATION.md) - What to do if secrets leak
- [GitGuardian Docs](https://docs.gitguardian.com/ggshield-docs/reference/configuration) - Official documentation

---

## Summary

**Key Takeaway**: GitGuardian scans everything except build artifacts and template files. This is intentional and correct. Don't exclude real `.env` files - that's what GitGuardian is designed to protect!
