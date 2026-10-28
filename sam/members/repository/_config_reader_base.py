"""Shared infrastructure for the Members projection config reader (design C4).

This is an INTERNAL helper module of
:mod:`sam.members.repository.projection_config_reader` — the large reader class was split
into cohesive mixins (code-quality file-length split, 2026-10-28) with **zero behaviour
change**. The public import surface stays
``from sam.members.repository.projection_config_reader import MembersProjectionReader``;
nothing imports this module directly except the reader facade that composes the mixins.

This module owns the parts EVERY config read shares:

- the ``config#<id>`` token constants sourced from the shared projection schema;
- :func:`_normalize_functional_groups`, the LIST↔MAP dual-read normalizer;
- :class:`_ConfigReaderBase`, the mixin carrying the boto3 table resolution, the
  per-invocation partition cache, sort-key classification, the ``config#<id>`` row lookup,
  and the projection-staleness (``version``) surface.

The field-overlay, scope, and mail reads live in sibling mixin modules
(:mod:`_fields_overlay_reader`, :mod:`_scope_reader`, :mod:`_mail_config_reader`); the reader
facade composes all four into the one ``MembersProjectionReader`` consumers use.
"""

from __future__ import annotations

from collections.abc import Mapping

from services import projection_schema as schema

#: The ``config#<id>`` rows the reader consumes. The tokens are the single source in the
#: shared projection schema so the Flask-plane builder and this reader cannot drift.
_CONFIG_ID_SCOPE = schema.CONFIG_ID_SCOPE
_CONFIG_ID_FIELDS = schema.CONFIG_ID_FIELDS
_CONFIG_ID_MAIL = schema.CONFIG_ID_MAIL


def _normalize_functional_groups(raw) -> dict:
    """Normalize a stored ``functional_groups`` attribute to a MAP keyed by group ``key`` (spec 03,
    design C6 / D2a / design-review Q3a).

    **DUAL-READ (review Must-fix #4):** the storage shape is being migrated from an ordered LIST
    ``[{key, label, order}, …]`` (legacy) to a MAP ``{key: {label, order}, …}`` (new, truncation-
    proof per-path ``update_item``). Both shapes must resolve IDENTICALLY until every tenant row is
    migrated AND all code is deployed — so this one normalizer is the single place that accepts
    either:

    - a **MAP** (new): each ``{group_key: entry}`` pair is kept; the entry's own ``key`` wins when
      it carries one, else the map key fills it in (so ``order`` / ``label`` live in the entry —
      the re-home is already done, Q3a). Non-dict entries are skipped (degrade gracefully).
    - a **LIST** (legacy): each ``{key, …}`` entry is re-keyed by its ``key``; a keyless/non-dict
      entry is skipped (mirrors the pre-migration loop ``for g in raw_groups``).
    - anything else (``None`` / missing / wrong type) → ``{}`` (empty-is-valid, never an error).

    Returns a ``{group_key: entry_dict}`` map; each ``entry_dict`` is guaranteed to carry its own
    ``key`` so downstream builders stay shape-agnostic. The returned entries are shallow copies so
    a caller may not mutate the stored row.
    """
    if isinstance(raw, Mapping):
        groups: dict = {}
        for gkey, entry in raw.items():
            if not isinstance(entry, Mapping) or not gkey:
                continue
            normalized = dict(entry)
            # The entry's own `key` is authoritative when present (so a round-trip is loss-free);
            # otherwise the map key IS the group key — fill it in so the shape matches the LIST
            # entries' `{key, …}` form the builders already consume.
            normalized.setdefault("key", str(gkey))
            groups[str(normalized.get("key") or gkey)] = normalized
        return groups
    if isinstance(raw, (list, tuple)):
        groups = {}
        for entry in raw:
            if not isinstance(entry, Mapping):
                continue
            key = entry.get("key")
            if not key:
                continue
            groups[str(key)] = dict(entry)
        return groups
    return {}


class _ConfigReaderBase:
    """Shared read infrastructure for the Members projection config reader (C4).

    Mixin carrying the boto3 table resolution, the per-invocation partition cache, sort-key
    classification, the ``config#<id>`` row lookup, and the projection-staleness surface. The
    overlay / scope / mail read mixins inherit from this (via the composed
    :class:`MembersProjectionReader`) and call :meth:`_find_config_row` / :meth:`_query_partition`
    on ``self``.

    Mirrors :class:`sam.pretokengen.projection_governance_reader.ProjectionGovernanceReader`:
    one ``Query`` per tenant partition, a per-invocation ``_partition_cache`` so a partition
    is read at most once, and *empty-is-valid* (a missing/empty partition or row is never an
    error — only a missing table env fails fast, at the first real Query).

    Args:
        table: A boto3 DynamoDB Table (or a fake exposing ``query``). Defaults to the
            fail-fast-resolved projection table
            (:func:`services.projection_schema.get_projection_table_resource`). Injectable so
            tests use an in-memory fake / local dynamodb-local.
    """

    def __init__(self, table=None):
        self._table = table
        # Per-invocation cache: tenant_id -> list of that partition's items, so a tenant's
        # partition is Queried at most once per invocation.
        self._partition_cache: dict[str, list[dict]] = {}

    @property
    def table(self):
        """The projection table, resolved lazily + fail-fast on first use (R4.1)."""
        if self._table is None:
            self._table = schema.get_projection_table_resource()
        return self._table

    def _query_partition(
        self, tenant_id: str, *, consistent_read: bool = False
    ) -> list[dict]:
        """Return all projected items for ``tenant_id`` (cached, read-only).

        One DynamoDB ``Query`` on the partition key. A missing/empty partition returns ``[]``
        (empty is valid). boto3 is imported lazily so the module imports cleanly where boto3's
        condition types aren't needed (a fake table in tests can bypass this by pre-seeding
        the cache).

        ``consistent_read`` (spec 03 task 2.3, design C1 step 1 / design-review Should-fix): the
        Change-Op CRUD service reads the resolved record STRONGLY-CONSISTENT ONLY to validate +
        decide placement/version, so a stale eventually-consistent read never produces a spurious
        409. A consistent read BYPASSES the per-invocation ``_partition_cache`` (reading, then
        caching, an eventually-consistent copy would defeat the point) and passes
        ``ConsistentRead=True`` down to the repository ``Query``. The default path
        (``consistent_read=False``) is UNCHANGED — the normal, cached, eventually-consistent read
        every existing reader method uses.
        """
        if not tenant_id:
            return []
        if not consistent_read and tenant_id in self._partition_cache:
            return self._partition_cache[tenant_id]

        from boto3.dynamodb.conditions import Key

        query_kwargs = {
            "KeyConditionExpression": Key(schema.PARTITION_KEY_ATTR).eq(tenant_id)
        }
        if consistent_read:
            query_kwargs["ConsistentRead"] = True
        response = self.table.query(**query_kwargs)
        items = list(response.get("Items", []) or [])
        # Only the normal (eventually-consistent) read populates the shared cache; a strongly-
        # consistent read is a point-in-time validate-and-place read, not a reusable snapshot.
        if not consistent_read:
            self._partition_cache[tenant_id] = items
        return items

    @staticmethod
    def _classify(item: dict) -> tuple[str, tuple[str, ...]]:
        """Return ``(record_type, id_parts)`` for a projected item's sort key.

        A missing/blank sort key classifies as ``("", ())`` so it is simply skipped by the
        callers (never a raise) — empty is valid.
        """
        sk = item.get(schema.SORT_KEY_ATTR, "")
        return schema.split_sort_key(sk) if sk else ("", ())

    # ── Delivered/loaded status (Phase 0 step 3 — projection staleness surface) ────────

    def get_config_status(self, tenant_id: str) -> dict:
        """Return the DELIVERED/LOADED status of the tenant's projected ``config#*`` rows.

        Phase 0 step 3 (impact-analysis §2 "No read-side version/staleness surface" / risk
        #6). The projection is written one-directionally by the Flask-plane ``ProjectionSync``
        (MySQL → DynamoDB); until now the SAM read side never exposed *what version it is
        serving*, so a stale or never-delivered config was invisible to the authoring UI. A
        Tenant Admin edits a ``members.*`` param on the Flask plane and has no way to see
        whether that edit has actually been projected (delivered) and is what the module is
        reading (loaded).

        This method surfaces, per config row, the projected ``version`` the reader is serving
        — the SAME monotonic ``version`` the conditional write and the version-bump-trap fix
        advance (:data:`services.projection_schema.VERSION_ATTR`). The authoring editor
        compares it to the source param's own revision (``parameters.updated_at`` on the Flask
        plane) to render a delivered/stale/not-yet-delivered indicator:

        - a row PRESENT with a ``version`` → that config has been DELIVERED and is what the
          module LOADS; the version lets the editor detect staleness (source newer than
          delivered);
        - a row ABSENT (``version`` is ``None``) → that config has NEVER been projected for
          this tenant (the editor shows "not yet delivered").

        Read-only and empty-is-valid, same discipline as the sibling readers: one ``Query``
        per partition (shared cache), a missing partition/row simply yields ``None`` versions,
        never a raise.

        Args:
            tenant_id: The tenant (partition key) whose projection status to resolve.

        Returns:
            A dict mapping each config id (``"scope"``/``"fields"``/``"mail"``) to
            its projected ``version`` (any JSON scalar — typically an ISO-8601 timestamp or an
            int), or ``None`` when that row has not been delivered.
        """
        return {
            config_id: self._config_row_version(tenant_id, config_id)
            for config_id in (
                _CONFIG_ID_SCOPE,
                _CONFIG_ID_FIELDS,
                _CONFIG_ID_MAIL,
            )
        }

    def _config_row_version(self, tenant_id: str, config_id: str):
        """Return the projected ``version`` of a ``config#<config_id>`` row, or ``None``.

        A missing row (never delivered) → ``None`` (empty-is-valid); otherwise the row's
        :data:`~services.projection_schema.VERSION_ATTR` value, verbatim (the monotonic version
        the write path advances), so the editor can compare it to the source param revision.
        """
        row = self._find_config_row(tenant_id, config_id)
        if row is None:
            return None
        return row.get(schema.VERSION_ATTR)

    # ── internals ──────────────────────────────────────────────────────────────────────

    def _find_config_row(
        self, tenant_id: str, config_id: str, *, consistent_read: bool = False
    ) -> dict | None:
        """Return the ``config#<config_id>`` row for ``tenant_id``, or ``None`` if absent.

        A missing row is valid (the caller collapses it to the empty/tenant-wide default);
        this never raises on missing/empty data. ``consistent_read`` flows to
        :meth:`_query_partition` so the Change-Op validate-and-place read (task 2.3) can request a
        strongly-consistent view of the partition; every normal reader keeps the cached,
        eventually-consistent default.
        """
        for item in self._query_partition(tenant_id, consistent_read=consistent_read):
            record_type, id_parts = self._classify(item)
            if record_type != schema.RECORD_TYPE_CONFIG:
                continue
            if id_parts and id_parts[0] == config_id:
                return item
        return None
