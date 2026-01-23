# Remove Secrets from Git History - Instructions

## Current Status

✅ **File deleted from working directory and committed**

- File: `.kiro/specs/Common/Security/Environment-Variables-Consolidation.md`
- Commit: "security: Remove file with exposed secrets"

## What's Left To Do

The file is deleted from the current version, but it still exists in git history. Anyone who clones the repo can still access old commits with the secrets.

To completely remove it, you need to rewrite git history.

## ⚠️ Important Warnings

**Before proceeding:**

- This will rewrite ALL git history
- All commit SHAs will change
- Team members will need to re-clone the repository
- You need force push permissions on GitHub
- Create a backup first!

## Option 1: Using git-filter-repo (Recommended)

### Step 1: Install git-filter-repo

```powershell
pip install git-filter-repo
```

### Step 2: Run the automated script

```powershell
.\scripts\remove-secrets-from-history.ps1
```

This script will:

1. Create a backup
2. Remove the file from all history
3. Optionally force push to GitHub

### Step 3: Verify

```powershell
# Check that file is gone from history
git log --all --full-history -- .kiro/specs/Common/Security/Environment-Variables-Consolidation.md
# Should return nothing
```

## Option 2: Using BFG Repo-Cleaner (Alternative)

### Step 1: Download BFG

Download from: https://rtyley.github.io/bfg-repo-cleaner/

### Step 2: Create a fresh clone

```powershell
cd ..
git clone --mirror https://github.com/PeterGeers/myAdmin.git myAdmin-mirror
cd myAdmin-mirror
```

### Step 3: Run BFG

```powershell
java -jar bfg.jar --delete-files Environment-Variables-Consolidation.md
```

### Step 4: Clean up and push

```powershell
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push --force
```

### Step 5: Update your local repo

```powershell
cd ../myAdmin
git fetch origin
git reset --hard origin/main
```

## Option 3: Manual Method (Most Control)

### Step 1: Use git filter-branch

```powershell
git filter-branch --force --index-filter `
  "git rm --cached --ignore-unmatch .kiro/specs/Common/Security/Environment-Variables-Consolidation.md" `
  --prune-empty --tag-name-filter cat -- --all
```

### Step 2: Clean up

```powershell
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

### Step 3: Force push

```powershell
git push origin main --force
```

## After Rewriting History

### 1. Verify the file is gone

```powershell
# Search all history for the file
git log --all --full-history -- .kiro/specs/Common/Security/Environment-Variables-Consolidation.md

# Should return nothing if successful
```

### 2. Force push to GitHub

```powershell
git push origin main --force
```

### 3. Notify team members

Send this message to your team:

```
⚠️ Git history has been rewritten to remove exposed secrets.

Please update your local repository:

1. Backup any uncommitted work
2. Run these commands:
   git fetch origin
   git reset --hard origin/main

Or simply re-clone:
   git clone https://github.com/PeterGeers/myAdmin.git
```

## Verification Checklist

After rewriting history:

- [ ] File is deleted from working directory
- [ ] File doesn't appear in `git log --all --full-history`
- [ ] Changes force pushed to GitHub
- [ ] Team members notified
- [ ] Credentials rotated (see SECURITY_INCIDENT_REMEDIATION.md)
- [ ] GitGuardian alerts resolved

## Alternative: Just Push the Deletion

If you don't want to rewrite history (simpler but less secure):

```powershell
# Just push the deletion commit
git push origin main
```

**Note**: The file will still exist in old commits, but:

- It won't be in the current version
- You can mark it as resolved in GitGuardian
- You MUST rotate all exposed credentials

## Recommended Approach

For maximum security:

1. ✅ Delete file (already done)
2. ✅ Commit deletion (already done)
3. ⏳ Rewrite git history (use Option 1 script)
4. ⏳ Force push to GitHub
5. ⏳ Rotate all credentials (see SECURITY_INCIDENT_REMEDIATION.md)

## Need Help?

If you're unsure about rewriting history:

1. **Minimum action**: Just push the deletion commit

   ```powershell
   git push origin main
   ```

2. **Then rotate credentials** (REQUIRED)
   - See: `SECURITY_INCIDENT_REMEDIATION.md`

3. **Consider history rewrite later** when you have time

## Current Git Status

```powershell
# Check current status
git status

# See the deletion commit
git log -1

# Push when ready
git push origin main
```

---

**Remember**: Even after removing from git history, you MUST rotate all exposed credentials!
