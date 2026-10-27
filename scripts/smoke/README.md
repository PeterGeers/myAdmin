# `scripts/smoke/` — deployed-stage smoke tests

Smoke tests that run against a **deployed** stack (real AWS), to cover what the local
test suites structurally cannot. Unlike the unit/E2E suites (`sam/tests/`, which run
against in-memory fakes or the local `dynamodb-local` emulator), these exercise behavior
that only real AWS can prove — chiefly **IAM enforcement**.

They follow the same house conventions as `scripts/test-environment/` and
`scripts/onboarding/`:

- **Robust paths (R4).** Find the repo root by walking up to a marker (`.git`/`.kiro`),
  then put repo root + `backend/src` on `sys.path` via
  `scripts/onboarding/_lib/paths.ensure_backend_src_on_path()`. No `../` counting.
- **Fail closed + non-destructive.** An identity check fails fast if the caller is not the
  expected account/role (steering 41 override-ranking trap). A write-touching smoke test
  targets a dedicated sentinel row (never real tenant data) and self-reverts, so it is safe
  to re-run.
- **No secrets.** Only PUBLIC identifiers (account id, stack/table names) appear in
  committed files — never passwords, client secrets, or AWS keys.

## Runners

| Runner | Purpose | Account / role | Safety |
| --- | --- | --- | --- |
| `members_config_update_item_grant_smoke.py` | **Spec 03 task 8.6.** Prove the Members Lambda execution role actually holds `dynamodb:UpdateItem` on the governance table (task 2.1, `template.yaml` Sid `MembersWriteGovernanceProjectionConfig`). Local DynamoDB does NOT enforce IAM, so the E2E suite passes regardless — this is the deployed-stage counterpart that catches a missing grant. | DATA account `506221081911` / `NonprofitDeployRole`, `eu-west-1`. Assumes the Members Lambda role to exercise the grant AS the Lambda. | Writes only a `__smoketest__` sentinel row and deletes it. Refuses any non-`test_` table unless explicitly overridden. Never touches a real tenant row or PROD. |

## Why this exists (the harness gap it closes)

Design `C5` ("Harness gaps the review flagged", R9/R11) of spec 03
(`.kiro/specs/Members/03 - config-fields-foolproof-crud/design.md`): local DynamoDB does
not enforce IAM, so a missing `dynamodb:UpdateItem` grant **passes** the whole E2E
invariant suite and only fails in real AWS at runtime. The `members_config_update_item_...`
smoke test exercises the grant against the deployed TEST stack so it is proven, not assumed.

## Usage

Run from the repo root (WSL), **after** a TEST deploy. Strip any lingering static keys +
endpoint override so the profile resolves the DATA account against real AWS (steering 41):

```bash
# 1. Deploy the new stack to TEST first (steering 43):
#    push the `test` branch (fires deploy-sam-members.yml), or:  sam deploy --config-env test

# 2. Confirm identity (must print 506221081911 / NonprofitDeployRole):
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  aws sts get-caller-identity --profile nonprofit-deploy --region eu-west-1 --output json

# 3. Run the smoke test:
env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
  backend/.venv/bin/python scripts/smoke/members_config_update_item_grant_smoke.py
```

Success is exit code 0 and a `SMOKE PASS:` line. A missing grant surfaces as an
`AccessDeniedException` on the `update_item` performed AS the Lambda role (exit 1) — the
exact failure local DynamoDB can never produce. See the script's `--help` and module
docstring for options (`--approach`, `--require-fresh-deploy`, `--table`, ...) and the full
rationale for assuming the Lambda role rather than writing as the deploy role.

## Tests

Pure helper logic (target guards, identity assertion, the update-expression plan, the
fresh-deploy cutoff, timestamp parsing) is unit-tested locally with no AWS:
`sam/tests/test_members_config_update_item_grant_smoke.py`
(`cd backend && source .venv/bin/activate && pytest ../sam/tests/test_members_config_update_item_grant_smoke.py -q`).
The AWS-touching path is NOT exercised by the unit test — it only runs against a deployed
stack via the runbook above.
