# CI/CD Pipeline Quick Reference

## Color Coding at a Glance

| Color         | Meaning               | Examples                                  |
| ------------- | --------------------- | ----------------------------------------- |
| 🟢 **Green**  | Success, Passed Tests | `PASS`, `✓`, `passed`, `SUCCESS`          |
| 🟡 **Yellow** | Warnings              | `npm warn`, `deprecated`, `warning`       |
| 🔴 **Red**    | Errors, Failures      | `error`, `ERROR`, `failed`, `✗`           |
| 🔵 **Cyan**   | Info, Summaries       | `Test Suites:`, `Tests:`, Coverage tables |
| ⚪ **White**  | Default output        | Regular build messages                    |

## Common Commands

### Run Full Pipeline

```powershell
.\scripts\CICD\pipeline.ps1
```

### Run Build Only

```powershell
.\scripts\CICD\build.ps1
```

### Skip Tests (Faster)

```powershell
.\scripts\CICD\build.ps1 -SkipTests
```

### Test Color Coding

```powershell
.\scripts\CICD\test-colors.ps1
```

### Test Progress Indicators

```powershell
.\scripts\CICD\test-progress.ps1
```

## Progress Indicators

The build process now shows progress for long-running operations:

```
⏱️  Starting: npm ci (frontend dependencies)
[real-time output streams here...]
✅ Completed: npm ci (frontend dependencies) (took 5s)

⏱️  Starting: Frontend production build (React)
Creating an optimized production build...
Compiled successfully!
✅ Completed: Frontend production build (React) (took 45s)
```

**Benefits**:

- See what's happening in real-time
- Know how long each step takes
- Identify slow operations
- Better visibility during long builds

See `PROGRESS_INDICATORS.md` for details.

## Reading Build Output

### ✅ Good Signs (Green)

```
PASS src/components/PDFValidation.test.tsx
Test Suites: 41 passed, 41 total
✓ All tests passed
```

### ⚠️ Warnings (Yellow) - Usually OK

```
npm warn deprecated package@1.0.0
warning: React Hook useEffect has a missing dependency
```

### ❌ Errors (Red) - Need Attention

```
error: 'availableAdmins' is assigned a value but never used
ERROR: Build failed
✗ Test failed
```

## Log Files

All output is saved to timestamped log files:

- **Location**: `scripts/CICD/logs/`
- **Build logs**: `build-YYYYMMDD-HHMMSS.log`
- **Pipeline logs**: `pipeline-YYYYMMDD-HHMMSS.log`

## Troubleshooting

### Build Fails with ESLint Errors

- Check red error messages in output
- Fix unused variables, missing dependencies
- Run `npm run lint` in frontend folder

### Tests Fail

- Look for red `FAIL` or `✗` markers
- Check test output for specific failures
- Run `npm test` locally to debug

### NPM Warnings (Yellow)

- Usually safe to ignore
- Deprecated packages can be updated later
- Peer dependency warnings are common

## Tips

1. **Scan for Red** - Red text means something needs fixing
2. **Yellow is OK** - Warnings don't stop deployment
3. **Green is Good** - Look for green checkmarks and PASS
4. **Cyan for Stats** - Test summaries and coverage info

## Need Help?

- See full guide: `scripts/CICD/COLOR_CODING_GUIDE.md`
- Check logs: `scripts/CICD/logs/`
- Run test: `.\scripts\CICD\test-colors.ps1`
