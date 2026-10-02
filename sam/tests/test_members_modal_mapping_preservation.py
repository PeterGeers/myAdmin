"""
Members modal field-mapping mismatch bugfix — Task 2 PRESERVATION tests (backend plane).

Feature: members-modal-field-mapping-mismatch
Property 6: Preservation — mapped overlay fields, header-name matching, and additional_info
concatenation are UNCHANGED by the config/loader/gate fix.

**Observation-first methodology.** These tests were written by first running the UNFIXED
``map_hdcn_row`` transform, recording its actual outputs, then asserting those observed outputs
across the input domain. They establish the baseline the config/loader/gate changes (tasks 3-6)
must NOT regress — so they are EXPECTED TO PASS on the unfixed code and must CONTINUE to pass
after the fix.

The three properties here live in the backfill transform (``sam/members/migration/hdcn_backfill``):
- **mapped overlay preservation (R3.1, R3.5)** — every declared-and-mapped overlay field
  (``magazine_pref``, ``motor_brand``, ``deregistration_date``, ``termination_date``, ``notes``,
  ``referral_source``) renders its stored value in the resolved record.
- **header-name matching stability (R3.2)** — ``map_hdcn_row`` matches source columns by BASE
  header (lower-cased), NOT by ``col_index``; a shuffled column order and/or the SAM Code
  col-0 insertion require no positional shift.
- **additional_info concatenation (R3.3)** — leftover ``(additional_info)``-routed columns
  (``Ondertekening`` / ``Naam voor akkoord``) concatenate into ``overlay.additional_info`` as
  ``Label: value`` pairs in stable source-column order with the ` | ` delimiter.

Validates: Requirements 3.1, 3.2, 3.3, 3.5
"""

from __future__ import annotations

import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# repo root + backend/src on sys.path (mirrors sam/conftest.py + the other sam tests).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.migration.hdcn_backfill import (
    RegionCanonicalizer,
    build_position_tracked_row,
    map_hdcn_row,
)

# A synthetic region canonicalizer — tenant vocabulary is INJECTED, never a core constant
# (matches the convention in test_hdcn_backfill.py).
_REGION = RegionCanonicalizer(("North", "South", "East", "West"), aliases={"Noorden": "North"})


def _raw(**overrides):
    """A well-formed raw h-dcn source row (REAL Ledenbestand headers) with overrides."""
    row = {
        "SAM Code": "M01001",
        "Voornaam": "Alex",
        "Achternaam": "de Vries",
        "E-mailadres": "alex@example.com",
        "Straat en huisnummer": "Dorpsstraat 1",
        "Soort lidmaatschap": "Erelid",
        "Datum ondertekening": "2010-01-01T00:00:00.000Z",
        "Regio": "North",
    }
    row.update(overrides)
    return row


def _map(**overrides):
    return map_hdcn_row(_raw(**overrides), region_canonicalizer=_REGION)


# ---------------------------------------------------------------------------
# Observed baseline (unit) — the concrete outputs recorded from the UNFIXED code.
# ---------------------------------------------------------------------------


class TestMappedOverlayPreservationBaseline:
    """Observed on UNFIXED code: declared-and-mapped overlay fields render their stored value."""

    def test_mapped_overlay_fields_render_their_stored_values(self):
        rec = _map(
            **{
                "Clubblad": "Papier",          # → overlay.magazine_pref (magazine rule)
                "Motormerk": "harley_davidson",  # → overlay.motor_brand (single)
                "Afmelding": "2020-06-15",      # → overlay.deregistration_date (date)
                "Beeindiging": "2021-07-20T00:00:00.000Z",  # → overlay.termination_date (date)
                "Opmerkingen": "some notes here",  # → overlay.notes (single)
                "WieWatWaar": "via een vriend",  # → overlay.referral_source (single)
            }
        )
        overlay = rec["overlay"]
        # Observed outputs (recorded from the unfixed transform):
        assert overlay["magazine_pref"] == "Papier"
        assert overlay["motor_brand"] == "harley_davidson"
        assert overlay["deregistration_date"] == "2020-06-15"
        assert overlay["termination_date"] == "2021-07-20"  # date-normalized to bare YYYY-MM-DD
        assert overlay["notes"] == "some notes here"
        assert overlay["referral_source"] == "via een vriend"


class TestAdditionalInfoConcatBaseline:
    """Observed on UNFIXED code: signature leftovers concatenate into overlay.additional_info."""

    def test_ondertekening_and_naam_voor_akkoord_concatenate_in_order(self):
        rec = map_hdcn_row(
            _raw(**{"Ondertekening": "13-4-2023", "Naam voor akkoord": "Alex de Vries"}),
            region_canonicalizer=_REGION,
        )
        # Observed output: `Label: value` pairs, stable source-column order, ` | ` delimiter.
        assert (
            rec["overlay"]["additional_info"]
            == "Ondertekening: 13-4-2023 | Naam voor akkoord: Alex de Vries"
        )


# ---------------------------------------------------------------------------
# PBT — mapped overlay preservation (Property 6, R3.1, R3.5).
# ---------------------------------------------------------------------------

# Non-empty, non-whitespace free-text values (single-line, no leading/trailing space so the
# transform's strip does not change the stored value — we assert the value is preserved verbatim).
_free_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs", "Zl", "Zp"), blacklist_characters="|"),
    min_size=1,
    max_size=40,
).map(lambda s: s.strip()).filter(lambda s: len(s) >= 1)

_motor_brand = st.sampled_from(["harley_davidson", "indian", "buell", "eigenbouw"])
_magazine = st.sampled_from(["Geen", "Papier", "Digitaal"])
# ISO-ish dates that _parse_source_date reduces to a bare YYYY-MM-DD verbatim (already YYYY-MM-DD).
_iso_date = st.dates().map(lambda d: d.isoformat())


@settings(max_examples=100)
@given(
    magazine=_magazine,
    motor_brand=_motor_brand,
    dereg=_iso_date,
    term=_iso_date,
    notes=_free_text,
    referral=_free_text,
)
def test_property_mapped_overlay_fields_render_their_stored_value(
    magazine, motor_brand, dereg, term, notes, referral
):
    """Every declared-and-mapped overlay field carries its stored value (Property 6, R3.1/R3.5).

    Validates: Requirements 3.1, 3.5
    """
    rec = _map(
        Clubblad=magazine, Motormerk=motor_brand, Afmelding=dereg, Beeindiging=term, Opmerkingen=notes, WieWatWaar=referral
    )
    overlay = rec["overlay"]
    # single-rule string fields are stored verbatim (trimmed); magazine maps as-is for the enum
    # values; date fields are already bare YYYY-MM-DD so they round-trip unchanged (R3.5).
    assert overlay["magazine_pref"] == magazine
    assert overlay["motor_brand"] == motor_brand
    assert overlay["deregistration_date"] == dereg
    assert overlay["termination_date"] == term
    assert overlay["notes"] == notes
    assert overlay["referral_source"] == referral


# ---------------------------------------------------------------------------
# PBT — header-name matching stability (Property 6, R3.2).
# ---------------------------------------------------------------------------

# The mapped columns whose presence/position we shuffle. Each entry maps a source header to the
# overlay key it feeds and a fixed sample value, so we can assert the output after any reorder.
_SHUFFLE_COLUMNS = [
    ("SAM Code", None, "M01001"),
    ("Voornaam", None, "Alex"),
    ("Achternaam", None, "de Vries"),
    ("E-mailadres", None, "alex@example.com"),
    ("Straat en huisnummer", None, "Dorpsstraat 1"),
    ("Soort lidmaatschap", None, "Erelid"),
    ("Datum ondertekening", None, "2010-01-01T00:00:00.000Z"),
    ("Regio", None, "North"),
    ("Motormerk", "motor_brand", "harley_davidson"),
    ("WieWatWaar", "referral_source", "via een vriend"),
    ("Opmerkingen", "notes", "some notes here"),
    ("Clubblad", "magazine_pref", "Papier"),
]


@settings(max_examples=100)
@given(
    perm=st.permutations(range(len(_SHUFFLE_COLUMNS))),
    dup_motor=st.booleans(),
)
def test_property_header_name_matching_is_stable_across_column_order(perm, dup_motor):
    """map_hdcn_row matches on the BASE header, NOT col_index — any order yields the same record.

    Random column orders (and an optional empty duplicate ``Motormerk``) must produce the SAME
    mapped values. Matching keyed on ``col_index`` would break under a reorder or the SAM Code
    col-0 insertion; keying on the base header (lower-cased) is position-independent (R3.2).

    Validates: Requirements 3.2
    """
    ordered = [_SHUFFLE_COLUMNS[i] for i in perm]
    headers = [h for (h, _key, _v) in ordered]
    values = [v for (_h, _key, v) in ordered]
    if dup_motor:
        # An EMPTY duplicate of Motormerk somewhere — must never clobber the populated sibling
        # (first-non-empty coalesce on the base header, R3.2/R1.4).
        headers.append("Motormerk")
        values.append("")

    row = build_position_tracked_row(headers, values)
    rec = map_hdcn_row(row, region_canonicalizer=_REGION)

    # Every mapped value resolves regardless of physical column position.
    assert rec["membership"]["member_number"] == "M01001"
    assert rec["personal"]["first_name"] == "Alex"
    assert rec["personal"]["email"] == "alex@example.com"
    assert rec["overlay"]["motor_brand"] == "harley_davidson"
    assert rec["overlay"]["referral_source"] == "via een vriend"
    assert rec["overlay"]["notes"] == "some notes here"
    assert rec["overlay"]["magazine_pref"] == "Papier"


# ---------------------------------------------------------------------------
# PBT — additional_info concatenation (Property 6, R3.3).
# ---------------------------------------------------------------------------

# The two contract-declared (additional_info) leftover columns, in their stable source order.
_ADDITIONAL_INFO_COLUMNS = ["Ondertekening", "Naam voor akkoord"]


@settings(max_examples=100)
@given(
    onder=st.one_of(st.just(""), _free_text),
    naam=st.one_of(st.just(""), _free_text),
)
def test_property_additional_info_concatenates_in_stable_order_with_pipe(onder, naam):
    """(additional_info)-routed leftovers concatenate as `Label: value`, ` | `, source order.

    Only NON-EMPTY cells contribute; the order is the stable source-column order
    (``Ondertekening`` before ``Naam voor akkoord``); the delimiter is ` | ` (R3.3).

    Validates: Requirements 3.3
    """
    rec = map_hdcn_row(
        _raw(**{"Ondertekening": onder, "Naam voor akkoord": naam}),
        region_canonicalizer=_REGION,
    )
    # Build the EXPECTED concatenation from the observed rule: `Label: value` for each non-empty
    # cell, in stable source-column order, joined by ` | `.
    parts = []
    if onder:
        parts.append(f"Ondertekening: {onder}")
    if naam:
        parts.append(f"Naam voor akkoord: {naam}")
    expected = " | ".join(parts)

    if expected:
        assert rec["overlay"]["additional_info"] == expected
    else:
        # No leftover contributed → the field stays UNSET (not an empty string).
        assert "additional_info" not in rec["overlay"]
