# `env-vars.local.json` — `sam local` runtime env for the Members app (S5b task 1.3)

This is the `--env-vars` JSON file that `sam local start-api` / `sam local invoke`
inject into the `MembersFunction` at LOCAL run time. It supplies the values the
template deliberately does NOT default (fail-fast discipline, R6.2 — see
`template.yaml`), plus the LOCAL-ONLY DynamoDB endpoint override.

## Format

SAM's `--env-vars` format is keyed by the **function logical id** (`MembersFunction`
in `template.yaml`). Each key under it becomes a runtime environment variable for
that function only.

```json
{
  "MembersFunction": {
    "MEMBERS_TABLE": "sam-members-local",
    "GOVERNANCE_PROJECTION_TABLE": "test_governance_projection",
    "AWS_ENDPOINT_URL_DYNAMODB": "http://dynamodb-local:8000",
    "AWS_REGION": "eu-west-1"
  }
}
```

- `MEMBERS_TABLE=sam-members-local` — the local module-plane Members table
  (SAM-plane `sam-` prefix, `-local` env suffix).
- `GOVERNANCE_PROJECTION_TABLE=test_governance_projection` — the local governance
  projection table. This is the actual local convention (`test_` prefix) used by
  `scripts/local/seed-dynamodb-local.py` / `teardown-dynamodb-local.py`
  (`DEFAULT_TABLE`) and `42-local-dynamodb-testing.md`. The env value carries its
  own prefix; the fail-fast client
  (`backend/src/services/dynamodb_client.py` / `projection_schema.resolve_projection_table_name`)
  never synthesizes one.
- `AWS_ENDPOINT_URL_DYNAMODB=http://dynamodb-local:8000` — **LOCAL-ONLY**. The
  Lambda runs INSIDE the `myadmin-local` docker network (see below), so it reaches
  DynamoDB Local by its in-network alias `dynamodb-local:8000`, NOT `localhost`.
  boto3 only overrides the endpoint when this var is set; leave it UNSET in prod.
- `AWS_REGION=eu-west-1` — supplied locally because `sam local` does not auto-inject
  the Lambda-reserved `AWS_REGION` the way the real runtime does; the fail-fast
  client requires it.

## Usage

Run from `sam/members` (after `sam build`), on the shared docker network so the
`dynamodb-local:8000` endpoint resolves:

```bash
cd sam/members && sam local start-api \
  --docker-network myadmin-local \
  --env-vars env-vars.local.json
```

`sam local start-api` serves the API on `http://127.0.0.1:3000` — the value the
SPA's `VITE_MEMBERS_API_BASE_URL` (in `frontend/.env.local`) points at.

## Committable — no secrets

This file holds only local, non-secret table names and endpoints, so it is safe to
commit (it is not a `.env` file, so the root `.gitignore` `.env.*` rule does not
match it). Never add credentials here.
