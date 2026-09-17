"""
S4 D2 (amended, Option A) — the read-only governance seam backed by the S3
DynamoDB projection, NOT MySQL.

Why this replaces the MySQL reader (see design.md "Design amendment A")
-----------------------------------------------------------------------
The Pre-Token-Generation Lambda runs in AWS during token issuance, under
Cognito's ~5s budget. Reading MySQL would mean reaching **Railway** MySQL from
AWS over its public TCP proxy on every cold start — an operational risk and a
bend of the S1 "a module Lambda never opens a MySQL connection" contract. S3
already built the exact data plane for this: a one-directional, read-only
DynamoDB projection of the tenant-level governance (`tenants` / `tenant_modules`
/ `user_tenant_roles`). This reader consumes that projection with ``boto3`` (no
``mysql-connector`` in the bundle, no Railway egress), keyed by the user's own
tenants.

Read pattern
------------
The user's tenant list is supplied by the caller (from the PreTokenGen event's
verified ``custom:tenants`` claim). For each tenant ``T`` the reader issues one
DynamoDB ``Query`` on partition ``tenant_id = T`` (the tenancy boundary, R5.4 —
cross-tenant reads are structurally unaddressable) and reconstructs, from the
projected items (shape per :mod:`services.projection_schema`):

- ``active_modules_by_tenant[T]`` = the ``module#<name>`` items whose
  ``is_active`` is truthy;
- ``roles_by_tenant[T]``          = the ``role#<email>#<role>`` items **filtered
  to the calling user's email**.

The handler then feeds those two maps to the UNCHANGED T1 resolver
(``resolve_entitlement``) and T4 codec (``encode_entitlements``). One rule, two
carriers — only the *source* of the rows changed (projection instead of MySQL).

Empty is valid (not an error)
-----------------------------
A tenant partition with no ``module``/``role`` items — or a tenant absent from
the projection entirely (e.g. before S5 registers real SAM-backed modules, when
the production table is empty) — yields an **empty** entry for that tenant. A
user with no projectable tenants yields empty maps, which the resolver turns into
an empty entitlement and the codec encodes as ``{v:1,t:{}}``. The reader NEVER
raises on missing/empty data; it returns what the projection holds.

Interface compatibility
------------------------
This class exposes the SAME method names as the MySQL ``GovernanceReader``
(``get_user_roles_by_tenant`` / ``get_active_modules_by_tenant``) so the handler
seam is a drop-in swap. The key difference: roles are resolved per the user's
tenants, so ``get_active_modules_by_tenant`` is called with the same tenant list
and both are backed by a small per-invocation cache of each tenant's Query result
(so a tenant's partition is read at most once per token issuance).

Config + fail-fast (R2.5, R4.1)
-------------------------------
The table name is resolved from ``GOVERNANCE_PROJECTION_TABLE`` via the S3
fail-fast client (:func:`services.projection_schema.resolve_projection_table_name`
/ :func:`services.dynamodb_client.require_env`) — missing/blank throws, no
dangerous default. The AWS region comes from ``AWS_REGION`` (required by the
client). In production the Lambda's IAM role grants read on the projection table;
``AWS_ENDPOINT_URL_DYNAMODB`` is left UNSET (real AWS) and only set for local
testing against the T0 ``dynamodb-local`` container.
"""

from __future__ import annotations

from collections.abc import Sequence

from services import projection_schema as schema


class ProjectionGovernanceReader:
    """Read-only governance reader backed by the S3 DynamoDB projection.

    Args:
        table: A boto3 DynamoDB Table (or a fake exposing ``query``). Defaults to
            the fail-fast-resolved projection table
            (:func:`services.projection_schema.get_projection_table_resource`).
            Injectable so tests use an in-memory fake / local dynamodb-local.
    """

    def __init__(self, table=None):
        self._table = table
        # Per-invocation cache: tenant_id -> list of that partition's items, so a
        # tenant's partition is Queried at most once per token issuance.
        self._partition_cache: dict[str, list[dict]] = {}

    @property
    def table(self):
        """The projection table, resolved lazily + fail-fast on first use (R4.1)."""
        if self._table is None:
            self._table = schema.get_projection_table_resource()
        return self._table

    def _query_partition(self, tenant_id: str) -> list[dict]:
        """Return all projected items for ``tenant_id`` (cached, read-only).

        One DynamoDB ``Query`` on the partition key. A missing/empty partition
        returns ``[]`` (empty is valid). boto3 is imported lazily so the module
        imports cleanly where boto3's condition types aren't needed (e.g. a fake
        table in tests can bypass this by pre-seeding the cache).
        """
        if not tenant_id:
            return []
        if tenant_id in self._partition_cache:
            return self._partition_cache[tenant_id]

        from boto3.dynamodb.conditions import Key

        response = self.table.query(
            KeyConditionExpression=Key(schema.PARTITION_KEY_ATTR).eq(tenant_id)
        )
        items = list(response.get("Items", []) or [])
        self._partition_cache[tenant_id] = items
        return items

    def get_user_roles_by_tenant(
        self, email: str, tenants: Sequence[str]
    ) -> dict[str, list[str]]:
        """Return ``{tenant -> [role, ...]}`` for ``email`` across ``tenants``.

        Reads each tenant's projection partition and keeps the ``role#<email>#<role>``
        items whose email equals ``email``. A tenant with no matching role items
        maps to ``[]`` (present but no roles) — empty is valid, never an error.

        Args:
            email: The calling user's email (from the verified token).
            tenants: The user's tenant list (from verified ``custom:tenants``).

        Returns:
            ``{tenant -> [role, ...]}`` for every tenant in ``tenants``.
        """
        roles_by_tenant: dict[str, list[str]] = {}
        for tenant in tenants:
            if not tenant:
                continue
            roles: list[str] = []
            for item in self._query_partition(tenant):
                sk = item.get(schema.SORT_KEY_ATTR, "")
                record_type, id_parts = schema.split_sort_key(sk) if sk else ("", ())
                if record_type != schema.RECORD_TYPE_ROLE:
                    continue
                # role#<email>#<role> — id_parts == (email, role). Filter to this user.
                if len(id_parts) >= 2 and id_parts[0] == email:
                    # Prefer the explicit 'role' attr if present; else the key segment.
                    roles.append(item.get("role") or id_parts[1])
            roles_by_tenant[tenant] = roles
        return roles_by_tenant

    def get_active_modules_by_tenant(
        self, tenants: Sequence[str]
    ) -> dict[str, list[str]]:
        """Return ``{tenant -> [active module_name, ...]}`` across ``tenants``.

        Reads each tenant's projection partition and keeps ``module#<name>`` items
        whose ``is_active`` is truthy. A tenant with no active modules maps to
        ``[]`` — empty is valid.

        Args:
            tenants: The user's tenant list (same list used for roles).

        Returns:
            ``{tenant -> [module_name, ...]}`` for every tenant in ``tenants``.
        """
        active_by_tenant: dict[str, list[str]] = {}
        for tenant in tenants:
            if not tenant:
                continue
            active: list[str] = []
            for item in self._query_partition(tenant):
                sk = item.get(schema.SORT_KEY_ATTR, "")
                record_type, id_parts = schema.split_sort_key(sk) if sk else ("", ())
                if record_type != schema.RECORD_TYPE_MODULE:
                    continue
                if id_parts and item.get("is_active"):
                    active.append(id_parts[0])
            active_by_tenant[tenant] = active
        return active_by_tenant
