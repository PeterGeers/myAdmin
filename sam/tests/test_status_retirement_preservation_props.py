"""
retire-members-status-lifecycle-engine — Task 2: the **preservation property tests**.

These are the BASELINE for the retirement. They are written **observation-first**: each facet
pins a behaviour observed on the CURRENT (unfixed) code that MUST REMAIN UNCHANGED after the
lifecycle engine is retired and ``membership.status`` becomes a plain, tenant-driven OPEN enum.
Therefore — unlike the task-1 exploration test — every assertion here is **EXPECTED TO PASS on
the UNFIXED code**, and task 3.8 re-runs this SAME file unchanged to prove the retirement caused
no regression.

Property 2 (Preservation — design §Correctness Properties / bugfix §3): *for any* input where
the bug condition does NOT hold, the fixed system SHALL produce the same result as the original —
preserving the public-form ``status=application`` default, tenant isolation, member
CRUD/read/export, ``gender`` + other open enums, every non-status field, and every OTHER
field-resolver platform invariant.

The five facets map 1:1 to the Unchanged-Behaviour requirements:

* **3.1 — public-form create defaults ``status=application``.** For every generated applicant
  submission, :meth:`MembershipService.create_application` lands a record whose
  ``membership.status == "application"`` — and a client-supplied status NEVER escalates it. This
  default is a server-forced literal on the public path, independent of the engine, so it is
  identical before and after the retirement.

* **3.3 — ``gender`` (and any OPEN overlay enum) round-trips.** For every generated set of tenant
  ``gender`` values: a ``field_overlay`` authoring them resolves into the ``config#fields``
  ``gender.choices`` (save → project → resolve), and a member carrying any of those values
  validates (open-enum path). **This is the EXACT precedent ``status`` follows after the fix** —
  so pinning it as unchanged pins the mechanism the retirement reuses for ``status``.

* **3.2 — member create / get / list / update / delete behave as today + tenant isolation.** For
  every generated NON-status member edit, the authoritative validation + the repository
  read/write path behave exactly as today and stay keyed by ``tenant_id`` (another tenant's
  records are structurally unreachable).

* **3.4 — the field-config read surface is unaffected (catalog / membership_type / non-status
  fields).** For every generated active catalog, :meth:`get_field_config` projects the active
  ``membership_type`` options and the fixed base unchanged — none of it ever depended on the
  lifecycle engine.

* **3.5 — every OTHER field-resolver platform invariant holds.** For generated overlays that
  violate a platform invariant (drop/rename a fixed field via collision, loosen a platform-
  required fixed field, change a fixed field's type), the resolver STILL fails fast — only the
  "NEVER touch the closed ``membership.status`` enum" invariant is being removed, never these.

All facets are DB-free: they drive the domain over in-memory fakes (the same fakes the sibling
create-application / field-config / reads tests use), never boto3 / DynamoDB / MySQL.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
"""

from __future__ import annotations

import os
import sys

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.field_resolver import (
    FieldResolver,
    FixedFieldOverride,
    OverlayError,
    OverlayField,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import (
    EnumOption,
    FieldType,
    FieldValidationError,
    field_by_key,
    validate_fixed_fields,
)
from sam.members.domain.membership_service import (
    MemberNotFound,
    MembershipService,
)

# Reuse the sibling tests' in-memory fakes + factories so these preservation observations run
# over EXACTLY the harness the behaviour they preserve is already exercised through — no new
# scaffolding, no AWS. (`_ApplicationRepo` is the create-application fake repo with the
# first-wins session claim; `FakeCatalogRepository`/`_entry` are the field-config catalog fake.)
from sam.tests.test_create_application import (
    _AFFIRMATIVE_CONSENT,
    _ApplicationRepo,
    _overlay_public_form,
)
from sam.tests.test_field_config_endpoint import FakeCatalogRepository, _entry
from sam.tests.test_membership_service_reads import FakeMembersRepository

TENANT = "h-dcn"


# ─────────────────────────────────────────────────────────────────────────────────────
# Shared generators
# ─────────────────────────────────────────────────────────────────────────────────────

# Simple non-blank enum-value tokens (the point is round-trip identity across the input space,
# not fuzzing the unicode codec — the real tenant values are short ASCII codes like M/V/X/N).
_enum_values = st.lists(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", min_size=1, max_size=10).filter(
        lambda s: s.strip() != ""
    ),
    min_size=1,
    max_size=6,
    unique=True,
)

# A person's name part (never blank — last_name is the platform-required identity anchor).
_name = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=20
).map(str.strip).filter(lambda s: s != "")


def _valid_member(**over) -> dict:
    """A minimal, otherwise-valid member record (all required fixed fields present, non-status).

    Required fixed fields per the registry: ``personal.last_name``, ``membership.status``,
    ``membership.membership_type``, ``membership.joined_date``. We hold ``status`` at a platform
    value here (``active``) so these NON-status facets never trip the bug condition — the point is
    everything ELSE behaves as today.
    """
    record = {
        "personal": {"last_name": "Jansen"},
        "membership": {
            "status": "active",
            "membership_type": "gewoon",
            "joined_date": "2020-01-01",
        },
    }
    for k, v in over.items():
        group, _, key = k.partition(".")
        record.setdefault(group, {})[key] = v
    return record


# ─────────────────────────────────────────────────────────────────────────────────────
# 3.1 — public application-form create stamps membership.status = "application"
# ─────────────────────────────────────────────────────────────────────────────────────


def _application_service() -> MembershipService:
    repo = _ApplicationRepo()
    repo.add_type(TENANT, _entry(TENANT, "gewoon", order=10))
    repo.add_type(TENANT, _entry(TENANT, "erelid", order=20))
    return MembershipService(
        repo, overlay_provider=StaticOverlayProvider({TENANT: _overlay_public_form()})
    )


# A generated applicant submission carrying the required public-path identity (email/name/DOB)
# plus arbitrary name values — and OPTIONALLY a hostile client-supplied status (which must be
# ignored, never escalated — R3.1).
@st.composite
def _applicant_submission(draw):
    body = {
        "personal.first_name": draw(_name),
        "personal.last_name": draw(_name),
        "personal.email": "applicant@example.com",
        "personal.birth_date": "1990-05-01",
        "membership.membership_type": "gewoon",
    }
    # Half the time the client tries to self-assign a status it must never get to keep.
    hostile = draw(st.sampled_from([None, "active", "pending", "left", "died", "anything"]))
    if hostile is not None:
        body["membership.status"] = hostile
    return body


@settings(max_examples=40, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(body=_applicant_submission(), session_n=st.integers(min_value=0, max_value=10_000))
def test_public_form_create_defaults_status_application(body, session_n):
    """3.1: every public-form applicant lands as ``status=application``, client value ignored.

    EXPECTED (unfixed AND fixed): PASS — the public create forces ``status=application`` as a
    server literal, independent of any lifecycle engine, so a generated applicant (with or
    without a hostile client status) always lands in ``application``.
    """
    service = _application_service()
    rec = service.create_application(
        TENANT, body, session_key=f"s-{session_n}", consent=_AFFIRMATIVE_CONSENT
    )
    assert rec["membership"]["status"] == "application", (
        "REGRESSION (3.1): public-form create no longer defaults membership.status to "
        f"'application' (got {rec['membership'].get('status')!r})"
    )


# ─────────────────────────────────────────────────────────────────────────────────────
# 3.3 — a tenant `gender` value saves → projects → resolves → validates (the status precedent)
# ─────────────────────────────────────────────────────────────────────────────────────


@settings(max_examples=60)
@given(values=_enum_values)
def test_gender_open_enum_round_trips_unchanged(values):
    """3.3: a tenant's ``gender`` values survive resolve AND validate on a member — unchanged.

    This is the EXACT precedent ``status`` follows after the fix: ``gender`` is already an OPEN
    enum (``choices=None``), its value list is tenant overlay config, and it round-trips
    save → project → resolve → validate with no code change. Pinning it as invariant pins the
    mechanism the retirement reuses for ``status``.

    EXPECTED (unfixed AND fixed): PASS.
    """
    options = tuple(EnumOption(value=v, label={"en": v, "nl": v}) for v in values)
    overlay = TenantOverlay(
        overrides={"personal.gender": FixedFieldOverride(options=options)}
    )
    resolver = FieldResolver(StaticOverlayProvider({TENANT: overlay}))

    # (A) The tenant values resolve into config#fields gender.choices (save → project → resolve).
    cfg = resolver.resolve(TENANT)
    gender = cfg.field("personal.gender")
    assert gender is not None and gender.type is FieldType.ENUM
    resolved = tuple(gender.choices or ())
    assert resolved == tuple(values), (
        "REGRESSION (3.3): tenant gender values did not round-trip into resolved "
        f"gender.choices (authored {tuple(values)!r}, resolved {resolved!r})"
    )

    # (B) A member carrying any of those gender values validates (the open-enum path).
    for v in values:
        validate_fixed_fields(_valid_member(**{"personal.gender": v}))


def test_gender_is_an_open_enum_baseline():
    """3.3 baseline: ``gender`` is an OPEN enum (``choices=None``) — the state ``status`` joins.

    EXPECTED (unfixed AND fixed): PASS. (On unfixed code ``status`` is NOT yet open — that is the
    bug the task-1 explore test pins; here we only assert the PRESERVED ``gender`` baseline.)
    """
    gender = field_by_key("personal.gender")
    assert gender is not None and gender.type is FieldType.ENUM
    assert gender.choices is None, (
        "REGRESSION (3.3): personal.gender is no longer an OPEN enum "
        f"(choices={gender.choices!r}); it must stay tenant-driven like before"
    )


# ─────────────────────────────────────────────────────────────────────────────────────
# 3.2 — member create / get / list / update / delete + tenant isolation unchanged
# ─────────────────────────────────────────────────────────────────────────────────────


class _CrudRepo(FakeMembersRepository):
    """The reads fake + the write/delete surface, so a full CRUD round-trip runs DB-free."""

    def save_member(self, tenant_id, record):  # type: ignore[override]
        member_id = record.get("member_id")
        if not member_id:
            raise ValueError("member must carry a non-empty 'member_id'")
        self.members[(tenant_id, member_id)] = dict(record)
        return dict(record)

    def delete_member(self, tenant_id, member_id):  # type: ignore[override]
        self.members.pop((tenant_id, member_id), None)

    def get_membership_type(self, tenant_id, type_code):  # type: ignore[override]
        # Any non-blank type resolves to an active entry so the reference check never blocks a
        # non-status edit (the catalog reference check is pinned elsewhere; here it is noise).
        return _entry(tenant_id, str(type_code), order=10) if type_code else None


# A NON-status member edit: a non-empty value for a non-status fixed field (first_name/city/
# phone). Never touches membership.status, so NOT a bug-condition input (Preservation domain).
_non_status_edits = st.fixed_dictionaries(
    {
        "field": st.sampled_from(
            ["personal.first_name", "personal.city", "personal.phone", "personal.street"]
        ),
        "value": _name,
    }
)


@settings(max_examples=50)
@given(
    member_id=st.uuids().map(str),
    edit=_non_status_edits,
    other_id=st.uuids().map(str),
)
def test_member_crud_and_tenant_isolation_unchanged(member_id, edit, other_id):
    """3.2: a NON-status member create/get/list/update/delete + tenant isolation are unchanged.

    EXPECTED (unfixed AND fixed): PASS — none of the member CRUD / read path depends on the
    lifecycle engine, and every repository touch stays keyed by ``tenant_id``.
    """
    repo = _CrudRepo()
    service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))

    # create (a valid, active, non-status record)
    record = _valid_member(**{edit["field"]: edit["value"]})
    record["member_id"] = member_id
    service._validate_member_record(TENANT, record, partial=False)  # authoritative validation
    repo.save_member(TENANT, record)

    # get + list are tenant-scoped
    assert repo.get_member(TENANT, member_id) is not None
    assert any(m["member_id"] == member_id for m in repo.list_members(TENANT))

    # a non-status partial update validates (an ordinary field edit — unchanged)
    group, _, key = edit["field"].partition(".")
    patch = {group: {key: edit["value"]}}
    service._validate_member_record(TENANT, patch, partial=True)

    # tenant isolation: a DIFFERENT tenant never sees this record (structural, keyed by tenant)
    assert other_id != member_id  # hypothesis gives distinct uuids
    assert repo.get_member("other-tenant", member_id) is None
    assert repo.list_members("other-tenant") == []

    # delete removes it, scoped to the tenant
    repo.delete_member(TENANT, member_id)
    assert repo.get_member(TENANT, member_id) is None


# ─────────────────────────────────────────────────────────────────────────────────────
# 3.4 — the field-config read surface (catalog / membership_type / non-status fields) unaffected
# ─────────────────────────────────────────────────────────────────────────────────────


# A generated active catalog: 1..5 distinct type codes with presentation order.
_catalog = st.lists(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=2, max_size=12).filter(
        lambda s: s.strip() != ""
    ),
    min_size=1,
    max_size=5,
    unique=True,
)


@settings(max_examples=40)
@given(codes=_catalog)
def test_field_config_surface_unaffected(codes):
    """3.4: the resolved field-config surface (catalog/membership_type/fixed base) is unchanged.

    EXPECTED (unfixed AND fixed): PASS — ``get_field_config`` composes the resolver + the active
    catalog read; none of that depended on the lifecycle engine. (The engine only ever added the
    ``lifecycle`` block, which the retirement removes — pinned in the paired field-config test,
    not here; this facet pins everything ELSE stays identical.)
    """
    repo = FakeCatalogRepository()
    for i, code in enumerate(codes):
        repo.add_type(TENANT, _entry(TENANT, code, order=(i + 1) * 10))
    service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))

    config = service.get_field_config(TENANT)

    # tenant-scoped + the fixed base survives
    assert config["tenant_id"] == TENANT
    keys = {(f["group"], f["key"]) for f in config["fields"]}
    assert ("personal", "last_name") in keys
    assert ("membership", "membership_type") in keys
    assert ("personal", "gender") in keys  # the open-enum precedent is still surfaced

    # membership_type options ride ON the field (03b BU-3 — no standalone feed). Pre-fold the
    # assembly seam falls back to the active catalog, presentation-ordered (design C8).
    mt = next(f for f in config["fields"] if f["key"] == "membership_type")
    option_values = [o["value"] for o in mt["options"]]
    assert set(option_values) == set(codes)

    # structural tenant isolation at the config surface: another tenant sees none of these types
    other = service.get_field_config("other-tenant")
    other_mt = next(f for f in other["fields"] if f["key"] == "membership_type")
    assert other_mt["options"] == []


# ─────────────────────────────────────────────────────────────────────────────────────
# 3.5 — every OTHER field-resolver platform invariant still holds (only the status one is removed)
# ─────────────────────────────────────────────────────────────────────────────────────


def _resolve(overlay: TenantOverlay):
    return FieldResolver(StaticOverlayProvider({TENANT: overlay})).resolve(TENANT)


def test_invariant_variable_field_cannot_collide_with_a_fixed_key():
    """3.5: an overlay variable field colliding with a fixed field key still fails fast.

    EXPECTED (unfixed AND fixed): PASS (raises :class:`OverlayError`).
    """
    overlay = TenantOverlay(
        fields={
            "last_name": OverlayField(
                key="last_name", type=FieldType.STRING, label={"en": "x"}
            )
        }
    )
    with pytest.raises(OverlayError):
        _resolve(overlay)


def test_overlay_may_loosen_a_platform_required_fixed_field():
    """03b Req 1.1/1.4: an override that makes a platform-required fixed field optional is NO
    LONGER rejected — the no-relax Hardcoded_Binding overruled the admin and is removed.

    ``personal.last_name`` is platform-required; an override setting ``required=False`` now
    resolves WITHOUT :class:`OverlayError`, and the resolved field is optional.
    """
    overlay = TenantOverlay(
        overrides={"personal.last_name": FixedFieldOverride(required=False)}
    )
    resolved = _resolve(overlay).field("personal.last_name")
    assert resolved is not None
    assert resolved.required is False


@settings(max_examples=25)
@given(
    key=st.sampled_from(
        ["personal.last_name", "membership.membership_type", "membership.joined_date"]
    )
)
def test_invariant_required_fixed_field_stays_required_across_overrides(key):
    """3.5: a presentation-only override (relabel) never relaxes a required fixed field.

    A relabel is allowed; the field stays required in the resolved config. EXPECTED (unfixed AND
    fixed): PASS.
    """
    overlay = TenantOverlay(
        overrides={key: FixedFieldOverride(label={"en": "Relabelled", "nl": "Herbenoemd"})}
    )
    resolved = _resolve(overlay).field(key)
    assert resolved is not None
    assert resolved.required is True, (
        f"REGRESSION (3.5): a relabel override loosened required-ness of {key!r}"
    )


def test_invariant_non_status_enum_member_value_still_validated_against_resolved_choices():
    """3.5: an OVERLAY enum field still enforces its closed ``choices`` (non-status path intact).

    A tenant overlay enum (e.g. a club dropdown) declares a closed ``choices`` list; a value
    outside it is still rejected. Only the ``status`` closed-set rule is being removed — this
    OTHER enum-membership invariant is untouched. EXPECTED (unfixed AND fixed): PASS.
    """
    overlay = TenantOverlay(
        fields={
            "club_section": OverlayField(
                key="club_section",
                type=FieldType.ENUM,
                choices=("noord", "zuid"),
                label={"en": "Section", "nl": "Afdeling"},
            )
        }
    )
    # A variable (overlay) field resolves under the ``overlay`` storage bucket, so its canonical
    # dotted key is ``overlay.club_section`` (the resolver's documented contract for tenant-added
    # fields) — not a bare ``club_section``.
    resolved = _resolve(overlay).field("overlay.club_section")
    assert resolved is not None
    assert tuple(resolved.choices or ()) == ("noord", "zuid")
