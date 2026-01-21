# Script & Test Folder Consolidation Plan

## Current Duplication Problem

### Root Level

- `scripts/` - Build, CI/CD, deployment scripts
- `pyScripts/` - Python analysis scripts
- `Ps1Scripts/` - PowerShell utility scripts

### Backend Level

- `backend/test/` - 38 test files (proper test suite)
- `backend/tests/` - 32 test files (we just created this)
- `backend/powershell/` - 4 PowerShell scripts (we just created this)
- `backend/scripts/` - Database & data scripts (we just created this)

## Recommended Structure

```
myAdmin/
├── scripts/                      # Root-level project scripts
│   ├── build/                    # Build scripts
│   ├── deployment/               # Deployment scripts
│   ├── git/                      # Git utilities
│   └── setup/                    # Setup scripts
│       ├── gitUpdate.ps1
│       ├── setup-vscode-alias.ps1
│       └── ...
│
├── backend/
│   ├── tests/                    # ALL backend tests (consolidated)
│   │   ├── unit/                 # Unit tests
│   │   ├── integration/          # Integration tests
│   │   ├── api/                  # API tests
│   │   └── conftest.py
│   │
│   ├── scripts/                  # Backend-specific scripts
│   │   ├── database/             # Database migrations
│   │   ├── data/                 # Data analysis
│   │   └── analysis/             # Analysis scripts (from pyScripts)
│   │
│   └── ...
```

## Actions Needed

### 1. Consolidate Backend Tests

- Move all files from `backend/test/` → `backend/tests/`
- Organize by type (unit, integration, api)
- Delete empty `backend/test/` folder

### 2. Move Python Analysis Scripts

- Move `pyScripts/*.py` → `backend/scripts/analysis/`
- Delete `pyScripts/` folder

### 3. Consolidate PowerShell Scripts

- Move `Ps1Scripts/*.ps1` → `scripts/setup/`
- Delete `Ps1Scripts/` folder
- Keep `backend/powershell/` for backend-specific scripts

### 4. Keep Root Scripts

- Keep `scripts/` for project-level scripts (build, deployment, CI/CD)

## Benefits

✅ Single location for backend tests
✅ Clear separation: project scripts vs backend scripts
✅ No duplicate folders
✅ Easier to find files
✅ Better organization

## Risk Assessment

⚠️ **Medium Risk** - Test imports may need updating

- `backend/test/` → `backend/tests/` requires import path changes
- Need to update pytest configuration
- Need to update CI/CD if it references old paths

## Recommendation

**Proceed with consolidation?**

- Consolidate backend tests first (highest value)
- Move analysis scripts second
- Move PowerShell scripts last (lowest risk)
