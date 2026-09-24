"""
S5 Task 1.4 — the tenant-scoped **table design** for the Members module (design C6 + data
models, R3.1 / Property 1 / Property 6).

This module is the **single source of truth** for the Members module's DynamoDB key shape:
the partition/sort key attribute names, the record-type tokens, the sort-key composition /
parsing, and the item builders. It mirrors the S3 projection's ``projection_schema`` pattern
(one place assembles/parses the ``record_type#id`` composite) so the repository
(:mod:`sam.members.repository.members_repository`), Step-4 provisioning, and the Step-4
backfill all agree on one definition instead of each re-deriving keys.

Single-table design (design "New tenant-scoped tables", data models)
--------------------------------------------------------------------
Every Members entity for a tenant lives in **one** table, partitioned by ``tenant_id`` so a
query cannot address more than one tenant's partition — cross-tenant reads are structurally
unaddressable (Property 1). The sort key is a ``record_type#id`` composite that groups a
member and everything hanging off it (memberships, delegates, payments) under access
patterns that never leave the tenant partition::

    Table: sam-members                    (sam-members-test in test/dev; PAY_PER_REQUEST)
      PK  tenant_id                        -- partition key = tenancy boundary (LeadingKeys)
      SK  record_type#id                   -- see the record-type tokens below
      attrs: personal{}, membership{}, scope_values{}, overlay{}, ...

      SK values (all within one tenant partition):
        member#<member_id>                              -- the member record (fixed ⊕ overlay)
        member#<member_id>#membership#<membership_id>   -- a membership of that member
        member#<member_id>#delegates                    -- the member's delegate set (single item)
        member#<member_id>#payment#<payment_id>         -- a member-scoped payment
        membershiptype#<type_code>                      -- Lidmaatschap Beheer catalog entry

Member numbering (s5k)
----------------------
``member_number`` (Lidnummer) is a plain OPTIONAL string the caller/import supplies — it is
NOT auto-generated and NOT guarded for uniqueness. The former ``counter#<name>`` (atomic
counter) and ``membernum#<member_number>`` (uniqueness guard) record types were REMOVED; a
duplicate member number is a data-quality concern, not a write-time conflict (see spec s5k).
``save_member`` / ``delete_member`` are single-item ``PutItem`` / ``DeleteItem``.

Config + fail-fast (mirrors ``services.dynamodb_client`` / ``projection_schema``)
---------------------------------------------------------------------------------
The table name is resolved from ``MEMBERS_TABLE`` (``sam-members`` in prod, ``sam-members-test``
in test/dev — the SAM-plane ``sam-`` prefix convention, env as a *suffix*, see
``23-aws-accounts.md`` / ``35-sam-module-architecture-sam.md``) — a missing/blank var raises
rather than defaulting, so nothing can silently point at the wrong table or at production.
This module never synthesizes the name; it takes it verbatim from the env var. The client
points at the local
``dynamodb-local`` container only when ``AWS_ENDPOINT_URL_DYNAMODB`` is set (Step-4 / local),
and at real AWS otherwise. Both concerns reuse the T0 fail-fast client
(:mod:`services.dynamodb_client`), so the no-dangerous-fallback discipline lives in one place.

Scope of THIS module: the **key shape + item builders + table-name resolution**. It is
storage-shape only — no business rules (those are the domain layer), and it does not itself
open a connection until the repository asks for the table resource. Provisioning the physical
table (PAY_PER_REQUEST, retain, managed outside CloudFormation) is Step 4 (task 4.0).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from services.dynamodb_client import get_dynamodb_resource, require_env

__all__ = [
    "MEMBERS_TABLE_ENV_VAR",
    "PARTITION_KEY_ATTR",
    "SORT_KEY_ATTR",
    "SORT_KEY_SEPARATOR",
    "RECORD_TYPE_MEMBER",
    "RECORD_TYPE_MEMBERSHIP",
    "RECORD_TYPE_DELEGATES",
    "RECORD_TYPE_PAYMENT",
    "RECORD_TYPE_MEMBERSHIP_TYPE",
    "build_sort_key",
    "split_sort_key",
    "member_sk",
    "membership_sk",
    "delegates_sk",
    "payment_sk",
    "membership_type_sk",
    "member_sk_prefix",
    "build_key",
    "floats_to_decimal",
    "build_member_item",
    "build_membership_type_item",
    "resolve_members_table_name",
    "get_members_table_resource",
    "LEADING_KEYS_IAM_POLICY_PLAN",
    "leading_keys_iam_policy_json",
]

# --- Config (fail-fast, reuses the T0 client) ------------------------------

#: The Members table-name env var. The value is the full SAM-plane table name —
#: ``sam-members`` (prod) / ``sam-members-test`` (test/dev), the ``sam-`` prefix convention
#: with the environment as a *suffix* — so this module never synthesizes a name: it refuses
#: to guess (no-dangerous-fallback, mirrors ``PROJECTION_TABLE_ENV_VAR``).
MEMBERS_TABLE_ENV_VAR = "MEMBERS_TABLE"


# --- Key schema attribute names (canonical) --------------------------------

#: Partition-key attribute name. Its value is the ``tenant_id`` — the tenancy boundary. Making
#: the tenant the partition key means a query cannot address more than one tenant's partition,
#: so cross-tenant reads are structurally unaddressable (Property 1). IAM
#: ``dynamodb:LeadingKeys`` (see :data:`LEADING_KEYS_IAM_POLICY_PLAN`) restricts a caller's
#: *credentials* to their own partition as defense-in-depth.
PARTITION_KEY_ATTR = "tenant_id"

#: Sort-key attribute name. Holds the ``record_type#id`` composite value (see below).
SORT_KEY_ATTR = "sk"

#: Separator that joins the sort-key segments into the sort-key value.
SORT_KEY_SEPARATOR = "#"


# --- Record-type tokens (leading segments of the SK value) -----------------

RECORD_TYPE_MEMBER = "member"
RECORD_TYPE_MEMBERSHIP = "membership"
RECORD_TYPE_DELEGATES = "delegates"
RECORD_TYPE_PAYMENT = "payment"
# s5k: the ``counter#`` (atomic per-tenant counter) and ``membernum#`` (member-number
# uniqueness guard) record types were REMOVED — member numbering is no longer generated or
# guarded (``member_number`` is a plain optional string). See spec s5k.
#: Lidmaatschap Beheer catalog entry (design C8). A ``membershiptype#<type_code>`` item is one
#: membership type the tenant offers; the member record's ``membership.membership_type``
#: references its ``type_code``. Lives in the tenant partition like every other entity.
RECORD_TYPE_MEMBERSHIP_TYPE = "membershiptype"


# --- Sort-key composition / parsing ----------------------------------------


def build_sort_key(*segments: str) -> str:
    """Join sort-key ``segments`` into the composite value stored under :data:`SORT_KEY_ATTR`.

    This is the *only* place the ``#``-join convention is applied, so the repository, the
    Step-4 provisioning, and the backfill cannot diverge on the format. Prefer the typed
    helpers (:func:`member_sk`, :func:`membership_sk`, ...) over calling this directly.

    Args:
        *segments: One or more non-empty segments (e.g. ``("member", member_id)``).

    Returns:
        The composite sort-key string.

    Raises:
        ValueError: No segments were given, or a segment is empty / contains the separator
            (which would make the key ambiguous to parse).
    """
    if not segments:
        raise ValueError("at least one sort-key segment is required")
    for segment in segments:
        if segment is None or segment == "":
            raise ValueError(f"sort-key segments must be non-empty: {segments!r}")
        if SORT_KEY_SEPARATOR in segment:
            raise ValueError(
                f"sort-key segment {segment!r} must not contain the separator "
                f"{SORT_KEY_SEPARATOR!r} (it would make the key ambiguous)"
            )
    return SORT_KEY_SEPARATOR.join(segments)


def split_sort_key(sort_key_value: str) -> tuple[str, ...]:
    """Split a sort-key value back into its segments (inverse of :func:`build_sort_key`).

    Args:
        sort_key_value: The composite value stored under :data:`SORT_KEY_ATTR`.

    Returns:
        The tuple of segments, e.g. ``("member", "M-1", "membership", "MS-9")``.

    Raises:
        ValueError: The value is empty.
    """
    if not sort_key_value:
        raise ValueError("sort-key value must be a non-empty string")
    return tuple(sort_key_value.split(SORT_KEY_SEPARATOR))


# --- Typed SK builders (one per access pattern) ----------------------------


def member_sk(member_id: str) -> str:
    """SK for a member record: ``member#<member_id>``."""
    return build_sort_key(RECORD_TYPE_MEMBER, member_id)


def membership_sk(member_id: str, membership_id: str) -> str:
    """SK for a membership of a member: ``member#<member_id>#membership#<membership_id>``."""
    return build_sort_key(
        RECORD_TYPE_MEMBER, member_id, RECORD_TYPE_MEMBERSHIP, membership_id
    )


def delegates_sk(member_id: str) -> str:
    """SK for a member's delegate set (a single item): ``member#<member_id>#delegates``."""
    return build_sort_key(RECORD_TYPE_MEMBER, member_id, RECORD_TYPE_DELEGATES)


def payment_sk(member_id: str, payment_id: str) -> str:
    """SK for a member-scoped payment: ``member#<member_id>#payment#<payment_id>``."""
    return build_sort_key(
        RECORD_TYPE_MEMBER, member_id, RECORD_TYPE_PAYMENT, payment_id
    )


def membership_type_sk(type_code: str) -> str:
    """SK for a Lidmaatschap Beheer catalog entry: ``membershiptype#<type_code>`` (C8)."""
    return build_sort_key(RECORD_TYPE_MEMBERSHIP_TYPE, type_code)


def member_sk_prefix(member_id: str) -> str:
    """The SK prefix that selects a member and everything hanging off it.

    ``member#<member_id>`` is a prefix of the member item's own SK *and* of its memberships,
    delegates, and payments — so a single ``begins_with`` Query inside the tenant partition
    fetches the member and all its children (still tenant-scoped: the partition key is fixed).
    """
    return build_sort_key(RECORD_TYPE_MEMBER, member_id)


# --- Full-key + item builders ----------------------------------------------


def build_key(tenant_id: str, sort_key_value: str) -> dict[str, str]:
    """Build a full DynamoDB primary key dict for a Members item.

    Args:
        tenant_id: The tenant (partition key). Must be non-empty — a blank tenant would be a
            cross-tenant hazard (Property 1).
        sort_key_value: The composite sort-key value (see the ``*_sk`` builders).

    Returns:
        ``{PARTITION_KEY_ATTR: tenant_id, SORT_KEY_ATTR: sort_key_value}`` — the shape boto3
        expects for ``get_item`` / ``put_item`` / ``update_item`` keys.

    Raises:
        ValueError: ``tenant_id`` or ``sort_key_value`` is empty.
    """
    if not tenant_id:
        raise ValueError(
            "tenant_id (partition key) must be non-empty — a blank tenant is a "
            "cross-tenant hazard (Property 1)"
        )
    if not sort_key_value:
        raise ValueError("sort_key_value (sort key) must be non-empty")
    return {PARTITION_KEY_ATTR: tenant_id, SORT_KEY_ATTR: sort_key_value}


def floats_to_decimal(value: Any) -> Any:
    """Recursively convert every ``float`` in ``value`` to :class:`~decimal.Decimal`.

    DynamoDB (boto3) refuses Python ``float`` — it stores numbers as ``Decimal`` and raises
    ``"Float types are not supported. Use Decimal types instead."`` on a ``put_item`` /
    ``transact_write_items`` that carries one. Source data (e.g. the h-dcn backfill's
    ``overlay.Bedrag`` fee, a JSON float) can therefore reach a write untouched. This helper is
    applied by every item builder below so no write path can hand boto3 a raw float, no matter
    how deeply nested inside ``personal`` / ``membership`` / ``overlay`` / lists it sits.

    ``Decimal(str(f))`` (not ``Decimal(f)``) is used deliberately: converting via the float's
    ``repr`` avoids dragging in binary-float artefacts (e.g. ``Decimal(22.6)`` →
    ``22.6000000000000014...``), so ``22.6`` round-trips as ``Decimal('22.6')``. This mirrors
    the read-side convention (numbers deserialize as ``Decimal`` and ``from_item`` coerces back
    — see ``test_membership_type_catalog.test_from_item_coerces_numeric_order``).

    ``bool`` is intentionally left alone (it is a DynamoDB BOOL, and ``bool`` is a subclass of
    ``int`` so it must not be caught by any numeric branch). ``int`` is already valid and is
    passed through unchanged.

    Args:
        value: Any JSON-ish value — scalar, ``Mapping``, or sequence.

    Returns:
        A new value of the same shape with every ``float`` replaced by an equivalent
        ``Decimal``. Non-float values are returned as-is (dicts/lists are rebuilt).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, Mapping):
        return {k: floats_to_decimal(v) for k, v in value.items()}
    # Recurse into lists/tuples/sets of values, but never strings/bytes (they are scalars).
    if isinstance(value, (list, tuple)):
        return [floats_to_decimal(v) for v in value]
    return value


def build_member_item(tenant_id: str, member_id: str, member: Mapping[str, Any]) -> dict:
    """Compose the stored DynamoDB item for a member record.

    Stamps the tenant partition key and the ``member#<member_id>`` sort key onto a copy of the
    domain-layer ``member`` payload (fixed base ⊕ overlay + ``scope_values``). The caller's
    ``tenant_id`` (from the verified context) is authoritative — any ``tenant_id`` already on
    the payload is overwritten so a domain-layer mistake can never land a record in the wrong
    partition.

    Args:
        tenant_id: The tenant (partition key).
        member_id: The member id (sort-key id segment).
        member: The domain member payload (``personal`` / ``membership`` / ``scope_values`` /
            ``overlay`` per the design data model).

    Returns:
        A new dict ready for ``put_item`` — the payload plus the primary key attributes.

    Raises:
        ValueError: ``tenant_id`` or ``member_id`` is empty.
    """
    if not member_id:
        raise ValueError("member_id must be non-empty")
    # Deep-copy with float→Decimal coercion so nested payload numbers (e.g. overlay.Bedrag)
    # are DynamoDB-safe before any write path serializes this item.
    item = floats_to_decimal(dict(member))
    item[PARTITION_KEY_ATTR] = tenant_id  # authoritative — overwrite any payload value
    item[SORT_KEY_ATTR] = member_sk(member_id)
    # Keep the bare id addressable without re-parsing the sort key.
    item.setdefault("member_id", member_id)
    # Fail-fast if the composed key would be invalid (blank tenant, etc.).
    build_key(tenant_id, item[SORT_KEY_ATTR])
    return item


def build_membership_type_item(
    tenant_id: str, type_code: str, entry: Mapping[str, Any]
) -> dict:
    """Compose the stored DynamoDB item for a Lidmaatschap Beheer catalog entry (C8).

    Stamps the tenant partition key and the ``membershiptype#<type_code>`` sort key onto a
    copy of the domain-layer ``entry`` payload (``label`` / ``active`` / ``order``). The
    caller's ``tenant_id`` and ``type_code`` are authoritative — any values already on the
    payload are overwritten so a domain-layer mistake can never land an entry in the wrong
    partition or under the wrong code.

    Args:
        tenant_id: The tenant (partition key).
        type_code: The catalog entry's code (sort-key id segment; also the member reference).
        entry: The domain entry payload (``label`` / ``active`` / ``order``; see C8).

    Returns:
        A new dict ready for ``put_item`` — the payload plus the primary-key + reference attrs.

    Raises:
        ValueError: ``tenant_id`` or ``type_code`` is empty.
    """
    if not type_code:
        raise ValueError("type_code must be non-empty")
    item = floats_to_decimal(dict(entry))  # DynamoDB-safe numbers (float→Decimal)
    item[PARTITION_KEY_ATTR] = tenant_id  # authoritative — overwrite any payload value
    item[SORT_KEY_ATTR] = membership_type_sk(type_code)
    # Keep the reference code addressable without re-parsing the sort key. (tenant_id is
    # already the partition-key attribute, stamped above.)
    item["type_code"] = type_code
    # Fail-fast if the composed key would be invalid (blank tenant, etc.).
    build_key(tenant_id, item[SORT_KEY_ATTR])
    return item


# --- Table-name resolution + resource (fail-fast, reuses the T0 client) ----


def resolve_members_table_name() -> str:
    """Return the Members table name from ``MEMBERS_TABLE``, or fail fast.

    Reuses the T0 fail-fast client (:func:`services.dynamodb_client.require_env`) so the
    no-dangerous-fallback discipline lives in one place. The env value is the full table
    name (``sam-members`` prod / ``sam-members-test`` test/dev — ``sam-`` prefix, env as a
    suffix), so this does not synthesize any prefix.

    Raises:
        services.dynamodb_client.DynamoDBConfigError: ``MEMBERS_TABLE`` is missing/blank.
    """
    return require_env(MEMBERS_TABLE_ENV_VAR)


def get_members_table_resource(*, region: str | None = None):
    """Return the boto3 Table handle for the Members table (fail-fast).

    Points at the local ``dynamodb-local`` container only when ``AWS_ENDPOINT_URL_DYNAMODB``
    is set (Step-4 / local); otherwise real AWS. The region comes from ``AWS_REGION`` unless
    passed explicitly.

    Args:
        region: Optional region override; otherwise ``AWS_REGION`` is required.

    Raises:
        services.dynamodb_client.DynamoDBConfigError: A required env var (table name or
            region) is missing/blank.
    """
    table_name = resolve_members_table_name()
    resource = get_dynamodb_resource(region=region)
    return resource.Table(table_name)


# --- IAM LeadingKeys policy plan (defense in depth) ------------------------

#: IAM policy *plan* for tenant-scoped access to the Members table using
#: ``dynamodb:LeadingKeys``. The partition key already makes cross-tenant reads unaddressable
#: (correctness, Property 1); this condition additionally restricts a caller's *credentials*
#: to their own partition (defense in depth), mirroring the S3 projection plan. The
#: ``${aws:PrincipalTag/tenant_id}`` placeholder is illustrative — binding a principal to its
#: tenant is a Step-4 IAM decision, captured here so the repository and provisioning build
#: against one agreed shape.
LEADING_KEYS_IAM_POLICY_PLAN: dict = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "TenantScopedMembersAccess",
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:BatchGetItem",
                "dynamodb:Query",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:TransactWriteItems",
            ],
            "Resource": "arn:aws:dynamodb:*:*:table/${MEMBERS_TABLE}",
            "Condition": {
                "ForAllValues:StringEquals": {
                    # LeadingKeys == the partition-key values a caller may touch — bound to
                    # the caller's own tenant only (defense in depth over the PK isolation).
                    "dynamodb:LeadingKeys": ["${aws:PrincipalTag/tenant_id}"]
                }
            },
        }
    ],
}


def leading_keys_iam_policy_json() -> str:
    """Return the LeadingKeys IAM policy plan as a formatted JSON string (for Step-4 / docs)."""
    import json

    return json.dumps(LEADING_KEYS_IAM_POLICY_PLAN, indent=2)
