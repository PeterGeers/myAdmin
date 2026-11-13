"""Direct unit tests for services/pivot_query_builder.py.

Covers configuration validation (limits, allowed aggregates, conflicting
column roles), tenant-only WHERE construction, and column metadata.

Reference: .kiro/specs/dynamic-pivot-views/design.md
"""

from unittest.mock import Mock

import pytest

from services.pivot_query_builder import (
    ALLOWED_AGG_FUNCTIONS,
    MAX_AGGREGATE_MEASURES,
    MAX_GROUP_COLUMNS,
    MAX_NEST_LEVELS,
    TENANT_COLUMN,
    PivotQueryBuilder,
)

TENANT = "test_admin"
DS = "members"
TYPES = {DS: {"region": "varchar", "team": "varchar", "amount": "decimal"}}


def _registry():
    reg = Mock()
    reg.get_available_columns.return_value = {
        "groupable": [{"name": "region"}, {"name": "team"}],
        "aggregatable": [{"name": "amount"}],
    }
    return reg


REG = _registry()
B = PivotQueryBuilder(REG, lambda: TYPES)


def _am(column="amount", function="SUM"):
    return [{"column": column, "function": function}]


class TestValidateConfig:
    def test_requires_group_and_measure(self):
        with pytest.raises(ValueError, match="At least one group column"):
            B.validate_config(DS, TENANT, [], _am(), None, [])

    def test_group_column_limit(self):
        too_many = ["c" + str(i) for i in range(MAX_GROUP_COLUMNS + 1)]
        with pytest.raises(ValueError, match="Maximum"):
            B.validate_config(DS, TENANT, too_many, _am(), None, [])

    def test_measure_limit(self):
        measures = _am() * (MAX_AGGREGATE_MEASURES + 1)
        with pytest.raises(ValueError, match="aggregate measures"):
            B.validate_config(DS, TENANT, ["region"], measures, None, [])

    def test_nest_level_limit(self):
        levels = ["n" + str(i) for i in range(MAX_NEST_LEVELS + 1)]
        with pytest.raises(ValueError, match="nest levels"):
            B.validate_config(DS, TENANT, ["region"], _am(), None, levels)

    def test_disallowed_function(self):
        with pytest.raises(ValueError, match="is not allowed"):
            B.validate_config(DS, TENANT, ["region"], _am(function="DROP"), None, [])

    def test_every_allowed_function_is_accepted(self):
        for func in ALLOWED_AGG_FUNCTIONS:
            B.validate_config(DS, TENANT, ["region"], _am(function=func), None, [])


class TestColumnRoles:
    def test_pivot_column_cannot_be_a_group_column(self):
        with pytest.raises(ValueError):
            B.validate_config(DS, TENANT, ["region"], _am(), "region", [])

    def test_pivot_column_cannot_be_a_nest_level(self):
        with pytest.raises(ValueError, match="nest level"):
            B.validate_config(DS, TENANT, ["team"], _am(), "region", ["region"])

    def test_group_column_cannot_be_a_nest_level(self):
        with pytest.raises(ValueError, match="row group and column nest"):
            B.validate_config(DS, TENANT, ["region"], _am(), None, ["region"])

    def test_registry_validation_is_delegated(self):
        B.validate_config(DS, TENANT, ["region"], _am(), None, ["team"])
        REG.validate_columns.assert_called_with(
            DS, TENANT, ["region"], ["amount"], None, ["team"]
        )


class TestWhereClause:
    def test_tenant_filter_always_comes_first(self):
        sql, params = B._build_where_clause(DS, {}, TENANT)
        assert TENANT_COLUMN in sql
        assert params == [TENANT]

    def test_unknown_filter_columns_are_ignored(self):
        sql, params = B._build_where_clause(DS, {"nope": "x"}, TENANT)
        assert "nope" not in sql
        assert params == [TENANT]

    def test_empty_filter_values_are_skipped(self):
        sql, params = B._build_where_clause(
            DS, {"region": "all", "team": "", "amount": None}, TENANT
        )
        assert params == [TENANT]
        assert "region" not in sql

    def test_like_and_in_filters(self):
        sql, params = B._build_where_clause(
            DS, {"region": ["A", "B"], "team": "Team%"}, TENANT
        )
        assert "IN (" in sql
        assert "LIKE %s" in sql
        assert params == [TENANT, "A", "B", "Team%"]


class TestColumnsMeta:
    def test_group_and_aggregate_columns(self):
        cols = B.build_columns_meta(DS, ["region"], _am(), None, [])
        assert [c["name"] for c in cols] == ["region", "SUM_amount"]
        assert cols[0]["type"] == "group"
        assert cols[1]["type"] == "aggregate"
        assert cols[1]["dataType"] == "decimal"

    def test_count_columns_are_typed_int(self):
        cols = B.build_columns_meta(DS, ["region"], _am(function="COUNT"), None, [])
        assert cols[1]["dataType"] == "int"

    def test_pivot_columns_carry_pivot_metadata(self):
        cols = B.build_columns_meta(
            DS, ["region"], _am(), "team", [], pivot_values=["A"]
        )
        pivot_col = [c for c in cols if c.get("pivotValue") == "A"][0]
        assert pivot_col["pivotColumn"] == "team"
        assert pivot_col["pivotGroup"] == "pivot"


class TestFetchPivotValues:
    def test_distinct_values_and_nest_combinations(self):
        db = Mock()
        db.execute_query.side_effect = [
            [{"team": "A"}, {"team": "B"}],
            [{"team": "A", "region": "N"}],
        ]
        values, combos = B.fetch_pivot_values(db, DS, "team", ["region"], {}, TENANT)
        assert values == ["A", "B"]
        assert combos == [("N",)]
