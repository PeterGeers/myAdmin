Yes
inclusion: auto
---

# CI/CD — workflows, branch→env contract, promote-to-prod runbook

How myAdmin's code reaches each environment. `.github/workflows/` holds two kinds of
workflow: **quality gates** (lint/test) and **deploy** (push to a live env). This file
owns the *process*; it does not restate facts other files own:

- Accounts, OIDC role, Cognito pools → `23-aws-accounts.md`.
- Per-env stack names / `samconfig.toml` deploy rule → `35-sam-module-architecture-sam.md`.
- `APP_ENV` / `VITE_APP_ENV` selection model → `.kiro/specs/Common/test-environment/` (Req 23).

## Branch → environment contract

The branch a commit lands on *is* the env selector — merging to `main` deploys production.

| Branch | Env | `--config-env` (SAM) / `VITE_APP_ENV` |
| --- | --- | --- |
| `test` | TEST | `test` — stacks `test-sam-members`, `test-pretokengen` |
| `main` | PRODUCTION | `prod` — stacks `sam-members`, `pretokengen-prod`; `VITE_APP_ENV=production` |

Feature branches (`spec/...`) never deploy — a deploy fires only on *push* to `test`/`main`
(or explicit `workflow_dispatch`). A feature-branch PR runs only the currently-enabled
gates (today: CodeQL + GitGuardian). CI mapping is separate from app source (Req 23.5).

> **CFN stack names can't contain underscores:** the CloudFormation stack is hyphenated
> (`test-sam-members`) while DynamoDB tables / env prefix keep the underscore
> (`test_sam-members`, `test_`). Intentionally different namespaces — don't "fix" either.

## Quality gates (no deploy)

> **CURRENT STATE (`gh workflow list --all`): Backend CI and Frontend CI are
> `disabled_manually`** — their YAML is still committed but GitHub does not run them on
> push or PR. So today the only per-PR checks are **CodeQL + GitGuardian**, and the only
> automated lint/test gate is the nightly **`full-test-suite.yml`**. The per-PR gates below
> are the *intended* design for when re-enabled (Frontend CI needs its `--max-warnings=0`
> ESLint backlog cleared/scoped first, or it goes red immediately).

| Workflow | State | What it does (trigger when enabled) |
| --- | --- | --- |
| `backend-code-quality.yml` ("Backend CI") | **DISABLED** | ruff lint+format, vulture, py_compile, unit tests. PR→`main` paths `backend/**`. |
| `frontend-ci.yml` ("Frontend CI") | **DISABLED** | ESLint `--max-warnings=0`, vitest (`continue-on-error`), build. PR→`main` paths `frontend/**`. |
| `full-test-suite.yml` ("Full Test Suite") | **ACTIVE — sole lint/test gate today** | Full backend+SAM+frontend suites + artifacts (SAM/frontend lint report-only). Nightly cron `37 1 * * *` + dispatch (scope: all/backend/sam/frontend). |
| CodeQL + GitGuardian | ACTIVE (only per-PR gates today) | Code scanning + secret scanning. Must be green on a PR before merge. |

**CodeQL** is an ADVANCED-SETUP workflow committed at `.github/workflows/codeql.yml`
(`name: "CodeQL Advanced"`). It triggers on push + pull_request to `main` AND `test`, on a
weekly schedule, and on **`workflow_dispatch`** — so it gates PRs into `test` and `main`, and can
be run manually. It REPLACED GitHub's old default-setup CodeQL (the non-dispatchable
`event: dynamic` scan); default setup must stay OFF in Settings → Security → Code scanning or
the two conflict. Languages: python, javascript-typescript, actions.

**GitGuardian** (secret scanning) is separate and enforced LOCALLY by the git hooks (pre-commit
`ggshield` + pre-push `scripts/scan-secrets-local.sh`); the `GitGuardian Security Checks` entry
on a PR is the GitGuardian App mirroring that.

Trigger CodeQL manually:

```bash
gh workflow run "CodeQL Advanced" --ref <branch>     # e.g. --ref test
gh run list --workflow "CodeQL Advanced" --limit 5   # watch it
```

Check a commit's PR gate results (CodeQL + GitGuardian):

```bash
# <sha> = the commit to inspect (for a PR, its head commit):
SHA=$(gh pr view <PR> --json headRefOid --jq .headRefOid)   # or: git rev-parse origin/test
gh api repos/PeterGeers/myAdmin/commits/$SHA/check-runs
```

> **Bugfix scope note:** a full-suite run is not always warranted. For a scoped bugfix prefer
> the paired tests for changed files (change-with-tests contract, `34-backend-testing.md` /
> `30-backend-api-flask-mysql.md`); dispatch `full-test-suite.yml` (optionally a narrowed
> `scope:`) only when blast radius or cadence makes it relevant.

## Deploy workflows

| Workflow | Trigger (push paths) | Target |
| --- | --- | --- |
| `deploy-sam-members.yml` | `main`/`test`, `sam/members/**`, `sam/shared/**`, self | SAM Members stack, data acct `506221081911` |
| `deploy-sam-pretokengen.yml` | `main`/`test`, `sam/pretokengen/**`, `sam/shared/**`, self | PreTokenGen Lambda+layer, data acct `506221081911` |
| `deploy-frontend.yml` | `main`, `frontend/**`, `docs/**`, self | Production SPA + MkDocs → GitHub Pages |

All deploy workflows: resolve `config-env` from the branch (`test`→`test`, else `prod`;
`workflow_dispatch` **defaults `test`**); auth via **short-lived GitHub OIDC** assuming
`arn:aws:iam::506221081911:role/NonprofitDeployRole` (**no stored AWS secrets**); carry a
`concurrency` group; read per-env params from `samconfig.toml [<config-env>]` so CI and a
manual `sam deploy --config-env <env>` produce the same stack.

**Frontend TEST has no hosted target yet:** `deploy-frontend.yml` publishes only the `main`
(production) build to the single Pages site. The TEST frontend is the local dev server
(`VITE_APP_ENV=test`, `localhost:3000`). Add a `test`-branch job when a hosted TEST target exists.

**Deploys touch the DATA account only** (`506221081911`): Lambda, layer, same-account IAM,
and the cross-account invoke *permission*. Attaching the Pre-Token-Generation **trigger** on
the Cognito pool is in the identity account (`344561557829`) and is a **separate manual step**
(`sam/pretokengen/DEPLOY.md`). A merge never (re)wires the pool.

## Infrastructure-as-Code (Terraform) — NOT in the pipeline (yet)

> **CURRENT STATE: there is NO Terraform workflow.** `.github/workflows/` has no
> `terraform plan`/`apply` step — the deploy workflows above are SAM + frontend only. The
> `infrastructure/*.tf` (CloudFront, Cognito, SNS, S3, IAM, the application-form
> `frame-ancestors` KVS + function) is applied **manually from a workstation** per
> `infrastructure/README.md`. So "codified deploy, not hand-typed" (below) is TRUE for
> SAM/frontend but ASPIRATIONAL for Terraform — a `.tf` header that says "deployment is
> codified (steering 43)" means *will be*; today a human runs the apply. Close this gap by
> adding a `deploy-infra.yml` (OIDC → `NonprofitDeployRole`, `plan` on PR / `apply` on
> `main`) rather than by hand-applying more often.

**State + provider (facts, `infrastructure/main.tf`):** remote **S3 backend**
`myadmin-terraform-state-eu-west-1`, key `infrastructure/terraform.tfstate`, region
`eu-west-1`; AWS provider `~> 5.0`; a committed `.terraform.lock.hcl`. The S3 backend — not
any local file — is the source of truth. **Never commit `terraform.tfstate*`**: local state
files in the working tree are stale scratch, not authoritative; `.gitignore` them and read
state from the backend (`terraform state list`).

**Target account:** Terraform manages the DATA account `506221081911` (CloudFront, KVS, IAM)
plus identity-account Cognito — see `23-aws-accounts.md`. Sanity-check `aws sts
get-caller-identity` before an apply; the override-ranking trap (`41-shell-environment.md`)
can silently point you at the wrong account.

**Manual apply workflow (until a pipeline exists):**

1. **`terraform init`** (first run / after a provider or backend change; `-upgrade` to move
   within the pinned range).
2. **`terraform plan -out=tf.plan`** — ALWAYS plan to a saved file and READ it. Scope a
   focused change with `-target` (e.g. `-target=aws_cloudfront_function.application_form_frame_ancestors`)
   to shrink blast radius, but a `-target` run is a patch, not a reconcile — follow it with a
   full untargeted `plan` to confirm no drift.
3. **Inspect for danger BEFORE applying** — a destroy or a `# forces replacement` on a
   STATEFUL / shared resource (the `public_pages` CloudFront distribution, a KVS, a Cognito
   pool, an S3 bucket) is a STOP: replacing a live distribution or pool is a user-visible
   outage. Confirm the plan only *adds/updates in place* for such resources.
4. **`terraform apply tf.plan`** — apply the exact reviewed plan (never a bare
   `terraform apply` that re-plans and prompts `yes` against unseen changes).
5. **Record** what was applied (the plan summary) alongside the PR that merged the `.tf`, so
   the manual apply is traceable to a reviewed change.

**Change-with-review:** commit the `.tf` edit through the SAME reviewed PR as the code that
depends on it (the builder's embed feature needs the `frame-ancestors` KVS/function), so the
infra change is reviewed even though its apply is manual. Never hand-edit live infrastructure
in the console to match code — the console drifts from state; change the `.tf` and apply.

**Ordering with SAM/frontend:** when an IaC change is a PREREQUISITE for a code deploy (the
`frame-ancestors` function reads the KVS the backend populates from
`application_embed_origins`), apply the Terraform FIRST (or in the same window), then let the
codified SAM/frontend deploy follow — otherwise the feature is half-wired (a tenant authors
origins nothing enforces). Note the two live in different lifecycles (Terraform state vs.
CloudFormation stacks) and must not reference each other's resources by hard-coded id.

**Destroy / high-blast-radius ops** (`terraform destroy`, `-replace=`, `state rm`/`import`,
a backend migration) are owner-run only, never agent-run, and never without a reviewed plan.


## Promote `test` → `main` (production) runbook

1. **Confirm TEST is green & verified** — gates pass on `test`; exercised in live TEST, not just units.
2. **Open ONE PR `test → main`** for the whole promotion; close stale ones.
3. **Preview prod changesets** — for SAM, `sam deploy --config-env prod --no-execute-changeset`;
   confirm no unexpected `Replacement: True` on stateful resources.
3a. **Preview IaC changesets too** — if the promotion includes `infrastructure/*.tf`,
    `terraform plan -out=tf.plan` and confirm no `# forces replacement` on a stateful/shared
    resource; the manual `apply` happens in the same release window as the merge, not after.

4. **Clear security gates** — CodeQL **and** GitGuardian green on the PR; fix root cause, don't suppress.
5. **Merge with a MERGE COMMIT** (not squash) to preserve phase history on `main`.
6. **Watch the deploys** — the merge fires each deploy workflow whose paths changed (up to three
   runs, same title ≠ duplicate). Confirm each `success` and stacks settle `UPDATE_COMPLETE`.

## Non-negotiables

- **Never push straight to `main`** — production goes through a reviewed PR.
- **No AWS secrets in CI** — OIDC + `NonprofitDeployRole` only.
- **Branch decides the env** — resolve from `github.ref`, never hard-code `prod`/`test`.
- **`workflow_dispatch` defaults to `test`** — a mis-click must never deploy production.
- **A merge to `main` IS a production deploy** — treat every `test → main` merge as a release.
- **Terraform is manual + plan-first** — no pipeline today; `plan -out` → review for
  replacement/destroy on stateful resources → `apply` the saved plan. Never commit
  `tfstate`; never hand-edit live infra; destroy/`-replace`/state surgery is owner-run only.
