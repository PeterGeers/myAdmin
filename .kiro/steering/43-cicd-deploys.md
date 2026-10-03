---
inclusion: auto
---

# CI/CD — workflows, branch→env contract, promote-to-prod runbook

How myAdmin's code reaches each environment. Two different kinds of GitHub Actions
workflow live in `.github/workflows/`: **quality gates** (lint/test, no deploy) and
**deploy workflows** (push code to a live environment). This file owns the *process* —
which workflow fires when, the branch→environment contract, and the runbook for
promoting `test` → `main` (production). It does **not** restate the facts other files
own:

- **Accounts, OIDC role, Cognito pools** → `23-aws-accounts.md`.
- **Per-env stack names / `samconfig.toml` deploy rule** → `35-sam-module-architecture-sam.md`.
- **The `APP_ENV` / `VITE_APP_ENV` environment-selection model** →
  `.kiro/specs/Common/test-environment/` (Req 23 — Branch_Environment_Mapping).

## The branch → environment contract

The branch a commit lands on *is* the environment selector. There is no manual
"deploy to prod" button in the normal path — merging to `main` deploys production.

| Branch | Environment | `--config-env` (SAM) / `VITE_APP_ENV` (frontend) |
| --- | --- | --- |
| `test` | TEST | `--config-env test` — stacks `test-sam-members`, `test-pretokengen` |
| `main` | PRODUCTION | `--config-env prod` — stacks `sam-members`, `pretokengen-prod`; `VITE_APP_ENV=production` |

Feature branches (`spec/...`) run **gates only** (via PR), never a deploy. A deploy only
fires from a *push* to `test` or `main` (or an explicit `workflow_dispatch`). This CI
mapping is deliberately separate from the application source so it can evolve without
touching the spec (test-environment Req 23.5).

> **CFN stack names cannot contain underscores** — so the *CloudFormation stack* is
> hyphenated (`test-sam-members`, `test-pretokengen`) while the DynamoDB tables / env
> prefix keep the underscore (`test_sam-members`, `test_governance_projection`, `test_`).
> Don't "fix" one to match the other; they are intentionally different namespaces.

## The six workflows

### Quality gates (no deploy)

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `backend-code-quality.yml` ("Backend CI") | push to `main` + PR→`main` (paths: `backend/**`) + dispatch | ruff lint, ruff format check, vulture dead-code, py_compile syntax, unit tests (`-m "unit and not skip_ci and not slow"`). **Blocking.** |
| `frontend-ci.yml` ("Frontend CI") | PR→`main` (paths: `frontend/**`) + dispatch | ESLint (`--max-warnings=0`, blocking), vitest (`continue-on-error`), build check. |
| `full-test-suite.yml` ("Full Test Suite") | nightly cron `37 1 * * *` + dispatch (scope: all/backend/sam/frontend) | Full backend + SAM + frontend suites with coverage/HTML/JUnit artifacts. SAM & frontend lint are **report-only** (non-blocking) for now. |
| CodeQL + GitGuardian | GitHub default-setup / app scans (NOT repo YAML) | Code scanning (`py/clear-text-logging-sensitive-data` etc.) + secret scanning. Must be green on a PR before merge. |

Note: CodeQL and GitGuardian are configured through GitHub's UI/app, not a committed
workflow file — don't look for them in `.github/workflows/`.

### Deploy workflows

| Workflow | Trigger (push paths) | Target |
| --- | --- | --- |
| `deploy-sam-members.yml` ("Deploy SAM Members") | push `main`/`test`, paths `sam/members/**`, `sam/shared/**`, self | SAM Members stack in data account `506221081911` |
| `deploy-sam-pretokengen.yml` ("Deploy SAM PreTokenGen") | push `main`/`test`, paths `sam/pretokengen/**`, `sam/shared/**`, self | PreTokenGen Lambda+layer in data account `506221081911` |
| `deploy-frontend.yml` ("Deploy Frontend to GitHub Pages") | push `main`, paths `frontend/**`, `docs/**`, self | Production SPA + MkDocs → GitHub Pages |

All three deploy workflows:
- Resolve `config-env` from the branch: `refs/heads/test → test`, else `prod`
  (`workflow_dispatch` picks explicitly, **default `test`** so a mis-click never hits prod).
- Authenticate via **short-lived STS / GitHub OIDC** — assume
  `arn:aws:iam::506221081911:role/NonprofitDeployRole` (trust
  `repo:PeterGeers/myAdmin:*`). **No stored AWS secrets.** (Role/trust detail:
  `23-aws-accounts.md`.)
- Carry a `concurrency` group so two deploys never race the same stack.
- Read every per-env parameter from `samconfig.toml [<config-env>]` — the workflow only
  picks the env, so CI and a manual `sam deploy --config-env <env>` produce the SAME
  stack (`35-sam-module-architecture-sam.md`).

### Frontend TEST has no hosted target (yet)

`deploy-frontend.yml` publishes **only** the `main` (production) build to GitHub Pages —
there is a single Pages site, so a second env would collide. The TEST frontend today is
the **local dev server** (`VITE_APP_ENV=test`, `localhost:3000`). When a hosted TEST
frontend target exists, add a `test`-branch job that builds with `VITE_APP_ENV=test` and
deploys to that target. The SAM backends already deploy per-environment from `test`/`main`.

## Scope boundary: deploys touch the DATA account only

The SAM deploy workflows act **only** in the data account (`506221081911`): the Lambda,
layer, same-account IAM, and the cross-account invoke *permission*. Attaching the
Pre-Token-Generation **trigger** on the Cognito pool itself lives in the identity account
(`344561557829`) and is a **separate manual step** (see `sam/pretokengen/DEPLOY.md`). A
merge never (re)wires the pool.

## Promote `test` → `main` (production) runbook

Production is reached by merging `test` into `main`. Do it deliberately:

1. **Confirm TEST is green & verified.** All gates pass on `test`; the change was
   exercised in the live TEST environment (not just unit tests).
2. **Open ONE PR `test → main`.** One PR for the whole promotion — don't stack
   per-phase PRs. Close any stale ones.
3. **Preview the prod changesets.** For SAM changes, run `sam deploy --config-env prod`
   with `--no-execute-changeset` (or review in CFN) and confirm no unexpected
   `Replacement: True` on stateful resources.
4. **Clear the security gates.** CodeQL **and** GitGuardian must be green on the PR.
   A clear-text-secret / logging finding blocks the merge — fix the root cause, don't
   suppress.
5. **Merge with a MERGE COMMIT** (not squash) so the phase history on `test` is
   preserved on `main`.
6. **Watch the deploys.** The merge fires every deploy workflow whose paths changed —
   expect up to three distinct runs (members / pretokengen / frontend) with the same
   commit title. **Same title ≠ duplicate** — they're different workflows. Confirm each
   run concludes `success` and the stacks settle `UPDATE_COMPLETE`.

## Non-negotiables

- **Never push straight to `main`.** Production changes go through a reviewed PR.
- **No AWS secrets in CI.** OIDC + `NonprofitDeployRole` only. If you reach for an access
  key in a workflow, stop.
- **Branch decides the env** — never hard-code `prod` into a `test`-triggered path or
  vice-versa; resolve from `github.ref`.
- **`workflow_dispatch` defaults to `test`** — keep it that way; a mis-click must never
  deploy production.
- **A merge to `main` IS a production deploy.** Treat every `test → main` merge as a
  release, with the runbook above.
