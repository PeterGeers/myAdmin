# Backend Code Quality

## Automated Checks

### Dead Code Detection (vulture)

Vulture scans for unused Python code. It runs in CI on every push/PR to `backend/`.

**Run locally:**

```bash
cd backend
pip install vulture
vulture src/ vulture_whitelist.py --min-confidence 80 --exclude validate_pattern/
```

**Whitelist:** `backend/vulture_whitelist.py` suppresses false positives for Flask route handlers (registered via decorators) and gunicorn config variables.

**Confidence levels:**

- 100% — definitely dead code, remove immediately
- 80%+ — high confidence, review and remove unless whitelisted
- 60% — often false positives (Flask routes, gunicorn vars)

### Syntax Check

All `.py` files are compiled to verify no syntax errors:

```bash
cd backend/src
find . -name "*.py" -not -path "./__pycache__/*" | xargs python -m py_compile
```

## Scheduled Scans

Run a full code quality scan quarterly (or after major refactoring) using the spec process:

1. Run vulture with `--min-confidence 60` to catch lower-confidence dead code
2. Check file lengths: `find backend/src -name "*.py" | xargs wc -l | sort -rn | head -20`
3. Check for missing type hints: review function signatures in top files
4. Review `manualsSysAdm/` docs for stale references

## File Length Guidelines

| Target    | Maximum    | Action                              |
| --------- | ---------- | ----------------------------------- |
| 500 lines | 1000 lines | Refactor files exceeding 1000 lines |

Exceptions: test files, generated files, configuration files.

## CI Workflow

See `.github/workflows/backend-code-quality.yml` — triggers on backend changes to `main` or PRs.
