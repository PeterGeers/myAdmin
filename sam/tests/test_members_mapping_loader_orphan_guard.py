"""
members-modal-field-mapping-mismatch — Task 4.2 orphan-guard VERIFICATION tests.

Task 4.1 added the config↔mapping orphan-field guard to
``scripts/onboarding/members/h-dcn/members_mapping_loader.load_mapping_contract`` (R2.5): every
overlay field
DECLARED in ``members_config.json`` must have a mapping backing in the CSV, else the loader
HARD-FAILS with a ``MappingContractError``. This file VERIFIES that guard from four angles:

  1. the guard RAISES for a config declaring a declared-but-unmapped overlay field (the same
     assertion that failed SILENTLY on unfixed code in Task 1 now fails LOUDLY) — see also
     ``test_members_modal_mapping_mismatch_explore.py::TestLoaderOrphanGuardGap``;
  2. the guard PASSES (does NOT raise) for the CORRECTED real config from Task 3 (the two orphans
     ``signature_date`` / ``privacy_consent`` were removed) loaded with the real mapping CSV;
  3. the OPPOSITE-direction drift guard STILL RAISES for a mapping target NOT declared in the
     config — proving 4.1 did not weaken it;
  4. **Property 4 (property-based)**: for a config carrying a RANDOM extra declared-but-unmapped
     overlay field, the guard flags it (raises ``MappingContractError`` naming the orphan).

Follows the sys.path / import pattern of the sibling exploration test. Run via ``sam/pytest.ini``.

Validates: Requirements 2.5
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# repo root + backend/src on sys.path (mirrors the sibling exploration test + sam/conftest.py).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

# The h-dcn scripts dir carries the CSV + its two loaders; on sys.path so they import as
# top-level modules (mirrors test_hdcn_backfill.py and the exploration test).
_HDCN_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "scripts", "onboarding", "members", "h-dcn")
if _HDCN_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _HDCN_SCRIPTS_DIR)

from members_mapping_loader import (
    MappingContractError,
    load_mapping_contract,
)

_MAPPING_CSV = os.path.join(_HDCN_SCRIPTS_DIR, "members_source_mapping.csv")
_CONFIG_JSON = os.path.join(_HDCN_SCRIPTS_DIR, "members_config.json")


def _load_real_config() -> dict:
    with open(_CONFIG_JSON, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _declared_overlay_fields(config: dict) -> set[str]:
    return set((config.get("field_overlay", {}) or {}).get("fields", {}) or {})


def _write_mapping(tmp_path, body: str) -> str:
    """Write a minimal mapping CSV (header + ``body``) and return its path."""
    header = "source_column,col_index,target,rule,note\n"
    p = tmp_path / "mapping.csv"
    p.write_text(header + body, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# 1 — the guard RAISES for a declared-but-unmapped overlay field
# ---------------------------------------------------------------------------


class TestOrphanGuardRaises:
    """The guard added in 4.1 surfaces a config↔mapping orphan as a contract violation.

    This is the assertion that failed SILENTLY (DID NOT RAISE) on unfixed code in Task 1; the
    guard now makes it fail LOUDLY.

    Validates: Requirements 2.5
    """

    def test_load_mapping_contract_raises_for_declared_unmapped_overlay_field(self, tmp_path):
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
        # The mapping maps only a fixed field, so the declared overlay field has NO backing.
        mapping_path = _write_mapping(tmp_path, "Voornaam,0,personal.first_name,single,x\n")

        with pytest.raises(MappingContractError) as exc:
            load_mapping_contract(mapping_path, config=orphan_config)
        # The message names the orphan and the guard.
        assert any(
            "orphan" in e.lower() and "orphan_field" in e for e in exc.value.errors
        ), exc.value.errors


# ---------------------------------------------------------------------------
# 2 — the guard PASSES for the CORRECTED real config from Task 3
# ---------------------------------------------------------------------------


class TestCorrectedConfigLoads:
    """The corrected real config (Task 3 removed the two orphans) loads with the real CSV.

    Before the Task 3 edit the real config declared ``signature_date`` / ``privacy_consent`` with
    no mapping backing, so — once the 4.1 guard existed — the loader would have RAISED. With the
    orphans removed the real contract loads clean.

    Validates: Requirements 2.5
    """

    def test_corrected_real_config_has_no_orphans_and_loads(self):
        config = _load_real_config()
        declared = _declared_overlay_fields(config)
        # Guard against a regression of the Task 3 config edit.
        assert "signature_date" not in declared
        assert "privacy_consent" not in declared

        # Loading the REAL mapping CSV against the REAL corrected config must NOT raise.
        contract = load_mapping_contract(_MAPPING_CSV, config=config)
        assert contract.overlay  # sanity: it parsed real overlay mappings


# ---------------------------------------------------------------------------
# 3 — the OPPOSITE-direction drift guard still RAISES (4.1 didn't weaken it)
# ---------------------------------------------------------------------------


class TestDriftGuardStillRaises:
    """A mapping target NOT declared in the config still trips the pre-existing drift guard.

    This is the OPPOSITE direction from the orphan guard: the mapping invents an ``overlay.*`` key
    the config does not carry. 4.1 must not have weakened this.

    Validates: Requirements 2.5
    """

    def test_load_mapping_contract_raises_for_undeclared_mapping_target(self, tmp_path):
        # Config declares ONE overlay field that IS mapped below (so the orphan guard is clean),
        # while the mapping ALSO targets a SECOND overlay key the config never declares.
        config = {
            "field_overlay": {
                "fields": {
                    "declared_field": {
                        "type": "string",
                        "required": False,
                        "label": {"nl": "x", "en": "x"},
                    }
                }
            }
        }
        body = (
            "Kolom A,0,overlay.declared_field,single,\n"
            "Kolom B,1,overlay.undeclared_field,single,\n"
        )
        mapping_path = _write_mapping(tmp_path, body)

        with pytest.raises(MappingContractError) as exc:
            load_mapping_contract(mapping_path, config=config)
        assert any(
            "drift guard" in e.lower() and "undeclared_field" in e for e in exc.value.errors
        ), exc.value.errors


# ---------------------------------------------------------------------------
# 4 — Property 4 (property-based): a random extra orphan is always flagged
# ---------------------------------------------------------------------------

# Overlay keys already backed by the real mapping / the disposition-backed key. Any generated
# orphan key must avoid these so it is genuinely a declared-but-unmapped field.
_RESERVED_KEYS = frozenset(
    _declared_overlay_fields(_load_real_config()) | {"additional_info"}
)

# A valid overlay key name: lower snake_case identifier (matches how overlay keys are authored).
_orphan_key = st.from_regex(r"[a-z][a-z_]{2,20}", fullmatch=True).filter(
    lambda k: k not in _RESERVED_KEYS
)


class TestOrphanGuardProperty:
    """Property 4: a config carrying a RANDOM declared-but-unmapped overlay field is flagged.

    Generator: a random valid overlay key name that is NOT already mapped and NOT
    ``additional_info``. Adding it as a declared field with no mapping backing must always trip
    the orphan guard, and the raised error must name that key.

    Validates: Requirements 2.5
    """

    @settings(max_examples=100, deadline=None)
    @given(orphan=_orphan_key)
    def test_loader_flags_random_extra_declared_unmapped_overlay_field(self, orphan):
        config = {
            "field_overlay": {
                "fields": {
                    orphan: {
                        "type": "string",
                        "required": False,
                        "label": {"nl": orphan, "en": orphan},
                    }
                }
            }
        }
        # A mapping that backs ONLY a fixed field — the generated overlay field is an orphan.
        # Use a self-managed temp file (NOT the function-scoped tmp_path fixture, which
        # hypothesis will not reset between generated inputs).
        with tempfile.NamedTemporaryFile(
            "w", suffix=".csv", encoding="utf-8", newline="", delete=False
        ) as fh:
            fh.write("source_column,col_index,target,rule,note\n")
            fh.write("Voornaam,0,personal.first_name,single,\n")
            mapping_path = fh.name
        try:
            with pytest.raises(MappingContractError) as exc:
                load_mapping_contract(mapping_path, config=config)
            assert any(
                "orphan" in e.lower() and orphan in e for e in exc.value.errors
            ), (orphan, exc.value.errors)
        finally:
            os.unlink(mapping_path)
