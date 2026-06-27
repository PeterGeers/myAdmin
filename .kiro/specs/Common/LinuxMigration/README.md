# Linux Migration — Issues Analysis

Analysis of potential issues across configurations, PowerShell scripts, and CI/CD.

---

## ~~1. Security — Plaintext Credentials in Git~~ (False Positive)

**File:** `railway/backend-env-variables.md`

**Status:** ✅ False positive — not a real production credential. No action needed.

---

## 2. CI/CD Pipeline — Exists but Incomplete

Two GitHub Actions workflows exist (`.github/workflows/`):

### `backend-code-quality.yml`

- **Triggers:** push/PR to `main` when `backend/**` changes, plus manual dispatch
- **Jobs:**
  - `dead-code-check` — runs `vulture` with 80% confidence threshold
  - `syntax-check` — `py_compile` on all Python files
- **What's missing:**
  - No `pytest` execution — syntax and dead code only, no functional tests
  - No `ruff` or linting step (the commit-guard hook uses ruff locally but CI doesn't)
  - No `requirements.txt` install — only installs vulture (so import-level issues not caught)

### `deploy-frontend.yml`

- **Triggers:** push to `main` when `frontend/**` changes, plus manual dispatch
- **Jobs:**
  - Builds with `npm run build:ci` (Vite build, no TypeScript check)
  - Deploys to GitHub Pages at `petergeers.github.io/myAdmin/`
  - Hardcodes Cognito config + Railway API URL as build-time env vars
- **What's missing:**
  - No `vitest run` — no tests before deploy
  - No `eslint` step — lint issues don't block deployment
  - `CI: false` set explicitly (warnings don't fail the build)

### Deployment workflow

- **Local dev/test:** Docker (backend + MySQL) + `npm start` (frontend on localhost:3000, Vite dev server)
- **Build:** rarely done locally — the GitHub Actions workflow handles `build:ci` for production
- **Deploy:** push directly to `main` when satisfied → GitHub Actions builds + deploys frontend to Pages, Railway auto-deploys backend + MySQL
- **Feature branches:** rarely used

### Railway (backend + MySQL only)

- Railway auto-deploys on push to `main` via `backend/railway.toml` (Dockerfile builder)
- No pre-deploy test gate — Railway builds immediately on push
- `frontend/railway.toml` exists in the repo but is unused/leftover

### Summary of gaps

- [ ] Add `pytest` job to backend workflow (needs `requirements.txt` install + MySQL service container or mocked DB)
- [ ] Add `vitest run` step to frontend workflow before build
- [ ] Add `eslint` step to frontend workflow
- [ ] Consider: add `pip-audit` / `npm audit` for vulnerability scanning
- [ ] Since pushes go directly to `main`, the workflows are the only automated safety net — tests here matter more than in a PR-based flow

---

## 3. PowerShell Scripts — Candidates for Removal

The `.ps1` scripts are rarely used — most operations are now done via Kiro using CLIs directly. These scripts add maintenance burden without providing value.

### Scripts inventory

| Script                                            | Purpose                             | Replacement                                       |
| ------------------------------------------------- | ----------------------------------- | ------------------------------------------------- |
| `scripts/setup/setup.ps1`                         | Install backend/frontend deps       | `pip install -r requirements.txt` + `npm install` |
| `scripts/setup/sync-env-files.ps1`                | Check .env consistency              | Manual check or Kiro-assisted                     |
| `scripts/setup/gitUpdate.ps1`                     | Git operations                      | `git` CLI directly                                |
| `scripts/setup/setup-vscode-alias.ps1`            | VS Code alias                       | Not needed with Kiro                              |
| `scripts/setup/open-workspace.ps1`                | Open workspace                      | Not needed                                        |
| `scripts/setup/vscode-fast.ps1`                   | Fast VS Code launch                 | Not needed with Kiro                              |
| `scripts/verify-setup.ps1`                        | Validate env + Docker               | Convert to bash or keep as reference              |
| `infrastructure/setup-cognito.ps1`                | Deploy Cognito via Terraform        | `terraform` CLI directly                          |
| `infrastructure/setup-notifications.ps1`          | Deploy SNS via Terraform            | `terraform` CLI directly                          |
| `infrastructure/setup-notifications-simple.ps1`   | Simpler SNS setup                   | `terraform` CLI directly                          |
| `infrastructure/setup-sns-only.ps1`               | SNS only                            | `terraform` CLI directly                          |
| `infrastructure/setup-aws-cli-only.ps1`           | Install AWS CLI                     | One-time, already done                            |
| `infrastructure/install-terraform.ps1`            | Install Terraform                   | One-time, already done                            |
| `infrastructure/create-cognito-user.ps1`          | Create Cognito user                 | `aws cognito-idp` CLI                             |
| `infrastructure/assign-user-groups.ps1`           | Assign Cognito groups               | `aws cognito-idp` CLI                             |
| `infrastructure/assign-user-tenants.ps1`          | Assign tenants                      | `aws cognito-idp` CLI                             |
| `infrastructure/update-cognito-callbacks.ps1`     | Update callback URLs                | `terraform apply`                                 |
| `infrastructure/update-aws-region.ps1`            | Update region config                | Direct env file edit                              |
| `infrastructure/create-module-groups.ps1`         | Terraform modules                   | `terraform` CLI                                   |
| `infrastructure/migrate-to-module-groups.ps1`     | Terraform migration                 | `terraform` CLI                                   |
| `update-cognito-callbacks.ps1` (root)             | Duplicate of infrastructure version | Remove                                            |
| `scripts/security/Invoke-GitGuardianScan.ps1`     | Run ggshield                        | `ggshield` CLI directly                           |
| `scripts/security/install-gitguardian.ps1`        | Install ggshield                    | One-time, already done                            |
| `scripts/security/copy-gitguardian-from-hdcn.ps1` | Copy config                         | One-time                                          |

### Fix

- [x] Remove unused/one-time scripts that just wrap CLI commands
- [x] Keep `verify-setup.ps1` logic — convert to bash or a Kiro-runnable checklist
- [x] Keep `sync-env-files.ps1` logic — convert to bash or document as manual checklist
- [x] Fix `commit-guard.kiro.hook`: change `.venv/Scripts/python` → `python` (or detect platform)
- [x] Fix `test-after-spec-task.kiro.hook`: remove `react-scripts test` → `npx vitest run`

---

## 4. Docker MySQL Version Mismatch

| Environment                             | MySQL Version |
| --------------------------------------- | ------------- |
| `docker-compose.yml` (local)            | **mysql:9.4** |
| `railway/mysql/Dockerfile` (production) | **mysql:8.0** |

Railway is already running 9.4. The Dockerfile in the repo is outdated.

**Fix:**

- [x] Update `railway/mysql/Dockerfile` to `FROM mysql:9.4`
- [x] Remove `--default-authentication-plugin=mysql_native_password` CMD (deprecated in 9.x, use `mysql_native_password=ON` in config instead if still needed)
- [x] ~~Test Python connector compatibility with 9.4 auth defaults~~ — already working in production for months

---

## ~~5. Frontend Build Path Conflict~~ (Not an Issue)

In `vite.config.ts`:

```ts
base: command === 'build' ? '/myAdmin' : '/',
```

This is correct. The frontend deploys to GitHub Pages at `petergeers.github.io/myAdmin/` where the `/myAdmin` base is required. Railway is not used for the frontend (the `frontend/railway.toml` is a leftover file).

**Cleanup:**

- [x] ~~Consider removing `frontend/railway.toml` if Railway is backend-only~~ — removed

---

## 6. Backend Start Command — Dead Code from Docker→Railway Migration

**Background:** When first deploying to Railway, imports broke because Railway's working directory differed from Docker's. `start_railway.py` was written as a bypass — it manually fixes `sys.path` and `os.chdir()` so Flask could find its modules. `validate_env.py` was added as a pre-flight check.

**Current state:**

| Context                  | Start Command                                             | Status       |
| ------------------------ | --------------------------------------------------------- | ------------ |
| `backend/railway.toml`   | `waitress-serve --host=0.0.0.0 --port=$PORT src.wsgi:app` | ✅ Active    |
| `backend/Dockerfile CMD` | `python validate_env.py && python start_railway.py`       | ❌ Dead code |
| `backend/src/wsgi.py`    | Clean WSGI entry point used by waitress                   | ✅ Active    |

Railway's `startCommand` in `railway.toml` **overrides** the Dockerfile CMD entirely. So the CMD branch (`start_railway.py` + `validate_env.py`) never executes in production. It's leftover debugging code.

**Files involved:**

- `backend/start_railway.py` — Debug script with path hacks, runs Flask dev server (not production-grade)
- `backend/validate_env.py` — Env validation, skips itself when `DOCKER_ENV=true` (Docker), never reached by Railway
- `backend/src/wsgi.py` — The real entry point, clean 4-line module

**Fix:**

- [x] Delete `backend/start_railway.py` (dead code, Railway uses wsgi.py via railway.toml)
- [x] Simplify Dockerfile CMD to just `python src/app.py` (local Docker only, no Railway branching)
- [x] Keep `validate_env.py` as optional local debugging tool (removed from startup chain)
- [x] The `PYTHONPATH=/app/src` in Dockerfile already handles the import issue that `start_railway.py` was working around

---

## 7. Dependency Issues

**Backend:**

- [x] `cryptography==41.0.7` — outdated (current 44.x), has known CVEs → updated to 44.0.0
- [x] `requests==2.31.0` — has CVEs fixed in 2.32+ → updated to 2.32.3
- [x] ~~Both `PyPDF2==3.0.1` AND `pypdf==6.1.3` — duplicates (PyPDF2 is deprecated)~~ — removed PyPDF2

**Frontend:**

- [x] ~~`@types/node: "^16.18.126"` — very old for Vite 8 / Node 20+~~ — updated to `^22.0.0`
- [ ] No `engines` field in package.json to enforce Node version

---

## 8. Terraform State — Local Only (Low Risk for Solo Dev)

`infrastructure/main.tf` stores Terraform state locally (`terraform.tfstate` file on your machine). This file tracks what AWS resources Terraform created (Cognito, SNS, SES, S3). It's `.gitignore`d so it only exists on the machine that last ran `terraform apply`.

**Status:** ✅ State file copied from Windows (`C:\Users\peter\aws\myAdmin\infrastructure\`) to Linux (`/home/peter/projects/myAdmin/infrastructure/`). Terraform can now manage existing resources from WSL.

**What this means:** If that local state file is lost (new machine, reinstall), Terraform won't know the resources exist and could try to recreate them. For a team this is a real issue. For a solo developer with stable infrastructure already deployed, it's low risk.

**Mitigation already in place:** The infrastructure rarely changes — Cognito/SNS/SES are set up once and left alone.

**If you ever need it:**

- [x] ~~Copy state file from Windows to Linux~~ (done)
- [ ] If an external backup is ever needed, copy `terraform.tfstate` to Google Drive or OneDrive
- [ ] Remote backend (S3 + DynamoDB) is overkill for a solo project — skip unless going multi-dev

---

## 9. Environment Variable Management

Three separate `.env` files (root, backend, frontend) must stay in sync manually. `.env.example` files exist for all of them (`/.env.example`, `backend/.env.example`, `frontend/.env.example`, `railway/mysql/.env.example`).

**History:** This caused issues months ago when moving from local Docker to Railway backend — env vars that worked in Docker weren't set correctly in Railway, leading to startup failures. The `validate_env.py` script and various bypasses were created in response.

**Current status: needs retesting** — unclear if the sync issues still exist or were resolved during the Railway migration fixes.

**Known issues:**

- `verify-setup.ps1` only validates `backend/.env`, not frontend
- `sync-env-files.ps1` requires manual execution (no automation)
- The deploy-frontend workflow hardcodes Cognito env vars instead of using GitHub Secrets

**Fix:**

- [ ] **Test:** Compare Railway env vars vs local Docker `.env` — are they still in sync?
- [ ] **Test:** Start fresh local Docker environment with only `.env.example` values — does it boot?
- [ ] Extend verify script to check frontend/.env
- [ ] Move hardcoded env vars in `deploy-frontend.yml` to GitHub repository secrets
- [ ] Document which vars need syncing vs which are environment-specific

---

## 10. Kiro Hook Issues

**`commit-guard.kiro.hook`** and **`test-after-spec-task.kiro.hook`** both reference `react-scripts test` — but the frontend uses **Vitest** (`"test": "vitest"` in package.json).

**Fix:**

- [x] Change `npx react-scripts test --watchAll=false --ci` → `npx vitest run`
- [x] Fix `.venv/Scripts/python` → platform-appropriate path (`python`)

---

## Priority Matrix

| Priority        | Issue                                                 | Effort             | Status  |
| --------------- | ----------------------------------------------------- | ------------------ | ------- |
| ~~🔴 Critical~~ | ~~Rotate exposed password + scrub from history~~      | ~~False positive~~ | ~~N/A~~ |
| 🟠 High         | ~~MySQL Dockerfile outdated (8.0 → align to 9.4)~~    | 15min              | ✅ Done |
| 🟠 High         | ~~CI/CD gaps: add pytest + vitest to workflows~~      | 2-4h               | ✅ Done |
| 🟠 High         | ~~Fix hooks (react-scripts → vitest, Windows paths)~~ | 15min              | ✅ Done |
| 🟡 Medium       | ~~PowerShell scripts → cross-platform~~               | 2-4h               | ✅ Done |
| 🟡 Medium       | ~~Update dependencies with CVEs~~                     | 1h                 | ✅ Done |
| 🟡 Medium       | ~~Move workflow env vars to GitHub Secrets~~          | 30min              | ✅ Done |
| 🟡 Medium       | ~~Backend start command: remove dead Railway bypass~~ | 15min              | ✅ Done |
| 🟢 Low          | ~~Terraform state: back up tfstate file~~             | 5min               | ✅ Done |
| 🟢 Low          | ~~Remove unused `frontend/railway.toml`~~             | 5min               | ✅ Done |
| 🟢 Low          | ~~Remove duplicate PDF library (PyPDF2)~~             | 15min              | ✅ Done |
| 🟢 Low          | ~~Update @types/node~~                                | 5min               | ✅ Done |
