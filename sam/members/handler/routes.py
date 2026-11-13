"""
S5 Task 1.0 — the Members module **internal route map** (stubs only).

This is the single source of truth for the Members Lambda's internal routes: the
**union of h-dcn's ~18 per-action handler behaviours**, collapsed into one module that
routes internally by ``(method, path)`` (design C1, migration-plan Step 1, R1.1). h-dcn's
Members backend is ~18 one-Lambda-per-action handlers — a learning-curve artefact, not a
design to preserve — so the migration goes straight to the best-practice shape: **one
module, many routes**, the auth/entitlement toolkit adopted **once** at the edge.

Scope of THIS task (1.0): **stubs only.** Each route is declared with its method, path
pattern, a stable ``name``, the behaviour ``group`` it belongs to, and the
``capability``/``self_service`` metadata the handler edge (task 3.0) will gate on. No
route has an implementation yet — the domain service + repository that back them are
populated by the later Step 1 / Step 3 / Step 5 tasks. The router (``router.py``) resolves
an incoming request to one of these specs; the thin handler (``app.py``) then delegates to
the (still-stubbed) domain layer.

Layering (see ``.kiro/steering/35-sam-module-architecture-sam.md``): this module is part of
the **handler layer**. It holds NO business logic and NO DynamoDB access — only the
declarative description of the HTTP surface. Dependencies point downward only.

The route names mirror h-dcn's handler behaviours so parity is auditable at the Go/No-Go:

    Member CRUD ............ create · get-by-id · get-self · list · list-filtered ·
                            update · delete · export                     (8)
    Membership lifecycle ... create · get · list · update · delete         (5)
    Delegates .............. manage delegates · send delegate invitation (2)
    Payments (member) ...... get member payments                        (1)
                                                                    total 16
"""

from __future__ import annotations

__all__ = [
    "ROUTES",
    "HttpMethod",
    "RouteGroup",
    "RouteSpec",
    "route_names",
    "routes_by_group",
]

from ._routes_spec import (  # noqa: F401 (surface compat)
    CAP_MEMBERS_ADMIN,
    CAP_MEMBERS_EXPORT,
    CAP_MEMBERS_READ,
    CAP_MEMBERS_WRITE,
    HttpMethod,
    RouteGroup,
    RouteSpec,
)
from .routes_table import (
    ROUTES,
)


# ── Import-time integrity checks (the route map is a single source of truth) ───────────
#
# A duplicate (method, path) or a duplicate behaviour name would make routing ambiguous,
# so we fail fast at import rather than silently shadow a route.
def _assert_route_map_is_consistent() -> None:
    seen_endpoints: set[tuple[str, str]] = set()
    seen_names: set[str] = set()
    for spec in ROUTES:
        endpoint = (spec.method.value, spec.path)
        if endpoint in seen_endpoints:
            raise ValueError(
                f"duplicate route endpoint: {spec.method.value} {spec.path}"
            )
        seen_endpoints.add(endpoint)
        if spec.name in seen_names:
            raise ValueError(f"duplicate route name: {spec.name}")
        seen_names.add(spec.name)
        # A route must be gated by a capability, an any-of capability set, self-service, or a
        # combination — never nothing.
        if (
            spec.capability is None
            and not spec.capabilities_any
            and not spec.self_service
        ):
            raise ValueError(
                f"route {spec.name} has no gate "
                "(needs a capability, capabilities_any, or self_service)"
            )


_assert_route_map_is_consistent()


def route_names() -> tuple[str, ...]:
    """All route behaviour names in declaration order (parity-audit source of truth)."""
    return tuple(spec.name for spec in ROUTES)


def routes_by_group(group: RouteGroup) -> tuple[RouteSpec, ...]:
    """Return the routes belonging to one behaviour group."""
    return tuple(spec for spec in ROUTES if spec.group is group)
