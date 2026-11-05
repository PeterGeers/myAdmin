"""
Bugfix spec `bugfix-published-form-submit` — Round 5, Task 17: the bug-condition EXPLORATION test.

Branch: `bugfix/published-form-submit-round5`. Property 9 (Round-5 Bug Condition).

This test ENCODES THE EXPECTED (Round-5-fixed) behaviour, so on the CURRENT code it MUST FAIL — each
failure is the counterexample proving the bug. After the fix (tasks 19.x) the SAME assertions PASS
unchanged. DO NOT fix the test or the code when it fails.

Live evidence (TEST, `https://hdcn-aanmelden.jabaki.nl`): an EMPTY submit returns 422 with
`errors[].field` = personal.last_name, membership.membership_type, overlay.region, personal.email,
personal.birth_date; the rendered form names its controls by BARE key (last_name, email, birth_date,
membership_type, region, ...) and only `magazine_pref` carries `required`; the stylesheet has no
`.field-error` / `.form-status-error` rules.

ONE h-dcn-shaped setup, used by every facet (steering 39 — prove against the REAL shape)
-----------------------------------------------------------------------------------------
`_hdcn_service()` builds a REAL `MembershipService` over a REAL `MembersProjectionReader` seeded with
the REAL h-dcn `config#fields` row captured read-only from TEST (`test_governance_projection`) and
committed as `fixtures/hdcn_config_fields_live_test_round5.json` (config only: fields / overrides /
functional_groups). The older `hdcn_config_fields_overlay.json` is stale vs live (it does not put
`magazine_pref` on the form), so it cannot reproduce the evidence. The only synthetic piece is the
scope dimension vocabulary (`SAMPLE_SCOPE_CONFIG`, as in sibling tests) — the live `region` field is
scope-backed and its option VALUES are irrelevant to required-ness / error keys.

Facets
------
  * KEYS            — the REAL `public_app.handler` (slug store faked, `_application_service`
                      -> `ApplicationService` over the real service) answers an empty POST with 422
                      whose every `errors[].field` has no '.' and is a rendered control name.
  * REQUIRED_PARITY — controls rendered with `required` == fields the engine rejects as required for
                      an all-blank submission (engine dotted keys mapped to bare by suffix ONLY here,
                      in the test, for comparison).
  * SCRIPT          — in the rendered submit script:
                        (a) the 422 branch maps `errors.validation.required` to "Dit veld is
                            verplicht." (not only the client-side check);
                        (b) `entry.detail` never appears (server English text is never shown);
                        (c) `aria-invalid` is set;
                        (d) NON-REPLACING SUMMARY MARKER (so task 19.3 can satisfy it): the 422
                            *errors branch* — the BRACE-MATCHED body of
                            `if (Array.isArray(arr) && arr.length) {` — contains NO `neutral(` call (neutral REPLACES the
                            status text and wipes fallback messages) and DOES call `statusAppend(`
                            (the appending summary). The other `neutral(` calls (no usable array,
                            network failure, client-side check) are legitimate and not inspected.
  * CSS             — the shared `LandingPageStyles` stylesheet (built exactly as
                      `application_form_render.render_application_form_page` builds it) defines
                      `.field-error`, `.form-status-error` and `.has-error`.

Validates (bugfix): Requirements 13.1, 13.2, 13.3, 13.4 (Round 5 exploration)
"""

from __future__ import annotations

import json
import os
import re
import sys
from html.parser import HTMLParser

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema
from services.landing_page_styles import LandingPageStyles

from sam.members.domain import application_form_render as render_mod
from sam.members.domain._membership_errors import MemberValidationError
from sam.members.domain.application_form_render import (
    render_application_form_page,
)
from sam.members.domain.application_readiness import (
    StaticMailReadinessProvider,
)
from sam.members.domain.application_service import ApplicationService
from sam.members.domain.error_codes import VALIDATION_REQUIRED
from sam.members.domain.membership_service import MembershipService
from sam.members.domain.scope_dimensions import StaticScopeConfigProvider
from sam.members.handler import public_app
from sam.members.repository.projection_config_reader import (
    MembersProjectionReader,
)
from sam.members.repository.slug_marker_store import SlugMarker
from sam.tests._scope_fixtures import SAMPLE_SCOPE_CONFIG
from sam.tests.test_create_application import _ApplicationRepo
from sam.tests.test_published_form_submit_round3_bug_condition import (
    _FakeEmbedOriginReader,
    _FakeSlugReader,
    _FakeTable,
)

_SLUG = "hdcn-aanmelden"
_TENANT = "h-dcn"
_APEX = "jabaki.nl"
_ORIGIN = f"https://{_SLUG}.{_APEX}"
_BASELINE = "https://aanmelden-test.jabaki.nl"
_API_BASE = "https://api.test.example"
_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "hdcn_config_fields_live_test_round5.json",
)


# ══════════════════════════════════════════════════════════════════════════════════════
# The ONE h-dcn-shaped setup
# ══════════════════════════════════════════════════════════════════════════════════════


def _hdcn_service() -> MembershipService:
    """A REAL `MembershipService` over the REAL live-shaped h-dcn `config#fields` row."""
    with open(_FIXTURE, encoding="utf-8") as fh:
        row = json.load(fh)
    table = _FakeTable()
    table.put(
        {
            schema.PARTITION_KEY_ATTR: _TENANT,
            schema.SORT_KEY_ATTR: schema.build_sort_key(
                schema.RECORD_TYPE_CONFIG, "fields"
            ),
            "fields": row["fields"],
            "overrides": row["overrides"],
            "functional_groups": row["functional_groups"],
            schema.VERSION_ATTR: 1,
        }
    )
    return MembershipService(
        _ApplicationRepo(),
        overlay_provider=MembersProjectionReader(table=table),
        scope_config_provider=StaticScopeConfigProvider({_TENANT: SAMPLE_SCOPE_CONFIG}),
    )


def _application_service(service: MembershipService) -> ApplicationService:
    return ApplicationService(
        service,
        mail_readiness_provider=StaticMailReadinessProvider(
            {_TENANT: (True, "h-dcn.nl")}
        ),
    )


def _render(service: MembershipService) -> str:
    """The published artifact, rendered exactly as publish does (public field config -> page)."""
    return render_application_form_page(
        service.get_public_field_config(_TENANT),
        head_meta={"title": "Aanmelden", "canonical": f"{_ORIGIN}/"},
        slug=_SLUG,
        public_api_base=_API_BASE,
    )


class _ControlCollector(HTMLParser):
    """Collect named form controls and whether each carries the `required` attribute."""

    def __init__(self) -> None:
        super().__init__()
        self.names: set[str] = set()
        self.required: set[str] = set()

    def handle_starttag(self, tag, attrs):
        if tag not in ("input", "select", "textarea"):
            return
        attr = dict(attrs)
        name = attr.get("name")
        if not name:
            return
        self.names.add(name)
        if "required" in attr:
            self.required.add(name)


def _controls(artifact: str) -> _ControlCollector:
    collector = _ControlCollector()
    collector.feed(artifact)
    collector.close()
    return collector


def _script(artifact: str) -> str:
    match = re.search(r"<script>(.*?)</script>", artifact, re.DOTALL)
    assert match, "precondition: the artifact embeds the submit script"
    return match.group(1)


def _errors_branch(script: str) -> str | None:
    """The 422 *errors branch*: the brace-matched body of `if (Array.isArray(arr) && arr.length) {`.

    Brace-matched (not "up to the next `} else {`") so a nested if/else inside the `forEach` cannot
    truncate the block before its trailing summary call.
    """
    head = "if (Array.isArray(arr) && arr.length) {"
    start = script.find(head)
    if start == -1:
        return None
    i = start + len(head)
    depth = 1
    while i < len(script) and depth:
        ch = script[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    return script[start:i]


def _422_branch(script: str) -> str | None:
    """The whole `response.status === 422` block, up to the opaque 404/5xx fallthrough."""
    start = script.find("response.status === 422")
    if start == -1:
        return None
    end = script.find("// 404 / 5xx", start)
    return script[start:end] if end != -1 else script[start:]


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: KEYS — Defect 13.1
# ══════════════════════════════════════════════════════════════════════════════════════


def test_keys_empty_submit_422_carries_bare_keys_that_match_rendered_controls(
    monkeypatch,
):
    """KEYS facet: every `errors[].field` is a bare key (no '.') present in the rendered controls.

    CURRENT: the 422 carries engine dotted keys (`personal.last_name`, `overlay.region`, ...), none of
    which names a rendered control -> FAILS.

    Validates (bugfix): Requirement 13.1 / 14.1
    """
    service = _hdcn_service()
    control_names = _controls(_render(service)).names

    monkeypatch.setenv(public_app.ALLOWED_ORIGINS_ENV, _BASELINE)
    monkeypatch.delenv(public_app.APEX_ENV, raising=False)
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _FakeSlugReader(
            {_SLUG: _TENANT},
            {
                _SLUG: SlugMarker(
                    owner_plane="sam",
                    kind="application_form",
                    tenant_id=_TENANT,
                    resource_ref="config#fields",
                )
            },
        ),
    )
    monkeypatch.setattr(
        public_app, "MembersProjectionReader", lambda *a, **k: _FakeEmbedOriginReader()
    )
    app_service = _application_service(service)
    monkeypatch.setattr(public_app, "_application_service", lambda: app_service)

    resp = public_app.handler(
        {
            "httpMethod": "POST",
            "path": f"/public/members/{_SLUG}/applications",
            "headers": {"Origin": _ORIGIN, "Content-Type": "application/json"},
            "queryStringParameters": None,
            "body": json.dumps(
                {
                    "fields": {},
                    "locale": "nl",
                    "consent": {"accepted": True},
                    "website": "",
                }
            ),
            "isBase64Encoded": False,
        }
    )

    assert resp["statusCode"] == 422, (
        f"precondition: expected a 422 for an empty submit, got {resp['statusCode']}: "
        f"{resp.get('body')!r}"
    )
    errors = json.loads(resp["body"]).get("errors") or []
    assert errors, "precondition: the 422 carries a per-field errors array"

    fields = [e.get("field") for e in errors]
    dotted = [f for f in fields if "." in str(f)]
    unmatched = [f for f in fields if f not in control_names]
    assert not dotted and not unmatched, (
        "BUG (KEYS facet): the public 422 leaks physical dotted keys that match no rendered "
        f"control. errors[].field={fields!r}; dotted={dotted!r}; not in rendered control names "
        f"{sorted(control_names)!r}: {unmatched!r}. Counterexample: the script finds no field "
        "wrapper for `personal.last_name`, so each message falls back to the status line."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: REQUIRED_PARITY — Defect 13.3
# ══════════════════════════════════════════════════════════════════════════════════════


def test_required_parity_rendered_required_equals_engine_required():
    """REQUIRED_PARITY facet: controls rendered `required` == fields the engine enforces as required.

    REPOINTED (Round 6, task 23.1b — "the form is the boss"): parity now holds under the SOLE
    public-form rule, NOT the old platform-floor union. The form renders `required` from
    :func:`effective_application_required` (identity keys ∪ `application_required` fields ∪ an
    exposed `membership_type`) and the engine's PUBLIC enforcement is pruned to the SAME predicate
    (`public_form=True` in `_collect_member_record_errors`), so a floor-only field like `region`
    is in NEITHER set. Both sides must therefore equal the sole-rule set — asserted EXPLICITLY, not
    as incidental equality, so a future regression on either side is caught (change-with-tests).

    Before Round 6 this FAILED: the form rendered from `application_required` only while the engine
    enforced the platform `required` floor too, so the engine demanded `region`/`membership_type`
    the form did not render. The Round-6 fix makes render and enforce lean on the one predicate.

    Validates (bugfix): Requirement 13.3 / 14.3 (parity), 16.1 / 17.1 / 17.3 (Round-6 sole-rule)
    """
    service = _hdcn_service()
    rendered_required = _controls(_render(service)).required

    # Engine side: an all-blank submission (consent accepted) through the REAL create_application.
    with pytest.raises(MemberValidationError) as caught:
        _application_service(service).create_application(
            _TENANT,
            {"fields": {}},
            "r5-parity",
            locale="nl",
            consent={"accepted": True},
        )
    # Map engine dotted keys -> bare by suffix. This mapping lives ONLY in the test, for comparison.
    engine_required = {
        dotted.rsplit(".", 1)[-1]
        for dotted, err in caught.value.errors.items()
        if err.code == VALIDATION_REQUIRED
    }

    # The sole public-form rule: the public identity keys + the tenant's `application_required`
    # fields + the exposed `membership_type`. The floor-only OVERLAY field `region` (resolved
    # platform `required:true`, NO `application_required`) and the server-stamped `status` are in
    # NEITHER set under "the form is the boss".
    expected = {"last_name", "email", "birth_date", "membership_type", "magazine_pref"}

    assert rendered_required == engine_required == expected, (
        "REQUIRED_PARITY under the sole-rule: the form's rendered `required` set and the engine's "
        "enforced `required` set must both equal the identity keys + application_required fields + "
        f"membership_type. rendered required={sorted(rendered_required)!r}; engine required "
        f"(all-blank submit)={sorted(engine_required)!r}; expected={sorted(expected)!r}; "
        f"rendered-only={sorted(rendered_required - expected)!r}; "
        f"engine-only={sorted(engine_required - expected)!r}. A floor-only field like `region` must "
        "be in NEITHER set now that render and enforce lean on the one predicate."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: SCRIPT — Defects 13.2 / 13.4
# ══════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def submit_script() -> str:
    return _script(_render(_hdcn_service()))


def test_script_422_branch_maps_required_code_to_dutch_text(submit_script):
    """SCRIPT (a): the 422 branch maps `errors.validation.required` -> "Dit veld is verplicht.".

    CURRENT: the Dutch text only exists in the client-side check; the 422 branch shows the English
    server `detail` -> FAILS.

    Validates (bugfix): Requirement 13.4 / 14.4
    """
    branch = _422_branch(submit_script)
    assert branch is not None, "precondition: the script has a 422 branch"
    assert (
        "errors.validation.required" in branch and "Dit veld is verplicht." in branch
    ), (
        "BUG (SCRIPT facet a): the 422 branch has no code->Dutch mapping for "
        "`errors.validation.required` (needs the code and 'Dit veld is verplicht.' in the 422 "
        "branch). Counterexample: the applicant sees the server's English 'is required'."
    )


def test_script_never_writes_entry_detail_to_the_ui(submit_script):
    """SCRIPT (b): `entry.detail` does not appear anywhere in the script.

    CURRENT: the 422 branch passes `entry.detail` to `showFieldError` -> FAILS.

    Validates (bugfix): Requirement 13.4 / 14.4
    """
    assert "entry.detail" not in submit_script, (
        "BUG (SCRIPT facet b): the script renders the server's English `entry.detail` "
        "(`showFieldError(entry.field, entry.detail || ...)`)."
    )


def test_script_sets_aria_invalid_on_errored_controls(submit_script):
    """SCRIPT (c): `aria-invalid` is set on the errored control.

    CURRENT: the script never sets `aria-invalid` -> FAILS.

    Validates (bugfix): Requirement 13.4 / 14.4
    """
    assert "aria-invalid" in submit_script, (
        "BUG (SCRIPT facet c): the script never sets aria-invalid on a control with an error."
    )


def test_script_422_errors_branch_summary_does_not_replace_fallback_text(submit_script):
    """SCRIPT (d): the 422 errors branch has no `neutral(` call and appends its summary.

    Marker (documented in the module docstring): inside the brace-matched body of
    `if (Array.isArray(arr) && arr.length) {` there is NO `neutral(` (it REPLACES
    the status text) and there IS a `statusAppend(` (the non-replacing summary).

    CURRENT: the branch ends with `neutral("Controleer de gemarkeerde velden.")`, wiping the
    fallback messages `showFieldError` appended -> FAILS.

    Validates (bugfix): Requirement 13.2 / 14.2
    """
    branch = _errors_branch(submit_script)
    assert branch is not None, "precondition: the 422 branch has an errors-array block"
    assert "neutral(" not in branch and "statusAppend(" in branch, (
        "BUG (SCRIPT facet d): the 422 errors branch replaces the status text. "
        f"contains neutral(={'neutral(' in branch}, contains statusAppend(="
        f"{'statusAppend(' in branch}. Counterexample: after mapping, neutral('Controleer de "
        "gemarkeerde velden.') overwrites the fallback messages."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: CSS — Defect 13.4
# ══════════════════════════════════════════════════════════════════════════════════════


def test_css_landing_page_styles_defines_error_and_status_rules():
    """CSS facet: the shared stylesheet defines `.field-error`, `.form-status-error`, `.has-error`.

    Built exactly as `render_application_form_page` builds it (`build_css_variables` +
    `build_page_css` with the default palette).

    CURRENT: none of the three selectors exist -> FAILS.

    Validates (bugfix): Requirement 13.4 / 14.5
    """
    css = "\n".join(
        (
            LandingPageStyles.build_css_variables({}),
            LandingPageStyles.build_page_css(
                render_mod._DEFAULT_COLOR_PRIMARY, render_mod._DEFAULT_COLOR_ACCENT
            ),
        )
    )
    missing = [
        sel
        for sel in (".field-error", ".form-status-error", ".has-error")
        if sel not in css
    ]
    assert not missing, (
        f"BUG (CSS facet): LandingPageStyles defines no rule for {missing!r}. Counterexample: an "
        "error message and the failed status line render unstyled."
    )
