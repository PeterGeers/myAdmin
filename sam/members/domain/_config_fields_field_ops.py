"""Field/group definition CRUD ops.

Part of ConfigFieldsCrudService (code-quality-fixes-2026-11-12 task 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sam.members.repository.projection_config_write_repository import REMOVE

from ._config_fields_shared import (
    _FIELDS_MAP,
    FIELD_APPLICATION_ATTRS,
    FIELD_DEFINITION_ATTRS,
    GROUP_ATTRS,
    ConfigFieldsCrudError,
)


class ConfigFieldsFieldOpsMixin:
    """Field/group definition CRUD ops."""

    # ── Field DEFINITION op (DEFINITION attrs ONLY — NO application_*) ──────────────────

    def set_field(
        self,
        tenant_id: str,
        field_key: str,
        def_attrs: Mapping[str, Any],
        *,
        client_op_id: str | None = None,
    ) -> dict:
        """Set/clear DEFINITION attributes of a field, placed server-side (design C1).

        ``def_attrs`` MUST be a subset of :data:`FIELD_DEFINITION_ATTRS`. An ``application_*`` (or
        ``format``) key is REJECTED with :class:`ConfigFieldsCrudError` — this op is structurally
        incapable of touching application-form config (the disjointness that makes D3(A) hold).

        Absent-vs-null semantics (review Should-fix): an attr ABSENT from ``def_attrs`` is left
        untouched (no path written); an attr whose value is explicit ``None`` is REMOVEd (a scoped
        ``REMOVE`` of just that aspect). To revert a whole base/calculated override use
        :meth:`reset_field`, not an attrs payload of nulls.
        """
        self._require_attr_surface(def_attrs, FIELD_DEFINITION_ATTRS, op="set_field")
        self._reject_duplicate_option_values(def_attrs, op="set_field")

        def derive(snapshot):
            placement = self._resolve_placement(tenant_id, field_key, snapshot=snapshot)
            # Write-side source-integrity guards (design W1/W2/W3, Property 5). Run AFTER placement
            # (so the field's stored spec is observable from the snapshot for kind classification)
            # but BEFORE op emission — hence before any repository call. They reject a stale
            # catalog/scope snapshot being re-frozen inline (W1/W2) and an inline-source enum made
            # selectable with an explicitly-empty vocabulary (W3).
            self._guard_write_source_integrity(
                field_key, def_attrs, placement, snapshot=snapshot
            )
            return self._attr_ops(placement, def_attrs)

        return self._run(tenant_id, derive, client_op_id=client_op_id)

    # ── Field APPLICATION op (the FOUR app attrs ONLY — NO definition attr) ─────────────

    def set_field_application(
        self,
        tenant_id: str,
        field_key: str,
        app_attrs: Mapping[str, Any],
        *,
        client_op_id: str | None = None,
    ) -> dict:
        """Set/clear the FOUR application attributes of a field, placed server-side (design C1).

        ``app_attrs`` MUST be a subset of :data:`FIELD_APPLICATION_ATTRS`. A DEFINITION key is
        REJECTED with :class:`ConfigFieldsCrudError` — this is the ONLY op the application-form
        builder calls (D3(A)), and it can never reach a field/group definition.

        Absent-vs-null semantics as per :meth:`set_field`.
        """
        self._require_attr_surface(
            app_attrs, FIELD_APPLICATION_ATTRS, op="set_field_application"
        )

        def derive(snapshot):
            placement = self._resolve_placement(tenant_id, field_key, snapshot=snapshot)
            return self._attr_ops(placement, app_attrs)

        return self._run(tenant_id, derive, client_op_id=client_op_id)

    # ── Reset a base/calculated field to its code-defined base ──────────────────────────

    def reset_field(
        self, tenant_id: str, field_key: str, *, client_op_id: str | None = None
    ) -> dict:
        """REMOVE a base/calculated field's tenant override entirely, reverting it to base (D4).

        Emits a single ``REMOVE overrides.<dotted>`` op (the whole override entry). A base field is
        NEVER removed from storage (it lives in code); "resetting" it simply drops the override so
        the resolver falls back to the base definition. For a tenant-added VARIABLE field, see
        :meth:`delete_field`.
        """

        def derive(snapshot):
            placement = self._resolve_placement(tenant_id, field_key, snapshot=snapshot)
            return [self._remove_entry_op(placement)]

        return self._run(tenant_id, derive, client_op_id=client_op_id)

    # ── Delete a tenant VARIABLE field (safety guard is task 2.6's territory) ────────────

    def delete_field(
        self, tenant_id: str, field_key: str, *, client_op_id: str | None = None
    ) -> dict:
        """Delete a tenant-added VARIABLE field (explicit — never inferred from omission, R2.5).

        Emits a single ``REMOVE fields.<key>`` op. A base/calculated field is NOT deletable here —
        use :meth:`reset_field` to drop its override. Before emitting the op, the
        :meth:`_guard_delete_field` usage-safety guard refuses a delete that would orphan member
        data or leave a dangling group/application reference (design C1; review Should-fix),
        offering ``visible=false`` (hide) as the safe alternative.
        """

        def derive(snapshot):
            placement = self._resolve_placement(tenant_id, field_key, snapshot=snapshot)
            if placement["map"] != _FIELDS_MAP:
                raise ConfigFieldsCrudError(
                    f"delete_field only deletes a tenant VARIABLE field; {field_key!r} is a "
                    f"base/calculated field — use reset_field to drop its override (R2.5)"
                )
            self._guard_delete_field(tenant_id, field_key, placement, snapshot=snapshot)
            return [self._remove_entry_op(placement)]

        return self._run(tenant_id, derive, client_op_id=client_op_id)

    # ── Legacy-cleanup op (migration companion — NOT part of the normal write surface) ──

    def remove_legacy_choices(
        self, tenant_id: str, field_key: str, *, client_op_id: str | None = None
    ) -> dict:
        """Remove a field's LEGACY ``choices`` attribute via a scoped Change-Op REMOVE (03a C7).

        This is the one-time ``choices`` → ``options`` backfill's companion. It is DELIBERATELY NOT
        part of the normal client write surface: :data:`FIELD_DEFINITION_ATTRS` no longer lists
        ``choices`` (C2 retired it), so :meth:`set_field` correctly REJECTS any payload mentioning
        ``choices`` (even ``choices: None``) via :meth:`_require_attr_surface`. That guard is right
        for the normal surface — there is ONE vocabulary model (``options``) and ``choices`` is off
        it — but it leaves no way for the migration to retire the legacy attribute through
        ``set_field``. This method is that way: it exists SOLELY to drop the retired ``choices``
        attribute of a field, modelled on :meth:`reset_field`/:meth:`delete_field` (derive a
        placement, then emit a scoped REMOVE op DIRECTLY — never routed through the attr-surface
        guard).

        It emits a SINGLE version-conditional ``update_item`` REMOVE on the ``choices`` path
        (``REMOVE <map>.<key>.choices``) — NO whole-row ``put_item`` replace (R3.3 / steering 39);
        DynamoDB leaves every sibling attribute physically untouched.

        Idempotent / safe no-op: if the field's stored spec carries NO ``choices`` attribute (an
        already-migrated row, or a never-legacy field), NOTHING is written — the method returns a
        no-op result rather than emitting an empty op set (``apply_ops`` requires a non-empty op
        set). Re-running the backfill therefore writes nothing once ``choices`` is gone.
        """
        snapshot = self._read_snapshot(tenant_id)
        placement = self._resolve_placement(tenant_id, field_key, snapshot=snapshot)
        stored = self._stored_field_spec(snapshot, placement)
        if "choices" not in stored:
            # Already migrated (or never legacy) → safe no-op. Do NOT call apply_ops with an empty
            # op set (it requires a non-empty sequence). Report the no-op explicitly.
            return {"version": None, "idempotent_replay": False, "no_op": True}
        op = {"action": REMOVE, "path": [placement["map"], placement["key"], "choices"]}
        return self._apply(
            tenant_id, [op], snapshot=snapshot, client_op_id=client_op_id
        )

    def remove_inline_options(
        self, tenant_id: str, field_key: str, *, client_op_id: str | None = None
    ) -> dict:
        """Remove a field's stale inline ``options`` attribute via a scoped Change-Op REMOVE (03a C7).

        The C7 COMPANION to :meth:`remove_legacy_choices` for SCOPE-BACKED (W2) and REFERENCE (W1)
        fields. Those fields do NOT source their vocabulary from inline ``options``: a scope-backed
        field is sourced from the ``config#scope`` dimension (``scope_vocab``) and a reference field
        from the live catalog, both injected at the C4 read seam. A stale inline ``options`` payload
        left on such a field is exactly the two-copies disease the write-edge guard (W1/W2) refuses
        going forward — so the C7 backfill must DROP it (never CONVERT a legacy ``choices`` into
        inline ``options`` for these kinds), letting the dimension/catalog be the SOLE source.

        Like :meth:`remove_legacy_choices`, this is DELIBERATELY NOT part of the normal client write
        surface: :meth:`set_field` cannot write inline ``options`` onto a scope-backed/reference
        field (the W1/W2 source-integrity guards reject it), so there is no way to clear a legacy
        inline ``options`` through ``set_field``. This method is that way — it is modelled on
        :meth:`remove_legacy_choices` / :meth:`reset_field`: derive a placement, then emit a scoped
        REMOVE op DIRECTLY (never routed through the attr-surface or source-integrity guards).

        It emits a SINGLE version-conditional ``update_item`` REMOVE on the ``options`` path
        (``REMOVE <map>.<key>.options``) — NO whole-row ``put_item`` replace (R3.3 / steering 39);
        DynamoDB leaves every sibling attribute physically untouched.

        Idempotent / safe no-op: if the field's stored spec carries NO ``options`` attribute (a
        field that never had inline vocabulary, or an already-cleaned row), NOTHING is written — the
        method returns the SAME no-op result shape :meth:`remove_legacy_choices` returns rather than
        emitting an empty op set (``apply_ops`` requires a non-empty op set). Re-running the backfill
        therefore writes nothing once the inline ``options`` is gone.
        """
        snapshot = self._read_snapshot(tenant_id)
        placement = self._resolve_placement(tenant_id, field_key, snapshot=snapshot)
        stored = self._stored_field_spec(snapshot, placement)
        if "options" not in stored:
            # No inline options to drop (never had one, or already cleaned) → safe no-op. Do NOT
            # call apply_ops with an empty op set (it requires a non-empty sequence).
            return {"version": None, "idempotent_replay": False, "no_op": True}
        op = {"action": REMOVE, "path": [placement["map"], placement["key"], "options"]}
        return self._apply(
            tenant_id, [op], snapshot=snapshot, client_op_id=client_op_id
        )

    # ── Group ops (attrs ⊆ {label, order}) ──────────────────────────────────────────────

    def set_group(
        self,
        tenant_id: str,
        group_key: str,
        attrs: Mapping[str, Any],
        *,
        client_op_id: str | None = None,
    ) -> dict:
        """Set/clear a functional group's ``{label, order}``, materialising a base group if absent.

        ``attrs`` MUST be a subset of :data:`GROUP_ATTRS`. Each op addresses ONLY
        ``functional_groups.<gkey>`` (or a single aspect of it), so other groups are physically
        untouched and the catalog cannot truncate (R4.1/R4.2). Absent-vs-null semantics as per
        :meth:`set_field`.
        """
        self._require_attr_surface(attrs, GROUP_ATTRS, op="set_group")

        def derive(snapshot):
            placement = self._group_placement(group_key, snapshot=snapshot)
            return self._attr_ops(placement, attrs)

        return self._run(tenant_id, derive, client_op_id=client_op_id)

    def delete_group(
        self, tenant_id: str, group_key: str, *, client_op_id: str | None = None
    ) -> dict:
        """Delete a functional group explicitly (refused-when-non-empty guard is task 2.6).

        Emits a single ``REMOVE functional_groups.<gkey>`` op. Before emitting the op, the
        :meth:`_guard_delete_group` guard refuses deleting a group that still holds fields (R4.3) —
        so a delete can never orphan a field into a group that no longer exists.
        """

        def derive(snapshot):
            placement = self._group_placement(group_key, snapshot=snapshot)
            self._guard_delete_group(tenant_id, group_key, placement, snapshot=snapshot)
            return [self._remove_entry_op(placement)]

        return self._run(tenant_id, derive, client_op_id=client_op_id)

    # ── Surface guard (the disjointness enforcement) ────────────────────────────────────

    @staticmethod
    def _require_attr_surface(
        attrs: Mapping[str, Any], allowed: frozenset, *, op: str
    ) -> None:
        """Reject an attrs payload that is not a mapping or carries a key outside ``allowed``.

        This is the structural barrier that makes the ops DISJOINT (design-review Must-fix #3): a
        key not in this op's surface — most importantly an ``application_*`` key on ``set_field`` or
        a definition key on ``set_field_application`` — raises :class:`ConfigFieldsCrudError` BEFORE
        any placement read or repository call. An empty payload is also rejected (a no-op write is a
        caller error, never a silent success).
        """
        if not isinstance(attrs, Mapping):
            raise ConfigFieldsCrudError(
                f"{op}: attrs must be an object of attribute changes"
            )
        if not attrs:
            raise ConfigFieldsCrudError(
                f"{op}: at least one attribute change is required"
            )
        extra = [k for k in attrs if k not in allowed]
        if extra:
            raise ConfigFieldsCrudError(
                f"{op} may only write {sorted(allowed)!r}; rejected out-of-surface "
                f"attribute(s) {sorted(extra)!r} — these belong to a different, disjoint op"
            )

    @staticmethod
    def _reject_duplicate_option_values(attrs: Mapping[str, Any], *, op: str) -> None:
        """Reject an ``options`` list carrying a duplicate ``value`` BEFORE any repository call
        (design C3 / P4; R2.4; steering 30).

        The one canonical vocabulary is ``options``, a list of ``{"value": ...}`` entries (a bare
        string is shorthand for ``{"value": <string>}``). Two entries with the SAME ``value`` are a
        content error — the stored vocabulary would carry an ambiguous duplicate the reader cannot
        round-trip meaningfully — so this is a deliberate, caller-safe rejection via
        :class:`ConfigFieldsCrudError` (subclasses :class:`ValueError`). The edge maps it to a 400
        with a GENERIC client message; the full detail (which values duplicated) rides the exception
        string the edge LOGS server-side, never echoed to the client (no ``str(e)`` leak,
        steering 30). The guard fires at the write edge, before placement reads or ``apply_ops`` —
        a duplicate never reaches storage.

        An ABSENT ``options`` attr is untouched; a non-list / non-``value`` shape is left to the
        normal validation path (this guard only speaks to duplicate VALUES within a well-shaped
        list). ``None`` entry values are ignored (no value to compare).
        """
        options = attrs.get("options")
        if not isinstance(options, (list, tuple)):
            return
        seen: set = set()
        duplicates: list = []
        for entry in options:
            value = entry.get("value") if isinstance(entry, Mapping) else entry
            if value is None:
                continue
            if value in seen:
                duplicates.append(value)
            else:
                seen.add(value)
        if duplicates:
            # Dedupe while preserving first-seen order for a stable, diagnosable message. This
            # string is LOGGED server-side by the edge (keyed to a correlation id); the client sees
            # only the edge's generic 400 message (steering 30).
            ordered_unique = list(dict.fromkeys(duplicates))
            raise ConfigFieldsCrudError(
                f"{op}: options may not contain duplicate value(s) "
                f"{ordered_unique!r} — each option value must be unique"
            )
