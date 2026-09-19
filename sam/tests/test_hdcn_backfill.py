"""
S5 Task 4.1 — tests for the h-dcn member **backfill** (dry-run first, non-destructive).

Three layers, none of which touch Google or live DynamoDB (per the task constraints):

- **The pure transform** (``map_hdcn_row``): fixed/overlay split, ``tenant_id`` +
  ``scope_values.region`` stamping, membership_type → catalog code mapping, and loud
  validation failure on a bad row. No I/O.
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


def _raw(**overrides):
    """A well-formed raw h-dcn source row (Dutch Ledenbestand columns), with overrides."""
    row = {
        "member_id": "M-1",
        "lidnummer": "1001",
        "naam": "Alex de Vries",
        "email": "alex@example.com",
        "adres": "Dorpsstraat 1",
        "geboortedatum": "1980-05-12",
        "status": "actief",
        "lidmaatschapstype": "Erelid",
        "ingangsdatum": "2010-01-01",
        "einddatum": "",
        "regio": "Noord",
        "motortype": "Honda CB500",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# The pure transform — map_hdcn_row
# ---------------------------------------------------------------------------


class TestMapHdcnRow:
    def test_stamps_the_pilot_tenant_id(self):
        rec = map_hdcn_row(_raw())
        assert rec["tenant_id"] == HDCN_TENANT_ID == "h-dcn"

    def test_splits_fixed_base_personal_and_membership(self):
        rec = map_hdcn_row(_raw())
        assert rec["personal"] == {
            "name": "Alex de Vries",
            "contact": "alex@example.com",
            "address": "Dorpsstraat 1",
            "birthdate": "1980-05-12",
        }
        assert rec["membership"]["member_number"] == "1001"
        assert rec["membership"]["joined"] == "2010-01-01"
        assert rec["member_id"] == "M-1"

    def test_maps_dutch_status_to_the_closed_enum(self):
        assert map_hdcn_row(_raw(status="actief"))["membership"]["status"] == "active"
        assert map_hdcn_row(_raw(status="geschorst"))["membership"]["status"] == "suspended"
        # already-canonical value passes through
        assert map_hdcn_row(_raw(status="active"))["membership"]["status"] == "active"

    def test_seeds_scope_values_region_single_valued(self):
        rec = map_hdcn_row(_raw(regio="Noord"))
        assert rec["scope_values"]["region"] == ["Noord"]

    def test_canonicalizes_region_casing(self):
        rec = map_hdcn_row(_raw(regio="zuid"))
        assert rec["scope_values"]["region"] == ["Zuid"]

    def test_unknown_region_is_preserved_not_dropped(self):
        rec = map_hdcn_row(_raw(regio="Centraal"))
        assert rec["scope_values"]["region"] == ["Centraal"]

    def test_missing_region_yields_empty_scope_list(self):
        rec = map_hdcn_row(_raw(regio=""))
        assert rec["scope_values"]["region"] == []

    def test_club_columns_fold_into_overlay(self):
        rec = map_hdcn_row(_raw(motortype="Honda CB500", kenteken="AB-12-CD"))
        assert rec["overlay"]["motortype"] == "Honda CB500"
        assert rec["overlay"]["kenteken"] == "AB-12-CD"
        # overlay must not contain fixed fields
        assert "naam" not in rec["overlay"] and "lidnummer" not in rec["overlay"]

    def test_membership_type_is_mapped_to_a_catalog_code(self):
        assert map_hdcn_row(_raw(lidmaatschapstype="Erelid"))["membership"]["membership_type"] == "erelid"
        assert map_hdcn_row(_raw(lidmaatschapstype="Donateur"))["membership"]["membership_type"] == "donateur"
        assert map_hdcn_row(_raw(lidmaatschapstype="Gewoon lid"))["membership"]["membership_type"] == "gewoon_lid"

    def test_bad_row_fails_loudly_missing_required_field(self):
        # No name → validate_fixed_fields fails → RowTransformError.
        with pytest.raises(RowTransformError) as exc:
            map_hdcn_row(_raw(naam=""))
        assert "personal.name" in exc.value.reasons

    def test_bad_row_fails_loudly_invalid_date(self):
        with pytest.raises(RowTransformError) as exc:
            map_hdcn_row(_raw(ingangsdatum="not-a-date"))
        assert "membership.joined" in exc.value.reasons

    def test_missing_member_id_is_reported(self):
        with pytest.raises(RowTransformError) as exc:
            map_hdcn_row(_raw(member_id=""))
        assert "member_id" in exc.value.reasons

    def test_type_mapper_validates_against_known_codes(self):
        mapper = MembershipTypeMapper(known_codes=["erelid", "donateur"])
        # 'sponsor' is not in the known set → the row fails to map (loud mismatch).
        with pytest.raises(RowTransformError) as exc:
            map_hdcn_row(_raw(lidmaatschapstype="Sponsor"), type_mapper=mapper)
        assert "membership.membership_type" in exc.value.reasons

    def test_transform_does_not_mutate_the_source_row(self):
        row = _raw()
        snapshot = dict(row)
        map_hdcn_row(row)
        assert row == snapshot  # pure — no mutation of the input (non-destructive)


# ---------------------------------------------------------------------------
# Source adapters — read-only
# ---------------------------------------------------------------------------


class TestSourceAdapters:
    def test_file_adapter_reads_the_csv_fixture(self):
        adapter = FileSourceAdapter(FIXTURE)
        rows = list(adapter.rows())
        assert len(rows) == 4
        assert rows[0]["lidnummer"] == "1001"
        assert rows[0]["naam"] == "Alex de Vries"

    def test_file_adapter_reads_json(self, tmp_path):
        path = tmp_path / "export.json"
        path.write_text(json.dumps([_raw(), _raw(member_id="M-2", lidnummer="1002")]), encoding="utf-8")
        rows = list(FileSourceAdapter(str(path)).rows())
        assert [r["lidnummer"] for r in rows] == ["1001", "1002"]

    def test_file_adapter_reads_json_rows_envelope(self, tmp_path):
        path = tmp_path / "export.json"
        path.write_text(json.dumps({"rows": [_raw()]}), encoding="utf-8")
        assert len(list(FileSourceAdapter(str(path)).rows())) == 1

    def test_file_adapter_does_not_write_the_source(self, tmp_path):
        # Reading must not change the file on disk (non-destructive, R5.2).
        path = tmp_path / "export.csv"
        original = "lidnummer,naam,email,status,lidmaatschapstype,ingangsdatum,regio\n1001,Alex,a@x.com,actief,Erelid,2010-01-01,Noord\n"
        path.write_text(original, encoding="utf-8")
        list(FileSourceAdapter(str(path)).rows())
        assert path.read_text(encoding="utf-8") == original

    def test_iterable_adapter_hands_out_copies(self):
        rows = [_raw()]
        adapter = IterableSourceAdapter(rows)
        out = list(adapter.rows())
        out[0]["naam"] = "changed"
        assert rows[0]["naam"] == "Alex de Vries"  # source untouched

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
        adapter = IterableSourceAdapter([_raw(), _raw(member_id="M-2", lidnummer="1002")])
        plan = build_backfill_plan(adapter)
        assert plan.source_row_count == 2
        assert plan.ok_count == 2
        assert plan.error_count == 0
        assert plan.tenant_id == "h-dcn"

    def test_plan_collects_errors_without_aborting(self):
        adapter = IterableSourceAdapter(
            [_raw(), _raw(member_id="M-2", lidnummer="1002", naam="")]  # 2nd is bad
        )
        plan = build_backfill_plan(adapter)
        assert plan.ok_count == 1
        assert plan.error_count == 1

    def test_plan_flags_duplicate_member_numbers_in_batch(self):
        adapter = IterableSourceAdapter(
            [_raw(member_id="M-1", lidnummer="1001"), _raw(member_id="M-2", lidnummer="1001")]
        )
        plan = build_backfill_plan(adapter)
        assert "1001" in plan.duplicate_member_numbers
        assert sorted(plan.duplicate_member_numbers["1001"]) == ["M-1", "M-2"]

    def test_plan_records_rows_missing_region(self):
        adapter = IterableSourceAdapter([_raw(regio="")])
        plan = build_backfill_plan(adapter)
        assert plan.rows_missing_region == ["M-1"]

    def test_field_mapping_summary_counts_populated_fields(self):
        adapter = IterableSourceAdapter([_raw(), _raw(member_id="M-2", lidnummer="1002")])
        summary = build_backfill_plan(adapter).field_mapping_summary()
        assert summary["membership.member_number"] == 2
        assert summary["personal.name"] == 2
        assert summary["scope_values.region"] == 2
        assert summary["overlay.motortype"] == 2


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
        rc = runner.main(["--source", FIXTURE])
        assert rc == 0
        assert "DRY-RUN" in capsys.readouterr().out

    def test_fail_fast_when_members_table_missing(self, monkeypatch, capsys):
        monkeypatch.delenv(td.MEMBERS_TABLE_ENV_VAR, raising=False)
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        rc = runner.main(["--source", FIXTURE])
        assert rc == 1  # DynamoDBConfigError surfaced as exit 1


class TestRunnerApply:
    def test_apply_saves_each_record_via_the_repository(self, members_env, fake_repo, capsys):
        rc = runner.backfill(FIXTURE, region="eu-west-1", apply=True, repo=fake_repo)
        assert rc == 0
        listed = fake_repo.list_members("h-dcn")
        assert sorted(m["member_id"] for m in listed) == ["M-1001", "M-1002", "M-1003", "M-1004"]
        # tenant stamped + scope + overlay landed via the transform
        m1 = fake_repo.get_member("h-dcn", "M-1001")
        assert m1["tenant_id"] == "h-dcn"
        assert m1["scope_values"]["region"] == ["Noord"]
        assert m1["overlay"]["motortype"] == "Honda CB500"
        assert m1["membership"]["membership_type"] == "erelid"

    def test_apply_reports_conflict_not_overwrite(self, members_env, fake_repo, capsys, tmp_path):
        # Two rows share member number 1001 but are different members → 2nd is a real conflict.
        export = tmp_path / "dupes.json"
        export.write_text(
            json.dumps(
                [
                    _raw(member_id="M-1", lidnummer="1001", naam="Alex"),
                    _raw(member_id="M-2", lidnummer="1001", naam="Bram"),
                ]
            ),
            encoding="utf-8",
        )
        rc = runner.backfill(str(export), region="eu-west-1", apply=True, repo=fake_repo)
        # exit 3 = applied but with a reconcilable conflict.
        assert rc == 3
        out = capsys.readouterr().out
        assert "conflicts : 1" in out
        assert "CONFLICT" in out
        # The FIRST writer stands; the conflicting one did NOT overwrite it.
        assert fake_repo.get_member("h-dcn", "M-1")["personal"]["name"] == "Alex"
        assert fake_repo.get_member("h-dcn", "M-2") is None

    def test_apply_refuses_a_batch_with_mapping_errors(self, members_env, fake_repo, capsys, tmp_path):
        export = tmp_path / "bad.json"
        export.write_text(
            json.dumps([_raw(), _raw(member_id="M-2", lidnummer="1002", naam="")]),
            encoding="utf-8",
        )
        rc = runner.backfill(str(export), region="eu-west-1", apply=True, repo=fake_repo)
        assert rc == 2  # refused
        # Nothing written because the batch had an unmappable row.
        assert fake_repo.list_members("h-dcn") == []

    def test_apply_is_idempotent_on_resave(self, members_env, fake_repo, tmp_path):
        export = tmp_path / "one.json"
        export.write_text(json.dumps([_raw(member_id="M-1", lidnummer="1001")]), encoding="utf-8")
        assert runner.backfill(str(export), region="eu-west-1", apply=True, repo=fake_repo) == 0
        # Re-apply the SAME member — repository idempotent re-save, no conflict.
        assert runner.backfill(str(export), region="eu-west-1", apply=True, repo=fake_repo) == 0
        assert len(fake_repo.list_members("h-dcn")) == 1
