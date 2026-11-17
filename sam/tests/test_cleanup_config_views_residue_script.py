"""Members config Phase 2 (step d) — tests for the ``config#views`` residue operator script.

Target: ``scripts/cleanup_config_views_residue.py`` — the runnable entry point for
``ProjectionSync.delete_config_views_residue`` (raised by the backlog item
``members-preferred-overview-columns.md``, F1: the routine had no production caller).

No AWS, no MySQL: the residue routine is driven over an in-memory fake table (the same seam the
sync's own unit tests use) and the CLI parsing/guard behaviour is exercised directly.

**Validates: Requirements 2.1, 2.6** (the retired ``config#views`` residue is removable —
tenant-scoped, idempotent, dry-run by default) · **Components: Phase 2 step (d)**
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

import services.projection_schema as schema  # noqa: E402
from services._projection_source import SourceProvider  # noqa: E402


def _load_script_module():
    """Load the operator script from ``scripts/`` (it is not an importable package)."""
    path = os.path.join(_REPO_ROOT, "scripts", "cleanup_config_views_residue.py")
    spec = importlib.util.spec_from_file_location("cleanup_config_views_residue", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script_module()


class FakeTable:
    """Minimal in-memory stand-in for a boto3 ``Table`` (only what the cleanup uses)."""

    def __init__(self, items=None):
        self.store = dict(items or {})
        self.delete_calls: list[tuple[str, str]] = []

    def get_item(self, Key):
        item = self.store.get((Key[schema.PARTITION_KEY_ATTR], Key[schema.SORT_KEY_ATTR]))
        return {"Item": item} if item is not None else {}

    def delete_item(self, Key):
        key = (Key[schema.PARTITION_KEY_ATTR], Key[schema.SORT_KEY_ATTR])
        self.delete_calls.append(key)
        self.store.pop(key, None)


def _views_sk() -> str:
    return schema.build_sort_key(schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_VIEWS)


def _fields_sk() -> str:
    return schema.build_sort_key(schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS)


def _seed_views_residue(table, administration, *, version=1) -> None:
    """Write a pre-retirement ``config#views`` residue row directly into the fake table."""
    sk = _views_sk()
    table.store[(administration, sk)] = {
        schema.PARTITION_KEY_ATTR: administration,
        schema.SORT_KEY_ATTR: sk,
        schema.VERSION_ATTR: version,
        "contexts": [{"name": "default", "columns": ["name", "email"]}],
    }


# ── tenant parsing (pure) ───────────────────────────────────────────────────────────────────


def test_parse_tenants_cleans_dedupes_and_keeps_order():
    assert script.parse_tenants("b , a,,b ,  c  ") == ["b", "a", "c"]
    assert script.parse_tenants("") == []
    assert script.parse_tenants("  ,  , ") == []


def test_explicit_tenant_source_satisfies_the_source_provider_protocol():
    """The stub the cleanup constructs must be a valid ``SourceProvider`` (protocol guard)."""
    source = script._ExplicitTenantSource(["h-dcn", "other"])
    assert isinstance(source, SourceProvider)
    assert source.list_administrations() == ["h-dcn", "other"]


# ── the cleanup itself (dry run default, tenant-scoped, idempotent) ─────────────────────────


def test_dry_run_is_the_default_and_makes_no_change():
    table = FakeTable()
    _seed_views_residue(table, "h-dcn")

    summary = script.cleanup_config_views_residue(["h-dcn"], table=table)

    assert summary == {"scanned": 1, "deleted": 0}
    assert _views_sk() in [sk for _pk, sk in table.store]
    assert table.delete_calls == []


def test_apply_deletes_only_the_views_row_for_the_named_tenants():
    table = FakeTable()
    _seed_views_residue(table, "h-dcn")
    _seed_views_residue(table, "other-tenant")  # a DIFFERENT partition: must survive
    table.store[("h-dcn", _fields_sk())] = {
        schema.PARTITION_KEY_ATTR: "h-dcn",
        schema.SORT_KEY_ATTR: _fields_sk(),
    }

    summary = script.cleanup_config_views_residue(["h-dcn"], apply=True, table=table)

    assert summary == {"scanned": 1, "deleted": 1}
    assert table.delete_calls == [("h-dcn", _views_sk())]
    assert ("h-dcn", _views_sk()) not in table.store
    assert ("h-dcn", _fields_sk()) in table.store       # only the views key is touched
    assert ("other-tenant", _views_sk()) in table.store  # tenant-scoped: never cross-partition


def test_apply_is_idempotent_on_a_rerun():
    table = FakeTable()
    _seed_views_residue(table, "h-dcn")

    first = script.cleanup_config_views_residue(["h-dcn"], apply=True, table=table)
    second = script.cleanup_config_views_residue(["h-dcn"], apply=True, table=table)

    assert first == {"scanned": 1, "deleted": 1}
    assert second == {"scanned": 0, "deleted": 0}
    assert table.delete_calls == [("h-dcn", _views_sk())]


def test_a_tenant_without_residue_contributes_zero():
    table = FakeTable()
    _seed_views_residue(table, "h-dcn")

    summary = script.cleanup_config_views_residue(["clean-tenant"], apply=True, table=table)

    assert summary == {"scanned": 0, "deleted": 0}
    assert table.delete_calls == []


# ── CLI contract (dry run default; --apply writes; --tenants parsing; no-tenant guard) ─────


def test_main_parses_tenants_and_defaults_to_a_dry_run():
    table = FakeTable()
    _seed_views_residue(table, "h-dcn")

    assert script.main(["--tenants", "h-dcn, h-dcn ,other"], table=table) == 0
    assert table.delete_calls == []  # dry run by default


def test_main_apply_deletes():
    table = FakeTable()
    _seed_views_residue(table, "h-dcn")

    assert script.main(["--tenants", "h-dcn", "--apply"], table=table) == 0
    assert table.delete_calls == [("h-dcn", _views_sk())]


def test_main_requires_a_tenant_selection():
    with pytest.raises(SystemExit):
        script.main([], table=FakeTable())
