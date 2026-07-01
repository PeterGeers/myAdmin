"""
SysAdmin Pivot Data Source Management Routes

API endpoints for managing which database tables/views are available
as pivot data sources. Sysadmins can enable/disable sources, assign
module tags (FIN, STR, ZZP), and set human-readable labels.

Routes:
    GET  /api/sysadmin/pivot/datasources — list all tables/views with pivot status
    PUT  /api/sysadmin/pivot/datasources — update pivot-enabled list and module tags

Requirements: 11.1, 11.2, 11.3, 11.4, 11.8, 11.9
Reference: .kiro/specs/dynamic-pivot-views/design.md §9
"""

import logging
import os
from flask import Blueprint, request, jsonify
from flask.typing import ResponseReturnValue
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from services.parameter_service import ParameterService
from services.pivot_service import derive_columns_from_schema

logger = logging.getLogger(__name__)

sysadmin_pivot_bp = Blueprint("sysadmin_pivot", __name__)

# Valid module tags for data sources
VALID_MODULES = {"FIN", "STR", "ZZP"}


def _get_db() -> DatabaseManager:
    """Create a DatabaseManager instance with current test mode setting."""
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    return DatabaseManager(test_mode=test_mode)


def _get_param_service(db=None) -> "ParameterService":
    """Create a ParameterService instance."""
    if db is None:
        db = _get_db()
    return ParameterService(db)


def _get_all_tables(db) -> list:
    """Run SHOW FULL TABLES and return list of {name, type} dicts."""
    rows = db.execute_query("SHOW FULL TABLES", fetch=True)
    if not rows:
        return []

    # SHOW FULL TABLES returns two columns; the first column name is
    # database-dependent (e.g. "Tables_in_finance"), the second is
    # "Table_type".  We access by position via the dict keys.
    results = []
    for row in rows:
        keys = list(row.keys())
        name = row[keys[0]]
        table_type = row.get("Table_type", row.get(keys[1], "BASE TABLE"))
        results.append(
            {
                "name": name,
                "type": table_type,
            }
        )
    return results


def _read_current_params(ps) -> tuple:
    """Read current pivot data source parameters from the parameter service.

    Returns:
        (registered_sources, modules_map, labels_map)
        - registered_sources: list of enabled source names
        - modules_map: {source_name: module_tag}
        - labels_map: {source_name: label}
    """
    registered = ps.get_param(namespace="ui.pivot", key="registered_sources") or []
    if not isinstance(registered, list):
        registered = []

    # Read module and label params for each registered source
    modules_map = {}
    labels_map = {}
    for name in registered:
        mod = ps.get_param(namespace="ui.pivot", key=f"datasource_module.{name}")
        if mod and isinstance(mod, str):
            modules_map[name] = mod
        lbl = ps.get_param(namespace="ui.pivot", key=f"datasource_label.{name}")
        if lbl and isinstance(lbl, str):
            labels_map[name] = lbl

    return registered, modules_map, labels_map


# ---------------------------------------------------------------------------
# GET /datasources
# ---------------------------------------------------------------------------


@sysadmin_pivot_bp.route("/datasources", methods=["GET"])
@cognito_required(required_roles=["SysAdmin"])
@tenant_required(allow_sysadmin=True)
def list_datasources(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """List all database tables/views with their pivot status.

    Merges ``SHOW FULL TABLES`` with current parameter values for
    ``registered_sources``, ``datasource_module.*``, and
    ``datasource_label.*``.

    Returns:
        JSON ``{success: true, data: [{name, type, pivot_enabled, module, label}, ...]}``.
    """
    try:
        db = _get_db()
        ps = _get_param_service(db)

        all_tables = _get_all_tables(db)
        registered, modules_map, labels_map = _read_current_params(ps)
        registered_set = set(registered)

        data = []
        for table in all_tables:
            name = table["name"]
            data.append(
                {
                    "name": name,
                    "type": table["type"],
                    "pivot_enabled": name in registered_set,
                    "module": modules_map.get(name),
                    "label": labels_map.get(name),
                }
            )

        return jsonify({"success": True, "data": data})

    except Exception as e:
        logger.error("Error listing pivot datasources: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# PUT /datasources
# ---------------------------------------------------------------------------


@sysadmin_pivot_bp.route("/datasources", methods=["PUT"])
@cognito_required(required_roles=["SysAdmin"])
@tenant_required(allow_sysadmin=True)
def update_datasources(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Update the pivot-enabled data source list and module/label tags.

    Request body::

        {
            "sources": [
                {"name": "vw_mutaties", "pivot_enabled": true,
                 "module": "FIN", "label": "Financial Transactions"},
                {"name": "vw_bnb_total", "pivot_enabled": true,
                 "module": "STR", "label": "STR Revenue"}
            ]
        }

    The handler:
    1. Validates each source name exists in the database.
    2. Writes ``ui.pivot / registered_sources`` at system scope.
    3. Writes ``datasource_module.<name>`` and ``datasource_label.<name>``
       per source at system scope.
    4. Auto-creates ``exclude_columns.<name>`` and ``force_groupable.<name>``
       defaults for newly enabled sources via schema introspection.

    Returns:
        JSON ``{success: true}`` on success.
    """
    try:
        body = request.get_json()
        if not body or "sources" not in body:
            return jsonify(
                {
                    "success": False,
                    "error": 'Request body must contain a "sources" array',
                }
            ), 400

        sources = body["sources"]
        if not isinstance(sources, list):
            return jsonify(
                {
                    "success": False,
                    "error": '"sources" must be an array',
                }
            ), 400

        db = _get_db()
        ps = _get_param_service(db)

        # 1. Validate source names against actual DB objects
        all_tables = _get_all_tables(db)
        valid_names = {t["name"] for t in all_tables}

        for src in sources:
            name = src.get("name")
            if not name:
                return jsonify(
                    {
                        "success": False,
                        "error": 'Each source must have a "name" field',
                    }
                ), 400
            if name not in valid_names:
                return jsonify(
                    {
                        "success": False,
                        "error": f"Source '{name}' does not exist in the database",
                    }
                ), 400
            module = src.get("module")
            if module is not None and module not in VALID_MODULES:
                return jsonify(
                    {
                        "success": False,
                        "error": (
                            f"Invalid module '{module}' for source '{name}'. "
                            f"Valid modules: {', '.join(sorted(VALID_MODULES))}"
                        ),
                    }
                ), 400

        # Determine which sources are being enabled
        enabled_sources = [s for s in sources if s.get("pivot_enabled", False)]
        enabled_names = [s["name"] for s in enabled_sources]

        # Read previously registered sources to detect newly enabled ones
        prev_registered = (
            ps.get_param(
                namespace="ui.pivot",
                key="registered_sources",
            )
            or []
        )
        if not isinstance(prev_registered, list):
            prev_registered = []
        prev_set = set(prev_registered)

        # 2. Write registered_sources (list of enabled names)
        ps.set_param(
            scope="system",
            scope_id="_system_",
            namespace="ui.pivot",
            key="registered_sources",
            value=enabled_names,
            value_type="json",
            created_by=user_email,
        )

        # 3. Write module and label per enabled source
        for src in enabled_sources:
            name = src["name"]
            module = src.get("module")
            label = src.get("label")

            if module:
                ps.set_param(
                    scope="system",
                    scope_id="_system_",
                    namespace="ui.pivot",
                    key=f"datasource_module.{name}",
                    value=module,
                    value_type="string",
                    created_by=user_email,
                )
            if label:
                ps.set_param(
                    scope="system",
                    scope_id="_system_",
                    namespace="ui.pivot",
                    key=f"datasource_label.{name}",
                    value=label,
                    value_type="string",
                    created_by=user_email,
                )

        # 4. Auto-create defaults for newly enabled sources
        newly_enabled = [name for name in enabled_names if name not in prev_set]
        for name in newly_enabled:
            _auto_create_defaults(db, ps, name, user_email)

        # Clean up module/label params for sources that were disabled
        disabled_names = prev_set - set(enabled_names)
        for name in disabled_names:
            ps.delete_param(
                "system", "_system_", "ui.pivot", f"datasource_module.{name}"
            )
            ps.delete_param(
                "system", "_system_", "ui.pivot", f"datasource_label.{name}"
            )

        logger.info(
            "Pivot datasources updated by %s: enabled=%s",
            user_email,
            enabled_names,
        )

        return jsonify({"success": True})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Error updating pivot datasources: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auto_create_defaults(db, ps, source_name, created_by) -> None:
    """Auto-create ``exclude_columns`` and ``force_groupable`` defaults
    for a newly enabled data source by introspecting its schema.

    - ``exclude_columns``: empty list (no columns excluded by default)
    - ``force_groupable``: numeric columns whose names suggest they are
      categorical (year, month, quarter, week, etc.)
    """
    try:
        # Introspect schema to discover columns
        groupable, aggregatable, type_map = derive_columns_from_schema(
            db,
            source_name,
            exclude_columns=set(),
            force_groupable=set(),
        )

        # Heuristic: numeric columns with category-like names → force groupable
        category_hints = {
            "year",
            "jaar",
            "month",
            "maand",
            "quarter",
            "kwartaal",
            "week",
            "q",
            "m",
            "period",
            "periode",
        }
        force_groupable = [col for col in aggregatable if col.lower() in category_hints]

        # Only write if no existing value (don't overwrite manual config)
        existing_exclude = ps.get_param(
            namespace="ui.pivot",
            key=f"exclude_columns.{source_name}",
        )
        if existing_exclude is None:
            ps.set_param(
                scope="system",
                scope_id="_system_",
                namespace="ui.pivot",
                key=f"exclude_columns.{source_name}",
                value=[],
                value_type="json",
                created_by=created_by,
            )

        existing_fg = ps.get_param(
            namespace="ui.pivot",
            key=f"force_groupable.{source_name}",
        )
        if existing_fg is None:
            ps.set_param(
                scope="system",
                scope_id="_system_",
                namespace="ui.pivot",
                key=f"force_groupable.{source_name}",
                value=force_groupable,
                value_type="json",
                created_by=created_by,
            )

        logger.info(
            "Auto-created defaults for '%s': force_groupable=%s",
            source_name,
            force_groupable,
        )

    except Exception as exc:
        # Non-fatal: log warning but don't fail the PUT request
        logger.warning(
            "Failed to auto-create defaults for '%s': %s",
            source_name,
            exc,
        )
