# Requirements Document

## S5e — Codify SAM deploys (committed samconfig + OIDC CI, no ad-hoc `sam deploy`) — Requirements

- Status: **Draft** (requirements phase — check in before design)
- Surfaced during: **s5d PHASE CE** (2026-09-23) — see `myBacklog/backlog.md`
  ("SAM deploys are ad-hoc"). This spec is **#3 of 3** remediation specs blocking the
  resumption of s5d; the others are #1 (SAM edge active-tenant resolution) and #2
  (projection reconcile of `role#`/`module#`/`config#`).
- Why tooling-first: the s5d **edge fix (#1)** will require a `sam/members` redeploy, and
  the PreTokenGen work already exposed that `sam/pretokengen` has **no repeatable deploy
  path at all**. Codifying deploys first means #1 ships through a reviewed, one-command,
  account-correct pipeline instead of another hand-typed `sam deploy`.
- Governing steering: `23-aws-accounts`, `35-sam-module-architecture-sam`,
  `41-shell-environment` (the `.env`-overrides-`AWS_PROFILE` credential trap),
  `40-spec-workflow`.

## Introduction

The two SAM applications in the repo are at **unequal maturity**:

- **`sam/members` is fully codified** (delivered in s5d / PR #16): a committed
  `sam/members/samconfig.toml` with a `[prod]` env that pins `stack_name = "sam-members"`,
  region, capabilities, and the full `parameter_overrides`; and a CI workflow
  `.github/workflows/deploy-sam-members.yml` that authenticates via **GitHub OIDC**
  (`NonprofitDeployRole`, account `506221081911`, `eu-west-1`) and runs
  `sam build` then `sam deploy --config-env prod`. CI and a manual
  `sam deploy --config-env prod` therefore produce the **same** stack.

- **`sam/pretokengen` is not codified at all**: **no `samconfig.toml`, no deploy
  workflow, no pinned stack name.** During s5d PHASE CE the prod-stage Lambda
  (`pretokengen-prod`) had to be deployed by a hand-typed `sam deploy` with inline
  `--parameter-overrides` and a hand-chosen `--stack-name`. That deploy carried three
  avoidable risks that this spec exists to remove:
  1. **Stack-name footgun.** In the template, `Stage` only feeds `!Sub` for the
     **function/layer** names (`pretokengen-${Stage}`); it does **not** name the
     CloudFormation stack. Re-deploying the same stack with a different `Stage` would
     **rename/replace** the existing function/layer (e.g. a `Stage=prod` deploy against
     the `test` stack would destroy the working `pretokengen-test`). Only operator
     discipline prevented it.
  2. **Credential trap.** The repo-root `.env` exports static
     `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` for the **personal** account
     (`344561557829`), which boto3/the CLI rank **above** `AWS_PROFILE`. A plain
     `AWS_PROFILE=nonprofit-deploy sam deploy` silently targets the **wrong account**
     (see `41-shell-environment`). CI (OIDC, no `.env`) sidesteps this — manual deploys
     do not.
  3. **Drift.** Inline params are typed fresh every time; nothing guarantees the next
     deploy matches the last.

The frontend showed the same *class* of gap (a required build var,
`VITE_MEMBERS_API_BASE_URL`, was simply missing from `deploy-frontend.yml`, so prod
silently shipped the `127.0.0.1:3000` fallback — fixed in PR #16). The common root cause
is **deploy config that is not complete, pinned, and committed.**

s5e closes the gap by bringing `sam/pretokengen` up to the `sam/members` standard and
hardening the shared pattern so the footgun cannot bite. It is **tooling/IaC only** — no
change to Lambda runtime behavior, no CloudFormation resource behavior change, no data.

## Glossary

- **Codified deploy** — a deploy whose stack name, region, capabilities, and every
  parameter come from a **committed** `samconfig.toml` env, invoked as
  `sam deploy --config-env <env>` (no inline `--parameter-overrides`, no ad-hoc
  `--stack-name`), so CI and a local run of the same command produce the identical stack.
- **`--config-env`** — the SAM CLI selector for a named environment block in
  `samconfig.toml` (e.g. `[test.deploy.parameters]`, `[prod.deploy.parameters]`).
- **Stage (template parameter)** — the SAM template `Stage` parameter. It names
  **resources** (`pretokengen-${Stage}`, `members-${Stage}`), NOT the CloudFormation
  **stack**. The stack name is a separate `samconfig` value.
- **OIDC deploy** — GitHub Actions assuming an AWS IAM role via short-lived STS
  (`aws-actions/configure-aws-credentials@v4`, `id-token: write`), with **no stored
  long-lived AWS secrets**.
- **Data account** (= the **`nonprofit-deploy`** account `506221081911`, `eu-west-1`,
  role `NonprofitDeployRole`) — matches the house naming in the s5d rollout plan
  ("data-account = `nonprofit-deploy` 506221081911"). Holds DynamoDB, Lambda, the
  `sam-members`/`pretokengen-*` stacks. Throughout this spec "data account" always means
  this `nonprofit-deploy` account.
- **Identity account** (= the **`personal`** account `344561557829`, profile `personal`) —
  holds the Cognito pools (Pool A `myAdmin` `eu-west-1_Hdp40eWmu`; test `myAdmin-test`
  `eu-west-1_xyrlzfqbl`). The PreTokenGen Lambda lives in the `nonprofit-deploy` data
  account but is invoked cross-account by Cognito in this `personal` identity account.
- **Cross-account invoke** — the `AWS::Lambda::Permission` allowing Cognito
  (identity `344561557829`) to invoke `pretokengen-prod` (data `506221081911`), plus the
  Pool A trigger attach. Currently applied by hand during s5d CE.5, NOT in any template.

## Guiding principles (settled — requirements enforce them)

- **`sam/members` is the reference implementation.** `sam/pretokengen` should reach the
  same shape (committed config + OIDC CI + pinned distinct stack). Do not invent a new
  pattern; mirror the proven one.
- **One reviewed command per environment.** Every prod (and test) deploy is
  `sam deploy --config-env <env>` — reproducible, reviewable in a diff, no typing params.
- **Stack name is pinned per environment and DISTINCT across environments.** `test` and
  `prod` deploys of the same app MUST target different stacks so one can never
  rename/replace the other.
- **No stored AWS secrets.** CI authenticates via OIDC role assumption only.
- **Two accounts, two jobs — kept explicit.** The full pretokengen deploy touches BOTH
  accounts, and the spec names both rather than pretending it is a single-account job:
  - **`nonprofit-deploy` data account (`506221081911`)** owns the deployable stack
    (Lambda + layer + the same-account IAM policy). This is what the CI workflow (R2)
    deploys via OIDC.
  - **`personal` identity account (`344561557829`)** owns Pool A and therefore the
    Pre-Token-Generation **trigger attach**; the cross-account **invoke permission** is a
    resource policy on the Lambda back in the data account. This cross-account wiring is
    R5's job, deliberately NOT the CI workflow's (the data-account OIDC role has no
    credentials in the personal account and the attach is a once-only action).
- **Account-correct by construction.** The deploy pipeline must land in the
  **`nonprofit-deploy` data account (`506221081911`)** regardless of the local `.env`
  credential trap. CI OIDC guarantees
  this; documented manual fallbacks must strip the `.env` static keys per
  `41-shell-environment`.
- **IaC/tooling only.** No Lambda code, no resource behavior, no data changes. Deploying
  from the new config MUST produce the same running resources as today (empty changeset
  where nothing changed).
- **Public config only in the repo.** `samconfig` may hold PUBLIC identifiers (pool id,
  app-client id, table names, ARNs); never secrets.

## Requirements

### R1 — `sam/pretokengen` gains a committed `samconfig.toml` with distinct `test` and `prod` envs

**User story:** As the operator, I want `sam/pretokengen` deploys driven by a committed
config so that a deploy is one reviewed command that always lands in the right account,
stack, and stage — never a hand-typed parameter list.

#### Acceptance criteria
1. WHEN the repo is inspected THEN a committed `sam/pretokengen/samconfig.toml` SHALL exist
   with a `[test.deploy.parameters]` env and a `[prod.deploy.parameters]` env.
2. The `[test]` env SHALL pin `stack_name` to a name distinct from `[prod]`'s, AND the
   two stack names SHALL be chosen so a deploy of one can never rename/replace the other's
   function/layer (e.g. `pretokengen-test` and `pretokengen-prod`).
3. Each env SHALL set `region = "eu-west-1"`, the `capabilities` the template needs
   (`CAPABILITY_IAM`, and `CAPABILITY_NAMED_IAM` because functions/layers are named via
   `!Sub`), `resolve_s3 = true`, and non-interactive changeset flags consistent with the
   members config.
4. Each env's `parameter_overrides` SHALL supply every template parameter that has no safe
   default — `Stage` (`test` / `prod`), `Region=eu-west-1`, and
   `GovernanceProjectionTableName` (the env-appropriate table:
   `test_governance_projection` for test, `governance_projection` for prod) — so the
   deploy is fail-fast-complete with no inline flags.
5. WHEN `sam deploy --config-env prod` is run from `sam/pretokengen` (in the data account)
   THEN it SHALL produce the SAME `pretokengen-prod` function/layer that exist today
   (an empty or no-op changeset), proving the committed config matches the live hand deploy.
6. The `samconfig.toml` SHALL contain a header comment stating the account
   (`506221081911`), the OIDC role, the distinct-stack-name rationale, and that no secrets
   belong in the file — mirroring `sam/members/samconfig.toml`.

### R2 — `sam/pretokengen` gains an OIDC CI deploy workflow

**User story:** As the operator, I want `sam/pretokengen` to deploy from CI on merge so
that its prod Lambda stays in sync with the repo without any hand-typed, account-fragile
local deploy.

#### Acceptance criteria
1. WHEN the repo is inspected THEN a committed
   `.github/workflows/deploy-sam-pretokengen.yml` SHALL exist.
2. The workflow SHALL authenticate via GitHub OIDC assuming
   `arn:aws:iam::506221081911:role/NonprofitDeployRole` in `eu-west-1`, with
   `permissions: id-token: write, contents: read`, and NO stored AWS secrets — mirroring
   `deploy-sam-members.yml`. This scope is the **`nonprofit-deploy` data account
   (`506221081911`) only** — deliberately: the workflow deploys the Lambda + layer +
   same-account IAM, which all live there. It does NOT (and cannot, with these
   credentials) act in the `personal` identity account (`344561557829`); the Pool A
   trigger attach there is R5's separate step.
3. The workflow's scope SHALL be documented in the workflow file's header as data-account
   deploy ONLY, with a one-line pointer to R5 (the identity-account Cognito wiring), so a
   reader is never left thinking a merge also (re)wires Pool A.
4. The workflow SHALL trigger on `push` to `main` for the paths that affect the app
   (`sam/pretokengen/**`, `sam/shared/**`, and the workflow file itself) AND on
   `workflow_dispatch`.
5. The workflow SHALL set a `concurrency` group so two pretokengen deploys never run
   against the same stack simultaneously.
6. The workflow SHALL run `sam build` then `sam deploy --config-env prod`
   `--no-confirm-changeset --no-fail-on-empty-changeset` from `sam/pretokengen`, taking
   ALL parameters from the committed `samconfig.toml` (R1) — no inline params.
7. IF the `NonprofitDeployRole` OIDC trust does not yet allow this workflow THEN the
   requirement to add/confirm that trust SHALL be captured as a gated `[H]` prerequisite
   task (as `deploy-sam-members.yml` documents), not silently assumed.

### R3 — The `Stage`-vs-stack-name footgun is neutralized and documented

**User story:** As the operator, I want it to be impossible (or loudly guarded) for a deploy
to rename/replace the wrong-stage Lambda so that a routine deploy can never destroy the
working test or prod function.

#### Acceptance criteria
1. WHEN both pretokengen envs exist (R1) THEN each SHALL pin a DISTINCT `stack_name`, so
   `--config-env test` and `--config-env prod` are physically separate CloudFormation
   stacks (the primary guard).
2. The `samconfig.toml` and the SAM template SHALL carry a comment explaining that `Stage`
   names resources only, NOT the stack, and that the distinct pinned stack names are what
   prevent the rename/replace footgun.
3. WHEN the design considers additional guards (e.g. a `RetentionPolicy: Retain` review, or
   a deploy-time assertion that `Stage` matches the target stack) THEN any such guard
   SHALL be tooling/comment-level only and MUST NOT change runtime behavior (per the
   IaC-only principle).

### R4 — `sam/members` codification is verified at parity (and any gap closed)

**User story:** As the operator, I want confidence that the reference app is actually
complete so that "mirror members" is a sound instruction and #1's redeploy is safe.

#### Acceptance criteria
1. WHEN `sam/members/samconfig.toml` and `deploy-sam-members.yml` are reviewed THEN the
   spec SHALL confirm the `[prod]` env pins the stack, region, capabilities, and full
   `parameter_overrides`, and that CI uses OIDC with no secrets.
2. IF the members app is expected to support a non-prod environment (e.g. a `test`/`dev`
   stack) THEN the gap SHALL be recorded; ELSE the spec SHALL state explicitly that
   members is prod-only by design (its runnable non-prod path is `sam local`, not a
   deployed stack) so the asymmetry with pretokengen's `test` env is intentional.
3. The verification SHALL be evidence-based (a `sam deploy --config-env prod` empty/no-op
   changeset, or an equivalent read of the live stack), not assumed.

### R5 — Cross-account Cognito wiring (the identity-account half) is documented as an explicit, repeatable step

**User story:** As the operator, I want the PreTokenGen cross-account invoke permission and
Pool A trigger attach to be a documented, repeatable step so that re-deploying pretokengen
never silently loses the Cognito wiring that was applied by hand in s5d CE.5.

**Why this is separate from R2 (both accounts, named):** the full deploy spans two
accounts and this spec covers BOTH — it just splits them by who can safely do each half:
- **Invoke permission** — a resource policy on `pretokengen-prod`, which lives in the
  **data account `506221081911`** (same account the R2 workflow already has credentials
  for). **DECIDED: this goes IN the SAM template**, so `sam deploy` creates and maintains
  it automatically on every deploy (the tool maintains it; nobody re-runs a manual grant).
- **Pre-Token-Generation trigger attach** — on Pool A, which lives in the **identity/
  personal account `344561557829`**. The R2 data-account OIDC role has NO credentials
  there, and the attach is a once-only action, so it cannot and should not ride the CI
  workflow.

#### Acceptance criteria
1. The cross-account `lambda:InvokeFunction` permission (Cognito → `pretokengen-prod`,
   data account `506221081911`) SHALL be declared IN the SAM template as an
   `AWS::Lambda::Permission` resource, so it is created and maintained by `sam deploy`
   (R2's workflow) — the tool maintains it, no manual grant. The permission SHALL be
   scoped to the Pool A principal / source ARN in the identity account `344561557829`.
2. The Pre-Token-Generation **trigger attach** on Pool A (identity account
   `344561557829`) SHALL remain a documented, repeatable **manual `[H]` step** applied with
   the `personal` profile — it CANNOT ride the data-account CI workflow (no credentials in
   that account; once-only action). The documentation SHALL carry the `41-shell-environment`
   account guardrail.
3. WHEN pretokengen is re-deployed via the codified path THEN the invoke permission SHALL be
   (re)asserted by the template and the existing Pool A trigger SHALL remain attached and
   functional (the deploy MUST NOT detach it); a post-deploy check SHALL confirm both.

### R6 — Documented, account-correct manual fallback (belt-and-suspenders)

**User story:** As the operator, I want a documented manual deploy path for when CI cannot
be used so that even a hand deploy lands in the correct account and stack.

#### Acceptance criteria
1. WHEN a manual deploy is needed THEN the documented command SHALL be exactly
   `sam deploy --config-env <env>` (no inline params, no `--stack-name`), preceded by the
   `41-shell-environment` credential-strip / export-role-creds guardrail so `.env` static
   keys cannot redirect it to the personal account.
2. The documentation SHALL include the sanity-check that identity resolves to
   `506221081911` (`NonprofitDeployRole`) BEFORE any mutating deploy command.
3. The manual path SHALL be documented alongside the app (README or a short deploy note in
   the spec), not only in chat history.

### R7 — Scope discipline: IaC/tooling only, no behavioral or data change

**User story:** As a reviewer, I want the change to be provably deploy-tooling-only so that
codifying deploys carries no risk to running Lambdas or data.

#### Acceptance criteria
1. The change set SHALL be limited to `samconfig.toml` files, `.github/workflows/*.yml`,
   documentation, and template edits that are EITHER comment-only OR the single
   deliberate `AWS::Lambda::Permission` addition from R5.1. NO other resource is added,
   altered, or removed.
2. The one intentional resource change is the R5.1 invoke permission. It SHALL be
   equivalent to the permission already applied by hand in s5d CE.5 (same Cognito
   principal / Pool A source, same `pretokengen-prod` target), so bringing it under the
   template asserts the SAME access that is already live — it grants NO new access. The
   design SHALL address how CloudFormation reconciles the pre-existing manual permission
   (adopt / import / recreate) so the deploy does not fail on a "resource already exists"
   conflict.
3. Apart from that one permission, WHEN deploying from the new config THEN the running
   resources (`pretokengen-prod`, `pretokengen-layer-prod`, `sam-members`) SHALL be
   unchanged versus before (empty/no-op changeset where nothing else was intended to
   change).
4. NO Lambda handler/domain/repository code, NO DynamoDB table, and NO Cognito pool
   configuration SHALL be modified by this spec. The Pool A **trigger attach** (R5.2) is
   applied out-of-band in the identity account (already done in CE.5), NOT by this
   template.
