# GitGuardian Authentication Check Fix

## Issue

Both `pipeline.ps1` and `git-upload.ps1` were checking if GitGuardian CLI (`ggshield`) was installed, but not verifying if it was authenticated. This caused:

- False warnings about "API key not configured" even when GitGuardian was working
- Potential silent failures if scans ran without authentication

## Root Cause

GitGuardian CLI stores authentication in `~/.gitguardian/config` file, not in environment variables. The scripts were checking for `$env:GITGUARDIAN_API_KEY` which doesn't exist in normal GitGuardian CLI usage.

## Solution

Added proper authentication check using `ggshield config list` to verify token exists before running scans.

### Implementation Pattern

```powershell
# Check if ggshield is installed
try {
    ggshield --version | Out-Null
    $ggInstalled = $true
}
catch {
    $ggInstalled = $false
}

if ($ggInstalled) {
    # Check if ggshield is authenticated
    try {
        $configCheck = ggshield config list 2>&1 | Select-String "token:"
        $isAuthenticated = $null -ne $configCheck
    }
    catch {
        $isAuthenticated = $false
    }

    if ($isAuthenticated) {
        # Run scan
        ggshield secret scan pre-commit
        # ... handle results
    }
    else {
        Write-Host "⚠️  GitGuardian not authenticated" -ForegroundColor Yellow
        Write-Host "   Run: ggshield auth login" -ForegroundColor Gray
    }
}
```

## Files Fixed

1. ✅ `scripts/CICD/pipeline.ps1` - Fixed in previous session
2. ✅ `scripts/git/git-upload.ps1` - Fixed in this session

## Testing

To verify the fix works:

1. **With authentication** (normal case):

   ```powershell
   # Should show: "✅ No secrets detected - safe to commit"
   .\scripts\git\git-upload.ps1 -Message "Test commit"
   ```

2. **Without authentication** (test case):

   ```powershell
   # Temporarily remove auth
   ggshield auth logout

   # Should show: "⚠️ GitGuardian not authenticated"
   .\scripts\git\git-upload.ps1 -Message "Test commit"

   # Restore auth
   ggshield auth login
   ```

## Impact

- ✅ No more false warnings about missing API key
- ✅ Clear messaging when authentication is needed
- ✅ Scans only run when properly authenticated
- ✅ Consistent behavior across pipeline.ps1 and git-upload.ps1

## Related Documentation

- GitGuardian CLI docs: https://docs.gitguardian.com/ggshield-docs/getting-started
- Authentication: `ggshield auth login`
- Configuration check: `ggshield config list`
