# Security — GitGuardian Secret Scanning

GitGuardian (`ggshield`) is used to prevent accidental commits of API keys, passwords, and other secrets.

## Setup

```bash
pip install ggshield
ggshield auth login
```

Free tier: 200 scans/month, pre-commit hooks, 350+ secret types detected.

## Usage

```bash
# Scan staged changes (pre-commit hook does this automatically)
ggshield secret scan pre-commit

# Scan entire repo
ggshield secret scan repo .

# Scan specific file
ggshield secret scan path backend/.env
```

## Configuration

See `.gitguardian.yaml` in the project root for exclusions and ignored patterns.

## Integration

- **Kiro hook** (`commit-guard`): runs `ruff` + `pytest` + `eslint` + `vitest` before push
- **Pre-commit hook**: `ggshield install --mode local` installs the git pre-commit hook
- **CI/CD** (future): add `GitGuardian/ggshield-action@v1` to GitHub Actions

## If secrets are accidentally committed

1. Rotate the exposed credential immediately
2. Use `git filter-repo` to scrub from history (see `scripts/REMOVE_FROM_HISTORY_INSTRUCTIONS.md`)
3. Force-push the cleaned history
