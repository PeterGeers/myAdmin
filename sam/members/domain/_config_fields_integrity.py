"""Write-side source-integrity guards.

Part of ConfigFieldsCrudService (code-quality-fixes-2026-11-12 task 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sam.members.domain._membership_errors import MEMBERSHIP_TYPE_FIELD_KEY

from ._config_fields_shared import _MAP_TO_WIRE_KEY, ConfigFieldsCrudError


class ConfigFieldsIntegrityMixin:
    """Write-side source-integrity guards."""

    # ── Write-side source-integrity guards (design W1/W2/W3, Property 5) ────────────────

    def _guard_write_source_integrity(
        self,
        field_key: str,
        def_attrs: Mapping[str, Any],
        placement: Mapping[str, Any],
        *,
        snapshot: Mapping[str, Any] | None,
    ) -> None:
        """Reject a definition write that violates a selectable field's source-integrity invariant
        (design "Write-side vocabulary invariants" W1/W2/W3; Property 5), BEFORE any repository
        call.

        Because C1 now seeds the editor from ``options`` IDENTICALLY for every kind, the write edge
        must stop a stale catalog/scope snapshot being re-frozen inline, and must stop an
        inline-source enum being made selectable with no vocabulary. Three deliberate, caller-safe
        rejections (each raises :class:`ConfigFieldsCrudError`, which the edge maps to a 400 with a
        GENERIC client message; the full reason rides the exception string the edge LOGS
        server-side under a correlation id — no ``str(e)`` leak, steering 30):

        - **W1 — reference field, inline options rejected.** A reference field (the
          ``membership_type`` reference key, or a field whose declared ``type`` is ``reference``)
          sources its vocabulary from the LIVE catalog, populated at the read seam (C4). Persisting
          an inline ``options`` payload would re-freeze a stale copy of the catalog — the
          two-copies disease on the WRITE side. Reference vocabulary lives in the catalog, never
          inline → reject a non-empty inline ``options`` payload.
        - **W2 — REMOVED (03a Option A).** A scope-backed field is now a NORMAL enum for authoring:
          its inline ``options`` payload is ACCEPTED (the editor round-trips the ``config#scope``
          dimension's options back on save — that is the whole point). Its dropdown may ALSO be
          sourced from ``scope_vocab`` (the ``config#scope`` dimension) at the C4 read seam (the
          pre-existing S5j read-path behaviour, UNCHANGED). An earlier revision wrongly rejected the
          only authoring path here; that rejection is gone. A scope-backed field falls through to W3
          like any enum.
        - **W3 — inline-source enum, EXPLICIT empty options rejected.** The write-edge invariant:
          an inline-source (enum) field CANNOT be made selectable with zero ``options``. Scoped to
          an EXPLICIT empty ``options`` payload (``[]``) — staging a field before adding its
          vocabulary (a ``set_field`` that does NOT carry ``options`` at all) stays legitimate, so
          an ABSENT ``options`` key never trips this guard. This invariant is what makes the
          read-time fail-loud discriminator unambiguous (an inline enum that reads back empty is
          ALWAYS the P3 asymmetry, never a legitimately-empty save).

        Kind is classified from the payload UNIONED with the field's stored spec in the snapshot:
        an UPDATE may carry ONLY ``options`` (no ``type``/``scope``), so the field's kind is read
        from what is already stored when the payload is silent — matching how the surrounding code
        (the read seam's ``MEMBERSHIP_TYPE_FIELD_KEY`` reference check, the resolver's ``scope``
        carry) classifies kind.
        """
        stored = self._stored_field_spec(snapshot, placement)
        inline_options_present = "options" in def_attrs
        inline_options = def_attrs.get("options")
        has_inline_option_values = bool(
            isinstance(inline_options, (list, tuple)) and len(inline_options) > 0
        )

        # W1 — reference field may never carry inline options (catalog is the source of truth).
        if self._is_reference_field(field_key, def_attrs, stored):
            if inline_options_present:
                raise ConfigFieldsCrudError(
                    f"set_field: field {field_key!r} is a reference field — its options are a "
                    "snapshot of the live catalog populated on read; an inline `options` payload "
                    "is rejected so a stale catalog copy is never re-frozen inline (W1)"
                )
            return

        # W2 REMOVED (03a Option A). A scope-backed field is a NORMAL enum for authoring: its
        # `options` payload is ACCEPTED here (that is the whole point — the editor round-trips the
        # scope dimension's options back on save). Its dropdown may ALSO be sourced from the
        # config#scope dimension at read time (the pre-existing S5j read-path behaviour), which is
        # UNCHANGED. An earlier revision wrongly rejected the only authoring path with a W2 guard;
        # that rejection is removed. A scope-backed field now falls through to W3 like any enum
        # (W3 still rejects an inline enum saved with an EXPLICIT empty `options`).

        # W3 — inline-source enum cannot be made selectable with an EXPLICIT empty options list.
        if (
            inline_options_present
            and not has_inline_option_values
            and self._is_inline_enum_field(def_attrs, stored)
        ):
            raise ConfigFieldsCrudError(
                f"set_field: field {field_key!r} is an inline-source enum — it cannot be saved "
                "selectable with zero `options` (the write-edge invariant). Supply at least one "
                "option, or stage the field without an `options` key until its vocabulary is "
                "ready (W3)"
            )

    @staticmethod
    def _stored_field_spec(
        snapshot: Mapping[str, Any] | None, placement: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """The field's CURRENTLY STORED spec from the consistent snapshot, or ``{}`` when absent.

        Reads the snapshot in the reader's WIRE shape (``overrides`` served under
        ``fixed_overrides``), matching :meth:`_entry_exists`. Lets the source-integrity guard
        classify a field's kind from what is already stored when an UPDATE payload carries only
        ``options`` (no ``type``/``scope``).
        """
        if not isinstance(snapshot, Mapping):
            return {}
        wire_key = _MAP_TO_WIRE_KEY.get(placement["map"], placement["map"])
        container = snapshot.get(wire_key)
        if not isinstance(container, Mapping):
            return {}
        spec = container.get(placement["key"])
        return spec if isinstance(spec, Mapping) else {}

    @staticmethod
    def _effective_type(
        def_attrs: Mapping[str, Any], stored: Mapping[str, Any]
    ) -> str | None:
        """The field's effective declared ``type`` — the payload's value if present, else the
        stored spec's (payload ∪ snapshot). ``None`` when neither declares one."""
        if "type" in def_attrs:
            declared = def_attrs.get("type")
        else:
            declared = stored.get("type")
        return declared if isinstance(declared, str) else None

    @staticmethod
    def _effective_scope(
        def_attrs: Mapping[str, Any], stored: Mapping[str, Any]
    ) -> Any:
        """The field's effective ``scope`` sub-object — the payload's value if the key is present
        (an explicit ``None`` disables scope), else the stored spec's."""
        if "scope" in def_attrs:
            return def_attrs.get("scope")
        return stored.get("scope")

    @classmethod
    def _is_reference_field(
        cls,
        field_key: str,
        def_attrs: Mapping[str, Any],
        stored: Mapping[str, Any],
    ) -> bool:
        """True when the field is a REFERENCE field (W1), classified the way the surrounding code
        does: the ``membership_type`` reference key (by bare or dotted identity, mirroring the read
        seam's ``MEMBERSHIP_TYPE_FIELD_KEY`` check) OR an effective declared ``type`` of
        ``reference``."""
        dotted = cls._dotted_for(field_key)
        if (
            dotted == MEMBERSHIP_TYPE_FIELD_KEY
            or field_key == MEMBERSHIP_TYPE_FIELD_KEY
        ):
            return True
        return cls._effective_type(def_attrs, stored) == "reference"

    @classmethod
    def _is_scope_backed_field(
        cls, def_attrs: Mapping[str, Any], stored: Mapping[str, Any]
    ) -> bool:
        """True when the field is SCOPE-BACKED (W2): its effective ``scope`` sub-object is a mapping
        with a truthy ``enabled`` flag (an enabled scope axis, sourced from ``scope_vocab``). An
        explicit ``scope: None`` in the payload disables scope and is NOT scope-backed."""
        scope = cls._effective_scope(def_attrs, stored)
        return isinstance(scope, Mapping) and bool(scope.get("enabled"))

    @classmethod
    def _is_inline_enum_field(
        cls, def_attrs: Mapping[str, Any], stored: Mapping[str, Any]
    ) -> bool:
        """True when the field is an INLINE-SOURCE enum (W3): the effective declared ``type`` is
        ``enum``. (Reference and scope-backed fields are classified and handled ahead of this by
        W1/W2, so this is reached only for a non-reference, non-scope field.)"""
        return cls._effective_type(def_attrs, stored) == "enum"
