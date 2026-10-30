"""
Spec 03 Task 2.2 — ``ConfigFieldsCrudService``: the DISJOINT, identity-keyed Change-Op surface
for ``config#fields`` mutations (design C1; design-review Must-fix #3).

This is the single domain authority for ``config#fields`` CRUD. It accepts a mutation BY DOMAIN
IDENTITY (a field/group key + the attribute change), decides storage placement server-side, and
emits a Change-Op set that it hands to the repository's
:meth:`~sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository.apply_ops`
(the task-2.4 contract). It NEVER lets a caller supply a storage path, a whole overlay, or a whole
``functional_groups`` object — each op addresses ONE path, so a partial payload is structurally
unable to truncate the catalog or any slice (steering 39; R1/R4).

Why DISJOINT ops (design-review Must-fix #3)
--------------------------------------------
Field DEFINITION and application-form configuration are two NON-OVERLAPPING surfaces:

- :meth:`set_field` owns field DEFINITION attributes ONLY
  (``{type,label,order,required,visible,choices,options,scope,functional_group}``). It is
  STRUCTURALLY INCAPABLE of writing an ``application_*`` attribute — passing one is rejected.
- :meth:`set_field_application` owns the FOUR application attributes ONLY
  (``{application_visible, application_required, application_choices, format}``). It is
  STRUCTURALLY INCAPABLE of writing a definition attribute (R7.2 under R7=A, design D3(A)).

Because the two op surfaces do not overlap in name, the application-form builder's single op
(``set_field_application``) can never reach a field/group definition — that disjointness IS the
"narrow surface" stability guarantee D3(A) rests on (it is not enforced by a separate table).

Layering (steering 35/39 — dependency inversion)
-------------------------------------------------
This is a **domain** service: NO ``boto3``, NO DynamoDB / table resolution. It depends only on
the pure fixed-field registry (for placement) and on a repository exposing ``apply_ops`` (in
production the concrete
:class:`~sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository`,
in tests an in-memory fake). The repository owns the ``update_item`` mechanics and the version
conditional; this service owns INTENT → OPS translation and must not duplicate repository logic.

The ops contract this service produces (task 2.4)
-------------------------------------------------
Each op is ``{"action": SET|REMOVE, "path": [segment, ...], "value": <any for SET>}`` where
``path`` is a list of RAW key segments outer→inner (the repository binds every segment through
``ExpressionAttributeNames``, so a dotted ``"<group>.<key>"`` override key is a LITERAL segment,
never a nested path). ``SET``/``REMOVE``/``LEGACY_NO_VERSION`` are imported from the repository
module so the two planes cannot drift on the verb tokens. ``base_version`` sentinels:
``None`` (no row yet) / :data:`LEGACY_NO_VERSION` (existing legacy row) / an explicit version
string (optimistic lock). ``apply_ops`` raises :class:`ChangeOpError` / :class:`StaleVersionError`.

Placement / verb mechanics (TASK 2.3 — design-review Q2/Q8 + Must-fix #1)
------------------------------------------------------------------------
Each public op reads the resolved ``config#fields`` record ONCE, STRONGLY-CONSISTENT, ONLY to
validate + decide placement/version — NOT a read-merge-write. The read flag flows all the way to
the repository ``Query`` (``get_raw_fields_overlay(..., consistent_read=True)``) so a stale
eventually-consistent read can never produce a spurious 409 (Should-fix). The mechanics:

- :meth:`_read_snapshot` — the single strongly-consistent validate-and-place read per op.
- :meth:`_resolve_placement` / :meth:`_group_placement` — map a domain identity to its storage
  path segments (``fields.<key>`` variable / ``overrides.<dotted>`` base-calc /
  ``functional_groups.<gkey>`` group) AND choose the CREATE-vs-UPDATE verb by ENTRY EXISTENCE in
  the snapshot (``create`` flag).
- :meth:`_attr_ops` — emits the chosen verb: a CREATE seeds the WHOLE entry with one
  ``SET #o.#k = :whole`` (never ``if_not_exists`` parent-seed + child-set in one expression —
  DynamoDB rejects it, Must-fix #1; the parent MAP exists by the C6 row skeleton); an UPDATE
  emits per-aspect ``SET #o.#k.#attr = :v`` / ``REMOVE`` ops.
- :meth:`_base_version_from_snapshot` — resolves the conditional-write base version from the SAME
  snapshot: a version present → optimistic lock; a legacy versionless row → ``LEGACY_NO_VERSION``;
  the empty/never-authored shape → ``None`` (first write onto the skeleton).

The dotted override key is handed to the repository as a LITERAL segment; the repository binds
every segment through ``ExpressionAttributeNames`` (so a ``.`` is a key name, never a nested path,
design-review Q2) — this service only guarantees the segments are correct.

Delete-safety guards (TASK 2.6 — design C1; R4.3; design-review Should-fix)
--------------------------------------------------------------------------
A delete is ALWAYS an explicit op (never inferred from omission, R2.5) AND must never leave the
record — or member data — inconsistent. Two guards fire BEFORE the ``REMOVE`` op is emitted:

- :meth:`_guard_delete_group` (R4.3) — refuse deleting a functional group that STILL HOLDS
  fields. "Holds a field" is read from the SAME consistent snapshot: any variable field
  (``fields.<key>``) or authored override (``overrides.<dotted>``) whose resolved
  ``functional_group`` is this group. Deleting a non-empty group would orphan those fields into
  a group that no longer exists, so it is refused with a caller-safe reason — the admin must
  first move or delete the fields.
- :meth:`_guard_delete_field` (design C1; review Should-fix) — refuse deleting a VARIABLE field
  that is IN USE: either member records store a value under the key, OR a group/application
  reference points at it. "In use" is reported by an optional, injected ``usage_probe``
  (:class:`FieldUsageProbe`-shaped) — the domain stays storage-agnostic (steering 35/39); the
  probe owns the member-data / reference lookup. When a field is in use the delete is refused
  with a caller-safe reason that offers ``visible=false`` (hide) as the safe alternative, so a
  delete can never orphan member data. A base field "delete" is :meth:`reset_field` (revert),
  never removing a base definition (Q9) — :meth:`delete_field` already refuses a base field.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sam.members.domain._membership_errors import MEMBERSHIP_TYPE_FIELD_KEY
from sam.members.domain.fixed_fields import field_by_key

from sam.members.repository.projection_config_write_repository import (
    LEGACY_NO_VERSION,
    REMOVE,
    SET,
    StaleVersionError,
)

__all__ = [
    "ConfigFieldsCrudService",
    "ConfigFieldsCrudError",
    "FIELD_DEFINITION_ATTRS",
    "FIELD_APPLICATION_ATTRS",
    "GROUP_ATTRS",
]

# ── The DISJOINT attribute surfaces (design C1; design-review Must-fix #3) ──────────────

#: Field DEFINITION attributes — the ONLY attrs :meth:`set_field` may write. Deliberately EXCLUDES
#: every ``application_*`` attr and ``format`` (those live on :data:`FIELD_APPLICATION_ATTRS`), so
#: a definition op is structurally unable to touch application-form config.
#:
#: ``choices`` was RETIRED (spec 03a, C2): the write surface now accepts ONLY the one canonical
#: ``options`` vocabulary. ``choices`` is no longer an accepted definition attribute, so a write
#: carrying it is rejected out-of-surface (:class:`ConfigFieldsCrudError`) — there is one
#: vocabulary model end-to-end (R2.1, R3.3). The storage key stays ``overrides``, served under the
#: wire key ``fixed_overrides`` (the one-key contract is unchanged); the write remains a Change-Op
#: on a single path (no whole-row replace).
FIELD_DEFINITION_ATTRS = frozenset(
    {
        "type",
        "label",
        "order",
        "required",
        "visible",
        "options",
        "scope",
        "functional_group",
    }
)

#: The FOUR application attributes — the ONLY attrs :meth:`set_field_application` may write. Fully
#: qualified so they never collide with the definition ``visible``/``required``/``choices`` names;
#: this is the structural barrier the application-form builder writes behind (D3(A)).
FIELD_APPLICATION_ATTRS = frozenset(
    {
        "application_visible",
        "application_required",
        "application_choices",
        "format",
    }
)

#: Group attributes — the ONLY attrs :meth:`set_group` may write.
GROUP_ATTRS = frozenset({"label", "order"})

#: The three parent maps on the ``config#fields`` row (the row-skeleton contract, design C6). Used
#: only to NAME the outer path segment; the service never writes a whole parent map. ``overrides``
#: is the STORAGE key the ops write to (and the resolver's canonical read key) — the write path
#: addresses ``overrides.<dotted>`` at rest; the reader serves that SAME map under the authoring
#: WIRE key ``fixed_overrides`` (the one-key contract in ``get_raw_fields_overlay``).
_FIELDS_MAP = "fields"
_OVERRIDES_MAP = "overrides"
_GROUPS_MAP = "functional_groups"

#: Map a STORAGE map name to the key it is served under in the reader's WIRE overlay shape. Only
#: ``overrides`` differs (served as ``fixed_overrides``); ``fields`` / ``functional_groups`` keep
#: their names. Used by :meth:`ConfigFieldsCrudService._entry_exists` to look an entry up in the
#: consistent snapshot by the key the reader actually serves it under.
_MAP_TO_WIRE_KEY = {
    _OVERRIDES_MAP: "fixed_overrides",
    _FIELDS_MAP: "fields",
    _GROUPS_MAP: "functional_groups",
}

#: The reader's wire-overlay container keys inspected for emptiness when deciding "no row yet"
#: vs "legacy row with no version" (base_version case ii vs iii).
_WIRE_CONTAINER_KEYS = ("fields", "fixed_overrides", "functional_groups")

#: The ``config#fields`` id the ops target (one SAM-owned config row).
_CONFIG_ID_FIELDS = "fields"


def _snapshot_is_empty(snapshot: Mapping[str, Any]) -> bool:
    """True when the wire overlay is the empty/never-authored shape (all containers empty).

    The reader returns ``{"fields": {}, "fixed_overrides": {}, "functional_groups": {}}`` for a
    tenant with no ``config#fields`` row (empty-is-valid). That shape must be read as "no row yet"
    (base_version ``None``), not as a legacy versionless row — so a first write onto the C6
    skeleton uses the ``attribute_not_exists(sk)`` condition, not a spurious legacy lock.
    """
    for key in _WIRE_CONTAINER_KEYS:
        container = snapshot.get(key)
        if isinstance(container, Mapping) and container:
            return False
    return True


class ConfigFieldsCrudError(ValueError):
    """A deliberate, caller-safe rejection of a malformed / out-of-surface CRUD request.

    Raised BEFORE any repository call (steering 35/39 — no raw internals) when an op is asked to
    write an attribute outside its disjoint surface (e.g. an ``application_*`` key handed to
    :meth:`set_field`, or a definition key handed to :meth:`set_field_application`), or when an
    identity / attrs payload is malformed. Subclasses :class:`ValueError` so existing
    ``except ValueError`` edges keep working.
    """


class ConfigFieldsCrudService:
    """Identity-keyed Change-Op authority for ``config#fields`` (design C1).

    Each public method accepts a DOMAIN IDENTITY (a field/group key) plus the change, never a
    storage path or a whole object. It normalises the change into a set of SET/REMOVE path ops and
    delegates the atomic, version-conditional write to the repository's ``apply_ops`` (task 2.4).

    Args:
        repository: An object exposing
            ``apply_ops(tenant_id, config_id, ops, base_version, client_op_id=None)`` — in
            production the concrete
            :class:`~sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository`,
            in tests an in-memory fake. Injectable so the domain stays storage-agnostic (no boto3).
        reader: Optional resolved-view reader used by task 2.3's placement/version mechanics
            (``ConsistentRead`` validate-and-place read). Left injectable now; the 2.2 surface does
            not require it (the stubs degrade to first-write placement), so unit tests can omit it.
        usage_probe: Optional member-data / reference usage probe used by the task-2.6
            :meth:`delete_field` safety guard. Any object exposing
            ``field_in_use(tenant_id, field_key) -> bool`` (or the richer
            ``field_usage(tenant_id, field_key) -> Mapping`` described on :meth:`_field_usage`).
            The domain stays storage-agnostic (steering 35/39) — the probe owns the member-data /
            reference lookup. When no probe is wired the field-usage guard cannot observe member
            data and does not block on it (the snapshot-level reference check still runs); a probe
            is injected in production so a real delete can never orphan member data.
    """

    def __init__(self, repository, reader=None, usage_probe=None):
        self._repository = repository
        self._reader = reader
        self._usage_probe = usage_probe

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
        self._require_attr_surface(
            def_attrs, FIELD_DEFINITION_ATTRS, op="set_field"
        )
        self._reject_duplicate_option_values(def_attrs, op="set_field")

        def derive(snapshot):
            placement = self._resolve_placement(
                tenant_id, field_key, snapshot=snapshot
            )
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
            placement = self._resolve_placement(
                tenant_id, field_key, snapshot=snapshot
            )
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
            placement = self._resolve_placement(
                tenant_id, field_key, snapshot=snapshot
            )
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
            placement = self._resolve_placement(
                tenant_id, field_key, snapshot=snapshot
            )
            if placement["map"] != _FIELDS_MAP:
                raise ConfigFieldsCrudError(
                    f"delete_field only deletes a tenant VARIABLE field; {field_key!r} is a "
                    f"base/calculated field — use reset_field to drop its override (R2.5)"
                )
            self._guard_delete_field(
                tenant_id, field_key, placement, snapshot=snapshot
            )
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
        placement = self._resolve_placement(
            tenant_id, field_key, snapshot=snapshot
        )
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
        placement = self._resolve_placement(
            tenant_id, field_key, snapshot=snapshot
        )
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
            self._guard_delete_group(
                tenant_id, group_key, placement, snapshot=snapshot
            )
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
            raise ConfigFieldsCrudError(f"{op}: attrs must be an object of attribute changes")
        if not attrs:
            raise ConfigFieldsCrudError(f"{op}: at least one attribute change is required")
        extra = [k for k in attrs if k not in allowed]
        if extra:
            raise ConfigFieldsCrudError(
                f"{op} may only write {sorted(allowed)!r}; rejected out-of-surface "
                f"attribute(s) {sorted(extra)!r} — these belong to a different, disjoint op"
            )

    @staticmethod
    def _reject_duplicate_option_values(
        attrs: Mapping[str, Any], *, op: str
    ) -> None:
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
        if dotted == MEMBERSHIP_TYPE_FIELD_KEY or field_key == MEMBERSHIP_TYPE_FIELD_KEY:
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

    # ── Op emission (absent = untouched / null = REMOVE that aspect) ────────────────────

    def _attr_ops(self, placement: Mapping[str, Any], attrs: Mapping[str, Any]) -> list[dict]:
        """Turn an attrs payload into Change-Ops under the resolved entry path, choosing the VERB
        by ENTRY EXISTENCE (design-review Must-fix #1 — the create-vs-update correction).

        Two cases, decided by ``placement["create"]`` (which the placement read set from the
        consistent record):

        - **CREATE (the entry does NOT yet exist):** emit a SINGLE ``SET <map>.<key> = :whole``
          whose value is the whole entry map (the non-``None`` attrs collected into one object).
          A child path ``SET <map>.<key>.<attr>`` would be rejected by DynamoDB because the parent
          entry does not exist, and ``if_not_exists`` parent-seed + child-set in one expression is
          the "Two document paths overlap" rejection (Must-fix #1). The parent MAP
          (``fields``/``overrides``/``functional_groups``) itself is guaranteed to exist by the row
          skeleton (C6), so a single whole-entry ``SET`` is legal and atomic. An explicit ``None``
          in a CREATE payload is simply absent from the seeded map (there is nothing yet to clear).
        - **UPDATE (the entry EXISTS):** emit ONE op per PRESENT attr addressing
          ``<map>.<key>.<attr>``: a non-``None`` value → ``SET``; an explicit ``None`` → ``REMOVE``
          (clear just that aspect). An attr the payload OMITS yields no op (left untouched).

        In both cases DynamoDB leaves every attribute the ops do not name physically untouched, so
        the write is structurally unable to truncate a sibling entry or slice (R1.3/R4.2).
        """
        entry_path = [placement["map"], placement["key"]]
        if placement.get("create"):
            # Seed the whole entry in one SET. A `None` has nothing to clear on a brand-new entry,
            # so it is dropped from the seed (absent = not-authored); every real value is included.
            whole_entry = {
                attr: value for attr, value in attrs.items() if value is not None
            }
            return [{"action": SET, "path": list(entry_path), "value": whole_entry}]

        ops: list[dict] = []
        for attr, value in attrs.items():
            path = [*entry_path, attr]
            if value is None:
                ops.append({"action": REMOVE, "path": path})
            else:
                ops.append({"action": SET, "path": path, "value": value})
        return ops

    @staticmethod
    def _remove_entry_op(placement: Mapping[str, Any]) -> dict:
        """A single ``REMOVE <map>.<key>`` op removing a whole field/override/group entry."""
        return {"action": REMOVE, "path": [placement["map"], placement["key"]]}

    def _apply(
        self,
        tenant_id: str,
        ops: list[dict],
        *,
        snapshot: Mapping[str, Any] | None,
        client_op_id: str | None,
    ) -> dict:
        """The single choke point: resolve the base version + delegate to ``apply_ops`` (task 2.4).

        Takes the SAME consistent snapshot the placement read produced so the base-version
        decision and the placement decision see one coherent view of the row (one strongly-
        consistent read per public op, not two). The op-emission shape handed to the repository is
        stable. Returns the repository result verbatim (``{"version": ..., "idempotent_replay":
        ...}``).
        """
        base_version = self._base_version_from_snapshot(snapshot)
        return self._repository.apply_ops(
            tenant_id=tenant_id,
            config_id=_CONFIG_ID_FIELDS,
            ops=ops,
            base_version=base_version,
            client_op_id=client_op_id,
        )

    def _run(
        self,
        tenant_id: str,
        derive,
        *,
        client_op_id: str | None,
    ) -> dict:
        """Read the consistent snapshot, derive the ops from it, and apply — with a GUARDED
        ONE-SHOT auto-retry on a version conflict (task 4.1; design C2/D5, review Should-fix).

        ``derive`` is a callable ``(snapshot) -> ops`` that RE-RUNS the op derivation (placement +
        verb choice + any safety guard) against WHATEVER snapshot it is handed. This is what makes
        the retry correct rather than a blind replay: under D3(A) the configurator and the
        form-builder share one ``config#fields`` row, so a row-level ``version`` conflict can be
        raised by an UNRELATED concurrent edit (e.g. another admin set a different field). On a
        :class:`StaleVersionError` we re-read the row STRONGLY-CONSISTENT, re-derive the ops against
        that fresh view (so a CREATE that the concurrent writer turned into an UPDATE — or a guard
        whose basis changed — is re-evaluated, never a stale replay), and retry the write ONCE.

        The guardrail (why retrying here is safe): every op this service emits is keyed by a single
        DOMAIN IDENTITY (one ``fields.<key>`` / ``overrides.<dotted>`` / ``functional_groups.<gkey>``
        path) and is IDEMPOTENT by that identity (SET the same attrs / REMOVE the same entry) — and
        :meth:`~...apply_ops` rejects overlapping paths up front — so re-applying the SAME intent
        onto a newer base is well-defined. We retry EXACTLY ONCE: if the second attempt also
        conflicts, we surface the :class:`StaleVersionError` (the edge maps it to a caller-safe 409
        "reload and retry"). We never loop, and we never paper over a genuine concurrent edit to the
        SAME identity — the re-derive + single-shot bound is the guard the review asked for. A
        malformed/out-of-surface request raises :class:`ConfigFieldsCrudError` from ``derive`` on
        the first pass and is never retried.
        """
        snapshot = self._read_snapshot(tenant_id)
        ops = derive(snapshot)
        try:
            return self._apply(
                tenant_id, ops, snapshot=snapshot, client_op_id=client_op_id
            )
        except StaleVersionError:
            # ONE guarded retry: re-read, re-derive against the fresh view, re-apply. A second
            # conflict is a genuine concurrent edit → surface the 409 (never loop).
            fresh_snapshot = self._read_snapshot(tenant_id)
            fresh_ops = derive(fresh_snapshot)
            return self._apply(
                tenant_id,
                fresh_ops,
                snapshot=fresh_snapshot,
                client_op_id=client_op_id,
            )

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
            overlay = reader.get_raw_fields_overlay(
                tenant_id, consistent_read=True
            )
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

    # ── Delete-safety guards (task 2.6 — design C1; R4.3; review Should-fix) ────────────

    def _guard_delete_field(
        self,
        tenant_id: str,
        field_key: str,
        placement: Mapping[str, Any],
        *,
        snapshot: Mapping[str, Any] | None = None,
    ) -> None:
        """Refuse deleting a VARIABLE field that is IN USE (design C1; review Should-fix).

        A delete must never orphan data. Two kinds of "in use" block the delete:

        - **Member data:** some member record stores a value under this field's key. Observed via
          the optional injected ``usage_probe`` (storage-agnostic — the domain never queries the
          members table itself, steering 35/39). When no probe is wired this leg cannot be checked
          and does not block (production always wires one).
        - **A dangling reference:** a group/application reference points at the field (e.g. an
          ``application_choices`` subset or a ``show_when`` condition naming it). The probe may also
          report this; the snapshot carries the field's own authored shape for a lightweight check.

        When the field is in use the delete is REFUSED with a caller-safe
        :class:`ConfigFieldsCrudError` that names the safe alternative — hide the field
        (``visible=false``) instead of deleting it, which preserves the stored member values while
        removing it from forms. The error carries NO raw internals (steering 39).
        """
        usage = self._field_usage(tenant_id, field_key)
        if usage is None:
            return
        reasons: list[str] = []
        if usage.get("member_data"):
            reasons.append("member records still store a value under it")
        if usage.get("references"):
            refs = usage["references"]
            if isinstance(refs, (list, tuple, set)):
                reasons.append(
                    "it is still referenced by " + ", ".join(sorted(str(r) for r in refs))
                )
            else:
                reasons.append("it is still referenced elsewhere")
        if not reasons:
            return
        raise ConfigFieldsCrudError(
            f"cannot delete field {field_key!r}: " + "; ".join(reasons) + ". "
            "Hide it instead (set visible=false) to keep existing data while removing it from "
            "forms."
        )

    def _field_usage(self, tenant_id: str, field_key: str) -> dict | None:
        """Ask the injected ``usage_probe`` whether ``field_key`` is in use, normalised to a dict.

        Returns ``{"member_data": bool, "references": <iterable|falsey>}`` or ``None`` when no
        probe is wired (usage unobservable → the member-data leg does not block). Accepts either
        probe shape:

        - a rich ``field_usage(tenant_id, field_key)`` returning a mapping with ``member_data`` /
          ``references`` keys (passed through), or
        - a boolean ``field_in_use(tenant_id, field_key)`` (normalised to
          ``{"member_data": <bool>}``).
        """
        probe = self._usage_probe
        if probe is None:
            return None
        if hasattr(probe, "field_usage"):
            usage = probe.field_usage(tenant_id, field_key)
            return dict(usage) if isinstance(usage, Mapping) else {}
        if hasattr(probe, "field_in_use"):
            return {"member_data": bool(probe.field_in_use(tenant_id, field_key))}
        return None

    def _guard_delete_group(
        self,
        tenant_id: str,
        group_key: str,
        placement: Mapping[str, Any],
        *,
        snapshot: Mapping[str, Any] | None = None,
    ) -> None:
        """Refuse deleting a functional group that STILL HOLDS fields (R4.3).

        Reads the SAME consistent snapshot used for placement: a group is non-empty when any
        AUTHORED field in the overlay — a variable field (``fields.<key>``) or a base-field
        override (``fixed_overrides.<dotted>``) — resolves into this group via its
        ``functional_group`` aspect. Deleting a non-empty group would orphan those fields into a
        group that no longer exists, so it is REFUSED with a caller-safe
        :class:`ConfigFieldsCrudError`; the admin must first move or delete the member fields.

        Note: this inspects the AUTHORED overlay (the snapshot), which is what the write addresses.
        A group holding only base fields whose membership is code-defined is a separate concern
        handled by the resolver; the authored-overlay check is the one that keeps a delete op from
        orphaning a tenant-authored field.
        """
        if not isinstance(snapshot, Mapping):
            return
        held = self._fields_in_group(snapshot, group_key)
        if held:
            raise ConfigFieldsCrudError(
                f"cannot delete group {group_key!r}: it still holds "
                + ", ".join(repr(k) for k in held)
                + ". Move or delete those fields first."
            )

    @staticmethod
    def _fields_in_group(snapshot: Mapping[str, Any], group_key: str) -> list[str]:
        """Authored field keys (variable + override) whose ``functional_group`` is ``group_key``.

        Scans the snapshot's ``fields`` and ``fixed_overrides`` wire containers; a spec assigns the
        group via its ``functional_group`` aspect. Returns the keys in a stable (sorted) order so
        the refusal message is deterministic.
        """
        held: list[str] = []
        for wire_key in ("fields", "fixed_overrides"):
            container = snapshot.get(wire_key)
            if not isinstance(container, Mapping):
                continue
            for key, spec in container.items():
                if isinstance(spec, Mapping) and spec.get("functional_group") == group_key:
                    held.append(key)
        return sorted(held)
