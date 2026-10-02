"""
members-modal-field-mapping-mismatch — BUG CONDITION exploration tests (Task 1, BEFORE any fix).

These tests demonstrate the four field-mapping mismatches the modal surfaces AGAINST the
UNFIXED code. Per the bugfix workflow they encode the EXPECTED POST-FIX behavior, so on the
current (unfixed) code:

  * the newsletter transform assertion PASSES  — proving `map_hdcn_row` is correct and the live
    bug is downstream (stale data / live-sheet header), NOT the transform;
  * the two orphan-field assertions FAIL       — `signature_date` / `privacy_consent` are declared
    in members_config.json but NO row in members_source_mapping.csv backs them (the modal renders
    permanently-empty "Datum ondertekening" / "Privacy" rows);
  * the loader-guard assertion FAILS           — `load_mapping_contract` accepts a config that
    declares an unmapped overlay field without complaint (the R1.5 / R2.5 gap).

The `evaluateShowWhen` gate (problem 4) is a FRONTEND predicate; its exploration test lives in
`frontend/src/components/members/fieldForm.test.ts` (this file covers only the Python planes).

Scoped-PBT approach (design "Exploratory Bug Condition Checking"): these are deterministic,
config/transform-driven bugs, so each property is scoped to the concrete failing case (the
specific config fields, the specific source header) for reproducibility.

Validates: Requirements 1.1, 1.2, 1.4, 1.5, 2.1, 2.2, 2.4, 2.5
"""

from __future__ import annotations

import json
import os
import sys

import pytest

# repo root + backend/src on sys.path (mirrors sam/conftest.py + the other sam tests).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

# The h-dcn onboarding scripts dir carries the CSV + its two loaders (config + mapping). Put it
# on sys.path so `members_mapping_loader` / `members_config_loader` import as top-level modules
# (mirrors how test_hdcn_backfill.py loads them).
_HDCN_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "scripts", "onboarding", "members", "h-dcn")
if _HDCN_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _HDCN_SCRIPTS_DIR)

from members_mapping_loader import (
    MappingContractError,
    load_mapping_contract,
)

from sam.members.migration.hdcn_backfill import map_hdcn_row

_MAPPING_CSV = os.path.join(_HDCN_SCRIPTS_DIR, "members_source_mapping.csv")
_CONFIG_JSON = os.path.join(_HDCN_SCRIPTS_DIR, "members_config.json")


def _mapping_targets() -> set[str]:
    """Every `overlay.*` / `personal.*` / `membership.*` target authored in the mapping CSV.

    Reads the raw CSV rows (not the parsed contract) so the assertion speaks directly to "what
    the single-source-of-truth contract targets" — the exact framing the bug analysis uses.
    """
    targets: set[str] = set()
    with open(_MAPPING_CSV, "r", encoding="utf-8", newline="") as fh:
        for line in fh:
            if line.lstrip().startswith("#") or not line.strip():
                continue
            parts = line.split(",")
            if len(parts) < 3:
                continue
            target = parts[2].strip()
            # A conditional-split row names two targets joined with '+'.
            for t in target.split("+"):
                t = t.strip()
                if t:
                    targets.add(t)
    return targets


def _declared_overlay_fields() -> set[str]:
    """The overlay field keys DECLARED in members_config.json (`field_overlay.fields`)."""
    with open(_CONFIG_JSON, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    return set((config.get("field_overlay", {}) or {}).get("fields", {}) or {})


# ---------------------------------------------------------------------------
# Problem 1 — newsletter transform (EXPECTED to PASS on unfixed code)
# ---------------------------------------------------------------------------


class TestNewsletterTransform:
    """Property 1 (Bug Condition): the transform DOES copy the newsletter cell onto the overlay.

    EXPECTED OUTCOME: PASS on unfixed code. A pass proves `map_hdcn_row` is correct, so the live
    "Nieuwsbrief" dash is a data-flow / stored-value concern (stale data or a live-sheet header
    mismatch), NOT a transform bug — disambiguated by investigation task 6.1.

    Validates: Requirements 1.1, 2.1
    """

    def test_map_hdcn_row_copies_newsletter_ja_onto_overlay_newsletter_pref(self):
        # A minimal-but-meaningful raw row (real headers): a valid SAM Code + a type + the
        # newsletter cell set to the raw sheet value "Ja" (the config enum is lowercase ja/nee,
        # but the `single` rule copies the cell VERBATIM — renderFieldValue stringifies as-is).
        raw = {
            "SAM Code": "M01001",
            "Voornaam": "Alex",
            "Achternaam": "de Vries",
            "Soort lidmaatschap": "Erelid",
            "Digitale nieuwsbrieven": "Ja",
        }
        record = map_hdcn_row(raw)
        assert record["overlay"]["newsletter_pref"] == "Ja"


# ---------------------------------------------------------------------------
# Problems 2 & 3 — orphan overlay fields (EXPECTED to FAIL on unfixed code)
# ---------------------------------------------------------------------------


class TestOrphanOverlayFields:
    """Property 2 (Bug Condition): a declared overlay field with NO mapping backing is an orphan.

    isBugCondition_orphan(fieldKey) := fieldKey IN config.field_overlay.fields
                                       AND NO mapping row targets ("overlay." + fieldKey).

    The assertions below encode the EXPECTED POST-FIX state (the orphan no longer declared), so on
    UNFIXED code — where the config STILL declares them — they FAIL. That failure is the SUCCESS
    case for an exploration test: it proves the orphan exists.

    Validates: Requirements 1.2, 1.4, 2.2, 2.4
    """

    def test_signature_date_is_not_a_declared_orphan(self):
        targets = _mapping_targets()
        declared = _declared_overlay_fields()
        # The bug: no mapping row targets overlay.signature_date, YET it is declared.
        assert "overlay.signature_date" not in targets  # confirms it is unmapped
        # EXPECTED POST-FIX: the orphan is removed from the config. FAILS on unfixed code.
        assert "signature_date" not in declared, (
            "orphan overlay field 'signature_date' is declared in members_config.json but NO "
            "row in members_source_mapping.csv targets overlay.signature_date — the modal "
            "renders a permanently-empty 'Datum ondertekening' row (isBugCondition_orphan)"
        )

    def test_privacy_consent_is_not_a_declared_orphan(self):
        targets = _mapping_targets()
        declared = _declared_overlay_fields()
        assert "overlay.privacy_consent" not in targets  # confirms it is unmapped
        # EXPECTED POST-FIX: the orphan is removed from the config. FAILS on unfixed code.
        assert "privacy_consent" not in declared, (
            "orphan overlay field 'privacy_consent' (required: true) is declared in "
            "members_config.json but NO source column maps to overlay.privacy_consent — the "
            "modal renders a permanently-empty 'Privacy' row (isBugCondition_orphan)"
        )


# ---------------------------------------------------------------------------
# R2.5 — loader orphan-field guard gap (EXPECTED to FAIL on unfixed code)
# ---------------------------------------------------------------------------


class TestLoaderOrphanGuardGap:
    """Property 4 (Bug Condition): the loader does NOT surface a declared-but-unmapped overlay.

    The mapping loader's drift guard only rejects a mapping TARGET not declared in the config (one
    direction). It does NOT flag a config overlay field with NO mapping backing (the other
    direction) — so orphan fields pass validation unnoticed (the R1.5 / R2.5 gap).

    The assertion below encodes the EXPECTED POST-FIX behavior (the loader RAISES for an orphan),
    so on UNFIXED code it FAILS — the loader loads the orphan config silently.

    Validates: Requirements 1.5, 2.5
    """

    def _write_mapping(self, tmp_path, body: str) -> str:
        header = "source_column,col_index,target,rule,note\n"
        p = tmp_path / "mapping.csv"
        p.write_text(header + body, encoding="utf-8")
        return str(p)

    def test_loader_flags_a_config_overlay_field_with_no_mapping_backing(self, tmp_path):
        # A minimal config declaring ONE overlay field ("orphan_field") that the mapping below
        # does NOT target. The mapping only maps a fixed field, so the orphan has no backing.
        orphan_config = {
            "field_overlay": {
                "fields": {
                    "orphan_field": {
                        "type": "string",
                        "required": False,
                        "label": {"nl": "Wees", "en": "Orphan"},
                    }
                }
            }
        }
        mapping_path = self._write_mapping(
            tmp_path, "Voornaam,0,personal.first_name,single,x\n"
        )

        # EXPECTED POST-FIX: loading a contract whose config declares an unmapped overlay field
        # surfaces it as a contract violation. On UNFIXED code the loader accepts it SILENTLY,
        # so this `pytest.raises` FAILS (DID NOT RAISE) — demonstrating the guard gap.
        with pytest.raises(MappingContractError) as exc:
            load_mapping_contract(mapping_path, config=orphan_config)
        assert any("orphan" in e.lower() for e in exc.value.errors)
