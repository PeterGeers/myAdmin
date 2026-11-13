"""Consistent-read snapshot / placement / version mechanics.

Part of ConfigFieldsCrudService (code-quality-fixes-2026-11-12 task 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sam.members.domain.fixed_fields import field_by_key
from sam.members.repository.projection_config_write_repository import LEGACY_NO_VERSION

from ._config_fields_shared import (
    _FIELDS_MAP,
    _GROUPS_MAP,
    _MAP_TO_WIRE_KEY,
    _OVERRIDES_MAP,
    ConfigFieldsCrudError,
    _snapshot_is_empty,
)


class ConfigFieldsReadMixin:
    """Consistent-read snapshot / placement / version mechanics."""

    # ── Placement + version mechanics (task 2.3 — design-review Q2/Q8 + Must-fix #1) ────

    def _read_snapshot(self, tenant_id: str) -> dict | None:
        """Read the resolved ``config#fields`` record STRONGLY-CONSISTENT, ONLY to validate +
        decide placement/version (design C1 step 1; design-review Q2/Q8 + Should-fix).

        This is the ONE read per public op. It is NOT a read-merge-write: the returned snapshot is
        used purely to (a) decide the storage path for the identity, (b) choose the CREATE-vs-
        UPDATE verb by entry existence, and (c) resolve the optimistic-lock base version. The write
        itself is a single path ``update_item`` that never re-sends the read record.

        The strong-consistency flag flows all the way to the repository ``Query`` via the reader's
        ``get_raw_fields_overlay(..., consistent_read=True)`` (so a stale eventually-consistent read
        can never produce a spurious 409, Should-fix). Returns the raw wire overlay
        (``{"fields", "fixed_overrides", "functional_groups", "version"?}``) or ``None`` when there
        is no reader wired (the 2.2 surface stays exercisable without one — first-write placement).
        """
        reader = self._reader
        if reader is None or not hasattr(reader, "get_raw_fields_overlay"):
            return None
        try:
            overlay = reader.get_raw_fields_overlay(tenant_id, consistent_read=True)
        except TypeError:
            # A fake/older reader whose signature predates the consistent_read kwarg: fall back to
            # the default read rather than crashing the op (the flag is a strengthening, not a
            # correctness precondition for placement).
            overlay = reader.get_raw_fields_overlay(tenant_id)
        if not isinstance(overlay, Mapping):
            return None

        # The optimistic-lock ``version`` is read via the SEPARATE control-plane accessor
        # (:meth:`MembersProjectionReader.get_config_fields_version`), NOT from the authoring wire
        # overlay above — that wire body is surfaced to the frontend under ``field_overlay`` and
        # deliberately carries NO ``version`` (its contract is "stored maps minus key + version").
        # So the base-version decision reads the control attribute here and MERGES it onto the
        # snapshot the placement/version logic consumes, keeping one coherent per-op view without
        # ever leaking ``version`` into the wire shape. ``row_present`` lets
        # :meth:`_base_version_from_snapshot` tell an existing legacy (versionless) row apart from
        # no row at all (base_version case ii vs iii). A reader without the accessor (an older/fake
        # one) degrades to the wire-overlay heuristic.
        snapshot = dict(overlay)
        version, row_present = self._read_version(reader, tenant_id)
        if version is not None:
            snapshot["version"] = version
        if row_present is not None:
            snapshot["__row_present__"] = row_present
        return snapshot

    @staticmethod
    def _read_version(reader, tenant_id: str):
        """Resolve ``(version, row_present)`` from the reader's control-plane version accessor.

        Returns ``(None, None)`` when the reader does not expose ``get_config_fields_version`` (an
        older/fake reader — the caller then falls back to the wire-overlay emptiness heuristic),
        otherwise ``(version_or_None, row_present_bool)``. ``consistent_read=True`` keeps the
        version read strongly-consistent in lockstep with the placement read (design C1 step 1).
        """
        if not hasattr(reader, "get_config_fields_version"):
            return (None, None)
        try:
            present, version = reader.get_config_fields_version(
                tenant_id, consistent_read=True
            )
        except TypeError:
            present, version = reader.get_config_fields_version(tenant_id)
        return (version, bool(present))

    def _resolve_placement(
        self,
        tenant_id: str,
        field_key: str,
        *,
        snapshot: Mapping[str, Any] | None,
    ) -> dict:
        """Map a field identity to its storage path + CREATE-vs-UPDATE verb (design C1 step 2–3).

        Returns ``{"map": <fields|overrides>, "key": <segment>, "create": <bool>}``:

        - **map/key (placement by identity):** a key known to the fixed-field registry
          (base/calculated) places under ``overrides.<dotted>``; an unknown key (a tenant VARIABLE
          field) places under ``fields.<key>``. The dotted override key is a LITERAL segment the
          repository binds through ``ExpressionAttributeNames`` (so the ``.`` is never mis-parsed
          as a nested path — the segments handed on are correct for that binding, design-review
          Q2). Registry lookup accepts either the bare key or the already-dotted key.
        - **create (the verb, by EXISTENCE in the consistent snapshot):** ``True`` when the entry
          does NOT yet exist under its map in ``snapshot`` → op emission seeds the WHOLE entry with
          one ``SET <map>.<key> = :whole``; ``False`` when it exists → op emission UPDATEs the named
          aspect(s). When no reader is wired (``snapshot is None``) we cannot observe existence and
          default to CREATE — the correct verb for a never-authored tenant on the C6 skeleton, and
          the behaviour the 2.2 surface tests exercise.
        """
        if not field_key:
            raise ConfigFieldsCrudError("field_key must be a non-empty identity")
        dotted = self._dotted_for(field_key)
        if dotted is not None:
            placement = {"map": _OVERRIDES_MAP, "key": dotted}
        else:
            placement = {"map": _FIELDS_MAP, "key": field_key}
        placement["create"] = not self._entry_exists(snapshot, placement)
        return placement

    @staticmethod
    def _dotted_for(field_key: str) -> str | None:
        """The canonical dotted key for a base/calculated field, or ``None`` for a variable field.

        Accepts either a bare key (``"gender"``) or an already-dotted key (``"personal.gender"``).
        Uses the pure registry (:func:`fixed_fields.field_by_key`), which is keyed by the dotted
        ``group.key``; a bare key is matched by scanning for a unique registry entry. Returns
        ``None`` when the key is not a registry (base) field → it is a tenant variable field.
        """
        if field_by_key(field_key) is not None:
            # already a dotted base key (e.g. "membership.status")
            return field_key
        # bare key → find the base field whose key matches (unique by registry construction)
        from sam.members.domain.fixed_fields import FIXED_FIELDS

        for f in FIXED_FIELDS:
            if f.key == field_key:
                return f.dotted_key()
        return None

    def _group_placement(
        self, group_key: str, *, snapshot: Mapping[str, Any] | None
    ) -> dict:
        """Placement for a functional group — always ``functional_groups.<gkey>`` (map post-D2a).

        Carries the same ``create`` verb choice as :meth:`_resolve_placement`: ``True`` when the
        group entry is absent from the consistent snapshot (seed the whole entry — this is the
        base-group MATERIALIZE, R4.1), ``False`` when it exists (update the aspect). The catalog
        cannot truncate either way — no op ever writes the whole ``functional_groups`` map.
        """
        if not group_key:
            raise ConfigFieldsCrudError("group_key must be a non-empty identity")
        placement = {"map": _GROUPS_MAP, "key": group_key}
        placement["create"] = not self._entry_exists(snapshot, placement)
        return placement

    @staticmethod
    def _entry_exists(
        snapshot: Mapping[str, Any] | None, placement: Mapping[str, Any]
    ) -> bool:
        """True when the entry ``placement`` names already exists in the consistent snapshot.

        Reads the snapshot in the reader's WIRE shape: ``fields`` and ``functional_groups`` are
        served under those keys, while the ``overrides`` storage map is served under the authoring
        wire key ``fixed_overrides`` (the one-key contract in
        :meth:`MembersProjectionReader.get_raw_fields_overlay`). A ``None`` snapshot (no reader
        wired) is treated as "does not exist" → CREATE (correct for a first write onto the C6
        skeleton). The lookup is by the entry key verbatim — for an override that is the dotted
        ``<group>.<key>`` segment, which is exactly how the map is keyed at rest.
        """
        if not isinstance(snapshot, Mapping):
            return False
        map_name = placement["map"]
        wire_key = _MAP_TO_WIRE_KEY.get(map_name, map_name)
        container = snapshot.get(wire_key)
        if not isinstance(container, Mapping):
            return False
        return placement["key"] in container

    @staticmethod
    def _base_version_from_snapshot(snapshot: Mapping[str, Any] | None):
        """Resolve the ``base_version`` sentinel for the conditional write from the snapshot.

        Three cases (design C1 step 4 / design-review Must-fix #2): an existing row carrying a
        ``version`` → that version (optimistic lock, case i); an existing row with NO ``version``
        (legacy, pre-version) → :data:`LEGACY_NO_VERSION` (case ii) so the first versioned write
        is not spuriously rejected; no row at all (``None`` snapshot, or the empty/never-authored
        shape) → ``None`` (case iii, first write onto the skeleton).

        A reader that returns the empty overlay shape (``fields``/``fixed_overrides``/
        ``functional_groups`` all empty, no ``version``) for a never-authored tenant is treated as
        "no row yet" (``None``), NOT as a legacy row — the empty-is-valid default must not force a
        spurious ``attribute_not_exists(version)`` lock onto a row that does not exist.
        """
        if not isinstance(snapshot, Mapping):
            return None
        version = snapshot.get("version")
        if version:
            return version
        # No version in the snapshot → distinguish an EXISTING legacy (versionless) row from NO
        # row. When the control-plane read told us whether the row is present (``__row_present__``,
        # set by :meth:`_read_snapshot`), trust it: a present row with no version is legacy
        # (case ii, ``LEGACY_NO_VERSION``); an absent row is a first write (case iii, ``None``).
        # Otherwise (an older/fake reader with no version accessor) fall back to the wire-overlay
        # emptiness heuristic — an all-empty overlay reads as "no row yet".
        row_present = snapshot.get("__row_present__")
        if row_present is True:
            return LEGACY_NO_VERSION
        if row_present is False:
            return None
        if _snapshot_is_empty(snapshot):
            return None
        return LEGACY_NO_VERSION
