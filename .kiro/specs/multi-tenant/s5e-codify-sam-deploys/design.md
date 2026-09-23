# Design Document

## S5e — Codify SAM deploys — Design

- Requirements: `./requirements.md` (R1–R7).
- Governing steering: `23-aws-accounts`, `35-sam-module-architecture-sam`,
  `41-shell-environment`, `40-spec-workflow`.
- Reference implementation (do not reinvent): `sam/members/samconfig.toml` +
  `.github/workflows/deploy-sam-members.yml` (both delivered in PR #16).

## Overview

s5e adds two committed artifacts to `sam/pretokengen` (a `samconfig.toml` and an OIDC CI
workflow) that mirror the proven `sam/members` pattern, plus comment-level hardening of the
`Stage`-vs-stack-name footgun and documentation of the cross-account Cognito wiring and the
account-correct manual fallback. It is **IaC/tooling only** — no runtime, resource, or data
change (R7). The success test throughout is an **empty/no-op changeset**: deploying from the
new config must reproduce exactly what is running today.

The essential asymmetry s5e removes:

| | `sam/members` (reference) | `sam/pretokengen` (today) | `sam/pretokengen` (after s5e) |
|---|---|---|---|
| committed `samconfig.toml` | ✓ `[prod]` | ✗ | ✓ `[test]` + `[prod]` |
| OIDC CI workflow | ✓ | ✗ | ✓ |
| pinned distinct stack name | ✓ `sam-members` | ✗ (ad-hoc `--stack-name`) | ✓ `pretokengen-data` (test) / `pretokengen-prod` |
| deploy = one reviewed command | ✓ | ✗ (hand-typed inline params) | ✓ |

## What "test" (and the other stages) mean here

"test" in this spec is a **deployment stage** (the SAM `Stage` param value), NOT software
tests. There are three non-prod-vs-prod environments; only the two DEPLOYED ones get a
`samconfig` env. Facts confirmed from steering `23-aws-accounts` + the s5c spec:

| Environment | `Stage` | Cognito pool (login) | Pool account | Projection table | DynamoDB | Deployed Lambda? |
|---|---|---|---|---|---|---|
| **Local dev** | `local` | `myAdmin-test` (`COGNITO_POOL_KEYS=TEST`) | `personal` `344561557829` | `test_governance_projection` | **Docker** `localhost:8000` | No — `sam local` only |
| **Deployed test** | `test` | `myAdmin-test` `eu-west-1_xyrlzfqbl` | **`personal` `344561557829`** | `governance_projection` (prod table, by design — ODx1/CE.3) | `nonprofit-deploy` `506221081911` | Yes — stack `pretokengen-data` |
| **Prod** | `prod` | Pool A `myAdmin` `eu-west-1_Hdp40eWmu` | **`personal` `344561557829`** | `governance_projection` | `nonprofit-deploy` `506221081911` | Yes — `pretokengen-prod` |

Account naming (house style, per s5d rollout plan + steering `23-aws-accounts`):
- **data account = the `nonprofit-deploy` account `506221081911`** (role
  `NonprofitDeployRole`) — DynamoDB + Lambda + the SAM stacks.
- **identity account = the `personal` account `344561557829`** — the Cognito pools.

Key points that shape the design:
- **Both Cognito pools (test AND prod) live in the `personal` identity account
  `344561557829`.** The Lambda for every stage lives in the **`nonprofit-deploy` data
  account `506221081911`**. So the cross-account invoke shape (identity pool → data
  Lambda) is IDENTICAL for test and prod — only the pool id differs. The invoke permission
  (D5a) is therefore parameterized per env: test scopes to `eu-west-1_xyrlzfqbl`, prod to
  `eu-west-1_Hdp40eWmu`, both in the `personal` account `344561557829`.
- **`local` is Docker + `sam local`, not a deployed stack.** It shares the `myAdmin-test`
  pool for SPA logins and the `test_governance_projection` table name, but against a local
  DynamoDB container — no AWS Lambda, no CloudFormation. So `samconfig` defines only the
  two DEPLOYED envs (`test`, `prod`); `local` is out of samconfig's scope.
- The samconfig `[test]`/`[prod]` blocks differ only in: stack name, `Stage`,
  `GovernanceProjectionTableName`, and the Cognito pool id for the invoke permission.

## Design decisions

### D1 — Stack names: `pretokengen-data` (test) and `pretokengen-prod` (distinct, pinned)

The primary and sufficient guard against the rename/replace footgun (R3.1) is that the two
environments pin **different `stack_name` values**. Per ODx1 (resolved), we pin the names to
the LIVE stacks — no churn: `[test]` → `pretokengen-data` (the historical test-pool stack
name, predating the `-test`/`-prod` convention); `[prod]` → `pretokengen-prod`. The `Stage`
param still names the resources (`pretokengen-${Stage}`) inside each stack. Because the two
are distinct CloudFormation stacks, a `--config-env prod` run can never touch the test
stack's function/layer, and vice-versa.

- Rejected: reusing a SINGLE stack parameterized only by `Stage` — that is precisely the
  footgun; a `Stage=prod` deploy against the test stack would RENAME/REPLACE the working
  test function/layer.
- Rejected (ODx1 option b): renaming the test stack to `pretokengen-test` — cosmetic only,
  and it would create a second stack + orphan `pretokengen-data`.
- The stack names read slightly unevenly (`pretokengen-data` vs `pretokengen-prod`); a
  samconfig comment records why (match live reality). The guard does not depend on the
  names being symmetric, only on their being DISTINCT.

### D2 — `samconfig.toml` shape: one `[<env>.deploy.parameters]` block per env

Mirror `sam/members/samconfig.toml` field-for-field where applicable:

```toml
version = 0.1

# Stack + Lambda deploy to the `nonprofit-deploy` data account 506221081911 (eu-west-1).
# The Cognito pool the invoke permission targets lives in the `personal` identity account
# 344561557829 (cross-account).
# --- TEST — Lambda in data acct; triggered from personal-acct pool `myAdmin-test` ---
[test.deploy.parameters]
stack_name = "pretokengen-data"      # LIVE test stack (ODx1); DISTINCT from prod (D1/R3)
region = "eu-west-1"
capabilities = "CAPABILITY_IAM CAPABILITY_NAMED_IAM"   # named fn/layer via !Sub
resolve_s3 = true
confirm_changeset = false
fail_on_empty_changeset = false
parameter_overrides = [
  "Stage=test",
  "Region=eu-west-1",
  # NOTE (ODx1): the live pretokengen-data stack reads the PROD projection table on purpose
  # (test = the test POOL, not a separate table; see CE.3). Match reality for an empty changeset.
  "GovernanceProjectionTableName=governance_projection",
  "CognitoAccountId=344561557829",              # personal/identity acct (D5a)
  "CognitoUserPoolId=eu-west-1_xyrlzfqbl",       # myAdmin-test pool
]

# --- PROD — Lambda in data acct; triggered from personal-acct Pool A `myAdmin` ---
[prod.deploy.parameters]
stack_name = "pretokengen-prod"      # DISTINCT from test
region = "eu-west-1"
capabilities = "CAPABILITY_IAM CAPABILITY_NAMED_IAM"
resolve_s3 = true
confirm_changeset = false
fail_on_empty_changeset = false
parameter_overrides = [
  "Stage=prod",
  "Region=eu-west-1",
  "GovernanceProjectionTableName=governance_projection",
  "CognitoAccountId=344561557829",              # personal/identity acct (D5a)
  "CognitoUserPoolId=eu-west-1_Hdp40eWmu",       # Pool A (myAdmin)
]
```

- `capabilities` includes `CAPABILITY_NAMED_IAM` because the template names its
  function/layer (`!Sub "pretokengen-${Stage}"`) and creates a named inline IAM policy;
  this matches the members config's capabilities string.
- The template's `GovernanceProjectionTableName` has **no default** (fail-fast), so it
  MUST be in `parameter_overrides` for each env (R1.4). **Both `test` and `prod` read
  `governance_projection`** — the live `pretokengen-data` (test) stack was deliberately
  deployed against the prod projection table (ODx1 / CE.3: the test *pool* is what makes it
  "test"). `test_governance_projection` is the LOCAL/Docker (`Stage=local`) table only, and
  `local` is not a deployed samconfig env.
- `Region` and `Stage` likewise have to be supplied (`Region` has no default; `Stage`
  defaults to `local`, which is not a deploy target).
- Header comment records account, OIDC role, distinct-stack rationale, and "no secrets"
  (R1.6). There are **no Cognito identifiers** here (unlike members) — pretokengen has no
  API authorizer; it only reads the projection table.

### D3 — CI workflow: clone `deploy-sam-members.yml`, retarget paths + config-env

`.github/workflows/deploy-sam-pretokengen.yml`:

```yaml
name: Deploy SAM PreTokenGen
on:
  push:
    branches: [main]
    paths:
      - "sam/pretokengen/**"
      - "sam/shared/**"
      - ".github/workflows/deploy-sam-pretokengen.yml"
  workflow_dispatch:
permissions:
  id-token: write
  contents: read
concurrency:
  group: sam-pretokengen-deploy
  cancel-in-progress: false
jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - uses: aws-actions/setup-sam@v2
        with: { use-installer: true }
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::506221081911:role/NonprofitDeployRole
          aws-region: eu-west-1
      - name: SAM Build
        working-directory: sam/pretokengen
        run: sam build
      - name: SAM Deploy
        working-directory: sam/pretokengen
        run: sam deploy --config-env prod --no-confirm-changeset --no-fail-on-empty-changeset
```

- Deploys **prod** on merge to `main` (mirrors members — CI is the prod path). The `test`
  env is for manual/`workflow_dispatch` or a local `sam deploy --config-env test`; s5e does
  NOT add an auto test-deploy trigger (test pool is not on the merge path). Recorded as
  **ODx2** if the user wants a test job too.
- Shares `sam/shared/**` in the path filter because both apps' layers vendor it — a shared
  change should redeploy both.
- OIDC trust prerequisite: `NonprofitDeployRole` must already trust
  `repo:PeterGeers/myAdmin:ref:refs/heads/main` (it does, for members). If the trust is
  scoped per-workflow it may need confirming — captured as a gated `[H]` task (R2.6).

### D4 — Footgun hardening is comment + distinct-stack, not runtime (R3, R7)

The distinct pinned stack names (D1) are the real guard. In addition:
- Add a comment block to `sam/pretokengen/template.yaml` (near the `Stage` parameter) and
  to the `samconfig.toml` header stating: *`Stage` names the function/layer only, NOT the
  stack; the stack is pinned per env in samconfig; never deploy two stages into one stack.*
- The layer/function already carry `RetentionPolicy: Retain` on the layer; note in the
  design that the function is replaced-in-place within its own stack (safe) but never
  across stacks (different stack = different logical+physical resource).
- No deploy-time assertion script is added (would be runtime tooling with its own failure
  modes); distinct stacks + comments satisfy R3 without it.

### D5 — Cross-account Cognito wiring: SPLIT by what the flow can reach (R5)

The Pool A trigger attach + cross-account `lambda:InvokeFunction` permission were applied by
hand in s5d CE.5. The decision (settled with the user): **let the flow maintain everything
it can reach, and leave manual only the one piece it physically cannot.** They split by
account:

**(a) Invoke permission → INTO the SAM template (the flow maintains it).**
The `lambda:InvokeFunction` grant is a resource policy on `pretokengen-prod`, a
**`nonprofit-deploy` data-account** (`506221081911`) resource — the same account the OIDC
pipeline already deploys into. So it is declared as an `AWS::Lambda::Permission` in
`sam/pretokengen/template.yaml`:
```yaml
  PreTokenGenCognitoInvokePermission:
    Type: AWS::Lambda::Permission
    Properties:
      Action: lambda:InvokeFunction
      FunctionName: !Ref PreTokenGenFunction
      Principal: cognito-idp.amazonaws.com
      SourceArn: !Sub "arn:aws:cognito-idp:${Region}:${CognitoAccountId}:userpool/${CognitoUserPoolId}"
```
This needs two new **template parameters**, both PUBLIC identifiers, supplied per env via
`samconfig.toml` `parameter_overrides`:
- `CognitoAccountId` = `344561557829` (the personal/identity account — SAME for both envs,
  because both the `myAdmin-test` and Pool A pools live there);
- `CognitoUserPoolId` = `eu-west-1_Hdp40eWmu` (Pool A) for prod, `eu-west-1_xyrlzfqbl`
  (`myAdmin-test`) for test.

Note the cross-account shape: the `SourceArn` points at a pool in `344561557829` while the
permission itself is attached to the Lambda in `506221081911`. That is exactly the
identity→data invoke pattern from ADR 0006 / s5c, and it is identical for test and prod —
only the pool id changes. After this, every `sam deploy` (re)asserts the permission; nobody
runs a manual `lambda add-permission` again.

**(b) Pool A trigger attach → stays a manual `[H]` step (the flow cannot reach it).**
The trigger lives ON Pool A in the **`personal` identity account** (`344561557829`). The
`nonprofit-deploy` data-account OIDC role has NO credentials there, so the pipeline
physically cannot attach
it. It is a once-only action anyway. Documented as a gated `[H]` runbook step (the exact
`cognito-idp` command from CE.5, `personal` profile) in `tasks.md` + a short `DEPLOY.md`
beside the app, carrying the `41-shell-environment` account guardrail.

**Reconciling the pre-existing manual permission (R7.2).** The invoke permission already
exists in AWS (added by hand in CE.5), so the FIRST codified deploy must not fail with
"resource already exists." Approach, in order of preference:
- The manual CE.5 permission was created with an explicit **statement id (`--statement-id`)**.
  If the template's generated permission logical id yields a DIFFERENT statement id, the two
  can briefly coexist harmlessly (same grant). Plan: after the first template deploy asserts
  the CFN-managed permission, **remove the orphaned hand-added statement** (a one-time `[H]`
  `lambda remove-permission --statement-id <ce5-sid>`) so the template is the sole owner.
- Alternatively `aws cloudformation import` the existing permission into the stack. Heavier;
  only if the coexist-then-remove path proves messy.
- Verify via a `--no-execute-changeset` first (task 1.3) to see exactly how CloudFormation
  treats it before any apply.

**Post-deploy check (R5.3 / P6).** After any `pretokengen-prod` deploy, confirm (i) the
function policy carries the CFN-managed Cognito invoke statement, and (ii) Pool A still
lists the trigger. The trigger is external to the stack, so an in-stack redeploy never drops
it — the check makes that explicit.

### D6 — members parity: prod-only by design (R4)

`sam/members` has only a `[prod]` env and that is **intentional**: its non-prod runnable
path is `sam local start-api` (see the template's `Stage` docstring and the local
`env-vars.local.json`), not a deployed `test` stack. So the members↔pretokengen asymmetry
(members has no `test` env; pretokengen does) is by design: pretokengen's `test` stage is a
real deployed Lambda attached to the `myAdmin-test` pool, whereas members' local stage is
served by `sam local`. The design records this rather than adding a members `test` env.
- Verification of members codification is evidence-based: a `sam deploy --config-env prod`
  dry-run/changeset showing empty, or a `describe-stacks` read (R4.3).

## Data models / resources touched

**One intentional new template resource** (D5a): the `AWS::Lambda::Permission`
(`PreTokenGenCognitoInvokePermission`) that grants Cognito/Pool A invoke on
`pretokengen-prod`. It asserts the SAME grant already applied by hand in CE.5 — no new
access (R7.2). Everything else is unchanged. For reference, the resources the codified
deploys manage:

- Stack `pretokengen-prod`: `PreTokenGenFunction` (`pretokengen-prod`),
  `PreTokenGenLayer` (`pretokengen-layer-prod`, `Retain`), inline IAM policy
  (`dynamodb:Query` scoped to `governance_projection` in `506221081911`), **and now the
  `PreTokenGenCognitoInvokePermission` (D5a)**.
- Stack `pretokengen-data` (test): `-test`-named fn/layer, reading `governance_projection`
  (the prod table, by design — ODx1/CE.3), permission scoped to the `myAdmin-test` pool.
- Stack `sam-members`: unchanged; verified only.
- External to all stacks (D5b): the Pool A **trigger** attach only (personal account) —
  the invoke *permission* is now IN the template, no longer external.

## Correctness properties

- **P1 — Reproducibility.** For each app+env, CI and a local `sam deploy --config-env <env>`
  produce the identical stack (same name, params, capabilities). _(R1, R2)_
- **P2 — Behavior-preserving changeset (VERIFIED 2026-09-23, task 1.4).** Deploying the
  codified prod config against the live `pretokengen-prod` yields a changeset with exactly
  these changes, all behavior-preserving:
  - `Add` `PreTokenGenCognitoInvokePermission` — the one intended new resource (D5a), same
    access as the live CE.5 hand-grant.
  - `Add` new `LayerVersion` + `Remove` old + `Modify` function (`Replacement: False`) —
    the STANDARD result of a `sam build` layer re-hash (new logical id per content hash);
    same vendored closure + pinned deps, no code change, old physical layer retained
    (`RetentionPolicy: Retain`), function updated in place (no replacement/downtime).
  There is NO pure-empty changeset for a SAM app whose layer is rebuilt — the layer churn
  is intrinsic and happens on every redeploy (members included). "No-op" here means "no
  behavioral or destructive change," NOT "zero changeset entries." The invoke permission is
  the only genuinely new/functional change. _(R1.5, R7.2, R7.3)_
- **P3 — Stack isolation.** No single deploy command can rename/replace the other stage's
  function/layer, because `test` and `prod` are distinct pinned stacks. _(R3.1)_
- **P4 — Account correctness.** Every deploy (CI via OIDC; manual via the documented strip)
  lands in the `nonprofit-deploy` data account (`506221081911`); a plain `.env`-polluted
  invocation is prevented or caught by the identity sanity-check. _(R2.2, R6)_
- **P5 — No stored secrets.** The workflow contains no AWS access keys; auth is STS via
  OIDC only. _(R2.2)_
- **P6 — Cognito wiring survives redeploy.** After a codified `pretokengen-prod` redeploy,
  the Pool A trigger and cross-account invoke permission remain intact (verified). _(R5.3)_

## Open decisions

- **ODx1 — RESOLVED 2026-09-23 (task 0.1).** Live stacks + their DEPLOYED PARAMETERS
  verified via `cloudformation describe-stacks` (`nonprofit-deploy` data account
  `506221081911`, `eu-west-1`):
  - `pretokengen-prod` (CREATE_COMPLETE): `Stage=prod`,
    `GovernanceProjectionTableName=governance_projection`.
  - `pretokengen-data` (UPDATE_COMPLETE): `Stage=test`,
    `GovernanceProjectionTableName=governance_projection` **← NOT `test_governance_projection`**.
  - `sam-members` (UPDATE_COMPLETE): matches its committed `[prod]` config.

  **Decisions:**
  1. **Test stack name → pin `[test].stack_name = "pretokengen-data"`** (option a: match
     reality, zero churn). The distinct-stack guard (D1/P3) still holds because
     `pretokengen-data` ≠ `pretokengen-prod`. Add a samconfig comment explaining the
     historical name (it predates the `-test`/`-prod` convention). Migrating to
     `pretokengen-test` (option b) is rejected — it would create a second stack and leave
     `pretokengen-data` to hand-delete, for cosmetic naming only.
  2. **CORRECTION to D2 — the live `[test]` stack reads the PROD projection table.**
     `pretokengen-data` was deployed with `GovernanceProjectionTableName=governance_projection`
     (confirmed by CE.3 in the s5d rollout plan: the test-pool Lambda points at the SAME
     prod projection table on purpose — the test POOL is what makes it "test", not a
     separate table). So `[test].parameter_overrides` MUST pin
     `GovernanceProjectionTableName=governance_projection`, **not** `test_governance_projection`,
     to match reality and yield an empty changeset (P2). `test_governance_projection` is the
     LOCAL/Docker table (`Stage=local`), which is NOT a deployed samconfig env — do not
     conflate the two. (Design D2 sample + the "What test means" table are corrected
     accordingly.)
  3. `[prod]` config (`stack_name=pretokengen-prod`, `Stage=prod`,
     `governance_projection`) matches reality exactly — zero churn.

- **R4 members parity — CONFIRMED by evidence 2026-09-23 (task 0.2).** `describe-stacks
  sam-members` (UPDATE_COMPLETE) returned deployed parameters that match the committed
  `sam/members/samconfig.toml` `[prod]` block field-for-field: `Stage=prod`,
  `MembersTableName=sam-members`, `GovernanceProjectionTableName=governance_projection`,
  `Region=eu-west-1`, `CognitoUserPoolArn=...eu-west-1_Hdp40eWmu`, `CognitoPoolKeys=MYADMIN`,
  the four `MyAdminCognito*` public identifiers, and `DynamoDbEndpointUrl=""` (template
  default, omitted in samconfig). So `sam deploy --config-env prod` for members is a proven
  no-op — members IS the codified reference standard, and it is **prod-only by design** (D6:
  non-prod path is `sam local`, no deployed test stack). No members gap to close.
- **ODx2 (nice-to-have):** add a CI job/trigger that deploys `--config-env test` on a
  non-main branch or dispatch input, so test-pool changes also flow through CI. Deferred
  unless the user wants it; s5e's blocking purpose is prod codification.
- **ODx3 (future):** after s5e, the ONLY un-IaC'd Cognito piece is the Pool A **trigger
  attach** (D5b, identity account) — the invoke permission is now in the SAM template
  (D5a). Fold that remaining trigger attach into IaC (e.g. a small Terraform addition in
  `infrastructure/`, which already manages the identity account) rather than an `[H]`
  runbook. Out of s5e scope; note for a later infra spec.
