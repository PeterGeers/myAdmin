"""
SAM config-write **domain service** (spec 02, design C2 — Task 1.5).

The domain seam between the Members Lambda edge (Component 1) and the write repository
(:class:`sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository`,
Component 3). It takes a validated-at-the-edge ``(tenant_id, config_id, body)`` write, shapes the
body into the EXACT projected attribute shape the read reader
(:class:`sam.members.repository.projection_config_reader.MembersProjectionReader`) reads back for
that ``config_id``, stamps the row-level monotonic version
(:func:`sam.members.domain.config_write_version.next_write_stamp`), and delegates persistence to
the repository.

Layering (dependency inversion — the arrow points inward, R: design C2)
-----------------------------------------------------------------------
This is a **domain** service: it contains NO ``boto3`` and NO DynamoDB / table resolution. It
depends only on the pure version helper and on a repository that exposes a
``put_config(tenant_id, config_id, attributes, version)`` method — in production the concrete
:class:`MembersConfigWriteRepository`, in tests an in-memory fake. The route holds no business
logic; the domain holds no persistence. This mirrors how the read reader is the infrastructure
adapter the domain never imports.

Per-``configId`` body-validation seam
--------------------------------------
Each SAM-owned ``config#*`` id has its own body validator that shapes + checks only that id's
attributes. **This task (1.5) implements the ``fields`` validator**; ``scope`` (Task 2/3) and
``mail`` (Task 3/5) land in their own steps and are wired into the same seam then. The validators
raise :class:`ConfigWriteValidationError` on a malformed body so the edge can map it to a 400 — a
deliberate, caller-safe validation error, DISTINCT from an unexpected exception (SAM-plane error
conventions, steering 35).

``config#fields`` authoring (Requirement 7)
-------------------------------------------
For ``fields`` the service authors ``fields`` / ``overrides`` / ``functional_groups`` ONLY, in the
shape ``MembersProjectionReader.get_overlay`` reads (R7.1). It does **NOT** author a
``default_page_size`` attribute — the tenant-level rows-per-page default is RETIRED in favor of the
per-user runtime selector (R7.2 / Requirement 25). Each per-field ``scope`` sub-object is preserved
**verbatim** on the written row so Task 2 can DERIVE ``config#scope`` from it (R7.3); this service
never reshapes or drops a field's ``scope`` attribute.
"""

from __future__ import annotations

from collections.abc import Mapping

from services import projection_schema as schema

from sam.members.domain import field_formats
from sam.members.domain.config_write_version import next_write_stamp
from sam.members.domain.fixed_fields import field_by_key

__all__ = [
    "ConfigWriteService",
    "ConfigWriteValidationError",
]

#: The storage bucket variable (overlay) fields live under (mirrors field_resolver.OVERLAY_GROUP /
#: the retired Flask ``members_config_validation.OVERLAY_GROUP``). Used ONLY to build a stable,
#: caller-safe dotted error key for a variable field (``overlay.<key>``) so a rejected write names
#: the offending field the same way across both planes (R8.3/R8.4).
OVERLAY_GROUP = "overlay"


class ConfigWriteValidationError(ValueError):
    """A deliberate, caller-safe config-write body validation error (maps to HTTP 400).

    Raised by a per-``configId`` body validator when the request body is malformed. It is a
    DELIBERATE validation error — distinct from an unexpected exception — so the edge may surface
    its message to the caller (SAM-plane error conventions, steering 35). It subclasses
    :class:`ValueError` so existing ``except ValueError`` seams keep working.
    """


class ConfigWriteService:
    """Domain service that validates, stamps, and persists a SAM-owned ``config#*`` write (C2).

    The edge resolves ``tenant_id`` from the verified token and validates the ``config_id`` path
    segment is one of ``{fields, scope, mail}`` BEFORE calling here; this service then validates
    the per-``configId`` body shape, computes the row-level version stamp, and delegates the
    versioned put to the repository. It holds no persistence (no ``boto3``) — it depends only on
    the pure version helper and the injected repository seam.

    Args:
        repository: Any object exposing
            ``put_config(tenant_id, config_id, attributes, version) -> dict`` — in production the
            concrete :class:`MembersConfigWriteRepository`, in tests an in-memory fake. Injectable
            so the domain stays storage-agnostic.
        version_fn: The row-level write-stamp minter (defaults to
            :func:`~sam.members.domain.config_write_version.next_write_stamp`). Injectable so tests
            can pin a deterministic stamp.
    """

    def __init__(self, repository, version_fn=next_write_stamp, overlay_reader=None):
        self._repository = repository
        self._version_fn = version_fn
        # Optional raw-overlay reader for MERGE-ON-WRITE of config#fields (bugfix): a config#fields
        # PUT carries only the slice the client is authoring, but the repository put REPLACES the
        # whole row. Without merging, a partial body (e.g. the Application Form Builder sending only
        # application-attribute toggles, with empty fields/functional_groups) would WIPE the other
        # slices. When a reader exposing ``get_raw_fields_overlay(tenant_id)`` is injected, the
        # fields validator merges the incoming slices onto the CURRENT stored row per key, so an
        # omitted field/group/override is preserved rather than erased. None (tests without the
        # reader) → legacy replace behaviour, so existing unit tests that assert the shaped body
        # are unaffected.
        self._overlay_reader = overlay_reader

    def put_config(self, tenant_id: str, config_id: str, body: Mapping) -> dict:
        """Validate ``body`` for ``config_id``, stamp a version, and persist the row.

        Shapes ``body`` into the reader-equivalent attribute dict for ``config_id`` (via the
        per-id validator), mints the monotonic row-level :func:`next_write_stamp`, and hands
        ``(tenant_id, config_id, attributes, version)`` to the repository's versioned put.

        Args:
            tenant_id: The tenant (partition key) to write under — resolved from the verified
                token by the edge, never from the body.
            config_id: One of ``{fields, scope, mail}``.
            body: The caller-supplied request body for this ``config_id``.

        Returns:
            A result dict ``{"success": True, "configId": config_id, "version": <stamp>}`` — the
            authoritative version the edge returns to the caller (R1.3).

        Raises:
            ConfigWriteValidationError: ``body`` is malformed for ``config_id`` (edge → HTTP 400).
            ValueError: ``config_id`` has no validator wired (an id outside ``{fields, scope,
                mail}`` — the edge rejects these first, so this is defense in depth).
        """
        attributes = self._validate_body(config_id, body, tenant_id)
        version = self._version_fn()
        self._repository.put_config(
            tenant_id=tenant_id,
            config_id=config_id,
            attributes=attributes,
            version=version,
        )
        return {"success": True, "configId": config_id, "version": version}

    # ── Per-configId body-validation seam ──────────────────────────────────────────────

    def _validate_body(self, config_id: str, body: Mapping, tenant_id: str) -> dict:
        """Dispatch to the per-``configId`` body validator.

        Each SAM-owned id shapes + validates only its own attributes — ``fields`` (Task 1.5),
        ``scope`` (Task 3.3), and ``mail`` (Task 5.1) are all implemented here. ``fields`` also
        needs ``tenant_id`` to MERGE the incoming slices onto the current stored row (bugfix).
        """
        if config_id == schema.CONFIG_ID_FIELDS:
            return self._validate_fields_body(body, tenant_id)
        validators = {
            schema.CONFIG_ID_SCOPE: self._validate_scope_body,
            schema.CONFIG_ID_MAIL: self._validate_mail_body,
        }
        validator = validators.get(config_id)
        if validator is None:
            # The edge already rejects an id outside {fields, scope, mail}; reaching here means a
            # writable id whose authoring step has not landed yet. Fail loudly rather than write a
            # half-shaped row.
            raise ValueError(
                f"no config-write validator wired for config_id {config_id!r}"
            )
        return validator(body)

    # ── config#fields validator (Task 1.5 / Requirement 7) ──────────────────────────────

    def _validate_fields_body(self, body: Mapping, tenant_id: str = "") -> dict:
        """Validate + shape a ``config#fields`` body into the reader's ``get_overlay`` shape (R7).

        Authors the ``fields`` / ``overrides`` / ``functional_groups`` attributes ONLY — the exact
        shape ``MembersProjectionReader.get_overlay`` reads (R7.1). Validation is SHAPE-ONLY (the
        reader degrades individual malformed entries gracefully, so the service checks container
        types, not every leaf):

        - ``fields`` — a mapping of ``{name: spec}``; each ``spec`` must be a mapping (R7.1).
        - ``overrides`` — a mapping of ``{dotted_key: spec}``; each ``spec`` must be a mapping.
        - ``functional_groups`` — a list of mapping entries, each with a non-blank ``key``.

        It does **NOT** author ``default_page_size`` — that tenant-level scalar is RETIRED in favor
        of the per-user runtime Rows_Per_Page_Selector (R7.2 / Requirement 25). Any
        ``default_page_size`` in the body is dropped, never written.

        Each per-field ``scope`` sub-object is preserved **verbatim** (R7.3): the service copies the
        field spec through unchanged so Task 2 can derive ``config#scope`` from the per-field
        ``scope`` attributes. It reshapes nothing inside a field spec.
        """
        if not isinstance(body, Mapping):
            raise ConfigWriteValidationError(
                "config#fields body must be an object with fields/overrides/functional_groups"
            )

        fields_in = self._validate_fields_map(body.get("fields"))
        # Fixed-field overrides: the canonical stored attribute is ``overrides`` (what
        # ``MembersProjectionReader.get_overlay`` reads). The frontend field_overlay object and the
        # legacy Flask ``build_config_fields_row`` builder author this map under the INPUT ALIAS
        # ``fixed_overrides``. Accept either on the wire and normalize to ``overrides``. Precedence
        # fix (bugfix): fall back to the alias when ``overrides`` is empty OR absent — a
        # present-but-empty ``overrides`` must NOT shadow a populated ``fixed_overrides`` (that
        # dropped every base-field toggle the Application Form Builder sent). A populated canonical
        # ``overrides`` still wins when both are non-empty.
        overrides_raw = body.get("overrides")
        if not overrides_raw:
            overrides_raw = body.get("fixed_overrides")
        overrides_in = self._validate_overrides_map(overrides_raw)
        functional_groups_in = self._validate_functional_groups(
            body.get("functional_groups")
        )

        # MERGE-ON-WRITE (bugfix): a config#fields PUT carries only the slice(s) the client is
        # authoring, but the repository put REPLACES the whole row. Without a merge, a partial body
        # (e.g. the Application Form Builder sending only application-attribute toggles under
        # ``overrides``/``fixed_overrides`` with empty ``fields``/``functional_groups``) would WIPE
        # the tenant's other slices. When an overlay reader is wired, load the CURRENT stored row
        # and merge the incoming slices onto it PER KEY: an incoming field/override spec REPLACES
        # the stored entry for that key (so a toggle updates it), and a stored entry the body OMITS
        # is PRESERVED. ``functional_groups`` (an ordered list) is replaced only when the body
        # carries a non-empty list, else the stored groups are kept. No reader (unit tests without
        # one) → legacy replace with exactly what the body carried.
        fields, overrides, functional_groups = self._merge_fields_slices(
            tenant_id, fields_in, overrides_in, functional_groups_in, body
        )

        # Per-field APPLICATION-attribute hardening (R8): the write path is the authoritative
        # author now that the Flask `_validate_application_attrs` guard is off the authoring path
        # (R8.4). Reject a subset ⊄ choices, an unknown `format.checker`, a malformed `format`,
        # or a relax of a platform-required field — fail-loud, BEFORE the row is written, keyed to
        # the offending field (R8.1/R8.3). Validated over the MERGED result so a preserved entry is
        # re-checked too.
        self._validate_application_attributes(fields, overrides)

        # Author exactly the three reader-read attributes — no default_page_size (R7.2).
        return {
            "fields": fields,
            "overrides": overrides,
            "functional_groups": functional_groups,
        }

    def _merge_fields_slices(
        self,
        tenant_id: str,
        fields_in: dict,
        overrides_in: dict,
        functional_groups_in: list,
        body: Mapping,
    ) -> tuple[dict, dict, list]:
        """Merge the incoming config#fields slices onto the CURRENT stored row (bugfix).

        Read-modify-write so a PARTIAL body never wipes a slice it did not author. Per-key merge:
        an incoming ``fields``/``overrides`` spec replaces the stored entry for that key; a stored
        key the body omits is preserved. ``functional_groups`` is replaced only when the body
        carries a non-empty list (an ordered catalog — a present non-empty list is authoritative),
        else the stored groups are kept.

        Falls back to the incoming slices verbatim (legacy replace) when no overlay reader is wired
        (unit tests) or the reader yields nothing — so a never-authored tenant writes exactly what
        the body carried.
        """
        reader = self._overlay_reader
        if (
            reader is None
            or not tenant_id
            or not hasattr(reader, "get_raw_fields_overlay")
        ):
            return fields_in, overrides_in, functional_groups_in

        current = reader.get_raw_fields_overlay(tenant_id) or {}
        cur_fields = (
            current.get("fields") if isinstance(current.get("fields"), dict) else {}
        )
        cur_overrides = (
            current.get("overrides")
            if isinstance(current.get("overrides"), dict)
            else {}
        )
        cur_groups = (
            current.get("functional_groups")
            if isinstance(current.get("functional_groups"), list)
            else []
        )

        # Per-key merge: stored first, then incoming wins for the keys it carries.
        merged_fields = {**cur_fields, **fields_in}
        merged_overrides = {**cur_overrides, **overrides_in}

        # A field/override key the body EXPLICITLY clears (incoming spec present but empty-ish) is
        # still a replace (the toggle-off case writes an empty/attr-stripped spec), so {**...}
        # already handles it. We do NOT delete keys — deletion in these editors is an explicit
        # field/group removal that sends the full slice, which the body-carries check below honours.

        # functional_groups: replace only when the body carried a non-empty list; else keep stored.
        body_carried_groups = (
            isinstance(body.get("functional_groups"), (list, tuple))
            and len(body.get("functional_groups")) > 0
        )
        merged_groups = (
            functional_groups_in if body_carried_groups else list(cur_groups)
        )

        return merged_fields, merged_overrides, merged_groups

    # ── Per-field application-attribute validation (Task 1.1 / Requirement 8) ────────────

    def _validate_application_attributes(
        self, fields: Mapping, overrides: Mapping
    ) -> None:
        """Validate the four per-field application attributes over BOTH specs, fail-loud (R8).

        The SAM equivalent of the retired Flask ``members_config_validation
        ._validate_application_attrs`` (R8.4) — same three write-time invariants, now enforced by
        the authoritative author so a crafted or buggy write can never store an incoherent
        ``config#fields`` row:

        1. **subset ⊆ choices (R8.1a):** a present ``application_choices`` must be a list whose
           every entry is a valid choice of the field's own resolved choices (``options[].value``
           / ``choices``). A subset on a field with no choices, or an entry not in choices, is a
           write error.
        2. **known checker (R8.1b):** a present ``format`` must be a well-formed ``{checker,
           params?}`` mapping whose ``checker`` is in :func:`field_formats.known_tokens`. Anything
           else is rejected (a tenant attaches a KNOWN token, it never authors a checker).
        3. **no relax (R8.1c):** a field the platform marks ``required`` may not carry
           ``application_required = False`` — the public form may only TIGHTEN requiredness, never
           relax the platform floor. The platform-required authority is the fixed-field registry
           (:func:`fixed_fields.field_by_key`); a variable overlay field is never platform-required.

        Reasons are COLLECTED across both maps (every offending field, not just the first) and, if
        any are found, raised as ONE :class:`ConfigWriteValidationError` whose message is keyed to
        the offending field(s) (R8.3) — caller-safe, no internals leaked.
        """
        reasons: dict[str, str] = {}

        # overrides — keyed by the canonical dotted key of a fixed/calculated field. A fixed field
        # the platform marks required cannot be relaxed on the form.
        for dotted, spec in overrides.items():
            if not isinstance(spec, Mapping):
                continue
            fixed = field_by_key(dotted)
            platform_required = bool(fixed is not None and fixed.required)
            self._collect_application_attr_reasons(
                dotted, spec, reasons, platform_required=platform_required
            )

        # fields — the added variable fields. A variable field is NEVER a platform-required field,
        # so only the subset ⊆ choices + known-checker invariants apply (platform_required=False).
        # The error key mirrors the Flask dotted form (`overlay.<key>`) so a rejected write names
        # the field consistently across planes.
        for name, spec in fields.items():
            if not isinstance(spec, Mapping):
                continue
            key = spec.get("key") if isinstance(spec.get("key"), str) else name
            dotted = f"{OVERLAY_GROUP}.{key}"
            self._collect_application_attr_reasons(
                dotted, spec, reasons, platform_required=False
            )

        if reasons:
            detail = "; ".join(
                f"{field}: {reason}" for field, reason in reasons.items()
            )
            raise ConfigWriteValidationError(
                f"config#fields application-attribute validation failed: {detail}"
            )

    @staticmethod
    def _collect_application_attr_reasons(
        dotted: str,
        spec: Mapping,
        reasons: dict[str, str],
        *,
        platform_required: bool,
    ) -> None:
        """Append a reason under ``dotted`` for any application-attribute violation on one spec.

        Mirrors the three rules of the retired Flask ``_validate_application_attrs`` (R8.4);
        batched (never raises here) so the caller collects every offending field before raising
        one :class:`ConfigWriteValidationError`.
        """
        # 1) enum application-subset ⊆ field choices (R8.1a).
        subset = spec.get("application_choices")
        if subset is not None:
            if not isinstance(subset, (list, tuple)):
                reasons[dotted] = "application_choices must be a list"
            else:
                choices = ConfigWriteService._field_choice_values(spec)
                if choices is None:
                    reasons[dotted] = (
                        "application_choices is set but the field declares no choices "
                        "(only an enum field with choices can carry an application subset)"
                    )
                else:
                    extra = [v for v in subset if v not in choices]
                    if extra:
                        reasons[dotted] = (
                            "application_choices entries are not valid field choices: "
                            f"{extra!r}"
                        )

        # 2) format.checker must be a platform-known token (R8.1b).
        fmt = spec.get("format")
        if fmt is not None:
            if not isinstance(fmt, Mapping):
                reasons[dotted] = "format must be an object with a 'checker' token"
            else:
                checker = fmt.get("checker")
                if (
                    not isinstance(checker, str)
                    or checker not in field_formats.known_tokens()
                ):
                    known = ", ".join(sorted(field_formats.known_tokens()))
                    reasons[dotted] = (
                        f"format.checker {checker!r} is not a platform-known token "
                        f"(known: {known})"
                    )

        # 3) application-required cannot relax a platform-required field (R8.1c).
        if platform_required and spec.get("application_required") is False:
            reasons[dotted] = (
                "application_required cannot relax a platform-required field "
                "(the public form may tighten requiredness, never loosen the platform floor)"
            )

    @staticmethod
    def _field_choice_values(spec: Mapping) -> set | None:
        """The field's resolved CHOICE vocabulary as a set, or ``None`` when it declares none.

        Mirrors the retired Flask ``_field_enum_values`` / ``_field_choice_values`` (R8.4): a
        field's choice vocabulary is read from rich ``options`` (``{value,...}`` dicts or bare
        strings) FIRST, then from a bare ``choices`` string list — the single ``options``/
        ``choices`` reader the public read side already uses. Returns the non-blank string values
        as a set for subset-membership checks, or ``None`` when the field declares no usable
        vocabulary (not an enum / value-less) — the caller treats an ``application_choices`` subset
        on such a field as a write error (you cannot subset a field that has no choices).
        """

        def _collect(raw) -> list | None:
            if not isinstance(raw, (list, tuple)):
                return None
            values: list = []
            for entry in raw:
                value = entry.get("value") if isinstance(entry, Mapping) else entry
                if isinstance(value, str) and value.strip():
                    values.append(value)
            return values or None

        values = _collect(spec.get("options")) or _collect(spec.get("choices"))
        return set(values) if values else None

    @staticmethod
    def _validate_fields_map(raw) -> dict:
        """Validate the ``fields`` map; preserve each field spec (incl. ``scope``) verbatim (R7.3).

        ``None`` / absent → ``{}`` (empty overlay is valid — the reader resolves it to the fixed
        base). Each value must be a mapping; each spec is carried through unchanged so a per-field
        ``scope`` attribute is preserved verbatim for the Task 2 ``config#scope`` derivation. The
        service does NOT reshape, drop, or default anything inside a field spec.
        """
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            raise ConfigWriteValidationError("config#fields 'fields' must be an object")
        for name, spec in raw.items():
            if not isinstance(spec, Mapping):
                raise ConfigWriteValidationError(
                    f"config#fields field {name!r} must be an object"
                )
        # Preserve each spec verbatim (shallow copy of the container only) — the per-field `scope`
        # sub-object rides through untouched for Task 2 derivation (R7.3).
        return {name: dict(spec) for name, spec in raw.items()}

    @staticmethod
    def _validate_overrides_map(raw) -> dict:
        """Validate the fixed-field ``overrides`` map; preserve each override spec verbatim.

        ``None`` / absent → ``{}``. Each value must be a mapping (a fixed-field override spec); a
        per-override ``scope`` attribute is likewise carried through verbatim for Task 2.
        """
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            raise ConfigWriteValidationError(
                "config#fields 'overrides' must be an object"
            )
        for dotted, spec in raw.items():
            if not isinstance(spec, Mapping):
                raise ConfigWriteValidationError(
                    f"config#fields override {dotted!r} must be an object"
                )
        return {dotted: dict(spec) for dotted, spec in raw.items()}

    @staticmethod
    def _validate_functional_groups(raw) -> list:
        """Validate the ``functional_groups`` catalog; preserve each entry verbatim.

        ``None`` / absent → ``[]``. Must be a list; each entry must be a mapping carrying a
        non-blank ``key`` (the reader keys the catalog by ``key`` and skips keyless entries, so an
        entry with no usable key is a malformed body here rather than a silently-dropped row).
        """
        if raw is None:
            return []
        if not isinstance(raw, (list, tuple)):
            raise ConfigWriteValidationError(
                "config#fields 'functional_groups' must be a list"
            )
        groups = []
        for entry in raw:
            if not isinstance(entry, Mapping):
                raise ConfigWriteValidationError(
                    "config#fields functional_groups entries must be objects"
                )
            key = entry.get("key")
            if not isinstance(key, str) or not key.strip():
                raise ConfigWriteValidationError(
                    "config#fields functional_groups entries must carry a non-blank 'key'"
                )
            groups.append(dict(entry))
        return groups

    # ── config#scope validator (Task 3.3 / Requirement 8 / 22) ──────────────────────────

    def _validate_scope_body(self, body: Mapping) -> dict:
        """Validate + shape a ``config#scope`` body into the reader's ``get_scope_config`` shape.

        The SAM-owned ``config#scope`` row is ``{"dimensions": [ <ScopeDimension dict>, … ]}`` —
        the exact shape ``MembersProjectionReader.get_scope_config`` reads back (R8.1). The frontend
        scope-save mirror (task 3.1a) writes the already-derived dimension set here as the
        AUTHORITATIVE source; this service shape-checks it and authors the ``dimensions`` attribute
        ONLY. Validation is SHAPE-ONLY, mirroring ``_validate_fields_body`` (the reader degrades an
        individual malformed dimension gracefully, so the service checks the container shape, not
        every leaf):

        - ``dimensions`` — ``None`` / absent → ``[]`` (EMPTY is valid: a tenant-wide scope config,
          R8.5 / R1.6 — the reader resolves an empty list to tenant-wide, never an error);
        - otherwise a list whose every entry is a mapping (one dimension spec), carried through
          verbatim so the reader maps each onto a ``ScopeDimension`` 1:1.

        It never authors ``all_wildcard`` / ``multi_valued`` (s5d clean break, R8.1) — it does not
        add keys, it only passes the authored dimension specs through.
        """
        if not isinstance(body, Mapping):
            raise ConfigWriteValidationError(
                "config#scope body must be an object with a 'dimensions' list"
            )
        dimensions = self._validate_scope_dimensions(body.get("dimensions"))
        return {"dimensions": dimensions}

    @staticmethod
    def _validate_scope_dimensions(raw) -> list:
        """Validate the ``dimensions`` list; preserve each dimension spec verbatim.

        ``None`` / absent → ``[]`` (empty is valid = tenant-wide). Must be a list; each entry must
        be a mapping (a dimension spec: ``key`` / ``field`` / ``enabled`` / ``values`` / ``label`` /
        ``required_for``). Each spec is carried through unchanged — the reader normalizes defaults
        and ignores unknown keys, so the service does not reshape a dimension.
        """
        if raw is None:
            return []
        if not isinstance(raw, (list, tuple)):
            raise ConfigWriteValidationError("config#scope 'dimensions' must be a list")
        for entry in raw:
            if not isinstance(entry, Mapping):
                raise ConfigWriteValidationError(
                    "config#scope 'dimensions' entries must be objects"
                )
        return [dict(entry) for entry in raw]

    # ── config#mail validator (Task 5.1 / Requirement 9 / 15) ───────────────────────────

    def _validate_mail_body(self, body: Mapping) -> dict:
        """Validate + shape a ``config#mail`` body into the reader's accessor shape (R9/R15).

        Authors ONLY the attributes the ``MembersProjectionReader`` mail accessors read back:
        ``mail_enabled`` / ``mail_certified`` / ``application_scope_copy`` (fail-closed bools —
        only an explicit ``True`` opens a gate), ``mail_local_part`` (default ``"noreply"``),
        ``mail_domain`` (NO safe default — omitted when blank so the pre-send resolver fails
        closed, R4.2), ``mail_reply_to_default`` (NEW, Task 5.1 — optional; omitted when blank;
        the scheduled/unattended-send Reply-To, falling back to the From when absent),
        ``application_embed_origins`` (NEW, Task 5.1 — the ONE tenant-authored embed-origin list
        that later feeds BOTH the CloudFront ``frame-ancestors`` and the SAM public API CORS;
        absent/empty writes nothing, a malformed list is rejected fail-loud, R5.2/R8), and
        ``consent_notice`` (the versioned bilingual notice — a truly absent notice writes nothing,
        back-compatible, but an INTENDED-but-malformed notice is REJECTED fail-loud, R8.2/R12.1).

        SHAPE-ONLY, fail-closed, mirroring the Flask ``build_config_mail_row`` so the SAM-written
        row is byte-for-byte what the reader expects — writer and builder cannot drift (R9). The
        boolean gates collapse any non-``True`` value to ``False`` (an absent/malformed gate can
        never silently permit sending).
        """
        if not isinstance(body, Mapping):
            raise ConfigWriteValidationError("config#mail body must be an object")

        attributes: dict = {
            # Fail-closed gates: only an explicit boolean True opens them (R0/R5.2).
            "mail_enabled": body.get("mail_enabled") is True,
            "mail_certified": body.get("mail_certified") is True,
            "application_scope_copy": body.get("application_scope_copy") is True,
            "mail_local_part": self._shape_mail_local_part(body.get("mail_local_part")),
        }

        # Domain: NO safe default — omit unless a non-blank string (a guessed host = a
        # foreign-sender leak, R4.2). The reader resolves a missing domain to None (fail-closed).
        domain = body.get("mail_domain")
        if isinstance(domain, str) and domain.strip():
            attributes["mail_domain"] = domain

        # Reply-To default (Task 5.1, R9): optional tenant-authored string for the
        # scheduled/unattended-send Reply-To. Omit unless a non-blank string so the send path
        # falls back to the From address when it is absent.
        reply_to = body.get("mail_reply_to_default")
        if isinstance(reply_to, str) and reply_to.strip():
            attributes["mail_reply_to_default"] = reply_to

        # Embed origins (Task 5.1, R5.2): ONE tenant-authored list `application_embed_origins`
        # that later feeds TWO distinct enforcement points — the CloudFront form's CSP
        # `frame-ancestors` (task 5.2) AND the SAM public API CORS `Access-Control-Allow-Origin`
        # (task 5.3). Absent / empty is back-compatible (write nothing = standalone, no origins);
        # an INTENDED-but-malformed list (non-list, or a non-string / blank-only entry) is REJECTED
        # fail-loud (R8 posture) rather than silently dropped, so a broken embed config surfaces.
        origins = self._shape_embed_origins(body.get("application_embed_origins"))
        if origins:
            attributes["application_embed_origins"] = origins

        # Consent notice (R8.2): a truly ABSENT notice (key omitted, or an empty/falsey value —
        # no authoring intent) writes nothing, back-compatible. But when the body INTENDS a notice
        # (the ``consent_notice`` key is present and non-empty) yet it is malformed (blank version,
        # or no non-blank locale text), REJECT with a clear error rather than silently omitting —
        # so an admin's broken notice surfaces instead of vanishing. When well-formed it projects
        # the SAME shape the reader's get_consent_notice reads.
        raw_consent_notice = body.get("consent_notice")
        if raw_consent_notice:  # key present AND non-empty → authoring intent
            consent_notice = self._shape_consent_notice(raw_consent_notice)
            if consent_notice is None:
                raise ConfigWriteValidationError(
                    "config#mail 'consent_notice' is malformed: it must carry a non-blank "
                    "'version' and at least one non-blank locale text under 'text'"
                )
            attributes["consent_notice"] = consent_notice

        return attributes

    @staticmethod
    def _shape_mail_local_part(raw) -> str:
        """``mail_local_part`` → a non-blank string, else the default ``"noreply"`` (R4)."""
        if isinstance(raw, str) and raw.strip():
            return raw
        return "noreply"

    @staticmethod
    def _shape_embed_origins(raw) -> list[str]:
        """Shape ``application_embed_origins`` → a list of trimmed, de-duplicated origins (R5.2).

        ONE tenant-authored list that later feeds TWO enforcement points (CloudFront
        ``frame-ancestors`` — task 5.2 — and the SAM public API CORS ``Access-Control-Allow-Origin``
        — task 5.3). This shaper is the single authoring guard for both; the consumers read the
        already-shaped attribute back, so writer and both enforcers cannot drift.

        - ``None`` / absent / empty list → ``[]`` (back-compatible = standalone, no embed origins —
          mirrors how ``mail_domain`` / ``mail_reply_to_default`` omit rather than default). The
          caller writes nothing when the result is empty.
        - a list whose every entry is a non-blank string → each entry is ``strip()``-ed and
          de-duplicated **preserving first-seen order**, matching the conservative public-edge CORS
          allow-list convention (``public_app._allowed_origins``: trim + de-dupe, NO scheme check).
          A scheme check is deliberately NOT imposed — there is no runtime-validation precedent for
          one in this codebase (the public edge and the SAM template both accept bare origin
          strings), so the conservative non-blank-string rule is used.
        - anything else — not a list, or a list containing a non-string / blank-only entry — is
          REJECTED fail-loud with a clear :class:`ConfigWriteValidationError` (R8), so an admin's
          malformed embed config surfaces as a 400 instead of silently becoming "standalone".
        """
        if raw is None:
            return []
        if not isinstance(raw, (list, tuple)):
            raise ConfigWriteValidationError(
                "config#mail 'application_embed_origins' must be a list of non-blank origin strings"
            )
        origins: list[str] = []
        seen: set[str] = set()
        for entry in raw:
            if not isinstance(entry, str) or not entry.strip():
                raise ConfigWriteValidationError(
                    "config#mail 'application_embed_origins' entries must be non-blank strings"
                )
            origin = entry.strip()
            if origin not in seen:
                seen.add(origin)
                origins.append(origin)
        return origins

    @staticmethod
    def _shape_consent_notice(raw) -> dict | None:
        """Shape a consent notice to ``{"version": str, "text": {locale: str}}`` or ``None``.

        Mirrors the Flask builder's ``_resolve_application_consent_notice`` read-side shaping so
        the written row matches ``get_consent_notice`` exactly (R12.1): requires a non-blank
        ``version`` (string, or an int coerced to str) AND >=1 non-blank string locale under
        ``text``; anything malformed collapses to ``None`` (the attribute is then omitted).
        """
        if not isinstance(raw, Mapping):
            return None
        raw_version = raw.get("version")
        if isinstance(raw_version, bool):
            return None
        if isinstance(raw_version, str):
            version = raw_version.strip()
        elif isinstance(raw_version, int):
            version = str(raw_version)
        else:
            version = ""
        if not version:
            return None
        raw_text = raw.get("text")
        if not isinstance(raw_text, Mapping):
            return None
        text: dict[str, str] = {}
        for locale, text_body in raw_text.items():
            if (
                isinstance(locale, str)
                and locale.strip()
                and isinstance(text_body, str)
                and text_body.strip()
            ):
                text[locale] = text_body
        if not text:
            return None
        return {"version": version, "text": text}
