# Backend Folder Restructure Plan

## Current Problem

- 70+ files in backend root directory
- Mix of scripts, tests, migrations, and documentation
- Hard to find specific files
- Unclear what's active vs. archived

## Proposed Structure

```
backend/
├── src/                          # Main application code (keep as is)
├── tests/                        # All test files
│   ├── api/                      # API tests
│   ├── database/                 # Database tests
│   ├── patterns/                 # Pattern analysis tests
│   └── integration/              # Integration tests
├── scripts/                      # Utility scripts
│   ├── database/                 # Database migrations & fixes
│   ├── data/                     # Data analysis & validation
│   └── maintenance/              # Maintenance scripts
├── docs/                         # Documentation
│   ├── guides/                   # User guides
│   └── summaries/                # Investigation summaries
├── config/                       # Configuration files
│   ├── .env
│   ├── .env.example
│   ├── pytest.ini
│   └── Dockerfile
├── data/                         # Data files
│   ├── credentials.json
│   ├── token.json
│   └── *.json (debug/gap files)
├── sql/                          # SQL scripts
│   └── *.sql files
├── powershell/                   # PowerShell scripts
│   └── *.ps1 files
├── cache/                        # Cache (keep)
├── logs/                         # Logs (keep)
├── uploads/                      # Uploads (keep)
├── storage/                      # Storage (keep)
├── static/                       # Static files (keep)
├── templates/                    # Templates (keep)
├── .venv/                        # Virtual env (keep)
└── requirements.txt              # Keep in root
```

## File Categories

### Tests (40+ files) → `tests/`

- test\_\*.py files
- Organized by feature area

### Scripts (20+ files) → `scripts/`

- Database migrations
- Data analysis
- Validation scripts
- Optimization scripts

### Documentation (5+ files) → `docs/`

- \*.md files
- Investigation summaries
- Guides

### PowerShell (3 files) → `powershell/`

- \*.ps1 files

### SQL (1 file) → `sql/`

- \*.sql files

### Data (3 files) → `data/`

- \*.json files (credentials, tokens, debug data)

### Config (5 files) → `config/`

- .env, .env.example
- pytest.ini
- Dockerfile
- .dockerignore

## Benefits

✅ Easy to find files by category
✅ Clear separation of concerns
✅ Better for version control
✅ Easier onboarding for new developers
✅ Cleaner root directory

## Migration Steps

1. Create new folder structure
2. Move files to appropriate folders
3. Update import paths (if needed)
4. Update .gitignore
5. Test that everything still works
6. Archive old structure

## Risks

⚠️ Import paths may need updating
⚠️ Scripts may reference relative paths
⚠️ CI/CD may need path updates

## Recommendation

Start with moving tests and scripts first (low risk), then documentation.
Keep config files in root for now (common practice).
