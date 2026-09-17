"""Canonical shape of the S3 governance projection table (design.md D3, R5.4).

S3 (`s3-claims-and-projection`) builds a one-directional MySQL->DynamoDB
projection. This module is the **single source of truth** for the projection
table's key shape so the sync (T16), the item builder (T12), the write-time
validator (T14), and the tenant-scoped read side (T19) all agree on one
definition instead of each re-deriving the keys.

Table shape (design.md D3 "DynamoDB table shape (tenant-scoped key design, R5.4)")::

    Table: {ENV_PREFIX}governance_projection      (test_ prefix in test/dev)
      PK  tenant_id            (== administration)   -- partition key = tenancy boundary
      SK  record_type#id       (e.g. "tenant", "module#members", "role#email#role")
      attrs: is_active, role, tenant fields, ...
      version: <source revision / updated-at>        -- monotonic per item

**SK attribute-name reconciliation.** The design describes the sort key
conceptually as ``record_type#id``. The physical table (created by the T0 seed
script ``scripts/local/seed-dynamodb-local.py``) stores that composite in an
attribute literally named ``sk``. This module makes ``sk`` the canonical SK
*attribute name* and treats ``record_type#id`` as the *value* stored under it,
so the code, the seed script, and any created table are all consistent. The
helpers below are the only place the ``record_type#id`` composite is assembled
or parsed, so the "#"-join convention lives in exactly one spot.

**Tenancy boundary (R5.4).** The partition key ``tenant_id`` equals the
``administration`` value — the tenancy boundary used everywhere else in the
platform. Making the tenant the partition key means a query cannot address more
than one tenant's partition, so cross-tenant reads are structurally
unaddressable (correctness). IAM ``dynamodb:LeadingKeys`` scoping (see
:data:`LEADING_KEYS_IAM_POLICY_PLAN`) restricts a caller's *credentials* to
their own partition as defense-in-depth, matching the S1 Scope seam.

**Table-name resolution + fail-fast (R4.1).** The table name is not synthesized
here; it is resolved from the ``GOVERNANCE_PROJECTION_TABLE`` env var (which
already carries its own ``test_`` prefix in test/dev) via the T0 fail-fast
client (:mod:`services.dynamodb_client`). A missing/blank var raises rather than
defaulting, so nothing can silently point at the wrong table or at production.
"""

from __future__ import annotations

import json

from services.dynamodb_client import (
    PROJECTION_TABLE_ENV_VAR,
    get_projection_table,
    require_env,
)

# --- Key schema attribute names (canonical) --------------------------------

#: Partition-key attribute name. Its value equals the tenant's ``administration``
#: — the tenancy boundary (R5.4). This is what makes cross-tenant reads
#: unaddressable.
PARTITION_KEY_ATTR = "tenant_id"

#: Sort-key attribute name. Reconciled with the T0 seed script: the physical
#: attribute is named ``sk`` and holds the ``record_type#id`` composite value.
SORT_KEY_ATTR = "sk"

#: Version attribute name — a monotonic per-item value (source revision or
#: ``updated_at``) used for the conditional/idempotent write (R5.6) and read-side
#: staleness detection (R5.8).
VERSION_ATTR = "version"

#: Separator that joins ``record_type`` and ``id`` into the sort-key value.
SORT_KEY_SEPARATOR = "#"

#: Record-type tokens the sort key uses (the leading segment of the SK value).
#: ``tenant`` rows have no id segment; ``module``/``role`` rows do.
RECORD_TYPE_TENANT = "tenant"
RECORD_TYPE_MODULE = "module"
RECORD_TYPE_ROLE = "role"


# --- Sort-key composition / parsing ----------------------------------------


def build_sort_key(record_type: str, *id_parts: str) -> str:
    """Build a projection sort-key value from a record type and id part(s).

    The sort key is ``record_type`` optionally followed by ``#``-joined id
    segments, e.g.::

        build_sort_key("tenant")                       -> "tenant"
        build_sort_key("module", "members")            -> "module#members"
        build_sort_key("role", "a@b", "Members_CRUD")  -> "role#a@b#Members_CRUD"

    This is the *only* place the "#"-join convention is applied, so the builder
    (T12) and read side (T19) cannot diverge on the format.

    Args:
        record_type: The leading segment (e.g. ``tenant``/``module``/``role``).
        *id_parts: Zero or more id segments appended after the record type.

    Returns:
        The composite sort-key string stored under :data:`SORT_KEY_ATTR`.

    Raises:
        ValueError: ``record_type`` is empty, or any segment itself contains the
            separator (which would make the key ambiguous to parse).
    """
    if not record_type:
        raise ValueError("record_type must be a non-empty string")

    segments = (record_type, *id_parts)
    for segment in segments:
        if segment is None or segment == "":
            raise ValueError(f"sort-key segments must be non-empty: {segments!r}")
        if SORT_KEY_SEPARATOR in segment:
            raise ValueError(
                f"sort-key segment {segment!r} must not contain the separator "
                f"{SORT_KEY_SEPARATOR!r} (it would make the key ambiguous)"
            )
    return SORT_KEY_SEPARATOR.join(segments)


def split_sort_key(sort_key_value: str) -> tuple[str, tuple[str, ...]]:
    """Split a sort-key value back into its record type and id segments.

    Inverse of :func:`build_sort_key`::

        split_sort_key("tenant")               -> ("tenant", ())
        split_sort_key("module#members")       -> ("module", ("members",))
        split_sort_key("role#a@b#Members_CRUD") -> ("role", ("a@b", "Members_CRUD"))

    Args:
        sort_key_value: The composite value stored under :data:`SORT_KEY_ATTR`.

    Returns:
        A ``(record_type, id_parts)`` tuple.

    Raises:
        ValueError: The value is empty.
    """
    if not sort_key_value:
        raise ValueError("sort-key value must be a non-empty string")
    record_type, *id_parts = sort_key_value.split(SORT_KEY_SEPARATOR)
    return record_type, tuple(id_parts)


def build_key(tenant_id: str, sort_key_value: str) -> dict[str, str]:
    """Build a full DynamoDB primary key dict for a projection item.

    Args:
        tenant_id: The tenant / ``administration`` value (partition key). Must be
            non-empty — a blank tenant would be a cross-tenant hazard (R5.4).
        sort_key_value: The composite sort-key value (see :func:`build_sort_key`).

    Returns:
        ``{PARTITION_KEY_ATTR: tenant_id, SORT_KEY_ATTR: sort_key_value}`` — the
        shape boto3 expects for ``get_item``/``put_item`` keys.

    Raises:
        ValueError: ``tenant_id`` or ``sort_key_value`` is empty.
    """
    if not tenant_id:
        raise ValueError(
            "tenant_id (partition key) must be non-empty — a blank tenant is a "
            "cross-tenant hazard (R5.4)"
        )
    if not sort_key_value:
        raise ValueError("sort_key_value (sort key) must be non-empty")
    return {PARTITION_KEY_ATTR: tenant_id, SORT_KEY_ATTR: sort_key_value}


# --- Table-name resolution (fail-fast, reuses the T0 client) ---------------


def resolve_projection_table_name() -> str:
    """Return the projection table name from the env, or fail fast.

    Reuses the T0 fail-fast client (:func:`services.dynamodb_client.require_env`)
    so the no-dangerous-fallback discipline (R4.1) lives in one place. The env
    value already carries its environment prefix (``test_`` in test/dev), so this
    does not synthesize a prefix — it refuses to guess a name.

    Returns:
        The configured, non-blank table name.

    Raises:
        services.dynamodb_client.DynamoDBConfigError: The
            ``GOVERNANCE_PROJECTION_TABLE`` var is missing or blank.
    """
    return require_env(PROJECTION_TABLE_ENV_VAR)


def get_projection_table_resource(*, region: str | None = None):
    """Return the boto3 Table handle for the projection table (fail-fast).

    Thin passthrough to :func:`services.dynamodb_client.get_projection_table`, so
    callers that already depend on this schema module do not also need to import
    the client module directly.

    Args:
        region: Optional region override; otherwise ``AWS_REGION`` is required.

    Returns:
        A boto3 DynamoDB Table resource bound to the projection table.

    Raises:
        services.dynamodb_client.DynamoDBConfigError: A required env var (table
            name or region) is missing/blank.
    """
    return get_projection_table(region=region)


# --- IAM LeadingKeys policy plan (defense in depth, R5.4) ------------------

#: IAM policy *plan* for tenant-scoped access to the projection table using
#: ``dynamodb:LeadingKeys``. This documents the defense-in-depth layer described
#: in design.md D3: the partition key already makes cross-tenant reads
#: unaddressable (correctness); this condition additionally restricts a caller's
#: *credentials* to their own partition, matching the S1 Scope seam.
#:
#: The ``${aws:PrincipalTag/tenant_id}`` placeholder is illustrative — the actual
#: binding of a principal to its tenant is a promotion-time IAM decision (T25),
#: not something this module enforces at runtime. It is captured here so T19's
#: read side and the promotion step build against one agreed shape.
LEADING_KEYS_IAM_POLICY_PLAN: dict = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "TenantScopedProjectionAccess",
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:BatchGetItem",
                "dynamodb:Query",
            ],
            "Resource": "arn:aws:dynamodb:*:*:table/${GOVERNANCE_PROJECTION_TABLE}",
            "Condition": {
                "ForAllValues:StringEquals": {
                    # LeadingKeys == the partition key values a caller may touch.
                    # Bound to the caller's own tenant only (defense in depth).
                    "dynamodb:LeadingKeys": ["${aws:PrincipalTag/tenant_id}"]
                }
            },
        }
    ],
}


def leading_keys_iam_policy_json() -> str:
    """Return the LeadingKeys IAM policy plan as a formatted JSON string.

    Convenience for the promotion step (T25) / docs so the plan can be emitted
    verbatim rather than hand-copied.
    """
    return json.dumps(LEADING_KEYS_IAM_POLICY_PLAN, indent=2)
