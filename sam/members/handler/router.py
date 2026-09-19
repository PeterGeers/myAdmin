"""
S5 Task 1.0 — the Members module **internal router** (method/path → RouteSpec).

The single Members Lambda routes internally: one deployable, many routes (R1.1, design C1).
This module turns an incoming ``(method, path)`` into the matching :class:`RouteSpec` from
the route map (``routes.py``) plus the extracted path parameters, or an explicit,
distinguishable no-match outcome:

- **not found** — no route pattern matches the path at all → the edge answers ``404``.
- **method not allowed** — the path matches one or more routes but not for this method →
  the edge answers ``405`` and can advertise the allowed methods.

Keeping *not-found* and *method-not-allowed* distinct (rather than collapsing both to 404)
lets the thin handler return correct HTTP semantics without embedding routing knowledge.

Layering: this is **handler-layer** code. It performs pure, in-memory pattern matching —
no auth, no business logic, no DynamoDB. Path patterns use ``{param}`` placeholders
(e.g. ``/members/{member_id}/memberships/{membership_id}``); a segment placeholder matches
exactly one non-empty, non-slash path segment and is returned as a named parameter.

The compiled matchers are built **once at import** (module/global scope) so warm Lambda
invocations reuse them and never recompile per request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional, Pattern

from sam.members.handler.routes import ROUTES, RouteSpec

__all__ = [
    "RouteMatch",
    "MethodNotAllowed",
    "NoRouteMatch",
    "Router",
    "get_router",
]


# ── Match results ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RouteMatch:
    """A successful match: the resolved route and the extracted path parameters."""

    spec: RouteSpec
    path_params: Mapping[str, str]


@dataclass(frozen=True)
class MethodNotAllowed:
    """The path matched a known resource, but not for the requested method (→ 405).

    ``allowed_methods`` lists the methods that WOULD match this path, sorted, so the edge
    can populate an ``Allow`` header.
    """

    allowed_methods: tuple[str, ...]


class NoRouteMatch(Exception):
    """Raised when no route pattern matches the path at all (→ 404)."""

    def __init__(self, method: str, path: str):
        self.method = method
        self.path = path
        super().__init__(f"no route matches {method} {path}")


# ── Pattern compilation ───────────────────────────────────────────────────────────────

# A `{name}` placeholder in a path pattern. Names are valid Python identifiers so they map
# cleanly to keyword-ish path params.
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _compile_path_pattern(path: str) -> Pattern[str]:
    """Compile a route path pattern into an anchored regex.

    Each ``{param}`` becomes a named group matching exactly one path segment (one or more
    characters, no ``/``). Literal segments are escaped. The result is fully anchored so a
    pattern matches the whole path, never a prefix.
    """
    pos = 0
    parts: list[str] = []
    for match in _PLACEHOLDER_RE.finditer(path):
        parts.append(re.escape(path[pos:match.start()]))
        name = match.group(1)
        parts.append(rf"(?P<{name}>[^/]+)")
        pos = match.end()
    parts.append(re.escape(path[pos:]))
    return re.compile("^" + "".join(parts) + "$")


@dataclass(frozen=True)
class _CompiledRoute:
    """A route spec paired with its compiled, anchored path matcher."""

    spec: RouteSpec
    pattern: Pattern[str]


# ── Router ────────────────────────────────────────────────────────────────────────────


class Router:
    """Resolves ``(method, path)`` to a :class:`RouteMatch` over a fixed route map.

    Built once from the module route map and reused for every request. Matching is:

    1. Try each compiled route whose method equals the request method; the first whose
       pattern matches the path wins (declaration order — the route map forbids duplicate
       ``(method, path)`` pairs, so at most one can match anyway).
    2. If none match for this method but the path matches some route of *another* method,
       return :class:`MethodNotAllowed` with the allowed methods (→ 405).
    3. Otherwise raise :class:`NoRouteMatch` (→ 404).
    """

    def __init__(self, specs: tuple[RouteSpec, ...] = ROUTES):
        self._compiled: tuple[_CompiledRoute, ...] = tuple(
            _CompiledRoute(spec=spec, pattern=_compile_path_pattern(spec.path))
            for spec in specs
        )

    def resolve(self, method: str, path: str):
        """Resolve a request to a :class:`RouteMatch` or a :class:`MethodNotAllowed`.

        Args:
            method: The HTTP method (case-insensitive).
            path: The request path (no query string), e.g. ``/members/42/payments``.

        Returns:
            A :class:`RouteMatch` on success, or :class:`MethodNotAllowed` when the path is
            known but the method is not.

        Raises:
            NoRouteMatch: When no route pattern matches the path for any method (→ 404).
        """
        method_upper = (method or "").upper()
        normalized = self._normalize_path(path)

        allowed: list[str] = []
        for compiled in self._compiled:
            match = compiled.pattern.match(normalized)
            if match is None:
                continue
            # The path matches this route's pattern; does the method line up?
            if compiled.spec.method.value == method_upper:
                return RouteMatch(spec=compiled.spec, path_params=dict(match.groupdict()))
            allowed.append(compiled.spec.method.value)

        if allowed:
            # Path is a known resource, wrong method → 405 with the methods that fit.
            return MethodNotAllowed(allowed_methods=tuple(sorted(set(allowed))))

        raise NoRouteMatch(method_upper, normalized)

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize a request path for matching.

        Strips any trailing slash (except the root ``/``) so ``/members`` and ``/members/``
        resolve to the same route. Empty/None becomes the root path.
        """
        if not path:
            return "/"
        if len(path) > 1 and path.endswith("/"):
            return path.rstrip("/")
        return path


# ── Warm-reuse singleton ──────────────────────────────────────────────────────────────

_ROUTER: Optional[Router] = None


def get_router() -> Router:
    """Return the module-global :class:`Router`, building it once at cold start."""
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = Router()
    return _ROUTER
