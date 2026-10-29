"""
03a C6 HARD GATE — unit tests for the all-tenant zero-un-migrated-`choices` scan
(``scripts/scan_config_fields_un_migrated_choices.py``).

The scan is the BLOCKING deployment step gating C6 fail-loud (design 03a "Hard gate before C6
goes live" / "Deployment ordering" §4): it must PASS (exit 0) iff ZERO un-migrated bare-``choices``
rows remain across EVERY tenant, and FAIL (exit non-zero) — naming the offender — if any remain.

Tested without AWS / boto3 (steering 34/39), two layers mirroring the C7 migration test:

1. **Pure scan core** (:func:`scan_overlay`) — over the COMMITTED REAL h-dcn fixture (the
   ``personal.gender`` override under rich-dict ``choices``) and a clean post-migration overlay.
   Proves the gate reuses the C7 enumerator's offender predicate: a bare-``choices`` entry is an
   offender, an ``options``-only entry is not.

2. **Live driver + exit-code contract** (:func:`scan_tenant` / :func:`scan_tenants` /
   :func:`main`) — over an in-memory ``FakeTable`` wired to the REAL
   :class:`MembersProjectionReader` resolved read (no mocking of the read mechanics). Proves the
   gate PASSES (exit 0) on a clean tenant set, FAILS (exit 1) when a bare-``choices`` row is
   present naming the offender, and that the all-tenant discovery scan finds every tenant with a
   ``config#fields`` row.

**Validates: Requirements 2.3** · **Components: C6 (hard gate), C7 (confirms backfill completeness)**
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
    path = os.path.join(_REPO_ROOT, "scripts", "scan_config_fields_un_migrated_choices.py")
    spec = importlib.util.spec_from_file_location(
        "scan_config_fields_un_migrated_choices", path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scan = _load_scan_module()

from services import projection_schema as schema  # noqa: E402

from sam.members.repository.projection_config_reader import MembersProjectionReader  # noqa: E402

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _load_fixture(name: str) -> dict:
    with open(os.path.join(_FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 1. Pure scan core — offender predicate over the REAL committed fixture
# ═══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_scan_overlay_flags_the_real_hdcn_gender_choices_override():
    overlay = _load_fixture("hdcn_config_fields_overlay.json")
    result = scan.scan_overlay("h-dcn", overlay)
    assert not result.clean
    offenders = {(o.map_name, o.entry_key) for o in result.offenders}
    assert ("overrides", "personal.gender") in offenders, (
        "the real h-dcn personal.gender override carries bare `choices` and must be flagged"
    )


@pytest.mark.unit
def test_scan_overlay_clean_when_only_options_no_choices():
    # POST-migration shape: options present, choices absent -> no offenders.
    overlay = {
        "fields": {},
        "overrides": {
            "personal.gender": {
                "type": "enum",
                "options": [{"value": "man"}, {"value": "vrouw"}],
                "order": 60,
            }
        },
    }
    result = scan.scan_overlay("clean-tenant", overlay)
    assert result.clean
    assert result.offenders == ()


@pytest.mark.unit
def test_scan_overlay_flags_variable_field_choices_under_fields_map():
    overlay = {
        "fields": {"referral_source": {"type": "enum", "choices": ["internet", "facebook"]}},
        "overrides": {},
    }
    result = scan.scan_overlay("v-tenant", overlay)
    assert not result.clean
    assert {(o.map_name, o.entry_key) for o in result.offenders} == {
        ("fields", "referral_source")
    }


# ═══════════════════════════════════════════════════════════════════════════════════════════
# 2. Live driver over the REAL reader + exit-code contract
# ═══════════════════════════════════════════════════════════════════════════════════════════


class FakeTable:
    """In-memory DynamoDB Table stand-in: query (per-partition read) + scan (discovery).

    Read-only for the scan's purposes — the gate never writes. ``query`` returns one tenant's
    partition (what ``MembersProjectionReader.get_raw_fields_overlay`` uses); ``scan`` returns the
    whole table (what the operator-level tenant discovery uses).
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def query(self, KeyConditionExpression=None, **_kwargs):
        expr = KeyConditionExpression.get_expression()
        tenant_id = expr["values"][1]
        return {"Items": [dict(v) for k, v in self.store.items() if k[0] == tenant_id]}

    def scan(self, **_kwargs):
        # Single page (no pagination needed for the fake); returns every item.
        return {"Items": [dict(v) for v in self.store.values()]}


def _seed_fields_row(table, tenant_id, *, fields=None, overrides=None):
    key = (
        tenant_id,
        schema.build_sort_key(schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS),
    )
    table.store[key] = {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS
        ),
        "fields": fields or {},
        "overrides": overrides or {},
        "functional_groups": {},
        schema.VERSION_ATTR: "v-seed",
    }


@pytest.mark.unit
def test_scan_tenant_clean_tenant_has_no_offenders():
    table = FakeTable()
    _seed_fields_row(
        table,
        "clean-tenant",
        overrides={"personal.gender": {"type": "enum", "options": [{"value": "man"}]}},
    )
    reader = MembersProjectionReader(table=table)
    result = scan.scan_tenant("clean-tenant", reader=reader)
    assert result.clean


@pytest.mark.unit
def test_scan_tenant_flags_a_bare_choices_row():
    real_gender = _load_fixture("hdcn_config_fields_overlay.json")["overrides"]["personal.gender"]
    table = FakeTable()
    _seed_fields_row(table, "h-dcn", overrides={"personal.gender": dict(real_gender)})
    reader = MembersProjectionReader(table=table)
    result = scan.scan_tenant("h-dcn", reader=reader)
    assert not result.clean
    assert {(o.map_name, o.entry_key) for o in result.offenders} == {
        ("overrides", "personal.gender")
    }


@pytest.mark.unit
def test_scan_passes_exit_zero_on_clean_tenant_set(capsys):
    # A clean tenant set (all options, no choices) -> PASS, exit 0.
    table = FakeTable()
    _seed_fields_row(
        table,
        "clean-a",
        overrides={"personal.gender": {"type": "enum", "options": [{"value": "man"}]}},
    )
    _seed_fields_row(
        table,
        "clean-b",
        fields={"referral_source": {"type": "enum", "options": [{"value": "internet"}]}},
    )
    reader = MembersProjectionReader(table=table)
    results = scan.scan_tenants(["clean-a", "clean-b"], reader=reader)
    assert all(r.clean for r in results)
    assert scan._print_summary(results) == 0
    out = capsys.readouterr().out
    assert "PASS" in out


@pytest.mark.unit
def test_scan_fails_non_zero_and_names_offender_when_bare_choices_present(capsys):
    real_gender = _load_fixture("hdcn_config_fields_overlay.json")["overrides"]["personal.gender"]
    table = FakeTable()
    _seed_fields_row(table, "clean-a", overrides={"x.y": {"options": [{"value": "ok"}]}})
    _seed_fields_row(table, "dirty-h-dcn", overrides={"personal.gender": dict(real_gender)})
    reader = MembersProjectionReader(table=table)

    results = scan.scan_tenants(["clean-a", "dirty-h-dcn"], reader=reader)
    assert scan._print_summary(results) == 1, "a remaining bare-`choices` row must FAIL the gate"

    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "dirty-h-dcn" in out, "the FAIL report must name the offender tenant"
    assert "personal.gender" in out, "the report must name the offender field"


@pytest.mark.unit
def test_discover_tenants_finds_every_tenant_with_a_config_fields_row():
    table = FakeTable()
    _seed_fields_row(table, "tenant-a", overrides={"x.y": {"options": [{"value": "ok"}]}})
    _seed_fields_row(table, "tenant-b", fields={"f": {"options": [{"value": "v"}]}})
    # A non-config#fields row for tenant-c must NOT make it a scanned tenant.
    table.store[("tenant-c", schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope"))] = {
        schema.PARTITION_KEY_ATTR: "tenant-c",
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "scope"),
    }

    discovered = scan._discover_tenants_with_config_fields(table=table)
    assert discovered == ["tenant-a", "tenant-b"]


@pytest.mark.unit
def test_main_all_tenants_discovery_fails_when_any_tenant_un_migrated(monkeypatch, capsys):
    # End-to-end-ish: main() discovers all tenants (no --tenant list) and FAILs on an offender.
    real_gender = _load_fixture("hdcn_config_fields_overlay.json")["overrides"]["personal.gender"]
    table = FakeTable()
    _seed_fields_row(table, "clean-a", overrides={"x.y": {"options": [{"value": "ok"}]}})
    _seed_fields_row(table, "dirty-h-dcn", overrides={"personal.gender": dict(real_gender)})

    # main() uses reader.table for discovery; the fake reader exposes the FakeTable there.
    reader = MembersProjectionReader(table=table)
    monkeypatch.setattr(scan, "_build_reader", lambda table=None: reader)

    exit_code = scan.main([])  # no args -> discover all tenants
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "dirty-h-dcn" in out


@pytest.mark.unit
def test_main_explicit_tenant_list_passes_on_clean(monkeypatch, capsys):
    table = FakeTable()
    _seed_fields_row(
        table,
        "clean-a",
        overrides={"personal.gender": {"type": "enum", "options": [{"value": "man"}]}},
    )
    reader = MembersProjectionReader(table=table)
    monkeypatch.setattr(scan, "_build_reader", lambda table=None: reader)

    exit_code = scan.main(["--tenant", "clean-a"])
    assert exit_code == 0
    assert "PASS" in capsys.readouterr().out
