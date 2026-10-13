"""
Property + example tests for the Phase 2 overrides -> fixed_overrides migration.

Covers task 5.2 of the "Delete the Redundant Surface" spec.

Property 2 (migration preserves data and is idempotent) exercises the PURE,
DB-free helper ``rename_overrides_key`` over randomly generated overlays:
  1. Merge invariant: result ``fixed_overrides`` carries every pre-existing entry;
     on a per-key collision the pre-existing ``fixed_overrides`` entry WINS.
  2. Other top-level overlay keys (e.g. ``fields``) are byte-for-byte unchanged.
  3. Idempotence: ``f(f(x)) == f(x)`` and the result never carries a top-level
     ``overrides`` key.

The example tests exercise ``migrate(dry_run=...)`` against mocked DatabaseManager
+ ParameterService (Flask-plane isolation, steering 34): dry-run makes NO write,
the applied run performs the rename via ``ParameterService.set_param`` with the
merged overlay, and only ``members.field_overlay`` parameter rows are touched
(member records are never queried or written).

The autouse connection guard (tests/unit/conftest.py) forbids a real DB.

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 8.1, 8.3
Reference: .kiro/specs/Members/Parameter redesign/phase-2-delete-redundant-surface/
"""

import copy
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, strategies as st

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from migrations import migrate_overrides_to_fixed_overrides as mig
from migrations.migrate_overrides_to_fixed_overrides import (
    migrate,
    overlay_needs_rewrite,
    rename_overrides_key,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# JSON-ish override VALUES: the migration copies them verbatim so they can be
# anything that survives a round-trip (we only assert identity-of-content here).
_override_values = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-1000, max_value=1000),
        st.text(max_size=12),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(st.text(min_size=1, max_size=6), children, max_size=3),
    ),
    max_leaves=5,
)

# Override MAPS keyed by field name. A shared key pool makes collisions between
# the legacy ``overrides`` map and the canonical ``fixed_overrides`` map likely.
_override_keys = st.sampled_from(["name", "email", "status", "region", "member_id", "notes"])
_override_maps = st.dictionaries(_override_keys, _override_values, max_size=4)

# Arbitrary OTHER top-level overlay keys that must be left byte-for-byte unchanged.
_other_keys = st.dictionaries(
    st.sampled_from(["fields", "labels", "default_page_size", "scope_dimensions"]),
    _override_values,
    max_size=3,
)


@st.composite
def overlays(draw, with_legacy):
    """Build an overlay dict, optionally carrying a top-level legacy ``overrides`` key."""
    overlay = dict(draw(_other_keys))
    # fixed_overrides present roughly half the time, independent of the legacy key.
    if draw(st.booleans()):
        overlay["fixed_overrides"] = draw(_override_maps)
    if with_legacy:
        overlay["overrides"] = draw(_override_maps)
    return overlay


# ---------------------------------------------------------------------------
# Property 2 — migration preserves data and is idempotent
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(overlay=st.one_of(overlays(with_legacy=True), overlays(with_legacy=False)))
def test_rename_overrides_key_merge_invariant_fixed_overrides_wins(overlay):
    """Merge invariant: every pre-existing entry survives; fixed_overrides wins on collision.

    Validates: Requirements 6.1, 6.2
    """
    legacy = overlay.get("overrides", {})
    pre_fixed = overlay.get("fixed_overrides", {})
    legacy = legacy if isinstance(legacy, dict) else {}
    pre_fixed = pre_fixed if isinstance(pre_fixed, dict) else {}

    result = rename_overrides_key(overlay)
    merged = result.get("fixed_overrides", {}) if isinstance(result, dict) else {}

    # Every key that was present (either side) is present in the merged result.
    expected_keys = set(legacy) | set(pre_fixed)
    assert set(merged) >= expected_keys

    # On a collision the pre-existing fixed_overrides entry WINS.
    for key in legacy:
        if key in pre_fixed:
            assert merged[key] == pre_fixed[key]
        else:
            assert merged[key] == legacy[key]
    # Keys only in fixed_overrides are preserved verbatim.
    for key in pre_fixed:
        assert merged[key] == pre_fixed[key]


@settings(max_examples=200)
@given(overlay=overlays(with_legacy=True))
def test_rename_overrides_key_other_keys_byte_for_byte_unchanged(overlay):
    """Non-override top-level keys are left exactly as-is (R6.3 / R8.1 / R8.3).

    Validates: Requirements 6.3, 8.1, 8.3
    """
    snapshot = {k: copy.deepcopy(v) for k, v in overlay.items() if k not in ("overrides", "fixed_overrides")}

    result = rename_overrides_key(overlay)

    for key, value in snapshot.items():
        assert key in result
        assert result[key] == value


@settings(max_examples=200)
@given(overlay=st.one_of(overlays(with_legacy=True), overlays(with_legacy=False)))
def test_rename_overrides_key_idempotent_and_drops_legacy_key(overlay):
    """f(f(x)) == f(x) and the result never carries a top-level 'overrides' key (R6.4).

    Validates: Requirements 6.4
    """
    once = rename_overrides_key(overlay)
    twice = rename_overrides_key(once)

    assert twice == once
    if isinstance(once, dict):
        assert "overrides" not in once


@settings(max_examples=200)
@given(overlay=st.one_of(overlays(with_legacy=True), overlays(with_legacy=False)))
def test_rename_overrides_key_values_copied_verbatim(overlay):
    """Override values are moved verbatim — content identical to the source (R6.1).

    Validates: Requirements 6.1, 8.1
    """
    legacy = overlay.get("overrides", {})
    legacy = legacy if isinstance(legacy, dict) else {}
    legacy_before = copy.deepcopy(legacy)

    result = rename_overrides_key(overlay)
    merged = result.get("fixed_overrides", {}) if isinstance(result, dict) else {}

    # Every legacy-only key keeps its exact value in the merged map.
    pre_fixed = overlay.get("fixed_overrides", {})
    pre_fixed = pre_fixed if isinstance(pre_fixed, dict) else {}
    for key, value in legacy_before.items():
        if key not in pre_fixed:
            assert merged[key] == value


# ---------------------------------------------------------------------------
# Example tests — specific merge / collision / idempotence cases
# ---------------------------------------------------------------------------

def test_rename_overrides_key_collision_prefers_fixed_overrides():
    """A key present in both maps resolves to the fixed_overrides value."""
    overlay = {
        "fields": ["name", "email"],
        "overrides": {"name": {"hidden": True}, "email": {"label": "legacy"}},
        "fixed_overrides": {"email": {"label": "canonical"}},
    }
    result = rename_overrides_key(overlay)

    assert "overrides" not in result
    assert result["fields"] == ["name", "email"]
    # Collision: canonical wins.
    assert result["fixed_overrides"]["email"] == {"label": "canonical"}
    # Legacy-only key moves in.
    assert result["fixed_overrides"]["name"] == {"hidden": True}


def test_rename_overrides_key_no_legacy_key_returns_unchanged():
    """An overlay without a top-level 'overrides' key is returned unchanged (no-op)."""
    overlay = {"fields": ["name"], "fixed_overrides": {"name": {"hidden": True}}}
    result = rename_overrides_key(overlay)

    assert result is overlay


def test_overlay_needs_rewrite_detects_only_top_level_legacy_key():
    """overlay_needs_rewrite is true iff a dict carries a top-level 'overrides' key."""
    assert overlay_needs_rewrite({"overrides": {}}) is True
    assert overlay_needs_rewrite({"fixed_overrides": {}}) is False
    assert overlay_needs_rewrite({"fields": ["a"]}) is False
    assert overlay_needs_rewrite("not a dict") is False
    assert overlay_needs_rewrite(None) is False


# ---------------------------------------------------------------------------
# Example tests — migrate() against mocked DB + ParameterService
# ---------------------------------------------------------------------------

_LEGACY_ROW = {
    "scope_id": "ExampleTenant",
    "value": json.dumps(
        {
            "fields": ["name", "email"],
            "overrides": {"name": {"hidden": True}, "email": {"label": "legacy"}},
            "fixed_overrides": {"email": {"label": "canonical"}},
        }
    ),
    "value_type": "json",
    "is_secret": False,
}


def _make_migrate_mocks(rows):
    """Build (mock_db, mock_param_service) wired for a migrate() run.

    The sweep issues exactly one SELECT against the parameters table; its result
    is the supplied ``rows``. No member table is ever queried.
    """
    mock_db = MagicMock()
    mock_db.execute_query.return_value = rows
    mock_param_service = MagicMock()
    return mock_db, mock_param_service


def test_migrate_dry_run_makes_no_write():
    """Dry-run (default) scans the row but performs NO ParameterService.set_param write.

    Validates: Requirements 6.4, 6.5, 8.1
    """
    mock_db, mock_param_service = _make_migrate_mocks([dict(_LEGACY_ROW)])

    with patch.object(mig, "DatabaseManager", return_value=mock_db), patch.object(
        mig, "ParameterService", return_value=mock_param_service
    ):
        summary = migrate(dry_run=True)

    # The legacy row is scanned and counted as a would-be rewrite...
    assert summary == {"scanned": 1, "rewritten": 1, "skipped": 0}
    # ...but NOTHING is written and nothing is committed.
    mock_param_service.set_param.assert_not_called()


def test_migrate_apply_run_performs_rename_with_merged_overlay():
    """The applied run writes the merged overlay via ParameterService.set_param.

    Validates: Requirements 6.1, 6.2, 6.3
    """
    mock_db, mock_param_service = _make_migrate_mocks([dict(_LEGACY_ROW)])

    with patch.object(mig, "DatabaseManager", return_value=mock_db), patch.object(
        mig, "ParameterService", return_value=mock_param_service
    ):
        summary = migrate(dry_run=False)

    assert summary == {"scanned": 1, "rewritten": 1, "skipped": 0}
    mock_param_service.set_param.assert_called_once()

    _, kwargs = mock_param_service.set_param.call_args
    assert kwargs["scope"] == "tenant"
    assert kwargs["scope_id"] == "ExampleTenant"
    assert kwargs["namespace"] == "members"
    assert kwargs["key"] == "field_overlay"
    assert kwargs["value_type"] == "json"
    assert kwargs["is_secret"] is False

    written = kwargs["value"]
    # The written overlay carries the merged fixed_overrides and no legacy key.
    assert "overrides" not in written
    assert written["fields"] == ["name", "email"]
    assert written["fixed_overrides"]["email"] == {"label": "canonical"}  # collision -> canonical
    assert written["fixed_overrides"]["name"] == {"hidden": True}  # legacy-only moved in


def test_migrate_only_queries_members_field_overlay_rows():
    """The sweep queries ONLY tenant members.field_overlay rows — never member records.

    Validates: Requirements 8.1, 8.3
    """
    mock_db, mock_param_service = _make_migrate_mocks([dict(_LEGACY_ROW)])

    with patch.object(mig, "DatabaseManager", return_value=mock_db), patch.object(
        mig, "ParameterService", return_value=mock_param_service
    ):
        migrate(dry_run=False)

    # Exactly one query is issued, against the parameters table, scoped to the
    # members.field_overlay tenant rows — no member table is touched.
    mock_db.execute_query.assert_called_once()
    sql, params = mock_db.execute_query.call_args[0][0], mock_db.execute_query.call_args[0][1]
    assert "FROM parameters" in sql
    assert params == ("tenant", "members", "field_overlay")
    assert "members.field_overlay" not in sql.lower() or "from parameters" in sql.lower()


def test_migrate_skips_row_without_legacy_key():
    """A row already using fixed_overrides is scanned, skipped, and never rewritten.

    Validates: Requirements 6.4, 8.1
    """
    clean_row = {
        "scope_id": "ExampleTenant",
        "value": json.dumps({"fields": ["name"], "fixed_overrides": {"name": {"hidden": True}}}),
        "value_type": "json",
        "is_secret": False,
    }
    mock_db, mock_param_service = _make_migrate_mocks([clean_row])

    with patch.object(mig, "DatabaseManager", return_value=mock_db), patch.object(
        mig, "ParameterService", return_value=mock_param_service
    ):
        summary = migrate(dry_run=False)

    assert summary == {"scanned": 1, "rewritten": 0, "skipped": 1}
    mock_param_service.set_param.assert_not_called()


def test_migrate_no_rows_is_noop():
    """With no field_overlay rows the migration is a clean no-op."""
    mock_db, mock_param_service = _make_migrate_mocks([])

    with patch.object(mig, "DatabaseManager", return_value=mock_db), patch.object(
        mig, "ParameterService", return_value=mock_param_service
    ):
        summary = migrate(dry_run=False)

    assert summary == {"scanned": 0, "rewritten": 0, "skipped": 0}
    mock_param_service.set_param.assert_not_called()
