"""
S5 Task 4.1 — tests for the h-dcn member **backfill** (dry-run first, non-destructive).

Three layers, none of which touch Google or live DynamoDB (per the task constraints):

- **The pure transform** (``map_hdcn_row``): fixed/overlay split, ``tenant_id`` +
  ``overlay.region`` scope-field normalization (S5d D1 — no ``scope_values`` bucket),
  membership_type → catalog code mapping, and loud validation failure on a bad row. No I/O.
- **The source adapters** (``FileSourceAdapter`` / ``IterableSourceAdapter``): read a CSV/JSON
  fixture READ-ONLY; the legacy-DynamoDB adapter is a deliberate stub.
- **The runner** (``scripts/aws/backfill-hdcn-members.py``): dry-run writes NOTHING and emits a
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
    FileSourceAdapter,
    IterableSourceAdapter,
    LegacyDynamoSourceAdapter,
    MembershipTypeMapper,
    RegionCanonicalizer,
    RowSkipped,
    RowTransformError,
    build_backfill_plan,
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

from test_members_repository import FakeDynamoTable  # noqa: E402


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
    (the transform mints a uuid4), Lidnummer is the human number, no status column (defaults
    to active), Datum ondertekening → joined_date. Region defaults to a synthetic sample value.
    """
    row = {
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
        # A.2). member_id is a MINTED uuid4 (no source column). member_number is Lidnummer
        # shaped to M#####. joined_date derived from the Datum ondertekening date-part.
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

    def test_club_columns_fold_into_overlay(self):
        rec = _map(**{"Type motor": "Honda CB500", "Kenteken": "AB-12-CD"})
        assert rec["overlay"]["Type motor"] == "Honda CB500"
        assert rec["overlay"]["Kenteken"] == "AB-12-CD"
        # overlay must not contain fixed source columns
        assert "Achternaam" not in rec["overlay"] and "Lidnummer" not in rec["overlay"]

    def test_membership_type_is_mapped_to_a_catalog_code(self):
        assert _map(**{"Soort lidmaatschap": "Erelid"})["membership"]["membership_type"] == "erelid"
        assert _map(**{"Soort lidmaatschap": "Donateur"})["membership"]["membership_type"] == "donateur"
        assert _map(**{"Soort lidmaatschap": "Gewoon lid"})["membership"]["membership_type"] == "gewoon_lid"

    def test_bad_row_fails_loudly_missing_required_field(self):
        # No last name → validate_fixed_fields fails → RowTransformError.
        with pytest.raises(RowTransformError) as exc:
            _map(Achternaam="")
        assert "personal.last_name" in exc.value.reasons

    def test_row_with_no_member_number_is_skipped(self):
        # A row with no Lidnummer is NOT a member (non-member / empty) → RowSkipped, not error.
        with pytest.raises(RowSkipped):
            _map(Lidnummer="")

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


# ---------------------------------------------------------------------------
# build_backfill_plan — the fidelity plan (non-destructive read)
# ---------------------------------------------------------------------------


class TestBackfillPlan:
    def test_plan_transforms_all_good_rows(self):
        adapter = IterableSourceAdapter([_raw(), _raw(Lidnummer="1002")])
        plan = build_backfill_plan(adapter, region_canonicalizer=_TEST_REGION_CANON)
        assert plan.source_row_count == 2
        assert plan.ok_count == 2
        assert plan.error_count == 0
        assert plan.tenant_id == "h-dcn"

    def test_plan_collects_errors_without_aborting(self):
        adapter = IterableSourceAdapter(
            [_raw(), _raw(Lidnummer="1002", Achternaam="")]  # 2nd is bad (no last name)
        )
        plan = build_backfill_plan(adapter, region_canonicalizer=_TEST_REGION_CANON)
        assert plan.ok_count == 1
        assert plan.error_count == 1

    def test_plan_flags_and_skips_duplicate_member_numbers_in_batch(self):
        # A.15: duplicate Lidnummer → ALL occurrences left out (skipped, not written).
        adapter = IterableSourceAdapter([_raw(Lidnummer="1001"), _raw(Lidnummer="1001")])
        plan = build_backfill_plan(adapter, region_canonicalizer=_TEST_REGION_CANON)
        # Shaped number "M01001" is the duplicate key; BOTH minted uuids are recorded.
        assert "M01001" in plan.duplicate_member_numbers
        assert len(plan.duplicate_member_numbers["M01001"]) == 2
        # Both rows are skipped (left out), none transformed.
        assert plan.ok_count == 0
        assert plan.skipped_count == 2

    def test_plan_records_rows_missing_region(self):
        # A row with no region omits overlay.region → recorded in rows_missing_region (by the
        # MINTED member_id, a uuid4).
        adapter = IterableSourceAdapter([_raw(Regio="")])
        plan = build_backfill_plan(adapter, region_canonicalizer=_TEST_REGION_CANON)
        assert len(plan.rows_missing_region) == 1
        assert plan.rows_missing_region[0] == plan.transformed[0].member_id

    def test_non_member_row_without_number_is_skipped(self):
        # A row with no Lidnummer is a non-member → skipped (reported), NOT an error.
        adapter = IterableSourceAdapter([_raw(), _raw(Lidnummer="")])
        plan = build_backfill_plan(adapter, region_canonicalizer=_TEST_REGION_CANON)
        assert plan.ok_count == 1
        assert plan.error_count == 0
        assert plan.skipped_count == 1

    def test_field_mapping_summary_counts_populated_fields(self):
        adapter = IterableSourceAdapter([_raw(), _raw(Lidnummer="1002")])
        summary = build_backfill_plan(
            adapter, region_canonicalizer=_TEST_REGION_CANON
        ).field_mapping_summary()
        assert summary["membership.member_number"] == 2
        assert summary["personal.last_name"] == 2
        # S5d D1: the scope field is a plain `overlay.region` field now (no `scope_values`).
        assert summary["overlay.region"] == 2
        assert summary["overlay.Type motor"] == 2


# ---------------------------------------------------------------------------
# The runner script — dry-run / --apply / conflict
# ---------------------------------------------------------------------------


def _load_runner_module():
    """Import the hyphen-named runner script by path (not a valid module name)."""
    path = os.path.join(_REPO_ROOT, "scripts", "aws", "backfill-hdcn-members.py")
    spec = importlib.util.spec_from_file_location("backfill_hdcn_members", path)
    module = importlib.util.module_from_spec(spec)
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
        assert m1["overlay"]["motor"] == "Honda CB500"
        assert m1["membership"]["membership_type"] == "erelid"

    def test_apply_leaves_duplicate_numbers_out(self, members_env, fake_repo, capsys, tmp_path):
        # A.15: two rows share Lidnummer 1001 (different people) → ALL occurrences skipped,
        # NOTHING written (the data owner must resolve the source conflict, then re-run).
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
        assert rc == 0  # clean apply — the dups are skipped, not an error
        assert fake_repo.list_members("h-dcn") == []  # neither written

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
        export.write_text(json.dumps([_raw(Lidnummer="9001")]), encoding="utf-8")
        rc = runner.backfill(str(export), region="eu-west-1", apply=True, tenant_id="other-org", repo=fake_repo)
        assert rc == 0
        # The record landed in the "other-org" partition, stamped with that tenant.
        assert fake_repo.list_members("h-dcn") == []
        other = fake_repo.list_members("other-org")
        assert len(other) == 1
        assert other[0]["tenant_id"] == "other-org"
        assert other[0]["membership"]["member_number"] == "M09001"

    def test_dry_run_lists_unmapped_extra_columns(self, members_env, capsys):
        # The fixture carries "Type motor"/"Kenteken" — neither is a fixed/region column, so
        # they are tolerated (folded into overlay) and LISTED in the report (task 6.2 OUT-scope).
        runner.main(["--source", FIXTURE, "--tenant", "h-dcn"])
        out = capsys.readouterr().out
        assert "unmapped / extra source columns" in out
        assert "Kenteken" in out
        # A recognized fixed column must NOT be listed as unmapped.
        section = out.split("unmapped / extra source columns")[1].split("=" * 68)[0]
        assert "Lidnummer" not in section

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
