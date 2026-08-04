"""
Budget Routes Blueprint

Handles core budget management endpoints:
- Budget version CRUD and status transitions
- Budget line entry
- Dashboard budget vs actuals comparison

AI and copy endpoints are in budget_ai_routes.py.
"""

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.budget_service import BudgetService

# Create blueprint
budget_bp = Blueprint("budget", __name__)

# Service instances (will be set by set_test_mode)
budget_service = None


def set_test_mode(test_mode: bool) -> None:
    """Set test mode for budget service"""
    global budget_service
    budget_service = BudgetService(test_mode=test_mode)


# =============================================================================
# Budget Version Routes
# =============================================================================


@budget_bp.route("/api/budget/versions", methods=["GET"])
@cognito_required(required_permissions=["finance_read"])
@tenant_required()
def budget_list_versions(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """List budget versions, optionally filtered by fiscal year."""
    try:
        year = request.args.get("year", None)
        if year is not None:
            year = int(year)

        result = budget_service.list_versions(tenant, year=year)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except ValueError:
        return jsonify({"success": False, "error": "Invalid year parameter"}), 400
    except Exception as e:  # noqa: BLE001
        print(f"Budget list versions error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


@budget_bp.route("/api/budget/versions", methods=["POST"])
@cognito_required(required_permissions=["finance_write"])
@tenant_required()
def budget_create_version(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Create a new budget version with status Draft."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        name = data.get("name")
        fiscal_year = data.get("fiscal_year")

        # Validate required fields
        if not name:
            return jsonify({"success": False, "error": "Name is required"}), 400
        if not fiscal_year:
            return jsonify({"success": False, "error": "Fiscal year is required"}), 400

        # Validate name length
        if len(name) > 100:
            return jsonify(
                {"success": False, "error": "Name must be 100 characters or fewer"}
            ), 400

        # Validate fiscal year format
        if not isinstance(fiscal_year, int) or fiscal_year < 1000 or fiscal_year > 9999:
            return jsonify(
                {"success": False, "error": "Fiscal year must be a 4-digit year"}
            ), 400

        result = budget_service.create_version(tenant, name, fiscal_year)

        if result["success"]:
            return jsonify(result), 201
        else:
            return jsonify(result), 400
    except Exception as e:  # noqa: BLE001
        print(f"Budget create version error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


@budget_bp.route("/api/budget/versions/<int:version_id>/status", methods=["PUT"])
@cognito_required(required_permissions=["finance_write"])
@tenant_required()
def budget_transition_status(
    user_email, user_roles, tenant, user_tenants, version_id
) -> ResponseReturnValue:
    """Transition a budget version's status (approve or revise)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        action = data.get("action")
        if not action:
            return jsonify({"success": False, "error": "Action is required"}), 400

        result = budget_service.transition_status(tenant, version_id, action)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:  # noqa: BLE001
        print(f"Budget transition status error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


@budget_bp.route("/api/budget/versions/<int:version_id>/activate", methods=["PUT"])
@cognito_required(required_permissions=["finance_write"])
@tenant_required()
def budget_activate_version(
    user_email, user_roles, tenant, user_tenants, version_id
) -> ResponseReturnValue:
    """Toggle the active flag on a budget version."""
    try:
        data = request.get_json()
        # Default to activate if no body or no 'active' key provided
        active = True
        if data and "active" in data:
            active = bool(data["active"])

        result = budget_service.activate_version(tenant, version_id, active=active)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:  # noqa: BLE001
        print(f"Budget activate version error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


@budget_bp.route("/api/budget/versions/<int:version_id>", methods=["DELETE"])
@cognito_required(required_permissions=["finance_write"])
@tenant_required()
def budget_delete_version(
    user_email, user_roles, tenant, user_tenants, version_id
) -> ResponseReturnValue:
    """Delete a draft budget version."""
    try:
        result = budget_service.delete_version(tenant, version_id)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:  # noqa: BLE001
        print(f"Budget delete version error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# Budget Line Routes
# =============================================================================


@budget_bp.route("/api/budget/versions/<int:version_id>/lines", methods=["GET"])
@cognito_required(required_permissions=["finance_read"])
@tenant_required()
def budget_list_lines(
    user_email, user_roles, tenant, user_tenants, version_id
) -> ResponseReturnValue:
    """List all budget lines for a specific version."""
    try:
        result = budget_service.list_lines(tenant, version_id)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:  # noqa: BLE001
        print(f"Budget list lines error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


@budget_bp.route("/api/budget/versions/<int:version_id>/lines", methods=["POST"])
@cognito_required(required_permissions=["finance_write"])
@tenant_required()
def budget_create_line(
    user_email, user_roles, tenant, user_tenants, version_id
) -> ResponseReturnValue:
    """Create a new budget line for a specific version."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        account_code = data.get("account_code")
        period_mode = data.get("period_mode")

        # Validate required fields
        if not account_code:
            return jsonify({"success": False, "error": "account_code is required"}), 400
        if not period_mode:
            return jsonify({"success": False, "error": "period_mode is required"}), 400
        if period_mode not in ("Monthly", "Annual"):
            return jsonify(
                {"success": False, "error": "period_mode must be 'Monthly' or 'Annual'"}
            ), 400

        # Validate based on period mode
        amounts = None
        annual_amount = None

        if period_mode == "Monthly":
            amounts = data.get("amounts")
            if amounts is None:
                return jsonify(
                    {
                        "success": False,
                        "error": "amounts is required for Monthly period mode",
                    }
                ), 400
            if not isinstance(amounts, list) or len(amounts) != 12:
                return jsonify(
                    {
                        "success": False,
                        "error": "amounts must be a list of exactly 12 numbers",
                    }
                ), 400
            # Validate each amount is numeric
            for i, amt in enumerate(amounts):
                if not isinstance(amt, (int, float)):
                    return jsonify(
                        {"success": False, "error": f"amounts[{i}] must be a number"}
                    ), 400
        elif period_mode == "Annual":
            annual_amount = data.get("annual_amount")
            if annual_amount is None:
                return jsonify(
                    {
                        "success": False,
                        "error": "annual_amount is required for Annual period mode",
                    }
                ), 400
            if not isinstance(annual_amount, (int, float)):
                return jsonify(
                    {"success": False, "error": "annual_amount must be a number"}
                ), 400

        detail_dimension_type = data.get("detail_dimension_type")
        detail_dimension_value = data.get("detail_dimension_value")
        notes = data.get("notes")

        result = budget_service.create_line(
            tenant,
            version_id,
            account_code,
            period_mode,
            amounts=amounts,
            annual_amount=annual_amount,
            detail_dimension_type=detail_dimension_type,
            detail_dimension_value=detail_dimension_value,
            notes=notes,
        )

        if result["success"]:
            return jsonify(result), 201
        else:
            return jsonify(result), 400
    except Exception as e:  # noqa: BLE001
        print(f"Budget create line error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


@budget_bp.route("/api/budget/lines/<int:line_id>", methods=["PUT"])
@cognito_required(required_permissions=["finance_write"])
@tenant_required()
def budget_update_line(
    user_email, user_roles, tenant, user_tenants, line_id
) -> ResponseReturnValue:
    """Update a budget line's amounts."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        amounts = data.get("amounts")
        annual_amount = data.get("annual_amount")

        result = budget_service.update_line(
            tenant, line_id, amounts=amounts, annual_amount=annual_amount
        )

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:  # noqa: BLE001
        print(f"Budget update line error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


@budget_bp.route("/api/budget/lines/<int:line_id>", methods=["DELETE"])
@cognito_required(required_permissions=["finance_write"])
@tenant_required()
def budget_delete_line(
    user_email, user_roles, tenant, user_tenants, line_id
) -> ResponseReturnValue:
    """Delete a budget line."""
    try:
        result = budget_service.delete_line(tenant, line_id)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:  # noqa: BLE001
        print(f"Budget delete line error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# Dashboard Route
# =============================================================================


@budget_bp.route("/api/budget/dashboard", methods=["GET"])
@cognito_required(required_permissions=["finance_read"])
@tenant_required()
def budget_dashboard(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Get budget vs actuals dashboard data."""
    try:
        version_id = request.args.get("version_id")
        year = request.args.get("year")

        # Parse version_id if provided
        parsed_version_id = None
        if version_id:
            try:
                parsed_version_id = int(version_id)
            except ValueError:
                return jsonify(
                    {"success": False, "error": "version_id must be a number"}
                ), 400

        # Parse year if provided (legacy support)
        parsed_year = None
        if year:
            try:
                parsed_year = int(year)
            except ValueError:
                return jsonify(
                    {"success": False, "error": "year must be a number"}
                ), 400

        if not parsed_version_id and not parsed_year:
            return jsonify(
                {
                    "success": False,
                    "error": "Either version_id or year parameter is required",
                }
            ), 400

        level = request.args.get("level", "parent")
        period = request.args.get("period", "ytd")
        parent_code = request.args.get("parent_code")
        subparent_code = request.args.get("subparent_code")
        reference_number = request.args.get("reference_number")

        result = budget_service.get_dashboard(
            tenant,
            level,
            period,
            version_id=parsed_version_id,
            year=parsed_year,
            parent_code=parent_code,
            subparent_code=subparent_code,
            reference_number=reference_number,
        )

        # Dashboard always returns 200 (even with notification about missing version)
        if result.get("success"):
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:  # noqa: BLE001
        print(f"Budget dashboard error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500
