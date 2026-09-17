"""DynamoDB client factory for the S3 tenant-governance projection.

S3 (`s3-claims-and-projection`) builds a one-directional MySQL->DynamoDB
projection (design.md D3). This module is the single place the projection's
DynamoDB client is constructed. It exists so the fail-fast / no-dangerous-
fallback discipline (requirements R4.1) is enforced in *one* place rather than
scattered across every caller.

Two independent guardrails (R4.1):

1. **Endpoint override only when explicitly set.** The client points at a local
   DynamoDB (the Phase 0 / T0 `dynamodb-local` container) **only when
   ``AWS_ENDPOINT_URL_DYNAMODB`` is set**. When it is unset, boto3 resolves the
   real AWS endpoint as normal. There is no hardcoded ``http://localhost:8000``
   default that could accidentally be shipped, and no silent fallback that could
   point projection work at production. The switch is the presence of the env
   var, nothing else.

2. **Required config throws, never defaults.** The projection table name and
   region are resolved via :func:`require_env`, which raises
   :class:`DynamoDBConfigError` on a missing/blank value. A missing table var is
   a misconfiguration, never a silently-defaulted table name that could read or
   clobber the wrong table.

Boto3 itself already honours ``AWS_ENDPOINT_URL_DYNAMODB`` when resolving
endpoints, but relying on that alone would still let a *missing* var fall
through to real AWS with no signal. Passing the endpoint explicitly (only when
present) plus fail-fast on the table/region keeps the two concerns separate and
auditable.
"""

from __future__ import annotations

import os

import boto3

# The projection table name env var (design.md D3 / R5.4). The value carries the
# environment prefix itself (e.g. ``test_governance_projection`` in test/dev),
# so this module does not synthesize a prefix — it just refuses to guess a name.
PROJECTION_TABLE_ENV_VAR = "GOVERNANCE_PROJECTION_TABLE"

# The endpoint-override env var. When set (and only when set), the DynamoDB
# client talks to that endpoint instead of real AWS. This is the *sole* trigger
# for local/offline DynamoDB — there is no other default.
ENDPOINT_URL_ENV_VAR = "AWS_ENDPOINT_URL_DYNAMODB"

# Region env var. boto3 needs a region even for DynamoDB Local; we require it
# explicitly rather than defaulting so misconfiguration fails loudly.
REGION_ENV_VAR = "AWS_REGION"


class DynamoDBConfigError(RuntimeError):
    """A required DynamoDB projection env var is missing or blank.

    Raised instead of substituting a default, so nothing can silently point the
    projection at the wrong table or at production (R4.1, no dangerous
    fallback).
    """


def require_env(name: str) -> str:
    """Return a required env var's value, or raise if missing/blank.

    No default is ever substituted (no-dangerous-fallbacks guardrail, R4.1).

    Args:
        name: Environment variable name.

    Returns:
        The stripped, non-empty value.

    Raises:
        DynamoDBConfigError: The variable is unset or blank.
    """
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        raise DynamoDBConfigError(
            f"Required DynamoDB projection env var '{name}' is missing or blank. "
            f"There is no default fallback (S3 R4.1): a missing table/region var "
            f"must fail loudly rather than silently point at the wrong table or "
            f"at production."
        )
    return value.strip()


def get_endpoint_url() -> str | None:
    """Return the DynamoDB endpoint override, or ``None`` when unset.

    The override is used **only when ``AWS_ENDPOINT_URL_DYNAMODB`` is set** — the
    single switch that points the client at the local ``dynamodb-local``
    container (T0). When unset, this returns ``None`` and boto3 resolves the
    real AWS endpoint. A blank value is treated as unset.

    Returns:
        The endpoint URL string, or ``None`` if not configured.
    """
    value = os.environ.get(ENDPOINT_URL_ENV_VAR)
    if value is None or value.strip() == "":
        return None
    return value.strip()


def get_dynamodb_resource(*, region: str | None = None):
    """Build a boto3 DynamoDB *resource* for the projection.

    Points at the local ``dynamodb-local`` endpoint only when
    ``AWS_ENDPOINT_URL_DYNAMODB`` is set; otherwise talks to real AWS via the
    normal boto3 resolution. The region is required (via env) unless passed
    explicitly.

    Args:
        region: Optional region override. If omitted, ``AWS_REGION`` is required.

    Returns:
        A ``boto3.resources.factory.dynamodb.ServiceResource``.

    Raises:
        DynamoDBConfigError: The region is neither passed nor set in the env.
    """
    resolved_region = region or require_env(REGION_ENV_VAR)
    endpoint_url = get_endpoint_url()

    kwargs = {"region_name": resolved_region}
    if endpoint_url is not None:
        # Local / offline path: talk to the dynamodb-local container. Dummy
        # credentials keep boto3 happy against the emulator; when unset boto3
        # uses the ambient AWS credential chain against real AWS. These dummy
        # values are applied ONLY when an endpoint override is present, so they
        # can never leak onto a real-AWS call.
        kwargs["endpoint_url"] = endpoint_url
        kwargs.setdefault(
            "aws_access_key_id", os.environ.get("AWS_ACCESS_KEY_ID", "local")
        )
        kwargs.setdefault(
            "aws_secret_access_key",
            os.environ.get("AWS_SECRET_ACCESS_KEY", "local"),
        )

    return boto3.resource("dynamodb", **kwargs)


def get_projection_table(*, region: str | None = None):
    """Return the boto3 Table handle for the governance projection table.

    Resolves the table name from ``GOVERNANCE_PROJECTION_TABLE`` (fail-fast) and
    builds the resource via :func:`get_dynamodb_resource` (local endpoint only
    when set). This is the entry point the projection sync / read side should
    use.

    Args:
        region: Optional region override; otherwise ``AWS_REGION`` is required.

    Returns:
        A ``boto3`` DynamoDB Table resource bound to the projection table.

    Raises:
        DynamoDBConfigError: A required env var (table name or region) is
            missing/blank.
    """
    table_name = require_env(PROJECTION_TABLE_ENV_VAR)
    resource = get_dynamodb_resource(region=region)
    return resource.Table(table_name)
