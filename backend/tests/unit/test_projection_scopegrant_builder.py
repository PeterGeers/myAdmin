"""Direct unit tests for services/_projection_scopegrant.py.

Covers the per-user ``scopegrant#<email>#<dimension>`` projection builder:
- tenant partition-key guard (blank tenant is a cross-tenant hazard)
- deny-by-default (no dimensions / disabled dimension / unknown values)
- wildcard grant projection
- canonicalized value matching emitted in declared order
- malformed row tolerance (never raises)
- per-row freshness version (ODx4a) and tenant fallback
- deterministic ordering and sort-key shape

Reference: .kiro/specs/code-quality-maintenance/code-quality-fixes/
"""

import json
from datetime import datetime
from unittest.mock import Mock

import pytest

from services._projection_config_builders import (
    _SCOPE_DIMENSIONS_PARAM_KEY,
)
from services._projection_scopegrant import (
    WILDCARD_VALUE,
    _parse_scopes,
    _scopegrant_version,
    build_scopegrant_rows,
)

TENANT = "test_admin"
USER_EMAIL = "user" + "@" + "test.local"
TENANT_UPDATED_AT = datetime(2026, 1, 1, 12, 0, 0)
TENANT_ROW = {"administration": TENANT, "updated_at": TENANT_UPDATED_AT}

DIMENSIONS = [
    {"key": "region", "enabled": True, "values": ["Noord Holland", "Zuid Holland"]},
    {"key": "team", "enabled": True, "values": ["Team A", "Team B"]},
]


def _param_service(dimensions=None):
    """ParameterService stub returning the given scope-dimension definitions."""
    dimensions = DIMENSIONS if dimensions is None else dimensions
    svc = Mock()

    def _get_param(namespace, key, tenant=None):
        if key == _SCOPE_DIMENSIONS_PARAM_KEY:
            return dimensions
        return None

    svc.get_param.side_effect = _get_param
    return svc


def _scope_row(email=USER_EMAIL, scopes=None, module="MEMBERS", **extra):
    row = {
        "email": email,
        "module": module,
        "scopes": json.dumps(scopes if scopes is not None else {}),
    }
    row.update(extra)
    return row


class TestTenantGuard:
    """A blank partition key must never produce projection rows."""

    def test_missing_administration_raises(self):
        with pytest.raises(ValueError, match="cross-tenant hazard"):
            build_scopegrant_rows({}, [], _param_service())

    def test_tenant_id_key_is_accepted_as_partition_key(self):
        items = build_scopegrant_rows(
            {"tenant_id": TENANT},
            [_scope_row(scopes={"region": ["Noord Holland"]})],
            _param_service(),
        )
        assert [item.tenant_id for item in items] == [TENANT]


class TestDenyByDefault:
    """Absent/disabled/unknown grants produce no rows."""

    def test_no_dimensions_configured_returns_empty(self):
        assert (
            build_scopegrant_rows(TENANT_ROW, [_scope_row()], _param_service([])) == []
        )

    def test_disabled_dimension_yields_no_rows(self):
        dimensions = [{"key": "region", "enabled": False, "values": ["Noord Holland"]}]
        items = build_scopegrant_rows(
            TENANT_ROW,
            [_scope_row(scopes={"region": ["Noord Holland"]})],
            _param_service(dimensions),
        )
        assert items == []

    def test_unknown_granted_value_is_dropped(self):
        items = build_scopegrant_rows(
            TENANT_ROW,
            [_scope_row(scopes={"region": ["Atlantis"]})],
            _param_service(),
        )
        assert items == []

    def test_non_list_grant_is_ignored(self):
        items = build_scopegrant_rows(
            TENANT_ROW,
            [_scope_row(scopes={"region": "Noord Holland"})],
            _param_service(),
        )
        assert items == []


class TestGrantProjection:
    """Granted values are validated, canonicalized, and projected."""

    def test_wildcard_grant_projects_wildcard(self):
        items = build_scopegrant_rows(
            TENANT_ROW,
            [_scope_row(scopes={"region": [WILDCARD_VALUE]})],
            _param_service(),
        )
        assert len(items) == 1
        assert items[0].attributes["dimension"] == "region"
        assert items[0].attributes["values"] == [WILDCARD_VALUE]

    def test_values_are_canonicalized_and_emitted_in_declared_order(self):
        items = build_scopegrant_rows(
            TENANT_ROW,
            [_scope_row(scopes={"region": ["zuid-holland", "Noord  Holland"]})],
            _param_service(),
        )
        assert len(items) == 1
        assert items[0].attributes["values"] == ["Noord Holland", "Zuid Holland"]

    def test_duplicate_granted_values_are_de_duplicated(self):
        items = build_scopegrant_rows(
            TENANT_ROW,
            [_scope_row(scopes={"region": ["Noord Holland", "noord holland"]})],
            _param_service(),
        )
        assert items[0].attributes["values"] == ["Noord Holland"]

    def test_sort_key_carries_email_and_dimension(self):
        items = build_scopegrant_rows(
            TENANT_ROW,
            [_scope_row(scopes={"region": ["Noord Holland"]})],
            _param_service(),
        )
        assert items[0].sort_key == "scopegrant#" + USER_EMAIL + "#region"

    def test_only_configured_dimensions_project(self):
        items = build_scopegrant_rows(
            TENANT_ROW,
            [_scope_row(scopes={"region": ["Noord Holland"], "unknown": ["X"]})],
            _param_service(),
        )
        assert [i.attributes["dimension"] for i in items] == ["region"]

    def test_multiple_users_are_ordered_by_email(self):
        rows = [
            _scope_row(
                email="z" + "@" + "test.local", scopes={"region": ["Noord Holland"]}
            ),
            _scope_row(
                email="a" + "@" + "test.local", scopes={"region": ["Noord Holland"]}
            ),
        ]
        items = build_scopegrant_rows(TENANT_ROW, rows, _param_service())
        assert [i.sort_key for i in items] == [
            "scopegrant#a" + "@" + "test.local#region",
            "scopegrant#z" + "@" + "test.local#region",
        ]


class TestMalformedRows:
    """A malformed source row is skipped, never raised on."""

    def test_non_members_module_row_is_skipped(self):
        items = build_scopegrant_rows(
            TENANT_ROW,
            [_scope_row(module="EVENTS", scopes={"region": ["Noord Holland"]})],
            _param_service(),
        )
        assert items == []

    def test_malformed_scopes_json_is_skipped(self):
        row = {"email": USER_EMAIL, "module": "MEMBERS", "scopes": "{not json"}
        assert build_scopegrant_rows(TENANT_ROW, [row], _param_service()) == []

    def test_row_without_email_is_skipped(self):
        row = {"module": "MEMBERS", "scopes": json.dumps({"region": ["Noord Holland"]})}
        assert build_scopegrant_rows(TENANT_ROW, [row], _param_service()) == []

    def test_non_mapping_row_is_skipped(self):
        assert build_scopegrant_rows(TENANT_ROW, ["oops"], _param_service()) == []

    def test_empty_source_sequence_returns_empty(self):
        assert build_scopegrant_rows(TENANT_ROW, None, _param_service()) == []


class TestFreshnessVersion:
    """Per-row updated_at drives the emitted version (ODx4a)."""

    def test_row_updated_at_supersedes_tenant_version(self):
        newer = datetime(2026, 3, 4, 5, 6, 7)
        row = _scope_row(scopes={"region": ["Noord Holland"]}, updated_at=newer)
        items = build_scopegrant_rows(TENANT_ROW, [row], _param_service())
        assert items[0].version == newer.isoformat()
        assert items[0].version != TENANT_UPDATED_AT.isoformat()

    def test_row_without_version_fields_falls_back_to_tenant(self):
        items = build_scopegrant_rows(
            TENANT_ROW,
            [_scope_row(scopes={"region": ["Noord Holland"]})],
            _param_service(),
        )
        assert items[0].version == TENANT_UPDATED_AT.isoformat()

    def test_all_dimension_rows_for_a_user_share_one_version(self):
        row = _scope_row(
            scopes={"region": ["Noord Holland"], "team": ["Team A"]},
            version=9,
        )
        items = build_scopegrant_rows(TENANT_ROW, [row], _param_service())
        assert len(items) == 2
        assert {i.version for i in items} == {9}

    def test_version_field_priority(self):
        row = {"updated_at": 3, "version": 2, "revision": 1}
        assert _scopegrant_version(row, 0) == 3
        assert _scopegrant_version({"revision": 1}, 0) == 1
        assert _scopegrant_version({}, 7) == 7


class TestParseScopes:
    """The scopes column may arrive as JSON text or an already-parsed mapping."""

    def test_mapping_passes_through(self):
        value = {"region": ["Noord Holland"]}
        assert _parse_scopes(value) == value

    def test_json_text_is_parsed(self):
        assert _parse_scopes(json.dumps({"region": ["A"]})) == {"region": ["A"]}

    def test_invalid_json_returns_none(self):
        assert _parse_scopes("{not json") is None

    def test_non_mapping_json_returns_none(self):
        assert _parse_scopes(json.dumps(["A"])) is None

    def test_none_returns_none(self):
        assert _parse_scopes(None) is None
