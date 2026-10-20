"""Members config **write repository** (spec 02, design C3) — the net-new, SAM-owned writer.

The ``boto3``-backed **writer** sibling of the read-only
:mod:`sam.members.repository.projection_config_reader` (``MembersProjectionReader``). It
performs a versioned ``put_item`` on exactly the three SAM-owned ``config#*`` rows —
``config#fields`` / ``config#scope`` / ``config#mail`` — so DynamoDB ``governance_projection``
becomes the system-of-record for those rows while the reader keeps serving them UNCHANGED.

Why this exists (design C3)
---------------------------
Phase 1 introduces a SAM-owned write path (API Gateway PUT -> Members Lambda edge ->
config-write domain service -> **this repository** -> DynamoDB) for the three tenant-level
config rows the SAM plane ONLY reads. This is infrastructure: the config-write domain service
(no ``boto3``) shapes the validated body and the row-level version stamp, then hands
``(tenant_id, config_id, attributes, version)`` here for persistence. The domain never imports
this module (dependency inversion — the arrow points inward, mirroring the reader's layering).

Split-ownership guardrail (R2)
------------------------------
The write surface is CLOSED to exactly ``{scope, fields, mail}`` via :data:`_WRITABLE_CONFIG_IDS`.
This repository is the structural second guard behind the route's ``configId`` check: it NEVER
authors ``tenant`` / ``module#`` / ``role#`` / ``scopegrant#`` / ``config#views`` rows, so the
split-ownership partition between SAM and ``ProjectionSync`` (Flask) stays clean. A write for any
id outside the closed set raises ``ValueError`` BEFORE any ``put_item``.

Schema tokens only (R1.6)
-------------------------
Every key attribute name and token comes from :mod:`services.projection_schema` — the same single
source the reader uses (``CONFIG_ID_*``, ``RECORD_TYPE_CONFIG``, ``build_sort_key``, ``build_key``,
``PARTITION_KEY_ATTR`` / ``SORT_KEY_ATTR`` / ``VERSION_ATTR``). Reusing the shared schema means the
writer and reader cannot drift on the key shape or the ``config#<id>`` id tokens.

Config + fail-fast (R5.1/R5.2)
------------------------------
The table is resolved from ``GOVERNANCE_PROJECTION_TABLE`` via the S3 fail-fast client
(:func:`services.projection_schema.get_projection_table_resource`) — missing/blank throws, no
dangerous default, resolved lazily on first real ``put_item``. The ``table`` is injectable so tests
use an in-memory fake / local dynamodb-local. A blank ``tenant_id`` is rejected before any write so
the tenancy boundary is never crossed by a blank key (R5.5).
"""

from __future__ import annotations

from services import projection_schema as schema

__all__ = ["MembersConfigWriteRepository"]

#: The CLOSED set of ``config#<id>`` ids this repository may write (R2.1). The tokens come from
#: the shared projection schema so the writer, reader, and Flask builder cannot drift. Any id
#: outside this set is rejected before a ``put_item`` (R2.3) — so ``tenant`` / ``module#`` /
#: ``role#`` / ``scopegrant#`` / ``config#views`` are structurally unwritable by SAM (R2.4/R2.5).
_WRITABLE_CONFIG_IDS = frozenset(
    {schema.CONFIG_ID_SCOPE, schema.CONFIG_ID_FIELDS, schema.CONFIG_ID_MAIL}
)


class MembersConfigWriteRepository:
    """Versioned writer for the three SAM-owned ``config#*`` rows (design C3).

    Performs a single ``put_item`` per write, authoring the EXACT attribute shape the
    :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader` reads back
    for that ``configId`` (R1.4), so the reader stays unchanged. The write surface is closed to
    :data:`_WRITABLE_CONFIG_IDS` (R2), the table resolves fail-fast (R5.1/R5.2), and every write
    requires a non-empty ``tenant_id`` partition key (R5.5).

    Args:
        table: A boto3 DynamoDB Table (or a fake exposing ``put_item``). Defaults to the
            fail-fast-resolved projection table
            (:func:`services.projection_schema.get_projection_table_resource`). Injectable so
            tests use an in-memory fake / local dynamodb-local.
    """

    def __init__(self, table=None):
        self._table = table

    @property
    def table(self):
        """The projection table, resolved lazily + fail-fast on first use (R5.1/R5.2)."""
        if self._table is None:
            self._table = schema.get_projection_table_resource()
        return self._table

    def put_config(
        self,
        tenant_id: str,
        config_id: str,
        attributes: dict,
        version: str,
    ) -> dict:
        """Write one SAM-owned ``config#<config_id>`` row with a versioned ``put_item``.

        Builds the key via ``build_key(tenant_id, build_sort_key(RECORD_TYPE_CONFIG, config_id))``,
        merges the caller-shaped ``attributes`` onto that key, stamps :data:`VERSION_ATTR` with the
        row-level ``version``, and performs a single ``put_item``. The item is authored in the exact
        shape the reader reads back for ``config_id`` (R1.4) — this repository adds only the key and
        the version stamp; it does not reshape the domain-provided ``attributes``.

        The key attributes (``PARTITION_KEY_ATTR`` / ``SORT_KEY_ATTR``) and the version stamp always
        win over any same-named keys that leaked into ``attributes``, so the written row's key and
        version are never shadowed by the body.

        Args:
            tenant_id: The tenant (partition key) to write under. Must be non-empty (R5.5).
            config_id: One of ``{scope, fields, mail}`` (R2.1) — rejected otherwise (R2.3).
            attributes: The reader-shaped attribute body (e.g. ``fields``/``overrides``/
                ``functional_groups`` for ``fields``), with no key or version attribute needed.
            version: The row-level monotonic ISO-8601 write stamp (computed by the domain service).

        Returns:
            The exact item dict written to DynamoDB (key + version + attributes merged).

        Raises:
            ValueError: ``tenant_id`` is blank (R3.5/R5.5), or ``config_id`` is outside the closed
                writable set (R2.3) — both raised BEFORE any ``put_item``.
        """
        if not tenant_id:
            raise ValueError(
                "tenant_id (partition key) must be non-empty — a blank tenant is a "
                "cross-tenant hazard (R5.5)"
            )
        if config_id not in _WRITABLE_CONFIG_IDS:
            raise ValueError(
                f"config_id {config_id!r} is not writable by the SAM plane; the write "
                f"surface is closed to {sorted(_WRITABLE_CONFIG_IDS)!r} (R2.3)"
            )

        sort_key_value = schema.build_sort_key(schema.RECORD_TYPE_CONFIG, config_id)
        key = schema.build_key(tenant_id, sort_key_value)

        # Merge the reader-shaped body first, then let the key + version stamp win so neither the
        # partition/sort key nor the authoritative version can be shadowed by a stray body attr.
        item = {
            **(attributes or {}),
            **key,
            schema.VERSION_ATTR: version,
        }

        self.table.put_item(Item=item)
        return item
