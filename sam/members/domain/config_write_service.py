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

from sam.members.domain.config_write_version import next_write_stamp

__all__ = [
    "ConfigWriteService",
    "ConfigWriteValidationError",
]


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

    def __init__(self, repository, version_fn=next_write_stamp):
        self._repository = repository
        self._version_fn = version_fn

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
        attributes = self._validate_body(config_id, body)
        version = self._version_fn()
        self._repository.put_config(
            tenant_id=tenant_id,
            config_id=config_id,
            attributes=attributes,
            version=version,
        )
        return {"success": True, "configId": config_id, "version": version}

    # ── Per-configId body-validation seam ──────────────────────────────────────────────

    def _validate_body(self, config_id: str, body: Mapping) -> dict:
        """Dispatch to the per-``configId`` body validator.

        Each SAM-owned id shapes + validates only its own attributes — ``fields`` (Task 1.5),
        ``scope`` (Task 3.3), and ``mail`` (Task 5.1) are all implemented here.
        """
        validators = {
            schema.CONFIG_ID_FIELDS: self._validate_fields_body,
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

    def _validate_fields_body(self, body: Mapping) -> dict:
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

        fields = self._validate_fields_map(body.get("fields"))
        # Fixed-field overrides: the canonical stored attribute is ``overrides`` (what
        # ``MembersProjectionReader.get_overlay`` reads). The frontend field_overlay object and the
        # legacy Flask ``build_config_fields_row`` builder author this map under the INPUT ALIAS
        # ``fixed_overrides``. Accept either on the wire and normalize to ``overrides`` so the
        # established frontend shape writes through unchanged (R13.3) WITHOUT silently dropping the
        # fixed-field overrides (the I-x data-loss bug: an alias-only body persisted zero
        # overrides, wiping membership.status / personal.* presentation). Canonical ``overrides``
        # wins if a body somehow carries both; the alias is read only when ``overrides`` is absent.
        overrides_in = body.get("overrides")
        if overrides_in is None:
            overrides_in = body.get("fixed_overrides")
        overrides = self._validate_overrides_map(overrides_in)
        functional_groups = self._validate_functional_groups(
            body.get("functional_groups")
        )

        # Author exactly the three reader-read attributes — no default_page_size (R7.2).
        return {
            "fields": fields,
            "overrides": overrides,
            "functional_groups": functional_groups,
        }

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
        the scheduled/unattended-send Reply-To, falling back to the From when absent), and
        ``consent_notice`` (the versioned bilingual notice; omitted unless well-formed, R12.1).

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

        # Consent notice: project ONLY when well-formed (non-blank version + >=1 non-blank
        # locale text), else omit — the SAME shape the reader's get_consent_notice reads.
        consent_notice = self._shape_consent_notice(body.get("consent_notice"))
        if consent_notice is not None:
            attributes["consent_notice"] = consent_notice

        return attributes

    @staticmethod
    def _shape_mail_local_part(raw) -> str:
        """``mail_local_part`` → a non-blank string, else the default ``"noreply"`` (R4)."""
        if isinstance(raw, str) and raw.strip():
            return raw
        return "noreply"

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
