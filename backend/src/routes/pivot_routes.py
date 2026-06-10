"""
Pivot API Routes

REST endpoints for executing dynamic pivot queries and managing
saved pivot model definitions (CRUD).

Routes:
    POST   /api/pivot/execute          — execute a pivot query
    GET    /api/pivot/columns/<source>  — available columns for a data source
    GET    /api/pivot/sources           — list registered data sources
    GET    /api/pivot/models            — list saved models for tenant
    POST   /api/pivot/models            — save a new model
    PUT    /api/pivot/models/<id>       — update an existing model
    GET    /api/pivot/models/<id>       — load a specific model
    DELETE /api/pivot/models/<id>       — delete a model
    POST   /api/pivot/export            — export underlying dataset

Requirements: 3.1, 3.3, 3.9, 4.4, 5.4, 6.4, 6.5
Reference: .kiro/specs/dynamic-pivot-views/design.md §3 Pivot API Routes
"""

import os
import logging
from datetime import date, datetime
from decimal import Decimal
from flask import Blueprint, request, jsonify
from flask.typing import ResponseReturnValue
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from services.parameter_service import ParameterService
from services.pivot_service import PivotService
from services.pivot_model_store import PivotModelStore

logger = logging.getLogger(__name__)

pivot_bp = Blueprint('pivot', __name__, url_prefix='/api/pivot')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_rows(rows) -> list:
    """Normalise DB rows for JSON serialisation.

    * ``datetime`` / ``date`` → ISO-8601 string (``YYYY-MM-DD`` or full ISO)
    * ``Decimal``             → ``float``
    * ``bytes``               → UTF-8 string

    This avoids Flask's default RFC-2822 date format
    (``"Thu, 21 Mar 2019 00:00:00 GMT"``) which is hard to use in
    spreadsheets and CSV exports.
    """
    if not rows:
        return rows
    cleaned = []
    for row in rows:
        out = {}
        for key, val in row.items():
            if isinstance(val, datetime):
                out[key] = val.strftime('%Y-%m-%d %H:%M:%S') if val.hour or val.minute or val.second else val.strftime('%Y-%m-%d')
            elif isinstance(val, date):
                out[key] = val.strftime('%Y-%m-%d')
            elif isinstance(val, Decimal):
                out[key] = float(val)
            elif isinstance(val, bytes):
                out[key] = val.decode('utf-8', errors='replace')
            else:
                out[key] = val
        cleaned.append(out)
    return cleaned


def _get_service() -> PivotService:
    """Create a PivotService instance with current test mode setting."""
    test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
    db = DatabaseManager(test_mode=test_mode)
    ps = ParameterService(db)
    return PivotService(db, ps)


def _get_store() -> PivotModelStore:
    """Create a PivotModelStore instance with current test mode setting."""
    test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
    db = DatabaseManager(test_mode=test_mode)
    return PivotModelStore(db)


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------

@pivot_bp.route('/execute', methods=['POST'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def execute_pivot(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Execute a dynamic pivot query.

    Request body:
        {
            "data_source": "vw_mutaties",
            "group_columns": ["Aangifte", "jaar"],
            "aggregate_measures": [{"function": "SUM", "column": "Amount"}],
            "filters": {"years": [2024, 2025]},
            "column_pivot": null,
            "column_nest_levels": [],
            "include_rollup": true
        }

    Returns:
        JSON with ``success``, ``data``, ``columns``, and ``row_count``.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400

        service = _get_service()
        result = service.execute_pivot(tenant, user_tenants, data)
        # Clean date/Decimal/bytes values for JSON serialisation
        if result.get('data'):
            result['data'] = _clean_rows(result['data'])
        return jsonify(result)
    except ValueError as e:
        error_msg = str(e)
        if 'already exists' in error_msg:
            return jsonify({'success': False, 'error': error_msg}), 409
        if 'not found' in error_msg.lower():
            return jsonify({'success': False, 'error': error_msg}), 404
        return jsonify({'success': False, 'error': error_msg}), 400
    except RuntimeError as e:
        logger.error("Pivot query execution failed: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        logger.error("Unexpected error executing pivot: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Column & source discovery
# ---------------------------------------------------------------------------

@pivot_bp.route('/columns/<source>', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_available_columns(source, user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Return groupable and aggregatable columns for a data source.

    Args:
        source: data source name (URL path parameter).

    Returns:
        JSON ``{groupable: [...], aggregatable: [...]}``.
    """
    try:
        service = _get_service()
        columns = service.get_available_columns(source, tenant)
        return jsonify({'success': True, **columns})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error("Error fetching columns for %s: %s", source, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@pivot_bp.route('/sources', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def get_registered_sources(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Return the list of registered pivot data sources.

    Returns:
        JSON ``{success: true, data: [{name, label}, ...]}``.
    """
    try:
        service = _get_service()
        sources = service.get_registered_sources()
        return jsonify({'success': True, 'data': sources})
    except Exception as e:
        logger.error("Error fetching registered sources: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Pivot model CRUD
# ---------------------------------------------------------------------------

@pivot_bp.route('/models', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def list_models(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """List all saved pivot models for the current tenant.

    Returns:
        JSON ``{success: true, data: [{id, name, data_source, created_by, created_at}, ...]}``.
    """
    try:
        store = _get_store()
        models = store.list_models(tenant)
        return jsonify({'success': True, 'data': models})
    except Exception as e:
        logger.error("Error listing pivot models: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@pivot_bp.route('/models', methods=['POST'])
@cognito_required(required_permissions=['reports_export'])
@tenant_required()
def save_model(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Save a new pivot model.

    Request body:
        {
            "name": "BTW per year",
            "definition": {
                "data_source": "vw_mutaties",
                "group_columns": ["Aangifte", "jaar"],
                "aggregate_measures": [{"function": "SUM", "column": "Amount"}],
                "filters": {"years": [2024, 2025]},
                "column_pivot": null,
                "column_nest_levels": [],
                "display_mode": "hierarchical"
            }
        }

    Returns:
        JSON ``{success: true, id: <int>}`` on success.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400

        name = data.get('name')
        definition = data.get('definition')
        if not name:
            return jsonify({'success': False, 'error': 'Model name is required'}), 400
        if not definition:
            return jsonify({'success': False, 'error': 'Model definition is required'}), 400

        store = _get_store()
        result = store.save_model(tenant, user_email, name, definition)
        return jsonify(result), 201
    except ValueError as e:
        error_msg = str(e)
        if 'already exists' in error_msg:
            return jsonify({'success': False, 'error': error_msg}), 409
        if 'not found' in error_msg.lower():
            return jsonify({'success': False, 'error': error_msg}), 404
        return jsonify({'success': False, 'error': error_msg}), 400
    except Exception as e:
        logger.error("Error saving pivot model: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@pivot_bp.route('/models/<int:model_id>', methods=['PUT'])
@cognito_required(required_permissions=['reports_export'])
@tenant_required()
def update_model(model_id, user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Update an existing pivot model's definition.

    Args:
        model_id: primary key of the model (URL path parameter).

    Request body:
        {
            "definition": { ... }
        }

    Returns:
        JSON ``{success: true}`` on success.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400

        definition = data.get('definition')
        if not definition:
            return jsonify({'success': False, 'error': 'Model definition is required'}), 400

        store = _get_store()
        result = store.update_model(tenant, user_email, model_id, definition)
        return jsonify(result)
    except ValueError as e:
        error_msg = str(e)
        if 'already exists' in error_msg:
            return jsonify({'success': False, 'error': error_msg}), 409
        if 'not found' in error_msg.lower():
            return jsonify({'success': False, 'error': error_msg}), 404
        return jsonify({'success': False, 'error': error_msg}), 400
    except Exception as e:
        logger.error("Error updating pivot model %s: %s", model_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@pivot_bp.route('/models/<int:model_id>', methods=['GET'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def load_model(model_id, user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Load a specific pivot model by ID.

    Args:
        model_id: primary key of the model (URL path parameter).

    Returns:
        JSON with model metadata and deserialized definition.
    """
    try:
        store = _get_store()
        model = store.load_model(tenant, model_id)
        return jsonify({'success': True, **model})
    except ValueError as e:
        error_msg = str(e)
        if 'not found' in error_msg.lower():
            return jsonify({'success': False, 'error': error_msg}), 404
        return jsonify({'success': False, 'error': error_msg}), 400
    except Exception as e:
        logger.error("Error loading pivot model %s: %s", model_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@pivot_bp.route('/models/<int:model_id>', methods=['DELETE'])
@cognito_required(required_permissions=['reports_export'])
@tenant_required()
def delete_model(model_id, user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Delete a pivot model.

    Args:
        model_id: primary key of the model (URL path parameter).

    Returns:
        JSON ``{success: true}`` if deleted, 404 if not found.
    """
    try:
        store = _get_store()
        deleted = store.delete_model(tenant, model_id)
        if not deleted:
            return jsonify({'success': False, 'error': 'Pivot model not found'}), 404
        return jsonify({'success': True})
    except Exception as e:
        logger.error("Error deleting pivot model %s: %s", model_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@pivot_bp.route('/export', methods=['POST'])
@cognito_required(required_permissions=['reports_read'])
@tenant_required()
def export_underlying(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Export the underlying (non-aggregated) dataset for a pivot config.

    Uses the same filters and tenant isolation as ``execute_pivot`` but
    returns raw rows without GROUP BY.

    Request body:
        Same structure as ``/execute`` (data_source, filters, etc.).

    Returns:
        JSON ``{success: true, data: [...], row_count: <int>}``.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400

        service = _get_service()
        query, params = service.build_underlying_query(data, tenant)

        try:
            rows = service.db.execute_query(query, params, fetch=True)
        except Exception as exc:
            logger.error("Export query execution failed: %s", exc)
            raise RuntimeError(
                "Query execution failed. Please check your configuration."
            ) from exc

        return jsonify({
            'success': True,
            'data': _clean_rows(rows) if rows else [],
            'row_count': len(rows) if rows else 0,
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except RuntimeError as e:
        logger.error("Export execution failed: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        logger.error("Unexpected error exporting pivot data: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500
