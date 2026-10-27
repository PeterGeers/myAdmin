"""
E2E invariant ENGINE — the truncation/leak detector (Phase 1 task 1.2, design C5, R9.2/R9.4).

This module is the heart of the "foolproof CRUD" proof. A Change-Op must change ONLY the field /
group / attribute it names; every other byte of the resolved record must be identical before and
after. The engine below turns that sentence into an assertion:

    assert_change_op_isolated(before_resolved, op, after_resolved)

- ``before_resolved`` / ``after_resolved`` are the FULL Resolved_Record (base ⊕ overlay) read
  before and after the write — NOT the raw stored overlay (steering 39: the raw shape never
  crosses the boundary; the invariant is proven on the resolved view the consumer actually sees).
- ``op`` is a :class:`ChangeOp` descriptor that NAMES the target identity the write is ALLOWED to
  touch (a field attribute, a whole field, a group attribute, a whole group). Anything the op does
  NOT name that differs between before/after is a LEAK — the exact class of bug that truncated the
  ``functional_groups`` catalog 6→2 and stripped field attributes on PROD
  (``.kiro/specs/Members/root-cause-analysis.md``).

Why GENERIC (R9.4 / design C5): the engine diffs an origin-agnostic tree (dataclasses, mappings,
sequences, scalars), so the SAME ``assert_change_op_isolated`` proves isolation for ``config#fields``
today and for ``config#scope`` / ``config#mail`` / member CRUD later — only the ``ChangeOp``
descriptors change, never the engine. The harness that drives a real reader+writer round-trip
(``run_change_op_isolation``) takes a ``(reader, writer, record_id, op)`` tuple so the same proof
scaffolds any SAM-plane record.

This file is pure (no boto3, no AWS, no container): it is importable and self-testable without the
local-DynamoDB fixture (task 1.1), so the engine's own correctness is a fast unit test while the
container-backed round-trip cases (tasks 1.3/1.4) layer on top.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, Self

# ── The op descriptor: what the write is ALLOWED to change ────────────────────────────


@dataclass(frozen=True)
class ChangeOp:
    """Descriptor naming the ONE target identity a Change-Op is allowed to touch.

    The engine is generic over op kinds; an op names its allowed-to-change target(s) as a set of
    DOTTED PATHS into the resolved record (identity-level, not physical storage). Any difference
    between before/after at a path NOT covered by ``allowed_paths`` is a leak.

    ``kind`` / ``target`` are descriptive (they appear in failure messages and let a harness pick
    the right reader/writer call); ``allowed_paths`` is what the engine actually enforces. A path
    is a ``.``-joined sequence of keys/indices addressing a node in the resolved tree, e.g.::

        "fields.gender.label"          # one attribute of one field may change
        "fields.motor_brand"           # a whole field may appear/disappear (add/delete)
        "functional_groups.motor.order"  # one attribute of one group

    A path with a trailing ``.*`` (or an exact prefix match) allows the whole subtree under it to
    change — used for add/delete where the entire entry legitimately appears or vanishes.
    """

    kind: str
    """Op kind, e.g. ``set_field_attr`` / ``add_field`` / ``delete_field`` / ``set_group`` — used
    only for human-readable messages and harness dispatch, NOT for enforcement."""

    target: str
    """The named identity the op addresses (a field key, a group key, a dotted attr) — for
    messages/traceability."""

    allowed_paths: frozenset[str] = field(default_factory=frozenset)
    """The set of dotted resolved-record paths this op is permitted to change. A path matches a
    changed node when it equals the node's path OR is a prefix of it (so naming a whole entry
    allows every attribute under it to change)."""

    def __post_init__(self) -> None:
        # Normalise to a frozenset of plain strings (accept any iterable at construction).
        object.__setattr__(self, "allowed_paths", frozenset(self.allowed_paths))

    # ── convenience constructors for the common config#fields op kinds ────────────────

    @classmethod
    def set_field_attr(cls, field_key: str, *attrs: str) -> ChangeOp:
        """A write that may change ONLY the named attribute(s) of ONE field."""
        return cls(
            kind="set_field_attr",
            target=field_key,
            allowed_paths=frozenset(f"fields.{field_key}.{a}" for a in attrs),
        )

    @classmethod
    def set_field_application(cls, field_key: str, *attrs: str) -> ChangeOp:
        """A form-builder write that may change ONLY the named application attribute(s)."""
        return cls(
            kind="set_field_application",
            target=field_key,
            allowed_paths=frozenset(f"fields.{field_key}.{a}" for a in attrs),
        )

    @classmethod
    def add_field(cls, field_key: str) -> ChangeOp:
        """A write that may introduce ONE whole new field (the whole entry subtree)."""
        return cls(
            kind="add_field",
            target=field_key,
            allowed_paths=frozenset({f"fields.{field_key}"}),
        )

    @classmethod
    def delete_field(cls, field_key: str) -> ChangeOp:
        """A write that may remove ONE whole field (the whole entry subtree)."""
        return cls(
            kind="delete_field",
            target=field_key,
            allowed_paths=frozenset({f"fields.{field_key}"}),
        )

    @classmethod
    def set_group(cls, group_key: str, *attrs: str) -> ChangeOp:
        """A write that may change ONLY the named attribute(s) of ONE functional group."""
        return cls(
            kind="set_group",
            target=group_key,
            allowed_paths=frozenset(f"functional_groups.{group_key}.{a}" for a in attrs),
        )

    @classmethod
    def delete_group(cls, group_key: str) -> ChangeOp:
        """A write that may remove ONE whole functional group (the whole entry subtree)."""
        return cls(
            kind="delete_group",
            target=group_key,
            allowed_paths=frozenset({f"functional_groups.{group_key}"}),
        )


# ── The leak the engine reports ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Diff:
    """One change between the before/after resolved records at a dotted ``path``.

    ``before`` / ``after`` carry a sentinel (:data:`MISSING`) when the node only exists on one
    side (an added or removed node), so an add/delete is representable without ambiguity with a
    legitimate ``None`` value.
    """

    path: str
    before: Any
    after: Any

    def _render(self, value: Any) -> str:
        return "<absent>" if value is MISSING else repr(value)

    def __str__(self) -> str:
        return f"{self.path}: {self._render(self.before)} -> {self._render(self.after)}"


class _Missing:
    """Sentinel for a node present on only one side of the diff (add / delete)."""

    _instance: _Missing | None = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "MISSING"


MISSING = _Missing()


# ── The generic deep diff ─────────────────────────────────────────────────────────────


def _canonical(node: Any) -> Any:
    """Normalise a resolved node into comparable, diff-friendly primitives.

    - a dataclass → an ordered dict of its fields (so ``ResolvedField`` / ``FunctionalGroup`` and
      a plain dict compare the same way — the engine is origin-agnostic, R9.4);
    - a Mapping → a plain dict;
    - a non-string Sequence (list/tuple) → a list;
    - everything else (str, int, bool, None, Enum, …) is returned as-is.

    Strings are treated as scalars, never as sequences of characters.
    """
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        return {f.name: getattr(node, f.name) for f in dataclasses.fields(node)}
    if isinstance(node, Mapping):
        return dict(node)
    if isinstance(node, (str, bytes)):
        return node
    if isinstance(node, Sequence):
        return list(node)
    return node


def _child_items(node: Any) -> list[tuple[str, Any]] | None:
    """Return ``(key, child)`` pairs for a container node, or ``None`` for a scalar leaf.

    A mapping keys by its string keys; a sequence keys by its index. A dataclass is canonicalised
    to a mapping first. Scalars (including strings and enums) have no children.
    """
    canon = _canonical(node)
    if isinstance(canon, dict):
        return [(str(k), v) for k, v in canon.items()]
    if isinstance(canon, list):
        return [(str(i), v) for i, v in enumerate(canon)]
    return None


def diff_resolved(before: Any, after: Any, _prefix: str = "") -> list[Diff]:
    """Deep-diff two resolved records, returning every differing leaf/node as a :class:`Diff`.

    Walks both trees in lockstep. When one side has a child key the other lacks, that is an
    add/remove recorded with a :data:`MISSING` sentinel at the child's path. When both sides are
    scalars (or containers of a different kind), they are compared by value. The result is a flat
    list of dotted-path differences — the raw material :func:`assert_change_op_isolated` filters
    against the op's ``allowed_paths``.
    """
    before_items = _child_items(before)
    after_items = _child_items(after)

    # Both scalars (or incomparable container-vs-scalar) → compare by canonical value.
    if before_items is None or after_items is None:
        if _canonical(before) != _canonical(after) or (before_items is None) != (
            after_items is None
        ):
            return [Diff(_prefix or "<root>", before, after)]
        # One is a scalar, the other a container of the same canonical value is impossible here;
        # fall through only when both are scalars and equal.
        if before_items is None and after_items is None:
            return []

    diffs: list[Diff] = []
    before_map = dict(before_items or [])
    after_map = dict(after_items or [])
    for key in list(before_map.keys()) + [k for k in after_map if k not in before_map]:
        path = f"{_prefix}.{key}" if _prefix else key
        if key not in after_map:
            diffs.append(Diff(path, before_map[key], MISSING))
        elif key not in before_map:
            diffs.append(Diff(path, MISSING, after_map[key]))
        else:
            diffs.extend(diff_resolved(before_map[key], after_map[key], path))
    return diffs


# ── Path matching + the assertion ─────────────────────────────────────────────────────


def _path_allowed(changed_path: str, allowed_paths: frozenset[str]) -> bool:
    """Is a changed dotted path covered by one of the op's allowed paths?

    A changed path is allowed when it EQUALS an allowed path or is a descendant of one (naming a
    whole entry ``fields.motor_brand`` permits every ``fields.motor_brand.<attr>`` under it). A
    trailing ``.*`` on an allowed path is accepted as an explicit subtree wildcard.
    """
    for allowed in allowed_paths:
        base = allowed.removesuffix(".*")
        if changed_path == base or changed_path.startswith(base + "."):
            return True
    return False


def assert_change_op_isolated(
    before_resolved: Any, op: ChangeOp, after_resolved: Any
) -> None:
    """Assert a Change-Op changed ONLY what it named; everything else is byte-identical (R9.2).

    Diffs the FULL resolved record before/after and fails if ANY differing path is outside the
    op's :attr:`ChangeOp.allowed_paths`. The failure message lists each UNEXPECTED path with its
    before→after values — this is the truncation/leak detector: a group that vanished from
    ``functional_groups`` or a field attribute that was stripped shows up here as an unexpected
    diff naming the exact lost path.

    Does NOT require the op's target to actually change (a no-op write is isolated too). It fails
    ONLY on a change the op did not name — the single thing the "foolproof" guarantee forbids.
    """
    all_diffs = diff_resolved(before_resolved, after_resolved)
    leaks = [d for d in all_diffs if not _path_allowed(d.path, op.allowed_paths)]
    if leaks:
        allowed = ", ".join(sorted(op.allowed_paths)) or "<nothing>"
        detail = "\n".join(f"    - {d}" for d in leaks)
        raise AssertionError(
            f"Change-Op {op.kind!r} on target {op.target!r} LEAKED: it changed "
            f"{len(leaks)} path(s) it did not name.\n"
            f"  Allowed to change: {allowed}\n"
            f"  Unexpectedly changed:\n{detail}\n"
            f"  (This is the truncation/field-strip detector — the write touched data it was "
            f"not supposed to. See .kiro/specs/Members/root-cause-analysis.md.)"
        )


# ── Reusable round-trip harness over a (reader, writer, record_id, op) tuple (C5/R9.4) ─


class _Reader(Protocol):
    """Reads the FULL resolved record for a record id (the Resolved_Record, steering 39)."""

    def read_resolved(self, record_id: str) -> Any:  # pragma: no cover - protocol
        ...


class _Writer(Protocol):
    """Applies a :class:`ChangeOp` to a record (the Change-Op write path)."""

    def apply(self, record_id: str, op: ChangeOp) -> None:  # pragma: no cover - protocol
        ...


def run_change_op_isolation(reader: _Reader, writer: _Writer, record_id: str, op: ChangeOp) -> None:
    """Drive a real read → apply(op) → read round-trip and assert isolation (design C5, R9.4).

    This is the GENERIC harness entry point: hand it any reader/writer pair for any SAM-plane
    record (``config#fields`` now; ``config#scope`` / ``config#mail`` / member CRUD later) plus
    the op descriptor, and it proves the write changed only what the op named. Keeping the drive
    loop here (not in each test) is what makes the invariant reusable with minimal new code.
    """
    before = reader.read_resolved(record_id)
    writer.apply(record_id, op)
    after = reader.read_resolved(record_id)
    assert_change_op_isolated(before, op, after)
