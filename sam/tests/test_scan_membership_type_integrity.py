"""
03b BU-7 (Task 7.1) — unit tests for the membership_type collapse INTEGRITY SCAN
(``scripts/scan_membership_type_integrity.py``), the automated form of design.md's
"Migration-safety proof" (Req 3.6) and the Req 6.3 pre/post-migration integrity scan.

The scan is the gate for the fold: it must PASS (exit 0) iff, across EVERY tenant, ZERO ACTIVE
catalog rows remain un-folded (every active ``type_code`` is a field option) AND ZERO member
references are orphaned (every member-held ``membership.membership_type`` resolves to a field
option, INCLUDING a grandfathered ``allowed:false`` option); and FAIL (exit 1) — naming the
offender — otherwise.

Tested without AWS / boto3 (steering 34/39), two layers mirroring the ``choices`` gate's test:

1. **Pure scan core** (:func:`scan_membership_type`) over the COMMITTED REAL h-dcn fixture
   ``backend/tests/fixtures/hdcn_membership_type_integrity.json`` — the design-proof data: 7 field
   options (incl. ``erelid``=allowed:false), the 7 catalog rows (``erelid`` active:false), and the
   real 1215-member tally. Proves the PROOF itself holds (zero un-folded, zero orphaned) and that
   the two checks fire correctly on deliberately-broken variants of the real data.

2. **Live driver + exit-code contract** (:func:`scan_tenant` / :func:`scan_tenants` /
   :func:`main`) — the field options flow through the REAL :class:`MembersProjectionReader`
   resolved read over an in-memory ``FakeTable`` (no mocking of the config read mechanics, per
   steering 39's round-trip-against-real-data rule); the catalog + member tally come from a small
   in-memory fake repository. Proves the gate PASSES on a clean tenant set and FAILS naming the
   offender when a row is un-folded or a member reference is orphaned.

**Validates: Requirements 3.6, 6.2, 6.3** · **Property 1 (no orphaned reference), Property 2
(grandfather preserved)**
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)


# ── Load the scan module from scripts/ (not an importable package) ──────────────────────────
def _load_scan_module():
    path = os.path.join(_REPO_ROOT, "scripts", "scan_membership_type_integrity.py")
    spec = importlib.util.spec_from_file_location("scan_membership_type_integrity", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scan = _load_scan_module()

from services import projection_schema as schema  # noqa: E402

from sam.members.repository.projection_config_reader import MembersProjectionReader  # noqa: E402

_FIXTURES = os.path.join(_REPO_ROOT, "backend", "tests", "fixtures")


def _load_fixture() -> dict:
    with open(
        os.path.join(_FIXTURES, "hdcn_membership_type_integrity.json"), encoding="utf-8"
    ) as f:
        return json.load(f)


def _real_inputs():
    """The three REAL slices from the committed fixture, as the pure core's typed inputs."""
    fx = _load_fixture()
    field_options = [scan.FieldOption.from_raw(o) for o in fx["field_options"]]
    catalog_rows = [scan.CatalogRow.from_raw(r) for r in fx["catalog_rows"]]
    member_tally = dict(fx["member_tally"])
    return field_options, catalog_rows, member_tally


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 1. Pure scan core — the design proof over the REAL committed fixture
# ═══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_real_hdcn_fixture_is_clean_the_migration_safety_proof_holds():
    # The design "Migration-safety proof": every stored value maps to a field option -> zero
    # orphans; every active catalog type is a field option -> zero un-folded rows.
    field_options, catalog_rows, member_tally = _real_inputs()
    result = scan.scan_membership_type(
        "h-dcn",
        field_options=field_options,
        catalog_rows=catalog_rows,
        member_tally=member_tally,
    )
    assert result.clean, (
        "the real h-dcn fold is proven orphan-free + fully folded; a dirty result means the "
        "fixture or the proof drifted"
    )
    assert result.unfolded_catalog_rows == ()
    assert result.orphaned_member_references == ()


@pytest.mark.unit
def test_real_fixture_tally_totals_the_full_live_population():
    # Guard the provenance: the committed tally must still sum to the design proof's 1215 members
    # (936+200+57+17+4+1). A silent edit to the fixture that breaks this is caught here.
    _, _, member_tally = _real_inputs()
    assert sum(member_tally.values()) == 1215


@pytest.mark.unit
def test_grandfathered_erelid_resolves_and_is_not_an_orphan():
    # Property 2: the retired erelid (allowed:false) is a field option, so the 4 members holding
    # it resolve — it is grandfathered, NOT orphaned.
    field_options, catalog_rows, member_tally = _real_inputs()
    assert "erelid" in member_tally and member_tally["erelid"] == 4
    erelid_opt = next(o for o in field_options if o.value == "erelid")
    assert erelid_opt.allowed is False  # retired: hidden from picker …
    result = scan.scan_membership_type(
        "h-dcn",
        field_options=field_options,
        catalog_rows=catalog_rows,
        member_tally=member_tally,
    )
    # … yet no orphan reports erelid (the allowed:false option still resolves the reference).
    assert all(o.value != "erelid" for o in result.orphaned_member_references)


@pytest.mark.unit
def test_removing_an_active_catalog_type_from_options_is_flagged_un_folded():
    # Drop `donateur` (active catalog row, 1 member) from the field options: it is now both an
    # un-folded active catalog row AND an orphaned member reference.
    field_options, catalog_rows, member_tally = _real_inputs()
    field_options = [o for o in field_options if o.value != "donateur"]
    result = scan.scan_membership_type(
        "h-dcn",
        field_options=field_options,
        catalog_rows=catalog_rows,
        member_tally=member_tally,
    )
    assert not result.clean
    assert {o.type_code for o in result.unfolded_catalog_rows} == {"donateur"}
    orphan = {o.value: o.member_count for o in result.orphaned_member_references}
    assert orphan == {"donateur": 1}


@pytest.mark.unit
def test_an_active_catalog_type_with_zero_members_must_still_be_folded():
    # `sponsor` is an ACTIVE catalog row with 0 members (not in the tally). It must still appear
    # as a field option — removing it is an un-folded row but NOT an orphan (nobody holds it).
    field_options, catalog_rows, member_tally = _real_inputs()
    assert "sponsor" not in member_tally  # 0 members, per the proof
    field_options = [o for o in field_options if o.value != "sponsor"]
    result = scan.scan_membership_type(
        "h-dcn",
        field_options=field_options,
        catalog_rows=catalog_rows,
        member_tally=member_tally,
    )
    assert {o.type_code for o in result.unfolded_catalog_rows} == {"sponsor"}
    assert result.orphaned_member_references == ()  # no member holds sponsor -> no orphan


@pytest.mark.unit
def test_a_retired_catalog_row_absent_from_options_is_not_un_folded():
    # A retired (active:false) catalog row need NOT be a field option — only active rows must fold.
    # Rebuild the fixture with erelid removed from BOTH the options and the tally: since the erelid
    # catalog row is active:false, its absence from the options is NOT an un-folded offender.
    field_options, catalog_rows, member_tally = _real_inputs()
    field_options = [o for o in field_options if o.value != "erelid"]
    member_tally = {k: v for k, v in member_tally.items() if k != "erelid"}
    erelid_row = next(r for r in catalog_rows if r.type_code == "erelid")
    assert erelid_row.active is False
    result = scan.scan_membership_type(
        "h-dcn",
        field_options=field_options,
        catalog_rows=catalog_rows,
        member_tally=member_tally,
    )
    assert result.clean, "a retired catalog row absent from the options is neither un-folded nor an orphan"


@pytest.mark.unit
def test_a_member_value_in_no_option_is_an_orphan():
    # An orphan independent of the catalog: a member holds a value that is not any field option.
    field_options, catalog_rows, member_tally = _real_inputs()
    member_tally = dict(member_tally)
    member_tally["ghost_type"] = 3
    result = scan.scan_membership_type(
        "h-dcn",
        field_options=field_options,
        catalog_rows=catalog_rows,
        member_tally=member_tally,
    )
    orphan = {o.value: o.member_count for o in result.orphaned_member_references}
    assert orphan == {"ghost_type": 3}


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 2. Resolved-read extractors (field options from the real reader wire shape; member tally)
# ═══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_extract_field_options_reads_the_dotted_override_options():
    fx = _load_fixture()
    wire = {
        "fields": {},
        "fixed_overrides": {
            scan.DOTTED_MEMBERSHIP_TYPE_KEY: {"type": "enum", "options": fx["field_options"]}
        },
    }
    options = scan.extract_field_options(wire)
    assert [o.value for o in options] == [o["value"] for o in fx["field_options"]]
    by_val = {o.value: o for o in options}
    assert by_val["erelid"].allowed is False
    assert by_val["gewoon_lid"].allowed is True


@pytest.mark.unit
def test_extract_field_options_pre_fold_row_has_no_inline_options():
    # A pre-fold override (application flags only, no inline options) yields an empty option list,
    # so every active catalog row then reports un-folded (correct: the fold has not run).
    wire = {
        "fields": {},
        "fixed_overrides": {
            scan.DOTTED_MEMBERSHIP_TYPE_KEY: {"application_visible": True}
        },
    }
    assert scan.extract_field_options(wire) == []


@pytest.mark.unit
def test_tally_member_types_counts_and_skips_absent_values():
    members = [
        {"membership": {"membership_type": "gewoon_lid"}},
        {"membership": {"membership_type": "gewoon_lid"}},
        {"membership": {"membership_type": "erelid"}},
        {"membership": {}},  # no membership_type -> skipped (holds no reference)
        {"personal": {}},  # no membership block -> skipped
    ]
    assert scan.tally_member_types(members) == {"gewoon_lid": 2, "erelid": 1}


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 3. Live driver over the REAL reader + a fake repository + exit-code contract
# ═══════════════════════════════════════════════════════════════════════════════════════════


class FakeTable:
    """In-memory DynamoDB Table stand-in for the config reader: query + scan (discovery)."""

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def query(self, KeyConditionExpression=None, **_kwargs):
        expr = KeyConditionExpression.get_expression()
        tenant_id = expr["values"][1]
        return {"Items": [dict(v) for k, v in self.store.items() if k[0] == tenant_id]}

    def scan(self, **_kwargs):
        return {"Items": [dict(v) for v in self.store.values()]}


def _seed_fields_row(table, tenant_id, *, overrides=None):
    sk = schema.build_sort_key(schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS)
    table.store[(tenant_id, sk)] = {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: sk,
        "fields": {},
        "overrides": overrides or {},  # storage key is `overrides`; reader serves it as fixed_overrides
        "functional_groups": {},
        schema.VERSION_ATTR: "v-seed",
    }


class FakeMembersRepository:
    """Catalog + member surface the scan's live driver reads (the two non-config slices)."""

    def __init__(self):
        self._catalog: dict[str, list] = {}
        self._members: dict[str, list] = {}

    def add_catalog(self, tenant_id, type_code, *, active=True):
        from sam.members.domain.membership_type_catalog import MembershipTypeEntry

        self._catalog.setdefault(tenant_id, []).append(
            MembershipTypeEntry(
                tenant_id=tenant_id,
                type_code=type_code,
                label={"nl": type_code},
                active=active,
            )
        )

    def add_members(self, tenant_id, value, count):
        for _ in range(count):
            self._members.setdefault(tenant_id, []).append(
                {"membership": {"membership_type": value}}
            )

    def list_membership_types(self, tenant_id, *, active_only=False):
        entries = list(self._catalog.get(tenant_id, []))
        return [e for e in entries if e.active] if active_only else entries

    def list_members(self, tenant_id, **_kwargs):
        return list(self._members.get(tenant_id, []))


def _mt_override(options):
    return {scan.DOTTED_MEMBERSHIP_TYPE_KEY: {"type": "enum", "options": options}}


@pytest.mark.unit
def test_scan_tenant_clean_over_real_reader_and_fixture():
    fx = _load_fixture()
    table = FakeTable()
    _seed_fields_row(table, "h-dcn", overrides=_mt_override(fx["field_options"]))
    reader = MembersProjectionReader(table=table)

    repo = FakeMembersRepository()
    for row in fx["catalog_rows"]:
        repo.add_catalog("h-dcn", row["type_code"], active=row["active"])
    for value, count in fx["member_tally"].items():
        repo.add_members("h-dcn", value, count)

    result = scan.scan_tenant("h-dcn", reader=reader, repository=repo)
    assert result.clean


@pytest.mark.unit
def test_scan_tenant_flags_un_folded_active_catalog_row():
    table = FakeTable()
    # Field options missing the active `donateur` the catalog still carries.
    _seed_fields_row(
        table,
        "h-dcn",
        overrides=_mt_override([{"value": "gewoon_lid", "allowed": True}]),
    )
    reader = MembersProjectionReader(table=table)
    repo = FakeMembersRepository()
    repo.add_catalog("h-dcn", "gewoon_lid", active=True)
    repo.add_catalog("h-dcn", "donateur", active=True)  # active, but not a field option
    repo.add_members("h-dcn", "gewoon_lid", 5)

    result = scan.scan_tenant("h-dcn", reader=reader, repository=repo)
    assert not result.clean
    assert {o.type_code for o in result.unfolded_catalog_rows} == {"donateur"}


@pytest.mark.unit
def test_scan_passes_exit_zero_on_clean_tenant_set(capsys):
    table = FakeTable()
    _seed_fields_row(table, "clean-a", overrides=_mt_override([{"value": "x", "allowed": True}]))
    reader = MembersProjectionReader(table=table)
    repo = FakeMembersRepository()
    repo.add_catalog("clean-a", "x", active=True)
    repo.add_members("clean-a", "x", 3)

    results = scan.scan_tenants(["clean-a"], reader=reader, repository=repo)
    assert all(r.clean for r in results)
    assert scan._print_summary(results) == 0
    assert "PASS" in capsys.readouterr().out


@pytest.mark.unit
def test_scan_fails_non_zero_and_names_offender_on_orphan(capsys):
    table = FakeTable()
    # `died` members exist but `died` is not a field option -> orphan.
    _seed_fields_row(
        table, "dirty-h-dcn", overrides=_mt_override([{"value": "active", "allowed": True}])
    )
    reader = MembersProjectionReader(table=table)
    repo = FakeMembersRepository()
    repo.add_catalog("dirty-h-dcn", "active", active=True)
    repo.add_members("dirty-h-dcn", "active", 10)
    repo.add_members("dirty-h-dcn", "ghost_type", 2)  # orphaned reference

    results = scan.scan_tenants(["dirty-h-dcn"], reader=reader, repository=repo)
    assert scan._print_summary(results) == 1

    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "dirty-h-dcn" in out
    assert "ghost_type" in out


@pytest.mark.unit
def test_main_all_tenants_discovery_fails_when_any_tenant_has_an_offender(monkeypatch, capsys):
    table = FakeTable()
    _seed_fields_row(table, "clean-a", overrides=_mt_override([{"value": "ok", "allowed": True}]))
    _seed_fields_row(
        table, "dirty-h-dcn", overrides=_mt_override([{"value": "active", "allowed": True}])
    )
    reader = MembersProjectionReader(table=table)
    repo = FakeMembersRepository()
    repo.add_catalog("clean-a", "ok", active=True)
    repo.add_members("clean-a", "ok", 1)
    repo.add_catalog("dirty-h-dcn", "active", active=True)
    repo.add_catalog("dirty-h-dcn", "sponsor", active=True)  # active but not a field option

    monkeypatch.setattr(
        scan, "_build_reader_and_repository", lambda table=None: (reader, repo)
    )

    exit_code = scan.main([])  # no args -> discover all tenants via the fake table scan
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "dirty-h-dcn" in out
    assert "sponsor" in out


@pytest.mark.unit
def test_main_explicit_tenant_list_passes_on_clean(monkeypatch, capsys):
    table = FakeTable()
    _seed_fields_row(table, "clean-a", overrides=_mt_override([{"value": "ok", "allowed": True}]))
    reader = MembersProjectionReader(table=table)
    repo = FakeMembersRepository()
    repo.add_catalog("clean-a", "ok", active=True)
    repo.add_members("clean-a", "ok", 2)
    monkeypatch.setattr(
        scan, "_build_reader_and_repository", lambda table=None: (reader, repo)
    )

    exit_code = scan.main(["--tenant", "clean-a"])
    assert exit_code == 0
    assert "PASS" in capsys.readouterr().out
