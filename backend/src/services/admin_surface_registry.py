"""
Admin Surface Registry: the single in-code source of truth for the Tenant-Admin
dashboard's surfaces (tabs), plus the pure derivation that decides which of them
apply to a tenant.

Every surface declares WHEN it applies:

    always      platform baseline for any Tenant_Admin
    module      config owned by exactly one module (FIN -> financial, MEMBERS -> members)
    capability  a cross-cutting surface that SERVES modules; applies when any
                entitled module declares it consumes the capability (admin.consumes)
    role        a role-gated generic surface (Advanced = the raw Flask parameters editor)

Modules declare what they own and consume in their MODULE_REGISTRY entry::

    "admin": {
        "panel": "financial",
        "consumes": ["storage", "templates", "pivot"],
        "typed_editor": {"namespace": "members", "surface": "members", "owner": "module"},
    }

Config ownership (``owner``) is a property of a NAMESPACE, not a taxonomy of planes:
``flask`` means the namespace lives in the MySQL ``parameters`` table; ``module`` means
it lives as a ``config#*`` row on the DynamoDB governance projection, written by the
owning module's Change-Op path. The generic Advanced surface therefore covers only
``flask``-owned namespaces.

This module is PURE METADATA: it reads no store, imports no plane-specific code
(only the shared ``MODULE_REGISTRY`` dict), and is importable from both planes.

Requirements: 1.1-1.5, 2.6, 3.1-3.8, 7.1-7.8, 8.1, 11.3-11.4
Reference: .kiro/specs/Common/Tenant/admin-surface-registry/design.md
"""

import logging
from typing import Literal, TypedDict

from services.module_registry import MODULE_REGISTRY, module_backing_or_none

logger = logging.getLogger(__name__)

SurfaceKind = Literal["always", "module", "capability", "role"]

VALID_KINDS: tuple = ("always", "module", "capability", "role")
VALID_OWNERS: tuple = ("flask", "module")
LABEL_KEY_PREFIX = "tenantAdmin.tabs."


class AdminSurface(TypedDict, total=False):
    """One addressable area of the Tenant-Admin dashboard (a tab).

    Registry entries are keyed by ``id``; ``get_surface`` / ``derive_admin_surfaces``
    fill ``id`` in on the copy they return, so callers never rely on the key name.
    """

    id: str
    kind: str  # one of VALID_KINDS
    order: int
    label_key: str  # i18n key under tenantAdmin.tabs.*
    module: str  # kind == "module": the owning MODULE_REGISTRY key
    required_roles: list  # kind == "role": any-of; empty list == no extra gate


ADMIN_SURFACE_REGISTRY: dict[str, AdminSurface] = {
    # ── always: the platform baseline for any Tenant_Admin ──────────────────────────
    "users": {
        "kind": "always",
        "order": 10,
        "label_key": "tenantAdmin.tabs.users",
    },
    "tenant-info": {
        "kind": "always",
        "order": 30,
        "label_key": "tenantAdmin.tabs.tenantInfo",
    },
    "sender": {
        "kind": "always",
        "order": 40,
        "label_key": "tenantAdmin.tabs.senderSettings",
    },
    "landing": {
        "kind": "always",
        "order": 60,
        "label_key": "tenantAdmin.tabs.landingPage",
    },
    # ── module panels: owned by exactly one module ─────────────────────────────────
    "financial": {
        "kind": "module",
        "order": 100,
        "label_key": "tenantAdmin.tabs.financial",
        "module": "FIN",
    },
    "members": {
        "kind": "module",
        "order": 110,
        "label_key": "tenantAdmin.tabs.membersConfig",
        "module": "MEMBERS",
    },
    # ── capabilities: cross-cutting, driven by admin.consumes ──────────────────────
    "functions": {
        "kind": "capability",
        "order": 20,
        "label_key": "tenantAdmin.tabs.functions",
    },
    "pivot": {
        "kind": "capability",
        "order": 50,
        "label_key": "tenantAdmin.tabs.pivotViews",
    },
    "storage": {
        "kind": "capability",
        "order": 200,
        "label_key": "tenantAdmin.tabs.storage",
    },
    "media": {
        "kind": "capability",
        "order": 210,
        "label_key": "tenantAdmin.tabs.mediaAssets",
    },
    "templates": {
        "kind": "capability",
        "order": 220,
        "label_key": "tenantAdmin.tabs.templates",
    },
    # ── role-gated generic surface (the raw Flask parameters editor) ───────────────
    "advanced": {
        "kind": "role",
        "order": 900,
        "label_key": "tenantAdmin.tabs.advanced",
        "required_roles": [],
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Read-only accessors — callers never reach into the dict shape
# ─────────────────────────────────────────────────────────────────────────────


def admin_surface_ids() -> list[str]:
    """Every registered surface id, in declaration order."""
    return list(ADMIN_SURFACE_REGISTRY.keys())


def get_surface(surface_id: str) -> AdminSurface | None:
    """One surface with its id filled in, or None when the id is unknown."""
    descriptor = ADMIN_SURFACE_REGISTRY.get(surface_id)
    if descriptor is None:
        return None
    return {"id": surface_id, **descriptor}


def surfaces_of_kind(kind: str) -> list[AdminSurface]:
    """Every surface of the given kind (one of VALID_KINDS), id filled in."""
    return [
        {"id": surface_id, **descriptor}
        for surface_id, descriptor in ADMIN_SURFACE_REGISTRY.items()
        if descriptor.get("kind") == kind
    ]


def module_admin_declaration(module_name: str) -> dict:
    """A module's admin declaration, or an empty dict when it has none."""
    return MODULE_REGISTRY.get(module_name, {}).get("admin") or {}


def typed_editors() -> dict[str, dict]:
    """Map namespace to surface/owner/module for every declared typed editor."""
    editors: dict[str, dict] = {}
    for module_name in MODULE_REGISTRY:
        declaration = module_admin_declaration(module_name).get("typed_editor")
        if not declaration:
            continue
        namespace = declaration.get("namespace")
        if not namespace:
            continue
        editors[namespace] = {
            "surface": declaration.get("surface"),
            "owner": declaration.get("owner"),
            "flask_mirror_keys": declaration.get("flask_mirror_keys") or [],
            "module": module_name,
        }
    return editors


def typed_editor_namespaces() -> list[str]:
    """Namespaces a module edits through its own typed editor.

    Excluded from the generic Advanced (MySQL parameters) table so that every
    namespace has exactly one editing door.
    """
    return sorted(typed_editors().keys())


def module_owned_namespaces() -> list[str]:
    """Namespaces whose single writer is the module plane (owner == "module")."""
    return sorted(
        namespace
        for namespace, editor in typed_editors().items()
        if editor.get("owner") == "module"
    )


def flask_mirror_keys(namespace: str) -> list[str]:
    """Keys the Flask plane may still legitimately mirror for a module-owned namespace.

    A module-plane-owned namespace is authored on the module plane. Flask may keep a
    narrow validator mirror for some keys (Members/02: the `scope_dimensions` mirror),
    and those keys are declared here so the Flask parameter route can fail closed for
    every OTHER key instead of silently re-opening a second authoring door.
    """
    editor = typed_editors().get(namespace)
    if not editor:
        return []
    return list(editor.get("flask_mirror_keys") or [])


# ─────────────────────────────────────────────────────────────────────────────
# Startup validation — fail loud at boot, never a half-configured dashboard
# ─────────────────────────────────────────────────────────────────────────────


def validate_admin_surface_registry(
    registry: dict | None = None, module_registry: dict | None = None
) -> None:
    """Validate the surface registry and every module's admin declaration.

    Raises:
        ValueError: naming the offending surface id, module, or namespace.
    """
    registry = ADMIN_SURFACE_REGISTRY if registry is None else registry
    module_registry = MODULE_REGISTRY if module_registry is None else module_registry

    for surface_id, descriptor in registry.items():
        if not surface_id:
            raise ValueError("Admin surface registry contains an empty surface id")
        kind = descriptor.get("kind")
        if kind not in VALID_KINDS:
            raise ValueError(
                f"Admin surface '{surface_id}' has invalid kind '{kind}': "
                f"must be one of {', '.join(VALID_KINDS)}"
            )
        order = descriptor.get("order")
        if isinstance(order, bool) or not isinstance(order, int):
            # ValueError (not TypeError) is the documented startup contract: every
            # registry/declaration violation is a single ValueError naming the id,
            # which the boot-time validation and its callers rely on.
            raise ValueError(  # noqa: TRY004
                f"Admin surface '{surface_id}' has non-integer order {order!r}"
            )
        label_key = descriptor.get("label_key", "")
        if not label_key.startswith(LABEL_KEY_PREFIX):
            raise ValueError(
                f"Admin surface '{surface_id}' has label_key '{label_key}': "
                f"must start with '{LABEL_KEY_PREFIX}'"
            )
        if kind == "module":
            owner_module = descriptor.get("module")
            if owner_module not in module_registry:
                raise ValueError(
                    f"Admin surface '{surface_id}' names module '{owner_module}', "
                    "which is not in MODULE_REGISTRY"
                )
        if kind == "role" and not isinstance(
            descriptor.get("required_roles", []), list
        ):
            raise ValueError(
                f"Admin surface '{surface_id}': required_roles must be a list"
            )

    claimed_namespaces: dict[str, str] = {}
    for module_name, module_def in module_registry.items():
        declaration = (module_def or {}).get("admin") or {}

        panel = declaration.get("panel")
        if panel is not None:
            target = registry.get(panel)
            if target is None:
                raise ValueError(
                    f"Module '{module_name}' declares admin.panel '{panel}', "
                    "which is not a registered admin surface"
                )
            if target.get("kind") != "module":
                raise ValueError(
                    f"Module '{module_name}' declares admin.panel '{panel}', which is "
                    f"a '{target.get('kind')}' surface, not a 'module' panel"
                )
            if target.get("module") != module_name:
                raise ValueError(
                    f"Module '{module_name}' declares admin.panel '{panel}', but that "
                    f"surface is owned by module '{target.get('module')}'"
                )

        for capability in declaration.get("consumes") or []:
            target = registry.get(capability)
            if target is None:
                raise ValueError(
                    f"Module '{module_name}' consumes '{capability}', which is not a "
                    "registered admin surface"
                )
            if target.get("kind") != "capability":
                raise ValueError(
                    f"Module '{module_name}' consumes '{capability}', which is a "
                    f"'{target.get('kind')}' surface, not a 'capability'"
                )

        editor = declaration.get("typed_editor")
        if not editor:
            continue
        namespace = editor.get("namespace")
        if not namespace:
            raise ValueError(
                f"Module '{module_name}': admin.typed_editor.namespace must be non-empty"
            )
        editor_surface = editor.get("surface")
        if editor_surface not in registry:
            raise ValueError(
                f"Module '{module_name}': admin.typed_editor.surface "
                f"'{editor_surface}' is not a registered admin surface"
            )
        owner = editor.get("owner")
        if owner not in VALID_OWNERS:
            raise ValueError(
                f"Module '{module_name}': admin.typed_editor.owner '{owner}' must be "
                f"one of {', '.join(VALID_OWNERS)}"
            )
        if owner == "module" and module_backing_or_none(module_name) != "sam":
            raise ValueError(
                f"Module '{module_name}' declares a module-plane typed editor for "
                f"namespace '{namespace}', but the module is not module-plane backed"
            )
        mirror_keys = editor.get("flask_mirror_keys")
        if mirror_keys is not None and not isinstance(mirror_keys, list):
            raise ValueError(
                f"Module '{module_name}': admin.typed_editor.flask_mirror_keys must be a list"
            )
        if mirror_keys and owner != "module":
            raise ValueError(
                f"Module '{module_name}' declares flask_mirror_keys for namespace "
                f"'{namespace}', but that namespace is not module-plane owned"
            )
        if namespace in claimed_namespaces:
            raise ValueError(
                f"Namespace '{namespace}' is claimed by both "
                f"'{claimed_namespaces[namespace]}' and '{module_name}'"
            )
        claimed_namespaces[namespace] = module_name

    logger.info(
        "Admin surface registry validated: %d surfaces, %d typed namespace(s)",
        len(registry),
        len(claimed_namespaces),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Derivation — the pure (entitlements, roles) → ordered surfaces function
# ─────────────────────────────────────────────────────────────────────────────


def derive_admin_surfaces(
    entitled_modules: list[str],
    user_roles: list[str],
    registry: dict | None = None,
    module_registry: dict | None = None,
) -> list[AdminSurface]:
    """Surfaces that apply, ordered by (order, id).

    Pure: no database, no environment, no clock — a function of its inputs only.

    Applicability (design §3):

    - ``always``      always
    - ``module``      the owning module is in Entitlement_Truth
    - ``capability``  some entitled module declares ``admin.consumes`` for it
    - ``role``        no ``required_roles``, or the caller holds one of them

    Module names that are not registered are ignored, so a legacy ``tenant_modules``
    row for another tenant cannot abort the list.
    """
    registry = ADMIN_SURFACE_REGISTRY if registry is None else registry
    module_registry = MODULE_REGISTRY if module_registry is None else module_registry

    entitled = set(entitled_modules or [])
    roles = set(user_roles or [])

    consumed: set = set()
    for module_name in entitled:
        declaration = (module_registry.get(module_name) or {}).get("admin") or {}
        for capability in declaration.get("consumes") or []:
            consumed.add(capability)

    derived: list[AdminSurface] = []
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
            applies = not required or bool(set(required) & roles)
        else:  # validate_admin_surface_registry rejects these at boot
            applies = False
        if applies:
            derived.append({"id": surface_id, **descriptor})

    derived.sort(key=lambda surface: (surface.get("order", 0), surface["id"]))
    return derived
