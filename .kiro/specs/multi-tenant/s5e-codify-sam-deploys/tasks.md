# Implementation Plan

## S5e — Codify SAM deploys — Tasks

- Requirements: `./requirements.md` (R1–R7) · Design: `./design.md` (D1–D6, P1–P6,
  ODx1–ODx3).
- **Purpose:** #3 of 3 s5d-remediation specs. Bring `sam/pretokengen` up to the codified
  `sam/members` standard (committed `samconfig.toml` + OIDC CI) and harden the shared
  deploy pattern, so the s5d edge fix (#1) later ships through a reviewed, account-correct,
  one-command pipeline. **IaC/tooling only — no runtime, resource, or data change (R7).**
- Legend: `[ ]` todo · `[H]` human-run/gated (deploy / cross-account / prod) · `(dt)`
  verify-first · each task cites the Requirement(s) + design decision it implements.
- **Execution rules (steering):** `41-shell-environment` — WSL path split; exit code `-1`
  is NOT failure (judge by the `<<<DONE marker=$?>>>` marker); empty output ≠ finished; NO
  `sleep`; for any `nonprofit-deploy` command STRIP the `.env` static keys first
  (`env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN
  -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ENDPOINT_URL … --profile nonprofit-deploy`) and
  sanity-check identity resolves to `506221081911` before any mutating deploy.
  `35-sam-module-architecture-sam`, `23-aws-accounts`, `40-spec-workflow`.
- **Verified pre-facts (2026-09-23):** live `nonprofit-deploy` data-account stacks are `pretokengen-prod`
  (CREATE_COMPLETE), `pretokengen-data` (the `Stage=test` stack, UPDATE_COMPLETE), and
  `sam-members` (UPDATE_COMPLETE).

## Overview

Two new committed artifacts (`sam/pretokengen/samconfig.toml`, a
`deploy-sam-pretokengen.yml` workflow), comment-level footgun hardening on the pretokengen
template + config, a documented `[H]` runbook for the cross-account Cognito wiring and the
account-correct manual fallback, and an evidence-based parity check of `sam/members`. The
running test throughout: an **empty/no-op changeset** on the codified prod deploy (P2).

## Phase 0 — Resolve ODx1 + confirm parity (foundation, no writes yet)

- [x] **0.1 (dt) Resolve ODx1 (test stack name).** DONE 2026-09-23. Verified deployed
  params via `describe-stacks`: `pretokengen-prod` = `Stage=prod`/`governance_projection`
  (matches `[prod]`); `pretokengen-data` = `Stage=test` but **`governance_projection`** (the
  PROD table, not `test_governance_projection` — by design, CE.3). RESOLVED: pin
  `[test].stack_name = "pretokengen-data"` (match live, zero churn) AND both envs pin
  `GovernanceProjectionTableName=governance_projection`. Recorded inline in `design.md`
  ODx1. _(R1.2, R3.1; D1/ODx1)_
- [x] **0.2 (dt) Confirm `sam/members` parity is real (R4).** DONE 2026-09-23. Ran
  `describe-stacks --stack-name sam-members` (account strip, `nonprofit-deploy`): stack
  UPDATE_COMPLETE and its deployed params match the committed `samconfig.toml` `[prod]`
  block field-for-field (`Stage=prod`, `MembersTableName=sam-members`,
  `GovernanceProjectionTableName=governance_projection`, `Region=eu-west-1`,
  `CognitoUserPoolArn ...Hdp40eWmu`, `CognitoPoolKeys=MYADMIN`, 4×`MyAdminCognito*` public
  ids, `DynamoDbEndpointUrl=""` = template default). So `sam deploy --config-env prod` is a
  proven no-op — members is the codified reference standard, **prod-only by design**
  (non-prod = `sam local`, no deployed `test` env). Evidence recorded in `design.md` ODx1
  block. _(R4.1–R4.3; D6)_

## Phase 1 — Codify `sam/pretokengen` (the core gap)

- [x] **1.1 Author `sam/pretokengen/samconfig.toml`** with `[test.deploy.parameters]` and
  `[prod.deploy.parameters]` per design D2 + ODx1 (resolved): distinct pinned `stack_name`
  (**`pretokengen-data` for test** — the live stack; `pretokengen-prod` for prod), each
  with `region = "eu-west-1"`, `capabilities = "CAPABILITY_IAM CAPABILITY_NAMED_IAM"`,
  `resolve_s3 = true`, `confirm_changeset = false`, `fail_on_empty_changeset = false`, and
  `parameter_overrides` = `Stage`, `Region=eu-west-1`, and
  **`GovernanceProjectionTableName=governance_projection` for BOTH envs** (verified 0.1: the
  live `pretokengen-data` test stack reads the prod projection table by design — NOT
  `test_governance_projection`, which is the local/Docker table only). Header comment
  records the `nonprofit-deploy` data account (`506221081911`), the OIDC role, the
  distinct-stack rationale, and "no secrets" (the only Cognito identifiers here are the
  PUBLIC `CognitoAccountId` /
  `CognitoUserPoolId` for the invoke permission — task 1.2; pretokengen has no API
  authorizer). _(R1.1–R1.4, R1.6; D1/D2)_
- [x] **1.2 Add the Cognito invoke permission to the template (the flow maintains it).**
  In `sam/pretokengen/template.yaml`: add two PUBLIC parameters `CognitoAccountId`
  (`344561557829` — the personal/identity account, SAME for both envs) and
  `CognitoUserPoolId` (prod `eu-west-1_Hdp40eWmu` = Pool A; test `eu-west-1_xyrlzfqbl` =
  `myAdmin-test`), and an `AWS::Lambda::Permission` resource
  `PreTokenGenCognitoInvokePermission` (`Action: lambda:InvokeFunction`,
  `FunctionName: !Ref PreTokenGenFunction`, `Principal: cognito-idp.amazonaws.com`,
  `SourceArn: !Sub arn:aws:cognito-idp:${Region}:${CognitoAccountId}:userpool/${CognitoUserPoolId}`).
  Supply the two new params in each `samconfig.toml` env's `parameter_overrides` (task 1.1).
  This grants the SAME access as the CE.5 hand command — no new access. _(R5.1, R7.2; D5a)_
- [x] **1.3 Add the footgun comment block** to `sam/pretokengen/template.yaml` (DONE: placed
  in the `Stage` parameter Description + the samconfig header + the invoke-permission
  comment; `sam validate --lint` passes). `Stage` names the
  function/layer only, NOT the CloudFormation stack; the stack is pinned per env in
  samconfig; never deploy two stages into one stack. No resource/behavior change. _(R3.2,
  R3.3; D4, R7.1)_
- [x] **1.4 (dt) [H] Changeset review (P2).** DONE 2026-09-23. `sam build` (Build Succeeded)
  then `sam deploy --config-env prod --no-execute-changeset` (account strip +
  export-role-creds; identity verified `506221081911`). Changeset created (not executed),
  inspected, then DELETED (stack left clean). **Changeset contents (4 changes):**
  1. `Add` `AWS::Lambda::Permission PreTokenGenCognitoInvokePermission` — the intended D5a
     change. ✓
  2. `Add` new `AWS::Lambda::LayerVersion` + `Remove` old one — **expected SAM behavior**,
     NOT a spec-driven change: the layer's logical id carries a content hash, and any
     `sam build` re-stages the layer → new hash → CFN publishes a new version and retires
     the old logical resource (`RetentionPolicy: Retain` keeps the physical old version).
     Same vendored closure + pinned deps; no code/behavior change.
  3. `Modify` `AWS::Lambda::Function PreTokenGenFunction`, `Replacement: False` — in-place
     update to point at the new layer version. No replacement, no downtime.
  So it is NOT the pure "permission-only" changeset the task originally predicted — the
  layer add/remove + function-modify is the unavoidable consequence of rebuilding the layer
  (it happens on ANY redeploy, for members too). The only NEW resource is the permission;
  nothing is replaced or deleted destructively (layer is Retain). Corrected P2/R7 wording +
  the 1.5a/5.2 reconciliation split accordingly. _(R1.5, R7.2, R7.3; P1, P2)_
- [x] **1.5a (dt) [H] Investigate the pre-existing CE.5 permission (R7.2 / D5).** DONE
  2026-09-23 (`lambda get-policy pretokengen-prod`): the live function has ONE hand-added
  statement, **Sid `cognito-poolA-pretokengen`** (Principal `cognito-idp.amazonaws.com`,
  `lambda:InvokeFunction`, SourceArn Pool A `eu-west-1_Hdp40eWmu` in `344561557829`) — the
  SAME grant the template's `PreTokenGenCognitoInvokePermission` creates, but under a
  DIFFERENT (CFN-generated) Sid. CONCLUSION: the two **coexist** on execute (no "already
  exists" conflict — the 1.4 changeset showed a clean `Add`, not a failure), so the
  coexist-then-remove path holds and the `cloudformation import` fallback is NOT needed.
  The actual removal is a POST-DEPLOY step — see task **5.2** in Phase 5. _(R7.2; D5)_

## Phase 2 — CI workflow (OIDC, no secrets)

- [x] **2.1 Add `.github/workflows/deploy-sam-pretokengen.yml`** DONE 2026-09-23 — cloned
  `deploy-sam-members.yml` and retargeted per design D3: name "Deploy SAM PreTokenGen";
  triggers `push` to `main` on `sam/pretokengen/**`, `sam/shared/**`, and the workflow
  file, plus `workflow_dispatch`; `permissions: id-token: write, contents: read`;
  `concurrency: sam-pretokengen-deploy`; steps checkout → setup-python 3.11 → setup-sam →
  `configure-aws-credentials` assuming
  `arn:aws:iam::506221081911:role/NonprofitDeployRole` in `eu-west-1` (NO secrets) →
  `sam build` → `sam deploy --config-env prod --no-confirm-changeset
  --no-fail-on-empty-changeset`, both with `working-directory: sam/pretokengen`. _(R2.1–R2.5;
  D3; P1, P5)_
- [x] **2.2 [H] Confirm the OIDC trust covers this workflow (R2.6).** DONE + PASS 2026-09-23.
  `iam get-role NonprofitDeployRole` trust policy: the GitHub-OIDC statement
  (`sts:AssumeRoleWithWebIdentity`, provider `token.actions.githubusercontent.com`, aud
  `sts.amazonaws.com`) has a `StringLike` `sub` condition allowing **`repo:PeterGeers/myAdmin:*`**
  (and `repo:PeterGeers/h-dcn:*`). The `:*` wildcard is REPO-scoped, not per-workflow, so it
  already matches `repo:PeterGeers/myAdmin:ref:refs/heads/main` for the new workflow —
  **no IAM change needed.** No gated prerequisite remains. _(R2.6; D3)_

## Phase 3 — Cognito wiring: the flow owns the permission; only the trigger is manual (R5)

Note the split (D5): the **invoke permission** is now maintained by the SAM template
(tasks 1.2/1.4/1.5a, orphan removed post-deploy in 5.2) — NOT a manual step. Phase 3 covers
only the piece the flow cannot reach (the Pool A trigger) plus the survives-redeploy check.

- [x] **3.1 Document the ONE remaining manual step (the Pool A trigger) as an `[H]` runbook**
  DONE 2026-09-23 — wrote `sam/pretokengen/DEPLOY.md`: the two-account split table; the Pool A
  (and myAdmin-test) Pre-Token-Generation **trigger attach** via `cognito-idp
  update-user-pool --lambda-config` (V2_0, exact ARNs, `personal` profile, account strip) +
  its rollback (`--lambda-config '{}'`); and the post-deploy wiring check. States clearly the
  invoke *permission* is template-owned (NOT in the runbook; do not re-run `add-permission`),
  and the hand statement `cognito-poolA-pretokengen` is removed post-deploy (task 5.2).
  _(R5.2; D5b)_
- [x] **3.2a (dt) Validate the wiring-check commands + capture baseline (R5.3).** DONE
  2026-09-23. The check commands (in `DEPLOY.md`) were run against the current live state:
  `describe-user-pool eu-west-1_Hdp40eWmu` → `LambdaConfig.PreTokenGenerationConfig
  {LambdaVersion=V2_0, LambdaArn=...pretokengen-prod}` (trigger live from CE.5); invoke
  permission present (Phase 1: Sid `cognito-poolA-pretokengen`). Baseline established; the
  commands work. _(R5.3; D5, P6)_
- [ ] **3.2b [H] Post-deploy wiring check — POST-DEPLOY ONLY (R5.3 / P6).** GATED: run AFTER
  the first real deploy + task 5.2. Re-run the two `DEPLOY.md` checks and confirm (i) the
  Pool A trigger is UNCHANGED (`PreTokenGenerationConfig` still points at `pretokengen-prod`
  — the deploy must not have disturbed the external trigger), and (ii) the invoke statement
  is now the CFN-managed one (orphan `cognito-poolA-pretokengen` removed). _(R5.3; D5, P6)_

## Phase 4 — Manual fallback + docs (R6)

- [x] **4.1 Document the account-correct manual deploy** DONE 2026-09-23 — appended a
  "Deploying the Lambda" section to `sam/pretokengen/DEPLOY.md`: (preferred) CI via
  `workflow_dispatch`/merge; (fallback) the ONE command per env
  (`sam deploy --config-env prod` / `--config-env test`), preceded by the
  `41-shell-environment` credential strip + export-role-creds and the `sts get-caller-identity`
  sanity-check that MUST print `506221081911` before any mutating deploy. No inline params, no
  `--stack-name`; `--no-execute-changeset` preview noted. _(R6.1–R6.3; D5b)_
- [x] **4.2 Cross-link from steering/rollout.** DONE 2026-09-23 — added a pointer in the s5d
  rollout plan (CE.4a note: "RESOLVED by s5e … runbook `sam/pretokengen/DEPLOY.md`; use
  `--config-env prod`, not inline params") AND a References-section line in steering
  `35-sam-module-architecture-sam.md` (codified `sam deploy --config-env <env>` for every SAM
  app; points at both apps' samconfig + workflow + DEPLOY.md). _(R6.3)_

## Phase 5 — Verification (evidence-based, IaC-only)

- [ ] **5.1 (dt) Confirm change-set scope (R7.1).** The diff for s5e contains ONLY:
  `sam/pretokengen/samconfig.toml`, `.github/workflows/deploy-sam-pretokengen.yml`,
  `sam/pretokengen/DEPLOY.md`, doc pointers, and template edits limited to (a) the footgun
  comment and (b) the single `PreTokenGenCognitoInvokePermission` resource + its two PUBLIC
  params (tasks 1.2/1.3). No `.py`, no table, no pool config, no other resource. _(R7.1)_
- [ ] **5.2 [H] Remove the orphaned CE.5 statement (was 1.5b; R7.3 / D5 / P6).** GATED: run
  ONLY AFTER the first real (executed) deploy has published the CFN-managed permission —
  removing it earlier would leave Pool A logins with NO invoke permission (breaks token
  enrichment). Prereq investigation done in **1.5a** (orphan Sid = `cognito-poolA-pretokengen`).
  So the template is sole owner:
  `... aws lambda remove-permission --function-name pretokengen-prod --statement-id
  cognito-poolA-pretokengen --region eu-west-1` (account strip). Verify with `get-policy`:
  only the CFN-managed statement remains. _(R7.3; D5, P6)_
- [ ] **5.3 [H] Final changeset proof (P2/R7.3).** After the deploy + the 5.2 removal, re-run
  `sam deploy --config-env prod --no-execute-changeset` (or read the merged workflow's next
  run) and confirm the changeset is **behavior-preserving** against `pretokengen-prod`: the
  invoke permission is CFN-owned (no duplicate hand statement), and the only remaining
  entries are the intrinsic layer re-hash (add new / remove old LayerVersion + in-place
  function modify — NOT a pure-empty changeset; see P2). No new/replaced/destroyed
  functional resource. _(R7.2, R7.3; P2)_
- [ ] **5.4 Update `myBacklog/backlog.md`.** Mark the "SAM deploys are ad-hoc" backlog item
  as addressed by this spec (link `s5e-codify-sam-deploys`); note ODx2 (auto test-deploy
  job) and ODx3 (fold the remaining Pool A trigger attach into Terraform) as any remaining
  follow-ups. _(spec bookkeeping)_

## Done criteria

- `sam/pretokengen` deploys via one reviewed command per env from committed config, on OIDC
  CI with no secrets, into distinct pinned stacks (P1, P3, P5).
- The codified prod deploy is a proven no-op against the live `pretokengen-prod` (P2, R7).
- Cross-account Cognito wiring and the account-correct manual fallback are documented and
  guarded; the Pool A trigger survives redeploy (P4, P6, R5, R6).
- `sam/members` parity confirmed as prod-only-by-design (R4).
- The s5d edge fix (#1) now has a stable, repeatable `sam/members` redeploy path to ship
  through.
