"""
S5j Phase 1/2 — scope-dimension-sourced dropdown choices (design D1a) + the change-gated
overlay-enum validation activating for a scope-dimension field.

The structural fix: an OVERLAY ``enum`` field with NO inline ``choices`` whose key matches an
ENABLED scope dimension's ``field`` gets its ``choices`` filled from that dimension's ``values``
at field-config resolve time. ``scope_dimensions.values`` stays the single source of truth (no
stored duplication, no data migration). h-dcn's ``region`` is exactly this case; today it makes
``GET /members/field-config`` raise ``OverlayError`` (→ 502).

These tests inject a ``StaticOverlayProvider`` + ``StaticScopeConfigProvider`` + an in-memory
fake catalog repo (no boto3), reusing the field-config test's fake-catalog pattern.

Test naming: ``test_{function}_{scenario}_{expected}`` (steering 34).
"""

from __future__ import annotations

import pytest

from sam.members.domain.field_resolver import (
    OverlayField,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import FieldType
from sam.members.domain.membership_service import (
    MembershipService,
    MemberValidationError,
)
from sam.members.domain.scope_dimensions import (
    ScopeDimension,
    StaticScopeConfigProvider,
)

# Reuse the field-config test's in-memory fake catalog repo (read-only catalog surface).
from sam.tests.test_field_config_endpoint import FakeCatalogRepository, _entry


TENANT = "h-dcn"
REGION_VALUES = (
    "Brabant/Zeeland",
    "Duitsland",
    "Friesland",
    "Geen",
    "Groningen/Drenthe",
    "Limburg",
    "Noord Holland",
    "Oost",
    "Utrecht",
    "Zuid Holland",
)


# ── Fixtures ──────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def catalog_repo() -> FakeCatalogRepository:
    r = FakeCatalogRepository()
    r.add_type(TENANT, _entry(TENANT, "gewoon", label={"nl": "Gewoon", "en": "Ordinary"}, order=10))
    return r


def _overlay_with_choiceless_enum(field_key: str) -> TenantOverlay:
    """An overlay whose only variable field is an ``enum`` with NO inline choices — exactly the
    shape of h-dcn's ``region`` (and the shape the resolver rejects today)."""
    return TenantOverlay(
        fields={
            field_key: OverlayField(
                key=field_key,
                type=FieldType.ENUM,
                required=False,
                label={"nl": "Regio", "en": "Region"},
                functional_group="membership",
                order=10,
            ),
        }
    )


def _service(overlay: TenantOverlay, dimensions, catalog_repo) -> MembershipService:
    """Build a service with the overlay + a scope config provider carrying ``dimensions``.

    NOTE (S5j): passing a ``scope_config_provider`` to MembershipService is the wiring this
    spec introduces. Until Phase 1.2 lands, this kwarg does not exist / is not consumed and
    these tests fail — that is the intended RED state.
    """
    return MembershipService(
        catalog_repo,
        overlay_provider=StaticOverlayProvider({TENANT: overlay}),
        scope_config_provider=StaticScopeConfigProvider({TENANT: tuple(dimensions)}),
    )


def _field(config: dict, key: str) -> dict:
    return next(f for f in config["fields"] if f["key"] == key)


# ── Phase 1 (R1/R2): resolve sources choices from the scope dimension ─────────────────


class TestScopeDimensionSourcesChoices:
    def test_get_field_config_region_enum_without_choices_resolves_and_gets_dimension_values(
        self, catalog_repo
    ):
        # h-dcn's real case: region is a choiceless enum; the region dimension carries values.
        overlay = _overlay_with_choiceless_enum("region")
        dims = [ScopeDimension(key="region", values=REGION_VALUES, required_for=("Members_CRUD",))]
        svc = _service(overlay, dims, catalog_repo)

        config = svc.get_field_config(TENANT)  # was: raises OverlayError (→ 502)

        # In the SERIALIZED field-config a bare `choices` list is emitted under `options`
        # (the frontend's dropdown-source key; rich enum options use the same key).
        region = _field(config, "region")
        assert region["options"] == list(REGION_VALUES)

    def test_get_field_config_dimension_field_differs_from_key_choices_land_on_field(
        self, catalog_repo
    ):
        # The dimension is NAMED "home_region" but BINDS to the member field "woonregio".
        # Choices must land on the field named by `.field`, not `.key` (R1.1).
        overlay = _overlay_with_choiceless_enum("woonregio")
        dims = [
            ScopeDimension(key="home_region", field="woonregio", values=REGION_VALUES)
        ]
        svc = _service(overlay, dims, catalog_repo)

        config = svc.get_field_config(TENANT)

        field = _field(config, "woonregio")
        assert field["options"] == list(REGION_VALUES)

    def test_get_field_config_multiple_dimensions_fill_multiple_fields(self, catalog_repo):
        # Two enabled dimensions binding two different choiceless overlay enums → BOTH filled.
        overlay = TenantOverlay(
            fields={
                "region": OverlayField(
                    key="region", type=FieldType.ENUM, label={"nl": "Regio", "en": "Region"},
                    functional_group="membership", order=10,
                ),
                "team": OverlayField(
                    key="team", type=FieldType.ENUM, label={"nl": "Team", "en": "Team"},
                    functional_group="membership", order=20,
                ),
            }
        )
        dims = [
            ScopeDimension(key="region", values=REGION_VALUES),
            ScopeDimension(key="team", values=("A", "B", "C")),
        ]
        svc = _service(overlay, dims, catalog_repo)

        config = svc.get_field_config(TENANT)

        assert _field(config, "region")["options"] == list(REGION_VALUES)
        assert _field(config, "team")["options"] == ["A", "B", "C"]

    def test_get_field_config_non_dimension_enum_without_choices_still_raises(self, catalog_repo):
        # CONTROL (R1.4): a choiceless enum that is NOT a scope dimension is still a config bug.
        overlay = _overlay_with_choiceless_enum("motor_brand")  # not a dimension
        dims = [ScopeDimension(key="region", values=REGION_VALUES)]
        svc = _service(overlay, dims, catalog_repo)

        with pytest.raises(Exception):  # OverlayError surfaces the genuine misconfig
            svc.get_field_config(TENANT)

    def test_get_field_config_disabled_dimension_does_not_source_choices(self, catalog_repo):
        # A DISABLED dimension must not source choices → the choiceless enum stays invalid.
        overlay = _overlay_with_choiceless_enum("region")
        dims = [ScopeDimension(key="region", values=REGION_VALUES, enabled=False)]
        svc = _service(overlay, dims, catalog_repo)

        with pytest.raises(Exception):
            svc.get_field_config(TENANT)


# ── Phase 2 (R3): the change-gated overlay-enum validation activates for region ───────


def _member(region_value):
    """A minimal member record carrying the overlay.region value under the overlay bucket."""
    return {
        "personal": {
            "first_name": "Test",
            "last_name": "Member",
            "email": "t@example.com",
        },
        "membership": {"membership_type": "gewoon"},
        "overlay": {"region": region_value},
    }


class TestRegionChangeGatedValidation:
    """Once region has resolved choices, MembershipService._reject_invalid_overlay_enum_values
    fires for it: enforce on create/change, tolerate an unchanged legacy value (R3.2/R3.3).
    These prove the EXISTING rule now covers region; they add no new logic.
    """

    @pytest.fixture()
    def svc(self, catalog_repo) -> MembershipService:
        overlay = _overlay_with_choiceless_enum("region")
        dims = [ScopeDimension(key="region", values=REGION_VALUES)]
        return _service(overlay, dims, catalog_repo)

    def test_reject_invalid_overlay_enum_values_create_region_in_values_ok(self, svc):
        from sam.members.domain.membership_service import MembershipService as MS

        config = svc.get_field_config(TENANT)
        # Rebuild a ResolvedFieldConfig-like path is internal; drive via the write validator.
        errors: dict = {}
        # Access the resolved config object (not the serialized dict) via the resolver.
        resolved = svc._field_resolver.resolve(TENANT, scope_vocab=svc._scope_vocab(TENANT))  # noqa: SLF001
        MS._reject_invalid_overlay_enum_values(resolved, _member("Oost"), errors)
        assert errors == {}

    def test_reject_invalid_overlay_enum_values_create_region_not_in_values_errors(self, svc):
        from sam.members.domain.membership_service import MembershipService as MS

        resolved = svc._field_resolver.resolve(TENANT, scope_vocab=svc._scope_vocab(TENANT))  # noqa: SLF001
        errors: dict = {}
        MS._reject_invalid_overlay_enum_values(resolved, _member("Atlantis"), errors)
        assert "overlay.region" in errors

    def test_reject_invalid_overlay_enum_values_update_unchanged_legacy_ok(self, svc):
        from sam.members.domain.membership_service import MembershipService as MS

        resolved = svc._field_resolver.resolve(TENANT, scope_vocab=svc._scope_vocab(TENANT))  # noqa: SLF001
        legacy = _member("Groningen/Drente")  # old spelling, not in the current values
        errors: dict = {}
        MS._reject_invalid_overlay_enum_values(
            resolved, legacy, errors, previous=legacy
        )
        assert errors == {}  # unchanged legacy value tolerated

    def test_reject_invalid_overlay_enum_values_update_change_to_invalid_errors(self, svc):
        from sam.members.domain.membership_service import MembershipService as MS

        resolved = svc._field_resolver.resolve(TENANT, scope_vocab=svc._scope_vocab(TENANT))  # noqa: SLF001
        previous = _member("Oost")
        changed = _member("Atlantis")
        errors: dict = {}
        MS._reject_invalid_overlay_enum_values(
            resolved, changed, errors, previous=previous
        )
        assert "overlay.region" in errors

    def test_reject_invalid_overlay_enum_values_update_legacy_to_valid_ok(self, svc):
        from sam.members.domain.membership_service import MembershipService as MS

        resolved = svc._field_resolver.resolve(TENANT, scope_vocab=svc._scope_vocab(TENANT))  # noqa: SLF001
        previous = _member("Groningen/Drente")  # legacy
        changed = _member("Groningen/Drenthe")  # corrected, in values
        errors: dict = {}
        MS._reject_invalid_overlay_enum_values(
            resolved, changed, errors, previous=previous
        )
        assert errors == {}
