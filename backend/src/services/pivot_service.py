"""
Pivot Service — AllowedColumnsRegistry, schema introspection, and PivotService.

Query construction is delegated to ``pivot_query_builder.py``.
Column definitions are introspected at startup via parameters in ``ui.pivot``.

Requirements: 1.5–1.8, 2.4, 3.1–3.3, 3.9, 6.1–6.6, 7.4, 9.1–9.11
Reference: .kiro/specs/dynamic-pivot-views/design.md
"""

import logging
import re
from typing import Any

from dialect_helpers import dialect

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — canonical definitions in pivot_query_builder.py; re-exported here
# for backward compatibility.
# ---------------------------------------------------------------------------

from services.pivot_query_builder import (
    TENANT_COLUMN,
)

# SQL types that are treated as numeric (→ aggregatable by default).
_NUMERIC_TYPE_PATTERN = re.compile(
    r"^(int|integer|tinyint|smallint|mediumint|bigint"
    r"|decimal|numeric|float|double|real)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Schema introspection helpers
# ---------------------------------------------------------------------------


def _normalise_sql_type(raw_type: str) -> str:
    """Normalise a MySQL type string to a simple category."""
    base = raw_type.split("(")[0].strip().lower()
    if base in ("decimal", "numeric", "float", "double", "real"):
        return "decimal"
    if base in ("int", "integer", "tinyint", "smallint", "mediumint", "bigint"):
        return "int"
    if base in ("date", "datetime", "timestamp"):
        return "date"
    return "varchar"


def _is_numeric_type(raw_type: str) -> bool:
    """Return True if the SQL type is numeric."""
    return bool(_NUMERIC_TYPE_PATTERN.match(raw_type.strip()))


def derive_columns_from_schema(
    db,
    data_source: str,
    exclude_columns: set,
    force_groupable: set,
) -> tuple[list[str], list[str], dict[str, str]]:
    """Introspect a view/table via DESCRIBE and classify columns.

    Returns ``(groupable, aggregatable, type_map)``.
    """
    rows = db.execute_query(dialect.describe_table(data_source), fetch=True)

    groupable: list[str] = []
    aggregatable: list[str] = []
    type_map: dict[str, str] = {}

    for row in rows:
        col_name = row["Field"]
        raw_type = row["Type"]

        # MySQL connector may return bytes instead of str in some environments
        if isinstance(col_name, bytes):
            col_name = col_name.decode("utf-8")
        if isinstance(raw_type, bytes):
            raw_type = raw_type.decode("utf-8")

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
        val = parameter_service.get_param(namespace="ui.pivot", key=key)
        if val and isinstance(val, list):
            return val
    except Exception as exc:
        # Missing/unreadable parameter falls back to an empty list.
        logger.debug("Could not read list param ui.pivot/%s: %s", key, exc)
    return []


def _get_param_str(parameter_service, key: str) -> str | None:
    """Read a string parameter from ui.pivot namespace, or return None."""
    if parameter_service is None:
        return None
    try:
        val = parameter_service.get_param(namespace="ui.pivot", key=key)
        if val and isinstance(val, str):
            return val
    except Exception as exc:
        # Missing/unreadable parameter falls back to None.
        logger.debug("Could not read str param ui.pivot/%s: %s", key, exc)
    return None


def build_registry_from_db(db, parameter_service=None) -> None:
    """Populate module-level lookup dicts by introspecting the database.

    Reads ``ui.pivot / registered_sources`` for view names (defaults to
    ``['vw_mutaties', 'vw_bnb_total']``), then introspects each and
    populates SYSTEM_ALLOWED_COLUMNS, COLUMN_TYPE_MAP, etc.

    Raises:
        RuntimeError: if any data source cannot be introspected.
    """
    # SYSTEM_ALLOWED_COLUMNS, COLUMN_TYPE_MAP, DATA_SOURCE_LABELS and
    # DATA_SOURCE_MODULES are mutated in place (item assignment), so no
    # `global` declaration is required for them.
    global _registry_initialised

    # Which views/tables to register
    sources = _get_param_list(parameter_service, "registered_sources")
    if not sources:
        sources = ["vw_mutaties", "vw_bnb_total"]

    for ds_name in sources:
        exclude = set(_get_param_list(parameter_service, f"exclude_columns.{ds_name}"))
        force_g = set(_get_param_list(parameter_service, f"force_groupable.{ds_name}"))
        label = (
            _get_param_str(parameter_service, f"datasource_label.{ds_name}") or ds_name
        )
        module = _get_param_str(parameter_service, f"datasource_module.{ds_name}")

        try:
            groupable, aggregatable, col_types = derive_columns_from_schema(
                db,
                ds_name,
                exclude,
                force_g,
            )
        except Exception as exc:
            msg = (
                f"FATAL: Cannot introspect schema for pivot data source "
                f"'{ds_name}': {exc}"
            )
            logger.critical(msg)
            raise RuntimeError(msg) from exc

        SYSTEM_ALLOWED_COLUMNS[ds_name] = {
            "groupable": groupable,
            "aggregatable": aggregatable,
        }
        COLUMN_TYPE_MAP[ds_name] = col_types
        DATA_SOURCE_LABELS[ds_name] = label
        DATA_SOURCE_MODULES[ds_name] = module

    _registry_initialised = True
    logger.info(
        "Pivot registry initialised from DB for %d data source(s): %s",
        len(sources),
        ", ".join(sources),
    )


def ensure_registry(db=None, parameter_service=None) -> None:
    """Lazily initialise the pivot registry if startup init failed.

    Safe to call on every request — returns immediately when the
    registry is already populated.  When *db* or *parameter_service*
    are ``None`` the function creates throwaway instances using the
    current ``TEST_MODE`` environment variable.
    """
    # _registry_initialised is only read here (assignment happens inside
    # build_registry_from_db), so no `global` declaration is needed.
    if _registry_initialised:
        return

    import os

    from database import DatabaseManager
    from services.parameter_service import ParameterService

    if db is None:
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = DatabaseManager(test_mode=test_mode)
    if parameter_service is None:
        parameter_service = ParameterService(db)

    build_registry_from_db(db, parameter_service)
    logger.info("Pivot registry lazily initialised on first request")


# ---------------------------------------------------------------------------
# Module-level dicts — populated by build_registry_from_db() at startup.
# ---------------------------------------------------------------------------

SYSTEM_ALLOWED_COLUMNS: dict[str, dict[str, list[str]]] = {}
COLUMN_TYPE_MAP: dict[str, dict[str, str]] = {}
DATA_SOURCE_LABELS: dict[str, str] = {}
DATA_SOURCE_MODULES: dict[str, str | None] = {}
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

    def get_available_columns(self, data_source: str, tenant: str) -> dict[str, list]:
        ensure_registry()
        system_cols = SYSTEM_ALLOWED_COLUMNS.get(data_source)
        if system_cols is None:
            raise ValueError(f"Unknown data source '{data_source}'")

        type_map = COLUMN_TYPE_MAP.get(data_source, {})

        def _col_obj(name: str) -> dict:
            return {"name": name, "type": type_map.get(name, "varchar"), "label": name}

        tenant_restriction = self._get_tenant_restriction(data_source, tenant)
        if tenant_restriction is None:
            return {
                "groupable": [_col_obj(c) for c in system_cols["groupable"]],
                "aggregatable": [_col_obj(c) for c in system_cols["aggregatable"]],
            }
        return {
            "groupable": [
                _col_obj(c)
                for c in system_cols["groupable"]
                if c in tenant_restriction.get("groupable", [])
            ],
            "aggregatable": [
                _col_obj(c)
                for c in system_cols["aggregatable"]
                if c in tenant_restriction.get("aggregatable", [])
            ],
        }

    def get_registered_sources(self) -> list[dict[str, Any]]:
        ensure_registry()
        return [
            {
                "name": name,
                "label": DATA_SOURCE_LABELS.get(name, name),
                "module": DATA_SOURCE_MODULES.get(name),
            }
            for name in SYSTEM_ALLOWED_COLUMNS
        ]

    def validate_columns(
        self,
        data_source: str,
        tenant: str,
        group_columns: list[str],
        aggregate_columns: list[str],
        column_pivot: str | None = None,
        column_nest_levels: list[str] | None = None,
    ) -> None:
        allowed = self.get_available_columns(data_source, tenant)
        allowed_g = {
            c["name"] if isinstance(c, dict) else c for c in allowed["groupable"]
        }
        allowed_a = {
            c["name"] if isinstance(c, dict) else c for c in allowed["aggregatable"]
        }

        for col in group_columns:
            if col not in allowed_g:
                raise ValueError(
                    f"Column '{col}' is not allowed for data source '{data_source}'"
                )
        for col in aggregate_columns:
            if col != "*" and col not in allowed_a:
                raise ValueError(
                    f"Column '{col}' is not allowed for data source '{data_source}'"
                )
        if column_pivot and column_pivot not in allowed_g:
            raise ValueError(
                f"Column '{column_pivot}' is not allowed for data source '{data_source}'"
            )
        for col in column_nest_levels or []:
            if col not in allowed_g:
                raise ValueError(
                    f"Column '{col}' is not allowed for data source '{data_source}'"
                )

    @staticmethod
    def _quote_column(name: str, quote_char: str = "`") -> str:
        sanitised = name.replace(quote_char, "")
        return f"{quote_char}{sanitised}{quote_char}"

    def _get_tenant_restriction(
        self, data_source: str, tenant: str
    ) -> dict[str, Any] | None:
        try:
            value = self.parameter_service.get_param(
                namespace="ui.pivot",
                key=f"allowed_columns.{data_source}",
                tenant=tenant,
            )
            if value and isinstance(value, dict):
                return value
        except Exception:
            logger.warning(
                "Failed to read tenant column restriction for %s / %s",
                data_source,
                tenant,
            )
        return None


# ===================================================================
# PivotService
# ===================================================================


class PivotService:
    """Builds and executes dynamic pivot queries with tenant isolation.

    Query construction is delegated to PivotQueryBuilder
    (services/pivot_query_builder.py). This class orchestrates
    validation, execution, and result assembly.
    """

    COLUMN_QUOTE = "`"

    def __init__(self, db, parameter_service) -> None:
        self.db = db
        self.parameter_service = parameter_service
        self.registry = AllowedColumnsRegistry(parameter_service)

        from services.pivot_query_builder import PivotQueryBuilder

        self._qb = PivotQueryBuilder(
            registry=self.registry,
            column_type_map_getter=lambda: COLUMN_TYPE_MAP,
        )

    def get_available_columns(self, data_source: str, tenant: str) -> dict[str, list]:
        return self.registry.get_available_columns(data_source, tenant)

    def get_registered_sources(self) -> list[dict[str, Any]]:
        return self.registry.get_registered_sources()

    def execute_pivot(
        self, tenant: str, user_tenants: list[str], config: dict[str, Any]
    ) -> dict[str, Any]:
        ds = config.get("data_source", "")
        gc = config.get("group_columns", [])
        am = config.get("aggregate_measures", [])
        cp = config.get("column_pivot")
        cnl = config.get("column_nest_levels", [])

        self._validate_config(ds, tenant, gc, am, cp, cnl)

        # Auto-fetch distinct pivot values when column_pivot is set
        # but pivot_values are not provided by the caller.
        pivot_values = config.get("pivot_values", [])
        nest_combinations = config.get("nest_combinations", [])
        if cp and not pivot_values:
            pivot_values, nest_combinations = self._fetch_pivot_values(
                ds,
                cp,
                cnl,
                config.get("filters", {}),
                tenant,
            )
            config = {
                **config,
                "pivot_values": pivot_values,
                "nest_combinations": nest_combinations,
            }

        try:
            query, params = self.build_pivot_query(config, tenant)
            rows = self.db.execute_query(query, params, fetch=True)
        except ValueError:
            raise
        except Exception as exc:
            logger.error("Pivot query execution failed: %s", exc)
            raise RuntimeError(
                "Query execution failed. Please check your configuration."
            ) from exc

        return {
            "success": True,
            "data": rows or [],
            "columns": self._build_columns_meta(
                ds, gc, am, cp, cnl, pivot_values, nest_combinations
            ),
            "row_count": len(rows) if rows else 0,
        }

    # -- Delegated query building ------------------------------------------

    def build_pivot_query(
        self, config: dict[str, Any], tenant: str
    ) -> tuple[str, list]:
        return self._qb.build_pivot_query(config, tenant)

    def build_underlying_query(
        self, config: dict[str, Any], tenant: str
    ) -> tuple[str, list]:
        return self._qb.build_underlying_query(config, tenant)

    # -- Validation (delegated) --------------------------------------------

    def _validate_config(
        self,
        ds: str,
        tenant: str,
        gc: list[str],
        am: list[dict[str, str]],
        cp: str | None,
        cnl: list[str],
    ) -> None:
        self._qb.validate_config(ds, tenant, gc, am, cp, cnl)

    @staticmethod
    def _validate_column_roles(gc: list[str], cp: str | None, cnl: list[str]) -> None:
        from services.pivot_query_builder import PivotQueryBuilder

        PivotQueryBuilder._validate_column_roles(gc, cp, cnl)

    # -- Column metadata (delegated) ---------------------------------------

    def _build_columns_meta(
        self, ds, gc, am, cp, cnl, pivot_values=None, nest_combinations=None
    ):
        return self._qb.build_columns_meta(
            ds, gc, am, cp, cnl, pivot_values, nest_combinations
        )

    # -- Fetch distinct pivot values (delegated) ----------------------------

    def _fetch_pivot_values(
        self, data_source, column_pivot, nest_levels, filters, tenant
    ):
        return self._qb.fetch_pivot_values(
            self.db, data_source, column_pivot, nest_levels, filters, tenant
        )

    # -- Helpers (kept for backward compat) --------------------------------

    def _quote_col(self, name):
        return AllowedColumnsRegistry._quote_column(name, self.COLUMN_QUOTE)

    @staticmethod
    def _agg_alias(func, col):
        return func if col == "*" else f"{func}_{col}"
