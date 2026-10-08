"""
S5b Task 8.1 — the Members module **projection config reader** (design C4).

A read-only, ``boto3``-backed consumer of the S3/S5b governance projection that feeds the
S5 Members domain seams with **real projected data**. It mirrors
:mod:`sam.pretokengen.projection_governance_reader` exactly — one DynamoDB ``Query`` per
tenant partition, a per-invocation cache so a partition is read at most once, fail-fast
table resolution via :mod:`services.projection_schema`, and *empty-is-valid* everywhere —
but reconstructs the **S5b** projected rows (``config#scope`` / ``config#fields`` /
``scopegrant#<email>#<dimension>``) into the storage-agnostic domain shapes the UNCHANGED
domain consumes.

Why this exists (design C4)
---------------------------
The S5 domain (``scope_dimensions`` / ``field_resolver`` / ``scope_access``) is deliberately
storage-agnostic: it depends on two ``Protocol`` seams —
:class:`sam.members.domain.scope_dimensions.ScopeConfigProvider` and
:class:`sam.members.domain.field_resolver.TenantOverlayProvider` — never on where the config
lives. S5 shipped in-memory ``Static*`` providers as the reference. This reader is the
SAM-plane concrete provider that replaces them (task 8.2 wires it into cold start): it reads
the projection the S5b builders (tasks 5.1/5.2/5.3) populate and returns exactly the domain
dataclasses those seams expect, so it can be handed straight to ``FieldResolver`` /
``resolve_scope_access`` (duck-typed to the Protocols). It **reads only** — it never writes
MySQL or the projection.

Layering
--------
SAM-plane **infrastructure adapter**: it depends on ``boto3`` + the projection schema and
produces the domain shapes. The domain never imports it (dependency inversion — the arrow
points inward, exactly like ``FieldConfigMixin`` → ``parameter_service`` in the Flask plane).

Projected row shapes consumed (built by tasks 5.1/5.2/5.3)
----------------------------------------------------------
- ``config#scope``: ``dimensions`` = list of dicts (``key``/``field``/``label``/``enabled``/
  ``values``/``required_for``) → mapped 1:1 onto
  :class:`ScopeDimension`; the whole row → :class:`ScopeConfig`. A **missing row** →
  ``ScopeConfig(tenant_id, dimensions=())`` (tenant-wide), never an error (R1.6).
- ``config#fields``: ``fields`` = ``{name: {key,type,required,label,choices,visible,order}}``
  and ``overrides`` = ``{dotted: {label?,visible?,required?,order?}}`` →
  :class:`TenantOverlay`. The projected ``type`` is a *string*; it is converted to
  :class:`FieldType` (unknown/missing → :data:`FieldType.STRING`). A ``FixedFieldOverride``
  only carries the aspects actually present (a missing aspect stays ``None`` → "leave the
  base as-is"). A **missing row** → ``TenantOverlay()`` (fixed base only), never an error
  (R1.7).
- ``scopegrant#<email>#<dimension>``: ``dimension`` (str), ``values`` (list[str], or
  ``["*"]`` for all-access). :meth:`get_scope_grants` returns ``{dimension: values}`` for the
  **caller's** rows only — filtered by the email segment of the SK, mirroring how
  ``ProjectionGovernanceReader.get_user_roles_by_tenant`` filters ``role#<email>#<role>`` rows
  by ``id_parts[0] == email``. A missing grant is simply **absent** from the map (the edge
  then applies deny-by-default via ``required_for`` — R2.6).

Config + fail-fast (R4.1)
-------------------------
The table name is resolved from ``GOVERNANCE_PROJECTION_TABLE`` via the S3 fail-fast client
(:func:`services.projection_schema.get_projection_table_resource`) — missing/blank throws,
no dangerous default, resolved lazily on first real Query. In production the Lambda's IAM
role grants read on the projection table; ``AWS_ENDPOINT_URL_DYNAMODB`` is left UNSET (real
AWS) and only set for local testing against the T0 ``dynamodb-local`` container.
"""

from __future__ import annotations

from services import projection_schema as schema

from sam.members.domain.field_resolver import (
    AddressMapping,
    AnalyticsConfig,
    AnalyticsRole,
    FixedFieldOverride,
    FunctionalGroup,
    JubileeRule,
    OverlayField,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import EnumOption, FieldType, MemberNumberFormat
from sam.members.domain.scope_dimensions import ScopeConfig, ScopeDimension
from sam.members.domain.view_contexts import ViewContext, default_view_context

__all__ = ["MembersProjectionReader"]

#: The ``config#<id>`` rows the reader consumes. The tokens are the single source in the
#: shared projection schema so the Flask-plane builder and this reader cannot drift.
_CONFIG_ID_SCOPE = schema.CONFIG_ID_SCOPE
_CONFIG_ID_FIELDS = schema.CONFIG_ID_FIELDS
_CONFIG_ID_VIEWS = schema.CONFIG_ID_VIEWS
_CONFIG_ID_MAIL = schema.CONFIG_ID_MAIL


class MembersProjectionReader:
    """Read-only Members config/grant reader backed by the governance projection (C4).

    Implements the S5 domain seams by duck-typing:

    - :meth:`get_scope_config` → :class:`ScopeConfigProvider`
      (``sam.members.domain.scope_dimensions``);
    - :meth:`get_overlay` → :class:`TenantOverlayProvider`
      (``sam.members.domain.field_resolver``);
    - :meth:`get_view_contexts` → :class:`ViewContextsProvider`
      (``sam.members.domain.view_contexts``, S5c task 3.1 — the ``config#views`` sibling row);
    - :meth:`is_mail_enabled` → the tenant's mail-enabled gate flag from the ``config#mail``
      row (pivot-output-actions R0, design §6.3 — the Members edge reads it at request time,
      NO live MySQL);
    - :meth:`get_scope_grants` → the caller's projected scope grants (consumed by the edge's
      ``resolve_scope_access`` wiring, task 8.3).

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

    def _query_partition(self, tenant_id: str) -> list[dict]:
        """Return all projected items for ``tenant_id`` (cached, read-only).

        One DynamoDB ``Query`` on the partition key. A missing/empty partition returns ``[]``
        (empty is valid). boto3 is imported lazily so the module imports cleanly where boto3's
        condition types aren't needed (a fake table in tests can bypass this by pre-seeding
        the cache).
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

    @staticmethod
    def _classify(item: dict) -> tuple[str, tuple[str, ...]]:
        """Return ``(record_type, id_parts)`` for a projected item's sort key.

        A missing/blank sort key classifies as ``("", ())`` so it is simply skipped by the
        callers (never a raise) — empty is valid.
        """
        sk = item.get(schema.SORT_KEY_ATTR, "")
        return schema.split_sort_key(sk) if sk else ("", ())

    # ── ScopeConfigProvider ──────────────────────────────────────────────────────────

    def get_scope_config(self, tenant_id: str) -> ScopeConfig:
        """Return the tenant's :class:`ScopeConfig` from the ``config#scope`` row (R1.4/R1.6).

        Reads the tenant partition, finds the ``config#scope`` row, and rebuilds its
        ``dimensions`` list into :class:`ScopeDimension` objects (mapped 1:1). A **missing**
        row → ``ScopeConfig(tenant_id, dimensions=())`` (tenant-wide), never an error (R1.6).

        Args:
            tenant_id: The tenant (partition key) whose scope config to resolve.

        Returns:
            The tenant's :class:`ScopeConfig` (empty dimensions when unconfigured).
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_SCOPE)
        if row is None:
            return ScopeConfig(tenant_id=tenant_id, dimensions=())

        raw_dimensions = row.get("dimensions") or []
        dimensions = tuple(
            self._build_dimension(raw) for raw in raw_dimensions if isinstance(raw, dict)
        )
        return ScopeConfig(tenant_id=tenant_id, dimensions=dimensions)

    @staticmethod
    def _build_dimension(raw: dict) -> ScopeDimension:
        """Map a projected dimension dict onto a :class:`ScopeDimension` (1:1)."""
        return ScopeDimension(
            key=raw.get("key", ""),
            # `field` binds the dimension to a member field; defaults to the dimension `key`
            # (matching the domain model's back-compat default) when unprojected.
            field=raw.get("field") or raw.get("key"),
            label=dict(raw.get("label") or {}),
            enabled=bool(raw.get("enabled", True)),
            values=tuple(raw.get("values") or ()),
            # s5d clean break (R2.2/R8.1): no `all_wildcard` role-name — a stray projected key
            # is simply ignored; the all-access sentinel lives on the GRANT side as `["*"]`.
            required_for=tuple(raw.get("required_for") or ()),
        )

    # ── TenantOverlayProvider ──────────────────────────────────────────────────────────

    def get_overlay(self, tenant_id: str) -> TenantOverlay:
        """Return the tenant's :class:`TenantOverlay` from the ``config#fields`` row (R1.5/R1.7).

        Reads the tenant partition, finds the ``config#fields`` row, and rebuilds its
        ``fields`` / ``overrides`` maps into :class:`OverlayField` / :class:`FixedFieldOverride`
        objects. A **missing** row → ``TenantOverlay()`` (fixed base only), never an error
        (R1.7).

        Args:
            tenant_id: The tenant (partition key) whose field overlay to resolve.

        Returns:
            The tenant's :class:`TenantOverlay` (empty when unconfigured).
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_FIELDS)
        if row is None:
            return TenantOverlay()

        raw_fields = row.get("fields") or {}
        # The authoring UI writes `fixed_overrides`; older projections used `overrides`. Accept
        # either key so the reader is compatible with both shapes (empty-is-valid).
        raw_overrides = row.get("fixed_overrides") or row.get("overrides") or {}
        raw_groups = row.get("functional_groups") or []
        fields = {
            name: self._build_overlay_field(name, spec)
            for name, spec in raw_fields.items()
            if isinstance(spec, dict)
        }
        overrides = {
            dotted: self._build_override(spec)
            for dotted, spec in raw_overrides.items()
            if isinstance(spec, dict)
        }
        functional_groups = {
            g["key"]: self._build_functional_group(g)
            for g in raw_groups
            if isinstance(g, dict) and g.get("key")
        }
        # member-analytics R9 / C-CONFIG (ODI-2): the analytics config is authored as a SLICE of
        # this same `config#fields` row (an `analytics` object beside `fields`/`fixed_overrides`/
        # `functional_groups`), so it is read here — one projection reader, one row. Empty/absent
        # → `None` (empty-is-valid; the consumer falls back to the documented R9.5 defaults).
        analytics = self._build_analytics(row.get("analytics"))
        return TenantOverlay(
            fields=fields,
            overrides=overrides,
            functional_groups=functional_groups,
            analytics=analytics,
        )

    @classmethod
    def _build_analytics(cls, spec) -> AnalyticsConfig | None:
        """Map a projected analytics slice onto :class:`AnalyticsConfig` (R9, C-CONFIG).

        Degrades gracefully (projected config data, not user input): a missing/non-dict spec, or
        one whose three sub-blocks are all empty, returns ``None`` (empty-is-valid → consumer
        defaults, R9.5). Unknown role keys and malformed sub-values are skipped rather than
        raising — a stray projected token never crashes the field-config read.
        """
        if not isinstance(spec, dict):
            return None

        jubilee = cls._build_jubilee_rule(spec.get("jubilee_rule"))

        field_roles: dict[AnalyticsRole, str] = {}
        raw_roles = spec.get("field_roles")
        if isinstance(raw_roles, dict):
            for role_key, field_key in raw_roles.items():
                if not isinstance(field_key, str) or not field_key:
                    continue
                try:
                    role = AnalyticsRole(role_key)
                except (ValueError, TypeError):
                    continue  # unknown role token → skip (degrade gracefully)
                field_roles[role] = field_key

        address = cls._build_address_mapping(spec.get("address_mapping"))

        config = AnalyticsConfig(
            jubilee_rule=jubilee,
            field_roles=field_roles,
            address_mapping=address,
        )
        return None if config.is_empty() else config

    @staticmethod
    def _build_jubilee_rule(spec) -> JubileeRule | None:
        """Map a projected ``jubilee_rule`` dict onto :class:`JubileeRule` (R9.2).

        ``years`` keeps only int-coercible entries; ``multiple_of`` keeps a positive int. An
        empty/absent/all-malformed spec → ``None`` (the consumer applies the default multiples-
        of-5, R9.5 — not materialized here).
        """
        if not isinstance(spec, dict):
            return None
        years: list[int] = []
        raw_years = spec.get("years")
        if isinstance(raw_years, (list, tuple)):
            for y in raw_years:
                if isinstance(y, bool):
                    continue
                try:
                    years.append(int(y))
                except (ValueError, TypeError):
                    continue
        multiple_of = spec.get("multiple_of")
        if isinstance(multiple_of, bool) or not isinstance(multiple_of, int) or multiple_of <= 0:
            multiple_of = None
        rule = JubileeRule(
            years=tuple(years) if years else None,
            multiple_of=multiple_of,
        )
        return None if rule.is_empty() else rule

    @staticmethod
    def _build_address_mapping(spec) -> AddressMapping | None:
        """Map a projected ``address_mapping`` dict onto :class:`AddressMapping` (R9.4).

        Each line is a resolvable field KEY (a string); non-string/empty values are dropped. An
        empty/absent spec → ``None`` (the consumer makes PDF labels unavailable with a reason,
        R4.10; CSV always works).
        """
        if not isinstance(spec, dict):
            return None

        def _key(name: str) -> str | None:
            v = spec.get(name)
            return v if isinstance(v, str) and v else None

        mapping = AddressMapping(
            name=_key("name"),
            street=_key("street"),
            postcode=_key("postcode"),
            city=_key("city"),
            country=_key("country"),
            region=_key("region"),
        )
        return None if mapping.is_empty() else mapping

    @staticmethod
    def _build_functional_group(spec: dict) -> FunctionalGroup:
        """Map a projected functional-group catalog entry onto a :class:`FunctionalGroup` (R4.9)."""
        return FunctionalGroup(
            key=str(spec.get("key", "")),
            label=dict(spec.get("label") or {}),
            order=int(spec.get("order", 0) or 0),
        )

    @staticmethod
    def _build_options(specs) -> tuple[EnumOption, ...] | None:
        """Map projected enum-option specs (``{value,label,roles?}``) onto :class:`EnumOption`s.

        A missing/empty list → ``None`` (no rich options); malformed entries are skipped
        (empty-is-valid — projected config data degrades gracefully rather than raising).
        """
        if not specs or not isinstance(specs, (list, tuple)):
            return None
        options = []
        for o in specs:
            if not isinstance(o, dict) or "value" not in o:
                continue
            roles = o.get("roles")
            options.append(
                EnumOption(
                    value=str(o["value"]),
                    label=dict(o.get("label") or {}),
                    roles=tuple(roles) if roles else None,
                )
            )
        return tuple(options) if options else None

    @staticmethod
    def _build_member_number_format(spec) -> MemberNumberFormat | None:
        """Map a projected member-number format spec onto a :class:`MemberNumberFormat` (task 1.4b)."""
        if not isinstance(spec, dict):
            return None
        fmt = MemberNumberFormat(
            prefix=str(spec.get("prefix", "") or ""),
            width=int(spec.get("width", 0) or 0),
            regex=spec.get("regex") or None,
        )
        return None if fmt.is_empty() else fmt

    @staticmethod
    def _to_field_type(value) -> FieldType:
        """Convert a projected ``type`` string to :class:`FieldType`.

        Unknown/missing values default to :data:`FieldType.STRING` — a projected type token is
        config data, not user input, so a stray value degrades gracefully rather than raising.
        """
        if isinstance(value, FieldType):
            return value
        try:
            return FieldType(value)
        except (ValueError, TypeError):
            return FieldType.STRING

    @classmethod
    def _build_overlay_field(cls, name: str, spec: dict) -> OverlayField:
        """Map a projected variable-field spec onto an :class:`OverlayField`.

        ``functional_group`` (R4.9) is the field's display group referencing the tenant's
        ``functional_groups`` catalog; it MUST be carried so an added field is sectioned by
        FUNCTION, not by its storage bucket. ``options`` (rich enum {value,label,roles}) and
        ``show_when`` (conditional visibility) are reconstructed when the projection carries them.
        """
        choices = spec.get("choices")
        options = cls._build_options(spec.get("options"))
        return OverlayField(
            key=spec.get("key") or name,
            type=cls._to_field_type(spec.get("type")),
            required=bool(spec.get("required", False)),
            label=dict(spec.get("label") or {}),
            choices=tuple(choices) if choices is not None else None,
            options=options,
            functional_group=spec.get("functional_group") or None,
            show_when=spec.get("show_when") or None,
            visible=bool(spec.get("visible", True)),
            order=int(spec.get("order", 0) or 0),
        )

    @staticmethod
    def _build_override(spec: dict) -> FixedFieldOverride:
        """Map a projected fixed-field override onto a :class:`FixedFieldOverride`.

        Only the aspects actually present are passed through; a missing aspect stays ``None``
        so the resolver leaves the base value as-is (design C4 override semantics).
        ``functional_group`` (R4.9) reassigns the field's display group — it is carried
        through so an authored fixed/calculated-field group reassignment reaches the resolved
        field (``FieldResolver._apply_override`` / ``_as_calculated_field`` already read it).
        """
        label = spec.get("label")
        visible = spec.get("visible")
        required = spec.get("required")
        order = spec.get("order")
        functional_group = spec.get("functional_group")
        return FixedFieldOverride(
            label=dict(label) if isinstance(label, dict) else None,
            visible=bool(visible) if visible is not None else None,
            required=bool(required) if required is not None else None,
            order=int(order) if order is not None else None,
            functional_group=str(functional_group) if functional_group else None,
        )

    # ── ViewContextsProvider (S5c task 3.1) ────────────────────────────────────────────

    def get_view_contexts(self, tenant_id: str) -> tuple[ViewContext, ...]:
        """Return the tenant's view contexts from the ``config#views`` row (S5c C-VIEW, R5.1).

        Reads the tenant partition, finds the sibling ``config#views`` row (the settled
        projection shape — Open Design Item 1), and rebuilds its ``contexts`` list into
        :class:`ViewContext` objects. **Empty-is-valid (R5.1):** a **missing** ``config#views``
        row, an **empty** ``contexts`` list, or a row with no well-formed context all collapse
        to **exactly one** :func:`~sam.members.domain.view_contexts.default_view_context` —
        over all visible fields — never an error and never an empty tuple.

        Storage-agnostic per the module pattern: this reader reconstructs the plain
        :class:`ViewContext` shape; it does NOT resolve column ``field_key``s against the field
        config (that skip-on-unresolvable is the SPA's at render, and the fail-fast rejection is
        the Flask-plane validator's at Save — R5.1a).

        Args:
            tenant_id: The tenant (partition key) whose view contexts to resolve.

        Returns:
            The tenant's view contexts — always ≥1 (a single default when unconfigured).
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_VIEWS)
        if row is None:
            return (default_view_context(),)

        raw_contexts = row.get("contexts") or []
        contexts = tuple(
            self._build_view_context(raw)
            for raw in raw_contexts
            if isinstance(raw, dict) and raw.get("key")
        )
        # Empty-is-valid: an absent/empty/all-malformed contexts list → one default context.
        return contexts if contexts else (default_view_context(),)

    @staticmethod
    def _build_view_context(raw: dict) -> ViewContext:
        """Map a projected view-context dict onto a :class:`ViewContext` (1:1, R5.1).

        Malformed sub-values degrade gracefully (projected config data, not user input):
        non-list ``columns``/``filterable_columns``/``permission_roles`` fall back to empty,
        a non-mapping ``default_sort`` to ``None``, a non-int ``page_size`` to ``None``.
        """
        def _str_list(value) -> tuple[str, ...]:
            if not isinstance(value, (list, tuple)):
                return ()
            return tuple(str(v) for v in value if isinstance(v, str))

        default_sort = raw.get("default_sort")
        if not isinstance(default_sort, dict):
            default_sort = None

        page_size = raw.get("page_size")
        if not isinstance(page_size, int) or isinstance(page_size, bool):
            page_size = None

        return ViewContext(
            key=str(raw.get("key", "")),
            label=dict(raw.get("label") or {}),
            permission_roles=_str_list(raw.get("permission_roles")),
            columns=_str_list(raw.get("columns")),
            filterable_columns=_str_list(raw.get("filterable_columns")),
            default_sort=dict(default_sort) if default_sort is not None else None,
            page_size=page_size,
        )

    # ── Mail-enabled gate (pivot-output-actions R0, design §6.3) ───────────────────────

    def is_mail_enabled(self, tenant_id: str) -> bool:
        """Return whether the tenant is cleared to send mail, from ``config#mail`` (R0).

        Reads the tenant partition, finds the ``config#mail`` row (the per-tenant
        "mail-enabled / SES-certified" onboarding gate authored on the Flask plane
        as ``members.mail_enabled`` and projected by ``build_config_mail_row``), and
        returns its ``mail_enabled`` boolean. The Members edge calls this at request
        time to decide whether to offer the mail output actions (R1–R5) — a Lambda
        NEVER queries MySQL for the flag (ADR 0005/0006); it reads only this
        projected row.

        Fail-closed (R0): a **missing** ``config#mail`` row, a missing
        ``mail_enabled`` attribute, or any non-boolean-``True`` value all resolve to
        ``False``. The gate opens only on an explicit projected ``True`` — the
        absence of the projection never permits sending. Never raises on
        missing/empty data (empty-is-valid, same discipline as the sibling config
        readers).

        Args:
            tenant_id: The tenant (partition key) whose mail gate to resolve.

        Returns:
            ``True`` iff the tenant's projected ``config#mail`` row carries
            ``mail_enabled`` == ``True``; ``False`` otherwise (fail-closed).
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_MAIL)
        if row is None:
            return False
        return row.get("mail_enabled") is True

    # ── Scope grants (consumed by the edge, task 8.3) ──────────────────────────────────

    def get_scope_grants(self, tenant_id: str, email: str) -> dict[str, list[str]]:
        """Return ``{dimension -> [values] | ["*"]}`` for ``email`` in ``tenant_id`` (R2.3).

        Reads the tenant partition and keeps the ``scopegrant#<email>#<dimension>`` rows whose
        email segment equals ``email`` (mirroring the role-filter in
        ``ProjectionGovernanceReader.get_user_roles_by_tenant``). Each kept row contributes
        ``{dimension: values}``, where ``values`` is the granted subset or ``["*"]`` for
        all-access. A dimension with no grant for this caller is simply **absent** from the
        map — the edge then applies deny-by-default via ``required_for`` (R2.6). Never raises
        on missing/empty data.

        Args:
            tenant_id: The tenant (partition key) to read grants from.
            email: The calling user's email (from the verified token).

        Returns:
            ``{dimension: values}`` for the caller's granted dimensions only (possibly empty).
        """
        grants: dict[str, list[str]] = {}
        if not email:
            return grants
        for item in self._query_partition(tenant_id):
            record_type, id_parts = self._classify(item)
            if record_type != schema.RECORD_TYPE_SCOPEGRANT:
                continue
            # scopegrant#<email>#<dimension> — id_parts == (email, dimension). Filter to caller.
            if len(id_parts) < 2 or id_parts[0] != email:
                continue
            # Prefer the explicit 'dimension' attr if present; else the key segment.
            dimension = item.get("dimension") or id_parts[1]
            values = item.get("values") or []
            grants[dimension] = list(values)
        return grants

    # ── internals ──────────────────────────────────────────────────────────────────────

    def _find_config_row(self, tenant_id: str, config_id: str) -> dict | None:
        """Return the ``config#<config_id>`` row for ``tenant_id``, or ``None`` if absent.

        A missing row is valid (the caller collapses it to the empty/tenant-wide default);
        this never raises on missing/empty data.
        """
        for item in self._query_partition(tenant_id):
            record_type, id_parts = self._classify(item)
            if record_type != schema.RECORD_TYPE_CONFIG:
                continue
            if id_parts and id_parts[0] == config_id:
                return item
        return None
