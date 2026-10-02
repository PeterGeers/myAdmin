"""
S5 Task 4.1 — tests for the h-dcn member **backfill** (dry-run first, non-destructive).

Three layers, none of which touch Google or live DynamoDB (per the task constraints):

- **The pure transform** (``map_hdcn_row``): fixed/overlay split, ``tenant_id`` +
  ``overlay.region`` scope-field normalization (S5d D1 — no ``scope_values`` bucket),
  membership_type → catalog code mapping, and loud validation failure on a bad row. No I/O.
- **The source adapters** (``FileSourceAdapter`` / ``IterableSourceAdapter``): read a CSV/JSON
  fixture READ-ONLY; the legacy-DynamoDB adapter is a deliberate stub.
- **The runner** (``scripts/onboarding/members/h-dcn/backfill-hdcn-members.py``): dry-run
  writes NOTHING and emits a
  fidelity report; ``--apply`` calls ``save_member`` on a fake repository; a member-number
  conflict is REPORTED, not overwritten.

DynamoDB (for the ``--apply`` path) is faked with the same in-memory ``FakeDynamoTable`` /
``FakeDynamoClient`` used by ``test_members_repository.py`` — no moto, no live AWS — so the
repository's real uniqueness/conflict behaviour is exercised, not mocked away.

Validates: Requirements R5.2 (C6 repository, C3 fixed⊕overlay, data models; Property 7
reversibility / non-destructiveness; Property 6 uniqueness surfaced as a reported conflict)
"""

from __future__ import annotations

import importlib.util
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

from sam.members.migration.hdcn_backfill import (
    HDCN_TENANT_ID,
    ColumnShiftWarning,
    DuplicateHeaderConflict,
    FileSourceAdapter,
    GoogleSheetsSourceAdapter,
    IterableSourceAdapter,
    LegacyDynamoSourceAdapter,
    MembershipTypeMapper,
    RegionCanonicalizer,
    RowSkipped,
    RowTransformError,
    _parse_source_date,
    build_backfill_plan,
    build_position_tracked_row,
    contract_source_columns,
    detect_column_shift,
    map_hdcn_row,
)
from sam.members.repository import table_design as td
from sam.members.repository.members_repository import DynamoDbMembersRepository

# Reuse the faithful in-memory DynamoDB fakes from the repository tests. The tests directory
# (this file's own dir) is put on sys.path so the sibling module imports as a top-level name
# regardless of the pytest rootdir/invocation.
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from test_members_repository import FakeDynamoTable

FIXTURE = os.path.join(_REPO_ROOT, "sam", "tests", "fixtures", "hdcn_ledenbestand_sample.csv")


#: A synthetic region canonicalizer for the transform tests (D17 — tenant vocabulary is
#: INJECTED, never a core constant). Uses abstract North/South/East/West + a Drente→Drenthe
#: style alias so the alias path is exercised without any real tenant data.
_TEST_REGION_CANON = RegionCanonicalizer(
    ("North", "South", "East", "West"), aliases={"Noorden": "North"}
)


def _raw(**overrides):
    """A well-formed raw h-dcn source row (REAL Ledenbestand column headers), with overrides.

    Reflects the actual export (A.2): capitalized/multi-word headers, NO member_id column
    (the transform mints a uuid4). The authoritative human number is the ``SAM Code`` column
    (SAM Code identity change) — read verbatim as membership.member_number (default ``M01001``
    here; specific tests override it). Legacy ``Lidnummer`` is kept for reference only. No status
    column (defaults to active), Datum ondertekening → joined_date. Region defaults to a sample.
    """
    row = {
        "SAM Code": "M01001",
        "Lidnummer": "1001",
        "Voornaam": "Alex",
        "Achternaam": "de Vries",
        "E-mailadres": "alex@example.com",
        "Straat en huisnummer": "Dorpsstraat 1",
        "Soort lidmaatschap": "Erelid",
        "Datum ondertekening": "2010-01-01T00:00:00.000Z",
        "Regio": "North",
        "Type motor": "Honda CB500",
    }
    row.update(overrides)
    return row


def _map(**overrides):
    """map_hdcn_row over ``_raw(**overrides)`` with the synthetic region canonicalizer."""
    return map_hdcn_row(_raw(**overrides), region_canonicalizer=_TEST_REGION_CANON)


# ---------------------------------------------------------------------------
# The pure transform — map_hdcn_row
# ---------------------------------------------------------------------------


class TestMapHdcnRow:
    def test_stamps_the_pilot_tenant_id(self):
        rec = _map()
        assert rec["tenant_id"] == HDCN_TENANT_ID == "h-dcn"

    def test_splits_fixed_base_personal_and_membership(self):
        rec = _map()
        # Real headers → s5c canonical EN keys. birth_date is NOT imported (calculated field,
        # A.2). member_id is a MINTED uuid4 (no source column). member_number is READ verbatim
        # from the SAM Code column (default M01001). joined_date from the Datum ondertekening date.
        assert rec["personal"] == {
            "first_name": "Alex",
            "last_name": "de Vries",
            "email": "alex@example.com",
            "street": "Dorpsstraat 1",
        }
        assert rec["membership"]["member_number"] == "M01001"
        assert rec["membership"]["joined_date"] == "2010-01-01"
        assert rec["membership"]["status"] == "active"  # no status column → default active
        # member_id is a minted uuid4 (36 chars, 4 dashes), NOT the source Lidnummer.
        assert isinstance(rec["member_id"], str) and rec["member_id"].count("-") == 4
        assert rec["member_id"] != "1001"

    def test_status_defaults_to_active(self):
        # The export has NO status column → default to "active" (A.2 decision).
        assert _map()["membership"]["status"] == "active"

    def test_stores_region_on_the_overlay_field_as_a_scalar(self):
        # S5d D1/R3.4: scope is a PLAIN member field — the region lands on `overlay.region`
        # as a SCALAR (single-valued per scope field, R3.2), NOT a `scope_values` bucket/list.
        rec = _map(Regio="North")
        assert rec["overlay"]["region"] == "North"
        assert "scope_values" not in rec

    def test_canonicalizes_region_casing_via_injected_canonicalizer(self):
        # A.10/R9.2: the INJECTED canonicalizer folds variant spellings onto the canonical set.
        assert _map(Regio="south")["overlay"]["region"] == "South"

    def test_canonicalizes_region_separator_and_case_variants(self):
        assert _map(Regio="  EAST ")["overlay"]["region"] == "East"
        assert _map(Regio="wEsT")["overlay"]["region"] == "West"

    def test_region_alias_is_applied_before_canonical_match(self):
        # A.3: an alias (raw spelling scope_canon cannot fold) maps onto the canonical value.
        assert _map(Regio="Noorden")["overlay"]["region"] == "North"

    def test_unknown_region_is_preserved_not_dropped(self):
        # R9.3: an un-normalizable value is kept verbatim (surfaced by the R9.5 check), never
        # silently dropped nor forced to a wrong canonical value.
        rec = _map(Regio="Centraal")
        assert rec["overlay"]["region"] == "Centraal"

    def test_missing_region_omits_the_field(self):
        # An absent region omits the field entirely (no empty placeholder / no `scope_values`).
        rec = _map(Regio="")
        assert "region" not in rec["overlay"]
        assert "scope_values" not in rec

    def test_no_scope_values_bucket_is_written(self):
        # Clean break (D1): the member record has ZERO scope awareness — no `scope_values`.
        assert "scope_values" not in _map()

    def test_club_columns_land_on_canonical_overlay_keys(self):
        # s5m R2.3: club/motor columns land on the tenant's CANONICAL overlay keys (from the
        # mapping contract), NOT raw Dutch header keys. `Type motor` → overlay.motor_type,
        # `Kenteken` → overlay.license_plate.
        rec = _map(**{"Type motor": "Honda CB500", "Kenteken": "AB-12-CD"})
        assert rec["overlay"]["motor_type"] == "Honda CB500"
        assert rec["overlay"]["license_plate"] == "AB-12-CD"
        # No raw Dutch header key survives in overlay.
        assert "Type motor" not in rec["overlay"] and "Kenteken" not in rec["overlay"]
        # overlay must not contain fixed source columns
        assert "Achternaam" not in rec["overlay"] and "Lidnummer" not in rec["overlay"]

    def test_empty_named_column_is_dropped_not_folded_into_overlay(self):
        # The real export has a blank-header column. It must NOT land as overlay[""] — DynamoDB
        # rejects an empty attribute name ("Empty attribute name" on write). It is dropped.
        rec = _map(**{"": "junk value in a nameless column"})
        assert "" not in rec["overlay"]
        # No empty key anywhere in the record's dict groups (defensive).
        for group in ("personal", "membership", "overlay"):
            assert "" not in rec[group]

    def test_membership_type_is_mapped_to_a_catalog_code(self):
        assert _map(**{"Soort lidmaatschap": "Erelid"})["membership"]["membership_type"] == "erelid"
        assert _map(**{"Soort lidmaatschap": "Donateur"})["membership"]["membership_type"] == "donateur"
        assert _map(**{"Soort lidmaatschap": "Gewoon lid"})["membership"]["membership_type"] == "gewoon_lid"

    def test_bad_row_fails_loudly_missing_required_field(self):
        # No last name → validate_fixed_fields fails → RowTransformError.
        with pytest.raises(RowTransformError) as exc:
            _map(Achternaam="")
        assert "personal.last_name" in exc.value.reasons

    def test_member_number_is_read_verbatim_from_sam_code(self):
        # SAM Code identity change: member_number is READ from the SAM Code column verbatim
        # (a Member 'M#####'), NOT derived from Lidnummer.
        rec = _map(**{"SAM Code": "M06599"})
        assert rec["membership"]["member_number"] == "M06599"
        # member_id (internal uuid) is unchanged — still minted, decoupled from member_number.
        assert isinstance(rec["member_id"], str) and rec["member_id"].count("-") == 4

    def test_donateur_sam_code_imports_verbatim(self):
        # A Donateur now IMPORTS (no longer skipped): its SAM Code 'D#####' is the member_number.
        rec = _map(**{"SAM Code": "D00001"})
        assert rec["membership"]["member_number"] == "D00001"

    def test_contact_sam_code_imports_verbatim(self):
        # A contact/organisation row is keyed by its SAM Code 'C#####' (read verbatim), NOT by a
        # derived `C_<Achternaam>`. Lidnummer/Achternaam no longer drive the number.
        rec = _map(**{"SAM Code": "C00001", "Lidnummer": "", "Achternaam": "Sponsor BV"})
        assert rec["membership"]["member_number"] == "C00001"
        assert rec["member_id"]  # a stable uuid is still minted as the internal identity

    def test_meaningful_row_with_blank_sam_code_is_a_transform_error(self):
        # Transition rule (user-approved): a MEANINGFUL data row with a BLANK SAM Code is a
        # data-gap ERROR (reported, NOT written) — never silently derived from Lidnummer/name.
        with pytest.raises(RowTransformError) as exc:
            _map(**{"SAM Code": ""})
        assert "membership.member_number" in exc.value.reasons

    def test_malformed_sam_code_is_rejected_by_the_format(self):
        # The format regex accepts M#####/D#####/C##### and REJECTS a bad code (e.g. X00001):
        # a present-but-malformed SAM Code is a transform error, not a silent write.
        with pytest.raises(RowTransformError) as exc:
            _map(**{"SAM Code": "X00001"})
        assert "membership.member_number" in exc.value.reasons
        # Well-formed codes for all three classes are accepted.
        assert _map(**{"SAM Code": "M06599"})["membership"]["member_number"] == "M06599"
        assert _map(**{"SAM Code": "D00001"})["membership"]["member_number"] == "D00001"
        assert _map(**{"SAM Code": "C00001"})["membership"]["member_number"] == "C00001"

    def test_type_mapper_validates_against_known_codes(self):
        mapper = MembershipTypeMapper(known_codes=["erelid", "donateur"])
        # 'sponsor' is not in the known set → the row fails to map (loud mismatch).
        with pytest.raises(RowTransformError) as exc:
            map_hdcn_row(
                _raw(**{"Soort lidmaatschap": "Sponsor"}),
                type_mapper=mapper,
                region_canonicalizer=_TEST_REGION_CANON,
            )
        assert "membership.membership_type" in exc.value.reasons

    def test_transform_does_not_mutate_the_source_row(self):
        row = _raw()
        snapshot = dict(row)
        map_hdcn_row(row, region_canonicalizer=_TEST_REGION_CANON)
        assert row == snapshot  # pure — no mutation of the input (non-destructive)


# ---------------------------------------------------------------------------
# S5m Task 1 — duplicate-header position tracking + first-non-empty coalesce (R1)
# ---------------------------------------------------------------------------


class TestPositionTrackedRowBuilder:
    """The shared row-build helper makes repeated headers unique by column index (R1.1)."""

    def test_unique_headers_pass_through_unchanged(self):
        row = build_position_tracked_row(["A", "B", "C"], ["1", "2", "3"])
        assert row == {"A": "1", "B": "2", "C": "3"}

    def test_first_occurrence_keeps_bare_header_repeat_gets_col_index(self):
        # `E-mailadres` at col 1 (bare) and col 3 (→ `E-mailadres#3`). No dict clobber (R1.1).
        row = build_position_tracked_row(
            ["E-mailadres", "Naam", "E-mailadres"],
            ["peter@pgeer.nl", "Peter", ""],
        )
        assert row["E-mailadres"] == "peter@pgeer.nl"
        assert row["E-mailadres#3"] == ""
        assert list(row) == ["E-mailadres", "Naam", "E-mailadres#3"]

    def test_third_duplicate_gets_its_own_col_index(self):
        # Three `H-DCN Clubblad` columns → distinct keys, none lost (the col-2/col-3 example).
        row = build_position_tracked_row(
            ["H-DCN Clubblad", "H-DCN Clubblad", "H-DCN Clubblad"],
            ["Papier", "", "Digitaal"],
        )
        assert row == {
            "H-DCN Clubblad": "Papier",
            "H-DCN Clubblad#2": "",
            "H-DCN Clubblad#3": "Digitaal",
        }

    def test_short_value_row_pads_missing_cells_to_empty(self):
        row = build_position_tracked_row(["A", "B", "C"], ["1"])
        assert row == {"A": "1", "B": "", "C": ""}

    def test_blank_named_column_kept_under_empty_key_index_still_consumed(self):
        # A blank-named column keeps its empty key here (the transform drops it, R1.5); later
        # columns still keep their true 1-based position.
        row = build_position_tracked_row(["A", "", "B"], ["1", "junk", "2"])
        assert row[""] == "junk"
        assert row["A"] == "1"
        assert row["B"] == "2"


class TestDuplicateHeaderCoalesce:
    """map_hdcn_row strips `#<colindex>` to the base header and coalesces first-non-empty (R1.3/R1.4)."""

    def test_populated_value_survives_an_empty_duplicate(self):
        # The peter@pgeer.nl bug: col-1 populated email, an empty col-3 duplicate must NOT win.
        rec = map_hdcn_row(
            _raw(**{"E-mailadres": "peter@pgeer.nl", "E-mailadres#34": ""}),
            region_canonicalizer=_TEST_REGION_CANON,
        )
        assert rec["personal"]["email"] == "peter@pgeer.nl"

    def test_empty_first_then_populated_duplicate_coalesces(self):
        # First-non-empty in column ORDER: a blank base header, a populated indexed duplicate.
        rec = map_hdcn_row(
            _raw(**{"E-mailadres": "", "E-mailadres#34": "real@x.com"}),
            region_canonicalizer=_TEST_REGION_CANON,
        )
        assert rec["personal"]["email"] == "real@x.com"

    def test_overlay_duplicate_coalesces_on_base_header(self):
        # Duplicate club/overlay columns share a base and coalesce onto ONE canonical overlay
        # key (R1.4): `Type motor` → overlay.motor_type, first-non-empty across the duplicate.
        rec = map_hdcn_row(
            _raw(**{"Type motor": "", "Type motor#40": "Honda CB500"}),
            region_canonicalizer=_TEST_REGION_CANON,
        )
        assert rec["overlay"]["motor_type"] == "Honda CB500"
        assert "Type motor" not in rec["overlay"] and "Type motor#40" not in rec["overlay"]

    def test_conflict_keeps_first_and_reports_losing_indexed_column(self):
        # Two DIFFERENT non-empty emails share a base → first-in-order kept, loser reported by
        # its INDEXED name so the operator can reconcile the source (R1.6).
        conflicts: list[DuplicateHeaderConflict] = []
        rec = map_hdcn_row(
            _raw(**{"E-mailadres": "first@x.com", "E-mailadres#34": "second@x.com"}),
            region_canonicalizer=_TEST_REGION_CANON,
            conflicts=conflicts,
        )
        assert rec["personal"]["email"] == "first@x.com"
        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.losing_column == "E-mailadres#34"
        assert c.base_header == "E-mailadres"
        assert c.kept_value == "first@x.com"
        assert c.dropped_value == "second@x.com"

    def test_equal_duplicate_values_are_not_reported_as_conflicts(self):
        conflicts: list[DuplicateHeaderConflict] = []
        map_hdcn_row(
            _raw(**{"E-mailadres": "same@x.com", "E-mailadres#34": "same@x.com"}),
            region_canonicalizer=_TEST_REGION_CANON,
            conflicts=conflicts,
        )
        assert conflicts == []

    def test_blank_named_duplicate_column_is_still_dropped(self):
        # R1.5: the blank-named column (even as a position-tracked duplicate) never reaches overlay.
        rec = map_hdcn_row(
            _raw(**{"": "junk", "#9": "more junk"}),
            region_canonicalizer=_TEST_REGION_CANON,
        )
        assert "" not in rec["overlay"]
        for group in ("personal", "membership", "overlay"):
            assert "" not in rec[group]

    def test_membership_type_blank_duplicate_does_not_mask_populated_sibling(self):
        # A blank `Soort lidmaatschap` duplicate must not trigger a spurious "is required" (R1.4).
        rec = map_hdcn_row(
            _raw(**{"Soort lidmaatschap": "Erelid", "Soort lidmaatschap#9": ""}),
            region_canonicalizer=_TEST_REGION_CANON,
        )
        assert rec["membership"]["membership_type"] == "erelid"

    def test_no_conflicts_list_still_transforms(self):
        # `conflicts` is optional — the transform works without it (a genuine conflict is simply
        # resolved first-in-order and not surfaced).
        rec = map_hdcn_row(
            _raw(**{"E-mailadres": "first@x.com", "E-mailadres#34": "second@x.com"}),
            region_canonicalizer=_TEST_REGION_CANON,
        )
        assert rec["personal"]["email"] == "first@x.com"


# ---------------------------------------------------------------------------
# S5m Task 3 — the contract-driven transform: birth_date, canonical overlay keys,
# dispositions (calculated/excluded/additional_info) + per-rule conversions
# (date/gender/magazine/iban_or_payment), R0.3/R2.1..R2.7/R3.3/D0b/D2b.
# ---------------------------------------------------------------------------


class TestContractDrivenTransform:
    """map_hdcn_row drives fixed/overlay/dispositions from the loaded MappingContract (Task 3)."""

    # --- birth_date (R2.1 / R3.3) --------------------------------------------------------

    def test_birth_date_maps_from_iso_datetime_to_bare_date(self):
        # `Geboorte datum` (rule `date`) → personal.birth_date reduced to a bare YYYY-MM-DD.
        rec = _map(**{"Geboorte datum": "1975-04-12T00:00:00.000Z"})
        assert rec["personal"]["birth_date"] == "1975-04-12"

    def test_birth_date_absent_leaves_it_unset(self):
        # birth_date is OPTIONAL — an absent cell leaves it unset, never blocks the row (R2.1/R3.3).
        rec = _map()
        assert "birth_date" not in rec["personal"]

    def test_birth_date_unparseable_leaves_it_unset(self):
        # An unparseable date leaves the optional field unset (no default, no block, R2.1/R3.3).
        rec = _map(**{"Geboorte datum": "not a date"})
        assert "birth_date" not in rec["personal"]

    # --- gender / magazine enum conversions (R0.2) ---------------------------------------

    def test_gender_normalizes_dutch_to_tenant_enum(self):
        assert _map(Geslacht="Man")["personal"]["gender"] == "M"
        assert _map(Geslacht="Vrouw")["personal"]["gender"] == "V"
        assert _map(Geslacht="v")["personal"]["gender"] == "V"

    def test_magazine_maps_to_enum_with_geen_fallback(self):
        assert _map(Clubblad="Papier")["overlay"]["magazine_pref"] == "Papier"
        assert _map(Clubblad="Digitaal")["overlay"]["magazine_pref"] == "Digitaal"
        # empty / unrecognized → Geen fallback
        assert _map(Clubblad="rubbish")["overlay"]["magazine_pref"] == "Geen"

    # --- iban_or_payment conditional split (R0.3 / R2.3) ---------------------------------

    def test_iban_value_sets_iban_and_incasso_payment_method(self):
        rec = _map(Bankrekeningnummer="NL91ABNA0417164300")
        assert rec["overlay"]["iban"] == "NL91ABNA0417164300"
        assert rec["overlay"]["payment_method"] == "incasso"

    def test_non_iban_value_sets_payment_method_text_only(self):
        rec = _map(Bankrekeningnummer="contant per kas")
        assert "iban" not in rec["overlay"]
        assert rec["overlay"]["payment_method"] == "contant per kas"

    def test_empty_bank_number_leaves_both_unset(self):
        rec = _map(Bankrekeningnummer="")
        assert "iban" not in rec["overlay"] and "payment_method" not in rec["overlay"]

    # --- dispositions: calculated / excluded / additional_info (R2.2/R2.6/R2.7) ----------

    def test_calculated_column_is_not_stored(self):
        # `Geboortejaar` is a (calculated) disposition → NOT stored anywhere (R2.2/R2.6).
        rec = _map(Geboortejaar="1975")
        assert "Geboortejaar" not in rec["overlay"]
        assert "additional_info" not in rec["overlay"] or "Geboortejaar" not in rec["overlay"].get(
            "additional_info", ""
        )

    def test_excluded_column_is_dropped(self):
        # `Bestuursfunctie` is an (excluded) disposition → dropped, not in overlay/additional_info.
        rec = _map(Bestuursfunctie="Voorzitter")
        assert "Bestuursfunctie" not in rec["overlay"]
        assert "Voorzitter" not in rec["overlay"].get("additional_info", "")

    def test_additional_info_disposition_is_concatenated(self):
        # `Ondertekening` is an (additional_info) disposition → concatenated as `Label: value`.
        rec = _map(Ondertekening="yes")
        assert rec["overlay"]["additional_info"] == "Ondertekening: yes"

    def test_unmapped_kept_column_goes_to_additional_info(self):
        # An unknown non-empty column (no mapping, no disposition) is concatenated into
        # overlay.additional_info as `Label: value` — never a raw Dutch overlay key (R2.4).
        rec = _map(**{"Iets Onbekends": "some value"})
        assert rec["overlay"]["additional_info"] == "Iets Onbekends: some value"

    def test_multiple_additional_info_join_with_pipe_in_source_order(self):
        # Multiple leftovers join with ` | ` in stable SOURCE-COLUMN order (R2.7).
        rec = map_hdcn_row(
            _raw(**{"Ondertekening": "sig", "Naam voor akkoord": "Alex"}),
            region_canonicalizer=_TEST_REGION_CANON,
        )
        assert rec["overlay"]["additional_info"] == "Ondertekening: sig | Naam voor akkoord: Alex"

    def test_additional_info_unset_when_nothing_contributes(self):
        # No leftover columns → the field is left unset (not an empty string, R2.7).
        rec = _map()
        assert "additional_info" not in rec["overlay"]

    def test_no_raw_dutch_header_key_appears_in_overlay(self):
        # The whole point of R2: overlay carries canonical keys only, never raw Dutch headers.
        rec = _map(**{"Type motor": "Honda", "Kenteken": "AB-12-CD", "Clubblad": "Papier"})
        for raw_key in ("Type motor", "Kenteken", "Clubblad", "Regio", "Motormerk"):
            assert raw_key not in rec["overlay"]

    # --- R1.7: an EXCLUDED duplicate targeted by its indexed name drops only that duplicate ----

    def test_excluding_hdcn_clubblad_indexed_duplicate_drops_only_that_column(self):
        # R1.7 / R2.6: the authored contract excludes the near-duplicate `H-DCN Clubblad`
        # (col 29) AND its position-tracked duplicate `H-DCN Clubblad#35` — both strip to the
        # SAME base header `h-dcn clubblad` (a distinct base from the MAPPED `Clubblad` at
        # col 21 → magazine_pref). So the excluded H-DCN Clubblad copies are dropped (neither
        # stored nor folded into additional_info), while the mapped `Clubblad` magazine
        # preference is preserved — excluding the duplicate never touches the real target.
        rec = map_hdcn_row(
            _raw(
                **{
                    "Clubblad": "Papier",          # col 21 → overlay.magazine_pref (MAPPED)
                    "H-DCN Clubblad": "junk-29",    # base `h-dcn clubblad` → (excluded)
                    "H-DCN Clubblad#35": "junk-35",  # indexed duplicate → (excluded), same base
                }
            ),
            region_canonicalizer=_TEST_REGION_CANON,
        )
        # The mapped magazine preference survives untouched.
        assert rec["overlay"]["magazine_pref"] == "Papier"
        # The excluded H-DCN Clubblad duplicates are dropped — not on overlay, not in
        # additional_info, and their values appear nowhere on the record.
        assert "junk-29" not in rec["overlay"].get("additional_info", "")
        assert "junk-35" not in rec["overlay"].get("additional_info", "")
        for group in ("personal", "membership", "overlay"):
            assert not any(
                "junk-" in str(v) for v in rec[group].values()
            ), f"excluded H-DCN Clubblad value leaked into {group}"


# ---------------------------------------------------------------------------
# Date parsing — the real h-dcn sheet stores Dutch d-m-yyyy (day-first), NOT ISO.
# _parse_source_date must accept BOTH Dutch d-m-yyyy (with an optional trailing time)
# AND the ISO form the old fixture uses, normalizing every parse to a bare YYYY-MM-DD.
# ---------------------------------------------------------------------------


class TestParseSourceDate:
    """The shared date helper — one code path for joined_date AND birth_date (no drift)."""

    def test_parses_dutch_day_month_year(self):
        # Real `Datum ondertekening` samples (d-m-yyyy, no time).
        assert _parse_source_date("13-4-2023") == "2023-04-13"
        assert _parse_source_date("22-11-2025") == "2025-11-22"

    def test_dutch_date_is_day_first_not_month_first(self):
        # `4-5-2026` = 4 May 2026 → month is 05, NOT 04 (day-first disambiguation, user-confirmed).
        assert _parse_source_date("4-5-2026") == "2026-05-04"

    def test_parses_dutch_datetime_keeping_only_the_date_part(self):
        # Real `Tijdstempel` samples carry a trailing ` hh:mm:ss` — the date part only is kept.
        assert _parse_source_date("4-5-2026 10:59:37") == "2026-05-04"
        assert _parse_source_date("26-3-2026 11:50:40") == "2026-03-26"
        # A bare ` hh:mm` (no seconds) is also tolerated.
        assert _parse_source_date("4-5-2026 10:59") == "2026-05-04"

    def test_still_parses_iso_datetime_from_the_old_fixture(self):
        # ISO must STILL parse (the fixture uses `2010-01-01T00:00:00.000Z`) — don't break it.
        assert _parse_source_date("2010-01-01T00:00:00.000Z") == "2010-01-01"
        assert _parse_source_date("1975-04-12") == "1975-04-12"

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "   ",
            "garbage",
            "32-1-2020",   # bad day (>31 / impossible)
            "4-13-2020",   # bad month (>12)
            "0-5-2026",    # day 0 is not a valid calendar day
            None,
        ],
    )
    def test_returns_none_for_empty_or_unparseable_or_out_of_range(self, bad):
        assert _parse_source_date(bad) is None


# ---------------------------------------------------------------------------
# joined_date derivation — Dutch dates parse (no more "defaults to today" bug), and
# the fallback order Datum ondertekening -> Tijdstempel -> Aanmeldingsjaar -> today.
# ---------------------------------------------------------------------------


class TestJoinedDateDerivation:
    def test_joined_date_from_dutch_datum_ondertekening(self):
        # The core bug: a Dutch `Datum ondertekening` used to fall through to today. Now it
        # parses to the real date (assert it is the parsed source date, NOT today).
        import datetime as _dt

        rec = _map(**{"Datum ondertekening": "13-4-2023"})
        assert rec["membership"]["joined_date"] == "2023-04-13"
        assert rec["membership"]["joined_date"] != _dt.date.today().isoformat()

    def test_datum_ondertekening_wins_over_tijdstempel(self):
        # Priority: the signature date beats the timestamp even though Tijdstempel is col 0.
        rec = _map(
            **{"Datum ondertekening": "13-4-2023", "Tijdstempel": "4-5-2026 10:59:37"}
        )
        assert rec["membership"]["joined_date"] == "2023-04-13"

    def test_falls_back_to_tijdstempel_when_signature_date_empty(self):
        # No `Datum ondertekening` → the Tijdstempel timestamp supplies joined_date (its date part).
        rec = _map(**{"Datum ondertekening": "", "Tijdstempel": "4-5-2026 10:59:37"})
        assert rec["membership"]["joined_date"] == "2026-05-04"

    def test_falls_back_to_aanmeldingsjaar_year_when_both_dates_empty(self):
        # Both date inputs empty → the bare registration year → <year>-01-01.
        rec = _map(
            **{"Datum ondertekening": "", "Tijdstempel": "", "Aanmeldingsjaar": "2019"}
        )
        assert rec["membership"]["joined_date"] == "2019-01-01"

    def test_iso_signature_date_still_parses(self):
        # The old ISO fixture form still works (default _raw uses it).
        assert _map()["membership"]["joined_date"] == "2010-01-01"


# ---------------------------------------------------------------------------
# birth_date — the real sheet's `Geboorte datum` is Dutch d-m-yyyy (day-first) too.
# ---------------------------------------------------------------------------


class TestBirthDateDutch:
    def test_birth_date_parses_dutch_day_first(self):
        rec = _map(**{"Geboorte datum": "12-4-1975"})
        assert rec["personal"]["birth_date"] == "1975-04-12"

    def test_birth_date_absent_leaves_it_unset(self):
        assert "birth_date" not in _map()["personal"]

    def test_birth_date_unparseable_leaves_it_unset(self):
        assert "birth_date" not in _map(**{"Geboorte datum": "not a date"})["personal"]


# ---------------------------------------------------------------------------
# Tijdstempel must be a MAPPED joined_date source now — never an unmapped/extra column.
# ---------------------------------------------------------------------------


class TestTijdstempelIsMapped:
    def test_tijdstempel_is_a_recognized_contract_source_column(self):
        # Adding Tijdstempel as a joined_date coalesce input reclassifies it as MAPPED — the
        # contract's recognized source columns must include it (no longer unmapped/extra).
        from sam.members.migration.hdcn_backfill import _load_default_contract

        known = contract_source_columns(_load_default_contract())
        assert "tijdstempel" in known

    def test_tijdstempel_value_does_not_leak_into_additional_info(self):
        # A mapped joined_date source must not also be folded into overlay.additional_info.
        rec = _map(Tijdstempel="4-5-2026 10:59:37")
        assert "Tijdstempel" not in rec["overlay"].get("additional_info", "")


# ---------------------------------------------------------------------------
# Source adapters — read-only
# ---------------------------------------------------------------------------


class TestSourceAdapters:
    def test_file_adapter_reads_the_csv_fixture(self):
        adapter = FileSourceAdapter(FIXTURE)
        rows = list(adapter.rows())
        assert len(rows) == 4
        assert rows[0]["Lidnummer"] == "1001"
        assert rows[0]["Voornaam"] == "Alex"
        assert rows[0]["Achternaam"] == "de Vries"

    def test_file_adapter_reads_json(self, tmp_path):
        path = tmp_path / "export.json"
        path.write_text(json.dumps([_raw(), _raw(Lidnummer="1002")]), encoding="utf-8")
        rows = list(FileSourceAdapter(str(path)).rows())
        assert [r["Lidnummer"] for r in rows] == ["1001", "1002"]

    def test_file_adapter_reads_json_rows_envelope(self, tmp_path):
        path = tmp_path / "export.json"
        path.write_text(json.dumps({"rows": [_raw()]}), encoding="utf-8")
        assert len(list(FileSourceAdapter(str(path)).rows())) == 1

    def test_file_adapter_does_not_write_the_source(self, tmp_path):
        # Reading must not change the file on disk (non-destructive, R5.2).
        path = tmp_path / "export.csv"
        original = "Lidnummer,Achternaam,E-mailadres,Soort lidmaatschap,Datum ondertekening,Regio\n1001,Alex,a@x.com,Erelid,2010-01-01,North\n"
        path.write_text(original, encoding="utf-8")
        list(FileSourceAdapter(str(path)).rows())
        assert path.read_text(encoding="utf-8") == original

    def test_iterable_adapter_hands_out_copies(self):
        rows = [_raw()]
        adapter = IterableSourceAdapter(rows)
        out = list(adapter.rows())
        out[0]["Achternaam"] = "changed"
        assert rows[0]["Achternaam"] == "de Vries"  # source untouched

    def test_legacy_dynamo_adapter_is_a_readonly_stub(self):
        adapter = LegacyDynamoSourceAdapter("LegacyMembers", region="eu-west-1")
        assert "READ-ONLY" in adapter.describe()
        with pytest.raises(NotImplementedError):
            list(adapter.rows())

    def test_filesource_adapter_position_tracks_duplicate_csv_headers(self, tmp_path):
        # R1.2: the CSV path reads the RAW header row and applies the SAME position tracking as
        # the sheet adapter — a duplicate header becomes `<header>#<colindex>`, NOT collapsed by
        # csv.DictReader. The populated col-1 email survives the empty col-3 duplicate.
        path = tmp_path / "dupes.csv"
        path.write_text(
            "E-mailadres,Naam,E-mailadres\npeter@pgeer.nl,Peter,\n",
            encoding="utf-8",
        )
        rows = list(FileSourceAdapter(str(path)).rows())
        assert len(rows) == 1
        # First occurrence keeps the bare header; the duplicate is disambiguated by its col index.
        assert rows[0]["E-mailadres"] == "peter@pgeer.nl"
        assert rows[0]["E-mailadres#3"] == ""
        assert "Naam" in rows[0]

    def test_filesource_adapter_pads_short_csv_rows(self, tmp_path):
        # A short data row (fewer cells than headers) pads missing cells to "" — every header
        # still gets a value (parity with the sheet adapter's matrix padding, R4.5).
        path = tmp_path / "short.csv"
        path.write_text("A,B,C\n1\n", encoding="utf-8")
        rows = list(FileSourceAdapter(str(path)).rows())
        assert rows == [{"A": "1", "B": "", "C": ""}]


class TestGoogleSheetsSourceAdapter:
    """The read-only, lazy Google Sheets adapter — tested WITHOUT any network (D5/R4)."""

    def test_rows_from_matrix_position_tracks_duplicate_headers(self):
        # R4.5/R1.1: a repeated header in the value matrix becomes a distinct `<header>#<colindex>`
        # key so no column is lost — parity with build_position_tracked_row / the file adapter.
        matrix = [
            ["E-mailadres", "Naam", "E-mailadres"],
            ["peter@pgeer.nl", "Peter", ""],
        ]
        rows = GoogleSheetsSourceAdapter._rows_from_matrix(matrix)
        assert rows == [
            {"E-mailadres": "peter@pgeer.nl", "Naam": "Peter", "E-mailadres#3": ""}
        ]

    def test_rows_from_matrix_pads_short_rows_to_header_width(self):
        # Sheets omits trailing empty cells → a short row is padded to the header width so every
        # header always gets a value (R4.5).
        matrix = [["A", "B", "C"], ["1"], ["1", "2", "3"]]
        rows = GoogleSheetsSourceAdapter._rows_from_matrix(matrix)
        assert rows == [
            {"A": "1", "B": "", "C": ""},
            {"A": "1", "B": "2", "C": "3"},
        ]

    def test_rows_from_matrix_empty_matrix_yields_no_rows(self):
        assert GoogleSheetsSourceAdapter._rows_from_matrix([]) == []
        # Header-only (no data rows) → no rows.
        assert GoogleSheetsSourceAdapter._rows_from_matrix([["A", "B"]]) == []

    def test_rows_from_matrix_feeds_the_transform_end_to_end(self):
        # The adapter's row shape is what map_hdcn_row consumes — a duplicate email column
        # coalesces first-non-empty exactly like the file source (source-agnostic transform).
        matrix = [
            ["SAM Code", "Lidnummer", "Voornaam", "Achternaam", "Soort lidmaatschap", "E-mailadres", "E-mailadres"],
            ["M01001", "1001", "Alex", "de Vries", "Erelid", "peter@pgeer.nl", ""],
        ]
        rows = GoogleSheetsSourceAdapter._rows_from_matrix(matrix)
        rec = map_hdcn_row(rows[0], region_canonicalizer=_TEST_REGION_CANON)
        assert rec["personal"]["email"] == "peter@pgeer.nl"
        assert rec["membership"]["member_number"] == "M01001"

    def test_init_requires_an_id_or_a_name(self):
        with pytest.raises(ValueError):
            GoogleSheetsSourceAdapter()

    def test_describe_names_the_sheet_and_marks_readonly(self):
        by_id = GoogleSheetsSourceAdapter(spreadsheet_id="abc123", worksheet="Ledenbestand")
        assert "abc123" in by_id.describe()
        assert "Ledenbestand" in by_id.describe()
        assert "READ-ONLY" in by_id.describe()
        by_name = GoogleSheetsSourceAdapter(spreadsheet_name="HDCN Ledenbestand 2026")
        assert "HDCN Ledenbestand 2026" in by_name.describe()
        assert "READ-ONLY" in by_name.describe()

    def test_missing_credentials_file_fails_fast_with_guidance(self, tmp_path):
        # R4.3: a missing key file raises FileNotFoundError with actionable setup guidance.
        adapter = GoogleSheetsSourceAdapter(
            spreadsheet_id="abc123",
            credentials_file=str(tmp_path / "does-not-exist.json"),
        )
        with pytest.raises(FileNotFoundError) as exc:
            adapter._load_credentials()
        assert "--credentials" in str(exc.value)

    def test_invalid_credentials_json_fails_fast(self, tmp_path):
        # R4.3: a file that is not valid JSON (or not a service-account key) fails fast.
        bad = tmp_path / "bad.json"
        bad.write_text("not json {", encoding="utf-8")
        adapter = GoogleSheetsSourceAdapter(spreadsheet_id="abc123", credentials_file=str(bad))
        with pytest.raises(FileNotFoundError):
            adapter._load_credentials()

    def test_non_service_account_credentials_file_fails_fast(self, tmp_path):
        # A valid JSON that is an OAuth client secret / template (not a service account) is rejected.
        tmpl = tmp_path / "client.json"
        tmpl.write_text(json.dumps({"installed": {"client_id": "x"}}), encoding="utf-8")
        adapter = GoogleSheetsSourceAdapter(spreadsheet_id="abc123", credentials_file=str(tmpl))
        with pytest.raises(FileNotFoundError):
            adapter._load_credentials()

    def test_a1_range_quotes_worksheet_and_defaults(self):
        assert GoogleSheetsSourceAdapter(spreadsheet_id="x")._a1_range() == "A1:ZZ"
        assert (
            GoogleSheetsSourceAdapter(spreadsheet_id="x", worksheet="Ledenbestand")._a1_range()
            == "'Ledenbestand'!A1:ZZ"
        )
        assert (
            GoogleSheetsSourceAdapter(spreadsheet_id="x", cell_range="Sheet1!A1:C9")._a1_range()
            == "Sheet1!A1:C9"
        )


class TestLazyGoogleImports:
    """Importing hdcn_backfill must NOT import any Google client library (R4.4)."""

    def test_importing_hdcn_backfill_does_not_import_google_libs(self):
        # R4.4: the SAM Lambda runtime ships NO Google libs — importing the transform module must
        # never pull them in. Every google/googleapiclient import lives INSIDE adapter methods.
        # Import in a subprocess so this test is independent of whatever else the suite imported.
        import subprocess

        code = (
            "import sys, os\n"
            f"sys.path.insert(0, {_REPO_ROOT!r})\n"
            f"sys.path.insert(0, {_BACKEND_SRC!r})\n"
            "import sam.members.migration.hdcn_backfill\n"
            "leaked = [m for m in sys.modules if m == 'google' or m.startswith('google.') "
            "or m == 'googleapiclient' or m.startswith('googleapiclient.')]\n"
            "assert not leaked, f'Google libs imported at module load: {leaked}'\n"
            "print('OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout


# ---------------------------------------------------------------------------
# build_backfill_plan — the fidelity plan (non-destructive read)
# ---------------------------------------------------------------------------


class TestBackfillPlan:
    def test_plan_transforms_all_good_rows(self):
        adapter = IterableSourceAdapter([_raw(), _raw(**{"SAM Code": "M01002"})])
        plan = build_backfill_plan(adapter, region_canonicalizer=_TEST_REGION_CANON)
        assert plan.source_row_count == 2
        assert plan.ok_count == 2
        assert plan.error_count == 0
        assert plan.tenant_id == "h-dcn"

    def test_plan_collects_errors_without_aborting(self):
        adapter = IterableSourceAdapter(
            [_raw(), _raw(**{"SAM Code": "M01002", "Achternaam": ""})]  # 2nd is bad (no last name)
        )
        plan = build_backfill_plan(adapter, region_canonicalizer=_TEST_REGION_CANON)
        assert plan.ok_count == 1
        assert plan.error_count == 1

    def test_plan_flags_but_imports_duplicate_member_numbers_in_batch(self):
        # s5k: a reused member number (a repeated SAM Code) is a DATA-QUALITY warning, not a
        # reason to drop members. The uniqueness guard is gone, so BOTH occurrences are imported
        # AND the duplicate is reported.
        adapter = IterableSourceAdapter([_raw(**{"SAM Code": "M01001"}), _raw(**{"SAM Code": "M01001"})])
        plan = build_backfill_plan(adapter, region_canonicalizer=_TEST_REGION_CANON)
        # "M01001" is the duplicate key; BOTH minted uuids are recorded (reported).
        assert "M01001" in plan.duplicate_member_numbers
        assert len(plan.duplicate_member_numbers["M01001"]) == 2
        # Both rows are imported (nothing skipped for a duplicate number).
        assert plan.ok_count == 2
        assert plan.skipped_count == 0

    def test_plan_records_rows_missing_region(self):
        # A row with no region omits overlay.region → recorded in rows_missing_region (by the
        # MINTED member_id, a uuid4).
        adapter = IterableSourceAdapter([_raw(Regio="")])
        plan = build_backfill_plan(adapter, region_canonicalizer=_TEST_REGION_CANON)
        assert len(plan.rows_missing_region) == 1
        assert plan.rows_missing_region[0] == plan.transformed[0].member_id

    def test_contact_is_imported_via_its_sam_code_not_skipped(self):
        # A contact/organisation row is imported via its authoritative C##### SAM Code (read
        # verbatim), NOT skipped and NOT derived from the name. The member and the contact carry
        # distinct SAM Codes → no duplicate bucket.
        adapter = IterableSourceAdapter(
            [_raw(), _raw(**{"SAM Code": "C00001", "Lidnummer": "", "Achternaam": "Sponsor BV"})]
        )
        plan = build_backfill_plan(adapter, region_canonicalizer=_TEST_REGION_CANON)
        assert plan.ok_count == 2
        assert plan.error_count == 0
        assert plan.skipped_count == 0
        assert plan.duplicate_member_numbers == {}  # distinct numbers never bucket as duplicates
        numbers = sorted(t.member_number for t in plan.transformed)
        assert numbers == ["C00001", "M01001"]

    def test_field_mapping_summary_counts_populated_fields(self):
        adapter = IterableSourceAdapter([_raw(), _raw(**{"SAM Code": "M01002"})])
        summary = build_backfill_plan(
            adapter, region_canonicalizer=_TEST_REGION_CANON
        ).field_mapping_summary()
        assert summary["membership.member_number"] == 2
        assert summary["personal.last_name"] == 2
        # S5d D1: the scope field is a plain `overlay.region` field now (no `scope_values`).
        assert summary["overlay.region"] == 2
        # s5m R2.3: `_raw()`'s `Type motor` lands on the canonical overlay key motor_type.
        assert summary["overlay.motor_type"] == 2


# ---------------------------------------------------------------------------
# The runner script — dry-run / --apply / duplicate-number warning
# ---------------------------------------------------------------------------


def _load_runner_module():
    """Import the hyphen-named runner script by path (not a valid module name)."""
    path = os.path.join(
        _REPO_ROOT, "scripts", "onboarding", "members", "h-dcn", "backfill-hdcn-members.py"
    )
    spec = importlib.util.spec_from_file_location("backfill_hdcn_members", path)
    module = importlib.util.module_from_spec(spec)
    # Register BEFORE exec_module: the runner defines @dataclass classes (ReconcilePlan), and
    # @dataclass resolves its module via sys.modules[cls.__module__] during class creation — an
    # unregistered by-path module makes that lookup return None (AttributeError on load).
    sys.modules["backfill_hdcn_members"] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner_module()


@pytest.fixture()
def members_env(monkeypatch):
    """MEMBERS_TABLE + region set (fail-fast resolution passes); no endpoint (irrelevant here)."""
    monkeypatch.setenv(td.MEMBERS_TABLE_ENV_VAR, "sam-members-test")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.delenv("AWS_ENDPOINT_URL_DYNAMODB", raising=False)
    return monkeypatch


@pytest.fixture()
def fake_repo():
    """A real DynamoDbMembersRepository backed by the in-memory FakeDynamoTable."""
    table = FakeDynamoTable()
    return DynamoDbMembersRepository(table=table, client=table.meta.client)


class TestRunnerDryRun:
    def test_dry_run_writes_nothing(self, members_env, fake_repo, capsys):
        rc = runner.backfill(FIXTURE, region="eu-west-1", apply=False, repo=fake_repo)
        assert rc == 0
        # Nothing persisted — the repository partition is empty.
        assert fake_repo.list_members("h-dcn") == []

    def test_dry_run_emits_a_fidelity_report(self, members_env, fake_repo, capsys):
        runner.backfill(FIXTURE, region="eu-west-1", apply=False, repo=fake_repo)
        out = capsys.readouterr().out
        assert "fidelity report" in out
        assert "DRY-RUN" in out
        assert "sam-members-test" in out          # resolved target table
        assert "per-field mapping summary" in out
        assert "source rows   : 4" in out

    def test_dry_run_is_the_cli_default(self, members_env, capsys, monkeypatch):
        # main() without --apply must not write. Inject nothing → dry-run never builds a repo.
        rc = runner.main(["--source", FIXTURE, "--tenant", "h-dcn"])
        assert rc == 0
        assert "DRY-RUN" in capsys.readouterr().out

    def test_fail_fast_when_members_table_missing(self, monkeypatch, capsys):
        monkeypatch.delenv(td.MEMBERS_TABLE_ENV_VAR, raising=False)
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        rc = runner.main(["--source", FIXTURE, "--tenant", "h-dcn"])
        assert rc == 1  # DynamoDBConfigError surfaced as exit 1


class TestRunnerApply:
    def test_apply_saves_each_record_via_the_repository(self, members_env, fake_repo, capsys):
        rc = runner.backfill(FIXTURE, region="eu-west-1", apply=True, repo=fake_repo)
        assert rc == 0
        listed = fake_repo.list_members("h-dcn")
        # member_id is a MINTED uuid4 now — identify members by their shaped member_number.
        numbers = sorted(m["membership"]["member_number"] for m in listed)
        assert numbers == ["M01001", "M01002", "M01003", "M01004"]
        # tenant stamped + scope field + overlay landed via the transform (S5d D1: the scope
        # value lands on the plain `overlay.region` field, a scalar — no `scope_values` bucket).
        m1 = next(m for m in listed if m["membership"]["member_number"] == "M01001")
        assert m1["tenant_id"] == "h-dcn"
        # No --members-config here → region kept verbatim (the fixture already uses "North").
        assert m1["overlay"]["region"] == "North"
        assert "scope_values" not in m1
        # s5m R2.3: `Kenteken` lands on the canonical overlay key license_plate; the fixture's
        # unmapped `motor` column is concatenated into overlay.additional_info (R2.7), not a raw key.
        assert m1["overlay"]["license_plate"] == "AB-12-CD"
        assert m1["overlay"]["additional_info"] == "motor: Honda CB500"
        assert "motor" not in m1["overlay"]
        assert m1["membership"]["membership_type"] == "erelid"

    def test_apply_imports_duplicate_numbers_both_written(self, members_env, fake_repo, capsys, tmp_path):
        # s5k: two rows share Lidnummer 1001 (different people). The uniqueness guard is gone, so
        # BOTH are written (distinct minted member_ids); the duplicate is a reported data-quality
        # warning, not a block. The data owner reconciles the recycled number afterwards.
        export = tmp_path / "dupes.json"
        export.write_text(
            json.dumps(
                [
                    _raw(Lidnummer="1001", Achternaam="Alex"),
                    _raw(Lidnummer="1001", Achternaam="Bram"),
                ]
            ),
            encoding="utf-8",
        )
        rc = runner.backfill(str(export), region="eu-west-1", apply=True, repo=fake_repo)
        assert rc == 0
        listed = fake_repo.list_members("h-dcn")
        assert len(listed) == 2  # both written under distinct member_ids
        assert {m["membership"]["member_number"] for m in listed} == {"M01001"}
        assert len({m["member_id"] for m in listed}) == 2
        # The duplicate is surfaced in the fidelity report (a warning, not a skip).
        assert "DUPLICATE member numbers" in capsys.readouterr().out

    def test_apply_refuses_a_batch_with_mapping_errors(self, members_env, fake_repo, capsys, tmp_path):
        export = tmp_path / "bad.json"
        export.write_text(
            json.dumps([_raw(), _raw(Lidnummer="1002", Achternaam="", Voornaam="")]),
            encoding="utf-8",
        )
        rc = runner.backfill(str(export), region="eu-west-1", apply=True, repo=fake_repo)
        assert rc == 2  # refused
        # Nothing written because the batch had an unmappable row.
        assert fake_repo.list_members("h-dcn") == []

    def test_apply_writes_one_member_per_row(self, members_env, fake_repo, tmp_path):
        export = tmp_path / "one.json"
        export.write_text(json.dumps([_raw(Lidnummer="1001")]), encoding="utf-8")
        assert runner.backfill(str(export), region="eu-west-1", apply=True, repo=fake_repo) == 0
        listed = fake_repo.list_members("h-dcn")
        assert len(listed) == 1
        assert listed[0]["membership"]["member_number"] == "M01001"


# ---------------------------------------------------------------------------
# S5c Task 6.2 — the runnable host-script CLI (required --tenant, no default;
# unmapped/extra columns tolerated + listed; tenant threaded into the writes).
# ---------------------------------------------------------------------------


class TestRunnerCliTenant:
    """The importer is a runnable host script with a REQUIRED --tenant (no default tenant)."""

    def test_tenant_is_a_required_cli_arg(self, members_env, capsys):
        # argparse must reject a missing --tenant (SystemExit(2)) — no hardcoded/default tenant.
        with pytest.raises(SystemExit) as exc:
            runner.main(["--source", FIXTURE])
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "--tenant" in err

    def test_dry_run_report_names_the_supplied_tenant(self, members_env, capsys):
        rc = runner.main(["--source", FIXTURE, "--tenant", "h-dcn"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "tenant        : h-dcn" in out

    def test_apply_stamps_the_supplied_tenant_not_a_default(self, members_env, fake_repo, tmp_path):
        # A non-pilot tenant proves the stamp comes from --tenant, never a hardcoded literal.
        export = tmp_path / "one.json"
        export.write_text(json.dumps([_raw(**{"SAM Code": "M09001"})]), encoding="utf-8")
        rc = runner.backfill(str(export), region="eu-west-1", apply=True, tenant_id="other-org", repo=fake_repo)
        assert rc == 0
        # The record landed in the "other-org" partition, stamped with that tenant.
        assert fake_repo.list_members("h-dcn") == []
        other = fake_repo.list_members("other-org")
        assert len(other) == 1
        assert other[0]["tenant_id"] == "other-org"
        assert other[0]["membership"]["member_number"] == "M09001"

    def test_dry_run_lists_unmapped_extra_columns(self, members_env, capsys):
        # s5m single-source cleanup: the classifier now judges mapped-vs-unmapped against the
        # authored MAPPING CONTRACT (the CSV), not a stale in-code dict. The fixture's lower-case
        # `motor` column has NO contract target (folded into overlay.additional_info) → it is the
        # tolerated unmapped/extra column, LISTED in the report (task 6.2 OUT-scope). `Kenteken`
        # IS a contract target now (overlay.license_plate) → it must NOT be listed as unmapped.
        runner.main(["--source", FIXTURE, "--tenant", "h-dcn"])
        out = capsys.readouterr().out
        assert "unmapped / extra source columns" in out
        section = out.split("unmapped / extra source columns")[1].split("=" * 68)[0]
        assert "motor" in section
        # A contract-mapped column (fixed OR overlay) must NOT be listed as unmapped. `SAM Code`
        # is now the mapped authoritative member_number column → never listed.
        assert "SAM Code" not in section
        assert "Kenteken" not in section

    def test_empty_named_column_is_tolerated_and_listed_as_dropped(self, members_env, capsys, tmp_path):
        # A trailing empty-named column (a common Google-Sheet export artifact) is dropped, not
        # a crash, and is surfaced in the report.
        export = tmp_path / "with_empty_col.csv"
        export.write_text(
            "Lidnummer,Achternaam,E-mailadres,Soort lidmaatschap,Datum ondertekening,Regio,\n"
            "1001,Alex,a@x.com,Erelid,2010-01-01,North,junk\n",
            encoding="utf-8",
        )
        rc = runner.main(["--source", str(export), "--tenant", "h-dcn"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "empty-named column" in out


# ---------------------------------------------------------------------------
# S5m Task 2 — the authored mapping CSV + loader (the declared contract, R0.1/R0.4/D0).
#
# The mapping lives in ONE authored CSV (scripts/onboarding/members/h-dcn/members_source_mapping.csv); the
# loader parses it into the fixed/overlay maps + disposition sets the transform consumes, and
# VALIDATES it on load (every target is a known fixed key / declared overlay key / disposition
# token; every rule is known; every overlay.* target is a declared overlay field — drift guard).
# These tests exercise the loaded contract without touching Google or DynamoDB.
# ---------------------------------------------------------------------------

# The h-dcn onboarding scripts dir carries the CSV + its two loaders (config + mapping). Put it
# on sys.path so `members_mapping_loader` / `members_config_loader` import as top-level modules
# (mirrors how the runner is loaded by path above).
_HDCN_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "scripts", "onboarding", "members", "h-dcn")
if _HDCN_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _HDCN_SCRIPTS_DIR)

from members_config_loader import load_members_config
from members_mapping_loader import (
    KNOWN_RULES,
    MappingContractError,
    load_mapping_contract,
)


def _write_mapping(tmp_path, body: str):
    """Write a minimal mapping CSV (header + the given data lines) and return its path."""
    header = "source_column,col_index,target,rule,note\n"
    p = tmp_path / "mapping.csv"
    p.write_text(header + body, encoding="utf-8")
    return str(p)


class TestMappingContractLoader:
    """The authored CSV loads into the fixed/overlay/disposition structures (R0.1/D0)."""

    def test_load_mapping_contract_parses_the_authored_csv(self):
        c = load_mapping_contract()
        # Fixed base fields resolve to their dotted keys (matched on the BASE header, lower-cased).
        assert c.fixed["e-mailadres"].target == "personal.email"
        # SAM Code identity change: the authoritative member_number is READ from `SAM Code`
        # (matched on its base header), NOT from the legacy Lidnummer (now excluded).
        assert c.fixed["sam code"].target == "membership.member_number"
        assert c.fixed["sam code"].rule == "member_number"
        assert "lidnummer" not in c.fixed
        assert c.fixed["geboorte datum"].rule == "date"
        # Overlay columns resolve to CANONICAL overlay keys.
        assert c.overlay["clubblad"].targets == ("magazine_pref",)
        assert c.overlay["regio"].targets == ("region",)

    def test_conditional_split_row_names_two_overlay_targets(self):
        # Bankrekeningnummer drives BOTH overlay.iban and overlay.payment_method (R0.3 / R2.3).
        c = load_mapping_contract()
        m = c.overlay["bankrekeningnummer"]
        assert m.rule == "iban_or_payment"
        assert m.targets == ("iban", "payment_method")

    def test_disposition_sets_are_populated_from_the_csv(self):
        # Calculated / Excluded / Additional-info dispositions land in their sets (R2.6/R2.7).
        c = load_mapping_contract()
        assert {"geboortedag", "geboortemaand", "geboortejaar"} <= c.calculated
        # Lidnummer is now EXCLUDED (retired as the member_number source; SAM Code supplies it).
        assert {"bestuursfunctie", "lidmaatschapsnummer", "h-dcn clubblad", "lidnummer"} <= c.excluded
        assert {"ondertekening", "naam voor akkoord"} <= c.additional_info

    def test_comment_lines_are_skipped(self, tmp_path):
        path = _write_mapping(
            tmp_path,
            "# a comment line\n"
            "Voornaam,0,personal.first_name,single,x\n"
            "#(blank),1,(excluded),,dropped\n",
        )
        # Minimal empty-overlay config: this test exercises comment-skipping, not the R2.5 orphan guard (which would otherwise flag the real config's overlay fields as unbacked by this 1-row mapping).
        c = load_mapping_contract(path, config={"field_overlay": {"fields": {}}})
        assert "voornaam" in c.fixed
        # The '#(blank)' row is a COMMENT (starts with '#') so it never becomes an excluded entry.
        assert c.excluded == frozenset()


class TestMappingContractDriftGuard:
    """Every overlay.* target is a declared overlay field in members_config.json (R0.4)."""

    def test_every_overlay_target_is_a_declared_overlay_field(self):
        # The drift guard the loader enforces, asserted directly against the config (R0.4).
        config = load_members_config()
        declared = set((config["field_overlay"]["fields"]).keys())
        c = load_mapping_contract(config=config)
        used = {k for m in c.overlay.values() for k in m.targets}
        assert used, "expected at least one overlay target"
        assert used <= declared, f"overlay targets not in config: {used - declared}"

    def test_additional_info_is_a_declared_overlay_field(self):
        # R2.7: the catch-all overlay.additional_info field must exist in the tenant config.
        config = load_members_config()
        assert "additional_info" in config["field_overlay"]["fields"]

    def test_unknown_overlay_target_is_rejected_as_drift(self, tmp_path):
        path = _write_mapping(tmp_path, "Foo,0,overlay.not_a_real_field,single,x\n")
        with pytest.raises(MappingContractError) as exc:
            load_mapping_contract(path)
        assert any("drift guard" in e for e in exc.value.errors)


class TestMappingContractValidation:
    """The CSV is a CONTRACT — a bad target / rule / disposition fails loudly on load (R0.4)."""

    def test_unknown_fixed_key_is_rejected(self, tmp_path):
        path = _write_mapping(tmp_path, "Foo,0,personal.not_a_field,single,x\n")
        with pytest.raises(MappingContractError) as exc:
            load_mapping_contract(path)
        assert any("known fixed field key" in e for e in exc.value.errors)

    def test_unknown_rule_is_rejected(self, tmp_path):
        path = _write_mapping(tmp_path, "Foo,0,personal.email,frobnicate,x\n")
        with pytest.raises(MappingContractError) as exc:
            load_mapping_contract(path)
        assert any("unknown rule" in e for e in exc.value.errors)

    def test_bad_target_form_is_rejected(self, tmp_path):
        path = _write_mapping(tmp_path, "Foo,0,garbage,single,x\n")
        with pytest.raises(MappingContractError):
            load_mapping_contract(path)

    def test_disposition_row_with_a_real_rule_is_rejected(self, tmp_path):
        path = _write_mapping(tmp_path, "Foo,0,(excluded),single,x\n")
        with pytest.raises(MappingContractError) as exc:
            load_mapping_contract(path)
        assert any("must have a blank rule" in e for e in exc.value.errors)

    def test_blank_rule_on_a_real_target_defaults_to_single(self, tmp_path):
        path = _write_mapping(tmp_path, "Voornaam,0,personal.first_name,,x\n")
        # Minimal empty-overlay config: this test exercises blank-rule defaulting, not the R2.5 orphan guard.
        c = load_mapping_contract(path, config={"field_overlay": {"fields": {}}})
        assert c.fixed["voornaam"].rule == "single"

    def test_all_rules_used_in_the_authored_csv_are_known(self):
        # Nothing in the authored CSV uses a rule outside the declared vocabulary (R0.2/R0.3).
        c = load_mapping_contract()
        used = {m.rule for m in c.fixed.values()} | {m.rule for m in c.overlay.values()}
        assert used <= KNOWN_RULES


class TestMappingContractTargetPopulation:
    """R0.4: each declared fixed/overlay target is reachable from its source column(s)."""

    def test_key_fixed_and_overlay_targets_are_declared_in_the_contract(self):
        c = load_mapping_contract()
        fixed_targets = {m.target for m in c.fixed.values()}
        overlay_targets = {k for m in c.overlay.values() for k in m.targets}
        # The data-quality bug drivers (R0/US1): email, birth_date, motor, IBAN, payment method.
        assert "personal.email" in fixed_targets
        assert "personal.birth_date" in fixed_targets
        assert "membership.member_number" in fixed_targets
        assert {"motor_brand", "motor_type", "iban", "payment_method", "magazine_pref"} <= overlay_targets


# ---------------------------------------------------------------------------
# S5m Task 3b — ported h-dcn business rules, RETARGETED to SAM canonical values
# (R8.1/R8.2/R8.4): region variants, gender M/V/X/N, magazine variant table,
# email no-valid-email indicators, column-shift detection.
# ---------------------------------------------------------------------------

# The region canonicalizer built from the REAL tenant config + the ported REGION_ALIASES — this
# is the exact canonicalizer the onboarding/runner uses, so the tests exercise the ported region
# variant table against the SAM canonical value set (Noord Holland w/ space, Geen not Overig).
from members_config_loader import (
    REGION_ALIASES,
)
from members_config_loader import (
    region_canonicalizer as _build_region_canonicalizer,
)

_REAL_REGION_CANON = _build_region_canonicalizer(load_members_config())


def _map_real_region(regio: str):
    """map_hdcn_row over a well-formed row using the REAL (config-backed) region canonicalizer."""
    return map_hdcn_row(_raw(Regio=regio), region_canonicalizer=_REAL_REGION_CANON)


class TestPortedRegionVariants:
    """h-dcn's ~40-variant region table, ported + RETARGETED to SAM canonical values (R8.1/R8.2)."""

    def test_hyphen_and_space_variants_fold_onto_noord_holland(self):
        # SAM canonical is `Noord Holland` (a SPACE, not h-dcn's hyphen). scope_canon folds the
        # separator, so both spellings land on the canonical value (R8.2 retarget).
        assert _map_real_region("Noord-Holland")["overlay"]["region"] == "Noord Holland"
        assert _map_real_region("Noord Holland")["overlay"]["region"] == "Noord Holland"
        assert _map_real_region("NOORD-HOLLAND")["overlay"]["region"] == "Noord Holland"

    def test_zuid_holland_variants_fold_onto_canonical(self):
        assert _map_real_region("Zuid-Holland")["overlay"]["region"] == "Zuid Holland"
        assert _map_real_region("ZH")["overlay"]["region"] == "Zuid Holland"

    def test_abbreviation_alias_maps_to_canonical(self):
        assert _map_real_region("NH")["overlay"]["region"] == "Noord Holland"
        assert _map_real_region("NB")["overlay"]["region"] == "Brabant/Zeeland"

    def test_misspelling_drente_maps_to_groningen_drenthe(self):
        # A real letter difference scope_canon cannot fold → the ported alias handles it.
        assert _map_real_region("Groningen/Drente")["overlay"]["region"] == "Groningen/Drenthe"
        assert _map_real_region("Drenthe")["overlay"]["region"] == "Groningen/Drenthe"

    def test_overig_is_retargeted_to_geen_not_the_hdcn_dutch_value(self):
        # R8.2: h-dcn stored `Overig` ("Other"); SAM's canonical set uses `Geen`. The ported
        # alias RETARGETS onto the SAM value — h-dcn's Dutch target is NOT copied.
        assert _map_real_region("Overig")["overlay"]["region"] == "Geen"
        assert _map_real_region("Anders")["overlay"]["region"] == "Geen"

    def test_english_label_germany_maps_to_duitsland(self):
        assert _map_real_region("Germany")["overlay"]["region"] == "Duitsland"

    def test_geen_stays_geen(self):
        # `Geen` is itself a valid canonical region value — it must survive verbatim.
        assert _map_real_region("Geen")["overlay"]["region"] == "Geen"

    def test_east_provinces_fold_onto_oost(self):
        assert _map_real_region("Gelderland")["overlay"]["region"] == "Oost"
        assert _map_real_region("Overijssel")["overlay"]["region"] == "Oost"

    def test_aliases_do_not_target_values_outside_the_canonical_set(self):
        # R8.2 guard: every ported alias TARGET is a value in the tenant's canonical region set
        # (no h-dcn Dutch leftover like "Noord-Holland"/"Overig" leaks in as a target).
        canonical = set(load_members_config()["scope_dimensions"][0]["values"])
        assert set(REGION_ALIASES.values()) <= canonical


class TestPortedGenderNormalization:
    """Gender ported from h-dcn gender_mapping, retargeted to the tenant M/V/X/N enum (R8.1/R8.2)."""

    def test_dutch_man_vrouw_map_to_enum(self):
        assert _map(Geslacht="Man")["personal"]["gender"] == "M"
        assert _map(Geslacht="Vrouw")["personal"]["gender"] == "V"

    def test_bare_m_v_and_english_map_to_enum(self):
        assert _map(Geslacht="m")["personal"]["gender"] == "M"
        assert _map(Geslacht="v")["personal"]["gender"] == "V"
        assert _map(Geslacht="Male")["personal"]["gender"] == "M"
        assert _map(Geslacht="female")["personal"]["gender"] == "V"

    def test_other_and_prefer_not_to_say_map_to_x_and_n(self):
        assert _map(Geslacht="Anders")["personal"]["gender"] == "X"
        assert _map(Geslacht="Divers")["personal"]["gender"] == "X"
        assert _map(Geslacht="Wil niet zeggen")["personal"]["gender"] == "N"

    def test_already_canonical_values_pass_through(self):
        for g in ("M", "V", "X", "N"):
            assert _map(Geslacht=g)["personal"]["gender"] == g

    def test_unrecognized_gender_is_kept_verbatim(self):
        # Never silently forced to a wrong code — kept verbatim (surfaced by config validation).
        assert _map(Geslacht="Robot")["personal"]["gender"] == "Robot"


class TestPortedMagazineVariants:
    """Clubblad → magazine_pref variant table, ported + retargeted (R8.1); status rule NOT copied."""

    def test_paper_variants_map_to_papier(self):
        assert _map(Clubblad="Papier")["overlay"]["magazine_pref"] == "Papier"
        assert _map(Clubblad="print")["overlay"]["magazine_pref"] == "Papier"
        assert _map(Clubblad="gedrukt")["overlay"]["magazine_pref"] == "Papier"

    def test_digital_variants_map_to_digitaal(self):
        assert _map(Clubblad="Digitaal")["overlay"]["magazine_pref"] == "Digitaal"
        assert _map(Clubblad="pdf")["overlay"]["magazine_pref"] == "Digitaal"
        assert _map(Clubblad="online")["overlay"]["magazine_pref"] == "Digitaal"

    def test_none_and_unrecognized_fall_back_to_geen(self):
        assert _map(Clubblad="Geen")["overlay"]["magazine_pref"] == "Geen"
        assert _map(Clubblad="nee")["overlay"]["magazine_pref"] == "Geen"
        assert _map(Clubblad="something odd")["overlay"]["magazine_pref"] == "Geen"

    def test_magazine_pref_is_never_an_hdcn_status_string(self):
        # R8.1/D8: the OLD Clubblad→status (Papier→Sponsor / Digitaal→Club) is NOT copied — the
        # rule only yields the tenant magazine_pref enum, never a Dutch status/type string.
        assert _map(Clubblad="Papier")["overlay"]["magazine_pref"] in {"Geen", "Papier", "Digitaal"}
        # membership_type/status come from their own columns, NOT from Clubblad.
        assert _map(Clubblad="Papier")["membership"]["status"] == "active"


class TestPortedEmailIndicators:
    """The 'no valid email' indicator list, ported from h-dcn (R8.1): a placeholder → empty."""

    def test_no_valid_email_placeholder_is_treated_as_empty(self):
        # A "geen email" style placeholder must NOT land on personal.email as if it were real.
        rec = _map(**{"E-mailadres": "geen email"})
        assert "email" not in rec["personal"]

    def test_various_placeholders_are_all_stripped(self):
        for placeholder in ("n.v.t.", "onbekend", "no@email.com", "-", "geen"):
            rec = _map(**{"E-mailadres": placeholder})
            assert "email" not in rec["personal"], placeholder

    def test_a_real_address_passes_through(self):
        rec = _map(**{"E-mailadres": "real.person@example.com"})
        assert rec["personal"]["email"] == "real.person@example.com"

    def test_placeholder_does_not_win_coalesce_over_a_real_duplicate(self):
        # The peter@pgeer.nl-style fix, ported-rule variant: a placeholder in col 12 must not
        # beat a real address in the col-34 duplicate — the placeholder coalesces to empty first.
        rec = map_hdcn_row(
            _raw(**{"E-mailadres": "geen email", "E-mailadres#34": "real@x.com"}),
            region_canonicalizer=_TEST_REGION_CANON,
        )
        assert rec["personal"]["email"] == "real@x.com"


class TestColumnShiftDetection:
    """Column-shift detection ported from h-dcn as a data-quality WARNING (R8.1/R8.4)."""

    def test_year_in_geslacht_is_flagged(self):
        warnings = detect_column_shift(_raw(Geslacht="1975"))
        assert any(w.column == "Geslacht" and w.value == "1975" for w in warnings)

    def test_gender_in_regio_is_flagged(self):
        warnings = detect_column_shift(_raw(Regio="Man"))
        assert any(w.column == "Regio" and "gender" in w.reason.lower() for w in warnings)

    def test_well_aligned_row_has_no_warnings(self):
        assert detect_column_shift(_raw(Geslacht="Man", Regio="North")) == []

    def test_shift_warning_is_a_warning_only_never_blocks_the_row(self):
        # A shifted value is reported but the row still transforms (never blocked/rewritten).
        warnings: list[ColumnShiftWarning] = []
        rec = map_hdcn_row(
            _raw(Geslacht="1975"),
            region_canonicalizer=_TEST_REGION_CANON,
            shift_warnings=warnings,
        )
        assert rec["member_id"]  # the row still mapped
        assert len(warnings) == 1
        assert warnings[0].column == "Geslacht"

    def test_shift_detection_matches_on_base_header_of_a_position_tracked_duplicate(self):
        # A position-tracked duplicate (Regio#20) is still checked on its base header.
        warnings = detect_column_shift({"Regio#20": "V"})
        assert any(w.value == "V" for w in warnings)


# ---------------------------------------------------------------------------
# S5m single-source-of-truth cleanup — the mapped-column set comes from the loaded
# CONTRACT (the authored CSV), never a stale in-code dict (R0.1/R0.4).
# ---------------------------------------------------------------------------


class TestContractSourceColumns:
    """contract_source_columns() derives the mapped-column set from the loaded contract."""

    def test_returns_fixed_and_overlay_source_columns(self):
        c = load_mapping_contract()
        cols = contract_source_columns(c)
        # Fixed + overlay source headers are present (base, lower-cased) …
        assert "e-mailadres" in cols
        assert "sam code" in cols       # the authoritative member_number column
        assert "lidnummer" not in cols  # legacy number is now excluded (not a mapped target)
        assert "regio" in cols          # the region overlay column
        assert "clubblad" in cols       # a magazine overlay column
        assert "bankrekeningnummer" in cols

    def test_disposition_columns_are_not_counted_as_mapped(self):
        c = load_mapping_contract()
        cols = contract_source_columns(c)
        # (calculated)/(excluded)/(additional_info) columns are NOT "mapped" targets.
        assert "geboortejaar" not in cols       # (calculated)
        assert "bestuursfunctie" not in cols    # (excluded)
        assert "ondertekening" not in cols      # (additional_info)

    def test_classifier_known_set_tracks_the_csv_not_a_stale_dict(self):
        # The runner's classifier builds its "known" set from THIS function; renaming/moving a
        # column in the CSV changes what counts as mapped — the invariant of the cleanup.
        c = load_mapping_contract()
        cols = contract_source_columns(c)
        # Every fixed + overlay base header the contract declares is in the set (no more, via the
        # disposition assertions above); this is exactly the mapped surface.
        expected = set(c.fixed.keys()) | set(c.overlay.keys())
        assert cols == expected


class TestRunnerClassifierUsesTheContract:
    """The runner's _classify_source_columns judges mapped-vs-unmapped against the contract."""

    def test_classifier_marks_contract_columns_mapped_and_others_unmapped(self):
        rows = [
            {
                "SAM Code": "M00001",
                "E-mailadres": "a@x.com",
                "Regio": "North",
                "Clubblad": "Papier",
                "Iets Onbekends": "leftover",
                "": "blank col",
            }
        ]
        adapter = IterableSourceAdapter(rows)
        known = contract_source_columns(load_mapping_contract())
        mapped, unmapped = runner._classify_source_columns(adapter, known)
        assert "SAM Code" in mapped and "E-mailadres" in mapped
        assert "Regio" in mapped and "Clubblad" in mapped
        assert "Iets Onbekends" in unmapped
        assert any("empty-named" in u for u in unmapped)

    def test_classifier_matches_a_position_tracked_duplicate_on_base_header(self):
        # A duplicate email column (E-mailadres#34) is classified mapped via its base header.
        adapter = IterableSourceAdapter([{"E-mailadres": "a@x.com", "E-mailadres#34": ""}])
        known = contract_source_columns(load_mapping_contract())
        mapped, _unmapped = runner._classify_source_columns(adapter, known)
        assert "E-mailadres" in mapped and "E-mailadres#34" in mapped


# ---------------------------------------------------------------------------
# S5m Task 6 — runner adapter selection + CLI flags (design D6, R4.6/R5.1).
#
# --source (file) is mutually exclusive with --sheet-id/--sheet-name (Google Sheet); --worksheet
# and --credentials accompany the sheet options. backfill() builds a GoogleSheetsSourceAdapter
# when a sheet is requested, else a FileSourceAdapter — and uses the SAME adapter type for the
# header probe. --tenant stays required. NO network is touched: the sheet path is asserted via
# the constructed adapter (a monkeypatched _build_source_adapter captures it), never a live read.
# ---------------------------------------------------------------------------


class TestRunnerAdapterSelection:
    """The runner selects the source adapter from the CLI flags (design D6/R4.6)."""

    def test_source_flag_builds_a_file_adapter(self):
        adapter = runner._build_source_adapter(FIXTURE)
        assert isinstance(adapter, FileSourceAdapter)

    def test_sheet_id_builds_a_google_sheets_adapter_no_network(self):
        # A --sheet-id request builds a GoogleSheetsSourceAdapter aimed at that id. Construction is
        # inert (no auth, no fetch) — describe() proves the target without any network call (R5.1).
        adapter = runner._build_source_adapter(
            None, sheet_id="abc123", worksheet="Ledenbestand"
        )
        assert isinstance(adapter, GoogleSheetsSourceAdapter)
        assert "abc123" in adapter.describe()
        assert "Ledenbestand" in adapter.describe()
        assert "READ-ONLY" in adapter.describe()

    def test_sheet_name_builds_a_google_sheets_adapter_no_network(self):
        adapter = runner._build_source_adapter(None, sheet_name="HDCN Ledenbestand 2026")
        assert isinstance(adapter, GoogleSheetsSourceAdapter)
        assert "HDCN Ledenbestand 2026" in adapter.describe()

    def test_credentials_path_is_threaded_into_the_sheet_adapter(self, tmp_path):
        # --credentials PATH reaches the adapter (used for from_service_account_file). We assert
        # the stored path without loading it — no key file needed, no network.
        key = str(tmp_path / "sa.json")
        adapter = runner._build_source_adapter(None, sheet_id="abc123", credentials_file=key)
        assert adapter._credentials_file == key

    def test_no_credentials_default_leaves_resolution_to_the_caller(self):
        # Tenant-Onboarding Tooling R2.3: the runner carries NO baked-in legacy credential path.
        # When no credential is passed, _build_source_adapter threads None through (the real
        # credential is resolved in main() from the tenant's secrets.local.json, NOT a hardcoded
        # external file). So the adapter's stored path is None here.
        adapter = runner._build_source_adapter(None, sheet_id="abc123")
        assert adapter._credentials_file is None

    def test_no_source_at_all_raises(self):
        with pytest.raises(ValueError):
            runner._build_source_adapter(None)

    def test_backfill_uses_the_selected_adapter_for_plan_and_probe(
        self, members_env, fake_repo, capsys, monkeypatch
    ):
        # backfill() must build the SAME adapter type for the plan AND the header probe (D6). Feed
        # a fake sheet adapter (in-memory rows) so the dry-run runs end-to-end with NO network.
        built = []

        def _fake_build(source_path, **kwargs):
            assert kwargs["sheet_id"] == "abc123"
            adapter = IterableSourceAdapter([_raw(Lidnummer="7001")], description="fake sheet")
            built.append(adapter)
            return adapter

        monkeypatch.setattr(runner, "_build_source_adapter", _fake_build)
        rc = runner.backfill(
            None, region="eu-west-1", apply=False, sheet_id="abc123", repo=fake_repo
        )
        assert rc == 0
        # Built twice with the SAME (sheet) selection: once for the plan, once for the probe.
        assert len(built) == 2
        assert "DRY-RUN" in capsys.readouterr().out


class TestRunnerSourceSelectionCli:
    """CLI mutual-exclusion + required-source wiring for the source-selection group (R4.6)."""

    def test_source_and_sheet_id_are_mutually_exclusive(self, members_env, capsys):
        with pytest.raises(SystemExit) as exc:
            runner.main(["--source", FIXTURE, "--sheet-id", "abc123", "--tenant", "h-dcn"])
        assert exc.value.code == 2
        assert "not allowed with" in capsys.readouterr().err

    def test_source_and_sheet_name_are_mutually_exclusive(self, members_env, capsys):
        with pytest.raises(SystemExit) as exc:
            runner.main(["--source", FIXTURE, "--sheet-name", "HDCN", "--tenant", "h-dcn"])
        assert exc.value.code == 2

    def test_sheet_id_and_sheet_name_are_mutually_exclusive(self, members_env, capsys):
        with pytest.raises(SystemExit) as exc:
            runner.main(["--sheet-id", "abc123", "--sheet-name", "HDCN", "--tenant", "h-dcn"])
        assert exc.value.code == 2

    def test_no_cli_source_falls_through_to_secrets_then_fails_loudly(self, members_env, capsys):
        # Tenant-Onboarding Tooling: the source group is NO LONGER argparse-required — when no
        # --source/--sheet-id/--sheet-name is given, sheet_id is resolved from the tenant's
        # secrets.local.json. With no secrets file present, main() must fail LOUDLY (rc=1,
        # NOT a crash) naming the missing file + the --secrets escape hatch (R3.1). It must NOT
        # fall back to any hardcoded source.
        rc = runner.main(["--tenant", "h-dcn"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "secrets.local.json" in err
        assert "--secrets" in err

    def test_tenant_is_still_required_with_a_sheet_source(self, members_env, capsys):
        # --tenant has no default even on the sheet path: a missing --tenant is rejected.
        with pytest.raises(SystemExit) as exc:
            runner.main(["--sheet-id", "abc123"])
        assert exc.value.code == 2
        assert "--tenant" in capsys.readouterr().err

    def test_sheet_flags_parse_and_thread_into_backfill(self, members_env, monkeypatch):
        # main() wires --sheet-id/--worksheet/--credentials through to backfill() unchanged.
        captured = {}

        def _fake_backfill(source_path, **kwargs):
            captured["source_path"] = source_path
            captured.update(kwargs)
            return 0

        monkeypatch.setattr(runner, "backfill", _fake_backfill)
        rc = runner.main(
            [
                "--sheet-id", "abc123",
                "--worksheet", "Ledenbestand",
                "--credentials", "/tmp/key.json",
                "--tenant", "h-dcn",
            ]
        )
        assert rc == 0
        assert captured["source_path"] is None
        assert captured["sheet_id"] == "abc123"
        assert captured["sheet_name"] is None
        assert captured["worksheet"] == "Ledenbestand"
        assert captured["credentials_file"] == "/tmp/key.json"
        assert captured["tenant_id"] == "h-dcn"

    def test_fully_specified_cli_run_needs_no_secrets_file(self, members_env, monkeypatch):
        # Every gsheet key on the CLI → main() must NOT require a secrets file at all (lazy load).
        monkeypatch.setattr(runner, "backfill", lambda source_path, **kw: 0)
        rc = runner.main(
            [
                "--sheet-id", "abc123",
                "--worksheet", "Ledenbestand",
                "--credentials", "/tmp/key.json",
                "--tenant", "tenant-with-no-secrets-file",
            ]
        )
        assert rc == 0


class TestRunnerSecretsResolution:
    """gsheet keys resolve from the tenant secrets file; CLI wins; missing keys fail loudly.

    Tenant-Onboarding Tooling R2/R3: two-level precedence (CLI flag > secrets.local.json),
    then a loud NAMED error — never a silent fallback.
    """

    def _write_secrets(self, tmp_path, body):
        import json as _json

        p = tmp_path / "secrets.local.json"
        p.write_text(_json.dumps(body), encoding="utf-8")
        return str(p)

    def test_sheet_id_credentials_resolve_from_secrets_when_absent_on_cli(
        self, members_env, tmp_path, monkeypatch
    ):
        key = tmp_path / "sa.json"
        key.write_text("{}", encoding="utf-8")
        secrets_path = self._write_secrets(
            tmp_path,
            {
                "sheet_id": "SHEET_FROM_SECRETS",
                "worksheet": "Ledenbestand",
                "credentials": {"google_sheets": {"type": "google_service_account", "file": str(key)}},
            },
        )
        captured = {}

        def _fake_backfill(source_path, **kw):
            captured.update(kw)
            return 0

        monkeypatch.setattr(runner, "backfill", _fake_backfill)
        rc = runner.main(["--tenant", "h-dcn", "--secrets", secrets_path])
        assert rc == 0
        assert captured["sheet_id"] == "SHEET_FROM_SECRETS"
        assert captured["worksheet"] == "Ledenbestand"
        # absolute file in the secrets map is honored as-is by credential_file()
        assert captured["credentials_file"] == str(key)

    def test_cli_sheet_id_overrides_the_secrets_value(self, members_env, tmp_path, monkeypatch):
        secrets_path = self._write_secrets(
            tmp_path,
            {"sheet_id": "SHEET_FROM_SECRETS",
             "credentials": {"google_sheets": {"file": str(tmp_path / "sa.json")}}},
        )
        captured = {}
        monkeypatch.setattr(runner, "backfill", lambda source_path, **kw: captured.update(kw) or 0)
        rc = runner.main(
            ["--sheet-id", "CLI_WINS", "--tenant", "h-dcn", "--secrets", secrets_path]
        )
        assert rc == 0
        assert captured["sheet_id"] == "CLI_WINS"

    def test_missing_sheet_id_in_secrets_fails_loudly_naming_the_key(
        self, members_env, tmp_path, capsys
    ):
        secrets_path = self._write_secrets(
            tmp_path,
            {"credentials": {"google_sheets": {"file": str(tmp_path / "sa.json")}}},  # no sheet_id
        )
        rc = runner.main(["--tenant", "h-dcn", "--secrets", secrets_path])
        assert rc == 1
        assert "sheet_id" in capsys.readouterr().err

    def test_source_path_run_never_consults_secrets(self, members_env, monkeypatch):
        # The file-export path (--source) needs no gsheet keys → secrets must NOT be loaded even
        # if absent. We assert load_tenant_secrets is never called.
        called = {"n": 0}
        monkeypatch.setattr(runner, "load_tenant_secrets", lambda *a, **k: called.__setitem__("n", called["n"] + 1) or {})
        monkeypatch.setattr(runner, "backfill", lambda source_path, **kw: 0)
        rc = runner.main(["--source", FIXTURE, "--tenant", "h-dcn"])
        assert rc == 0
        assert called["n"] == 0


# ---------------------------------------------------------------------------
# S5m Task 7 — the reconciling sync (--reconcile: match by member_number, upsert,
# absence sweep). Match key is the stable authoritative member_number read from SAM Code
# (M##### / D##### / C#####);
# UPDATE reuses the existing member_id (idempotent, R5.3); an absent SAM record is
# soft-flagged status='left' (R7.4, NEVER deleted); a numberless sheet row is
# UNMATCHABLE; a duplicate sheet number blocks --apply --reconcile (R7.7).
#
# Validates: Requirements R5.2, R5.3, R7.1, R7.2, R7.3, R7.4, R7.5, R7.6, R7.7
# ---------------------------------------------------------------------------


def _export(tmp_path, rows, name="sheet.json"):
    """Write a JSON export of raw h-dcn rows and return its path (a source for the runner)."""
    p = tmp_path / name
    p.write_text(json.dumps(rows), encoding="utf-8")
    return str(p)


class TestReconcileSync:
    def test_matched_number_updates_the_same_member_id(self, members_env, fake_repo, tmp_path):
        # Seed SAM by an initial insert-only backfill of SAM Code M01001.
        first = _export(tmp_path, [_raw(**{"SAM Code": "M01001", "Voornaam": "Alex"})], "first.json")
        assert runner.backfill(first, region="eu-west-1", apply=True, repo=fake_repo) == 0
        seeded = fake_repo.list_members("h-dcn")
        assert len(seeded) == 1
        original_id = seeded[0]["member_id"]

        # A reconcile run of the SAME SAM Code (edited first name) must UPDATE — not mint a new
        # record — reusing the existing member_id (R7.3), and SHEET-WINS on the mapped field.
        again = _export(tmp_path, [_raw(**{"SAM Code": "M01001", "Voornaam": "Alexander"})], "again.json")
        rc = runner.backfill(again, region="eu-west-1", apply=True, reconcile=True, repo=fake_repo)
        assert rc == 0
        after = fake_repo.list_members("h-dcn")
        assert len(after) == 1  # no duplicate minted
        assert after[0]["member_id"] == original_id  # same internal id reused
        assert after[0]["personal"]["first_name"] == "Alexander"  # sheet-wins on the mapped field

    def test_unseen_number_inserts_a_new_record(self, members_env, fake_repo, tmp_path):
        seed = _export(tmp_path, [_raw(**{"SAM Code": "M01001"})], "seed.json")
        assert runner.backfill(seed, region="eu-west-1", apply=True, repo=fake_repo) == 0

        # A reconcile with a NEW number (and the old one still present) inserts the new member.
        both = _export(
            tmp_path,
            [_raw(**{"SAM Code": "M01001"}), _raw(**{"SAM Code": "M01002", "Voornaam": "Bram"})],
            "both.json",
        )
        rc = runner.backfill(both, region="eu-west-1", apply=True, reconcile=True, repo=fake_repo)
        assert rc == 0
        numbers = sorted(m["membership"]["member_number"] for m in fake_repo.list_members("h-dcn"))
        assert numbers == ["M01001", "M01002"]

    def test_member_absent_from_sheet_is_soft_flagged_left_not_deleted(
        self, members_env, fake_repo, tmp_path
    ):
        # Seed two members.
        seed = _export(
            tmp_path,
            [_raw(**{"SAM Code": "M01001"}), _raw(**{"SAM Code": "M01002", "Voornaam": "Bram"})],
            "seed.json",
        )
        assert runner.backfill(seed, region="eu-west-1", apply=True, repo=fake_repo) == 0

        # Reconcile a sheet that only carries M01001 → M01002 must be SOFT-flagged 'left', not deleted.
        only1 = _export(tmp_path, [_raw(**{"SAM Code": "M01001"})], "only1.json")
        rc = runner.backfill(only1, region="eu-west-1", apply=True, reconcile=True, repo=fake_repo)
        assert rc == 0
        listed = fake_repo.list_members("h-dcn")
        assert len(listed) == 2  # NOT deleted — still present (R5.2)
        by_number = {m["membership"]["member_number"]: m for m in listed}
        assert by_number["M01002"]["membership"]["status"] == "left"  # soft-flagged (R7.4)
        assert by_number["M01001"]["membership"]["status"] == "active"  # present → untouched

    def test_left_member_back_in_sheet_is_reactivated(self, members_env, fake_repo, tmp_path):
        # Seed M01001, then sweep it 'left' by reconciling an empty-of-M01001 sheet.
        seed = _export(tmp_path, [_raw(**{"SAM Code": "M01001"}), _raw(**{"SAM Code": "M01002"})], "seed.json")
        assert runner.backfill(seed, region="eu-west-1", apply=True, repo=fake_repo) == 0
        only2 = _export(tmp_path, [_raw(**{"SAM Code": "M01002"})], "only2.json")
        assert runner.backfill(only2, region="eu-west-1", apply=True, reconcile=True, repo=fake_repo) == 0
        left = {m["membership"]["member_number"]: m for m in fake_repo.list_members("h-dcn")}
        assert left["M01001"]["membership"]["status"] == "left"

        # M01001 reappears in the sheet → reactivated (its status comes from the transform: active).
        back = _export(tmp_path, [_raw(**{"SAM Code": "M01001"}), _raw(**{"SAM Code": "M01002"})], "back.json")
        rc = runner.backfill(back, region="eu-west-1", apply=True, reconcile=True, repo=fake_repo)
        assert rc == 0
        after = {m["membership"]["member_number"]: m for m in fake_repo.list_members("h-dcn")}
        assert after["M01001"]["membership"]["status"] == "active"

    def test_contact_is_reconciled_and_swept_like_a_member(self, members_env, fake_repo, tmp_path):
        # A CONTACT (an organisation row) is keyed by its C##### SAM Code and reconciled/swept
        # exactly like a member (R7.4 — contacts included in the sweep).
        seed = _export(
            tmp_path,
            [_raw(**{"SAM Code": "C00001", "Lidnummer": "", "Achternaam": "Acme Sponsors", "Voornaam": "Acme"})],
            "seed.json",
        )
        assert runner.backfill(seed, region="eu-west-1", apply=True, repo=fake_repo) == 0
        seeded = fake_repo.list_members("h-dcn")
        assert seeded[0]["membership"]["member_number"] == "C00001"

        # Reconcile a sheet WITHOUT the contact → it is soft-flagged 'left' (not deleted).
        empty = _export(tmp_path, [_raw(**{"SAM Code": "M01001"})], "with_member.json")
        rc = runner.backfill(empty, region="eu-west-1", apply=True, reconcile=True, repo=fake_repo)
        assert rc == 0
        by_number = {m["membership"]["member_number"]: m for m in fake_repo.list_members("h-dcn")}
        assert by_number["C00001"]["membership"]["status"] == "left"

    def test_duplicate_sheet_number_blocks_apply_reconcile(self, members_env, fake_repo, tmp_path):
        # Two rows share SAM Code M01001 → a matching hazard. --apply --reconcile refuses
        # (writes nothing) and reports the duplicate (R7.7).
        dupes = _export(
            tmp_path,
            [_raw(**{"SAM Code": "M01001", "Achternaam": "Alex"}), _raw(**{"SAM Code": "M01001", "Achternaam": "Bram"})],
            "dupes.json",
        )
        rc = runner.backfill(dupes, region="eu-west-1", apply=True, reconcile=True, repo=fake_repo)
        assert rc == 2  # refused
        assert fake_repo.list_members("h-dcn") == []  # nothing written

    def test_reconcile_dry_run_writes_nothing(self, members_env, fake_repo, tmp_path, capsys):
        seed = _export(tmp_path, [_raw(**{"SAM Code": "M01001"})], "seed.json")
        assert runner.backfill(seed, region="eu-west-1", apply=True, repo=fake_repo) == 0
        # Dry-run reconcile: report the sync plan, write nothing.
        report = _export(tmp_path, [_raw(**{"SAM Code": "M01002"})], "report.json")
        rc = runner.backfill(report, region="eu-west-1", apply=False, reconcile=True, repo=fake_repo)
        assert rc == 0
        out = capsys.readouterr().out
        assert "RECONCILE (sync) plan" in out
        assert "to-INSERT" in out and "to-LEAVE" in out
        # Still exactly the one seeded member — the dry-run reconcile persisted nothing.
        assert len(fake_repo.list_members("h-dcn")) == 1
        assert fake_repo.list_members("h-dcn")[0]["membership"]["member_number"] == "M01001"

    def test_second_reconcile_run_is_idempotent(self, members_env, fake_repo, tmp_path):
        # R5.3: because the match key is the stable member_number and UPDATE reuses member_id, a
        # second identical reconcile run produces NO duplicates and no status churn.
        sheet = _export(
            tmp_path,
            [_raw(**{"SAM Code": "M01001"}), _raw(**{"SAM Code": "M01002", "Voornaam": "Bram"})],
            "sheet.json",
        )
        assert runner.backfill(sheet, region="eu-west-1", apply=True, reconcile=True, repo=fake_repo) == 0
        first = fake_repo.list_members("h-dcn")
        first_ids = {m["membership"]["member_number"]: m["member_id"] for m in first}

        assert runner.backfill(sheet, region="eu-west-1", apply=True, reconcile=True, repo=fake_repo) == 0
        second = fake_repo.list_members("h-dcn")
        assert len(second) == len(first) == 2  # no duplicates minted on the re-run
        second_ids = {m["membership"]["member_number"]: m["member_id"] for m in second}
        assert second_ids == first_ids  # same member_ids reused (idempotent)
        assert all(m["membership"]["status"] == "active" for m in second)

    def test_reconcile_default_backfill_is_unchanged_without_the_flag(
        self, members_env, fake_repo, tmp_path
    ):
        # Backward compatibility (R7.1): without --reconcile the runner is insert-only. A second
        # apply of the same source mints NEW records (the s5k mint-a-uuid behaviour), NOT an upsert.
        sheet = _export(tmp_path, [_raw(**{"SAM Code": "M01001"})], "sheet.json")
        assert runner.backfill(sheet, region="eu-west-1", apply=True, repo=fake_repo) == 0
        assert runner.backfill(sheet, region="eu-west-1", apply=True, repo=fake_repo) == 0
        # Insert-only: the second run added a second record under a new minted member_id.
        assert len(fake_repo.list_members("h-dcn")) == 2


class TestReconcileCli:
    def test_reconcile_flag_parses_and_threads_into_backfill(self, members_env, monkeypatch):
        captured = {}

        def _fake_backfill(source_path, **kwargs):
            captured.update(kwargs)
            return 0

        monkeypatch.setattr(runner, "backfill", _fake_backfill)
        rc = runner.main(["--source", FIXTURE, "--tenant", "h-dcn", "--reconcile"])
        assert rc == 0
        assert captured["reconcile"] is True

    def test_sync_alias_parses_as_reconcile(self, members_env, monkeypatch):
        captured = {}
        monkeypatch.setattr(runner, "backfill", lambda source_path, **kw: captured.update(kw) or 0)
        assert runner.main(["--source", FIXTURE, "--tenant", "h-dcn", "--sync"]) == 0
        assert captured["reconcile"] is True

    def test_reconcile_is_off_by_default(self, members_env, monkeypatch):
        captured = {}
        monkeypatch.setattr(runner, "backfill", lambda source_path, **kw: captured.update(kw) or 0)
        assert runner.main(["--source", FIXTURE, "--tenant", "h-dcn"]) == 0
        assert captured["reconcile"] is False


# ---------------------------------------------------------------------------
# s5m follow-up — R7.2 empty-row skip, Donateur-coded Lidnummer exclusion, and
# first_name-optional contacts (Change A/B/C). None touch Google or DynamoDB.
# ---------------------------------------------------------------------------


class TestEmptyRowAndBlankSamCode:
    """Empty/spacer rows are SKIPPED; a meaningful row with a blank SAM Code is a data-gap error.

    The SAM Code identity change replaces the old Lidnummer/Donateur/C_-derivation skips: the
    member_number is READ from SAM Code, so a Donateur now imports (its D##### code), a contact
    is keyed by its C##### code, and a MEANINGFUL row missing its authoritative code errors
    rather than being silently derived around.
    """

    def test_empty_row_is_skipped_not_an_error(self):
        # A row with no populated cell (incl. a blank SAM Code) is EMPTY and SKIPPED via
        # RowSkipped — never written, never an error.
        empty_row = {"SAM Code": "", "Voornaam": "", "Achternaam": "", "E-mailadres": "", "Regio": ""}
        with pytest.raises(RowSkipped):
            map_hdcn_row(empty_row, region_canonicalizer=_TEST_REGION_CANON)

    def test_placeholder_only_row_is_skipped_silently(self):
        # A row whose ONLY populated cell is a NO-VALID-EMAIL placeholder (`E-mailadres` =
        # "GEEN GELDIG EMAILADRES", normalizes to empty) is treated as EMPTY and skipped
        # silently — not an error — even though SAM Code is blank.
        placeholder_row = {
            "SAM Code": "",
            "Lidnummer": "",
            "Achternaam": "",
            "E-mailadres": "GEEN GELDIG EMAILADRES",
        }
        with pytest.raises(RowSkipped):
            map_hdcn_row(placeholder_row, region_canonicalizer=_TEST_REGION_CANON)

    def test_meaningful_row_with_blank_sam_code_is_reported_not_skipped(self):
        # Transition rule (user-approved): a row with SOME real data but a BLANK SAM Code is NOT
        # empty — it is a data-gap ERROR (reported, not written), NOT silently derived nor skipped.
        data_no_code = {
            "SAM Code": "",
            "Lidnummer": "6564",
            "Achternaam": "Zuidmeer",
            "E-mailadres": "someone@example.com",
            "Soort lidmaatschap": "Erelid",
        }
        with pytest.raises(RowTransformError) as exc:
            map_hdcn_row(data_no_code, region_canonicalizer=_TEST_REGION_CANON)
        assert "membership.member_number" in exc.value.reasons

    def test_donateur_now_imports_with_its_sam_code(self):
        # The old Donateur-coded-Lidnummer SKIP is RETIRED: a Donateur carries a D##### SAM Code
        # and imports verbatim (no longer dropped, no colliding M##### derivation).
        rec = _map(**{"SAM Code": "D00042", "Lidnummer": "6564 Donateur"})
        assert rec["membership"]["member_number"] == "D00042"

    def test_contact_without_first_name_transforms_ok(self):
        # Change A: first_name (Voornaam) is OPTIONAL. A contact/org row with an Achternaam (org
        # name) + no Voornaam maps fine and is keyed by its SAM Code (C#####), not a derived name.
        rec = _map(**{"SAM Code": "C00007", "Lidnummer": "", "Voornaam": "", "Achternaam": "KNMV"})
        assert "first_name" not in rec["personal"]
        assert rec["personal"]["last_name"] == "KNMV"
        assert rec["membership"]["member_number"] == "C00007"


class TestBackfillPlanSkipBucket:
    """build_backfill_plan buckets skipped rows as `skipped`, distinct from errors/transformed."""

    def test_empty_row_lands_in_skipped_not_errors_or_transformed(self):
        adapter = IterableSourceAdapter(
            [_raw(), {"SAM Code": "", "Voornaam": "", "Achternaam": "", "E-mailadres": ""}]
        )
        plan = build_backfill_plan(adapter, region_canonicalizer=_TEST_REGION_CANON)
        assert plan.ok_count == 1
        assert plan.skipped_count == 1
        assert plan.error_count == 0

    def test_placeholder_only_row_lands_in_skipped(self):
        adapter = IterableSourceAdapter(
            [{"SAM Code": "", "Lidnummer": "", "Achternaam": "", "E-mailadres": "GEEN GELDIG EMAILADRES"}]
        )
        plan = build_backfill_plan(adapter, region_canonicalizer=_TEST_REGION_CANON)
        assert plan.skipped_count == 1
        assert plan.ok_count == 0
        assert plan.error_count == 0

    def test_meaningful_row_with_blank_sam_code_lands_in_errors(self):
        # A meaningful data row missing its authoritative SAM Code is a data-gap ERROR — it lands
        # in the errors bucket, NOT skipped, NOT transformed (never silently derived around).
        adapter = IterableSourceAdapter(
            [_raw(), _raw(**{"SAM Code": "", "Lidnummer": "6564", "Achternaam": "Zuidmeer"})]
        )
        plan = build_backfill_plan(adapter, region_canonicalizer=_TEST_REGION_CANON)
        assert plan.ok_count == 1
        assert plan.error_count == 1
        assert plan.skipped_count == 0
