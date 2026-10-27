"""
E2E invariant-harness fixtures for `config#fields` CRUD (spec 03, Phase 1 / task 1.1).

This is the RED scaffold the Phase-1 invariant tests (1.2–1.4) build on: it stands up the
REAL `h-dcn` `config#fields` row inside a LOCAL DynamoDB table so a read → Change-Op → read
can be proven to change only the named target (R9, design C5). It targets the
`amazon/dynamodb-local` container described in steering `42-local-dynamodb-testing.md` — the
DEV-only offline emulator, NOT the deployed TEST stack.

Two non-negotiables this module honours:

1. **Skip cleanly when the container/endpoint is absent.** Ordinary unit runs
   (`sam/pytest.ini`) have no local DynamoDB. Every fixture here either is gated behind the
   `local_dynamodb_endpoint` fixture (which `pytest.skip`s when `AWS_ENDPOINT_URL_DYNAMODB` is
   unset) or behind a reachability probe that `pytest.skip`s when the endpoint does not answer.
   A missing container must SKIP, never ERROR — so running `python -m pytest sam/tests/e2e -q`
   without the stack up does not redden a unit run.

2. **Seed from the COMMITTED real fixture**, `sam/tests/fixtures/hdcn_config_fields_overlay.json`
   (captured from `test_governance_projection`) — never a hand-built shape. Spec 11's lesson:
   *trust runs, not inference* (steering 39). The seed reuses the project's seed-script pattern
   (`scripts/local/seed-dynamodb-local.py`): dummy creds, PAY_PER_REQUEST, PK `tenant_id` / SK
   `sk`, idempotent create.

No product code is touched. Downstream invariant tests are EXPECTED red until Phase 2.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

# ─────────────────────────────────────────────────────────────────────────────────────
# Path bootstrap — mirror the sibling SAM tests so `services.projection_schema` (the single
# source for the PK/SK/version attribute names) and the `sam.*` packages import without a
# package install. `sam/tests/e2e/` is three levels under the repo root.
# ─────────────────────────────────────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema  # noqa: E402

# The committed real-data fixture (NOT hand-built) — steering 39 "prove against real data".
_FIXTURE_PATH = os.path.join(
    _REPO_ROOT, "sam", "tests", "fixtures", "hdcn_config_fields_overlay.json"
)

# Default table name for the E2E harness. Kept distinct from the unit-seed default
# (`test_governance_projection`) so an E2E run can create/drop its own table without colliding
# with a developer's seeded unit table in the same container. Overridable via env so CI /
# docker-compose can pin it.
_DEFAULT_E2E_TABLE = os.environ.get(
    "GOVERNANCE_PROJECTION_TABLE", "e2e_config_fields_projection"
)

# Host-side default endpoint (the container publishes host port 8000 — steering 42). Only used
# as the probe target WHEN AWS_ENDPOINT_URL_DYNAMODB is set; an unset var means "no local
# endpoint" and skips.
_DEFAULT_ENDPOINT = "http://localhost:8000"
_DEFAULT_REGION = os.environ.get("AWS_REGION", "eu-west-1")


def pytest_configure(config):
    """Register the `e2e` marker locally so these tests don't emit an unknown-marker warning.

    `sam/pytest.ini` only declares `unit`; this layer is the first `e2e` user. Registering here
    keeps the marker self-contained to the E2E package.
    """
    config.addinivalue_line(
        "markers",
        "e2e: end-to-end test against local DynamoDB (steering 34/42); skips when the "
        "container/endpoint is absent",
    )


# ─────────────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def real_hdcn_overlay() -> dict:
    """The committed real `h-dcn` `config#fields` overlay (fields / overrides / groups).

    This is a pure file read — available even without the container — so invariant tests can
    reference the expected shape for assertions regardless of skip state.
    """
    with open(_FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def local_dynamodb_endpoint() -> str:
    """Resolve the local-DynamoDB endpoint, or SKIP when it is absent.

    Gate 1 — configuration: `AWS_ENDPOINT_URL_DYNAMODB` must be set. Per steering 42 the
    projection client uses the override ONLY when this var is set (no hardcoded localhost
    default, no silent fallback to real AWS). An unset var means "no local emulator" → skip,
    so a plain unit run is unaffected.

    Gate 2 — reachability: the endpoint must actually answer. If boto3 isn't installed or the
    container isn't up, we skip rather than error (a missing dev container is not a test
    failure).
    """
    endpoint = os.environ.get("AWS_ENDPOINT_URL_DYNAMODB")
    if not endpoint:
        pytest.skip(
            "local DynamoDB not configured (AWS_ENDPOINT_URL_DYNAMODB unset) — skipping E2E; "
            "start the dynamodb-local container and set the endpoint to run the invariant "
            "harness (steering 42)"
        )

    try:
        import boto3  # noqa: F401
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:  # pragma: no cover - env without boto3 simply skips
        pytest.skip("boto3 not available — skipping local-DynamoDB E2E")

    # Probe: a cheap list_tables confirms the emulator is actually reachable. A connection
    # error (container down) → skip; it is not a defect in the code under test.
    try:
        client = _dynamodb_client(endpoint, _DEFAULT_REGION)
        client.list_tables()
    except (BotoCoreError, ClientError, OSError) as exc:
        pytest.skip(
            f"local DynamoDB endpoint {endpoint} is not reachable ({type(exc).__name__}) — "
            "skipping E2E; is the dynamodb-local container running?"
        )
    return endpoint


@pytest.fixture
def seeded_config_fields_table(local_dynamodb_endpoint, real_hdcn_overlay):
    """Create (idempotent, --reset style) the E2E projection table and seed the real h-dcn row.

    Reuses the seed-script pattern from `scripts/local/seed-dynamodb-local.py`: dummy creds,
    PAY_PER_REQUEST, PK `tenant_id` / SK `sk`. The seeded item mirrors
    `test_field_config_realdata_roundtrip.py`'s row shape (fields / overrides / functional_groups
    + a `version`) so the invariant engine reads exactly what production resolves.

    Yields a dict describing the seeded resource so invariant tests can build a reader/writer:
        {"table": <boto3 Table>, "table_name": str, "endpoint": str,
         "region": str, "tenant_id": str}

    The table is DROPPED on teardown (mirrors teardown-dynamodb-local.py) so each test gets a
    clean row and nothing lingers in the shared container.
    """
    import boto3  # already confirmed importable by local_dynamodb_endpoint
    from botocore.exceptions import ClientError

    endpoint = local_dynamodb_endpoint
    region = _DEFAULT_REGION
    table_name = _DEFAULT_E2E_TABLE

    dynamodb = boto3.resource(
        "dynamodb",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id="local",
        aws_secret_access_key="local",
        aws_session_token="local",
    )
    client = dynamodb.meta.client

    # Reset: drop a stale table from a previous run so the seed is deterministic.
    _drop_table_if_present(dynamodb, client, table_name)
    _create_projection_table(dynamodb, client, table_name)

    tenant_id = real_hdcn_overlay["tenant_id"]
    table = dynamodb.Table(table_name)
    table.put_item(
        Item={
            schema.PARTITION_KEY_ATTR: tenant_id,
            schema.SORT_KEY_ATTR: schema.build_sort_key(
                schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS
            ),
            "fields": real_hdcn_overlay["fields"],
            "overrides": real_hdcn_overlay["overrides"],
            "functional_groups": real_hdcn_overlay["functional_groups"],
            schema.VERSION_ATTR: 1,
        }
    )

    try:
        yield {
            "table": table,
            "table_name": table_name,
            "endpoint": endpoint,
            "region": region,
            "tenant_id": tenant_id,
        }
    finally:
        # Idempotent drop — leave the container running, just clear our table (teardown pattern).
        try:
            _drop_table_if_present(dynamodb, client, table_name)
        except ClientError:  # pragma: no cover - best-effort cleanup
            pass


# ─────────────────────────────────────────────────────────────────────────────────────
# Helpers (seed-script pattern — kept local so the harness has no runtime dep on scripts/)
# ─────────────────────────────────────────────────────────────────────────────────────
def _dynamodb_client(endpoint_url: str, region: str):
    """A low-level boto3 DynamoDB client at the local endpoint with dummy creds.

    Dummy credentials let botocore sign; local DynamoDB ignores the signature. This never
    reaches real AWS (steering 42 fail-fast: endpoint override used only when explicitly set).
    """
    import boto3

    return boto3.client(
        "dynamodb",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id="local",
        aws_secret_access_key="local",
        aws_session_token="local",
    )


def _table_exists(client, name: str) -> bool:
    from botocore.exceptions import ClientError

    try:
        client.describe_table(TableName=name)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceNotFoundException":
            return False
        raise


def _create_projection_table(dynamodb, client, name: str) -> None:
    """Create the projection table with the design's key schema (PK tenant_id / SK sk)."""
    dynamodb.create_table(
        TableName=name,
        KeySchema=[
            {"AttributeName": schema.PARTITION_KEY_ATTR, "KeyType": "HASH"},
            {"AttributeName": schema.SORT_KEY_ATTR, "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": schema.PARTITION_KEY_ATTR, "AttributeType": "S"},
            {"AttributeName": schema.SORT_KEY_ATTR, "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=name)


def _drop_table_if_present(dynamodb, client, name: str) -> None:
    """Drop the table if it exists (idempotent — mirrors teardown-dynamodb-local.py)."""
    if _table_exists(client, name):
        dynamodb.Table(name).delete()
        client.get_waiter("table_not_exists").wait(TableName=name)
