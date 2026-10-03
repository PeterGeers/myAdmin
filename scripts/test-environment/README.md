# `scripts/test-environment/` — Test_Environment operational tooling

Operational runners for the **test-environment** spec
(`.kiro/specs/Common/test-environment/first-draft/`). These are cross-cutting
environment operations (NOT tenant-onboarding — that lives in
`scripts/onboarding/`), so they get their own purpose-named folder per the
repo script-folder standard (`scripts/onboarding/README.md` → "Conventions").

All runners here follow the same conventions as the onboarding runners:

- **Robust paths (R4).** Find the repo root by walking up to a marker (`.git`/
  `.kiro`), then put repo root + `backend/src` on `sys.path` via
  `scripts/onboarding/_lib/paths.ensure_backend_src_on_path()`. No `../` counting.
- **Dry-run first.** The default run writes NOTHING; a real write needs explicit
  flags (see each runner). Runners are safe to re-run.
- **No secrets.** Only PUBLIC identifiers (Cognito pool ids) appear in committed
  files — never passwords, client secrets, or AWS keys.

## Runners

| Runner | Purpose | Writes to | Safety |
| --- | --- | --- | --- |
| `copy-prod-to-test.py` | **Copy_Utility** (Req 16). Copy PROD contents into TEST, one-directionally: a reference account's non-secret Cognito attributes (PROD Pool A → test pool), or a PROD DynamoDB table's items → its `test_`-prefixed table. | TEST only (test pool / `test_` tables) | Dry-run default; a real write needs BOTH `--apply` and `--i-understand-this-writes-test`. Refuses any write toward PROD or a non-`test_` destination. Never copies passwords/secrets. |
| `provision-test-account.py` | **Test_Account provisioning** (Req 17). Create/seed a test user in the test pool with a permanent password (no forced-change trap) and a chosen `custom:tenants`/`custom:role` shape. | TEST pool (identity account) | Dry-run default; `--apply` to write. Optional prod-mirror mode goes through the Copy_Utility, not as the default. |

## One-directional guarantee (Copy_Utility)

`copy-prod-to-test.py` is structurally one-directional (Req 16.4/16.5): the SOURCE
clients read PROD; the DESTINATION clients write TEST, and there is no code path
that writes toward PROD. Before any write it also asserts the destination is
demonstrably TEST (the `test_` table prefix / the test pool id) and that source ≠
destination — defense in depth. The paired test
(`sam/tests/test_copy_prod_to_test.py`) uses in-memory fakes that FAIL the test if
any write targets PROD, so the guarantee is proven, not just inspected.

## Usage

Run from the repo root (WSL). Both runners print `--help`. Examples:

```bash
# Copy_Utility — preview (writes nothing):
backend/.venv/bin/python scripts/test-environment/copy-prod-to-test.py dynamodb \
    --source-table governance_projection

# Copy_Utility — actually write TEST (data account):
AWS_PROFILE=nonprofit-deploy AWS_REGION=eu-west-1 \
    backend/.venv/bin/python scripts/test-environment/copy-prod-to-test.py dynamodb \
    --source-table governance_projection --apply --i-understand-this-writes-test
```
