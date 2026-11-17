"""
Property-based tests for the admin surface registry and its derivation.

Feature: admin-surface-registry
Properties: 1-6 (soundness/completeness/order/purity/capability/registry
integrity), 11 (plane fidelity), 12 (plane-agnostic metadata).

Requirements: 1.3, 1.5, 2.6, 3.1-3.6, 3.8, 6.1-6.2, 7.2/7.5/7.7, 11.1-11.4
Reference: .kiro/specs/Common/Tenant/admin-surface-registry/design.md
"""

import copy
import importlib
import json
import os
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services.admin_surface_registry import (
    ADMIN_SURFACE_REGISTRY,
    VALID_KINDS,
    VALID_OWNERS,
    derive_admin_surfaces,
    flask_mirror_keys,
    module_owned_namespaces,
    surfaces_of_kind,
    typed_editors,
    validate_admin_surface_registry,
)
from services.module_registry import MODULE_REGISTRY

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

KNOWN_MODULES = ["FIN", "STR", "ZZP", "TENADMIN", "MEMBERS"]

module_name_st = st.sampled_from(KNOWN_MODULES + ["GHOST_LEGACY"])
entitled_modules_st = st.lists(module_name_st, max_size=5, unique=True)
role_st = st.sampled_from(["Tenant_Admin", "SysAdmin", "Members_CRUD"])
user_roles_st = st.lists(role_st, max_size=3, unique=True)
capability_st = st.sampled_from(["functions", "pivot", "storage", "media", "templates"])


def _applicable_ids(registry, module_registry, entitled, roles):
    """Independent re-implementation of the design §3 applicability rule."""
    consumed = set()
    for module_name in entitled:
        declaration = (module_registry.get(module_name) or {}).get("admin") or {}
        consumed.update(declaration.get("consumes") or [])

    applicable = []
    for surface_id, descriptor in registry.items():
        kind = descriptor.get("kind")
        if kind == "always":
            applies = True
        elif kind == "module":
            applies = descriptor.get("module") in entitled
        elif kind == "capability":
            applies = surface_id in consumed
        elif kind == "role":
            required = descriptor.get("required_roles") or []
            applies = not required or bool(set(required) & set(roles))
        else:
            applies = False
        if applies:
            applicable.append(surface_id)
    return sorted(applicable)


def _full_module_registry(partial):
    """Merge a partial admin override over the real MODULE_REGISTRY."""

    merged = {name: dict(entry) for name, entry in MODULE_REGISTRY.items()}
    for name, entry in partial.items():
        merged.setdefault(name, {})
        merged[name] = dict(merged[name])
        merged[name]["admin"] = entry.get("admin")
    return merged


# ---------------------------------------------------------------------------
# Properties 1 + 2 — derivation soundness and completeness
# ---------------------------------------------------------------------------


class TestDerivationSoundnessAndCompleteness:
    """Every returned surface satisfies its rule; no applicable surface is omitted."""

    @settings(max_examples=100, deadline=None)
    @given(entitled=entitled_modules_st, roles=user_roles_st)
    def test_output_equals_the_applicability_rule(self, entitled, roles):
        derived = [s["id"] for s in derive_admin_surfaces(entitled, roles)]
        expected = _applicable_ids(
            ADMIN_SURFACE_REGISTRY, MODULE_REGISTRY, entitled, roles
        )
        assert sorted(derived) == expected

    @settings(max_examples=100, deadline=None)
    @given(entitled=entitled_modules_st, roles=user_roles_st)
    def test_every_returned_surface_has_a_valid_reason(self, entitled, roles):
        consumed = set()
        for module_name in entitled:
            declaration = (MODULE_REGISTRY.get(module_name) or {}).get("admin") or {}
            consumed.update(declaration.get("consumes") or [])

        for surface in derive_admin_surfaces(entitled, roles):
            if surface["kind"] == "module":
                assert surface["module"] in entitled
            elif surface["kind"] == "capability":
                assert surface["id"] in consumed
            elif surface["kind"] == "role":
                required = surface.get("required_roles") or []
                assert not required or set(required) & set(roles)


# ---------------------------------------------------------------------------
# Property 3 — uniqueness and ordering
# ---------------------------------------------------------------------------


class TestUniquenessAndOrdering:
    """Each surface appears at most once, ordered by (order, id)."""

    @settings(max_examples=100, deadline=None)
    @given(entitled=entitled_modules_st, roles=user_roles_st)
    def test_ids_are_unique_and_sorted(self, entitled, roles):
        derived = derive_admin_surfaces(entitled, roles)
        ids = [s["id"] for s in derived]
        assert len(ids) == len(set(ids))
        keys = [(s["order"], s["id"]) for s in derived]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Property 4 — purity and determinism
# ---------------------------------------------------------------------------


class TestPurityAndDeterminism:
    """Equal inputs give equal output; no environment or clock influence."""

    @settings(max_examples=100, deadline=None)
    @given(entitled=entitled_modules_st, roles=user_roles_st)
    def test_repeated_calls_are_equal(self, entitled, roles):
        first = derive_admin_surfaces(entitled, roles)
        second = derive_admin_surfaces(list(entitled), list(roles))
        assert first == second

    @settings(max_examples=50, deadline=None)
    @given(entitled=entitled_modules_st)
    def test_input_lists_are_not_mutated(self, entitled):
        original = list(entitled)
        derive_admin_surfaces(entitled, ["Tenant_Admin"])
        assert entitled == original


# ---------------------------------------------------------------------------
# Property 5 — capability follows consumption, not a fixed list
# ---------------------------------------------------------------------------


class TestCapabilityFollowsConsumption:
    """`storage` appears iff an entitled module declares it consumes storage."""

    @settings(max_examples=100, deadline=None)
    @given(
        declarations=st.lists(
            st.tuples(st.sampled_from(["M1", "M2", "M3"]), st.booleans()),
            max_size=3,
            unique_by=lambda pair: pair[0],
        )
    )
    def test_storage_presence_tracks_consumption(self, declarations):
        synthetic = {}
        expects_storage = False
        for name, consumes_storage in declarations:
            synthetic[name] = {
                "admin": {"consumes": ["storage"] if consumes_storage else ["pivot"]}
            }
            expects_storage = expects_storage or consumes_storage

        ids = [
            s["id"]
            for s in derive_admin_surfaces(
                [name for name, _ in declarations], [], module_registry=synthetic
            )
        ]
        assert ("storage" in ids) is expects_storage


# ---------------------------------------------------------------------------
# Property 6 — registry integrity fails loud
# ---------------------------------------------------------------------------


class TestRegistryIntegrityFailsLoud:
    """Any mutated registry / declaration raises ValueError; committed ones do not."""

    def test_committed_registry_validates(self):
        validate_admin_surface_registry()

    @settings(max_examples=50, deadline=None)
    @given(
        bad_kind=st.text(min_size=1, max_size=12).filter(lambda k: k not in VALID_KINDS)
    )
    def test_invalid_kind_is_rejected(self, bad_kind):
        registry = copy.deepcopy(ADMIN_SURFACE_REGISTRY)
        registry["users"]["kind"] = bad_kind
        with pytest.raises(ValueError, match="users"):
            validate_admin_surface_registry(registry=registry)

    @settings(max_examples=50, deadline=None)
    @given(bad_order=st.one_of(st.text(min_size=1, max_size=4), st.none()))
    def test_non_integer_order_is_rejected(self, bad_order):
        registry = copy.deepcopy(ADMIN_SURFACE_REGISTRY)
        registry["users"]["order"] = bad_order
        with pytest.raises(ValueError, match="users"):
            validate_admin_surface_registry(registry=registry)

    @settings(max_examples=50, deadline=None)
    @given(
        bad_label=st.text(min_size=1, max_size=20).filter(
            lambda s: not s.startswith("tenantAdmin.tabs.")
        )
    )
    def test_bad_label_key_is_rejected(self, bad_label):
        registry = copy.deepcopy(ADMIN_SURFACE_REGISTRY)
        registry["users"]["label_key"] = bad_label
        with pytest.raises(ValueError, match="users"):
            validate_admin_surface_registry(registry=registry)

    def test_module_surface_naming_an_unknown_module_is_rejected(self):
        registry = copy.deepcopy(ADMIN_SURFACE_REGISTRY)
        registry["financial"]["module"] = "NOT_A_MODULE"
        with pytest.raises(ValueError, match=r"financial"):
            validate_admin_surface_registry(registry=registry)

    def test_unknown_consumes_capability_is_rejected(self):
        registry = copy.deepcopy(ADMIN_SURFACE_REGISTRY)
        module_registry = {"FIN": {"admin": {"consumes": ["not-a-surface"]}}}
        with pytest.raises(ValueError, match=r"not-a-surface"):
            validate_admin_surface_registry(
                registry=registry,
                module_registry=_full_module_registry(module_registry),
            )

    def test_panel_of_the_wrong_kind_is_rejected(self):
        registry = copy.deepcopy(ADMIN_SURFACE_REGISTRY)
        module_registry = {"FIN": {"admin": {"panel": "storage"}}}
        with pytest.raises(ValueError, match=r"FIN"):
            validate_admin_surface_registry(
                registry=registry,
                module_registry=_full_module_registry(module_registry),
            )

    def test_panel_owned_by_another_module_is_rejected(self):
        registry = copy.deepcopy(ADMIN_SURFACE_REGISTRY)
        module_registry = {"STR": {"admin": {"panel": "financial"}}}
        with pytest.raises(ValueError, match=r"STR"):
            validate_admin_surface_registry(
                registry=registry,
                module_registry=_full_module_registry(module_registry),
            )

    def test_duplicate_typed_namespace_is_rejected(self):
        registry = copy.deepcopy(ADMIN_SURFACE_REGISTRY)
        editor = {"namespace": "shared", "surface": "members", "owner": "module"}
        module_registry = {
            "MEMBERS": {
                "backing": {"kind": "sam"},
                "admin": {"typed_editor": dict(editor)},
            },
            "STR": {"admin": {"typed_editor": dict(editor)}},
        }
        with pytest.raises(ValueError, match=r"shared"):
            validate_admin_surface_registry(
                registry=registry,
                module_registry=_full_module_registry(module_registry),
            )

    def test_invalid_owner_is_rejected(self):
        registry = copy.deepcopy(ADMIN_SURFACE_REGISTRY)
        module_registry = {
            "MEMBERS": {
                "backing": {"kind": "sam"},
                "admin": {
                    "typed_editor": {
                        "namespace": "ns",
                        "surface": "members",
                        "owner": "nope",
                    }
                },
            }
        }
        with pytest.raises(ValueError, match=r"nope"):
            validate_admin_surface_registry(
                registry=registry,
                module_registry=_full_module_registry(module_registry),
            )

    def test_module_plane_editor_on_a_flask_module_is_rejected(self):
        registry = copy.deepcopy(ADMIN_SURFACE_REGISTRY)
        module_registry = {
            "FIN": {
                "admin": {
                    "typed_editor": {
                        "namespace": "ns",
                        "surface": "financial",
                        "owner": "module",
                    }
                }
            }
        }
        with pytest.raises(ValueError, match=r"FIN"):
            validate_admin_surface_registry(
                registry=registry,
                module_registry=_full_module_registry(module_registry),
            )

    def test_unknown_typed_editor_surface_is_rejected(self):
        registry = copy.deepcopy(ADMIN_SURFACE_REGISTRY)
        module_registry = {
            "MEMBERS": {
                "backing": {"kind": "sam"},
                "admin": {
                    "typed_editor": {
                        "namespace": "ns",
                        "surface": "ghost",
                        "owner": "module",
                    }
                },
            }
        }
        with pytest.raises(ValueError, match=r"ghost"):
            validate_admin_surface_registry(
                registry=registry,
                module_registry=_full_module_registry(module_registry),
            )

    def test_mirror_keys_on_a_flask_owned_namespace_are_rejected(self):
        registry = copy.deepcopy(ADMIN_SURFACE_REGISTRY)
        module_registry = {
            "FIN": {
                "admin": {
                    "typed_editor": {
                        "namespace": "ns",
                        "surface": "financial",
                        "owner": "flask",
                        "flask_mirror_keys": ["something"],
                    }
                }
            }
        }
        with pytest.raises(ValueError, match=r"ns"):
            validate_admin_surface_registry(
                registry=registry,
                module_registry=_full_module_registry(module_registry),
            )


# ---------------------------------------------------------------------------
# Property 11 — plane fidelity: no editor touches the wrong store
# ---------------------------------------------------------------------------


class TestPlaneFidelity:
    """Advanced is a Flask editor: it never emits a module-owned namespace."""

    def test_advanced_never_emits_a_module_owned_namespace(self):
        module_owned = set(module_owned_namespaces())
        assert "members" in module_owned
        # A module-owned namespace is never registered as a capability or role
        # surface, so the Flask Advanced editor has nothing to offer for it; it is
        # edited solely through its owning module's typed editor (the module panel).
        # The namespace name doubles as its module PANEL's id. That panel is a
        # `module` surface (the namespace's single editing door) — never a capability
        # and never the role-gated Advanced (Flask parameters) editor.
        capability_ids = {s["id"] for s in surfaces_of_kind("capability")}
        for namespace in module_owned:
            assert ADMIN_SURFACE_REGISTRY[namespace]["kind"] == "module"
            assert namespace not in capability_ids
        for entitled in (
            ["MEMBERS"],
            ["FIN", "MEMBERS"],
            ["FIN", "MEMBERS", "STR", "TENADMIN"],
        ):
            derived = {
                s["id"]: s for s in derive_admin_surfaces(entitled, ["Tenant_Admin"])
            }
            assert "advanced" in derived
            for namespace in module_owned:
                surface = derived.get(namespace)
                if surface is not None:
                    # the only surface a module-owned namespace appears as is its own
                    # module panel, never the Advanced (Flask parameters) editor
                    assert surface["kind"] == "module"

    def test_every_typed_editor_targets_a_registered_surface_of_the_right_kind(self):
        for editor in typed_editors().values():
            assert editor["surface"] in ADMIN_SURFACE_REGISTRY
            assert editor["owner"] in VALID_OWNERS

    def test_only_module_owned_namespaces_may_declare_a_flask_mirror(self):
        for namespace, editor in typed_editors().items():
            if flask_mirror_keys(namespace):
                assert editor["owner"] == "module"

    def test_flask_owned_namespaces_have_no_mirror_and_are_not_excluded(self):
        for namespace in ("storage", "str", "fin", "zzp"):
            assert flask_mirror_keys(namespace) == []
            assert namespace not in module_owned_namespaces()

    @settings(max_examples=50, deadline=None)
    @given(
        namespace=st.text(min_size=1, max_size=12),
        owner=st.sampled_from(VALID_OWNERS),
    )
    def test_generated_typed_editor_targets_match_the_declared_owner(
        self, namespace, owner
    ):
        # Generate both owner planes. A module-plane editor must land on a module
        # panel; a Flask editor lands on the generic role (Advanced) surface.
        surface_id = "members" if owner == "module" else "advanced"
        module_registry = {
            "MEMBERS": {
                "backing": {"kind": "sam"},
                "admin": {
                    "typed_editor": {
                        "namespace": namespace,
                        "surface": surface_id,
                        "owner": owner,
                    }
                },
            }
        }
        registry = copy.deepcopy(ADMIN_SURFACE_REGISTRY)
        validate_admin_surface_registry(
            registry=registry,
            module_registry=_full_module_registry(module_registry),
        )
        expected_kind = "module" if owner == "module" else "role"
        assert registry[surface_id]["kind"] == expected_kind


# ---------------------------------------------------------------------------
# Property 12 — the registry is plane-agnostic metadata
# ---------------------------------------------------------------------------


class TestRegistryIsPlaneAgnosticMetadata:
    """Importable with no DB/credentials; every admin block is JSON-safe."""

    def test_import_does_not_touch_a_database_or_credentials(self):
        # The unit-test conftest blocks real MySQL connections, so a successful
        # import here proves no store access happens at import time.
        module = importlib.import_module("services.admin_surface_registry")
        assert module.ADMIN_SURFACE_REGISTRY

    def test_every_admin_block_survives_a_json_round_trip(self):
        for module_name in MODULE_REGISTRY:
            declaration = MODULE_REGISTRY[module_name].get("admin") or {}
            assert json.loads(json.dumps(declaration)) == declaration

    def test_every_surface_descriptor_survives_a_json_round_trip(self):
        for descriptor in ADMIN_SURFACE_REGISTRY.values():
            assert json.loads(json.dumps(descriptor)) == descriptor

    def test_admin_blocks_hold_only_primitive_values(self):
        def primitives_only(value):
            if isinstance(value, dict):
                return all(primitives_only(v) for v in value.values())
            if isinstance(value, list):
                return all(primitives_only(v) for v in value)
            return isinstance(value, (str, int, float, bool)) or value is None

        for module_name in MODULE_REGISTRY:
            declaration = MODULE_REGISTRY[module_name].get("admin") or {}
            assert primitives_only(declaration)


# ---------------------------------------------------------------------------
# Typed-editor exclusion set (Requirements 7.2-7.4)
# ---------------------------------------------------------------------------


class TestTypedEditorExclusion:
    """The Advanced exclusion set is derived from the registry, not hardcoded."""

    def test_members_is_the_only_excluded_namespace_today(self):
        assert module_owned_namespaces() == ["members"]

    def test_exclusion_set_matches_the_declared_owners(self):
        expected = sorted(
            ns for ns, editor in typed_editors().items() if editor["owner"] == "module"
        )
        assert module_owned_namespaces() == expected
