"""Field-overlay + wire-shape reads for the Members projection config reader (design C4).

INTERNAL helper module of :mod:`sam.members.repository.projection_config_reader` — extracted
from the large reader class (code-quality file-length split, 2026-10-28) with **zero behaviour
change**. :class:`_FieldOverlayReadMixin` is composed into the public
``MembersProjectionReader``; it relies on the shared read infrastructure from
:class:`_config_reader_base._ConfigReaderBase` (``_find_config_row``) resolved via the composed
class' MRO. Nothing imports this module directly except the reader facade — but note that the
field-build static methods (e.g. ``MembersProjectionReader._build_override`` /
``._build_overlay_field``) stay reachable as attributes of the composed class, which tests and
the Change-Op CRUD service call.
"""

from __future__ import annotations

from collections.abc import Mapping

from services import projection_schema as schema

from sam.members.domain.field_formats import known_tokens
from sam.members.domain.field_resolver import (
    FieldScope,
    FixedFieldOverride,
    FunctionalGroup,
    OverlayField,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import (
    EnumOption,
    FieldFormat,
    FieldType,
    MemberNumberFormat,
)

from sam.members.repository._config_reader_base import (
    _CONFIG_ID_FIELDS,
    _normalize_functional_groups,
)


class MalformedOptionsError(ValueError):
    """A projected field's ``options`` vocabulary is present but not a canonical shape (C5/F3).

    The single-vocabulary model (spec 03a) surfaces ONE ``options`` of canonical entries
    ``{value, label?, roles?}``. A present-but-unexpected shape — a bare string, a scalar, a
    non-list, or a dict with no ``value`` — is NO LONGER silently coerced or degraded to ``None``
    (the retired F1/F2/F3 fallbacks); it is a LOUD, diagnosable failure raised here at the read
    build.

    Subclasses :class:`ValueError` so an edge can map it to a caller-safe 400/500 (steering 30):
    the message is GENERIC and does not echo the offending data; the actual malformed shape is
    recorded on :attr:`shape_repr` for server-side logging under a correlation id (never returned
    to the client).

    NOTE (task 9 / C6): the uniform fail-loud error TYPE across the whole read-assembly seam is
    standardized by a later task. This dedicated, clearly-named raise is the reasonable interim
    boundary error for the reader; C6 will fold it into the uniform taxonomy.
    """

    def __init__(self, shape):
        #: A SHORT, bounded repr of the offending shape for server-side diagnosis (NOT the raw
        #: value — bounded so a large/garbage payload cannot bloat a log line). Never surfaced to
        #: the client.
        self.shape_repr = f"{type(shape).__name__}: {repr(shape)[:120]}"
        super().__init__(
            "config#fields field carries a malformed `options` vocabulary "
            "(expected a list of {value, label?, roles?} entries)"
        )


class _FieldOverlayReadMixin:
    """The ``TenantOverlayProvider`` + authoring-wire + page-size/slug/version reads."""

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
        # Read the PROJECTED `config#fields.overrides` attribute. R6.8 keeps this projected
        # attribute name as `overrides` until Phase 3, so this is the live canonical read path.
        # The legacy INPUT dual-accept was dropped on the Flask builder side (it authors from
        # `fixed_overrides` only); the dead `row.get("fixed_overrides")` read branch is removed
        # here, since no builder emits that attribute onto the projected row.
        raw_overrides = row.get("overrides") or {}
        # DUAL-READ (spec 03, design C6 / review Must-fix #4): accept BOTH the legacy LIST and the
        # new MAP ``functional_groups`` storage shape, normalized to a MAP keyed by group key. This
        # is what lets the LIST→MAP migration roll out without a flag day — a legacy LIST row and a
        # migrated MAP row resolve to the SAME :class:`TenantOverlay`.
        raw_groups = _normalize_functional_groups(row.get("functional_groups"))
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
            gkey: self._build_functional_group(entry)
            for gkey, entry in raw_groups.items()
        }
        return TenantOverlay(
            fields=fields,
            overrides=overrides,
            functional_groups=functional_groups,
        )

    def get_raw_fields_overlay(
        self, tenant_id: str, *, consistent_read: bool = False
    ) -> dict:
        """Return the stored ``config#fields`` overlay in the AUTHORING WIRE shape — the
        round-trip seed for the editors (spec 11 bugfix; one-key contract).

        ``consistent_read`` (spec 03 task 2.3): the Change-Op CRUD service passes
        ``consistent_read=True`` so the validate-and-place read is STRONGLY-CONSISTENT (design C1
        step 1 / design-review Should-fix) — the flag flows through to the repository ``Query``
        (:meth:`_query_partition`). The editors' normal round-trip read keeps the default
        (cached, eventually-consistent) behaviour.

        The authoring editors (Application Form Builder + the Field-configuration editor) hold ONE
        working ``field_overlay`` object, then PUT it back WHOLE to ``config#fields`` (the write
        REPLACES the row). For that round-trip to be loss-free AND reliable, GET and PUT must use
        the SAME key names — otherwise a stored selection reads back under a key the editor does not
        inspect and renders as "not selected" even though it persisted.

        THE ONE-KEY CONTRACT (authoritative, do not reintroduce a second translator):

        - **Storage** (the DynamoDB ``config#fields`` row) uses the attribute ``overrides`` for the
          fixed-field override map. This is the resolver's canonical read key (:meth:`get_overlay`)
          and the public-form path — it is NOT changed here and must stay ``overrides`` at rest.
        - **The authoring WIRE shape** uses ``fixed_overrides`` — the key the whole frontend
          overlay model (``overlayModel`` + ``MembersFieldModal`` + the Application Form Builder)
          reads and writes, and the key the SAM write path already accepts.
        - **This reader is the SINGLE read-side translator**: it serves the stored ``overrides``
          map UNDER the wire key ``fixed_overrides``. Its symmetric counterpart is the write path's
          ``fixed_overrides`` → ``overrides`` normalization (``ConfigWriteService``). Those two
          boundary functions are the ONLY places storage↔wire key translation happens — the
          frontend needs NO normalizer, so read and write are symmetric by construction.

        A **missing** row → ``{"fields": {}, "fixed_overrides": {}, "functional_groups": {}}``
        (empty-is-valid, never an error). **``functional_groups`` is a MAP keyed by group key**
        (spec 03, design C6 / D2a) — the new, truncation-proof storage shape; the LIST→MAP
        migration (D2a) converts legacy rows, and this reader DUAL-READS both shapes
        (:func:`_normalize_functional_groups`) so a pre-migration LIST row and a migrated MAP row
        serve the SAME wire map during rollout (review Must-fix #4). Carries the per-field
        application attributes (``application_visible`` / ``application_required`` /
        ``application_choices`` / ``format``) and every other authored key THROUGH unchanged,
        because the editor writes them back unchanged. The write path stays the authoritative
        validator (R8).
        """
        row = self._find_config_row(
            tenant_id, _CONFIG_ID_FIELDS, consistent_read=consistent_read
        )
        if row is None:
            return {"fields": {}, "fixed_overrides": {}, "functional_groups": {}}
        raw_fields = row.get("fields")
        # Storage key is ``overrides``; serve it under the authoring WIRE key ``fixed_overrides``
        # (the one-key contract above) so the editor's read matches its write with no client-side
        # translation. Storage at rest is unchanged — only the served shape is normalized here.
        raw_overrides = row.get("overrides")
        # DUAL-READ + MAP normalize (spec 03, design C6): serve ``functional_groups`` as a MAP keyed
        # by group key regardless of whether the stored row is a legacy LIST or a migrated MAP, so
        # the round-trip seed is shape-stable across the migration rollout (review Must-fix #4).
        wire = {
            "fields": raw_fields if isinstance(raw_fields, dict) else {},
            "fixed_overrides": raw_overrides if isinstance(raw_overrides, dict) else {},
            "functional_groups": _normalize_functional_groups(
                row.get("functional_groups")
            ),
        }
        # Application-form slug + publish-state (spec 12 Task 1.1 / R4, design §Data Models): carry
        # the form's own ``slug`` plus ``published_at`` / ``published_version`` THROUGH on the raw
        # round-trip so a plain fields save reads them back and the write service can preserve them
        # (publish owns ``published_*``, Task 2.2). Only surfaced when STORED — a pre-slug row omits
        # them, so the empty-is-valid shape above is unchanged for a never-slugged tenant.
        for attr in ("slug", "published_at", "published_version"):
            if attr in row:
                wire[attr] = row.get(attr)
        return wire

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
        """Map projected enum-option specs onto :class:`EnumOption`s — ONE canonical shape (C5/F3).

        A selectable field has ONE vocabulary: ``options``, a list of RICH canonical entries
        ``{value, label{nl,en}?, roles?}`` (the authoring UI / Flask builder shape). This reader
        surfaces exactly that — there is no longer a second ``choices`` shape to coalesce (F1/F2)
        and no bare-string coercion / degrade-to-``None`` branch (F3). The retired behaviours:

        - the bare-string ``"man"`` coercion (a legacy ``choices`` value) is GONE — legacy
          bare-``choices`` rows are migrated to value-only ``options`` by C7, so a bare string here
          is now an UNEXPECTED shape, not something to silently coerce;
        - silently SKIPPING a malformed entry (a dict with no ``value``, a non-dict entry) is GONE
          — a malformed entry no longer degrades to ``None``; it is a LOUD, diagnosable error.

        Returns:
            A tuple of :class:`EnumOption` when ``specs`` carries canonical entries; ``None`` when
            ``specs`` is absent/empty (a legitimately empty vocabulary — the "declared source
            present but empty" ASYMMETRY is the seam's fail-loud concern, C6/task 9, not here).

        Raises:
            MalformedOptionsError: when ``specs`` is present but not a list/tuple of canonical
                ``{value, ...}`` entries (an unexpected shape — e.g. a bare string, a dict without
                a ``value``, a scalar). Caller-safe + diagnosable (a generic message; the offending
                shape is logged, not echoed). (NOTE: task 9/C6 will standardize the uniform
                fail-loud error TYPE across the seam; this is a reasonable, clearly-named raise
                until then.)
        """
        if specs is None:
            return None
        if not isinstance(specs, (list, tuple)):
            raise MalformedOptionsError(specs)
        if not specs:
            return None
        options = []
        for o in specs:
            if not isinstance(o, dict) or "value" not in o:
                raise MalformedOptionsError(o)
            roles = o.get("roles")
            options.append(
                EnumOption(
                    value=str(o["value"]),
                    label=dict(o.get("label") or {}),
                    roles=tuple(roles) if roles else None,
                )
            )
        return tuple(options)

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

    @staticmethod
    def _build_field_scope(spec) -> FieldScope | None:
        """Map a projected field ``scope`` attribute onto :class:`FieldScope` (Phase 3 step 9, R2.1).

        The SAM READ representation of scope-binding as a field attribute: a projected
        ``config#fields`` field (added variable field or a fixed-field override) may carry a
        ``scope`` object ``{enabled, values, label?, required_for?}``. A missing/non-dict spec →
        ``None`` (the field is not a scope axis). Read-only re-presentation only — scope
        RESOLUTION continues to consume the ``config#scope`` row (``ScopeConfig``) UNCHANGED
        (R2.3); this attribute is carried verbatim and the resolver never reads it.

        **Single-vocabulary collapse (C5/F7).** A scope axis has ONE vocabulary, so this builds
        the scope's canonical ``options`` from the stored value list and lets
        :class:`FieldScope` DERIVE ``.values`` from it (``tuple(o.value for o in options)``) — the
        values are NOT stored as an independent second copy. This removes the
        ``FieldScope(values=())`` divergence by construction: there is only one stored list, so
        ``options`` and ``values`` can never disagree. Non-string stored values are dropped
        (projected config data; the vocabulary list stays well-formed).
        """
        if not isinstance(spec, dict):
            return None
        options = tuple(
            EnumOption(value=v)
            for v in (spec.get("values") or ())
            if isinstance(v, str) and v
        )
        required_for = tuple(
            r for r in (spec.get("required_for") or ()) if isinstance(r, str) and r
        )
        return FieldScope(
            enabled=bool(spec.get("enabled", True)),
            options=options,
            label=dict(spec.get("label") or {}),
            required_for=required_for,
        )

    @staticmethod
    def _build_format(spec) -> FieldFormat | None:
        """Map a projected ``format`` sub-object onto a :class:`FieldFormat` (R7.1/R7.3; seam c).

        The declarative field-validator attribute: a projected ``config#fields`` field (overlay
        field or fixed-field override) may carry a ``format`` object ``{checker, params}`` naming
        a PLATFORM-DEFINED checker token (``EMAIL`` / ``IBAN`` / …). This reader rebuilds it onto
        the field so the public field-config read + create validator (tasks 3.4/4.1) can enforce
        it.

        **DEGRADES gracefully — never raises (R7.3).** A stray or outdated token must never crash
        the field-config read, so this returns ``None`` (no extra checker beyond ``type`` /
        ``required``) for every non-usable spec:

        - a missing / non-dict spec (the field carries no format);
        - a missing / non-string / empty ``checker`` (malformed shape);
        - an **unknown token** — a ``checker`` that is not in the registry's
          :func:`~sam.members.domain.field_formats.known_tokens` platform set (e.g. a token a
          since-removed checker once defined, or a typo). Validating the token against the
          registry HERE means a resolved field never carries a format the validator cannot run.

        ``params`` is carried verbatim as a mapping when it is one, else dropped to ``{}`` (the
        checker reads it; a non-mapping is treated as "no params" rather than a crash). This
        mirrors the degrade-on-garbage discipline of :meth:`_build_options` /
        :meth:`_build_member_number_format` / :meth:`_build_field_scope` — projected config data
        degrades gracefully, it is never user input that should surface an error.
        """
        if not isinstance(spec, dict):
            return None
        checker = spec.get("checker")
        if not isinstance(checker, str) or not checker:
            return None
        # Degrade on an UNKNOWN token (R7.3): a checker not in the platform-defined registry set
        # is dropped rather than carried, so no resolved field names a checker the validator
        # cannot run. A stray token never crashes the read — it is simply not enforced.
        if checker not in known_tokens():
            return None
        params = spec.get("params")
        return FieldFormat(
            checker=checker,
            params=dict(params) if isinstance(params, Mapping) else {},
        )

    @classmethod
    def _build_overlay_field(cls, name: str, spec: dict) -> OverlayField:
        """Map a projected variable-field spec onto an :class:`OverlayField`.

        ``functional_group`` (R4.9) is the field's display group referencing the tenant's
        ``functional_groups`` catalog; it MUST be carried so an added field is sectioned by
        FUNCTION, not by its storage bucket. ``options`` (rich enum {value,label,roles}) and
        ``show_when`` (conditional visibility) are reconstructed when the projection carries them.

        The four public member-application attributes (D20; R4.2/R4a/R4b/R7.1) ride as sibling
        keys and are carried 1:1: ``application_visible`` / ``application_required`` (bools,
        default ``False`` → field off the public form), ``application_choices`` (the enum
        application SUBSET, ``None`` = full set), and ``format`` (the declarative validator,
        degraded to ``None`` on an unknown/malformed token by :meth:`_build_format`).

        **Single-vocabulary collapse (C5/F2).** A selectable field has ONE vocabulary — the
        canonical ``options``. This reader NO LONGER reads a separate ``choices`` attribute off the
        spec nor carries it onto the overlay field; the dead ``choices`` shape is retired (migrated
        to ``options`` by C7). An unexpected ``options`` shape raises loudly (:meth:`_build_options`
        → :class:`MalformedOptionsError`) rather than silently degrading.
        """
        options = cls._build_options(spec.get("options"))
        application_choices = spec.get("application_choices")
        return OverlayField(
            key=spec.get("key") or name,
            type=cls._to_field_type(spec.get("type")),
            required=bool(spec.get("required", False)),
            label=dict(spec.get("label") or {}),
            options=options,
            functional_group=spec.get("functional_group") or None,
            show_when=spec.get("show_when") or None,
            visible=bool(spec.get("visible", True)),
            order=int(spec.get("order", 0) or 0),
            # Phase 3 step 9 (R2.1): carry the field's scope-axis attribute (SAM read repr).
            scope=cls._build_field_scope(spec.get("scope")),
            # Public member-application attributes (D20; R4.2/R4a/R4b). Defaults keep an
            # un-authored variable field OFF the public form with full choices.
            application_visible=bool(spec.get("application_visible", False)),
            application_required=bool(spec.get("application_required", False)),
            application_choices=(
                tuple(application_choices) if application_choices is not None else None
            ),
            format=cls._build_format(spec.get("format")),
        )

    @classmethod
    def _build_override(cls, spec: dict) -> FixedFieldOverride:
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
        # Public member-application attributes (D20; R4.2/R4a/R4b). On an OVERRIDE these are
        # `None` when absent ("leave the base value as-is"), consistent with every other
        # override aspect — an override that touches none of them does not change the fixed
        # field's application behaviour. A present bool is coerced; `application_choices` is
        # carried as a tuple when present, else `None` (full set).
        application_visible = spec.get("application_visible")
        application_required = spec.get("application_required")
        application_choices = spec.get("application_choices")
        # Enum values on an OVERRIDE of a fixed enum (e.g. membership.status): ONE canonical
        # vocabulary — the override's `options`. The legacy `options or choices` coalesce (F1) and
        # the separate `choices` source (F2) are RETIRED: a selectable field resolves through its
        # single `options`, legacy bare-`choices` rows are migrated to `options` by C7, and an
        # unexpected `options` shape raises loudly (`_build_options` → MalformedOptionsError)
        # rather than silently coercing or dropping to the fixed field's base choices.
        override_options = cls._build_options(spec.get("options"))
        return FixedFieldOverride(
            label=dict(label) if isinstance(label, dict) else None,
            visible=bool(visible) if visible is not None else None,
            required=bool(required) if required is not None else None,
            order=int(order) if order is not None else None,
            functional_group=str(functional_group) if functional_group else None,
            options=override_options,
            # Phase 3 step 9 (R2.1): carry a fixed field's scope-axis attribute (SAM read repr).
            scope=cls._build_field_scope(spec.get("scope")),
            application_visible=(
                bool(application_visible) if application_visible is not None else None
            ),
            application_required=(
                bool(application_required) if application_required is not None else None
            ),
            application_choices=(
                tuple(application_choices) if application_choices is not None else None
            ),
            format=cls._build_format(spec.get("format")),
        )

    # ── Pagination default (Phase 2 step (a) — the view_contexts.page_size re-home) ────

    def get_default_page_size(self, tenant_id: str) -> int | None:
        """Return the tenant's default rows-per-page from the ``config#fields`` row (R2.1).

        Phase 2 re-homes the per-context ``view_contexts.page_size`` to a SINGLE
        tenant-level ``default_page_size`` scalar carried on the EXISTING ``config#fields``
        row (NOT a new ``config#views`` row — ``38`` rule 3: pagination is a default, not a
        stored view object). The Members edge surfaces this on the ``GET /members/field-config``
        response so the SPA can resolve rows-per-page as
        ``userPreference ?? default_page_size ?? platformDefault``.

        Shares the per-invocation partition cache with the sibling config reads (one Query
        per tenant). Empty-is-valid / fail-safe (R2.4): a **missing** ``config#fields`` row,
        a missing/``None`` ``default_page_size`` attribute, or any non-positive / non-int /
        boolean value all resolve to ``None`` — the renderer then falls back to the per-user
        preference and finally the platform table-toolkit default (today's behaviour when a
        ``view_context.page_size`` was null). The Flask builder already guards the value to a
        positive int at projection time; this is the symmetric read-side guard so a stray
        stored value never surfaces a zero/negative default. Never raises on missing/empty
        data.

        Args:
            tenant_id: The tenant (partition key) whose default page size to resolve.

        Returns:
            The projected ``default_page_size`` as a positive int, or ``None`` when
            absent/unusable (fall back to the per-user preference / platform default).
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_FIELDS)
        if row is None:
            return None
        page_size = row.get("default_page_size")
        if isinstance(page_size, bool) or not isinstance(page_size, int):
            return None
        return page_size if page_size > 0 else None

    # ── Forward slug reader (tenant → slug, spec 12 Task 1.3 / R4; design C3) ───────────

    def get_form_slug(self, tenant_id: str) -> str | None:
        """Return the tenant's application-form ``slug`` from ``config#fields``, or ``None``.

        The FORWARD half of the spec-12 slug mapping (design C3): tenant → slug, resolved by the
        NORMAL ``tenant_id``-pinned partition read (the same shared, cached Query the sibling
        config reads use). The form's own public ``slug`` was added to the ``config#fields`` row by
        Task 1.1 and is carried through the authoring round-trip by :meth:`get_raw_fields_overlay`;
        this accessor is the RESOLVED read of it (e.g. the publish path / the slug-display surface
        reads a tenant's current slug here).

        The REVERSE lookup (slug → ``tenant_id``) deliberately does NOT live on this
        ``tenant_id``-PK table — a slug-keyed item would break its structural-isolation invariant
        (``template.yaml``). That is the ``_slugs/{slug}`` bucket marker (OQ4,
        :class:`sam.members.repository.slug_marker_store.S3SlugMarkerStore`), NOT this reader.

        Empty-is-valid / fail-safe (same discipline as :meth:`get_default_page_size`): a **missing**
        ``config#fields`` row, a missing ``slug`` attribute, or a non-string / blank value all
        resolve to ``None`` (the tenant has no public form address yet) — never a raise, never a
        guessed slug.

        Args:
            tenant_id: The tenant (partition key) whose form slug to resolve.

        Returns:
            The projected non-blank ``slug`` string, or ``None`` when absent/unusable.
        """
        row = self._find_config_row(tenant_id, _CONFIG_ID_FIELDS)
        if row is None:
            return None
        slug = row.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            return None
        return slug.strip()

    def get_config_fields_version(
        self, tenant_id: str, *, consistent_read: bool = False
    ):
        """Return the ``config#fields`` row's optimistic-lock ``version`` for the Change-Op path.

        This is the CONTROL-PLANE read the Change-Op CRUD service (spec 03 task 2.3) uses to
        resolve its ``base_version`` sentinel — DELIBERATELY SEPARATE from
        :meth:`get_raw_fields_overlay`, which serves the AUTHORING WIRE shape and MUST NOT carry
        ``version`` (that wire body is surfaced to the frontend under ``field_overlay``; the raw
        overlay's contract is the stored ``{fields, overrides, functional_groups}`` *minus key and
        version* — see ``test_members_projection_reader.py``). Mixing the control ``version`` into
        the authoring wire shape would leak it into an API response, so the service reads it HERE
        instead.

        ``consistent_read`` flows to :meth:`_find_config_row` → :meth:`_query_partition` so the
        validate-and-place read is STRONGLY-CONSISTENT (design C1 step 1 / design-review
        Should-fix) and a stale eventually-consistent version can never produce a spurious 409.

        Returns:
            A tuple ``(present, version)``: ``present`` is ``True`` when a ``config#fields`` row
            EXISTS for the tenant (so the service can distinguish an existing legacy row with no
            ``version`` from no row at all — base_version case ii vs iii), and ``version`` is that
            row's :data:`~services.projection_schema.VERSION_ATTR` value (or ``None`` when the row
            is absent or legacy/versionless). A missing row → ``(False, None)`` (empty-is-valid,
            never a raise).
        """
        row = self._find_config_row(
            tenant_id, _CONFIG_ID_FIELDS, consistent_read=consistent_read
        )
        if row is None:
            return (False, None)
        return (True, row.get(schema.VERSION_ATTR))
