"""
S5c Task 4.4 — the resolved-field-surface attributes + authoritative write gates.

Task 4.4 broadens the Members view/edit/add/delete modals over the RESOLVED field set,
sectioned by ``functional_group``, honoring field-level view/edit permissions,
``show_when`` conditional visibility, and value-level role-restricted enum options — with
the domain layer as the authoritative gate (the frontend only presents; R2.3). These tests
pin the two SERVER halves task 4.4 adds:

1. **Serialization** — ``GET /members/field-config`` now surfaces, per resolved field,
   ``functional_group`` (R4.9), ``read_only`` (calculated fields, R4.4), ``show_when``
   (R4.12), ``member_number_format`` (R4.8), and RICH enum ``options`` carrying the
   value-level ``roles`` gate (R4.11/R4.12); plus the top-level ``functional_groups``
   catalog the modals section by.

2. **Authoritative write gates** — a create/edit is rejected by the DOMAIN (not the
   frontend) when it: sets a role-restricted enum value the caller's role may not choose
   (R4.12), or a ``member_number`` that violates the tenant format pattern (R4.8). A field
   hidden by an unmet ``show_when`` is NOT required server-side (R4.12) — the mirror of the
   frontend not rendering/requiring it.

Layering: domain-level tests inject a ``StaticOverlayProvider`` + an in-memory fake repo (no
boto3), reusing the field-config test's fake-catalog pattern; the write-gate tests exercise
``MembershipService`` write methods directly with a tiny in-memory repo so the value-level
gate + format check are pinned without the full edge.

Validates: Requirements 5.5, 4.8, 4.9, 4.11, 4.12
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.field_resolver import (
    FieldResolver,
    FixedFieldOverride,
    FunctionalGroup,
    OverlayField,
    StaticOverlayProvider,
    TenantOverlay,
    evaluate_show_when,
)
from sam.members.domain.field_resolver import _RESERVED_KEYS
from sam.members.domain.fixed_fields import FieldType as _FieldType
from sam.members.domain.fixed_fields import (
    EnumOption,
    FieldType,
    MemberNumberFormat,
)
from sam.members.domain.default_page_size import StaticDefaultPageSizeProvider
from sam.members.domain.membership_service import (
    MembershipService,
    MemberValidationError,
)

# Reuse the field-config test's in-memory fake catalog repo (read-only catalog surface).
from sam.tests.test_field_config_endpoint import FakeCatalogRepository, _entry

# ── Fixtures ──────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def catalog_repo() -> FakeCatalogRepository:
    r = FakeCatalogRepository()
    r.add_type("h-dcn", _entry("h-dcn", "gewoon", label={"nl": "Gewoon lid", "en": "Ordinary"}, order=10))
    r.add_type("h-dcn", _entry("h-dcn", "erelid", label={"nl": "Erelid", "en": "Honorary"}, order=20))
    return r


def _overlay_with_groups_and_options() -> TenantOverlay:
    """A tenant overlay exercising: a functional-group catalog, a role-gated overlay enum, a
    ``show_when``-gated overlay field, and a fixed-field override reassigning a display group +
    setting a ``member_number`` format.
    """
    return TenantOverlay(
        functional_groups={
            "personal": FunctionalGroup(key="personal", label={"nl": "Persoonlijk", "en": "Personal"}, order=1),
            "address": FunctionalGroup(key="address", label={"nl": "Adres", "en": "Address"}, order=2),
            "motor": FunctionalGroup(key="motor", label={"nl": "Motor", "en": "Motor"}, order=3),
            "membership": FunctionalGroup(key="membership", label={"nl": "Lidmaatschap", "en": "Membership"}, order=4),
        },
        fields={
            # A role-gated overlay enum: "premium" restricted to Members_CRUD (R4.12).
            "tier": OverlayField(
                key="tier",
                type=FieldType.ENUM,
                required=False,
                label={"nl": "Niveau", "en": "Tier"},
                options=(
                    EnumOption(value="standard", label={"nl": "Standaard", "en": "Standard"}),
                    EnumOption(value="premium", label={"nl": "Premium", "en": "Premium"}, roles=("Members_CRUD",)),
                ),
                functional_group="membership",
                order=50,
            ),
            # A show_when-gated overlay field: only shown for a "motor"-type membership.
            "motor_brand": OverlayField(
                key="motor_brand",
                type=FieldType.STRING,
                required=True,  # required, BUT only when shown (show_when) — hidden-not-required
                label={"nl": "Motormerk", "en": "Motor brand"},
                functional_group="motor",
                show_when={"membership_type": ["motor"]},
                order=60,
            ),
        },
        overrides={
            "personal.street": FixedFieldOverride(functional_group="address"),
            "membership.member_number": FixedFieldOverride(
                member_number_format=MemberNumberFormat(prefix="Nr-", width=4),
            ),
        },
    )


@pytest.fixture()
def service(catalog_repo) -> MembershipService:
    overlay = _overlay_with_groups_and_options()
    return MembershipService(
        catalog_repo, overlay_provider=StaticOverlayProvider({"h-dcn": overlay})
    )


# ── (1) Serialization on GET /members/field-config ────────────────────────────────────


class TestFieldConfigSurfacesTask44Attributes:
    def test_functional_groups_catalog_present_and_ordered(self, service):
        config = service.get_field_config("h-dcn")
        keys = [g["key"] for g in config["functional_groups"]]
        assert keys == ["personal", "address", "motor", "membership"]  # by `order`
        assert config["functional_groups"][0]["label"] == {"nl": "Persoonlijk", "en": "Personal"}

    def test_every_field_carries_a_functional_group(self, service):
        config = service.get_field_config("h-dcn")
        assert all(f.get("functional_group") for f in config["fields"])
        # The overridden fixed field moved to the "address" display group (storage stays personal).
        street = next(f for f in config["fields"] if f["key"] == "street")
        assert street["group"] == "personal"
        assert street["functional_group"] == "address"

    def test_calculated_fields_are_read_only(self, service):
        config = service.get_field_config("h-dcn")
        calc = [f for f in config["fields"] if f["origin"] == "calculated"]
        assert calc, "expected at least one calculated field"
        assert all(f["read_only"] is True for f in calc)
        # Fixed/variable fields are not read-only.
        street = next(f for f in config["fields"] if f["key"] == "street")
        assert street["read_only"] is False

    def test_role_gated_enum_option_carries_roles(self, service):
        config = service.get_field_config("h-dcn")
        tier = next(f for f in config["fields"] if f["key"] == "tier")
        by_value = {o["value"]: o for o in tier["options"]}
        assert "roles" not in by_value["standard"]          # open option → no roles key
        assert by_value["premium"]["roles"] == ["Members_CRUD"]  # gated option carries its roles
        assert by_value["premium"]["label"] == {"nl": "Premium", "en": "Premium"}

    def test_show_when_condition_surfaced(self, service):
        config = service.get_field_config("h-dcn")
        motor = next(f for f in config["fields"] if f["key"] == "motor_brand")
        assert motor["show_when"] == {"membership_type": ["motor"]}
        assert motor["functional_group"] == "motor"

    def test_member_number_format_surfaced(self, service):
        config = service.get_field_config("h-dcn")
        mn = next(f for f in config["fields"] if f["key"] == "member_number")
        assert mn["member_number_format"]["regex"] == r"^Nr\-\d{4}$"
        assert mn["member_number_format"]["example"] == "Nr-0001"

    def test_field_config_is_json_serializable(self, service):
        json.dumps(service.get_field_config("h-dcn"))  # must not raise


# ── (1b) Phase 2 step (c): the server STOPS serializing view_contexts; keeps default_page_size ─
#
# Phase 2 re-homed the per-context `view_contexts.page_size` to a SINGLE tenant-level
# `default_page_size` scalar on the field-config response (step (a), R2.1). Step (b) stripped
# the SPA's reads of `view_contexts`; GATE CONFIRMED (no client reads it). Step (c) now removes
# the inert `view_contexts` array from the response entirely (R4.1) while KEEPING
# `default_page_size` (the step-(a) home, R4.4), so pagination remains served.
#
# These were the step-(a) ADDITIVITY tests (both keys present). Per the Change-With-Tests
# contract they are MIGRATED to step-(c) reality: `view_contexts` is now ABSENT and
# `default_page_size` is PRESENT — the assertions are FLIPPED to the intended new behaviour,
# never weakened.


class TestFieldConfigDefaultPageSizeStepA:
    def test_default_page_size_present_and_view_contexts_absent_when_authored(
        self, catalog_repo
    ):
        overlay = _overlay_with_groups_and_options()
        service = MembershipService(
            catalog_repo,
            overlay_provider=StaticOverlayProvider({"h-dcn": overlay}),
            default_page_size_provider=StaticDefaultPageSizeProvider({"h-dcn": 50}),
        )
        config = service.get_field_config("h-dcn")
        # Step (c): the authored tenant default is still surfaced (R4.4) …
        assert config["default_page_size"] == 50
        # … and the inert `view_contexts` array is now GONE from the response (R4.1).
        assert "view_contexts" not in config

    def test_default_page_size_none_when_unauthored_view_contexts_absent(self, service):
        # The `service` fixture wires NO default-page-size provider → the empty default
        # resolves every tenant to `None` (empty-is-valid, R2.4): the SPA then falls back to
        # the per-user preference and finally the platform table-toolkit default.
        config = service.get_field_config("h-dcn")
        assert config["default_page_size"] is None
        # `view_contexts` stays absent even with no authored default (R4.1).
        assert "view_contexts" not in config

    def test_default_page_size_is_json_serializable(self, catalog_repo):
        service = MembershipService(
            catalog_repo,
            overlay_provider=StaticOverlayProvider({"h-dcn": _overlay_with_groups_and_options()}),
            default_page_size_provider=StaticDefaultPageSizeProvider({"h-dcn": 25}),
        )
        json.dumps(service.get_field_config("h-dcn"))  # must not raise

    def test_default_page_size_served_without_view_context_surface(self, catalog_repo):
        # R4.1/R4.4: after step (c) the field-config response carries `default_page_size`
        # (the pagination home) and NO `view_contexts` surface, in a SINGLE response that
        # still serializes without raising. This pins the step-(c) contract explicitly: the
        # inert array that `default_page_size` rode alongside at step (a) is gone, pagination
        # stays. (Migrated from the former step-(a) additivity test — the assertions are
        # flipped to the intended new behaviour, not weakened.)
        service = MembershipService(
            catalog_repo,
            overlay_provider=StaticOverlayProvider({"h-dcn": _overlay_with_groups_and_options()}),
            default_page_size_provider=StaticDefaultPageSizeProvider({"h-dcn": 50}),
        )
        config = service.get_field_config("h-dcn")
        assert "default_page_size" in config
        assert config["default_page_size"] == 50
        assert "view_contexts" not in config
        # … and serializing that exact object does not raise.
        round_tripped = json.loads(json.dumps(config))
        assert "default_page_size" in round_tripped
        assert "view_contexts" not in round_tripped


# ── (2) evaluate_show_when unit behavior (shared predicate) ────────────────────────────


class TestEvaluateShowWhen:
    def test_none_or_empty_always_shown(self):
        assert evaluate_show_when(None, {}) is True
        assert evaluate_show_when({}, {}) is True

    def test_scalar_match(self):
        record = {"membership": {"membership_type": "motor"}}
        assert evaluate_show_when({"membership_type": "motor"}, record) is True
        assert evaluate_show_when({"membership_type": "family"}, record) is False

    def test_list_membership(self):
        record = {"membership": {"membership_type": "motor"}}
        assert evaluate_show_when({"membership_type": ["motor", "sport"]}, record) is True
        assert evaluate_show_when({"membership_type": ["family"]}, record) is False

    def test_dotted_key_and_top_level(self):
        record = {"membership": {"membership_type": "motor"}, "flag": "y"}
        assert evaluate_show_when({"membership.membership_type": "motor"}, record) is True
        assert evaluate_show_when({"flag": "y"}, record) is True

    def test_all_conditions_must_hold(self):
        record = {"membership": {"membership_type": "motor"}, "overlay": {"active": "yes"}}
        assert evaluate_show_when({"membership_type": "motor", "active": "yes"}, record) is True
        assert evaluate_show_when({"membership_type": "motor", "active": "no"}, record) is False


# ── (3) Authoritative write gates ──────────────────────────────────────────────────────


class _WritableCatalogRepo(FakeCatalogRepository):
    """The read-only fake catalog repo + a minimal member store so create/update can persist.

    Only the surface the write gates touch is implemented: ``get_member`` / ``save_member``.
    These tests focus on the task-4.4 gates (value-level + format) that run before the persist.
    """

    def __init__(self):
        super().__init__()
        self.members: dict[tuple[str, str], dict] = {}

    def get_membership_type(self, tenant_id, type_code):
        for e in self.catalog.get(tenant_id, []):
            if e.type_code == type_code:
                return e
        return None

    def get_member(self, tenant_id, member_id):
        return self.members.get((tenant_id, member_id))

    def save_member(self, tenant_id, record):
        # Enforce the SAME invariant the real DynamoDbMembersRepository does: a member must carry
        # a non-empty member_id (the real repo raises ValueError otherwise). A fake that silently
        # invented an id here is exactly what let a create-path 502 (missing member_id) reach prod.
        member_id = record.get("member_id")
        if not member_id:
            raise ValueError("member must carry a non-empty 'member_id'")
        self.members[(tenant_id, member_id)] = dict(record)
        return dict(record)


@pytest.fixture()
def write_service() -> MembershipService:
    repo = _WritableCatalogRepo()
    repo.add_type("h-dcn", _entry("h-dcn", "gewoon", order=10))
    repo.add_type("h-dcn", _entry("h-dcn", "motor", order=20))
    overlay = _overlay_with_groups_and_options()
    return MembershipService(repo, overlay_provider=StaticOverlayProvider({"h-dcn": overlay}))


def _create_body(*, member_number="Nr-0001", membership_type="gewoon", **membership_extra):
    # A create body carries NO member_id: it is a SYSTEM-minted uuid (create strips any client
    # value). member_number (Lidnummer) is just a field — no longer the identity (the old
    # "member_id == Lidnummer" conflation is exactly what s5k removes).
    membership = {
        "member_number": member_number,
        "membership_type": membership_type,
        "joined_date": "2024-01-01",
        "status": "active",
        **membership_extra,
    }
    return {
        "personal": {"first_name": "Sam", "last_name": "Jansen", "email": "sam@example.com"},
        "membership": membership,
    }


class TestValueLevelEnumRoleGate:
    def test_open_option_allowed_for_any_caller(self, write_service):
        body = _create_body()
        body["overlay"] = {"tier": "standard"}
        # A caller with no relevant role may still set the open "standard" option.
        created = write_service.create_member("h-dcn", body, {"region": ["*"]}, caller_roles=())
        assert created["overlay"]["tier"] == "standard"

    def test_role_gated_option_rejected_without_role(self, write_service):
        body = _create_body()
        body["overlay"] = {"tier": "premium"}  # restricted to Members_CRUD
        with pytest.raises(MemberValidationError) as exc:
            write_service.create_member("h-dcn", body, {"region": ["*"]}, caller_roles=("Members_Read",))
        assert "overlay.tier" in exc.value.errors

    def test_role_gated_option_allowed_with_role(self, write_service):
        body = _create_body()
        body["overlay"] = {"tier": "premium"}
        created = write_service.create_member("h-dcn", body, {"region": ["*"]}, caller_roles=("Members_CRUD",))
        assert created["overlay"]["tier"] == "premium"


class TestMemberNumberFormatGate:
    def test_matching_member_number_accepted(self, write_service):
        created = write_service.create_member(
            "h-dcn", _create_body(member_number="Nr-0042"), {"region": ["*"]}, caller_roles=("Members_CRUD",)
        )
        assert created["membership"]["member_number"] == "Nr-0042"

    def test_malformed_member_number_rejected(self, write_service):
        with pytest.raises(MemberValidationError) as exc:
            write_service.create_member(
                "h-dcn", _create_body(member_number="BAD1"), {"region": ["*"]}, caller_roles=("Members_CRUD",)
            )
        assert "membership.member_number" in exc.value.errors


class TestShowWhenHiddenNotRequired:
    def test_hidden_required_field_not_demanded(self, write_service):
        # motor_brand is required BUT only shown for membership_type "motor". A "gewoon"
        # member hides it → the create must NOT fail for a missing motor_brand.
        created = write_service.create_member(
            "h-dcn", _create_body(membership_type="gewoon"), {"region": ["*"]}, caller_roles=("Members_CRUD",)
        )
        # member_id is a SYSTEM-minted uuid (the body id is ignored — see TestCreateMintsMemberId).
        assert created["member_id"]

    def test_visible_required_field_still_demanded(self, write_service):
        # A "motor" member SHOWS motor_brand → it is required; omitting it fails (422).
        with pytest.raises(MemberValidationError) as exc:
            write_service.create_member(
                "h-dcn", _create_body(membership_type="motor"), {"region": ["*"]}, caller_roles=("Members_CRUD",)
            )
        assert "overlay.motor_brand" in exc.value.errors

    def test_visible_required_field_satisfied(self, write_service):
        body = _create_body(membership_type="motor")
        body["overlay"] = {"motor_brand": "Honda"}
        created = write_service.create_member("h-dcn", body, {"region": ["*"]}, caller_roles=("Members_CRUD",))
        assert created["overlay"]["motor_brand"] == "Honda"


class TestCreateMintsMemberId:
    """member_id is a SYSTEM-generated uuid; the Lidnummer (member_number) is just a field.

    Regression for a prod 502: ``create_member`` called ``save_member`` with NO ``member_id`` and
    the repository (correctly) rejected it. The fix mints a uuid4 on create. These also pin the
    s5k identity split — ``member_id`` is opaque/internal and is NEVER the human Lidnummer (the old
    "member_id == member_number" conflation is gone).
    """

    def test_create_mints_a_uuid_member_id_when_body_has_none(self, write_service):
        import uuid as _uuid

        created = write_service.create_member(
            "h-dcn", _create_body(member_number="Nr-0007"), {"region": ["*"]},
            caller_roles=("Members_CRUD",),
        )
        mid = created["member_id"]
        # A real uuid4 (parses), and NOT the Lidnummer.
        assert _uuid.UUID(str(mid)).version == 4
        assert mid != created["membership"]["member_number"]
        assert created["membership"]["member_number"] == "Nr-0007"

    def test_create_ignores_a_client_supplied_member_id(self, write_service):
        import uuid as _uuid

        body = _create_body(member_number="Nr-0008")
        body["member_id"] = "hacker-supplied-id"  # must be stripped + replaced (verify-before-trust)
        created = write_service.create_member(
            "h-dcn", body, {"region": ["*"]}, caller_roles=("Members_CRUD",)
        )
        assert created["member_id"] != "hacker-supplied-id"
        assert _uuid.UUID(str(created["member_id"])).version == 4

    def test_two_creates_get_distinct_member_ids(self, write_service):
        a = write_service.create_member(
            "h-dcn", _create_body(member_number="Nr-1001"), {"region": ["*"]},
            caller_roles=("Members_CRUD",),
        )
        b = write_service.create_member(
            "h-dcn", _create_body(member_number="Nr-1002"), {"region": ["*"]},
            caller_roles=("Members_CRUD",),
        )
        assert a["member_id"] != b["member_id"]


# ── (4) Property 4: no view-context surface after step (c), field set unchanged ────────
#
# Phase 2, Property 4 (task 4.2). *For any* tenant (configured or unconfigured), the
# field-config response produced after step (c) carries NO `view_contexts` key and DOES carry
# a `default_page_size` entry, and the resolved field SET it serves is identical to the field
# set the resolver produces for that same overlay (the deletion removed an INERT array, not any
# field — R1.6). We quantify over arbitrary tenants AND arbitrary overlays (varying overlay
# fields + functional groups) to show the invariant is universal, not fixture-specific.
#
# The "field set unchanged" leg is pinned against the resolver directly: the served `fields`
# list is driven SOLELY by `FieldResolver.resolve(...).fields` — `view_contexts` never fed it —
# so the served key set must equal the resolver's key set for the same overlay, with no view
# surface anywhere in the payload.
#
# **Validates: Requirements 4.1, 4.4, 1.6**

_PROP_TENANT_ID = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=24
).filter(lambda s: s.strip() != "")

# A small, resolver-safe set of overlay STRING fields keyed off generated names, each in the
# base `membership` group so the overlay always validates (no dangling functional-group ref).
# An overlay key may NOT collide with a fixed/calculated field key (the resolver rejects that
# as a genuine config bug), so the generator excludes the reserved canonical keys — the
# property is about the SURFACE, not re-proving the collision guard.
_OVERLAY_FIELD_NAME = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12
).filter(lambda s: s.strip() != "" and s not in _RESERVED_KEYS)


@st.composite
def _arbitrary_overlay(draw) -> TenantOverlay:
    """An arbitrary (resolver-safe) tenant overlay: 0..4 plain STRING overlay fields.

    Kept deliberately simple — the property is about the SURFACE (no `view_contexts`, field set
    == resolver's), not about exercising every overlay attribute. Plain string fields in the
    base `membership` group always validate, so the generator never produces an OverlayError.
    """
    names = draw(
        st.lists(_OVERLAY_FIELD_NAME, min_size=0, max_size=4, unique=True)
    )
    fields = {
        name: OverlayField(
            key=name,
            type=_FieldType.STRING,
            required=False,
            label={"nl": name, "en": name},
            functional_group="membership",
            order=100 + i,
        )
        for i, name in enumerate(names)
    }
    return TenantOverlay(fields=fields)


@settings(max_examples=100)
@given(tenant_id=_PROP_TENANT_ID, overlay=_arbitrary_overlay())
def test_property_field_config_has_no_view_context_surface_after_step_c(
    tenant_id, overlay
):
    """Property 4: no `view_contexts` surface; `default_page_size` present; field set unchanged.

    **Validates: Requirements 4.1, 4.4, 1.6**
    """
    repo = FakeCatalogRepository()
    overlay_provider = StaticOverlayProvider({tenant_id: overlay})
    service = MembershipService(repo, overlay_provider=overlay_provider)

    config = service.get_field_config(tenant_id)

    # R4.1 — no view-context surface anywhere in the response.
    assert "view_contexts" not in config
    # R4.4 — pagination remains served (the step-(a) home survives step (c)).
    assert "default_page_size" in config
    # R1.6 — the served field SET is exactly the resolver's field set for this overlay; the
    # inert-array deletion removed no field. Independent resolve → compare key sets AND order.
    resolver = FieldResolver(overlay_provider)
    expected_keys = [f.key for f in resolver.resolve(tenant_id).fields]
    served_keys = [f["key"] for f in config["fields"]]
    assert served_keys == expected_keys
