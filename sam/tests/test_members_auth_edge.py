"""
S5 Task 3.0 — tests for the Members handler **verified-auth + entitlement edge**.

These pin the observable security contract the thin handler enforces once, at the edge,
by adopting the ``sam/shared`` toolkit (R1.1) — parse → authenticate (verified) → tenant
context → authorize (has_capability + scope) → route → respond:

- **Authenticate (verified, Property 2):** no token → 401; a JWKS outage on the fallback
  path → 503; API-GW-authorizer verified claims are accepted without re-verification. A
  client header (``X-Enhanced-Groups`` / ``X-Tenant``) never grants anything.
- **Tenant context (verify-before-trust):** ``tenant_id`` comes from the verified
  entitlement's ``tenant_keys`` — never a client-supplied header/body. No usable tenant
  (fallback / overflow / empty entitlement) → 403 (fail-safe, Property 3), never a guess.
- **Authorize (has_capability three-state):** a token-backed grant → allowed (the READ
  route runs — task 3.2 — resolving to a scope-narrowed result);
  a token-backed denial (``False``) → 403; a "token does not answer" (``None`` — absent /
  malformed claim, or tenant not listed) → 403 (never a silent allow).
- **Scope seam (deny-by-default, Property 4):** the scope decision runs through the
  task-3.1 seam, which denies by default; a granted capability still resolves an
  ``allowed_scopes`` on the context (empty until 3.1 fills the resolver).

Validates: Requirements R1.1, R1.2, R6.1
"""

from __future__ import annotations

import ast
import inspect
import json

import pytest

from sam.members.handler import app
from sam.shared.auth_utils import (
    InvalidTokenError,
    ServiceUnavailableError,
)


# ── Helpers ───────────────────────────────────────────────────────────────────────────


def _entitlement(tenant: str, capabilities: list[str]) -> str:
    """A normal (fits-budget) ``custom:entitlements`` claim value for one tenant."""
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _authorizer_event(
    method: str,
    path: str,
    *,
    claims: dict | None = None,
    extra_headers: dict | None = None,
) -> dict:
    """An API-GW-authorizer proxy event with the given VERIFIED claims (v1 REST shape)."""
    return {
        "httpMethod": method,
        "path": path,
        "headers": extra_headers or {},
        "queryStringParameters": None,
        "body": None,
        "requestContext": {"authorizer": {"claims": claims or {}}},
    }


def _entitled_claims(
    tenant: str = "h-dcn",
    capabilities: tuple[str, ...] = ("members:read",),
    *,
    groups: tuple[str, ...] = ("Members_Read",),
    sub: str = "user-1",
) -> dict:
    """Verified claims that entitle the caller to ``capabilities`` for a single tenant."""
    return {
        "sub": sub,
        "cognito:groups": list(groups),
        "custom:entitlements": _entitlement(tenant, list(capabilities)),
    }


# ── Authenticate (verified) — 401 / 503 ───────────────────────────────────────────────


def test_no_token_returns_401():
    # No authorizer context and no bearer header → the edge cannot authenticate → 401.
    event = {"httpMethod": "GET", "path": "/members", "headers": {}}
    resp = app.handler(event)
    assert resp["statusCode"] == 401


def test_jwks_outage_on_fallback_returns_503(monkeypatch):
    # No authorizer context; a raw bearer token whose verification hits a JWKS outage.
    event = {
        "httpMethod": "GET",
        "path": "/members",
        "headers": {"Authorization": "Bearer sometoken"},
    }

    def _boom(_event, verifier=None):
        raise ServiceUnavailableError()

    monkeypatch.setattr(app, "get_verified_claims", _boom)
    resp = app.handler(event)
    assert resp["statusCode"] == 503


def test_invalid_token_returns_401(monkeypatch):
    event = {
        "httpMethod": "GET",
        "path": "/members",
        "headers": {"Authorization": "Bearer bogus"},
    }

    def _boom(_event, verifier=None):
        raise InvalidTokenError()

    monkeypatch.setattr(app, "get_verified_claims", _boom)
    resp = app.handler(event)
    assert resp["statusCode"] == 401


# ── Authorize (has_capability three-state) ─────────────────────────────────────────────


def test_granted_capability_reaches_the_read_route():
    # A token-backed grant for the route's capability → auth passes → the READ route runs
    # (task 3.2). The caller's role (Members_Read) carries no region grant, so the scope
    # resolves to deny-by-default → an empty scoped list, 200 (never 501, never tenant-wide).
    event = _authorizer_event(
        "GET", "/members", claims=_entitled_claims(capabilities=("members:read",))
    )
    resp = app.handler(event)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["data"] == []


def test_authoritative_token_denial_returns_403():
    # The claim is present and lists the tenant, but WITHOUT the required capability →
    # has_capability returns False (authoritative denial) → 403.
    event = _authorizer_event(
        "GET", "/members", claims=_entitled_claims(capabilities=("members:export",))
    )
    resp = app.handler(event)
    assert resp["statusCode"] == 403


def test_token_does_not_answer_missing_claim_returns_403():
    # No custom:entitlements claim → tenant context cannot be established (fail-safe) → 403.
    event = _authorizer_event(
        "GET", "/members", claims={"sub": "u", "cognito:groups": ["Members_Read"]}
    )
    resp = app.handler(event)
    assert resp["statusCode"] == 403


def test_token_does_not_answer_malformed_claim_returns_403():
    # A malformed/unknown-version claim → decoder fallback_required → no tenant → 403.
    event = _authorizer_event(
        "GET",
        "/members",
        claims={"sub": "u", "cognito:groups": [], "custom:entitlements": "not-json"},
    )
    resp = app.handler(event)
    assert resp["statusCode"] == 403


def test_overflow_claim_returns_403():
    # An overflow signal → token does not carry the per-user answer → deny by default.
    overflow = json.dumps({"v": 1, "overflow": True, "t_keys": ["h-dcn"]})
    event = _authorizer_event(
        "GET", "/members", claims={"sub": "u", "custom:entitlements": overflow}
    )
    resp = app.handler(event)
    assert resp["statusCode"] == 403


def test_tenant_listed_but_capability_absent_is_never_a_silent_allow():
    # Regression: None/False from has_capability must NEVER fall through to a 200/501.
    event = _authorizer_event(
        "POST", "/members", claims=_entitled_claims(capabilities=("members:read",))
    )
    # POST /members (create_member) requires members:write, which the token lacks.
    resp = app.handler(event)
    assert resp["statusCode"] == 403


# ── Tenant context: verify-before-trust ────────────────────────────────────────────────


def test_tenant_comes_from_verified_entitlement_not_header():
    # An X-Tenant header claiming another tenant must be ignored; the verified entitlement
    # (h-dcn) is the only source of tenant context.
    event = _authorizer_event(
        "GET",
        "/members",
        claims=_entitled_claims(tenant="h-dcn", capabilities=("members:read",)),
        extra_headers={"X-Tenant": "other-tenant", "X-Enhanced-Groups": "Members_CRUD"},
    )
    resp = app.handler(event)
    # The header is ignored; the verified h-dcn grant authorizes the read → the READ route
    # runs (task 3.2). No region grant → deny-by-default scope → empty list, 200.
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["data"] == []


def test_ambiguous_multi_tenant_token_denied_by_default():
    # Two tenants in the entitlement with no selector → the pilot edge denies rather than
    # guess which tenant to operate under.
    claim = json.dumps({"v": 1, "t": {"h-dcn": ["members:read"], "other": ["members:read"]}})
    event = _authorizer_event(
        "GET", "/members", claims={"sub": "u", "custom:entitlements": claim}
    )
    resp = app.handler(event)
    assert resp["statusCode"] == 403


def test_context_carries_verified_tenant_sub_and_groups(monkeypatch):
    # White-box: the RequestContext handed to the domain dispatch is built ONLY from
    # verified claims (tenant from entitlement, sub + groups from the token).
    captured = {}

    def _capture_dispatch(spec, request, ctx):
        captured["ctx"] = ctx
        raise app.RouteNotImplemented(spec.name)

    monkeypatch.setattr(app, "_dispatch", _capture_dispatch)

    event = _authorizer_event(
        "GET",
        "/members",
        claims=_entitled_claims(
            tenant="h-dcn", capabilities=("members:read",), groups=("Members_Read",), sub="abc"
        ),
    )
    resp = app.handler(event)
    assert resp["statusCode"] == 501

    ctx = captured["ctx"]
    assert ctx.tenant_id == "h-dcn"
    assert ctx.sub == "abc"
    assert ctx.groups == ["Members_Read"]
    assert ctx.capability == "members:read"


# ── Scope seam: deny-by-default (Property 4) ───────────────────────────────────────────


def test_scope_seam_denies_by_default_until_task_3_1(monkeypatch):
    # Until task 3.1 fills resolve_scope_access, the seam returns an empty scope set for a
    # granted capability — a scope-requiring capability cannot be exercised without a grant.
    captured = {}

    def _capture_dispatch(spec, request, ctx):
        captured["ctx"] = ctx
        raise app.RouteNotImplemented(spec.name)

    monkeypatch.setattr(app, "_dispatch", _capture_dispatch)

    event = _authorizer_event(
        "GET", "/members", claims=_entitled_claims(capabilities=("members:read",))
    )
    resp = app.handler(event)
    assert resp["statusCode"] == 501
    # s5d task 4.1: allowed_scopes is a PER-DIMENSION map. h-dcn wires a single ``region``
    # dimension, so a no-grant caller resolves to {"region": []} — deny for that dimension
    # (Property 4), not a bare empty list.
    assert captured["ctx"].allowed_scopes == {"region": []}


def test_scope_seam_is_a_wired_integration_point(monkeypatch):
    # The edge consults the scope seam for a capability route. Simulate a resolved scope by
    # patching the seam to return a subset and assert it flows onto the context. (The seam's
    # signature is (spec, tenant, claims, *, config_provider=..., grants_reader=...) — task 8.3.)
    # s5d task 4.1: the seam now returns a PER-DIMENSION map {dimension: [values]}; the stub
    # returns one and asserts it flows onto the context verbatim.
    monkeypatch.setattr(
        app, "_resolve_scope_access", lambda spec, tenant, claims, **kw: {"region": ["region-a"]}
    )
    captured = {}

    def _capture_dispatch(spec, request, ctx):
        captured["ctx"] = ctx
        raise app.RouteNotImplemented(spec.name)

    monkeypatch.setattr(app, "_dispatch", _capture_dispatch)

    event = _authorizer_event(
        "GET", "/members", claims=_entitled_claims(capabilities=("members:read",))
    )
    resp = app.handler(event)
    assert resp["statusCode"] == 501
    assert captured["ctx"].allowed_scopes == {"region": ["region-a"]}


# ── Scope from PROJECTED grants (S5b task 8.3, design C5) ──────────────────────────────


def _install_grants(monkeypatch, grants):
    """Install a fake projected-grant reader on the edge (design C5 role→value seam)."""
    from sam.tests.conftest import FakeScopeGrantsReader

    monkeypatch.setattr(
        app, "_SCOPE_GRANTS_READER_OVERRIDE", FakeScopeGrantsReader(grants)
    )


def _capture_ctx(monkeypatch):
    captured = {}

    def _dispatch(spec, request, ctx):
        captured["ctx"] = ctx
        raise app.RouteNotImplemented(spec.name)

    monkeypatch.setattr(app, "_dispatch", _dispatch)
    return captured


def test_scope_from_projected_all_access_grant_is_wildcard(monkeypatch):
    # R2.4: an all-access projected grant (region ["*"]) → allowed_scopes == ["*"]. The scope
    # comes from the PROJECTION keyed by the verified email, never from the token groups.
    _install_grants(monkeypatch, {("h-dcn", "alice@h-dcn.test"): {"region": ["*"]}})
    captured = _capture_ctx(monkeypatch)
    claims = _entitled_claims(capabilities=("members:read",))
    claims["email"] = "alice@h-dcn.test"
    resp = app.handler(_authorizer_event("GET", "/members", claims=claims))
    assert resp["statusCode"] == 501
    assert captured["ctx"].allowed_scopes == {"region": ["*"]}


def test_scope_from_projected_subgroup_grant_is_the_subset(monkeypatch):
    # R2.5: a subgroup-limited projected grant (region ["Noord"]) → exactly that subset.
    _install_grants(monkeypatch, {("h-dcn", "bob@h-dcn.test"): {"region": ["North"]}})
    captured = _capture_ctx(monkeypatch)
    claims = _entitled_claims(capabilities=("members:read",))
    claims["email"] = "bob@h-dcn.test"
    resp = app.handler(_authorizer_event("GET", "/members", claims=claims))
    assert resp["statusCode"] == 501
    assert captured["ctx"].allowed_scopes == {"region": ["North"]}


def test_scope_deny_by_default_when_no_projected_grant(monkeypatch):
    # R2.6: the caller holds the capability but has NO projected grant in the gating dimension
    # (region is required_for Members_CRUD) → the grant is ABSENT → deny (empty allowed_scopes).
    _install_grants(monkeypatch, {})  # no grants for anyone
    captured = _capture_ctx(monkeypatch)
    claims = _entitled_claims(capabilities=("members:read",), groups=("Members_CRUD",))
    claims["email"] = "carol@h-dcn.test"
    resp = app.handler(_authorizer_event("GET", "/members", claims=claims))
    assert resp["statusCode"] == 501
    assert captured["ctx"].allowed_scopes == {"region": []}


def test_scope_ignores_token_groups_uses_projection(monkeypatch):
    # C5: a caller whose TOKEN groups say Regio_All but whose PROJECTED grant is only Noord
    # resolves to ["Noord"] — the projection is authoritative, the token groups are not.
    _install_grants(monkeypatch, {("h-dcn", "dave@h-dcn.test"): {"region": ["North"]}})
    captured = _capture_ctx(monkeypatch)
    claims = _entitled_claims(capabilities=("members:read",), groups=("Regio_All",))
    claims["email"] = "dave@h-dcn.test"
    resp = app.handler(_authorizer_event("GET", "/members", claims=claims))
    assert resp["statusCode"] == 501
    assert captured["ctx"].allowed_scopes == {"region": ["North"]}


# ── CORS on error envelopes ────────────────────────────────────────────────────────────


def test_error_responses_carry_cors_headers():
    event = {"httpMethod": "GET", "path": "/members", "headers": {}}
    resp = app.handler(event)  # 401
    assert resp["statusCode"] == 401
    assert resp["headers"]["Access-Control-Allow-Origin"] == "*"

# ── Capability comes SOLELY from the verified entitlement (R6.1, C-UNWIND — s5c) ───────
#
# The former cognito:groups capability fallback (MEMBERS_LOCAL_AUTH_FALLBACK +
# _local_dev_group_grants_capability / _local_auth_fallback_grants) was REMOVED in s5c
# (R6.1, design C-UNWIND, Property 5). Capability now travels the real S4 channel
# (custom:entitlements via PreTokenGen); a token that does not answer the capability
# (has_capability → None) is an honest deny (403), and there is NO code path that derives a
# Members capability from cognito:groups. These tests pin that honest-deny behaviour.


def _none_capability(monkeypatch):
    """Force has_capability → None (the 'token does not answer' condition)."""
    monkeypatch.setattr(app, "has_capability", lambda claims, tenant, capability: None)


def test_no_capability_fallback_symbols_remain():
    # Grep-clean guard (R6.1): the removed capability-fallback surface must be gone.
    assert not hasattr(app, "_local_dev_group_grants_capability")
    assert not hasattr(app, "_local_auth_fallback_grants")
    assert not hasattr(app, "_LOCAL_AUTH_FALLBACK_ENV")


def test_none_capability_answer_denies_even_with_members_group(monkeypatch):
    # A local-style token: cognito:groups=[Members_CRUD, ...] and a tenant-resolving claim,
    # but the capability is not answered by the token (None). With the fallback removed the
    # groups NEVER grant → 403 (the honest deny the pilot proves).
    _none_capability(monkeypatch)
    event = _authorizer_event(
        "GET",
        "/members",
        claims=_entitled_claims(capabilities=("members:read",), groups=("Members_CRUD", "Regio_All")),
    )
    resp = app.handler(event)
    assert resp["statusCode"] == 403


def test_false_capability_denial_denies(monkeypatch):
    # A token-backed denial (False) must 403 regardless of a Members group.
    monkeypatch.setattr(app, "has_capability", lambda claims, tenant, capability: False)
    event = _authorizer_event(
        "GET",
        "/members",
        claims=_entitled_claims(capabilities=("members:read",), groups=("Members_CRUD",)),
    )
    resp = app.handler(event)
    assert resp["statusCode"] == 403

# ── Tenant fallback REMOVED (R6.2, C-UNWIND) — tenant resolves from the verified entitlement
#
# The s5b local-dev tenant fallback (``_local_dev_tenant_fallback`` / ``MEMBERS_LOCAL_TENANT_ID``)
# is GONE (task 0.2). Local Cognito tokens carry cognito:groups (e.g. Members_CRUD) but NO
# custom:entitlements claim, so get_entitlements_from_claims returns fallback_required=True with
# NO tenant_keys and _establish_tenant_context raises TenantResolutionError at STEP 2. With the
# fallback removed there is NO substitution: the edge denies honestly (403) at STEP 2, regardless
# of any environment variable. This is the correct pre-wiring state until the PreTokenGen channel
# is switched on (Phase 5). The tests below pin that honest-deny behaviour and guard that no
# tenant-fallback symbol / MEMBERS_LOCAL_TENANT_ID reference remains in live code.


# A local-style token: cognito:groups but NO custom:entitlements (so no tenant resolves).
def _local_groups_claims(*groups: str) -> dict:
    return {"sub": "local-user", "cognito:groups": list(groups or ("Members_CRUD",))}


# The tenant-fallback helper and its env constant MUST NO LONGER EXIST (R6.2, grep-clean guard).
# We assert on the module's LIVE symbols + parsed code (not raw text), so the docstring/comment
# that documents the removal does not count as a lingering reference.
def test_tenant_fallback_symbols_removed_from_live_code():
    assert not hasattr(app, "_local_dev_tenant_fallback"), (
        "_local_dev_tenant_fallback must be removed (R6.2, C-UNWIND)"
    )
    assert not hasattr(app, "_LOCAL_TENANT_ID_ENV"), (
        "_LOCAL_TENANT_ID_ENV must be removed (R6.2, C-UNWIND)"
    )
    # No live code may reference the MEMBERS_LOCAL_TENANT_ID env var. Parse the source to AST
    # so string literals in comments/docstrings that DOCUMENT the removal do not trip this
    # guard — only an actual string/name node counts as a live reference.
    tree = ast.parse(inspect.getsource(app))
    live_str_refs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "MEMBERS_LOCAL_TENANT_ID" in node.value
        and not _is_docstring_constant(tree, node)
    ]
    assert not live_str_refs, (
        "no live MEMBERS_LOCAL_TENANT_ID reference may remain in code (R6.2)"
    )


def _is_docstring_constant(tree: ast.AST, target: ast.Constant) -> bool:
    """True if ``target`` is a module/class/function docstring (an Expr-stmt string literal).

    Docstrings are the only place a MEMBERS_LOCAL_TENANT_ID string is allowed to survive (the
    docstring that DOCUMENTS the removal); any other string constant is a live reference.
    """
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and first.value is target
        ):
            return True
    return False


# End-to-end at the edge: a local no-entitlements token (no tenant resolves) is DENIED honestly
# at STEP 2 — there is no tenant fallback to substitute a tenant, regardless of environment.
def test_no_entitlement_token_denied_honestly_at_tenant_step(monkeypatch):
    # Even a leftover MEMBERS_LOCAL_TENANT_ID in the environment must NOT be consulted.
    monkeypatch.setenv("MEMBERS_LOCAL_TENANT_ID", "h-dcn")

    # cognito:groups=[Members_CRUD, Regio_All], NO custom:entitlements → no tenant resolves →
    # honest 403 at STEP 2 (tenant fallback removed; nothing substitutes a tenant).
    event = _authorizer_event(
        "GET", "/members", claims=_local_groups_claims("Members_CRUD", "Regio_All")
    )
    resp = app.handler(event)
    assert resp["statusCode"] == 403


def test_no_entitlement_token_403s_with_no_env_set(monkeypatch):
    monkeypatch.delenv("MEMBERS_LOCAL_TENANT_ID", raising=False)
    # No env at all → still a 403 at STEP 2 (tenant comes solely from the verified entitlement).
    event = _authorizer_event(
        "GET", "/members", claims=_local_groups_claims("Members_CRUD", "Regio_All")
    )
    resp = app.handler(event)
    assert resp["statusCode"] == 403
