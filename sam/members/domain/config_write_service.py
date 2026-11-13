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

from sam.members.domain import form_slug
from sam.members.domain.config_write_version import next_write_stamp

__all__ = [
    "ConfigWriteService",
    "ConfigWriteValidationError",
]

from ._config_write_shaping import (
    ConfigWriteShapingMixin,
)
from ._config_write_shared import (  # noqa: F401 (surface compat)
    _EMBED_ORIGIN_MAX_LEN,
    _EMBED_ORIGIN_RE,
    _EMBED_ORIGINS_MAX_COUNT,
    OVERLAY_GROUP,
    ConfigWriteValidationError,
)
from ._config_write_validation import (
    ConfigWriteValidationMixin,
)


class ConfigWriteService(
    ConfigWriteValidationMixin,
    ConfigWriteShapingMixin,
):
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

    def __init__(
        self,
        repository,
        version_fn=next_write_stamp,
        overlay_reader=None,
        overlay_reader_factory=None,
        usage_probe=None,
    ):
        self._repository = repository
        self._version_fn = version_fn
        # OPTION-INTEGRITY member-usage probe (03b BU-1, Req 3.2a). Storage-agnostic seam shared
        # with the delete-field guard (config_fields_crud_service): the write service cannot read
        # member data itself (steering 35/39), so to tell whether an option ``value`` the author is
        # removing/renaming is still referenced by a member it consults an injected probe exposing
        # ``option_in_use(tenant_id, field_key, value) -> bool`` (or the richer
        # ``field_usage(tenant_id, field_key) -> Mapping`` the delete-field guard uses, from which a
        # ``values`` set is read). When no probe is wired — or a wired probe exposes neither the
        # option-level nor the richer shape — the in-use leg cannot be observed and does NOT block
        # (production always wires one; this keeps the unit surface exercisable, mirroring the
        # delete-field guard's no-probe degradation).
        self._usage_probe = usage_probe
        # MERGE-ON-WRITE of config#fields (bugfix): a config#fields PUT carries only the slice the
        # client is authoring, but the repository put REPLACES the whole row. Without merging, a
        # partial body (e.g. the Application Form Builder sending only application-attribute toggles
        # with empty fields/functional_groups) would WIPE the other slices. The fields validator
        # reads the CURRENT stored overlay and merges the incoming slices onto it per key.
        #
        # RELIABILITY — read FRESH each write (no shared cache): the projection reader keeps a
        # per-instance partition cache. A module-global reader reused across warm invocations would
        # serve STALE state to a later write's merge (and lose a concurrent change). So prefer an
        # ``overlay_reader_factory`` (a zero-arg callable returning a FRESH reader) and build a new
        # reader per ``put_config`` merge — its cache lives only for that one read. ``overlay_reader``
        # (a shared instance) is still accepted for tests that inject a fake with fresh state; it is
        # used only when no factory is given. Neither provided → legacy replace (unit tests that
        # assert the shaped body are unaffected).
        self._overlay_reader = overlay_reader
        self._overlay_reader_factory = overlay_reader_factory

    def _merge_reader(self):
        """A reader for the merge read — FRESH per call when a factory is wired (no stale cache),
        else the injected shared instance (tests), else None (legacy replace)."""
        if self._overlay_reader_factory is not None:
            return self._overlay_reader_factory()
        return self._overlay_reader

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

    def _author_form_slug(
        self, attributes: dict, body: Mapping, tenant_id: str
    ) -> None:
        """Author ``slug`` + carry ``published_at`` / ``published_version`` onto the fields row.

        Spec 12 Task 1.1 (R4.2, design §Data Models). The application form's own public ``slug`` is
        stored on the ``config#fields`` row (NOT in Flask ``tenant_slugs``, D1). On a fields write:

        - If the body carries a ``slug``, validate its FORMAT with the landing ``SLUG_PATTERN``
          rules (:func:`form_slug.validate_slug_format`); a malformed slug raises a caller-safe
          :class:`ConfigWriteValidationError` (→ HTTP 400), nothing is written. An explicit
          ``null`` CLEARS the slug (``slug: None``). A body that OMITS ``slug`` leaves the stored
          slug untouched (carried through from the current row).
        - ``published_at`` / ``published_version`` are publish-state owned by the publish path
          (Task 2.2); a plain fields save never authors them from the body — they are carried
          through from the current stored row (defaulting to ``None`` on a never-published row).

        Uniqueness is deliberately NOT enforced here — within-tenant uniqueness is the Task-1.2
        ``_slugs/{slug}`` conditional-put claim; this step is slug FORMAT + the field only.
        """
        current = self._current_fields_row(tenant_id)

        # slug: body value (validated) when the key is present, else carry the stored slug.
        if "slug" in body:
            slug = body.get("slug")
            if slug is not None:
                error = form_slug.validate_slug_format(slug)
                if error is not None:
                    raise ConfigWriteValidationError(
                        f"config#fields slug is invalid: {error}"
                    )
            attributes["slug"] = slug
        else:
            attributes["slug"] = current.get("slug")

        # publish-state: owned by the publish path — carry through, never author on a fields save.
        attributes["published_at"] = current.get("published_at")
        attributes["published_version"] = current.get("published_version")

    def _current_fields_row(self, tenant_id: str) -> dict:
        """The current stored ``config#fields`` row (for carrying publish-state through), or ``{}``.

        Reuses the merge reader seam (fresh per call when a factory is wired; the injected shared
        instance in tests; ``None`` → legacy, no current row). Returns ``{}`` when there is no
        reader, no tenant, or no stored row — so a never-authored tenant carries ``None``
        publish-state and whatever ``slug`` the body supplies.
        """
        reader = self._merge_reader()
        if (
            reader is None
            or not tenant_id
            or not hasattr(reader, "get_raw_fields_overlay")
        ):
            return {}
        current = reader.get_raw_fields_overlay(tenant_id)
        return current if isinstance(current, Mapping) else {}

    def _merge_fields_slices(
        self,
        tenant_id: str,
        fields_in: dict,
        overrides_in: dict,
        functional_groups_in: dict,
        body: Mapping,
    ) -> tuple[dict, dict, dict]:
        """Merge the incoming config#fields slices onto the CURRENT stored row (bugfix).

        Read-modify-write so a PARTIAL body never wipes a slice it did not author. Per-key merge:
        an incoming ``fields``/``overrides`` spec replaces the stored entry for that key; a stored
        key the body omits is preserved.

        **``functional_groups`` is now a MAP keyed by group key** (spec 03, design C6 / D2a): it is
        merged PER KEY exactly like ``fields`` / ``overrides`` — an incoming group entry replaces
        the stored entry for that key, and a stored group the body omits is PRESERVED. This is the
        structural fix for the occurrence-3 truncation: a partial groups payload can no longer wipe
        the catalog, because a map merge never drops keys the body did not mention (the legacy LIST
        replace-if-non-empty was what truncated 6→1). The reader dual-reads, so a stored legacy LIST
        row is normalized to a MAP here before the merge — a write migrates the groups shape forward
        as a side effect, never backward.

        Falls back to the incoming slices verbatim (legacy replace) when no overlay reader is wired
        (unit tests) or the reader yields nothing — so a never-authored tenant writes exactly what
        the body carried.
        """
        reader = self._merge_reader()
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
        # The reader serves the override map under the AUTHORING WIRE key ``fixed_overrides``
        # (one-key contract); accept the storage key ``overrides`` as a fallback for robustness.
        # ``overrides_in`` is already the storage-shaped (normalized) incoming map, so merging them
        # yields the storage ``overrides`` the repository persists.
        cur_overrides_raw = current.get("fixed_overrides")
        if not isinstance(cur_overrides_raw, dict):
            cur_overrides_raw = current.get("overrides")
        cur_overrides = cur_overrides_raw if isinstance(cur_overrides_raw, dict) else {}
        # The reader now serves ``functional_groups`` as a MAP (dual-reading a legacy LIST row), so
        # this is already ``{gkey: entry}`` — merge it per key like the other two slices.
        cur_groups = (
            current.get("functional_groups")
            if isinstance(current.get("functional_groups"), dict)
            else {}
        )

        # Per-key merge: stored first, then incoming wins for the keys it carries.
        merged_fields = {**cur_fields, **fields_in}
        merged_overrides = {**cur_overrides, **overrides_in}
        # functional_groups MAP merge: an incoming group replaces its key's stored entry; a stored
        # group the body omits is PRESERVED (no truncation). A body that carried no groups leaves
        # the stored catalog entirely intact.
        merged_groups = {**cur_groups, **functional_groups_in}

        # A field/override/group key the body EXPLICITLY clears (incoming spec present but
        # empty-ish) is still a replace (the toggle-off case writes an empty/attr-stripped spec), so
        # {**...} already handles it. We do NOT delete keys — deletion in these editors is an
        # explicit field/group removal handled by Phase 2's REMOVE-path ops, not a merge.

        return merged_fields, merged_overrides, merged_groups
