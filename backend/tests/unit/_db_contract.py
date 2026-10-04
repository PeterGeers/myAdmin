"""Shared helpers for the DatabaseManager cursor/connection contract in unit tests.

`backend/src/database.py` was refactored so the context-managed cursor/transaction
APIs now yield a 2-tuple ``(cursor, conn)`` and consumers unpack it:

    with db.get_cursor() as (cursor, conn):
        ...
    with db.transaction() as (cursor, conn):
        ...

Read paths that never touch the connection use the single-value accessor
``get_cursor_only()``, which yields *only* the cursor::

    with db.get_cursor_only() as cursor:
        ...

The raw private accessor is ``_get_connection`` (formerly ``get_connection``).

These helpers build mocks that honour that contract so individual tests don't have
to re-implement the context-manager plumbing. See spec task H1
(full-test-suite-fixes-2026-10-03).
"""

from unittest.mock import MagicMock


def make_cursor_cm(cursor, conn):
    """Return a MagicMock usable as a ``with ... as (cursor, conn):`` context manager.

    ``__enter__`` yields the ``(cursor, conn)`` 2-tuple; ``__exit__`` returns False so
    exceptions raised inside the ``with`` block propagate (matching the real
    ``get_cursor``/``transaction`` behaviour, which re-raises after rollback).
    """
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=(cursor, conn))
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def make_cursor_only_cm(cursor):
    """Return a MagicMock usable as a ``with db.get_cursor_only() as cursor:`` CM.

    ``__enter__`` yields *only* the cursor (not a 2-tuple), matching the real
    ``get_cursor_only`` read-path accessor; ``__exit__`` returns False so exceptions
    propagate.
    """
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cursor)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def wire_cursor_contract(db, cursor, conn):
    """Wire the full cursor/connection contract onto a db double.

    Wires ``db.get_cursor()`` and ``db.transaction()`` to yield ``(cursor, conn)``, and
    ``db.get_cursor_only()`` to yield just ``cursor`` (the read-path accessor). Without
    the ``get_cursor_only`` wiring, read paths migrated to that accessor would receive a
    bare auto-generated ``MagicMock`` cursor whose ``fetchall()``/``fetchone()`` return
    mocks instead of the test-controlled ``cursor`` (see spec task H1
    full-test-suite-fixes-2026-10-04, requirements Lesson 1).

    Works for both ``Mock``/``MagicMock`` db doubles. Each call returns a fresh CM so a
    test that enters the context manager more than once still gets the right shape.
    """
    db.get_cursor = MagicMock(side_effect=lambda *a, **k: make_cursor_cm(cursor, conn))
    db.transaction = MagicMock(side_effect=lambda *a, **k: make_cursor_cm(cursor, conn))
    db.get_cursor_only = MagicMock(
        side_effect=lambda *a, **k: make_cursor_only_cm(cursor)
    )
    return db


# ---------------------------------------------------------------------------
# Safe-by-default cursor factory (spec task L2, full-test-suite-fixes-2026-10-04)
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS
# ---------------
# The preservation/closure/banking cluster has now broken twice off the SAME
# under-specified cursor mock:
#   * 10-03: ``ValueError: not enough values to unpack`` — the mock yielded a bare
#     cursor instead of the ``(cursor, conn)`` 2-tuple. Fixed by H1
#     (``wire_cursor_contract`` wiring the context managers).
#   * 10-04: ``MagicMock`` leaks into comparisons / "0 saved" / "every row reads as a
#     duplicate" — the ``cursor`` object H1 wires is still whatever the test created,
#     and a bare ``MagicMock()`` cursor returns a NEW ``MagicMock`` from ``fetchall()``
#     and ``fetchone()``. Code that does ``for row in cursor.fetchall():`` or
#     ``if cursor.fetchone():`` then operates on a mock, not concrete data.
#
# A fixture that hands back a bare ``MagicMock`` cursor keeps producing a fresh failure
# signature every refactor. The durable prevention is a factory whose ``fetchall()``
# defaults to a concrete empty ``list`` and ``fetchone()`` defaults to concrete ``None``
# — never a bare mock — with an explicit opt-in for seeded rows.
#
# This is ADDITIVE. It does not change ``make_cursor_cm`` / ``make_cursor_only_cm`` /
# ``wire_cursor_contract`` or any existing call site. Tests may migrate to it, but the
# six H1 files keep working unchanged.

#: Sentinel distinguishing "caller did not seed this return" from an explicit ``None``
#: / ``[]``. Lets ``make_cursor`` apply concrete defaults while still letting a test
#: pass ``fetchone=None`` deliberately (which is identical to the default here, but the
#: sentinel keeps the guard-helper below honest).
_UNSET = object()


def make_cursor(fetchall=_UNSET, fetchone=_UNSET):
    """Build a cursor mock whose ``fetchall()``/``fetchone()`` have CONCRETE defaults.

    This is the safe-by-default replacement for a bare ``MagicMock()`` cursor. Unless a
    test explicitly seeds rows, the cursor behaves like an empty result set rather than
    leaking a ``MagicMock`` into the code under test::

        cursor = make_cursor()                       # fetchall() -> [], fetchone() -> None
        cursor = make_cursor(fetchall=[{"ID": 1}])   # seeded read rows
        cursor = make_cursor(fetchone={"ID": 777})   # seeded single-row lookup

    Args:
        fetchall: concrete rows ``fetchall()`` should return. Defaults to a fresh empty
            ``list`` (``[]``) — NOT a bare mock.
        fetchone: concrete row ``fetchone()`` should return. Defaults to ``None`` — NOT
            a bare mock.

    Returns:
        A ``MagicMock`` cursor with ``fetchall``/``fetchone`` return values pinned to
        concrete objects. ``execute``/``executemany``/``lastrowid`` etc. remain ordinary
        auto-mocks so call-count/argument assertions still work.
    """
    cursor = MagicMock(name="cursor")
    cursor.fetchall.return_value = [] if fetchall is _UNSET else fetchall
    cursor.fetchone.return_value = None if fetchone is _UNSET else fetchone
    return cursor


def make_db_double(db=None, conn=None, fetchall=_UNSET, fetchone=_UNSET):
    """Build ``(db, cursor, conn)`` wired to the full cursor/connection contract.

    One-call setup for the common DatabaseManager-double shape: it builds a
    safe-by-default cursor via :func:`make_cursor`, wires ``get_cursor()`` /
    ``transaction()`` / ``get_cursor_only()`` via :func:`wire_cursor_contract`, and
    returns the trio so the test can seed further and assert::

        db, cursor, conn = make_db_double()                 # empty-result-set double
        db, cursor, conn = make_db_double(fetchone={"ID": 1})  # seed the duplicate gate
        cursor.fetchall.return_value = [{"ID": 2}]           # or seed after the fact

    Args:
        db: an existing db double to wire (e.g. a ``MagicMock`` already carrying
            ``execute_query`` / ``insert_transaction`` side effects). A fresh
            ``MagicMock`` is created when omitted.
        conn: the connection object the context managers should yield alongside the
            cursor. A fresh ``MagicMock`` is created when omitted.
        fetchall / fetchone: forwarded to :func:`make_cursor` for concrete defaults.

    Returns:
        ``(db, cursor, conn)``. The cursor's ``fetchall()``/``fetchone()`` return
        concrete values (``[]`` / ``None``) unless seeded, so a test that forgets to
        seed rows reads an empty result set instead of silently comparing against a
        mock.
    """
    if db is None:
        db = MagicMock(name="db")
    if conn is None:
        conn = MagicMock(name="conn")
    cursor = make_cursor(fetchall=fetchall, fetchone=fetchone)
    wire_cursor_contract(db, cursor, conn)
    return db, cursor, conn
