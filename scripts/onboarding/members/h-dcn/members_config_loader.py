#!/usr/bin/env python3
"""members_config_loader.py — the SINGLE loader for h-dcn's onboarding members CONFIG.

Reads ``scripts/onboarding/members/h-dcn/members_config.json`` (the single source of truth,
Decision D18)
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
#: fold because they differ by a real letter/word, not case/diacritic/separator. TENANT DATA —
#: kept here beside the config file, NOT in the generic core.
#:
#: PORTED (s5m R8.1) from h-dcn's proven importer ``import_members_sheets.py`` v2.0
#: ``regio_value_mapping`` (~40 variants) + ``VALID_REGIONS``, RETARGETED (R8.2) onto THIS
#: tenant's ENGLISH-plane canonical region value set authored in ``members_config.json``
#: (``region_values`` below) — NOT copied with h-dcn's old Dutch stored values. Key differences
#: from h-dcn's targets: SAM uses ``Noord Holland`` / ``Zuid Holland`` (a SPACE, not the hyphen
#: h-dcn stored) and ``Geen`` where h-dcn used ``Overig`` ("Other").
#:
#: Only genuine letter/word/label differences need an entry here — ``scope_canon`` already folds
#: case, diacritics and separators on BOTH sides of the match (so ``noord-holland`` /
#: ``NOORD HOLLAND`` / ``Noord  Holland`` all fold onto the canonical ``Noord Holland`` WITHOUT
#: an alias). These aliases cover the real export's abbreviations, misspellings, merged/split
#: region names and English labels that ``scope_canon`` cannot reach.
REGION_ALIASES: Mapping[str, str] = {
    # --- misspelling ``scope_canon`` cannot fold (real letter difference) -------------------
    "Groningen/Drente": "Groningen/Drenthe",
    "Groningen/Drenthe": "Groningen/Drenthe",
    "Groningen": "Groningen/Drenthe",
    "Drenthe": "Groningen/Drenthe",
    "Drente": "Groningen/Drenthe",
    # --- Noord/Zuid Holland variants that differ by a WORD (Nrd/Zd/N-/Z-), not a separator ---
    "Nrd Holland": "Noord Holland",
    "N Holland": "Noord Holland",
    "NH": "Noord Holland",
    "Noord-Holland": "Noord Holland",
    "Zd Holland": "Zuid Holland",
    "Z Holland": "Zuid Holland",
    "ZH": "Zuid Holland",
    "Zuid-Holland": "Zuid Holland",
    # --- Brabant / Zeeland split or abbreviated in the source → the merged canonical value ---
    "Brabant": "Brabant/Zeeland",
    "Zeeland": "Brabant/Zeeland",
    "Noord Brabant": "Brabant/Zeeland",
    "Noord-Brabant": "Brabant/Zeeland",
    "NB": "Brabant/Zeeland",
    # --- Oost (east) region spellings ---------------------------------------------------------
    "Oost Nederland": "Oost",
    "Overijssel": "Oost",
    "Gelderland": "Oost",
    "Flevoland": "Oost",
    # --- Friesland spelling variant (Frisian) -------------------------------------------------
    "Fryslan": "Friesland",
    "Fryslân": "Friesland",
    # --- Germany (English label) --------------------------------------------------------------
    "Germany": "Duitsland",
    # --- "Overig"/other/none → the SAM canonical ``Geen`` (h-dcn stored ``Overig``, R8.2) -----
    "Overig": "Geen",
    "Overige": "Geen",
    "Anders": "Geen",
    "Other": "Geen",
    "Onbekend": "Geen",
    "None": "Geen",
    "N.v.t.": "Geen",
    "NVT": "Geen",
    "Buitenland": "Geen",
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
