"""
Bugfix spec `bugfix-published-form-submit` — Round 6, Task 22: the PRESERVATION property tests.

Property 12 (Preservation, Round 6). Observation-first: every assertion below was OBSERVED on the
CURRENT (pre-Round-6-fix) code and MUST PASS NOW, so the Round-6 fix (tasks 23.x — dropping the
platform-floor union from the PUBLIC `effective_application_required` authority) cannot regress the
behaviours it is NOT meant to touch.

The Round-6 fix changes ONE thing: on the PUBLIC application form a field is required IFF it is an
identity key OR the tenant marked it `application_required` — the `_platform_required_by_engine`
floor union is removed from that PUBLIC rule. These tests pin everything AROUND that change:

  * STAFF_FLOOR_INTACT (18.1) — the AUTHENTICATED staff write path (`create_member` →
    `_validate_member_record` over the fixed-field registry + overlay `required`) still REJECTS a
    blank platform-required field. The fix only touches the PUBLIC rule, never the members-table /
    staff floor. This is the key guard: the public rule loosens, the staff floor stays.
  * MEMBERSHIP_TYPE_UNCHANGED (18.3) — `membership_type` keeps its OWN D21/R11 rule
    (`_apply_application_membership_type`): exposed on the form → application-required (blank → a
    `VALIDATION_REQUIRED` 422); NOT exposed → the tenant-default is stamped server-side. Both pinned.
  * IDENTITY_REQUIRED (18.2/"the one addition the sole-rule keeps") — the public identity keys
    (email, last_name, birth_date) stay required on the PUBLIC path (blank → 422). These are the
    one addition the sole-rule keeps; the fix preserves them.
  * SERVER_STAMPED (18.4) — a forged body `status` / `member_number` is stripped on the public
    create, and `status` defaults to `"application"` server-side.
  * RESOLVER_AXES_DISTINCT (18.5) — `required` (members-table/staff floor) and
    `application_required` (public-form flag) remain two independent axes on the resolved field.
    Asserted lightly against the REAL h-dcn `region` row (a platform-required, application-optional
    field) — the exhaustive dataclass proof already lives in
    `TestPlatformRequiredAndApplicationRequiredAreIndependentAxes` and is not duplicated here.

Round 1–5 unchanged (18.6) is covered by the full-suite checkpoint (task 24) and NOT re-run here.

ONE REAL h-dcn-shaped setup (steering 39 — prove against the stored shape, not a hand-built fixture)
---------------------------------------------------------------------------------------------------
`_hdcn_service()` (reused verbatim from the Round-6 exploration test) builds a REAL
`MembershipService` over a REAL `MembersProjectionReader` seeded with the REAL h-dcn `config#fields`
row captured read-only from TEST (`fixtures/hdcn_config_fields_live_test_round5.json`). The stored
row already carries the Round-6 shapes:
  * `fields.region`              — OVERLAY, `application_visible:true`, resolved platform
                                   `required:true`, NO `application_required` (floor-only).
  * `overrides.personal.last_name` — FIXED identity anchor (platform-required by the registry),
                                   `application_visible:true`.
  * `overrides.membership.membership_type` — FIXED, `application_visible:true` (EXPOSED → the
                                   application-required path).
  * `overrides.membership.status`— FIXED, server-stamped, `application_visible:true`.
  * `fields.magazine_pref`       — overlay, `application_required:true`.

Validates (bugfix): Requirements 18.1, 18.2, 18.3, 18.4, 18.5 (Round 6 preservation)
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
for _p in (_REPO_ROOT, os.path.join(_REPO_ROOT, "backend", "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sam.members.domain._membership_errors import MemberValidationError  # noqa: E402
from sam.members.domain.error_codes import VALIDATION_REQUIRED  # noqa: E402

# Reuse the Round-6 exploration harness VERBATIM (no duplicate setup): the REAL h-dcn service over
# the stored live `config#fields` row, plus the valid-submission / create helpers.
from sam.tests.test_published_form_submit_round6_bug_condition import (  # noqa: E402
    _REGION_KEY,
    _TENANT,
    _create,
    _hdcn_service,
    _valid_submission_fields,
)


# ══════════════════════════════════════════════════════════════════════════════════════
# STAFF_FLOOR_INTACT — Requirement 18.1 (the key guard: public rule loosens, staff floor stays)
# ══════════════════════════════════════════════════════════════════════════════════════


def test_staff_floor_intact_blank_platform_required_field_still_rejected():
    """The AUTHENTICATED staff write path still REJECTS a blank platform-required field.

    `create_member` → `_validate_member_record` enforces the members-table / staff `required` floor
    over the fixed-field registry + overlay `required`. `personal.last_name` is a platform-required
    identity anchor; a staff create that leaves it blank must be a `VALIDATION_REQUIRED` 422. The
    Round-6 fix touches ONLY the PUBLIC `effective_application_required` authority — it does NOT
    touch `_validate_member_record` / `validate_fixed_fields` / the staff overlay-required path — so
    this must keep rejecting both before AND after the fix.

    Validates (bugfix): Requirement 18.1
    """
    service = _hdcn_service()

    # A staff member body that OMITS the platform-required identity anchor (`personal.last_name`),
    # everything else supplied so last_name is the only required field under test. Scope is
    # all-access (region ["*"]) so the write is not blocked on scope — the required floor is.
    # (Omitted, not blank "": the write-dispatch precedent omits it; a missing platform-required
    # field is the canonical VALIDATION_REQUIRED case.)
    body = {
        "personal": {
            "first_name": "Alex",
            "email": "alex@example.com",
        },
        "membership": {"membership_type": "gewoon_lid", "joined_date": "2024-01-01"},
        "overlay": {"region": "North"},
    }

    with pytest.raises(MemberValidationError) as exc:
        service.create_member(_TENANT, body, {"region": ["*"]})

    err = exc.value.errors.get("personal.last_name")
    assert err is not None and err.code == VALIDATION_REQUIRED, (
        "STAFF_FLOOR_INTACT (18.1): the authenticated staff write path must still REJECT a missing "
        "platform-required field (`personal.last_name`) with VALIDATION_REQUIRED. The members-table "
        "floor is NOT the public form's requiredness rule the Round-6 fix loosens. "
        f"errors={ {k: v.code for k, v in exc.value.errors.items()} !r}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# MEMBERSHIP_TYPE_UNCHANGED — Requirement 18.3 (`_apply_application_membership_type`)
# ══════════════════════════════════════════════════════════════════════════════════════


def test_membership_type_exposed_is_application_required_on_public_path():
    """EXPOSED membership_type → application-required: blank on the public path is a 422.

    The stored h-dcn row exposes `membership.membership_type` on the form
    (`application_visible:true`), so D21/R11 make it application-required — the shared validate chain
    rejects a blank with `VALIDATION_REQUIRED`. Round 6 does NOT fold membership_type into the floor
    union it removes, so this stays unchanged.

    Validates (bugfix): Requirement 18.3
    """
    service = _hdcn_service()
    fields = _valid_submission_fields()
    fields.pop("membership.membership_type", None)  # blank the exposed membership_type

    with pytest.raises(MemberValidationError) as exc:
        _create(service, fields, "r6-mt-exposed")

    err = exc.value.errors.get("membership.membership_type")
    assert err is not None and err.code == VALIDATION_REQUIRED, (
        "MEMBERSHIP_TYPE_UNCHANGED (18.3): an EXPOSED membership_type left blank on the public path "
        "must be a VALIDATION_REQUIRED 422 (its own D21/R11 rule, unchanged by Round 6). "
        f"errors={ {k: v.code for k, v in exc.value.errors.items()} !r}"
    )


def test_membership_type_not_exposed_stamps_tenant_default():
    """NOT-exposed membership_type → the tenant-default is stamped server-side.

    `_apply_application_membership_type` owns this: when the field is NOT exposed on the form the
    applicant never supplies a type, so the FIRST assignable option is stamped server-side so the
    `status=application` record stays catalog-valid. Observed by calling the method directly with a
    config whose `membership_type` field is NOT `application_visible` (the real resolved field's
    options give an assignable default), then asserting the record carries a stamped type.

    Round 6 keeps `_apply_application_membership_type` exactly as today, so this stamp is preserved.

    Validates (bugfix): Requirement 18.3
    """
    import dataclasses

    service = _hdcn_service()
    config = service._field_resolver.resolve(
        _TENANT, scope_vocab=service._scope_vocab(_TENANT)
    )

    # Pull the REAL resolved membership_type field and flip ONLY application_visible → False to
    # observe the not-exposed branch; its real inline options supply the assignable default.
    from sam.members.domain._membership_errors import MEMBERSHIP_TYPE_FIELD_KEY

    mt_field = config.field(MEMBERSHIP_TYPE_FIELD_KEY)
    assert mt_field is not None, "fixture must resolve a membership_type field"
    not_exposed = dataclasses.replace(mt_field, application_visible=False)

    # Rebuild a config view whose membership_type field is not exposed. ResolvedFieldConfig exposes
    # fields via .field(); swap the one field in the resolved field list.
    patched_fields = [
        not_exposed if f.dotted_key() == mt_field.dotted_key() else f
        for f in config.fields
    ]
    patched_config = dataclasses.replace(config, fields=tuple(patched_fields))
    assert patched_config.field(MEMBERSHIP_TYPE_FIELD_KEY).application_visible is False

    record = {"tenant_id": _TENANT, "membership": {}}
    service._apply_application_membership_type(patched_config, record)

    stamped = record.get("membership", {}).get("membership_type")
    assert stamped, (
        "MEMBERSHIP_TYPE_UNCHANGED (18.3): a NOT-exposed membership_type must have the tenant-default "
        f"stamped server-side. record.membership={record.get('membership')!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# IDENTITY_REQUIRED — Requirement 18.2 (the one addition the sole-rule keeps)
# ══════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "blank_key, dotted",
    [
        ("personal.email", "personal.email"),
        ("personal.last_name", "personal.last_name"),
        ("personal.birth_date", "personal.birth_date"),
    ],
)
def test_identity_key_still_required_on_public_path(blank_key, dotted):
    """Each public identity key (email, last_name, birth_date) stays required on the PUBLIC path.

    These are tightened to required on the public path regardless of tenant config, and the Round-6
    sole-rule keeps them (identity key OR `application_required`). Blanking any one → a
    `VALIDATION_REQUIRED` 422 for that key, both before and after the fix.

    Validates (bugfix): Requirement 18.2
    """
    service = _hdcn_service()
    fields = _valid_submission_fields()
    fields.pop(blank_key, None)

    with pytest.raises(MemberValidationError) as exc:
        _create(service, fields, f"r6-identity-{blank_key}")

    err = exc.value.errors.get(dotted)
    assert err is not None and err.code == VALIDATION_REQUIRED, (
        f"IDENTITY_REQUIRED (18.2): the public identity key {dotted!r} must stay required on the "
        f"public path (blank -> VALIDATION_REQUIRED). "
        f"errors={ {k: v.code for k, v in exc.value.errors.items()} !r}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# SERVER_STAMPED — Requirement 18.4 (forged body stripped; status defaults to "application")
# ══════════════════════════════════════════════════════════════════════════════════════


def test_server_stamped_status_and_member_number_forged_body_is_stripped():
    """A forged body `status` / `member_number` is stripped and `status` defaults to "application".

    A public applicant may never set server-owned membership keys. Even with a forged
    `membership.status` / `membership.member_number` in the submission, the created record must
    carry `status == "application"` and no applicant-supplied `member_number`. Round 6 only stops
    these being OFFERED/required — the strip + stamp are unchanged.

    Validates (bugfix): Requirement 18.4
    """
    service = _hdcn_service()
    fields = _valid_submission_fields()
    # Forge the server-owned keys via their dotted public keys (they are application_visible in the
    # fixture, so they ride through the field gate — the create spine must still strip/force them).
    fields["membership.status"] = "active"  # forged: try to escalate the lifecycle state
    fields["membership.member_number"] = "HACK-0001"  # forged staff-owned number

    rec = _create(service, fields, "r6-server-stamped")

    membership = rec.get("membership", {})
    assert membership.get("status") == "application", (
        "SERVER_STAMPED (18.4): a forged body status must be dropped and status forced to "
        f"'application' on public create. membership={membership!r}"
    )
    assert not membership.get("member_number"), (
        "SERVER_STAMPED (18.4): a forged body member_number must be stripped on public create. "
        f"membership={membership!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# RESOLVER_AXES_DISTINCT — Requirement 18.5 (two independent axes on the resolved field)
# ══════════════════════════════════════════════════════════════════════════════════════


def test_resolver_axes_distinct_on_real_region_row():
    """`required` and `application_required` are two independent axes on the resolved field.

    Light assertion against the REAL h-dcn `region` row (OVERLAY, platform `required:true`, NO
    `application_required`): it proves the two axes are distinct on real data — a platform-required,
    application-optional field. The exhaustive dataclass proof lives in
    `TestPlatformRequiredAndApplicationRequiredAreIndependentAxes` and is not duplicated here. Round
    6 simply stops the PUBLIC engine consulting the floor axis; the data model keeping them distinct
    is unchanged.

    Validates (bugfix): Requirement 18.5
    """
    service = _hdcn_service()
    config = service._field_resolver.resolve(
        _TENANT, scope_vocab=service._scope_vocab(_TENANT)
    )

    # `region` is an OVERLAY field, so its canonical dotted key is `overlay.region`
    # (`config.field()` looks up by dotted key — the same key the public 422 reports it under).
    region = config.field(f"overlay.{_REGION_KEY}")
    assert region is not None, "fixture must resolve the overlay `region` field"
    assert region.required is True, (
        "RESOLVER_AXES_DISTINCT (18.5): `region` must stay platform-`required:true` on the resolved "
        f"field. region.required={region.required!r}"
    )
    assert not region.application_required, (
        "RESOLVER_AXES_DISTINCT (18.5): `region` carries NO `application_required`, so the two axes "
        f"are distinct (platform-required but application-optional). "
        f"region.application_required={region.application_required!r}"
    )
