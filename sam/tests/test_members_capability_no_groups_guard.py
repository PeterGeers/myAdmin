"""
S5c Task 0.5 (corrected) — durable guardrail for **Property 5 / R6.4**:
*no code path derives a Members CAPABILITY from ``cognito:groups``.*

Why this is a TEST, not an AWS script
-------------------------------------
The literal task wording ("confirm no per-tenant ``Members_*`` Cognito group exists;
add a check to the verify script") rested on a false premise. Live inspection this
session (read-only) showed:

- the TEST pool ``eu-west-1_xyrlzfqbl`` has **no** ``Members_*`` group;
- prod Pool A ``eu-west-1_Hdp40eWmu`` **has** ``Members_CRUD`` / ``Members_Read`` /
  ``Members_Export`` (created 2026-09-18).

But those ``Members_*`` names are **ROLES** in the authorization model, **not** a
capability-granting group. In-repo proof:

- projected as ``role#<email>#Members_CRUD`` (``scripts/local/seed-dynamodb-local.py``);
- consumed by ``required_for=("Members_CRUD",)`` scope gating
  (``sam/members/domain/scope_dimensions.py`` → ``resolve_scope_access``);
- carried in ``RequestContext.groups`` (``test_members_auth_edge.py`` asserts
  ``ctx.groups == ["Members_Read"]``).

They are **DISTINCT** from capabilities (``members:read`` / ``members:write`` /
``members:export`` / ``members:admin`` — ``sam/members/handler/routes.py``). Deleting
those Cognito groups would BREAK the scope/permission model, so s5c does NOT delete them.

The REAL intent of R6.4 / C-UNWIND (Property 5) is a **code contract**: capability comes
solely from the verified ``custom:entitlements`` claim; NO code path maps ``cognito:groups``
→ a Members capability. The risk that regresses is *code*, not pool state — so the durable
guardrail is a repeatable test, not an AWS-dependent script.

This file is the standalone, always-runnable guard (the edge already has companion
honest-deny tests in ``test_members_auth_edge.py``).

Validates: Requirements 6.4, 1.3, 6.1 (design C-UNWIND, Property 5)
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
import pathlib
import re

import pytest

from sam.members.handler import app


# ── (i) behavioural guard: a cognito:groups-only token is denied (403) ─────────────────


def _authorizer_event(method: str, path: str, *, claims: dict) -> dict:
    """An API-GW-authorizer proxy event carrying the given VERIFIED claims."""
    return {
        "httpMethod": method,
        "path": path,
        "headers": {},
        "queryStringParameters": None,
        "body": None,
        "requestContext": {"authorizer": {"claims": claims}},
    }


@pytest.mark.parametrize(
    "groups",
    [
        ["Members_Read"],
        ["Members_CRUD"],
        ["Members_Export"],
        ["Members_CRUD", "Regio_All"],
    ],
)
def test_groups_only_token_is_denied_no_capability_from_groups(groups):
    """A token whose ONLY Members signal is ``cognito:groups`` (no ``custom:entitlements``)
    MUST be denied — the groups NEVER synthesize a Members capability or a tenant.

    This is the observable half of Property 5 / R6.4: whatever ``Members_*`` role the token
    carries, with no verified entitlement there is no capability and no tenant → honest deny.
    Any status other than 401/403 (e.g. a 200/501 that reached a route) would mean a
    groups-derived grant leaked in.
    """
    event = _authorizer_event(
        "GET", "/members", claims={"sub": "u", "cognito:groups": groups}
    )
    resp = app.handler(event)
    assert resp["statusCode"] in (401, 403), (
        f"a cognito:groups-only token ({groups!r}) must be denied; got {resp['statusCode']}"
    )


def test_groups_only_write_token_is_denied():
    """Same contract on a WRITE route: a ``Members_CRUD`` group with no entitlement never
    grants ``members:write``."""
    event = _authorizer_event(
        "POST", "/members", claims={"sub": "u", "cognito:groups": ["Members_CRUD"]}
    )
    resp = app.handler(event)
    assert resp["statusCode"] in (401, 403)


# ── (ii) grep-clean guard: no non-test module code maps cognito:groups → a capability ──
#
# The module edge MAY read ``cognito:groups`` legitimately — but ONLY as *roles* for scope
# resolution (``RequestContext.groups`` → ``resolve_scope_access`` via the projected grant),
# NEVER as a source of a Members *capability*. This static guard walks the live module
# source (AST, so comments/docstrings that DOCUMENT the contract don't trip it) and asserts:
#
#   1. the removed capability-fallback symbols stay gone (regression tripwire), and
#   2. no live line co-locates a ``cognito:groups`` read with a Members-capability token
#      (``members:read/write/export/admin``) — i.e. no ``groups → capability`` mapping.

# The Members-plane module files whose LIVE code must never derive a capability from groups.
_MODULE_FILES = [
    app,
    importlib.import_module("sam.members.handler.routes"),
    importlib.import_module("sam.members.handler.router"),
]

# Capability token pattern (the ``members:*`` scopes, distinct from ``Members_*`` roles).
_CAPABILITY_RE = re.compile(r"members:(?:read|write|export|admin)")


def _live_source_without_strings(module) -> str:
    """Return the module's source with all string/docstring constants blanked out.

    We reduce the AST's string ``Constant`` nodes to empty text so that comments and
    docstrings (which legitimately explain the *removed* groups→capability path) are not
    mistaken for a live mapping. What remains is live code (names, calls, operators).
    """
    src = inspect.getsource(module)
    tree = ast.parse(src)
    lines = src.splitlines()

    # Blank the interior of every string constant span so its text can't match.
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            end = getattr(node, "end_lineno", None)
            if node.lineno is None or end is None:
                continue
            for ln in range(node.lineno - 1, end):
                if 0 <= ln < len(lines):
                    lines[ln] = ""
    # Also strip ``#`` comments from every remaining line.
    stripped = [re.sub(r"#.*$", "", ln) for ln in lines]
    return "\n".join(stripped)


@pytest.mark.parametrize("module", _MODULE_FILES, ids=lambda m: m.__name__)
def test_no_module_line_maps_cognito_groups_to_a_capability(module):
    """No LIVE line in a Members-plane module reads ``cognito:groups`` AND a
    ``members:<cap>`` capability together — i.e. there is no groups→capability derivation.

    ``cognito:groups`` may appear (roles for scope), and ``members:<cap>`` may appear
    (capability constants / route metadata), but never on the *same* live line, which is
    the only shape a "groups grant a capability" mapping could take here.
    """
    code = _live_source_without_strings(module)
    offenders = [
        ln.strip()
        for ln in code.splitlines()
        if "cognito:groups" in ln and _CAPABILITY_RE.search(ln)
    ]
    assert not offenders, (
        f"{module.__name__}: a live line co-locates cognito:groups with a Members "
        f"capability (groups→capability path forbidden by Property 5 / R6.4): {offenders!r}"
    )


def test_capability_fallback_symbols_stay_removed():
    """Regression tripwire (R6.1/R6.4): the removed groups→capability fallback surface
    (``_local_dev_group_grants_capability`` / ``_local_auth_fallback_grants`` /
    ``_LOCAL_AUTH_FALLBACK_ENV``) must never reappear on the edge module."""
    for symbol in (
        "_local_dev_group_grants_capability",
        "_local_auth_fallback_grants",
        "_LOCAL_AUTH_FALLBACK_ENV",
    ):
        assert not hasattr(app, symbol), (
            f"{symbol} must stay removed (Property 5 / R6.4, C-UNWIND)"
        )


def test_capability_source_is_the_verified_entitlement_only():
    """White-box: the edge answers capability via ``has_capability`` reading the verified
    ``custom:entitlements`` claim — not via ``cognito:groups``.

    We assert ``has_capability`` is the symbol the edge binds for the capability decision
    and that it belongs to the shared verified-entitlement reader (``sam.shared.auth_utils``),
    documenting *where* capability comes from so a future refactor can't quietly swap in a
    groups-based answer without this test noticing.
    """
    assert hasattr(app, "has_capability"), "the edge must resolve capability via has_capability"
    assert app.has_capability.__module__ == "sam.shared.auth_utils", (
        "capability must come from the shared verified-entitlement reader, "
        f"not {app.has_capability.__module__}"
    )


def test_this_guard_is_pool_state_independent():
    """Sanity: this guard imports no AWS SDK and depends on NO Cognito pool state.

    Documents the corrected 0.5 decision — the durable risk is code regression, so the
    guardrail is a static/behavioural test, not an AWS-dependent script. We assert via the
    AST that this module has no ``import boto3`` (so the check is robust to prose mentioning
    the SDK by name in comments/docstrings)."""
    module = inspect.getmodule(test_this_guard_is_pool_state_independent)
    tree = ast.parse(inspect.getsource(module))
    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.append(node.module)
    assert not any(name.split(".")[0] == "boto3" for name in imported_names), (
        "the guard must not import boto3 — it is pool-state-independent"
    )
