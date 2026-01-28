# CI/CD Pipeline Color Coding Guide

## Overview

The build pipeline now uses intelligent color coding to make output easier to read and understand at a glance.

## Color Scheme

### 🟢 Green - Success

- Test passes: `PASS`, `passed`, `✓`, `✔`
- Success messages: `success`, `SUCCESS`
- Coverage reports: `All files`

**Examples:**

```
PASS src/components/PDFValidation.test.tsx
✓ All tests passed
SUCCESS: Build completed
```

### 🟡 Yellow/Orange - Warnings

- NPM warnings: `npm warn`, `npm WARN`
- Deprecated packages: `deprecated`
- ESLint warnings: `warning`, `WARN`

**Examples:**

```
npm warn deprecated package@1.0.0: This package is deprecated
warning: React Hook useEffect has a missing dependency
```

### 🔴 Red - Errors

- Build errors: `error`, `ERROR`
- Test failures: `failed`, `FAILED`, `✗`, `✕`, `×`

**Examples:**

```
error: 'availableAdmins' is assigned a value but never used
ERROR: Build failed
✗ Test failed
```

### 🔵 Cyan - Information

- Test summaries: `Test Suites:`, `Tests:`, `Snapshots:`, `Time:`
- Coverage table headers: `File`, `% Stmts`, `% Branch`, etc.

**Examples:**

```
Test Suites: 41 passed, 41 total
Tests:       439 passed, 439 total
File                                | % Stmts | % Branch | % Funcs | % Lines |
```

### ⚪ White - Default

- Regular output that doesn't match any specific pattern

## Implementation

The color coding is implemented in the `Write-ColoredOutput` function in `build.ps1`:

```powershell
function Write-ColoredOutput {
    param(
        [Parameter(ValueFromPipeline = $true)]
        [string]$Line
    )

    process {
        if ($Line) {
            # Add to log file
            Add-Content -Path $BuildLog -Value $Line

            # Determine color based on content
            $color = "White"

            # NPM warnings (orange/yellow)
            if ($Line -match "npm warn|npm WARN|deprecated|warning|WARN") {
                $color = "Yellow"
            }
            # Errors (red)
            elseif ($Line -match "error|ERROR|failed|FAILED|✗|✕|×") {
                $color = "Red"
            }
            # Success indicators (green)
            elseif ($Line -match "PASS|passed|✓|✔|success|SUCCESS|All files") {
                $color = "Green"
            }
            # Test suite info (cyan)
            elseif ($Line -match "Test Suites:|Tests:|Snapshots:|Time:") {
                $color = "Cyan"
            }
            # Coverage table headers (cyan)
            elseif ($Line -match "^File\s+\||^-+\||% Stmts|% Branch|% Funcs|% Lines") {
                $color = "Cyan"
            }

            Write-Host $Line -ForegroundColor $color
        }
    }
}
```

## Testing

Run the test script to see the color coding in action:

```powershell
.\scripts\CICD\test-colors.ps1
```

## Benefits

1. **Quick Visual Scanning** - Instantly identify issues without reading every line
2. **Reduced Cognitive Load** - Colors help categorize information automatically
3. **Better Error Detection** - Red errors stand out immediately
4. **Professional Appearance** - Modern CI/CD pipelines use color coding
5. **Improved Debugging** - Easier to spot patterns in build output

## Log Files

All output is still saved to log files without color codes for:

- Archival purposes
- Text processing/parsing
- CI/CD system integration

Log files are stored in: `scripts/CICD/logs/`
