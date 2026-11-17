"""
Unit tests for the admin surface registry: committed coverage, registry purity,
module admin declarations, the typed-editor exclusion, and the derivation's
equivalence with today's dashboard.

Feature: admin-surface-registry

Requirements: 1.4, 1.6, 2.6, 3.7, 5.3, 6.1-6.3, 7.2-7.4, 9.1-9.4, 11.4
Reference: .kiro/specs/Common/Tenant/admin-surface-registry/design.md
"""

import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services.admin_surface_registry import (
    admin_surface_ids,
    derive_admin_surfaces,
    get_surface,
    module_admin_declaration,
    module_owned_namespaces,
    surfaces_of_kind,
    typed_editor_namespaces,
    typed_editors,
    validate_admin_surface_registry,
)
from services.module_registry import MODULE_REGISTRY, module_backing

# The registry the dashboard must expose (design §8 "Surface reference"), in
# DECLARATION order (the registry groups baseline, panels, capabilities, role).
EXPECTED_IDS = [
    "users",
    "tenant-info",
    "sender",
    "landing",
    "financial",
    "members",
    "functions",
    "pivot",
    "storage",
    "media",
    "templates",
    "advanced",
]

# The platform baseline: surfaces that apply to ANY Tenant_Admin.
EXPECTED_ALWAYS = ["users", "tenant-info", "sender", "landing"]

# Capabilities are driven by admin.consumes, never hardcoded always-on.
EXPECTED_CAPABILITIES = ["functions", "pivot", "storage", "media", "templates"]

# Checked-in mirror of what the module plane expects (steering 36 rule 5): the
# typed editor's namespace + owner are a vocabulary shared across planes, so a
# drift here must fail loudly rather than silently offer the wrong door.
EXPECTED_TYPED_EDITORS = {
    "members": {
        "surface": "members",
        "owner": "module",
        "module": "MEMBERS",
    },
}


def ids_for(*modules, roles=None):
    """Derived surface ids for a module set (helper for readability)."""
    return [s["id"] for s in derive_admin_surfaces(list(modules), list(roles or []))]


class TestCommittedRegistryCoverage:
    """Requirement 1.4 — the registry covers exactly today's dashboard surfaces."""

    def test_exposes_the_twelve_surfaces_in_declaration_order(self):
        assert admin_surface_ids() == EXPECTED_IDS

    def test_kinds_are_assigned_as_designed(self):
        assert [s["id"] for s in surfaces_of_kind("always")] == EXPECTED_ALWAYS
        assert [
            s["id"] for s in surfaces_of_kind("capability")
        ] == EXPECTED_CAPABILITIES
        assert [s["id"] for s in surfaces_of_kind("module")] == ["financial", "members"]
        assert [s["id"] for s in surfaces_of_kind("role")] == ["advanced"]

    def test_every_surface_has_an_order_and_a_label_key(self):
        for surface_id in EXPECTED_IDS:
            surface = get_surface(surface_id)
            assert isinstance(surface["order"], int)
            assert surface["label_key"].startswith("tenantAdmin.tabs.")

    def test_module_surfaces_name_their_owning_module(self):
        assert get_surface("financial")["module"] == "FIN"
        assert get_surface("members")["module"] == "MEMBERS"

    def test_unknown_surface_is_none(self):
        assert get_surface("nope") is None

    def test_committed_registry_validates(self):
        validate_admin_surface_registry()


class TestRegistryPurity:
    """Requirement 1.6 / 11.3-11.4 — pure metadata, safe to import on both planes."""

    def test_every_admin_block_is_json_round_trippable(self):
        for module_name in MODULE_REGISTRY:
            declaration = module_admin_declaration(module_name)
            assert json.loads(json.dumps(declaration)) == declaration

    def test_registry_surface_descriptors_are_json_round_trippable(self):
        for surface_id in admin_surface_ids():
            surface = get_surface(surface_id)
            assert json.loads(json.dumps(surface)) == surface

    def test_every_admin_block_holds_only_primitive_values(self):
        def primitives_only(value):
            if isinstance(value, dict):
                return all(primitives_only(v) for v in value.values())
            if isinstance(value, list):
                return all(primitives_only(v) for v in value)
            return isinstance(value, (str, int, float, bool)) or value is None

        for module_name in MODULE_REGISTRY:
            assert primitives_only(module_admin_declaration(module_name))


class TestModuleAdminDeclarations:
    """Requirements 2.1-2.6, 7.2-7.4 — what each module owns and consumes."""

    def test_every_declared_panel_and_capability_resolves_to_the_right_kind(self):
        for module_name in MODULE_REGISTRY:
            declaration = module_admin_declaration(module_name)
            if "panel" in declaration:
                surface = get_surface(declaration["panel"])
                assert surface["kind"] == "module"
                assert surface["module"] == module_name
            for capability in declaration.get("consumes", []):
                assert get_surface(capability)["kind"] == "capability"
            editor = declaration.get("typed_editor")
            if editor:
                assert get_surface(editor["surface"])["kind"] in ("module", "role")

    def test_the_declared_module_set_is_exactly_what_design_specifies(self):
        declared = {m for m in MODULE_REGISTRY if module_admin_declaration(m)}
        assert declared == {"FIN", "STR", "ZZP", "TENADMIN", "MEMBERS"}

    def test_members_namespace_is_module_owned(self):
        assert typed_editor_namespaces() == ["members"]
        assert module_owned_namespaces() == ["members"]
        assert typed_editors()["members"]["owner"] == "module"

    def test_no_namespace_retains_a_flask_mirror(self):
        # Option B (Members/02 mirror retirement): the Flask-written
        # members.scope_dimensions validator mirror is gone, so no typed editor
        # carries a mirror allowance any more. The key must not even be EXPOSED by
        # typed_editors() — a reintroduced mirror would be a second authoring door.
        for namespace, editor in typed_editors().items():
            assert "flask_mirror_keys" not in editor, namespace

    def test_every_tenant_admin_reaches_advanced(self):
        assert "advanced" in ids_for()
        assert "advanced" in ids_for("FIN", roles=["Tenant_Admin"])
        assert "advanced" in ids_for(roles=["SysAdmin"])


class TestCrossPlaneVocabularyGuard:
    """Requirement 11.4 — the shared owner/namespace vocabulary cannot drift."""

    def test_typed_editors_match_the_checked_in_mirror(self):
        assert typed_editors() == EXPECTED_TYPED_EDITORS

    def test_a_module_owned_namespace_belongs_to_a_module_plane_backed_module(self):
        for editor in typed_editors().values():
            if editor["owner"] == "module":
                assert module_backing(editor["module"]) == "sam"


class TestDerivationEquivalence:
    """Requirement 9 — the derived dashboard matches today's, plus the 4 deltas."""

    def test_tenant_with_no_modules_gets_the_baseline_only(self):
        assert ids_for() == EXPECTED_ALWAYS + ["advanced"]

    def test_fin_only_tenant(self):
        assert ids_for("FIN") == [
            "users",
            "tenant-info",
            "sender",
            "pivot",
            "landing",
            "financial",
            "storage",
            "templates",
            "advanced",
        ]

    def test_members_only_tenant(self):
        assert ids_for("MEMBERS") == [
            "users",
            "tenant-info",
            "sender",
            "landing",
            "members",
            "storage",
            "media",
            "advanced",
        ]

    def test_dual_tenant_gets_both_panels_and_the_capability_union_once(self):
        ids = ids_for("FIN", "MEMBERS")
        assert ids == [
            "users",
            "tenant-info",
            "sender",
            "pivot",
            "landing",
            "financial",
            "members",
            "storage",
            "media",
            "templates",
            "advanced",
        ]
        assert len(ids) == len(set(ids))
        assert ids.count("storage") == 1

    def test_all_committed_modules_derive_every_surface(self):
        ids = ids_for("FIN", "MEMBERS", "STR", "ZZP", "TENADMIN")
        assert sorted(ids) == sorted(EXPECTED_IDS)

    def test_ordering_is_by_order_then_id(self):
        surfaces = derive_admin_surfaces(["FIN", "MEMBERS"], [])
        keys = [(s["order"], s["id"]) for s in surfaces]
        assert keys == sorted(keys)

    def test_delta_1_a_store_nothing_module_gets_no_storage(self):
        # Δ1 (design §Delta): the surface follows the CONSUMPTION, not a fixed list.
        synthetic = {
            "QUIET": {"description": "stores nothing", "admin": {"consumes": ["pivot"]}}
        }
        ids = [
            s["id"]
            for s in derive_admin_surfaces(["QUIET"], [], module_registry=synthetic)
        ]
        assert "storage" not in ids
        assert ids == ["users", "tenant-info", "sender", "pivot", "landing", "advanced"]

    def test_delta_4_a_module_without_an_admin_block_contributes_nothing(self):
        synthetic = {"PLAIN": {"description": "no admin UI"}}
        ids = [
            s["id"]
            for s in derive_admin_surfaces(["PLAIN"], [], module_registry=synthetic)
        ]
        assert ids == EXPECTED_ALWAYS + ["advanced"]

    def test_an_unregistered_module_name_is_ignored(self):
        assert ids_for("GHOST") == EXPECTED_ALWAYS + ["advanced"]


class TestStorageCapabilityVisibility:
    """Requirements 6.1-6.3 — storage is a capability, shown once per consumption."""

    def test_storage_appears_for_a_members_only_tenant(self):
        assert "storage" in ids_for("MEMBERS")

    def test_storage_is_never_duplicated_across_consumers(self):
        assert ids_for("FIN", "MEMBERS", "STR", "ZZP").count("storage") == 1

    def test_storage_is_absent_when_no_entitled_module_consumes_it(self):
        synthetic = {
            "QUIET": {"description": "stores nothing", "admin": {"consumes": []}}
        }
        ids = [
            s["id"]
            for s in derive_admin_surfaces(["QUIET"], [], module_registry=synthetic)
        ]
        assert "storage" not in ids
