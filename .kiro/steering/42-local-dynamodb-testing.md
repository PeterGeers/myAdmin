---
inclusion: manual
---

# Local DynamoDB testing + long-running-process discipline

Scope: the tenant-governance projection (`s3-claims-and-projection`, design D3) and every
later phase that touches it (including the S5 module plane). Two rules that every phase
must follow.

## 1. Long-running processes go through `control_bash_process` (never foreground)

Any process that does not terminate quickly — `docker compose up`, `sam local
start-*` / `sam local invoke`, DynamoDB Local, build watchers, dev servers — MUST
be started with the `control_bash_process` tool (`action: start`, background), then
monitored with `get_process_output` and stopped with `action: stop`.

Do NOT launch them via foreground `execute_bash`: a foreground long-running command
blocks the session (and, on this WSL setup, an interactive pager can hijack the
terminal — see `41-shell-environment.md`). Short, terminating commands (seed scripts,
`docker compose config`, `pytest`, one-shot `docker compose stop`) are fine in
`execute_bash`.

Rule of thumb: if it "stays up until you stop it", it goes through
`control_bash_process`.

## 2. Local DynamoDB is the primary offline datastore for the projection

`docker-compose.yml` includes a `dynamodb-local` service (`amazon/dynamodb-local`,
`-sharedDb`) that comes up alongside MySQL + backend in one stack. This lets the
projection and its property/integration tests run fully offline. The cloud `test_` /
`-Test` tables are a fallback, not the primary local path.

Networking (mirrors the h-dcn `scripts/local/` reference):
- Named Docker network `myadmin-local`; the container has the network alias
  `dynamodb-local`, so in-network callers (backend, `sam local invoke
  --docker-network myadmin-local`) reach it at `http://dynamodb-local:8000`.
- Host port `8000` is published, so host-side seeding/tests use
  `http://localhost:8000`.
- Native WSL Docker only (not Docker Desktop).

### Fail-fast / no-dangerous-fallback

The projection's DynamoDB client lives in
`backend/src/services/dynamodb_client.py`. It enforces two guardrails:
- The endpoint override is used **only when `AWS_ENDPOINT_URL_DYNAMODB` is set**.
  Unset → boto3 resolves real AWS. There is **no** hardcoded `localhost` default and
  no silent fallback that could point projection work at production.
- `GOVERNANCE_PROJECTION_TABLE` and `AWS_REGION` are **required** — a missing/blank
  value raises `DynamoDBConfigError` rather than defaulting a table/region.

`docker-compose.yml` sets `AWS_ENDPOINT_URL_DYNAMODB=http://dynamodb-local:8000` on
the backend service; host scripts default to `http://localhost:8000`. In
production, leave `AWS_ENDPOINT_URL_DYNAMODB` unset.

### Typical local workflow

```bash
# 1. Start the stack (or just DynamoDB Local) in the BACKGROUND via
#    control_bash_process — NOT foreground execute_bash:
#      command: docker compose up            (whole stack)
#      command: docker compose up dynamodb-local   (just local DynamoDB)

# 2. Create + seed the projection table (short-lived, execute_bash is fine):
backend/.venv/bin/python scripts/local/seed-dynamodb-local.py --reset --with-fixtures

# 3. Run the projection tests against http://localhost:8000
#    (set AWS_ENDPOINT_URL_DYNAMODB + GOVERNANCE_PROJECTION_TABLE + AWS_REGION).

# 4. Between runs, drop just the table (idempotent):
backend/.venv/bin/python scripts/local/teardown-dynamodb-local.py

# 5. Bring the stack down via control_bash_process `stop`, then optionally:
#      docker compose stop dynamodb-local
```

Scripts:
- `scripts/local/seed-dynamodb-local.py` — creates the projection table
  (PK `tenant_id`, SK `sk` = `record_type#id`, PAY_PER_REQUEST) and optionally
  inserts synthetic fixtures (`--with-fixtures`). Table name from `--table` /
  `GOVERNANCE_PROJECTION_TABLE` (default `test_governance_projection`).
- `scripts/local/teardown-dynamodb-local.py` — drops just the projection table
  (idempotent). Bringing the container down is `docker compose stop dynamodb-local`
  / `docker compose down`.
