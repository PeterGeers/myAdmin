# scripts/local — local DynamoDB tooling (S3 projection)

Offline tooling for the S3 tenant-governance projection
(`.kiro/specs/multi-tenant/s3-claims-and-projection`, design D3). Lets the
projection and its property/integration tests run against a **local** DynamoDB
instead of the cloud `test_` / `-Test` tables.

See `.kiro/steering/local-dynamodb-testing.md` for the full workflow and the
long-running-process discipline (start `docker compose up` via the background
process tooling, never foreground).

## Container

`dynamodb-local` is defined in the repo-root `docker-compose.yml`
(`amazon/dynamodb-local`, `-sharedDb`), on the `myadmin-local` network with alias
`dynamodb-local:8000` (in-network) and host port `8000`. Native WSL Docker.

Start it (background) alongside MySQL + backend:

```bash
docker compose up                 # whole stack
docker compose up dynamodb-local  # just local DynamoDB
```

## Scripts

```bash
# Create + seed the projection table (PK tenant_id, SK sk, PAY_PER_REQUEST)
backend/.venv/bin/python scripts/local/seed-dynamodb-local.py --reset --with-fixtures

# Drop just the projection table (idempotent)
backend/.venv/bin/python scripts/local/teardown-dynamodb-local.py
```

Both accept `--endpoint-url` (default `http://localhost:8000`), `--region`
(default `eu-west-1`), and `--table` (default `test_governance_projection`, or the
`GOVERNANCE_PROJECTION_TABLE` env var).

## Env vars (fail-fast, S3 R4.1)

- `GOVERNANCE_PROJECTION_TABLE` — required; the client throws if missing/blank.
- `AWS_ENDPOINT_URL_DYNAMODB` — set → local DynamoDB; unset → real AWS. No default.

The projection client is `backend/src/services/dynamodb_client.py`.
