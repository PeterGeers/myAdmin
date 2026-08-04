"""
Pivot Query Builder — builds dynamic GROUP BY/pivot SQL queries.

Extracted from pivot_service.py for file-length compliance (<500 lines).
Contains all query construction, validation, and metadata logic used
by PivotService.execute_pivot().

Requirements: 2.4, 3.1–3.3, 9.1–9.11
Reference: .kiro/specs/dynamic-pivot-views/design.md
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants (shared with pivot_service.py)
# ---------------------------------------------------------------------------

ALLOWED_AGG_FUNCTIONS = {"SUM", "COUNT", "AVG", "MIN", "MAX"}

MAX_GROUP_COLUMNS = 5
MAX_AGGREGATE_MEASURES = 10
MAX_NEST_LEVELS = 5

# Tenant isolation column — same across all views in this application.
TENANT_COLUMN = "administration"


# ---------------------------------------------------------------------------
# Query Builder
# ---------------------------------------------------------------------------


class PivotQueryBuilder:
    """Builds dynamic pivot SQL queries with tenant isolation.

    Encapsulates all query construction, validation, and column metadata
    logic. Used by PivotService as a delegate for query building.
    """

    COLUMN_QUOTE = "`"

    def __init__(self, registry, column_type_map_getter):
        """
        Args:
            registry: AllowedColumnsRegistry instance for column validation.
            column_type_map_getter: callable returning COLUMN_TYPE_MAP dict.
        """
        self.registry = registry
        self._get_column_type_map = column_type_map_getter

    # -- Public API --------------------------------------------------------

    def build_pivot_query(
        self, config: dict[str, Any], tenant: str
    ) -> tuple[str, list]:
        """Build the main pivot GROUP BY query.

        Returns:
            (sql_query, params) tuple ready for execute_query.
        """
        ds = config.get("data_source", "")
        gc = config.get("group_columns", [])
        am = config.get("aggregate_measures", [])
        filters = config.get("filters", {})
        cp = config.get("column_pivot")
        rollup = config.get("include_rollup", False)

        q = self._quote_col
        select_parts, params = [], []

        for col in gc:
            select_parts.append(q(col))

        if cp:
            ps, pp = self._build_pivot_select(config, am)
            select_parts.extend(ps)
            params.extend(pp)
        else:
            for m in am:
                func, col = m["function"].upper(), m["column"]
                alias = self._agg_alias(func, col)
                select_parts.append(
                    f"{func}(*) AS {q(alias)}"
                    if col == "*"
                    else f"{func}({q(col)}) AS {q(alias)}"
                )

        where_clause, wp = self._build_where_clause(ds, filters, tenant)
        # SELECT params (pivot CASE WHEN) come before WHERE params in the SQL
        params = params + wp

        group_by = ", ".join(q(c) for c in gc)
        if rollup:
            group_by += " WITH ROLLUP"

        query = f"SELECT {', '.join(select_parts)} FROM {q(ds)} WHERE {where_clause} GROUP BY {group_by}"
        return query, params

    def build_underlying_query(
        self, config: dict[str, Any], tenant: str
    ) -> tuple[str, list]:
        """Build a non-aggregated SELECT query for the underlying data.

        Returns:
            (sql_query, params) tuple with only allowed columns selected.
        """
        ds = config.get("data_source", "")
        filters = config.get("filters", {})
        q = self._quote_col
        where_clause, params = self._build_where_clause(ds, filters, tenant)

        # Select only allowed columns (groupable + aggregatable) instead of
        # SELECT * — this excludes noisy/sensitive columns like addInfo,
        # guestName, phone, sourceFile that are in the exclude list.
        allowed = self.registry.get_available_columns(ds, tenant)
        col_names = [c["name"] for c in allowed["groupable"]] + [
            c["name"] for c in allowed["aggregatable"]
        ]
        if not col_names:
            raise ValueError(f"No allowed columns for data source '{ds}'")

        select_clause = ", ".join(q(c) for c in col_names)
        return f"SELECT {select_clause} FROM {q(ds)} WHERE {where_clause}", params

    def validate_config(
        self,
        ds: str,
        tenant: str,
        gc: list[str],
        am: list[dict[str, str]],
        cp: str | None,
        cnl: list[str],
    ) -> None:
        """Validate pivot configuration constraints and column access."""
        if not gc or not am:
            raise ValueError(
                "At least one group column and one aggregate measure are required"
            )
        if len(gc) > MAX_GROUP_COLUMNS:
            raise ValueError(f"Maximum {MAX_GROUP_COLUMNS} group columns allowed")
        if len(am) > MAX_AGGREGATE_MEASURES:
            raise ValueError(
                f"Maximum {MAX_AGGREGATE_MEASURES} aggregate measures allowed"
            )
        if len(cnl) > MAX_NEST_LEVELS:
            raise ValueError(f"Maximum {MAX_NEST_LEVELS} column nest levels allowed")
        for m in am:
            func = m.get("function", "").upper()
            if func not in ALLOWED_AGG_FUNCTIONS:
                raise ValueError(
                    f"Aggregation function '{func}' is not allowed. "
                    f"Allowed: {', '.join(sorted(ALLOWED_AGG_FUNCTIONS))}"
                )
        self._validate_column_roles(gc, cp, cnl)
        self.registry.validate_columns(
            ds, tenant, gc, [m["column"] for m in am], cp, cnl
        )

    def build_columns_meta(
        self, ds, gc, am, cp, cnl, pivot_values=None, nest_combinations=None
    ):
        """Build column metadata for the pivot result.

        When ``cp`` (column_pivot) is set, returns pivoted column metadata
        with ``pivotValue``, ``nestValues``, and ``pivotGroup`` fields so
        the frontend can render multi-row ``<thead>`` headers.
        """
        tm = self._get_column_type_map().get(ds, {})
        cols = []

        # Group columns (row axis)
        for col in gc:
            cols.append(
                {"name": col, "type": "group", "dataType": tm.get(col, "varchar")}
            )

        if cp and pivot_values:
            # Pivoted aggregate columns
            for pv in pivot_values:
                if cnl and nest_combinations:
                    for combo in nest_combinations:
                        for m in am:
                            func = m["function"].upper()
                            col = m["column"]
                            nl = "_".join(str(v) for v in combo)
                            alias = f"{pv}_{nl}_{func}_{col}"
                            dt = (
                                "int"
                                if func == "COUNT"
                                else (tm.get(col, "decimal") if col != "*" else "int")
                            )
                            nest_vals = {cnl[i]: combo[i] for i in range(len(cnl))}
                            cols.append(
                                {
                                    "name": alias,
                                    "type": "aggregate",
                                    "function": func,
                                    "sourceColumn": col,
                                    "dataType": dt,
                                    "pivotValue": pv,
                                    "pivotColumn": cp,
                                    "nestValues": nest_vals,
                                    "pivotGroup": "pivot",
                                }
                            )
                else:
                    for m in am:
                        func = m["function"].upper()
                        col = m["column"]
                        alias = f"{pv}_{func}_{col}"
                        dt = (
                            "int"
                            if func == "COUNT"
                            else (tm.get(col, "decimal") if col != "*" else "int")
                        )
                        cols.append(
                            {
                                "name": alias,
                                "type": "aggregate",
                                "function": func,
                                "sourceColumn": col,
                                "dataType": dt,
                                "pivotValue": pv,
                                "pivotColumn": cp,
                                "pivotGroup": "pivot",
                            }
                        )

            # Grand total columns — one per measure
            for m in am:
                func = m["function"].upper()
                col = m["column"]
                alias = f"TOTAL_{func}_{col}"
                dt = (
                    "int"
                    if func == "COUNT"
                    else (tm.get(col, "decimal") if col != "*" else "int")
                )
                cols.append(
                    {
                        "name": alias,
                        "type": "aggregate",
                        "function": func,
                        "sourceColumn": col,
                        "dataType": dt,
                        "pivotGroup": "total",
                    }
                )
        else:
            # Non-pivoted: simple aggregate columns
            for m in am:
                func = m["function"].upper()
                col = m["column"]
                alias = self._agg_alias(func, col)
                dt = (
                    "int"
                    if func == "COUNT"
                    else (tm.get(col, "decimal") if col != "*" else "int")
                )
                cols.append(
                    {
                        "name": alias,
                        "type": "aggregate",
                        "function": func,
                        "sourceColumn": col,
                        "dataType": dt,
                    }
                )

        return cols

    def fetch_pivot_values(
        self, db, data_source, column_pivot, nest_levels, filters, tenant
    ):
        """Fetch distinct values for the pivot column (and nest level combinations).

        Runs a lightweight SELECT DISTINCT query against the data source,
        applying the same tenant isolation and user filters as the main query.

        Returns:
            (pivot_values, nest_combinations) where pivot_values is a sorted
            list of distinct values for column_pivot, and nest_combinations
            is a sorted list of tuples of distinct value combinations for
            the nest levels (empty list when no nest levels).
        """
        q = self._quote_col
        where_clause, params = self._build_where_clause(data_source, filters, tenant)

        # Fetch distinct pivot values
        pv_query = (
            f"SELECT DISTINCT {q(column_pivot)} FROM {q(data_source)} "
            f"WHERE {where_clause} ORDER BY {q(column_pivot)}"
        )
        pv_rows = db.execute_query(pv_query, params, fetch=True) or []
        pivot_values = [
            row[column_pivot] for row in pv_rows if row.get(column_pivot) is not None
        ]

        # Fetch distinct nest level combinations
        nest_combinations = []
        if nest_levels:
            nl_cols = ", ".join(q(c) for c in nest_levels)
            nl_query = (
                f"SELECT DISTINCT {nl_cols} FROM {q(data_source)} "
                f"WHERE {where_clause} ORDER BY {nl_cols}"
            )
            nl_rows = db.execute_query(nl_query, list(params), fetch=True) or []
            nest_combinations = [
                tuple(row[c] for c in nest_levels)
                for row in nl_rows
                if all(row.get(c) is not None for c in nest_levels)
            ]

        return pivot_values, nest_combinations

    # -- Internal: validation ----------------------------------------------

    @staticmethod
    def _validate_column_roles(gc: list[str], cp: str | None, cnl: list[str]) -> None:
        """Ensure no column is used in conflicting roles."""
        gs, ns = set(gc), set(cnl)
        if cp:
            if cp in gs:
                raise ValueError(
                    f"Column '{cp}' cannot be used as both row group and column pivot"
                )
            if cp in ns:
                raise ValueError(
                    f"Column '{cp}' cannot be used as both column pivot "
                    f"and column nest level"
                )
        overlap = gs & ns
        if overlap:
            raise ValueError(
                f"Column '{next(iter(overlap))}' cannot be used as both "
                f"row group and column nest level"
            )

    # -- Internal: WHERE clause --------------------------------------------

    def _build_where_clause(
        self, data_source: str, filters: dict[str, Any], tenant: str
    ) -> tuple[str, list]:
        """Build WHERE clause filtering by the CURRENT tenant only."""
        parts, params = [], []
        # Filter by current tenant only
        parts.append(f"{self._quote_col(TENANT_COLUMN)} = %s")
        params.append(tenant)

        column_type_map = self._get_column_type_map()
        known = set(column_type_map.get(data_source, {}).keys())
        for col, val in filters.items():
            if val is None or val == "" or val == "all" or col not in known:
                continue
            if isinstance(val, list) and val:
                # Check if any list item contains a wildcard
                like_items = [v for v in val if isinstance(v, str) and "%" in v]
                exact_items = [v for v in val if v not in like_items]
                sub_parts = []
                if exact_items:
                    ph = ", ".join(["%s"] * len(exact_items))
                    sub_parts.append(f"{self._quote_col(col)} IN ({ph})")
                    params.extend(exact_items)
                for lv in like_items:
                    sub_parts.append(f"{self._quote_col(col)} LIKE %s")
                    params.append(lv)
                if sub_parts:
                    parts.append(f"({' OR '.join(sub_parts)})")
            elif isinstance(val, str) and "%" in val:
                parts.append(f"{self._quote_col(col)} LIKE %s")
                params.append(val)
            else:
                parts.append(f"{self._quote_col(col)} = %s")
                params.append(val)

        return " AND ".join(parts) if parts else "1=1", params

    # -- Internal: pivot SELECT clause -------------------------------------

    def _build_pivot_select(self, config, am):
        """Build CASE WHEN expressions for column pivoting."""
        cp = config.get("column_pivot", "")
        pvs = config.get("pivot_values", [])
        cnl = config.get("column_nest_levels", [])
        q = self._quote_col
        parts, params = [], []

        if not pvs:
            for m in am:
                func, col = m["function"].upper(), m["column"]
                alias = self._agg_alias(func, col)
                parts.append(
                    f"{func}(*) AS {q(alias)}"
                    if col == "*"
                    else f"{func}({q(col)}) AS {q(alias)}"
                )
            return parts, params

        for pv in pvs:
            if cnl:
                combos = config.get("nest_combinations", [])
                if combos:
                    for combo in combos:
                        for m in am:
                            func, col = m["function"].upper(), m["column"]
                            nl = "_".join(str(v) for v in combo)
                            alias = f"{pv}_{nl}_{func}_{col}"
                            conds = [f"{q(cp)} = %s"]
                            cp_params = [pv]
                            for i, lc in enumerate(cnl):
                                conds.append(f"{q(lc)} = %s")
                                cp_params.append(combo[i])
                            then = "1" if col == "*" else q(col)
                            parts.append(
                                f"{func}(CASE WHEN {' AND '.join(conds)} "
                                f"THEN {then} ELSE 0 END) AS {q(alias)}"
                            )
                            params.extend(cp_params)
                else:
                    for m in am:
                        func, col = m["function"].upper(), m["column"]
                        alias = f"{pv}_{func}_{col}"
                        then = "1" if col == "*" else q(col)
                        parts.append(
                            f"{func}(CASE WHEN {q(cp)} = %s "
                            f"THEN {then} ELSE 0 END) AS {q(alias)}"
                        )
                        params.append(pv)
            else:
                for m in am:
                    func, col = m["function"].upper(), m["column"]
                    alias = f"{pv}_{func}_{col}"
                    then = "1" if col == "*" else q(col)
                    parts.append(
                        f"{func}(CASE WHEN {q(cp)} = %s "
                        f"THEN {then} ELSE 0 END) AS {q(alias)}"
                    )
                    params.append(pv)

        for m in am:
            func, col = m["function"].upper(), m["column"]
            alias = f"TOTAL_{func}_{col}"
            parts.append(
                f"{func}(*) AS {q(alias)}"
                if col == "*"
                else f"{func}({q(col)}) AS {q(alias)}"
            )

        return parts, params

    # -- Internal: helpers -------------------------------------------------

    def _quote_col(self, name):
        """Quote a column name for safe use in SQL."""
        from services.pivot_service import AllowedColumnsRegistry

        return AllowedColumnsRegistry._quote_column(name, self.COLUMN_QUOTE)

    @staticmethod
    def _agg_alias(func, col):
        """Generate an alias for an aggregate expression."""
        return func if col == "*" else f"{func}_{col}"
