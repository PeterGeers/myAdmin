#!/usr/bin/env python3
"""members_config_loader.py — the SINGLE loader for h-dcn's onboarding members CONFIG.

Reads ``scripts/aws/h-dcn/members_config.json`` (the single source of truth, Decision D18)
and exposes it to BOTH onboarding consumers so importer + config + enforcement never drift:

- ``load_members_config()`` → the parsed ``{scope_dimensions, field_overlay}`` payloads that
  ``seed-hdcn-members-config.py`` upserts into MySQL (``members.scope_dimensions`` /
  ``members.field_overlay``) via ``ParameterService.set_param``.
- ``region_canonicalizer(...)`` → a ``RegionCanonicalizer`` (from the SAM backfill) built from
  the SAME ``scope_dimensions`` region values + a spelling-alias map, so the member backfill
  canonicalizes ``region`` onto the exact vocabulary onboarding authored (D17: tenant data,
  not a core constant).

This file carries NO tenant vocabulary itself — it only READS the JSON. The values live in
``members_config.json``; the generic SAM core ships none (``SAMPLE_SCOPE_CONFIG`` is synthetic).
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
#: Default onboarding config file (this tenant's single source of truth).
DEFAULT_CONFIG_PATH = os.path.join(_THIS_DIR, "members_config.json")

#: Region spelling ALIASES (raw export spelling → canonical value) that ``scope_canon`` cannot
#: fold because they differ by a real letter, not case/diacritic/separator. TENANT DATA — kept
#: here beside the config file, NOT in the generic core. h-dcn: the export's ``Groningen/Drente``
#: misspelling maps onto the canonical ``Groningen/Drenthe`` (see members_config.json).
REGION_ALIASES: Mapping[str, str] = {
    "Groningen/Drente": "Groningen/Drenthe",
}


def load_members_config(path: str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load + minimally validate the members config JSON. Returns the parsed dict."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "scope_dimensions" not in data or "field_overlay" not in data:
        raise ValueError(
            f"{path!r} must contain both 'scope_dimensions' and 'field_overlay' keys"
        )
    return data


def region_values(config: Mapping[str, Any]) -> tuple[str, ...]:
    """The canonical region value set from the config's scope_dimensions (the 'region' dim)."""
    for dim in config.get("scope_dimensions", []):
        if dim.get("key") == "region":
            return tuple(dim.get("values", ()))
    return ()


def region_canonicalizer(config: Mapping[str, Any]):
    """Build a ``RegionCanonicalizer`` from the config's region values + REGION_ALIASES.

    Imported lazily so this loader has no hard dependency on the SAM package import path when
    a caller only needs ``load_members_config`` (e.g. the MySQL config-seed script).
    """
    from sam.members.migration.hdcn_backfill import RegionCanonicalizer

    return RegionCanonicalizer(region_values(config), aliases=REGION_ALIASES)


def scope_dimensions_param(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The value to store under the ``members.scope_dimensions`` parameter."""
    return list(config.get("scope_dimensions", []))


def field_overlay_param(config: Mapping[str, Any]) -> dict[str, Any]:
    """The value to store under the ``members.field_overlay`` parameter (``_comment`` stripped)."""
    overlay = dict(config.get("field_overlay", {}))
    return _strip_comments(overlay)


def _strip_comments(value: Any) -> Any:
    """Recursively drop ``_comment`` keys so authoring notes never land in the stored param."""
    if isinstance(value, dict):
        return {k: _strip_comments(v) for k, v in value.items() if k != "_comment"}
    if isinstance(value, list):
        return [_strip_comments(v) for v in value]
    return value
