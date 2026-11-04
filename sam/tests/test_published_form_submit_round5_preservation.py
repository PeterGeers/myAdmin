"""
Bugfix spec `bugfix-published-form-submit` - Round 5, Task 18: the PRESERVATION property tests.
Property 10 (Preservation, Round 5). Observation-first: every assertion was OBSERVED on the CURRENT
(pre-Round-5-fix) code and MUST PASS NOW. The Round-5 fix (tasks 19.x) maps public 422 keys to bare
field keys, unifies `required`, reworks the form script and adds error/status CSS; it must NOT change:
  * R15.1/15.2 - a VALID complete submission still writes the same record shape (top-level keys, the
                 applicant's values, `membership.status == "application"`) and the consent gate/stamp;
  * R15.3      - Round-4 preflight: slug host echoed with today's Allow-* headers; foreign origin no ACAO;
  * R15.5      - the AUTHENTICATED MembersApi 422 keeps its dotted `errors[].field` keys (the bare-key
                 mapping of 19.1 is public-only);
  * R15.4      - every EXISTING `LandingPageStyles` rule stays present, unchanged and in order (the fix is
                 ADDITIVE), in the SAM render AND in the Flask-plane caller.
Deliberately NOT asserted: the public 422 key shape, the `required` markup, the script body, and the
absence of `.field-error` / `.form-status-error` CSS (those are the Round-5 bug).
Validates (bugfix): Requirements 15.1, 15.2, 15.3, 15.4, 15.5
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
for _p in (_REPO_ROOT, os.path.join(_REPO_ROOT, "backend", "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sam.members.domain.membership_service import MembershipService  # noqa: E402
from sam.members.domain.application_form_render import (  # noqa: E402
    render_application_form_page,
)

# Reuse sibling helpers/fixtures by import (no duplication).
from sam.tests.test_published_form_submit_round2_preservation import (  # noqa: E402
    _TENANT,
    _service,
    _submission,
)
from sam.tests.test_public_app_preflight import (  # noqa: E402,F401
    _SLUG,
    _SLUG_HOST,
    _edge,  # autouse fixture (slug-marker + embed-origin fakes)
    _h,
    _options,
)
from sam.tests.test_members_write_dispatch import (  # noqa: E402,F401
    _envelope,
    _event,
    _error_fields,
    hooks,  # fixtures consumed by the autouse `inject_service`
    inject_service,
    repo,
    table,
)
from sam.members.handler import app  # noqa: E402

_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "landing_page_styles_r5_snapshot.json",
)

# SNAPSHOT (observed on current code): the authenticated edge reports DOTTED keys.
_AUTH_422_FIELDS = {
    "membership.joined_date",
    "membership.membership_type",
    "personal.last_name",
}


# ══════════════════════════════════════════════════════════════════════════════════════
# R15.1 / R15.2 - valid submission: record shape + consent gate/stamp
# ══════════════════════════════════════════════════════════════════════════════════════
_NAME = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=2, max_size=12)


@settings(max_examples=25, deadline=None)
@given(first=_NAME, last=_NAME)
def test_preserve_valid_submission_record_shape(first, last):
    """A valid, consented submission writes the same record shape with the applicant's values."""
    rec = _service().create_application(
        _TENANT,
        _submission(**{"personal.first_name": first, "personal.last_name": last}),
        session_key="s-r5",
        consent={"accepted": True},
    )
    assert set(rec.keys()) == {
        "consent",
        "locale",
        "member_id",
        "membership",
        "personal",
        "tenant_id",
    }
    assert rec["tenant_id"] == _TENANT
    assert rec["membership"]["status"] == "application"
    assert rec["membership"]["membership_type"] == "gewoon"
    assert rec["personal"]["first_name"] == first
    assert rec["personal"]["last_name"] == last
    assert rec["personal"]["email"] == "sam@example.com"
    assert rec["personal"]["birth_date"] == "1990-05-01"
    assert set(rec["consent"].keys()) == {"version", "accepted_at", "locale"}
    assert rec["consent"]["version"] == "v1"


@settings(max_examples=40, deadline=None)
@given(
    accepted=st.one_of(
        st.booleans(),
        st.sampled_from(["true", "1", "yes", ""]),
        st.integers(min_value=0, max_value=3),
        st.none(),
    )
)
def test_preserve_consent_gate_true_only(accepted):
    """The consent gate is affirmative only for `accepted is True`."""
    assert MembershipService._consent_is_affirmative({"accepted": accepted}) is (
        accepted is True
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# R15.3 - Round-4 preflight unchanged
# ══════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("action", ["applications", "field-config"])
def test_preserve_preflight_slug_host_headers(action):
    resp = _options(_SLUG, _SLUG_HOST, action)
    h = _h(resp)
    assert resp["statusCode"] == 204
    assert h["access-control-allow-origin"] == _SLUG_HOST
    assert h["access-control-allow-methods"] == "GET,POST,OPTIONS"
    assert h["access-control-allow-headers"] == "Content-Type"
    assert h["access-control-max-age"] == "600"
    assert h["vary"] == "Origin"


def test_preserve_preflight_foreign_origin_no_acao():
    resp = _options(_SLUG, "https://evil.example")
    assert resp["statusCode"] == 204
    assert "access-control-allow-origin" not in _h(resp)


# ══════════════════════════════════════════════════════════════════════════════════════
# R15.5 - authenticated MembersApi 422 shape (dotted keys) unchanged
# ══════════════════════════════════════════════════════════════════════════════════════
def test_preserve_authenticated_422_keeps_dotted_field_keys():
    resp = app.handler(
        _event("POST", "/members", body={"membership": {"member_number": "9"}})
    )
    assert resp["statusCode"] == 422
    env = _envelope(resp)
    assert env["success"] is False
    assert env["code"] == "errors.validation.failed"
    assert isinstance(env["errors"], list) and env["errors"]
    assert _error_fields(resp) == _AUTH_422_FIELDS
    assert all("." in f for f in _error_fields(resp))
    by_field = {e["field"]: e for e in env["errors"]}
    assert by_field["personal.last_name"]["code"] == "errors.validation.required"
    for entry in env["errors"]:
        assert set(entry) <= {"field", "code", "params", "detail"}


# ══════════════════════════════════════════════════════════════════════════════════════
# R15.4 - existing LandingPageStyles rules preserved (additive change only)
# ══════════════════════════════════════════════════════════════════════════════════════
def _rule_lines(css: str) -> list[str]:
    return [ln.strip() for ln in css.splitlines() if ln.strip()]


def _is_ordered_subsequence(needles: list[str], hay: list[str]) -> bool:
    it = iter(hay)
    return all(any(n == h for h in it) for n in needles)


@pytest.fixture(scope="module")
def snap() -> dict:
    with open(_FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def test_preserve_styles_existing_rules_still_present(snap):
    from services.landing_page_styles import LandingPageStyles

    page = LandingPageStyles.build_page_css(snap["color_primary"], snap["color_accent"])
    variables = LandingPageStyles.build_css_variables(snap["branding"])
    assert _is_ordered_subsequence(_rule_lines(snap["page_css"]), _rule_lines(page))
    assert _is_ordered_subsequence(
        _rule_lines(snap["css_variables"]), _rule_lines(variables)
    )


def test_preserve_styles_sam_render_embeds_existing_rules(snap):
    """The SAM form render embeds the (unchanged) existing rules."""
    html = render_application_form_page(
        {"fields": []},
        head_meta={"title": "Aanmelden"},
        branding={
            "color_primary": snap["color_primary"],
            "color_accent": snap["color_accent"],
        },
        slug=_SLUG,
        public_api_base="https://api.example.test",
    )
    assert _is_ordered_subsequence(_rule_lines(snap["page_css"]), _rule_lines(html))


def test_preserve_styles_flask_caller_gets_existing_rules(snap, monkeypatch):
    """The Flask-plane caller (landing page publish) embeds the same existing rules."""
    import types

    # The SAM plane forbids importing mysql.connector. The Flask service only needs
    # `database.DatabaseManager` at import time, so stub that module for this test and
    # drop any cached import of the services that pull it in.
    fake_media = types.ModuleType("services.media_asset_service")
    fake_media.MediaAssetService = type("MediaAssetService", (), {})
    monkeypatch.setitem(sys.modules, "services.media_asset_service", fake_media)
    monkeypatch.delitem(
        sys.modules, "services.landing_page_publish_service", raising=False
    )
    from services.landing_page_publish_service import LandingPagePublishService

    svc = LandingPagePublishService(None, None, None)
    html = svc.generate_index_html(
        {
            "branding": {
                "color_primary": snap["color_primary"],
                "color_accent": snap["color_accent"],
            }
        },
        "r5-slug",
    )
    assert _is_ordered_subsequence(_rule_lines(snap["page_css"]), _rule_lines(html))
