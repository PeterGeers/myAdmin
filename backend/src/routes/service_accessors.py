"""Shared lazy-service-accessor factory for route blueprints.

Many route modules expose a module-level ``_get_service()`` that constructs a
fresh ``DatabaseManager`` and builds a service (optionally wiring a couple of
collaborator services off the same ``DatabaseManager``) on every call. This is a
lazy *constructor* — no module-level caching — created on first/each call and
not memoized. That exact pattern was copy-pasted across ~8 modules.

``make_db_service_accessor`` captures the identical skeleton once:

    db = DatabaseManager()
    return <service built from db>

Adopt it by assigning the returned closure to the module-level ``_get_service``
name, e.g.::

    from routes.service_accessors import make_db_service_accessor
    from services.asset_service import AssetService

    _get_service = make_db_service_accessor(AssetService)

The ``builder`` receives the freshly created ``DatabaseManager`` and returns the
service instance. For single-dependency services the service class itself is a
valid builder (``AssetService(db)``). For services that need collaborators built
off the same ``db``, pass a small lambda::

    _get_service = make_db_service_accessor(
        lambda db: ContactService(db=db, parameter_service=ParameterService(db))
    )

Why a module-level assignment (not a redefined ``def``) still preserves
patchability: handlers resolve ``_get_service`` through the module namespace at
call time, and tests patch/reassign the module attribute
(``@patch('routes.X._get_service')`` or ``mod._get_service = lambda: fake``).
Replacing the ``def`` with an assigned closure keeps that attribute present,
callable, patchable, and reassignable — identical observable behavior.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from database import DatabaseManager

T = TypeVar("T")


def make_db_service_accessor(
    builder: Callable[[DatabaseManager], T],
) -> Callable[[], T]:
    """Return a zero-arg accessor that builds a service from a fresh DatabaseManager.

    The returned closure creates a new ``DatabaseManager`` on every call and
    hands it to ``builder``, mirroring the per-call (non-cached) lazy
    construction the route modules used before consolidation.

    Args:
        builder: Callable taking the ``DatabaseManager`` and returning the
            service instance. A service class with a single ``db`` positional
            argument works directly; use a lambda to wire collaborators.

    Returns:
        A ``_get_service``-shaped callable with no arguments.
    """

    def _get_service() -> T:
        return builder(DatabaseManager())

    return _get_service
