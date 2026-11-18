"""
Architectural guard: the admin-surface vocabulary agrees across planes.

`ADMIN_SURFACE_REGISTRY` (Flask) declares, per surface, the id and the
``tenantAdmin.tabs.*`` label key the dashboard renders. The React plane carries the
same vocabulary in two places it cannot import from Python:

- the component map + label mirror in
  ``frontend/src/components/TenantAdmin/__tests__/adminSurfaceComponents.test.tsx``
- the actual translations in ``frontend/src/locales/{en,nl}/admin.json``

Steering 36 rule 5 requires ONE source of truth with agreement enforced by a test —
the same pattern as ``members_config_validation`` vs the module's ``fixed_fields``.
This is that test: add or rename a surface in the registry and the frontend mirror
and the locales must move with it, or this fails. (A missing translation renders the
raw key in the tab bar, which is how this guard came to exist.)

Reference: .kiro/specs/Common/Tenant/admin-surface-registry/ — Property 7, Req 11.4
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services.admin_surface_registry import ADMIN_SURFACE_REGISTRY

pytestmark = pytest.mark.architecture

REPO_ROOT = Path(__file__).resolve().parents[3]
TENANT_ADMIN_DIR = REPO_ROOT / "frontend/src/components/TenantAdmin"
MIRROR_FILE = TENANT_ADMIN_DIR / "__tests__/adminSurfaceComponents.test.tsx"
COMPONENT_MAP_FILE = TENANT_ADMIN_DIR / "adminSurfaceComponents.tsx"
LOCALES = {
    "en": REPO_ROOT / "frontend/src/locales/en/admin.json",
    "nl": REPO_ROOT / "frontend/src/locales/nl/admin.json",
}

LABEL_KEY_RE = re.compile(r"tenantAdmin\.tabs\.[A-Za-z]+")


def _backend_label_keys() -> set:
    return {descriptor["label_key"] for descriptor in ADMIN_SURFACE_REGISTRY.values()}


def _resolve(doc: object, dotted: str) -> object:
    current = doc
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def test_the_frontend_files_this_guard_reads_still_exist():
    """Fail loudly (not silently pass) if a path is renamed."""
    for path in (MIRROR_FILE, COMPONENT_MAP_FILE, *LOCALES.values()):
        assert path.is_file(), f"missing file: {path}"


def test_frontend_label_mirror_is_exactly_the_registry_vocabulary():
    """Both directions: no stale key in the mirror, no unmirrored key in the registry."""
    mirror_keys = set(LABEL_KEY_RE.findall(MIRROR_FILE.read_text(encoding="utf-8")))
    backend_keys = _backend_label_keys()
    assert mirror_keys == backend_keys, (
        f"only in frontend mirror: {sorted(mirror_keys - backend_keys)}; "
        f"only in backend registry: {sorted(backend_keys - mirror_keys)}"
    )


def test_every_surface_id_is_mapped_in_the_component_map():
    """No registered surface may be absent from the React component map."""
    source = COMPONENT_MAP_FILE.read_text(encoding="utf-8")
    missing = [
        surface_id
        for surface_id in ADMIN_SURFACE_REGISTRY
        if not re.search(
            r"^\s*['\"]?" + re.escape(surface_id) + r"['\"]?\s*:", source, re.MULTILINE
        )
    ]
    assert not missing, f"surfaces missing from adminSurfaceComponents.tsx: {missing}"


@pytest.mark.parametrize("locale", sorted(LOCALES))
def test_every_label_key_resolves_in_each_locale(locale):
    """A missing/blank translation renders the raw key — so every key must resolve."""
    doc = json.loads(LOCALES[locale].read_text(encoding="utf-8"))
    missing = [
        key
        for key in sorted(_backend_label_keys())
        if not isinstance(_resolve(doc, key), str) or not _resolve(doc, key).strip()
    ]
    assert not missing, f"{locale}: missing or empty tab translations: {missing}"
