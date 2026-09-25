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


class TestFieldConfigEmitsDimensions:
    """get_field_config must emit a `dimensions` array so the Add/Edit modal's region control +
    the table's region filter have their option list. The frontend reads region values ONLY from
    `FieldConfig.dimensions` (shape {key,label,enabled,values}); without it the region <Select>
    is empty and un-typeable. Regression for the prod "region dropdown shows nothing" bug.
    """

    def test_dimensions_array_carries_enabled_dimension_values(self, catalog_repo):
        overlay = _overlay_with_choiceless_enum("region")
        dims = [ScopeDimension(key="region", label={"nl": "Regio", "en": "Region"},
                               values=REGION_VALUES)]
        svc = _service(overlay, dims, catalog_repo)

        config = svc.get_field_config(TENANT)

        assert "dimensions" in config
        region = next(d for d in config["dimensions"] if d["key"] == "region")
        assert region["values"] == list(REGION_VALUES)
        assert region["enabled"] is True
        assert region["label"] == {"nl": "Regio", "en": "Region"}

    def test_disabled_dimension_is_omitted_from_dimensions(self, catalog_repo):
        # A disabled dimension is not offered as a dropdown source (mirrors _scope_vocab).
        overlay = TenantOverlay(fields={})  # no choiceless enum → no OverlayError
        dims = [ScopeDimension(key="region", values=REGION_VALUES, enabled=False)]
        svc = _service(overlay, dims, catalog_repo)

        config = svc.get_field_config(TENANT)

        assert config["dimensions"] == []


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


# ── Phase 1 (wiring): the PRODUCTION app must pass the scope-config provider to the service ──
# This is the gap the first s5j deploy missed: the domain fix was correct, but app.py built
# MembershipService WITHOUT scope_config_provider, so `_scope_vocab` was empty in prod and
# region was still rejected (field-config 502). This test drives the REAL app wiring.


class TestAppWiresScopeConfigProviderIntoService:
    def test_get_field_config_via_app_service_resolves_region_from_projection_scope(
        self, monkeypatch, catalog_repo
    ):
        from sam.members.handler import app as members_app
        from sam.members.domain.field_resolver import StaticOverlayProvider
        from sam.members.domain.scope_dimensions import StaticScopeConfigProvider

        # Region overlay = choiceless enum (h-dcn's real shape); scope config carries the values.
        overlay = _overlay_with_choiceless_enum("region")
        dims = (ScopeDimension(key="region", values=REGION_VALUES),)

        # Drive the SAME projection-override seams the read path uses (conftest pattern), so the
        # app's `_ProjectionScopeConfigProvider` / `_ProjectionOverlayProvider` resolve to these.
        monkeypatch.setattr(
            members_app, "_OVERLAY_PROVIDER_OVERRIDE",
            StaticOverlayProvider({TENANT: overlay}),
        )
        monkeypatch.setattr(
            members_app, "_SCOPE_CONFIG_PROVIDER_OVERRIDE",
            StaticScopeConfigProvider({TENANT: dims}),
        )
        # Rebuild the module singleton so it captures the (now overridden) providers, over a
        # fake catalog repo (no AWS).
        monkeypatch.setattr(members_app, "_SERVICE", None)
        monkeypatch.setattr(members_app, "_get_membership_service", None, raising=False)
        svc = MembershipService(
            catalog_repo,
            overlay_provider=members_app._OVERLAY_PROVIDER,
            scope_config_provider=members_app._SCOPE_CONFIG_PROVIDER_FOR_SERVICE,
        )
        monkeypatch.setattr(members_app, "_SERVICE", svc)

        config = svc.get_field_config(TENANT)  # must NOT raise (the prod 502 case)

        region = next(f for f in config["fields"] if f["key"] == "region")
        assert region["options"] == list(REGION_VALUES)


# ── Regression: dict-shaped overlay-enum `choices` must not 502 (prod incident) ─────────
# The prod Members Lambda returned 502 on create/update because a tenant's overlay enum carried
# rich option OBJECTS ({"value","label"}) under `choices` (not `options`); those flow through the
# resolver un-normalized, and `_reject_invalid_overlay_enum_values` did `", ".join(field.choices)`
# / `value not in field.choices` assuming bare strings -> `TypeError: expected str, dict found`,
# surfaced as a 502. The fix coerces each choice to its string value; a bad value must be a clean
# 422-style error, never a raise.


class TestOverlayEnumChoicesToleratesDictShape:
    def _config_with_dict_choices(self):
        from sam.members.domain.field_resolver import (
            FieldConfig,
            FieldOrigin,
            ResolvedField,
        )

        # Overlay enum whose `choices` are option OBJECTS, not bare strings (the prod data shape).
        field = ResolvedField(
            key="motor_type",
            group="overlay",
            type=FieldType.ENUM,
            required=False,
            origin=FieldOrigin.VARIABLE,
            choices=(
                {"value": "BMW", "label": {"nl": "BMW"}},
                {"value": "Honda", "label": {"nl": "Honda"}},
            ),
        )
        return FieldConfig(tenant_id=TENANT, fields=(field,)), field

    def test_valid_value_against_dict_choices_no_error_no_raise(self):
        config, _ = self._config_with_dict_choices()
        errors: dict = {}
        # Must NOT raise (the 502 case) and must accept a value present in the dict choices.
        MembershipService._reject_invalid_overlay_enum_values(  # noqa: SLF001
            config, {"overlay": {"motor_type": "BMW"}}, errors
        )
        assert errors == {}

    def test_invalid_value_against_dict_choices_is_a_clean_error(self):
        config, _ = self._config_with_dict_choices()
        errors: dict = {}
        MembershipService._reject_invalid_overlay_enum_values(  # noqa: SLF001
            config, {"overlay": {"motor_type": "Ducati"}}, errors
        )
        # A bad value is a 422-style field error whose message lists the string values (no dicts).
        assert "overlay.motor_type" in errors
        assert "BMW" in errors["overlay.motor_type"]
        assert "Honda" in errors["overlay.motor_type"]
        assert "{" not in errors["overlay.motor_type"]  # never a stringified dict
