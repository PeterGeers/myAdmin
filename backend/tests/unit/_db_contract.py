"""Shared helpers for the DatabaseManager cursor/connection contract in unit tests.

`backend/src/database.py` was refactored so the context-managed cursor/transaction
APIs now yield a 2-tuple ``(cursor, conn)`` and consumers unpack it:

    with db.get_cursor() as (cursor, conn):
        ...
    with db.transaction() as (cursor, conn):
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


def wire_cursor_contract(db, cursor, conn):
    """Wire ``db.get_cursor()`` and ``db.transaction()`` to yield ``(cursor, conn)``.

    Works for both ``Mock``/``MagicMock`` db doubles. Each call returns a fresh CM so a
    test that enters the context manager more than once still gets the tuple.
    """
    db.get_cursor = MagicMock(side_effect=lambda *a, **k: make_cursor_cm(cursor, conn))
    db.transaction = MagicMock(side_effect=lambda *a, **k: make_cursor_cm(cursor, conn))
    return db
