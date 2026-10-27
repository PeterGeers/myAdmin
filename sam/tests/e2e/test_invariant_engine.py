"""
Self-test for the E2E invariant ENGINE (Phase 1 task 1.2, design C5, R9.2/R9.4).

These are PURE unit tests of ``assert_change_op_isolated`` and its deep diff — no container, no
AWS, no local-DynamoDB fixture. They prove the detector itself is correct BEFORE it is used to
prove the CRUD is foolproof: it PASSES when a Change-Op touched only what it named, and it FAILS
(naming the exact leaked path) when the write touched anything else — the truncation/field-strip
class from ``.kiro/specs/Members/root-cause-analysis.md``.

The engine is generic (R9.4), so the self-test exercises it over BOTH a plain-dict resolved record
and a dataclass-based one, confirming origin-agnostic diffing.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.tests.e2e.invariant import (
    MISSING,
    ChangeOp,
    assert_change_op_isolated,
    diff_resolved,
    run_change_op_isolation,
)


def _resolved_record() -> dict:
    """A small synthetic Resolved_Record shaped like the config#fields resolved view.

    Two fields (one base, one with an application attr) and two functional groups — enough to
    distinguish "the named target changed" from "something else changed".
    """
    return {
        "fields": {
            "gender": {
                "label": {"nl": "Geslacht", "en": "Gender"},
                "order": 10,
                "functional_group": "personal",
                "application_visible": False,
            },
            "email": {
                "label": {"nl": "E-mail", "en": "Email"},
                "order": 20,
                "functional_group": "personal",
                "application_visible": True,
            },
        },
        "functional_groups": {
            "personal": {"label": {"nl": "Persoonlijk", "en": "Personal"}, "order": 10},
            "motor": {"label": {"nl": "Motor", "en": "Motor"}, "order": 40},
        },
    }


# ── PASSES for an isolated change ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_passes_when_only_the_named_field_attr_changed():
    before = _resolved_record()
    after = _resolved_record()
    after["fields"]["gender"]["label"] = {"nl": "Sekse", "en": "Sex"}  # the ONLY change

    op = ChangeOp.set_field_attr("gender", "label")
    assert_change_op_isolated(before, op, after)  # must NOT raise


@pytest.mark.unit
def test_passes_when_only_the_named_group_attr_changed():
    before = _resolved_record()
    after = _resolved_record()
    after["functional_groups"]["motor"]["order"] = 99  # the ONLY change

    op = ChangeOp.set_group("motor", "order")
    assert_change_op_isolated(before, op, after)


@pytest.mark.unit
def test_passes_when_a_whole_field_is_added_under_the_named_key():
    before = _resolved_record()
    after = _resolved_record()
    after["fields"]["motor_brand"] = {  # a whole new entry — the add op names the subtree
        "label": {"nl": "Merk", "en": "Brand"},
        "order": 50,
        "functional_group": "motor",
    }

    op = ChangeOp.add_field("motor_brand")
    assert_change_op_isolated(before, op, after)


@pytest.mark.unit
def test_passes_for_a_noop_write():
    # A write that changed nothing is trivially isolated.
    before = _resolved_record()
    after = _resolved_record()
    op = ChangeOp.set_field_attr("gender", "label")
    assert_change_op_isolated(before, op, after)


# ── FAILS (and names the leak) for a leaked change ────────────────────────────────────


@pytest.mark.unit
def test_fails_when_an_unnamed_field_attr_changed():
    before = _resolved_record()
    after = _resolved_record()
    after["fields"]["gender"]["label"] = {"nl": "Sekse", "en": "Sex"}  # the named change
    after["fields"]["email"]["order"] = 999  # LEAK: a different field changed too

    op = ChangeOp.set_field_attr("gender", "label")
    with pytest.raises(AssertionError) as exc:
        assert_change_op_isolated(before, op, after)
    assert "fields.email.order" in str(exc.value)


@pytest.mark.unit
def test_fails_when_a_functional_group_is_truncated():
    # The exact occurrence-3 shape: a group vanishes from the catalog as a side effect.
    before = _resolved_record()
    after = _resolved_record()
    after["functional_groups"]["personal"]["order"] = 11  # the intended named change
    del after["functional_groups"]["motor"]  # LEAK: the catalog shrank 2 -> 1

    op = ChangeOp.set_group("personal", "order")
    with pytest.raises(AssertionError) as exc:
        assert_change_op_isolated(before, op, after)
    msg = str(exc.value)
    assert "functional_groups.motor" in msg
    assert "<absent>" in msg  # the lost group renders as removed


@pytest.mark.unit
def test_fails_when_a_field_definition_is_stripped_by_an_application_write():
    # A form-builder op may touch ONLY application attrs; stripping a definition attr is a leak.
    before = _resolved_record()
    after = _resolved_record()
    after["fields"]["email"]["application_visible"] = False  # the named application change
    after["fields"]["email"]["label"] = {}  # LEAK: the definition label was stripped

    op = ChangeOp.set_field_application("email", "application_visible")
    with pytest.raises(AssertionError) as exc:
        assert_change_op_isolated(before, op, after)
    assert "fields.email.label" in str(exc.value)


# ── Origin-agnostic: works over dataclasses too (R9.4) ────────────────────────────────


@dataclass(frozen=True)
class _FakeField:
    label: str
    order: int


@dataclass(frozen=True)
class _FakeRecord:
    fields: dict = field(default_factory=dict)


@pytest.mark.unit
def test_engine_is_origin_agnostic_over_dataclasses():
    before = _FakeRecord(fields={"a": _FakeField("A", 1), "b": _FakeField("B", 2)})
    after_ok = _FakeRecord(fields={"a": _FakeField("A2", 1), "b": _FakeField("B", 2)})
    op = ChangeOp.set_field_attr("a", "label")
    assert_change_op_isolated(before, op, after_ok)  # only a.label changed

    after_leak = _FakeRecord(fields={"a": _FakeField("A2", 1), "b": _FakeField("B", 99)})
    with pytest.raises(AssertionError) as exc:
        assert_change_op_isolated(before, op, after_leak)
    assert "fields.b.order" in str(exc.value)


# ── The diff primitive directly ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_diff_reports_add_remove_with_missing_sentinel():
    before = {"x": 1, "y": 2}
    after = {"x": 1, "z": 3}
    diffs = {d.path: (d.before, d.after) for d in diff_resolved(before, after)}
    assert diffs["y"] == (2, MISSING)
    assert diffs["z"] == (MISSING, 3)
    assert "x" not in diffs  # unchanged leaf not reported


# ── The reusable round-trip harness (C5/R9.4) ─────────────────────────────────────────


class _FakeReader:
    def __init__(self, store: dict):
        self._store = store

    def read_resolved(self, record_id: str) -> dict:
        import copy

        return copy.deepcopy(self._store[record_id])


class _IsolatedWriter:
    """A writer that correctly touches ONLY the op's target."""

    def __init__(self, store: dict):
        self._store = store

    def apply(self, record_id: str, op: ChangeOp) -> None:
        self._store[record_id]["fields"][op.target]["order"] += 1


class _LeakyWriter:
    """A writer that ALSO corrupts an unrelated group (simulates the bug)."""

    def __init__(self, store: dict):
        self._store = store

    def apply(self, record_id: str, op: ChangeOp) -> None:
        self._store[record_id]["fields"][op.target]["order"] += 1
        self._store[record_id]["functional_groups"].pop("motor", None)  # truncation leak


@pytest.mark.unit
def test_round_trip_harness_passes_for_isolated_writer():
    store = {"config#fields": _resolved_record()}
    op = ChangeOp.set_field_attr("gender", "order")
    run_change_op_isolation(_FakeReader(store), _IsolatedWriter(store), "config#fields", op)


@pytest.mark.unit
def test_round_trip_harness_fails_for_leaky_writer():
    store = {"config#fields": _resolved_record()}
    op = ChangeOp.set_field_attr("gender", "order")
    with pytest.raises(AssertionError) as exc:
        run_change_op_isolation(_FakeReader(store), _LeakyWriter(store), "config#fields", op)
    assert "functional_groups.motor" in str(exc.value)
