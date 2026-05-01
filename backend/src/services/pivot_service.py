"""
Pivot Service — AllowedColumnsRegistry and PivotService query builder.

AllowedColumnsRegistry manages two-tier column access control
(system max + tenant restrictions).

PivotService constructs and executes dynamic GROUP BY queries with
tenant isolation, column validation, and optional column pivoting
via conditional aggregation.

**Zero hardcoded column definitions.** Everything is derived at startup:
  - Column names and types: introspected via ``dialect.describe_table(<view>)``
  - Excluded columns:       parameter ``ui.pivot / exclude_columns.<ds>``
  - Force-groupable cols:   parameter ``ui.pivot / force_groupable.<ds>``
  - Allowed columns:        parameter ``ui.pivot / allowed_columns.<ds>``
  - Data source labels:     parameter ``ui.pivot / datasource_label.<ds>``
  - Registered sources:     parameter ``ui.pivot / registered_sources``

The only constant in code is the tenant isolation column (``administration``)
which is the same across all views in this application.

Requirements: 1.5–1.8, 2.4, 3.1–3.3, 3.9, 6.1–6.6, 7.4, 9.1–9.11
Reference: .kiro/specs/dynamic-pivot-views/design.md
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from dialect_helpers import dialect

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_AGG_FUNCTIONS = {'SUM', 'COUNT', 'AVG', 'MIN', 'MAX'}

MAX_GROUP_COLUMNS = 5
MAX_AGGREGATE_MEASURES = 10
MAX_NEST_LEVELS = 5

# Tenant isolation column — same across all views in this application.
TENANT_COLUMN = 'administration'

# SQL types that are treated as numeric (→ aggregatable by default).
_NUMERIC_TYPE_PATTERN = re.compile(
    r'^(int|integer|tinyint|smallint|mediumint|bigint'
    r'|decimal|numeric|float|double|real)',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Schema introspection helpers
# ---------------------------------------------------------------------------

def _normalise_sql_type(raw_type: str) -> str:
    """Normalise a MySQL type string to a simple category."""
    base = raw_type.split('(')[0].strip().lower()
    if base in ('decimal', 'numeric', 'float', 'double', 'real'):
        return 'decimal'
    if base in ('int', 'integer', 'tinyint', 'smallint', 'mediumint', 'bigint'):
        return 'int'
    if base in ('date', 'datetime', 'timestamp'):
        return 'date'
    return 'varchar'


def _is_numeric_type(raw_type: str) -> bool:
    """Return True if the SQL type is numeric."""
    return bool(_NUMERIC_TYPE_PATTERN.match(raw_type.strip()))


def derive_columns_from_schema(
    db,
    data_source: str,
    exclude_columns: set,
    force_groupable: set,
) -> Tuple[List[str], List[str], Dict[str, str]]:
    """
    Introspect a view/table via ``DESCRIBE`` and classify columns.

    Args:
        db: DatabaseManager instance.
        data_source: view or table name.
        exclude_columns: column names to skip entirely.
        force_groupable: numeric column names to classify as groupable.

    Returns:
        ``(groupable, aggregatable, type_map)``
    """
    rows = db.execute_query(dialect.describe_table(data_source), fetch=True)

    groupable: List[str] = []
    aggregatable: List[str] = []
    type_map: Dict[str, str] = {}

    for row in rows:
        col_name = row['Field']
        raw_type = row['Type']

        # MySQL connector may return bytes instead of str in some environments
        if isinstance(col_name, bytes):
            col_name = col_name.decode('utf-8')
        if isinstance(raw_type, bytes):
            raw_type = raw_type.decode('utf-8')

        if col_name in exclude_columns:
            continue

        # Tenant isolation column is always filtered automatically — never expose it
        if col_name == TENANT_COLUMN:
            continue

        simple_type = _normalise_sql_type(raw_type)
        type_map[col_name] = simple_type

        if col_name in force_groupable:
            groupable.append(col_name)
        elif _is_numeric_type(raw_type):
            aggregatable.append(col_name)
        else:
            groupable.append(col_name)

    return groupable, aggregatable, type_map


# ---------------------------------------------------------------------------
# Registry initialisation
# ---------------------------------------------------------------------------

def _get_param_list(parameter_service, key: str) -> list:
    """Read a list parameter from ui.pivot namespace, or return []."""
    if parameter_service is None:
        return []
    try:
        val = parameter_service.get_param(namespace='ui.pivot', key=key)
        if val and isinstance(val, list):
            return val
    except Exception:
        pass
    return []


def _get_param_str(parameter_service, key: str) -> Optional[str]:
    """Read a string parameter from ui.pivot namespace, or return None."""
    if parameter_service is None:
        return None
    try:
        val = parameter_service.get_param(namespace='ui.pivot', key=key)
        if val and isinstance(val, str):
            return val
    except Exception:
        pass
    return None


def build_registry_from_db(db, parameter_service=None) -> None:
    """
    Populate the module-level lookup dicts by introspecting the database.

    Called at application startup (e.g. in ``app.py``).  If the database
    is unreachable or a view is missing this will raise — but the
    registry can be lazily initialised on first request via
    :func:`ensure_registry`.

    The list of data sources to register is read from the parameter
    ``ui.pivot / registered_sources`` (a JSON list of view/table names).
    Defaults to ``['vw_mutaties', 'vw_bnb_total']`` via CODE_DEFAULTS.

    For each data source, reads from ``ui.pivot``:
      - ``exclude_columns.<ds>``   → columns to hide
      - ``force_groupable.<ds>``   → numeric columns to treat as groupable
      - ``datasource_label.<ds>``  → human-readable label

    Raises:
        RuntimeError: if any data source cannot be introspected.
    """
    global SYSTEM_ALLOWED_COLUMNS, COLUMN_TYPE_MAP, DATA_SOURCE_LABELS, DATA_SOURCE_MODULES
    global _registry_initialised

    # Which views/tables to register
    sources = _get_param_list(parameter_service, 'registered_sources')
    if not sources:
        sources = ['vw_mutaties', 'vw_bnb_total']

    for ds_name in sources:
        exclude = set(_get_param_list(parameter_service, f'exclude_columns.{ds_name}'))
        force_g = set(_get_param_list(parameter_service, f'force_groupable.{ds_name}'))
        label = _get_param_str(parameter_service, f'datasource_label.{ds_name}') or ds_name
        module = _get_param_str(parameter_service, f'datasource_module.{ds_name}')

        try:
            groupable, aggregatable, col_types = derive_columns_from_schema(
                db, ds_name, exclude, force_g,
            )
        except Exception as exc:
            msg = (
                f"FATAL: Cannot introspect schema for pivot data source "
                f"'{ds_name}': {exc}"
            )
            logger.critical(msg)
            raise RuntimeError(msg) from exc

        SYSTEM_ALLOWED_COLUMNS[ds_name] = {
            'groupable': groupable,
            'aggregatable': aggregatable,
        }
        COLUMN_TYPE_MAP[ds_name] = col_types
        DATA_SOURCE_LABELS[ds_name] = label
        DATA_SOURCE_MODULES[ds_name] = module

    _registry_initialised = True
    logger.info(
        "Pivot registry initialised from DB for %d data source(s): %s",
        len(sources), ', '.join(sources),
    )


def ensure_registry(db=None, parameter_service=None) -> None:
    """Lazily initialise the pivot registry if startup init failed.

    Safe to call on every request — returns immediately when the
    registry is already populated.  When *db* or *parameter_service*
    are ``None`` the function creates throwaway instances using the
    current ``TEST_MODE`` environment variable.
    """
    global _registry_initialised
    if _registry_initialised:
        return

    import os
    from database import DatabaseManager
    from services.parameter_service import ParameterService

    if db is None:
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
    if parameter_service is None:
        parameter_service = ParameterService(db)

    build_registry_from_db(db, parameter_service)
    logger.info("Pivot registry lazily initialised on first request")


# ---------------------------------------------------------------------------
# Module-level dicts — populated by build_registry_from_db() at startup.
# ---------------------------------------------------------------------------

SYSTEM_ALLOWED_COLUMNS: Dict[str, Dict[str, List[str]]] = {}
COLUMN_TYPE_MAP: Dict[str, Dict[str, str]] = {}
DATA_SOURCE_LABELS: Dict[str, str] = {}
DATA_SOURCE_MODULES: Dict[str, Optional[str]] = {}
_registry_initialised: bool = False


# ===================================================================
# AllowedColumnsRegistry
# ===================================================================

class AllowedColumnsRegistry:
    """
    Two-tier column access control for pivot views.

    System-level columns come from schema introspection at startup.
    Tenant-level restrictions come from the parameters table
    (``ui.pivot / allowed_columns.<data_source>``).
    """

    def __init__(self, parameter_service):
        self.parameter_service = parameter_service

    def get_available_columns(self, data_source: str, tenant: str) -> Dict[str, list]:
        ensure_registry()
        system_cols = SYSTEM_ALLOWED_COLUMNS.get(data_source)
        if system_cols is None:
            raise ValueError(f"Unknown data source '{data_source}'")

        type_map = COLUMN_TYPE_MAP.get(data_source, {})

        def _col_obj(name: str) -> dict:
            return {'name': name, 'type': type_map.get(name, 'varchar'), 'label': name}

        tenant_restriction = self._get_tenant_restriction(data_source, tenant)
        if tenant_restriction is None:
            return {
                'groupable': [_col_obj(c) for c in system_cols['groupable']],
                'aggregatable': [_col_obj(c) for c in system_cols['aggregatable']],
            }
        return {
            'groupable': [_col_obj(c) for c in system_cols['groupable']
                          if c in tenant_restriction.get('groupable', [])],
            'aggregatable': [_col_obj(c) for c in system_cols['aggregatable']
                             if c in tenant_restriction.get('aggregatable', [])],
        }

    def get_registered_sources(self) -> List[Dict[str, Any]]:
        ensure_registry()
        return [
            {
                'name': name,
                'label': DATA_SOURCE_LABELS.get(name, name),
                'module': DATA_SOURCE_MODULES.get(name),
            }
            for name in SYSTEM_ALLOWED_COLUMNS
        ]

    def validate_columns(self, data_source, tenant, group_columns,
                         aggregate_columns, column_pivot=None,
                         column_nest_levels=None):
        allowed = self.get_available_columns(data_source, tenant)
        allowed_g = set(c['name'] if isinstance(c, dict) else c for c in allowed['groupable'])
        allowed_a = set(c['name'] if isinstance(c, dict) else c for c in allowed['aggregatable'])

        for col in group_columns:
            if col not in allowed_g:
                raise ValueError(f"Column '{col}' is not allowed for data source '{data_source}'")
        for col in aggregate_columns:
            if col != '*' and col not in allowed_a:
                raise ValueError(f"Column '{col}' is not allowed for data source '{data_source}'")
        if column_pivot and column_pivot not in allowed_g:
            raise ValueError(f"Column '{column_pivot}' is not allowed for data source '{data_source}'")
        for col in (column_nest_levels or []):
            if col not in allowed_g:
                raise ValueError(f"Column '{col}' is not allowed for data source '{data_source}'")

    @staticmethod
    def _quote_column(name: str, quote_char: str = '`') -> str:
        sanitised = name.replace(quote_char, '')
        return f'{quote_char}{sanitised}{quote_char}'

    def _get_tenant_restriction(self, data_source, tenant):
        try:
            value = self.parameter_service.get_param(
                namespace='ui.pivot', key=f'allowed_columns.{data_source}', tenant=tenant)
            if value and isinstance(value, dict):
                return value
        except Exception:
            logger.warning("Failed to read tenant column restriction for %s / %s", data_source, tenant)
        return None


# ===================================================================
# PivotService
# ===================================================================

class PivotService:
    """Builds and executes dynamic pivot queries with tenant isolation."""

    COLUMN_QUOTE = '`'

    def __init__(self, db, parameter_service):
        self.db = db
        self.parameter_service = parameter_service
        self.registry = AllowedColumnsRegistry(parameter_service)

    def get_available_columns(self, data_source, tenant):
        return self.registry.get_available_columns(data_source, tenant)

    def get_registered_sources(self):
        return self.registry.get_registered_sources()

    def execute_pivot(self, tenant, user_tenants, config):
        ds = config.get('data_source', '')
        gc = config.get('group_columns', [])
        am = config.get('aggregate_measures', [])
        cp = config.get('column_pivot')
        cnl = config.get('column_nest_levels', [])

        self._validate_config(ds, tenant, gc, am, cp, cnl)

        # Auto-fetch distinct pivot values when column_pivot is set
        # but pivot_values are not provided by the caller.
        pivot_values = config.get('pivot_values', [])
        nest_combinations = config.get('nest_combinations', [])
        if cp and not pivot_values:
            pivot_values, nest_combinations = self._fetch_pivot_values(
                ds, cp, cnl, config.get('filters', {}), tenant,
            )
            config = {**config, 'pivot_values': pivot_values, 'nest_combinations': nest_combinations}

        try:
            query, params = self.build_pivot_query(config, tenant)
            rows = self.db.execute_query(query, params, fetch=True)
        except ValueError:
            raise
        except Exception as exc:
            logger.error("Pivot query execution failed: %s", exc)
            raise RuntimeError("Query execution failed. Please check your configuration.") from exc

        return {
            'success': True,
            'data': rows or [],
            'columns': self._build_columns_meta(ds, gc, am, cp, cnl, pivot_values, nest_combinations),
            'row_count': len(rows) if rows else 0,
        }

    def build_pivot_query(self, config, tenant):
        ds = config.get('data_source', '')
        gc = config.get('group_columns', [])
        am = config.get('aggregate_measures', [])
        filters = config.get('filters', {})
        cp = config.get('column_pivot')
        rollup = config.get('include_rollup', False)

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
                func, col = m['function'].upper(), m['column']
                alias = self._agg_alias(func, col)
                select_parts.append(
                    f"{func}(*) AS {q(alias)}" if col == '*'
                    else f"{func}({q(col)}) AS {q(alias)}"
                )

        where_clause, wp = self._build_where_clause(ds, filters, tenant)
        # SELECT params (pivot CASE WHEN) come before WHERE params in the SQL
        params = params + wp

        group_by = ', '.join(q(c) for c in gc)
        if rollup:
            group_by += ' WITH ROLLUP'

        query = f"SELECT {', '.join(select_parts)} FROM {q(ds)} WHERE {where_clause} GROUP BY {group_by}"
        return query, params

    def build_underlying_query(self, config, tenant):
        ds = config.get('data_source', '')
        filters = config.get('filters', {})
        q = self._quote_col
        where_clause, params = self._build_where_clause(ds, filters, tenant)

        # Select only allowed columns (groupable + aggregatable) instead of
        # SELECT * — this excludes noisy/sensitive columns like addInfo,
        # guestName, phone, sourceFile that are in the exclude list.
        allowed = self.registry.get_available_columns(ds, tenant)
        col_names = (
            [c['name'] for c in allowed['groupable']]
            + [c['name'] for c in allowed['aggregatable']]
        )
        if not col_names:
            raise ValueError(f"No allowed columns for data source '{ds}'")

        select_clause = ', '.join(q(c) for c in col_names)
        return f"SELECT {select_clause} FROM {q(ds)} WHERE {where_clause}", params

    # -- Validation --------------------------------------------------------

    def _validate_config(self, ds, tenant, gc, am, cp, cnl):
        if not gc or not am:
            raise ValueError("At least one group column and one aggregate measure are required")
        if len(gc) > MAX_GROUP_COLUMNS:
            raise ValueError(f"Maximum {MAX_GROUP_COLUMNS} group columns allowed")
        if len(am) > MAX_AGGREGATE_MEASURES:
            raise ValueError(f"Maximum {MAX_AGGREGATE_MEASURES} aggregate measures allowed")
        if len(cnl) > MAX_NEST_LEVELS:
            raise ValueError(f"Maximum {MAX_NEST_LEVELS} column nest levels allowed")
        for m in am:
            func = m.get('function', '').upper()
            if func not in ALLOWED_AGG_FUNCTIONS:
                raise ValueError(f"Aggregation function '{func}' is not allowed. Allowed: {', '.join(sorted(ALLOWED_AGG_FUNCTIONS))}")
        self._validate_column_roles(gc, cp, cnl)
        self.registry.validate_columns(ds, tenant, gc, [m['column'] for m in am], cp, cnl)

    @staticmethod
    def _validate_column_roles(gc, cp, cnl):
        gs, ns = set(gc), set(cnl)
        if cp:
            if cp in gs:
                raise ValueError(f"Column '{cp}' cannot be used as both row group and column pivot")
            if cp in ns:
                raise ValueError(f"Column '{cp}' cannot be used as both column pivot and column nest level")
        overlap = gs & ns
        if overlap:
            raise ValueError(f"Column '{next(iter(overlap))}' cannot be used as both row group and column nest level")

    # -- WHERE clause (generic) --------------------------------------------

    def _build_where_clause(self, data_source, filters, tenant):
        """Build WHERE clause filtering by the CURRENT tenant only."""
        parts, params = [], []
        # Filter by current tenant only — never expose data from other tenants
        parts.append(f"{self._quote_col(TENANT_COLUMN)} = %s")
        params.append(tenant)

        known = set(COLUMN_TYPE_MAP.get(data_source, {}).keys())
        for col, val in filters.items():
            if val is None or val == '' or val == 'all' or col not in known:
                continue
            if isinstance(val, list) and val:
                # Check if any list item contains a wildcard
                like_items = [v for v in val if isinstance(v, str) and '%' in v]
                exact_items = [v for v in val if v not in like_items]
                sub_parts = []
                if exact_items:
                    ph = ', '.join(['%s'] * len(exact_items))
                    sub_parts.append(f"{self._quote_col(col)} IN ({ph})")
                    params.extend(exact_items)
                for lv in like_items:
                    sub_parts.append(f"{self._quote_col(col)} LIKE %s")
                    params.append(lv)
                if sub_parts:
                    parts.append(f"({' OR '.join(sub_parts)})")
            elif isinstance(val, str) and '%' in val:
                parts.append(f"{self._quote_col(col)} LIKE %s")
                params.append(val)
            else:
                parts.append(f"{self._quote_col(col)} = %s")
                params.append(val)

        return ' AND '.join(parts) if parts else '1=1', params

    # -- Column pivot ------------------------------------------------------

    def _build_pivot_select(self, config, am):
        cp = config.get('column_pivot', '')
        pvs = config.get('pivot_values', [])
        cnl = config.get('column_nest_levels', [])
        q = self._quote_col
        parts, params = [], []

        if not pvs:
            for m in am:
                func, col = m['function'].upper(), m['column']
                alias = self._agg_alias(func, col)
                parts.append(f"{func}(*) AS {q(alias)}" if col == '*' else f"{func}({q(col)}) AS {q(alias)}")
            return parts, params

        for pv in pvs:
            if cnl:
                combos = config.get('nest_combinations', [])
                if combos:
                    for combo in combos:
                        for m in am:
                            func, col = m['function'].upper(), m['column']
                            nl = '_'.join(str(v) for v in combo)
                            alias = f"{pv}_{nl}_{func}_{col}"
                            conds = [f"{q(cp)} = %s"]
                            cp_params = [pv]
                            for i, lc in enumerate(cnl):
                                conds.append(f"{q(lc)} = %s")
                                cp_params.append(combo[i])
                            then = '1' if col == '*' else q(col)
                            parts.append(f"{func}(CASE WHEN {' AND '.join(conds)} THEN {then} ELSE 0 END) AS {q(alias)}")
                            params.extend(cp_params)
                else:
                    for m in am:
                        func, col = m['function'].upper(), m['column']
                        alias = f"{pv}_{func}_{col}"
                        then = '1' if col == '*' else q(col)
                        parts.append(f"{func}(CASE WHEN {q(cp)} = %s THEN {then} ELSE 0 END) AS {q(alias)}")
                        params.append(pv)
            else:
                for m in am:
                    func, col = m['function'].upper(), m['column']
                    alias = f"{pv}_{func}_{col}"
                    then = '1' if col == '*' else q(col)
                    parts.append(f"{func}(CASE WHEN {q(cp)} = %s THEN {then} ELSE 0 END) AS {q(alias)}")
                    params.append(pv)

        for m in am:
            func, col = m['function'].upper(), m['column']
            alias = f"TOTAL_{func}_{col}"
            parts.append(f"{func}(*) AS {q(alias)}" if col == '*' else f"{func}({q(col)}) AS {q(alias)}")

        return parts, params

    # -- Column metadata ---------------------------------------------------

    def _build_columns_meta(self, ds, gc, am, cp, cnl, pivot_values=None, nest_combinations=None):
        """Build column metadata for the pivot result.

        When ``cp`` (column_pivot) is set, returns pivoted column metadata
        with ``pivotValue``, ``nestValues``, and ``pivotGroup`` fields so
        the frontend can render multi-row ``<thead>`` headers.
        """
        tm = COLUMN_TYPE_MAP.get(ds, {})
        cols = []

        # Group columns (row axis)
        for col in gc:
            cols.append({'name': col, 'type': 'group', 'dataType': tm.get(col, 'varchar')})

        if cp and pivot_values:
            # Pivoted aggregate columns — one per (pivot_value, [nest_combo], measure)
            for pv in pivot_values:
                if cnl and nest_combinations:
                    for combo in nest_combinations:
                        for m in am:
                            func = m['function'].upper()
                            col = m['column']
                            nl = '_'.join(str(v) for v in combo)
                            alias = f"{pv}_{nl}_{func}_{col}"
                            dt = 'int' if func == 'COUNT' else (tm.get(col, 'decimal') if col != '*' else 'int')
                            nest_vals = {cnl[i]: combo[i] for i in range(len(cnl))}
                            cols.append({
                                'name': alias,
                                'type': 'aggregate',
                                'function': func,
                                'sourceColumn': col,
                                'dataType': dt,
                                'pivotValue': pv,
                                'pivotColumn': cp,
                                'nestValues': nest_vals,
                                'pivotGroup': 'pivot',
                            })
                else:
                    for m in am:
                        func = m['function'].upper()
                        col = m['column']
                        alias = f"{pv}_{func}_{col}"
                        dt = 'int' if func == 'COUNT' else (tm.get(col, 'decimal') if col != '*' else 'int')
                        cols.append({
                            'name': alias,
                            'type': 'aggregate',
                            'function': func,
                            'sourceColumn': col,
                            'dataType': dt,
                            'pivotValue': pv,
                            'pivotColumn': cp,
                            'pivotGroup': 'pivot',
                        })

            # Grand total columns — one per measure
            for m in am:
                func = m['function'].upper()
                col = m['column']
                alias = f"TOTAL_{func}_{col}"
                dt = 'int' if func == 'COUNT' else (tm.get(col, 'decimal') if col != '*' else 'int')
                cols.append({
                    'name': alias,
                    'type': 'aggregate',
                    'function': func,
                    'sourceColumn': col,
                    'dataType': dt,
                    'pivotGroup': 'total',
                })
        else:
            # Non-pivoted: simple aggregate columns
            for m in am:
                func = m['function'].upper()
                col = m['column']
                alias = self._agg_alias(func, col)
                dt = 'int' if func == 'COUNT' else (tm.get(col, 'decimal') if col != '*' else 'int')
                cols.append({
                    'name': alias,
                    'type': 'aggregate',
                    'function': func,
                    'sourceColumn': col,
                    'dataType': dt,
                })

        return cols

    # -- Fetch distinct pivot values ----------------------------------------

    def _fetch_pivot_values(self, data_source, column_pivot, nest_levels, filters, tenant):
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
        pv_query = f"SELECT DISTINCT {q(column_pivot)} FROM {q(data_source)} WHERE {where_clause} ORDER BY {q(column_pivot)}"
        pv_rows = self.db.execute_query(pv_query, params, fetch=True) or []
        pivot_values = [row[column_pivot] for row in pv_rows if row.get(column_pivot) is not None]

        # Fetch distinct nest level combinations
        nest_combinations = []
        if nest_levels:
            nl_cols = ', '.join(q(c) for c in nest_levels)
            nl_query = (
                f"SELECT DISTINCT {nl_cols} FROM {q(data_source)} "
                f"WHERE {where_clause} ORDER BY {nl_cols}"
            )
            nl_rows = self.db.execute_query(nl_query, list(params), fetch=True) or []
            nest_combinations = [
                tuple(row[c] for c in nest_levels)
                for row in nl_rows
                if all(row.get(c) is not None for c in nest_levels)
            ]

        return pivot_values, nest_combinations

    # -- Helpers -----------------------------------------------------------

    def _quote_col(self, name):
        return AllowedColumnsRegistry._quote_column(name, self.COLUMN_QUOTE)

    @staticmethod
    def _agg_alias(func, col):
        return func if col == '*' else f"{func}_{col}"
