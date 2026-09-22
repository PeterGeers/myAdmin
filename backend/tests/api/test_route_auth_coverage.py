"""Authenticated-route verifier-coverage guard (S2 T6, R1.1).

Every registered HTTP route on the Flask plane must either:
  (a) carry ``@cognito_required`` (verified-JWT protection — since T5, that
      decorator routes through the multi-pool ``JWTVerifier``), or
  (b) appear in one of the two explicitly-justified allowlists below.

This test walks the *actual* Flask URL map (not the source text), so it also
catches decorator-order mistakes: if an auth decorator is applied but does not
actually wrap the registered view, the sentinel marker set by
``cognito_required`` / ``tenant_required`` will be absent and the test fails.

If you add a new route:
  - Authenticated / tenant-scoped route  -> add ``@cognito_required`` (and
    ``@tenant_required`` where it touches tenant data). Nothing to change here.
  - Genuinely public route               -> add it to ``PUBLIC_ENDPOINTS`` with
    a one-line justification.
  - Route that verifies the JWT manually -> add it to ``DELEGATED_OR_MANUAL``
    with a justification (e.g. an OPTIONS/CORS wrapper that delegates to a
    protected handler, or an SSE endpoint that verifies a query-param token via
    the same ``JWTVerifier``).

Reference: .kiro/specs/multi-tenant/s2-jwt-verification (requirements.md R1.1,
design.md "Audit every authenticated route").
"""
import pytest

# --- Legitimately public endpoints (no identity required) ----------------
# Keyed by Flask endpoint name. Value = justification (kept for auditability).
PUBLIC_ENDPOINTS = {
    # Documentation site (MkDocs) + Swagger/flasgger UI — static docs only.
    "serve_docs": "MkDocs documentation site (static)",
    "flasgger.apidocs": "Swagger UI (flasgger)",
    "flasgger.<lambda>": "Swagger UI index (flasgger)",
    "flasgger.apispec_1": "OpenAPI spec JSON (flasgger)",
    "flasgger.oauth_redirect": "Swagger OAuth2 redirect page (flasgger)",
    "flasgger.static": "flasgger static assets",
    # SPA / static asset serving — no user data.
    "static.serve_index": "SPA entrypoint (index.html)",
    "static.serve_backend_static": "backend static assets",
    "static.serve_config": "runtime config.js (public app config)",
    "static.serve_favicon": "favicon",
    "static.serve_jabaki_logo": "public logo asset",
    "static.serve_logo192": "PWA icon",
    "static.serve_logo512": "PWA icon",
    "static.serve_manifest": "PWA manifest",
    "static.serve_static": "static file serving",
    # Health / status — required unauthenticated for Railway/Docker probes and
    # explicitly whitelisted in the security middleware. Return no user data.
    "system_health.health": "container health probe (whitelisted in middleware)",
    "system_health.get_status": "env/mode status probe (whitelisted in middleware)",
    "media_assets.health": "media-assets service health probe (static payload)",
    # Pre-login auth flow — the user has no token yet; reset code is the credential.
    "auth.forgot_password": "password reset request (pre-login)",
    "auth.confirm_reset_password": "password reset confirm via code (pre-login)",
    # Public trial signup — no account yet.
    "signup.create_signup": "public trial signup",
    "signup.resend_verification": "resend signup verification (pre-account)",
    "signup.verify_signup": "verify signup code (pre-account)",
    # Static predefined config definitions from a bundled JSON file (no tenant data).
    "config.get_ledger_parameters": "static ledger parameter definitions (bundled JSON)",
    "config.get_members_parameters": "static members parameter definitions (bundled JSON)",
    # Public landing-page CMS endpoints (anonymous visitors).
    "landing_page.submit_contact": "public landing contact form",
    "landing_page.resolve_slug": "public landing slug resolution",
    # Webhook with its own auth (SNS signature); SNS cannot send a JWT.
    "email_log.ses_notification_webhook": "SES/SNS webhook — SNS signature auth",
    # OAuth redirect target for Google; only relays code to opener. The token
    # exchange/storage happens on the authenticated /oauth/complete endpoint.
    "tenant_admin_credentials.oauth_callback_public": "Google OAuth redirect relay",
}

# --- Verified but not via the decorator on the registered view -----------
# These DO verify the JWT before reading any claim; the decorator just isn't on
# the outermost registered function. Justification kept for auditability.
DELEGATED_OR_MANUAL = {
    # OPTIONS/CORS wrappers: the wrapper answers the CORS preflight without auth,
    # then delegates POST to a @cognito_required(+@tenant_required) handler.
    "invoices.upload_file_wrapper": "POST delegates to upload_file_authenticated (cognito+tenant)",
    "str.str_upload_wrapper": "POST delegates to str_upload_authenticated (cognito+tenant)",
    "str.str_import_payout_wrapper": "POST delegates to str_import_payout_authenticated (cognito)",
    # SSE stream: EventSource cannot send an Authorization header, so it verifies
    # a query-param token through the same JWTVerifier, then checks permission +
    # tenant ownership before streaming.
    "media_assets.scan_status_stream": "SSE — manual JWTVerifier + perms + tenant-ownership check",
}


def _has_cognito(view) -> bool:
    """True if cognito_required actually wraps this registered view.

    Relies on the sentinel attribute set by cognito_required AFTER functools.wraps
    (so it reflects the outermost applied layer, catching decorator-order bugs).
    Falls back to scanning the __wrapped__ chain's qualnames.
    """
    if getattr(view, "_cognito_required", False):
        return True
    seen = set()
    cur = view
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if "cognito_required" in getattr(cur, "__qualname__", ""):
            return True
        cur = getattr(cur, "__wrapped__", None)
    return False


@pytest.fixture
def flask_app(mock_env):
    from src.app import app as flask_app

    flask_app.config["TESTING"] = True
    return flask_app


def _iter_views(flask_app):
    for rule in flask_app.url_map.iter_rules():
        yield rule, flask_app.view_functions.get(rule.endpoint)


def test_every_route_is_protected_or_whitelisted(flask_app):
    """No registered route may be silently unauthenticated (R1.1)."""
    offenders = []
    for rule, view in _iter_views(flask_app):
        endpoint = rule.endpoint
        if _has_cognito(view):
            continue
        if endpoint in PUBLIC_ENDPOINTS or endpoint in DELEGATED_OR_MANUAL:
            continue
        offenders.append(f"{endpoint} ({rule})")

    assert not offenders, (
        "Routes without @cognito_required and not on an allowlist (R1.1). "
        "Add the decorator, or justify in PUBLIC_ENDPOINTS / DELEGATED_OR_MANUAL:\n  "
        + "\n  ".join(sorted(offenders))
    )


def test_allowlists_have_no_stale_entries(flask_app):
    """Allowlist hygiene: every whitelisted endpoint must still exist and must
    still be un-decorated (else remove it from the allowlist)."""
    registered = {rule.endpoint for rule in flask_app.url_map.iter_rules()}
    stale = []
    for ep in list(PUBLIC_ENDPOINTS) + list(DELEGATED_OR_MANUAL):
        if ep not in registered:
            stale.append(f"{ep}: not registered anymore")
            continue
        view = flask_app.view_functions.get(ep)
        if _has_cognito(view):
            stale.append(f"{ep}: now carries @cognito_required — remove from allowlist")
    assert not stale, "Stale allowlist entries (R1.1):\n  " + "\n  ".join(stale)


def test_verifier_coverage_baseline(flask_app):
    """Sanity floor: the vast majority of routes are cognito-protected.

    Guards against a regression where the sentinel/detection silently breaks
    and every route looks 'public'.
    """
    total = 0
    protected = 0
    for _rule, view in _iter_views(flask_app):
        total += 1
        if _has_cognito(view):
            protected += 1
    assert total > 300, f"unexpectedly few routes registered ({total})"
    # At time of the S2 T6 audit: 384/417 carried cognito_required directly.
    assert protected >= 380, f"verifier coverage regressed: {protected}/{total}"
