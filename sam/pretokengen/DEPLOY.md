# Deploying `sam/pretokengen` (PreTokenGen Lambda)

Runbook for the PreTokenGen Lambda deploy + the one cross-account step the deploy pipeline
cannot do. Companion to the s5e spec (`.kiro/specs/multi-tenant/s5e-codify-sam-deploys/`).

## The two-account split (read this first)

The full wiring spans **two AWS accounts**, and only some of it can be automated:

| Piece | Account | Owned by | How |
|---|---|---|---|
| Lambda + layer + projection-read IAM | **data** — `nonprofit-deploy` `506221081911` | the flow | `sam deploy` (CI or manual) |
| Cross-account **invoke permission** (Cognito → this Lambda) | **data** — `506221081911` | the flow | `sam deploy` — the template's `PreTokenGenCognitoInvokePermission` |
| Pre-Token-Generation **trigger** on the Cognito pool | **identity** — `personal` `344561557829` | **manual** | `cognito-idp update-user-pool` (this doc) |

The deploy pipeline authenticates only into the **data** account (`NonprofitDeployRole` via
OIDC). It has no credentials in the `personal` account, so **the pool trigger attach is the
one step it cannot perform** — that stays manual, below. Everything else is `sam deploy`.

> Do NOT hand-run `lambda add-permission` for the invoke permission any more — the SAM
> template now owns and re-asserts it on every deploy (s5e). The old CE.5 hand statement
> (`--statement-id cognito-poolA-pretokengen`) is removed once, post-deploy (spec task 5.2).

## Manual step: attach the Pre-Token-Generation trigger to a pool (identity account)

Run this in the **`personal`** account (where the pools live), NOT `nonprofit-deploy`. It is
a **once-only** action per pool — a Lambda redeploy does NOT touch it (the trigger is on the
pool, external to the CloudFormation stack).

`update-user-pool` REPLACES the entire `LambdaConfig` in one call, so set the FULL desired
config. Attach the V2 Pre-Token-Generation trigger pointing at the deployed function ARN:

```bash
# PROD → Pool A (eu-west-1_Hdp40eWmu), function pretokengen-prod
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  aws cognito-idp update-user-pool \
    --user-pool-id eu-west-1_Hdp40eWmu \
    --lambda-config '{"PreTokenGenerationConfig":{"LambdaVersion":"V2_0","LambdaArn":"arn:aws:lambda:eu-west-1:506221081911:function:pretokengen-prod"}}' \
    --profile personal --region eu-west-1
```

```bash
# TEST → myAdmin-test (eu-west-1_xyrlzfqbl), function pretokengen-test
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  aws cognito-idp update-user-pool \
    --user-pool-id eu-west-1_xyrlzfqbl \
    --lambda-config '{"PreTokenGenerationConfig":{"LambdaVersion":"V2_0","LambdaArn":"arn:aws:lambda:eu-west-1:506221081911:function:pretokengen-test"}}' \
    --profile personal --region eu-west-1
```

> `update-user-pool` is picky: if the pool has other settings that must persist, include them
> in the same call (it replaces the whole config, not just `LambdaConfig`). For Pool A the
> captured baseline was `LambdaConfig = {}` (no other triggers), so the call above is complete.

### Rollback (detach the trigger)

Restore the empty `LambdaConfig` (Pool A's captured baseline). Same one-call replace:

```bash
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  aws cognito-idp update-user-pool --user-pool-id eu-west-1_Hdp40eWmu \
    --lambda-config '{}' --profile personal --region eu-west-1
```

## Post-deploy wiring check (both halves)

After ANY `pretokengen-prod` deploy, confirm both halves are intact. A redeploy re-asserts
the invoke permission (template-owned) and NEVER drops the trigger (external to the stack).

```bash
# (1) DATA account: the CFN-managed invoke permission is present.
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ENDPOINT_URL \
  aws lambda get-policy --function-name pretokengen-prod \
    --profile nonprofit-deploy --region eu-west-1 --output json
# Expect: a statement with Principal cognito-idp.amazonaws.com, Action lambda:InvokeFunction,
# SourceArn ...userpool/eu-west-1_Hdp40eWmu. After spec task 5.2 the orphaned hand statement
# (Sid cognito-poolA-pretokengen) is gone — only the CFN-managed statement remains.

# (2) IDENTITY account: Pool A still carries the V2 trigger.
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  aws cognito-idp describe-user-pool --user-pool-id eu-west-1_Hdp40eWmu \
    --profile personal --region eu-west-1 \
    --query 'UserPool.LambdaConfig' --output json
# Expect: PreTokenGenerationConfig{LambdaVersion=V2_0, LambdaArn=...pretokengen-prod}.
```

End-to-end proof: a fresh login on the pool yields a token carrying `custom:entitlements`
(e.g. h-dcn `members:admin/export/read/write`) — see s5d CE.6.

## Deploying the Lambda

### Preferred: CI (no local creds, no `.env` trap)

Merging to `main` with changes under `sam/pretokengen/**` or `sam/shared/**` triggers
`.github/workflows/deploy-sam-pretokengen.yml`, which assumes `NonprofitDeployRole` via OIDC
and runs `sam build` + `sam deploy --config-env prod`. You can also run it on demand from the
Actions tab (`workflow_dispatch`). This is the recommended path — CI has clean, correct
credentials and cannot hit the `.env` account trap below.

### Manual fallback (account-correct)

Use only when CI can't. It is ONE reviewed command per env — all params come from
`samconfig.toml`, so there are NO inline `--parameter-overrides` and NO `--stack-name`.

The repo-root `.env` exports STATIC personal-account AWS keys that boto3/the CLI rank ABOVE
`AWS_PROFILE`, so a plain `AWS_PROFILE=nonprofit-deploy sam deploy` silently hits the WRONG
account (`personal` 344561557829) — see steering `41-shell-environment`. STRIP them and let
the role resolve:

```bash
cd /home/peter/projects/myAdmin
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_ENDPOINT_URL_DYNAMODB AWS_ENDPOINT_URL
eval "$(aws configure export-credentials --profile nonprofit-deploy --format env)"
unset AWS_PROFILE

# SANITY-CHECK identity FIRST — MUST print 506221081911 (NonprofitDeployRole), not 344561557829:
aws sts get-caller-identity --output json

# Then the one reviewed command (params come from samconfig.toml [prod]):
cd sam/pretokengen
sam build
sam deploy --config-env prod --no-confirm-changeset --no-fail-on-empty-changeset
# Test env (myAdmin-test pool, stack pretokengen-data): sam deploy --config-env test
```

> Preview first if unsure: add `--no-execute-changeset` to `sam deploy` to create (not apply)
> a changeset, inspect it, then delete it (`aws cloudformation delete-change-set`). The first
> real deploy adds the CFN-managed invoke permission; after it, run the one-time orphan
> cleanup (spec task 5.2) so only the template-owned statement remains.
