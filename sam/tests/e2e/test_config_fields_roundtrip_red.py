"""
REAL-DATA round-trip invariant cases for ``config#fields`` CRUD — Phase 1 task 1.4 PROVEN GREEN by
Phase 2 (task 2.8). Design C5/D1/D2, requirements R9.

================================================================================================
WHAT CHANGED AT TASK 2.8 (read before touching a case)
================================================================================================
These cases were authored RED in Phase 1 (task 1.4) against the OLD whole-row ``put_config``
REPLACE path: a partial body REPLACED the whole row, so the four ``overrides`` /
``functional_groups`` cases leaked (stripped sibling attrs; truncated the catalog) — RED was the
Phase-1 SUCCESS condition, the proof-before-fix. Phase 2 (``ConfigFieldsCrudService`` +
``MembersConfigWriteRepository.apply_ops`` path ``update_item``, tasks 2.2–2.7) landed the fix.

Task 2.8 RE-POINTS these cases at the NEW Change-Op write path (:class:`_ChangeOpWriter` below)
and they are now GREEN: read resolved → apply ONE identity-keyed Change-Op → read resolved →
assert ONLY the named target changed. The ``@xfail`` markers the Phase-1 file carried on the four
``overrides`` / ``functional_groups`` cases (and on the delete no-op case) have been REMOVED — per
those cases' own notes: "when Phase 2 lands, remove xfail … so a regression reddens the gate"
(R11.3). Every case is now a live, asserting acceptance-gate case: a regression that re-introduces
the strip/truncation reddens CI.

The write path is the real production object graph exercised end-to-end against a LIVE local
DynamoDB table seeded with the REAL ``h-dcn`` row (steering 39: *trust runs, not inference* —
``sam/tests/fixtures/hdcn_config_fields_overlay.json``):

    ConfigFieldsCrudService (identity-keyed op)
        → MembersConfigWriteRepository.apply_ops (single version-conditional update_item)
        → local DynamoDB

Because an ``update_item`` only ever writes the attributes the ops name, a partial op set is
structurally unable to truncate ``functional_groups`` or strip a sibling attribute — the guarantee
is in the verb, not in a flawless merge (design D2). That is what turns every case GREEN.

================================================================================================
THE OP KINDS PROVEN ISOLATED (each asserts isolation via ``assert_change_op_isolated``)
================================================================================================
1. set a BASE field attribute          — ``set_field`` on a base field (→ overrides.<dotted>)
2. ADD a variable field                 — a new tenant field (→ fields.<key>)
3. EDIT a variable field                — change an existing variable field's attrs
4. DELETE a variable field              — ``delete_field`` removes a tenant field (+ an EXPLICIT
                                          before/after presence assert — the 1.4 subagent flagged
                                          that the isolation engine proves no-leak, not delete
                                          COMPLETENESS, so a real delete must be shown to remove
                                          the entry, not merely "not leak")
5. edit a BASE GROUP's order + label    — ``set_group`` on a catalog group (catalog survives)
6. set ENUM choices on a field          — ``set_field`` rewrites only the field's choice data
7. set APPLICATION attrs on a field     — ``set_field_application`` (the four form attrs only)

Each case: read resolved → apply the Change-Op → read resolved → assert ONLY the named target
changed (everything else byte-identical). Isolation is asserted through the generic engine
(:func:`assert_change_op_isolated`, task 1.2); the delete case adds the completeness assert.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudService  # noqa: E402
from sam.members.domain.field_resolver import FieldResolver  # noqa: E402
from sam.members.repository.projection_config_reader import MembersProjectionReader  # noqa: E402
from sam.members.repository.projection_config_write_repository import (  # noqa: E402
    MembersConfigWriteRepository,
)
from sam.tests.e2e.invariant import ChangeOp, assert_change_op_isolated  # noqa: E402

# The whole module is container-gated e2e; it SKIPS cleanly without the local-DynamoDB container
# (via the seeded_config_fields_table fixture chain, task 1.1) so unit runs are unaffected.
pytestmark = pytest.mark.e2e


# ─────────────────────────────────────────────────────────────────────────────────────
# Round-trip reader + Change-Op writer over the LIVE seeded local-DynamoDB table
# ─────────────────────────────────────────────────────────────────────────────────────
class _ResolvedReader:
    """Reads the FULL resolved ``config#fields`` record from the live table as a STABLE keyed dict.

    The invariant engine (task 1.2) diffs an origin-agnostic tree and matches an op's
    ``allowed_paths`` (e.g. ``fields.gender.label``, ``functional_groups.motor.order``) by key. The
    resolver returns a ``FieldConfig`` whose ``fields`` / ``functional_groups`` are TUPLES — if
    diffed positionally an add/delete/reorder would read as a change at every shifted index. So this
    reader re-keys them by identity (field ``key``, group ``key``) so a path like ``fields.<key>``
    is stable across adds/deletes and the engine's prefix match works as designed.

    CRITICAL (no stale cache): :class:`MembersProjectionReader` caches a partition per instance, so
    this reader builds a FRESH reader for EVERY read — otherwise the second (post-write) read would
    serve the cached pre-write state and the harness would falsely pass. The round-trip reads real
    DynamoDB state both times.
    """

    def __init__(self, table, *, scope_vocab=None):
        self._table = table
        self._scope_vocab = scope_vocab

    def read_resolved(self, record_id: str) -> dict:
        reader = MembersProjectionReader(table=self._table)  # fresh per read — no stale cache
        config = FieldResolver(reader).resolve(record_id, scope_vocab=self._scope_vocab)
        return _serialize_resolved(config)


def _serialize_scope(scope) -> dict | None:
    """Serialize a resolved field's ``scope`` sub-object into comparable primitives, or ``None``.

    The scope sub-object (:class:`FieldScope`) is carried onto the resolved field (remediation
    R3.5) so the authoring UI can read it back. Emitting it here lets the invariant engine PROVE a
    field op preserves ``scope`` verbatim (R5.2 / design C4): a write that strips or mutates the
    scope sub-object of an untouched field shows up as a leak at ``fields.<key>.scope.*``.
    """
    if scope is None:
        return None
    return {
        "enabled": scope.enabled,
        "values": list(scope.values),
        "label": dict(scope.label or {}),
        "required_for": list(scope.required_for),
    }


def _serialize_resolved(config) -> dict:
    """Serialize a resolved ``FieldConfig`` into a stable keyed dict for the invariant engine.

    - ``fields`` → ``{field.key: {attr: value}}`` (every resolved attribute that is not None/absent),
    - ``functional_groups`` → ``{group.key: {label, order}}``.

    Only comparable, identity-stable primitives are emitted (dicts for i18n labels, lists for
    choices, scalars otherwise), so the deep diff compares like-for-like. ``scope`` is included
    (serialized to primitives) so the SCOPE-preservation invariant (R5.2 / C4) can prove a field
    op never strips or mutates an untouched field's ``scope`` sub-object.
    """
    fields: dict = {}
    for f in config.fields:
        fields[f.key] = {
            "group": f.group,
            "functional_group": f.functional_group,
            "type": getattr(f.type, "value", f.type),
            "required": f.required,
            "visible": f.visible,
            "order": f.order,
            "label": dict(f.label or {}),
            "choices": list(f.choices) if f.choices is not None else None,
            "scope": _serialize_scope(f.scope),
            "application_visible": f.application_visible,
            "application_required": f.application_required,
            "application_choices": (
                list(f.application_choices) if f.application_choices is not None else None
            ),
        }
    groups = {
        g.key: {"label": dict(g.label or {}), "order": g.order}
        for g in config.functional_groups
    }
    return {"fields": fields, "functional_groups": groups}


class _ChangeOpWriter:
    """Applies a Change-Op through the NEW Phase-2 Change-Op write path (the thing now PROVEN).

    Wires the REAL :class:`ConfigFieldsCrudService` to the REAL
    :class:`MembersConfigWriteRepository` (its ``apply_ops`` single version-conditional
    ``update_item``) over the live table, plus a reader for the service's strongly-consistent
    validate-and-place read. Each ``apply`` translates the op descriptor into ONE identity-keyed
    service call (``set_field`` / ``set_field_application`` / ``set_group`` / ``delete_field`` /
    ``reset_field``) — NEVER a whole-row body. The service decides storage placement + the
    create-vs-update verb; the repository issues the single path ``update_item``. DynamoDB leaves
    every attribute the op did not name physically untouched, so the invariant engine finds no leak.

    A FRESH reader is built per ``apply`` (like :class:`_ResolvedReader`) so the service's
    placement/version read sees live DynamoDB state, not a cached pre-write partition.
    """

    def __init__(self, table, tenant_id: str):
        self._table = table
        self._tenant_id = tenant_id

    def _service(self) -> ConfigFieldsCrudService:
        # Fresh reader per op → the strongly-consistent placement read sees live state, and the
        # base_version is resolved from the current row (no stale cache across the round-trip).
        reader = MembersProjectionReader(table=self._table)
        repository = MembersConfigWriteRepository(
            table=self._table, version_fn=_monotonic_version
        )
        return ConfigFieldsCrudService(repository, reader=reader)

    def apply(self, record_id: str, op: ChangeOp) -> None:
        handler = self._OP_HANDLERS.get(op.kind)
        if handler is None:  # pragma: no cover - guards against an unhandled op kind
            raise AssertionError(f"no Change-Op handler for op kind {op.kind!r}")
        handler(self, op)

    # -- per-op handlers: translate the descriptor into ONE identity-keyed service call --------
    def _set_field_attr(self, op: ChangeOp) -> None:
        # A base-field DEFINITION edit (label). The service places it under overrides.<dotted>
        # and SETs ONLY that aspect — sibling attrs (choices/order/type) survive.
        self._service().set_field(
            self._tenant_id, op.target, {"label": {"nl": "Gewijzigd", "en": "Changed"}}
        )

    def _add_field(self, op: ChangeOp) -> None:
        # Add a tenant VARIABLE field → placed under fields.<key> (CREATE verb, whole-entry SET).
        self._service().set_field(
            self._tenant_id,
            op.target,
            {
                "type": "string",
                "label": {"nl": "Nieuw veld", "en": "New field"},
                "functional_group": "motor",
                "order": 80,
                "required": False,
            },
        )

    def _edit_field(self, op: ChangeOp) -> None:
        # Edit an EXISTING variable field → per-aspect SETs under fields.<key> (UPDATE verb).
        self._service().set_field(
            self._tenant_id,
            op.target,
            {
                "label": {"nl": "Bewerkt", "en": "Edited"},
                "functional_group": "administrative",
                "order": 12,
                "required": True,
            },
        )

    def _delete_field(self, op: ChangeOp) -> None:
        # Explicit delete verb — REMOVE fields.<key>. No usage probe wired, so a variable field
        # with no member data deletes cleanly (the real deletion the whole-object path could not do).
        self._service().delete_field(self._tenant_id, op.target)

    def _set_group(self, op: ChangeOp) -> None:
        # Edit a BASE group's order + label → per-aspect SETs under functional_groups.<gkey>; the
        # other catalog groups are physically untouched (no whole-catalog write → no truncation).
        self._service().set_group(
            self._tenant_id,
            op.target,
            {"order": 99, "label": {"nl": "Herbenoemd", "en": "Renamed"}},
        )

    def _set_enum_choices(self, op: ChangeOp) -> None:
        # Rewrite only the field's choice data (a DEFINITION attr) → SET overrides.<dotted>.choices
        # (or the whole entry on CREATE). label/order/type survive.
        self._service().set_field(
            self._tenant_id,
            op.target,
            {
                "choices": [
                    {"value": "man", "label": {"nl": "Man", "en": "Man"}},
                    {"value": "vrouw", "label": {"nl": "Vrouw", "en": "Female"}},
                    {"value": "anders", "label": {"nl": "Anders", "en": "Other"}},
                ]
            },
        )

    def _set_application(self, op: ChangeOp) -> None:
        # The form-builder op: the FOUR application_* attrs ONLY — structurally unable to touch a
        # DEFINITION attr (D3(A)). SET overrides.<dotted>.application_* only.
        self._service().set_field_application(
            self._tenant_id,
            op.target,
            {"application_visible": True, "application_required": False},
        )

    def _set_scope(self, op: ChangeOp) -> None:
        # Author a field's `scope` sub-object via set_field (scope IS a DEFINITION attr). The
        # value is the whole scope map; the repository stores it and the reader rebuilds it as a
        # FieldScope verbatim — proving "a set_field carrying scope writes it unchanged" (R5.2).
        self._service().set_field(
            self._tenant_id,
            op.target,
            {
                "scope": {
                    "enabled": True,
                    "values": ["Noord", "Zuid", "Oost", "West"],
                    "label": {"nl": "Regio", "en": "Region"},
                    "required_for": ["Members_CRUD"],
                }
            },
        )

    def _set_unrelated_attr(self, op: ChangeOp) -> None:
        # A Change-Op touching a DIFFERENT field's non-scope attr — used to prove it never mutates
        # another (scope-carrying) field's `scope` sub-object (the "scope preserved verbatim"
        # isolation guarantee, R5.2 / design C4).
        self._service().set_field(
            self._tenant_id, op.target, {"label": {"nl": "Ongewijzigd", "en": "Unrelated"}}
        )

    _OP_HANDLERS = {
        "set_field_attr": _set_field_attr,
        "add_field": _add_field,
        "edit_field": _edit_field,
        "delete_field": _delete_field,
        "set_group": _set_group,
        "set_enum_choices": _set_enum_choices,
        "set_field_application": _set_application,
        "set_scope": _set_scope,
        "set_unrelated_attr": _set_unrelated_attr,
    }


_version_counter = 0


def _monotonic_version() -> str:
    """A strictly-increasing version stamp so repeated writes in one test never collide.

    The repository bumps ``version`` on every ``apply_ops``; a deterministic monotonic stamp keeps
    the optimistic-lock base distinct across the before/after reads without depending on wall-clock
    resolution.
    """
    global _version_counter
    _version_counter += 1
    return f"v-e2e-{_version_counter:06d}"


# ─────────────────────────────────────────────────────────────────────────────────────
# Fixtures bridging the task-1.1 seeded table to the reader/writer pair
# ─────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def roundtrip(seeded_config_fields_table):
    """A (reader, writer, record_id) bundle over the live seeded h-dcn row.

    Depends on ``seeded_config_fields_table`` (task 1.1) so it SKIPS cleanly when the local-DynamoDB
    container/endpoint is absent — a plain unit run is unaffected.
    """
    table = seeded_config_fields_table["table"]
    tenant_id = seeded_config_fields_table["tenant_id"]
    return {
        "reader": _ResolvedReader(table),
        "writer": _ChangeOpWriter(table, tenant_id),
        "record_id": tenant_id,
    }


def _run(roundtrip, op: ChangeOp) -> dict:
    """read resolved → apply the Change-Op → read resolved → assert ONLY the op's target changed.

    Returns ``{"before": ..., "after": ...}`` so a case can add a completeness assert (the delete
    case proves the entry actually vanished, not merely "did not leak").
    """
    reader = roundtrip["reader"]
    writer = roundtrip["writer"]
    record_id = roundtrip["record_id"]

    before = reader.read_resolved(record_id)
    writer.apply(record_id, op)
    after = reader.read_resolved(record_id)
    assert_change_op_isolated(before, op, after)
    return {"before": before, "after": after}


# ─────────────────────────────────────────────────────────────────────────────────────
# The seven round-trip cases — all GREEN under the Phase-2 Change-Op path (acceptance gate)
# ─────────────────────────────────────────────────────────────────────────────────────
def test_set_base_field_attr_is_isolated(roundtrip):
    # 1. Set a BASE field attribute (gender's label). Only fields.gender.label may change.
    #    GREEN under Phase 2: set_field SETs ONLY overrides.personal.gender.label, so the stored
    #    choices / order / type survive (the old whole-entry replace stripped them).
    op = ChangeOp.set_field_attr("gender", "label")
    _run(roundtrip, op)


def test_add_variable_field_is_isolated(roundtrip):
    # 2. ADD a variable field. Only the new field's subtree may appear; the catalog + every other
    #    field byte-identical. The CREATE verb seeds the whole fields.<key> entry in one SET.
    op = ChangeOp.add_field("motor_mileage")
    result = _run(roundtrip, op)
    # Completeness: the add actually introduced the field.
    assert "motor_mileage" not in result["before"]["fields"]
    assert "motor_mileage" in result["after"]["fields"]


def test_edit_variable_field_is_isolated(roundtrip):
    # 3. EDIT an existing variable field (the real fixture's `notes` overlay field). Only that
    #    field's named attrs may change (per-aspect SET under fields.notes, UPDATE verb).
    op = ChangeOp(
        kind="edit_field",
        target="notes",
        allowed_paths=frozenset(
            {
                "fields.notes.label",
                "fields.notes.functional_group",
                "fields.notes.order",
                "fields.notes.required",
            }
        ),
    )
    _run(roundtrip, op)


def test_delete_variable_field_removes_only_that_field(roundtrip):
    # 4. DELETE a variable field (`notes`). Only fields.notes may vanish — and it MUST actually
    #    vanish. Phase 2's explicit delete_field op REMOVEs fields.notes; the whole-object path
    #    could only no-op (the 1.4 subagent's flagged harness gap).
    #
    #    Isolation (engine) proves NO OTHER field/group changed. The engine catches LEAKS, not a
    #    MISSING change, so a no-op would also "pass" isolation — therefore we add the EXPLICIT
    #    before/after PRESENCE assert the 1.4 subagent asked for: the field is present before and
    #    gone after. That is the delete-COMPLETENESS proof the isolation engine cannot give.
    op = ChangeOp.delete_field("notes")
    result = _run(roundtrip, op)
    assert "notes" in result["before"]["fields"], (
        "fixture sanity: `notes` must be an authored variable field before the delete"
    )
    assert "notes" not in result["after"]["fields"], (
        "delete_field must ACTUALLY remove the field entry (completeness, not just isolation) — "
        "a no-op here is the whole-object-path bug Phase 2 fixes"
    )


def test_edit_base_group_order_and_label_is_isolated(roundtrip):
    # 5. Edit a BASE group's order + label (the `motor` catalog group). Only that group's
    #    order+label may change; the other FIVE catalog groups MUST survive.
    #    GREEN under Phase 2: set_group addresses only functional_groups.motor — a partial groups
    #    save can no longer truncate the catalog (the proven occurrence-3 bug, now structural).
    op = ChangeOp.set_group("motor", "order", "label")
    result = _run(roundtrip, op)
    # Completeness: the catalog did NOT shrink (every pre-existing group still present).
    assert set(result["before"]["functional_groups"]) == set(
        result["after"]["functional_groups"]
    ), "a base-group edit must NOT drop any group (occurrence-3 truncation guard)"


def test_set_enum_choices_on_field_is_isolated(roundtrip):
    # 6. Set ENUM choices on a field (gender). Only the field's choice data may change; its label /
    #    order / group / other attrs are preserved (the old override rewrite stripped the label).
    #    Use the `set_enum_choices` op KIND (dispatches to the choices-writer handler) with the
    #    choices path as the sole allowed target — NOT `ChangeOp.set_field_attr`, whose kind
    #    `set_field_attr` dispatches to the LABEL writer and would (correctly) be flagged as a leak.
    op = ChangeOp(
        kind="set_enum_choices",
        target="gender",
        allowed_paths=frozenset({"fields.gender.choices"}),
    )
    _run(roundtrip, op)


def test_set_application_attrs_on_field_is_isolated(roundtrip):
    # 7. Set the four application_* attrs on a field (gender). Only the named application attrs may
    #    change; the field DEFINITION (label/type/order/choices) and every other field/group
    #    untouched — the form-builder op is structurally unable to strip a definition (D3(A)).
    op = ChangeOp.set_field_application(
        "gender", "application_visible", "application_required"
    )
    _run(roundtrip, op)


# ─────────────────────────────────────────────────────────────────────────────────────
# Task 3.2 — SCOPE correctness (R5.2; design C4), proven end-to-end against the real h-dcn row
# ─────────────────────────────────────────────────────────────────────────────────────
# Three guarantees C4/R5.2 asserts, each proven here against the LIVE seeded row (not inference):
#
#   (a) a `set_field` carrying `scope` writes it unchanged — round-trip read rebuilds the exact
#       scope sub-object (enabled / values / label / required_for), proving the write stored it
#       verbatim (not mangled / not dropped);
#   (b) a Change-Op touching OTHER attrs never mutates a field's `scope` — an unrelated
#       `set_field` on `gender` leaves `region.scope` byte-identical (the isolation engine now
#       sees `scope`, because `_serialize_resolved` emits it);
#   (c) field/group ops only ever address `config#fields` — `config#scope` is a SEPARATE row the
#       field CRUD path never writes (the service targets config_id="fields" exclusively), and a
#       scope-dimension-backed CHOICELESS enum (`region`) STILL sources its choices from the scope
#       vocabulary (single source) AFTER the field write.
#
# REGION is h-dcn's real scope axis: in the committed fixture it is a choiceless enum (only
# `application_visible`), whose dropdown values come from the `config#scope` dimension, surfaced
# to the resolver as `scope_vocab`. We drive that path with a reader that carries the region
# vocabulary, mirroring the production wiring (app.py derives scope_vocab from ScopeConfig).

_REGION_VOCAB = {
    "region": (
        "Brabant/Zeeland",
        "Duitsland",
        "Friesland",
        "Geen",
        "Groningen/Drenthe",
        "Limburg",
        "Noord Holland",
        "Oost",
        "Utrecht",
        "Zuid Holland",
    )
}


@pytest.fixture
def scope_roundtrip(seeded_config_fields_table):
    """A (reader, writer, record_id) bundle whose READER carries the region scope vocabulary.

    Identical to the base ``roundtrip`` fixture except the reader resolves with
    ``scope_vocab=_REGION_VOCAB`` — so the choiceless `region` enum sources its choices from the
    scope dimension (`config#scope`), exactly as production does (app.py derives the vocab from
    the separate ``config#scope`` row via ``ScopeConfig``). This lets the SCOPE cases prove the
    single-source choice sourcing survives a `config#fields` write.
    """
    table = seeded_config_fields_table["table"]
    tenant_id = seeded_config_fields_table["tenant_id"]
    return {
        "reader": _ResolvedReader(table, scope_vocab=_REGION_VOCAB),
        "writer": _ChangeOpWriter(table, tenant_id),
        "record_id": tenant_id,
    }


def test_set_field_scope_is_written_verbatim(scope_roundtrip):
    # (a) A `set_field` carrying a `scope` sub-object writes it UNCHANGED. Author scope onto
    #     `region`, then read the resolved record back and assert the scope round-tripped exactly
    #     (enabled / values / label / required_for), and that ONLY `region.scope` changed.
    op = ChangeOp(
        kind="set_scope",
        target="region",
        allowed_paths=frozenset({"fields.region.scope"}),
    )
    result = _run(scope_roundtrip, op)
    before_scope = result["before"]["fields"]["region"]["scope"]
    after_scope = result["after"]["fields"]["region"]["scope"]
    assert before_scope is None, "fixture sanity: region carries no scope before the write"
    # The scope sub-object was stored and rebuilt verbatim (not mangled, not dropped).
    assert after_scope == {
        "enabled": True,
        "values": ["Noord", "Zuid", "Oost", "West"],
        "label": {"nl": "Regio", "en": "Region"},
        "required_for": ["Members_CRUD"],
    }, "set_field carrying scope must write the scope sub-object verbatim (R5.2)"


def test_field_op_preserves_an_untouched_fields_scope(scope_roundtrip):
    # (b) A Change-Op touching OTHER attrs never mutates another field's `scope`. First author a
    #     scope onto `region`, THEN do an unrelated `set_field` on `gender` and assert
    #     `region.scope` survives byte-identical (the scope-preservation isolation guarantee).
    #
    #     The unrelated op is allowed to change ONLY `gender.label`; if the write had leaked onto
    #     `region.scope` (the kind of whole-object strip Phase 2 structurally prevents) the
    #     isolation engine would flag `fields.region.scope.*` as an unexpected diff.
    writer = scope_roundtrip["writer"]
    reader = scope_roundtrip["reader"]
    record_id = scope_roundtrip["record_id"]

    # Seed the scope axis first (its own isolated write, asserted by case (a)).
    writer.apply(
        record_id,
        ChangeOp(kind="set_scope", target="region",
                 allowed_paths=frozenset({"fields.region.scope"})),
    )
    seeded = reader.read_resolved(record_id)
    region_scope = seeded["fields"]["region"]["scope"]
    assert region_scope is not None, "precondition: region now carries a scope sub-object"

    # Now an UNRELATED field op on gender — it must not touch region.scope.
    op = ChangeOp(
        kind="set_unrelated_attr", target="gender",
        allowed_paths=frozenset({"fields.gender.label"}),
    )
    before = reader.read_resolved(record_id)
    writer.apply(record_id, op)
    after = reader.read_resolved(record_id)
    assert_change_op_isolated(before, op, after)
    assert after["fields"]["region"]["scope"] == region_scope, (
        "an unrelated field op must preserve another field's scope sub-object VERBATIM (R5.2)"
    )


def test_scope_dimension_backed_choiceless_enum_still_sources_after_field_write(scope_roundtrip):
    # (c) A scope-dimension-backed CHOICELESS enum (`region`) STILL sources its choices from the
    #     scope vocabulary (single source) after a `config#fields` write — the field CRUD path
    #     never touches the separate `config#scope` row. We prove the single-source sourcing
    #     survives an unrelated field write.
    reader = scope_roundtrip["reader"]
    writer = scope_roundtrip["writer"]
    record_id = scope_roundtrip["record_id"]

    # Make `region` a CHOICELESS enum (the committed fixture seeds it with no `type`, so it
    # resolves as a plain string by default). It declares NO inline choices — so its values can
    # ONLY come from the scope dimension (`config#scope`, surfaced as `scope_vocab`). This is the
    # exact h-dcn scope-axis shape: a choiceless enum whose dropdown is the scope vocabulary.
    # (A bare set_field by identity — the real Change-Op write path, no raw-shape body.)
    writer._service().set_field(record_id, "region", {"type": "enum"})

    before = reader.read_resolved(record_id)
    # region sources its choices from the scope vocab BEFORE the unrelated write (single source).
    assert before["fields"]["region"]["choices"] == list(_REGION_VOCAB["region"]), (
        "precondition: a choiceless scope enum's choices come from the config#scope vocabulary "
        "(single source), not from inline choices"
    )

    # An unrelated field write (add a variable field) — addresses config#fields only.
    writer.apply(record_id, ChangeOp.add_field("motor_mileage"))

    after = reader.read_resolved(record_id)
    # The scope-sourced choices are UNCHANGED — the field write did not disturb the single source.
    assert after["fields"]["region"]["choices"] == list(_REGION_VOCAB["region"]), (
        "a config#fields write must not change a scope-dimension-backed enum's sourced choices — "
        "config#scope is a separate row the field CRUD path never writes (R5.2 / design C4)"
    )
