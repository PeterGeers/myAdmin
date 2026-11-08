"""
Bugfix spec `bugfix-published-form-submit` — Round 6, Task 21: the bug-condition EXPLORATION test.

Branch: `bugfix/published-form-submit-round6`. Property 11 (Round-6 Bug Condition).

DECISION (user, this session): **the application form is the boss.** On the PUBLIC application
form a field is required IFF the tenant marked it `application_required` (plus the fixed public
identity keys email/last_name/birth_date, with server-stamped keys always NOT required). The
engine's `effective_application_required` → `_platform_required_by_engine` ALSO unions the
platform-registry "required floor" into the public rule — that automated gatekeeping is the thing
to remove (bugfix.md Round 6, requirements 16/17/18; design.md Property 11).

REPRODUCTION (root-cause re-investigation, this session): the floor-union bug reproduces on the
OVERLAY field `region` — resolved platform-`required:true`, NO `application_required`, so the
engine demands it via the floor (`overlay.region` VALIDATION_REQUIRED) AND the public schema
renders it required. A FIXED-field override `required` (e.g. `personal.gender`) does NOT reach the
public floor, because `_platform_required_by_engine` reads the platform REGISTRY for fixed fields —
so `gender` is already accepted blank today. `region` is therefore the FORM_IS_BOSS reproduction;
`gender` is only the "already correct" illustrative case.

This test ENCODES THE EXPECTED (Round-6-fixed) behaviour, so on the CURRENT (unfixed) code the
FORM-IS-BOSS facets MUST FAIL — each failure is the counterexample proving the bug. After the fix
(tasks 23.x) the SAME assertions PASS unchanged. DO NOT fix the test or the code when it fails.

ONE h-dcn-shaped setup, used by every facet (steering 39 — prove against the REAL stored shape)
-----------------------------------------------------------------------------------------------
`_hdcn_service()` builds a REAL `MembershipService` over a REAL `MembersProjectionReader` seeded
with the REAL h-dcn `config#fields` row captured read-only from TEST and committed as
`fixtures/hdcn_config_fields_live_test_round5.json`. That stored row ALREADY carries exactly the
Round-6 shapes the decision describes — no invented fixture (steering 39):

  * `fields.region`             — OVERLAY, `application_visible:true`, resolved platform
                                   `required:true`, NO `application_required` (the floor-union
                                   reproduction: the engine demands it as `overlay.region`).
  * `overrides.personal.gender`  — FIXED, `application_visible:true`, override `required:true`
                                   (the members-table/staff floor axis), NO `application_required`.
                                   A fixed override does NOT reach the public floor, so gender is
                                   ALREADY accepted blank today — the illustrative, not the repro.
  * `overrides.membership.status`— FIXED, server-stamped, `application_visible:true`, override
                                   `required:true`, NO `application_required`.
  * `fields.magazine_pref`       — overlay, `application_visible:true`, `application_required:true`.

The only synthetic piece is the scope dimension vocabulary (`SAMPLE_SCOPE_CONFIG`, as in the
sibling Round-5 test) — the live `region` field is scope-backed and its option VALUES are
irrelevant to required-ness.

Facets of isBugConditionR6 (bugfix.md / design.md Round 6)
----------------------------------------------------------
  * FORM_IS_BOSS          — the OVERLAY field `region` with the resolved platform-floor
                            `required:true` but NO `application_required`, submitted BLANK (consent
                            accepted, all identity keys + every genuinely form-required field
                            supplied) → there must be NO `overlay.region` error in the 422 (region
                            accepted blank). Under the sole-rule a field the tenant did NOT mark
                            `application_required` is OPTIONAL on the public form. On unfixed code
                            the floor union demands the platform-required `region` → FAILS.
  * FORM_REQUIRED_ENFORCED— a field the tenant DID mark `application_required` (`magazine_pref`),
                            left blank → a `VALIDATION_REQUIRED` 422 (the form's intent honoured;
                            this already passes today — pinned so the fix cannot regress it).
  * RENDER_PARITY         — `get_public_field_config` renders `required` == the set the engine
                            enforces, under the SIMPLIFIED rule (so `region` / `gender` / `status`
                            render NOT required). On unfixed code the engine-enforced set still
                            includes the floor-only `region` → the two sets differ → FAILS.
  * SERVER_STAMPED_EXCLUDED— the stored override `required:true` on `membership.status`
                            notwithstanding, the public schema renders `status` NOT required AND
                            the engine does not demand it.

Validates (bugfix): Requirements 16.1, 16.2, 16.3, 17.1, 17.3, 17.4, 17.5 (Round 6 exploration)
"""

from __future__ import annotations

import json
import os
import sys

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

from sam.members.domain._membership_errors import MemberValidationError
from sam.members.domain.application_readiness import StaticMailReadinessProvider
from sam.members.domain.application_service import ApplicationService
from sam.members.domain.error_codes import VALIDATION_REQUIRED
from sam.members.domain.membership_service import MembershipService
from sam.members.domain.scope_dimensions import StaticScopeConfigProvider
from sam.members.repository.projection_config_reader import (
    MembersProjectionReader,
)
from sam.tests._scope_fixtures import SAMPLE_SCOPE_CONFIG
from sam.tests.test_create_application import _ApplicationRepo
from sam.tests.test_published_form_submit_round3_bug_condition import _FakeTable

_TENANT = "h-dcn"
_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "hdcn_config_fields_live_test_round5.json",
)

# The field-config keys the decision names (steering 39 — the stored h-dcn shapes).
_REGION_KEY = "region"  # OVERLAY, resolved platform required:true, NO application_required (REPRO)
_GENDER_KEY = "gender"  # FIXED, override required:true, NO application_required (already accepted)
_STATUS_KEY = "status"  # FIXED, server-stamped, override required:true
_MAGAZINE_KEY = "magazine_pref"  # overlay, application_required:true

# A valid region value from the synthetic scope vocabulary (so region never confounds the result).
_REGION_VALUE = "North"


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


def _valid_submission_fields() -> dict:
    """A VALID public submission: every genuinely form-required field supplied, consent accepted.

    Supplies the fixed public identity keys, every platform-required address/personal/membership
    field, the scope-backed `region`, the `application_required` overlay field (`magazine_pref`),
    and a valid `membership_type` — so the ONLY thing under test in a given facet is the single
    field that facet mutates.
    """
    return {
        "personal.first_name": "Sam",
        "personal.last_name": "Jansen",
        "personal.email": "sam@example.com",
        "personal.birth_date": "1990-05-01",
        "personal.phone": "0612345678",
        "personal.street": "Hoofdstraat 1",
        "personal.postal_code": "1000AA",
        "personal.city": "Amsterdam",
        "personal.country": "NL",
        "personal.gender": "man",  # a VALID enum value (facets mutate this when needed)
        "membership.membership_type": "gewoon_lid",
        "magazine_pref": "papier",  # application_required overlay field
        "region": _REGION_VALUE,
    }


def _create(service: MembershipService, fields: dict, session_key: str):
    return _application_service(service).create_application(
        _TENANT,
        {"fields": fields},
        session_key,
        locale="nl",
        consent={"accepted": True},
    )


def _rendered_required(service: MembershipService) -> set[str]:
    """The set of public field keys rendered `required` by `get_public_field_config`."""
    config = service.get_public_field_config(_TENANT)
    return {f["key"] for f in config["fields"] if f.get("required")}


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: FORM_IS_BOSS — Defect 16.1 / Expected 17.1
# ══════════════════════════════════════════════════════════════════════════════════════


def test_form_is_boss_blank_platform_required_overlay_field_is_accepted():
    """FORM_IS_BOSS: a blank OVERLAY field with the resolved platform floor `required:true` but NO
    `application_required` is ACCEPTED on the public form (the tenant did not mark it required on
    the form).

    `region` (OVERLAY, resolved platform `required:true`, NO `application_required`) is submitted
    BLANK while every identity key + every genuinely form-required field is supplied and consent is
    accepted. Under the sole-rule the form does not require it → there must be NO `overlay.region`
    error.

    CURRENT (unfixed): `effective_application_required` unions the platform-registry floor
    (`_platform_required_by_engine`), so the platform-required overlay field is demanded of the
    applicant → a `VALIDATION_REQUIRED` entry for `overlay.region` appears in the 422 → FAILS.
    This is the real reproduction of the floor-union bug (a FIXED override like `gender` never
    reaches the public floor and is already accepted blank today — see the companion assertion).

    Validates (bugfix): Requirement 16.1 / 17.1
    """
    service = _hdcn_service()
    fields = _valid_submission_fields()
    # Submit region BLANK (omitted): the field is on the form but the applicant leaves it empty.
    fields.pop(_REGION_KEY, None)

    region_error = None
    try:
        _create(service, fields, "r6-form-is-boss")
    except MemberValidationError as exc:
        region_error = exc.errors.get("overlay.region")

    assert region_error is None, (
        "BUG (FORM_IS_BOSS facet): a blank OVERLAY field the tenant did NOT mark "
        "`application_required` (`region`, resolved platform `required:true`) was demanded of the "
        f"applicant. 422 carries overlay.region -> {getattr(region_error, 'code', None)!r}. "
        "Counterexample: the platform-registry floor is unioned into the public-form requiredness "
        "rule, so the application form is NOT the boss — a field the human did not mark required "
        "on the form is still demanded."
    )


def test_form_is_boss_fixed_override_gender_is_already_accepted_today():
    """FORM_IS_BOSS (illustrative, must PASS on unfixed code): a blank FIXED-field override
    (`personal.gender`, stored override `required:true`, NO `application_required`) is ALREADY
    accepted blank today.

    A fixed-field override `required` never reaches the public floor — `_platform_required_by_engine`
    reads the platform REGISTRY for fixed fields — so gender is NOT the floor-union reproduction
    (that is the OVERLAY field `region`, asserted above). This pins the already-correct case so the
    Round-6 fix does not regress it.

    Validates (bugfix): Requirement 16.1 (illustrative)
    """
    service = _hdcn_service()
    fields = _valid_submission_fields()
    fields.pop("personal.gender", None)  # blank the fixed-override field

    gender_error = None
    try:
        _create(service, fields, "r6-gender-already-ok")
    except MemberValidationError as exc:
        gender_error = exc.errors.get("personal.gender")

    assert gender_error is None, (
        "A blank FIXED-field override (`personal.gender`) is expected to be ACCEPTED today — a "
        "fixed override `required` does not reach the public floor. If this now fails, the "
        "reproduction premise has shifted; re-investigate before changing the test."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: FORM_REQUIRED_ENFORCED — Expected 17.1 (the kept behaviour)
# ══════════════════════════════════════════════════════════════════════════════════════


def test_form_required_enforced_blank_application_required_field_is_rejected():
    """FORM_REQUIRED_ENFORCED: a field the tenant DID mark `application_required`, left blank,
    is REJECTED with a `VALIDATION_REQUIRED` 422 (the form's intent is honoured).

    `magazine_pref` is `application_required:true` on the stored row. This already passes today —
    it is pinned so the Round-6 fix (which removes the floor union) cannot accidentally stop
    enforcing the form's OWN requiredness axis.

    Validates (bugfix): Requirement 17.1 (kept behaviour)
    """
    service = _hdcn_service()
    fields = _valid_submission_fields()
    fields.pop(_MAGAZINE_KEY, None)  # blank the application_required field

    with pytest.raises(MemberValidationError) as exc:
        _create(service, fields, "r6-form-required")

    err = exc.value.errors.get("overlay.magazine_pref")
    assert err is not None and err.code == VALIDATION_REQUIRED, (
        "a field the tenant marked `application_required` (`magazine_pref`) left blank must be a "
        f"VALIDATION_REQUIRED 422. errors={ {k: v.code for k, v in exc.value.errors.items()} !r}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: RENDER_PARITY — Defect 16.1 / Expected 17.3
# ══════════════════════════════════════════════════════════════════════════════════════


def test_render_parity_rendered_required_equals_engine_required_under_sole_rule():
    """RENDER_PARITY: controls rendered `required` == the fields the engine enforces as required,
    under the SIMPLIFIED (sole-rule) requiredness.

    The engine-enforced set is probed by an all-blank submit (consent accepted) through the REAL
    `create_application`; engine dotted keys are mapped to bare by suffix ONLY here, for comparison
    (as in the Round-5 parity test).

    CURRENT (unfixed): the render side and the engine side BOTH read
    `effective_application_required`, so they agree WITH the floor union — but that union is the
    bug. Under the sole-rule a floor-only field like `region` must be in NEITHER set; on unfixed
    code `region` is BOTH engine-required (`overlay.region`) and rendered required via the floor →
    the expected sole-rule set (identity keys + `application_required` fields + membership_type)
    does not match → FAILS.

    Validates (bugfix): Requirement 16.1 / 17.3
    """
    service = _hdcn_service()
    rendered_required = _rendered_required(service)

    with pytest.raises(MemberValidationError) as caught:
        _application_service(service).create_application(
            _TENANT,
            {"fields": {}},
            "r6-parity",
            locale="nl",
            consent={"accepted": True},
        )
    engine_required = {
        dotted.rsplit(".", 1)[-1]
        for dotted, err in caught.value.errors.items()
        if err.code == VALIDATION_REQUIRED
    }

    # Under the sole-rule, requiredness == the public identity keys + the tenant's
    # `application_required` fields + membership_type (its own D21/R11 rule). The floor-only OVERLAY
    # field `region`, a FIXED floor-only field (`gender`) and a server-stamped field (`status`) are
    # all NOT required — so `region` must be in NEITHER set.
    expected = {"last_name", "email", "birth_date", "membership_type", "magazine_pref"}

    assert rendered_required == engine_required == expected, (
        "BUG (RENDER_PARITY facet): under the sole-rule the rendered-required set and the "
        "engine-required set must both equal the identity keys + application_required fields + "
        f"membership_type. rendered={sorted(rendered_required)!r}; "
        f"engine(all-blank)={sorted(engine_required)!r}; expected={sorted(expected)!r}. "
        f"rendered-only={sorted(rendered_required - expected)!r}; "
        f"engine-only={sorted(engine_required - expected)!r}. Counterexample: the platform-registry "
        "floor is unioned in, so the floor-only OVERLAY field `region` is demanded (and rendered "
        "required) though the tenant never marked it `application_required` on the form."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: SERVER_STAMPED_EXCLUDED — Defect 16.3 / Expected 17.5
# ══════════════════════════════════════════════════════════════════════════════════════


def test_server_stamped_status_is_not_required_in_schema_nor_demanded_by_engine():
    """SERVER_STAMPED_EXCLUDED: `membership.status` (server-stamped, stored override `required:true`)
    is rendered NOT required AND is not demanded by the engine.

    An applicant can never supply `status` — the server stamps `status="application"`. Its stored
    override `required:true` must not make it offerable/required on the public form.

    Validates (bugfix): Requirement 16.3 / 17.5
    """
    service = _hdcn_service()

    # (a) the public schema renders `status` NOT required
    rendered_required = _rendered_required(service)
    assert _STATUS_KEY not in rendered_required, (
        "BUG (SERVER_STAMPED_EXCLUDED facet): the public schema renders the server-stamped "
        f"`status` as required. rendered required={sorted(rendered_required)!r}."
    )

    # (b) the engine does not demand `status` on an all-blank submit (it is server-stamped)
    with pytest.raises(MemberValidationError) as caught:
        _application_service(service).create_application(
            _TENANT,
            {"fields": {}},
            "r6-stamped",
            locale="nl",
            consent={"accepted": True},
        )
    demanded = {
        d for d, e in caught.value.errors.items() if e.code == VALIDATION_REQUIRED
    }
    assert "membership.status" not in demanded, (
        "BUG (SERVER_STAMPED_EXCLUDED facet): the engine demands the server-stamped "
        f"`membership.status` as required. demanded={sorted(demanded)!r}."
    )
