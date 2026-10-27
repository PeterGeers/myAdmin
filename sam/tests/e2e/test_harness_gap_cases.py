"""
Harness GAP cases (spec 03, Phase 8 → task 8.7; design C5 "Harness gaps the review flagged (R9)";
requirements R9).

Design C5 enumerates FIVE R9 harness gaps the external review flagged. They are deliberately
split across tasks so no two files double-own a case:

  * gap (i)  — deployed-stage IAM smoke test .......... task **8.6** (NOT here; local DynamoDB
               does not enforce IAM, so the ``dynamodb:UpdateItem`` grant can only be proven
               against the real TEST stack).
  * gap (ii) — two-client stale-writer ................ task **4.3**
               (``test_concurrency_stale_writer_e2e.py``; NOT here).
  * gap (iii)— **randomized op-sequence** through ``assert_change_op_isolated`` ..... THIS FILE.
  * gap (iv) — **LIST→MAP migration invariant** ....................................... THIS FILE
               (the INVARIANT-ENGINE view; the pure transform + a resolved-view invariant already
               live in ``sam/tests/test_functional_groups_list_to_map_migration.py`` — this file
               adds the ``assert_change_op_isolated`` framing so the e2e invariant suite carries
               the gap, and asserts the two do not drift, rather than re-testing the transform).
  * gap (v)  — **orphaned-override** case ............................................. THIS FILE.

What each case proves
---------------------
1. **Randomized op-sequence (gap iii).** A SEEDED (deterministic) RNG draws a sequence of real
   Change-Ops — ``set_field`` / ``set_field_application`` / ``set_group`` / ``reset_field`` /
   ``delete_field`` / ``delete_group`` — over the seeded REAL h-dcn row, applies each through the
   production ``ConfigFieldsCrudService`` → ``MembersConfigWriteRepository`` graph on LIVE local
   DynamoDB, and asserts EACH op's isolation invariant holds (``assert_change_op_isolated``) as
   state accumulates across the sequence. The single-op round-trip cases
   (``test_config_fields_roundtrip_red.py``) prove each op kind in isolation from a pristine row;
   THIS proves isolation STILL holds op-after-op as the overlay grows/shrinks — the condition a
   fixed example set can miss. The seed is printed on failure so a counterexample reproduces.
   Container-gated: SKIPS cleanly when the ``amazon/dynamodb-local`` container is absent.

2. **LIST→MAP migration invariant (gap iv).** The ``functional_groups`` LIST→MAP migration must
   change STORAGE SHAPE ONLY — a migrated row resolves byte-identically to the already-MAP
   fixture, and the full 6-group catalog survives. The resolved-view proof already lives in the
   unit test; here it is re-expressed through the invariant ENGINE
   (``assert_change_op_isolated`` with an EMPTY allowed-paths op — "nothing may change") so the
   e2e invariant suite itself carries the migration gap, and a drift between the two committed
   real-data fixtures (LIST vs MAP) reddens this gate. Pure (no container) — runs always.

3. **Orphaned-override (gap v).** A base field renamed/removed in CODE leaves a dangling tenant
   ``overrides.<dotted>`` entry. The resolver MUST SURFACE it fail-loud (raise ``OverlayError``
   "overrides an unknown field"), NOT silently drop the tenant's intent and resolve wrong. This
   is the startup/harness check design C5 (v) asks for: the dangling override is detected the
   moment the tenant config is resolved, so a code rename that orphans an override cannot pass
   silently. Pure/in-memory (fits the resolver) — runs always.

**Validates: Requirements 9 (R9 harness gaps iii, iv, v)**
"""

from __future__ import annotations

import json
import os
import random
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

from services import projection_schema as schema  # noqa: E402

from sam.members.domain._field_models import (  # noqa: E402
    FixedFieldOverride,
    OverlayError,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudService  # noqa: E402
from sam.members.domain.field_resolver import FieldResolver  # noqa: E402
from sam.members.migration.functional_groups_list_to_map import (  # noqa: E402
    convert_functional_groups,
)
from sam.members.repository.projection_config_reader import MembersProjectionReader  # noqa: E402
from sam.members.repository.projection_config_write_repository import (  # noqa: E402
    MembersConfigWriteRepository,
)
from sam.tests.e2e.invariant import ChangeOp, assert_change_op_isolated  # noqa: E402

_FIXTURES = os.path.join(_REPO_ROOT, "sam", "tests", "fixtures")
_MAP_FIXTURE = os.path.join(_FIXTURES, "hdcn_config_fields_overlay.json")
_LIST_FIXTURE = os.path.join(
    _FIXTURES, "hdcn_config_fields_overlay_legacy_groups_list.json"
)


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ════════════════════════════════════════════════════════════════════════════════════════
# GAP (iv) — LIST→MAP migration invariant, via the invariant ENGINE (PURE — no container)
# ════════════════════════════════════════════════════════════════════════════════════════
# The resolved-view migration invariant (a migrated LIST row resolves identically to the MAP
# fixture + full catalog survives) is PROVEN against the real h-dcn row in the unit test
# `test_functional_groups_list_to_map_migration.py`
# (`test_migrated_list_row_resolves_identically_to_the_map_fixture`). We do NOT re-test the
# transform here. Instead we express the SAME invariant through the e2e invariant ENGINE
# (`assert_change_op_isolated`) so the e2e suite itself carries gap (iv): the migration is
# framed as a Change-Op that is allowed to change NOTHING in the resolved view — an EMPTY
# allowed-paths op — so any resolved-view difference the migration introduced is reported by
# the engine as a leak at the exact drifted path.


def _resolved_via_overlay(overlay_json: dict) -> dict:
    """Resolve an overlay JSON (fields / overrides / functional_groups) to a stable keyed dict.

    Resolves through the REAL reader over a minimal fake query table (mirroring the unit test's
    `_resolved_via_reader`), so this matches exactly what production resolves (steering 39: trust
    runs, not inference). Keyed by field key / group key so the invariant engine's path matching
    is identity-stable.
    """
    table = _FakeQueryTable()
    tenant_id = overlay_json["tenant_id"]
    table.put(
        {
            schema.PARTITION_KEY_ATTR: tenant_id,
            schema.SORT_KEY_ATTR: schema.build_sort_key(
                schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS
            ),
            "fields": overlay_json["fields"],
            "overrides": overlay_json["overrides"],
            "functional_groups": overlay_json["functional_groups"],
            schema.VERSION_ATTR: 1,
        }
    )
    config = FieldResolver(MembersProjectionReader(table=table)).resolve(tenant_id)
    fields = {
        f.key: {
            "functional_group": f.functional_group,
            "group": f.group,
            "type": getattr(f.type, "value", f.type),
            "order": f.order,
            "label": dict(f.label or {}),
        }
        for f in config.fields
    }
    groups = {
        g.key: {"label": dict(g.label or {}), "order": g.order}
        for g in config.functional_groups
    }
    return {"fields": fields, "functional_groups": groups}


class _FakeQueryTable:
    """Minimal in-memory DynamoDB Table stand-in (query side only) — mirrors the sibling reader
    tests' fake so the real reader/resolver run unchanged against a legacy LIST or a MAP row."""

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def put(self, item: dict) -> None:
        self.store[(item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])] = dict(item)

    def query(self, KeyConditionExpression=None):
        expr = KeyConditionExpression.get_expression()
        tenant_id = expr["values"][1]
        return {"Items": [dict(v) for k, v in self.store.items() if k[0] == tenant_id]}


@pytest.mark.unit
def test_list_to_map_migration_is_a_no_change_op_in_the_resolved_view():
    """gap (iv): the LIST→MAP migration changes STORAGE shape only. Framed through the invariant
    engine as a Change-Op permitted to change NOTHING: resolve the legacy LIST row, migrate its
    groups to MAP, resolve again, and assert `assert_change_op_isolated` finds ZERO leaks — any
    resolved-view difference the migration introduced would be reported at its exact path."""
    legacy = _load(_LIST_FIXTURE)
    legacy.pop("_comment", None)

    before = _resolved_via_overlay(legacy)

    migrated = dict(legacy)
    migrated["functional_groups"] = convert_functional_groups(legacy["functional_groups"])
    after = _resolved_via_overlay(migrated)

    # A migration op is allowed to change NOTHING in the resolved view (storage shape only).
    migration_op = ChangeOp(
        kind="functional_groups_list_to_map_migration",
        target="functional_groups",
        allowed_paths=frozenset(),  # nothing may change in the RESOLVED record
    )
    assert_change_op_isolated(before, migration_op, after)

    # And the full 6-group catalog survives the shape change (no truncation) — the structural
    # point of the migration (design C6 / occurrence-3).
    assert set(after["functional_groups"]) == {
        "personal",
        "address",
        "membership",
        "motor",
        "financial",
        "administrative",
    }


@pytest.mark.unit
def test_committed_list_and_map_fixtures_carry_the_same_catalog_engine_level():
    """Belt check at the e2e seam: the two committed real-data fixtures (legacy LIST + migrated
    MAP) name the SAME functional-group catalog, so the migration invariant above cannot silently
    rot because a fixture drifted. (The unit test asserts this too; keeping a copy at the e2e seam
    means the e2e suite fails loudly if the fixtures diverge, independent of the unit run.)"""
    list_groups = set(convert_functional_groups(_load(_LIST_FIXTURE)["functional_groups"]))
    map_groups = set(convert_functional_groups(_load(_MAP_FIXTURE)["functional_groups"]))
    assert list_groups == map_groups == {
        "personal",
        "address",
        "membership",
        "motor",
        "financial",
        "administrative",
    }


# ════════════════════════════════════════════════════════════════════════════════════════
# GAP (v) — ORPHANED-OVERRIDE case (PURE / in-memory — fits the resolver, no container)
# ════════════════════════════════════════════════════════════════════════════════════════
# A base field renamed/removed in CODE leaves a dangling tenant `overrides.<dotted>` entry. The
# resolver's `_reject_invalid_overlay` already surfaces this FAIL-LOUD: an override whose dotted
# key is not among the live FIXED/CALCULATED fields raises `OverlayError` "overrides an unknown
# field". This is exactly the startup/harness check design C5 (v) asks for — the dangling override
# is detected at RESOLVE time, so a code rename that orphans an override cannot resolve silently
# wrong. These cases pin that behaviour so a future resolver change can't regress it to a silent
# drop.

_ORPHAN_DOTTED = "personal.favourite_colour"  # a plausible base dotted key that does NOT exist in code


def _resolve(overlay: TenantOverlay, tenant_id: str = "orphan-tenant"):
    provider = StaticOverlayProvider({tenant_id: overlay})
    return FieldResolver(provider).resolve(tenant_id)


@pytest.mark.unit
def test_orphaned_override_is_surfaced_fail_loud_not_silently_dropped():
    """gap (v): a tenant override keyed by a dotted key whose base field was renamed/removed in
    code is a DANGLING override. The resolver SURFACES it fail-loud (OverlayError), rather than
    silently ignoring the tenant's intent and resolving wrong."""
    overlay = TenantOverlay(
        overrides={_ORPHAN_DOTTED: FixedFieldOverride(label={"en": "Favourite colour"})}
    )
    with pytest.raises(OverlayError) as excinfo:
        _resolve(overlay)

    # The failure names the exact orphaned dotted key AND the reason — a surfaced orphan, not a
    # vague error, so an operator can see which override dangled when the code catalog changed.
    assert _ORPHAN_DOTTED in excinfo.value.reasons, (
        "the orphaned override's dotted key must be named in the surfaced reasons"
    )
    assert "unknown field" in excinfo.value.reasons[_ORPHAN_DOTTED], (
        "the surfaced reason must identify the override as targeting a field no longer in code"
    )


@pytest.mark.unit
def test_orphaned_override_alongside_valid_overrides_still_surfaces_only_the_orphan():
    """A mixed overlay — one VALID base override (`personal.gender`) and one ORPHANED override —
    still resolves fail-loud, and the surfaced reasons name ONLY the orphan, not the valid one.
    So the harness check is precise: it flags the dangling override without false-positiving on a
    legitimate one (the operator sees exactly what to fix after a code rename)."""
    overlay = TenantOverlay(
        overrides={
            "personal.gender": FixedFieldOverride(label={"en": "Sex"}),  # VALID — gender exists
            _ORPHAN_DOTTED: FixedFieldOverride(visible=False),  # ORPHANED — no such base field
        }
    )
    with pytest.raises(OverlayError) as excinfo:
        _resolve(overlay)

    assert _ORPHAN_DOTTED in excinfo.value.reasons, "the orphan must be surfaced"
    assert "personal.gender" not in excinfo.value.reasons, (
        "a VALID override must NOT be flagged — the orphan check must not false-positive"
    )


@pytest.mark.unit
def test_non_orphaned_overlay_resolves_cleanly():
    """Control: an overlay whose overrides ALL target live base fields resolves without error —
    the orphan check does not fire on a healthy config (no false alarm)."""
    overlay = TenantOverlay(
        overrides={"personal.gender": FixedFieldOverride(label={"en": "Sex"})}
    )
    config = _resolve(overlay)  # must not raise
    assert any(f.key == "gender" for f in config.fields), (
        "the valid override's base field must still resolve"
    )


# ════════════════════════════════════════════════════════════════════════════════════════
# GAP (iii) — RANDOMIZED op-sequence through assert_change_op_isolated (container-gated e2e)
# ════════════════════════════════════════════════════════════════════════════════════════
# Deterministic (seeded) RNG draws a sequence of real Change-Ops over the seeded REAL h-dcn row,
# applies each through the production ConfigFieldsCrudService → MembersConfigWriteRepository graph
# on LIVE local DynamoDB, and asserts EACH op's isolation invariant holds as overlay state
# accumulates. The whole class SKIPS cleanly when the container is absent (via the conftest
# `seeded_config_fields_table` fixture chain), so a plain unit run is unaffected (steering 34/42).

pytest_e2e = pytest.mark.e2e

# A fixed battery of seeds — deterministic, so a failure always reproduces from the same seed.
_SEQUENCE_SEEDS = [1, 7, 42, 1337, 2026]
_OPS_PER_SEQUENCE = 12


def _serialize_resolved(config) -> dict:
    """Serialize a resolved FieldConfig into a stable keyed dict for the invariant engine.

    Fields keyed by field key, groups by group key, so a path like `fields.<key>.<attr>` /
    `functional_groups.<gkey>.<attr>` is identity-stable across adds/deletes/reorders (a tuple
    diffed positionally would read every shifted index as a change)."""
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


_version_counter = 0


def _monotonic_version() -> str:
    global _version_counter
    _version_counter += 1
    return f"v-rand-{_version_counter:06d}"


class _SequenceHarness:
    """Drives a seeded random op-sequence over the live seeded h-dcn row, asserting isolation
    per op. Each generated op carries (a) the identity-keyed service call to apply it and (b) the
    :class:`ChangeOp` descriptor naming the paths it is ALLOWED to change — so the SAME engine
    that proves the single-op cases proves each step of the sequence."""

    def __init__(self, table, tenant_id: str):
        self._table = table
        self._tenant_id = tenant_id
        # Track which tenant-added variable fields + materialized groups currently exist so the
        # generator only draws edits/deletes of things that are present (a delete of an absent key
        # is not an isolation question). Base field keys used for override ops are drawn from a
        # fixed real set below.
        self._variable_fields: set[str] = set()
        # Tenant-authored (non-base) groups the sequence created. ONLY these are safely
        # deletable: a BASE group (personal/membership/…) always holds base fields that resolve
        # into it, so the service (correctly) refuses to delete it — deleting one would orphan
        # those base fields. A freshly-created tenant group key that no field references is empty
        # and therefore deletable. (Materializing a base group via set_group does NOT make it
        # empty, so base groups are never offered to delete_group.)
        self._tenant_groups: set[str] = set()

    # -- live reader/writer wiring (fresh per call → no stale partition cache) ----------------
    def _reader(self) -> MembersProjectionReader:
        return MembersProjectionReader(table=self._table)

    def _service(self) -> ConfigFieldsCrudService:
        reader = self._reader()
        repo = MembersConfigWriteRepository(table=self._table, version_fn=_monotonic_version)
        return ConfigFieldsCrudService(repo, reader=reader)

    def _read_resolved(self) -> dict:
        config = FieldResolver(self._reader()).resolve(self._tenant_id)
        return _serialize_resolved(config)

    # -- the op generator: returns (apply_callable, ChangeOp) or None to skip ------------------
    _BASE_FIELDS = ["gender", "first_name", "last_name", "email", "birth_date"]
    _BASE_GROUPS = ["personal", "address", "membership"]
    _VAR_FIELD_POOL = ["club_motor", "club_note", "club_flag", "club_size", "club_region"]
    _TENANT_GROUP_POOL = ["club_extra", "club_misc", "club_aux"]

    def _gen_op(self, rng: random.Random):
        kinds = [
            "set_field",
            "set_field_application",
            "set_group",
            "reset_field",
            "add_field",
            "delete_field",
            "create_tenant_group",
            "delete_group",
        ]
        kind = rng.choice(kinds)

        if kind == "set_field":
            key = rng.choice(self._BASE_FIELDS)
            order = rng.randint(1, 99)

            def apply():
                self._service().set_field(self._tenant_id, key, {"order": order})

            return apply, ChangeOp.set_field_attr(key, "order")

        if kind == "set_field_application":
            key = rng.choice(self._BASE_FIELDS)
            vis = bool(rng.getrandbits(1))

            def apply():
                self._service().set_field_application(
                    self._tenant_id, key, {"application_visible": vis}
                )

            return apply, ChangeOp.set_field_application(key, "application_visible")

        if kind == "set_group":
            # Edit a BASE group's order — materializes a base-group override entry; the catalog
            # cannot truncate (R4.1/R4.2). Only the named group's `order` may change.
            gkey = rng.choice(self._BASE_GROUPS)
            order = rng.randint(1, 99)

            def apply():
                self._service().set_group(self._tenant_id, gkey, {"order": order})

            return apply, ChangeOp.set_group(gkey, "order")

        if kind == "reset_field":
            # reset_field reverts a base-field override; it may only change that field's
            # resolved attrs back toward base — allow the field's whole subtree.
            key = rng.choice(self._BASE_FIELDS)

            def apply():
                self._service().reset_field(self._tenant_id, key)

            return apply, ChangeOp(
                kind="reset_field",
                target=key,
                allowed_paths=frozenset({f"fields.{key}"}),
            )

        if kind == "add_field":
            available = [k for k in self._VAR_FIELD_POOL if k not in self._variable_fields]
            if not available:
                return None  # pool exhausted this sequence — skip
            key = rng.choice(available)

            def apply():
                self._service().set_field(
                    self._tenant_id,
                    key,
                    {
                        "type": "string",
                        "label": {"en": key},
                        "functional_group": "personal",
                        "order": rng.randint(1, 50),
                    },
                )
                self._variable_fields.add(key)

            return apply, ChangeOp.add_field(key)

        if kind == "delete_field":
            if not self._variable_fields:
                return None  # nothing added yet to delete — skip
            key = rng.choice(sorted(self._variable_fields))

            def apply():
                self._service().delete_field(self._tenant_id, key)
                self._variable_fields.discard(key)

            return apply, ChangeOp.delete_field(key)

        if kind == "create_tenant_group":
            # Create a fresh tenant (non-base) group key with no field referencing it — an EMPTY
            # catalog group, which is later safely deletable. Only functional_groups.<gkey> may
            # appear.
            available = [g for g in self._TENANT_GROUP_POOL if g not in self._tenant_groups]
            if not available:
                return None
            gkey = rng.choice(available)
            order = rng.randint(1, 99)

            def apply():
                self._service().set_group(
                    self._tenant_id, gkey, {"order": order, "label": {"en": gkey}}
                )
                self._tenant_groups.add(gkey)

            return apply, ChangeOp(
                kind="create_tenant_group",
                target=gkey,
                allowed_paths=frozenset({f"functional_groups.{gkey}"}),
            )

        if kind == "delete_group":
            # Only delete a TENANT-created empty group (no field references it). A base group is
            # never deletable here: base fields always resolve into it, so the service refuses the
            # delete (proven by the group-delete guard) — offering it would be a generator bug, not
            # an isolation question.
            deletable = sorted(self._tenant_groups)
            if not deletable:
                return None
            gkey = rng.choice(deletable)

            def apply():
                self._service().delete_group(self._tenant_id, gkey)
                self._tenant_groups.discard(gkey)

            return apply, ChangeOp.delete_group(gkey)

        return None  # pragma: no cover - defensive

    def run(self, seed: int, n_ops: int) -> None:
        rng = random.Random(seed)
        applied = 0
        for step in range(n_ops):
            generated = self._gen_op(rng)
            if generated is None:
                continue
            apply, op = generated
            before = self._read_resolved()
            apply()
            after = self._read_resolved()
            try:
                assert_change_op_isolated(before, op, after)
            except AssertionError as exc:  # pragma: no cover - only on a real isolation leak
                raise AssertionError(
                    f"RANDOMIZED SEQUENCE isolation leak at seed={seed} step={step} "
                    f"(op {applied + 1} applied) kind={op.kind!r} target={op.target!r}.\n"
                    f"Reproduce with: _SequenceHarness(...).run(seed={seed}, n_ops={n_ops}).\n"
                    f"{exc}"
                ) from exc
            applied += 1


@pytest_e2e
@pytest.mark.parametrize("seed", _SEQUENCE_SEEDS)
def test_randomized_op_sequence_preserves_isolation_per_op(seeded_config_fields_table, seed):
    """gap (iii): a SEEDED random sequence of real Change-Ops over the seeded h-dcn row keeps the
    isolation invariant op-after-op. Each op changes ONLY what it names even as overlay state
    accumulates — the condition single-op cases can miss. The seed is parametrized so each run is
    deterministic and a failure reproduces exactly (the harness prints the seed + step)."""
    table = seeded_config_fields_table["table"]
    tenant_id = seeded_config_fields_table["tenant_id"]
    harness = _SequenceHarness(table, tenant_id)
    harness.run(seed=seed, n_ops=_OPS_PER_SEQUENCE)
