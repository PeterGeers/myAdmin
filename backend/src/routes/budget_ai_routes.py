"""
Budget AI & Copy Routes Blueprint

Extracted from budget_routes.py to keep file sizes under 500 lines.
Handles:
- Budget copy (POST /api/budget/copy)
- AI narrative generation (POST /api/budget/ai/narrative)
- AI natural language query (POST /api/budget/ai/query)
- AI draft adjustment suggestions (POST /api/budget/ai/draft-suggestions)
- AI budget line generation (POST /api/budget/ai/generate-lines)
"""

import logging

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.budget_ai_service import BudgetAIService
from services.budget_service import BudgetService

logger = logging.getLogger(__name__)

# Create blueprint
budget_ai_bp = Blueprint("budget_ai", __name__)

# Service instances (will be set by set_test_mode)
budget_service = None
budget_ai_service = None


def set_test_mode(test_mode: bool) -> None:
    """Set test mode for budget AI/copy services"""
    global budget_service, budget_ai_service
    budget_service = BudgetService(test_mode=test_mode)
    budget_ai_service = BudgetAIService(
        db=budget_service.db if budget_service else None
    )


# =============================================================================
# Copy Route
# =============================================================================


@budget_ai_bp.route("/api/budget/copy", methods=["POST"])
@cognito_required(required_permissions=["finance_write"])
@tenant_required()
def budget_copy(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Copy a budget version to a new fiscal year."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        source_version_id = data.get("source_version_id")
        target_fiscal_year = data.get("target_fiscal_year")
        version_name = data.get("version_name")

        # Validate required fields
        if source_version_id is None:
            return jsonify(
                {"success": False, "error": "source_version_id is required"}
            ), 400
        if not isinstance(source_version_id, int):
            return jsonify(
                {"success": False, "error": "source_version_id must be an integer"}
            ), 400

        if target_fiscal_year is None:
            return jsonify(
                {"success": False, "error": "target_fiscal_year is required"}
            ), 400
        if (
            not isinstance(target_fiscal_year, int)
            or target_fiscal_year < 1000
            or target_fiscal_year > 9999
        ):
            return jsonify(
                {
                    "success": False,
                    "error": "target_fiscal_year must be a 4-digit integer",
                }
            ), 400

        if not version_name:
            return jsonify({"success": False, "error": "version_name is required"}), 400
        if len(version_name) > 100:
            return jsonify(
                {
                    "success": False,
                    "error": "version_name must be 100 characters or fewer",
                }
            ), 400

        result = budget_service.copy_budget(
            tenant, source_version_id, target_fiscal_year, version_name
        )

        if result["success"]:
            return jsonify(result), 201
        else:
            return jsonify(result), 400
    except Exception as e:
        print(f"Budget copy error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# AI Routes
# =============================================================================


@budget_ai_bp.route("/api/budget/ai/narrative", methods=["POST"])
@cognito_required(required_permissions=["finance_write"])
@tenant_required()
def budget_ai_narrative(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Generate an AI-powered executive narrative from budget vs actuals data."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        year = data.get("year")
        if not year or not isinstance(year, int):
            return jsonify(
                {"success": False, "error": "year is required and must be an integer"}
            ), 400

        level = data.get("level", "parent")
        period = data.get("period", "ytd")

        # Get dashboard data to feed to the AI
        dashboard_result = budget_service.get_dashboard(
            tenant, level, period, year=year
        )

        if not dashboard_result.get("success"):
            return jsonify(dashboard_result), 400

        # Generate narrative from dashboard data
        result = budget_ai_service.generate_narrative(
            dashboard_data=dashboard_result.get("data", {}),
            period=period,
            year=year,
            administration=tenant,
        )

        if result.get("success"):
            return jsonify(result)
        else:
            # Graceful degradation — return 200 even on AI failure
            return jsonify(result)
    except Exception as e:
        print(f"Budget AI narrative error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


@budget_ai_bp.route("/api/budget/ai/query", methods=["POST"])
@cognito_required(required_permissions=["finance_write"])
@tenant_required()
def budget_ai_query(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Translate a natural language question into dashboard parameters via AI."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        question = data.get("question")
        year = data.get("year")

        if not question or not isinstance(question, str):
            return jsonify(
                {"success": False, "error": "question is required and must be a string"}
            ), 400
        if not year or not isinstance(year, int):
            return jsonify(
                {"success": False, "error": "year is required and must be an integer"}
            ), 400

        # Get hierarchy context for the AI (parent-level rollup for account names)
        rollup_result = budget_service.get_rollup(tenant, 0, "parent")
        hierarchy_context = []
        if rollup_result.get("success"):
            hierarchy_context = [
                {"code": row.get("code", ""), "name": row.get("name", "")}
                for row in rollup_result.get("data", [])
            ]

        # If no rollup data, try to get account names from chart of accounts
        if not hierarchy_context:
            try:
                accounts = budget_service.db.execute_query(
                    "SELECT DISTINCT Account AS code, AccountName AS name "
                    "FROM rekeningschema WHERE administration = %s "
                    "ORDER BY Account",
                    (tenant,),
                )
                if accounts:
                    hierarchy_context = [
                        {"code": a["code"], "name": a["name"]} for a in accounts[:100]
                    ]
            except Exception as exc:
                # Hierarchy context is optional enrichment; the AI query proceeds
                # without it if the lookup fails.
                logger.debug("Could not load hierarchy context for AI query: %s", exc)

        # Translate query via AI
        result = budget_ai_service.translate_query(
            question=question,
            year=year,
            hierarchy_context=hierarchy_context,
            administration=tenant,
        )

        if not result.get("success"):
            # Graceful degradation — return 200 even on AI failure
            return jsonify(result)

        # If AI returned interpreted params, optionally execute the query
        ai_data = result.get("data", {})
        interpreted_params = ai_data.get("interpreted_params", {})

        # Execute the interpreted dashboard query
        query_year = interpreted_params.get("year", year)
        query_level = interpreted_params.get("level", "parent")
        query_period = interpreted_params.get("period", "ytd")
        query_parent_code = interpreted_params.get("parent_code")
        query_subparent_code = interpreted_params.get("subparent_code")
        query_reference_number = interpreted_params.get("reference_number")

        dashboard_result = budget_service.get_dashboard(
            tenant,
            query_level,
            query_period,
            year=query_year,
            parent_code=query_parent_code,
            subparent_code=query_subparent_code,
            reference_number=query_reference_number,
        )

        # Combine AI interpretation with dashboard results
        response_data = {
            "interpreted_params": interpreted_params,
            "filter_description": ai_data.get("filter_description", ""),
            "results": dashboard_result.get("data", {}).get("rows", [])
            if dashboard_result.get("success")
            else [],
            "model_used": ai_data.get("model_used"),
            "tokens_used": ai_data.get("tokens_used", 0),
        }

        return jsonify({"success": True, "data": response_data})
    except Exception as e:
        print(f"Budget AI query error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


@budget_ai_bp.route("/api/budget/ai/draft-suggestions", methods=["POST"])
@cognito_required(required_permissions=["finance_write"])
@tenant_required()
def budget_ai_draft_suggestions(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Get AI-powered adjustment suggestions for a draft budget version."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        version_id = data.get("version_id")
        if not version_id or not isinstance(version_id, int):
            return jsonify(
                {
                    "success": False,
                    "error": "version_id is required and must be an integer",
                }
            ), 400

        context_notes = data.get("context_notes", "")
        scope = data.get("scope", {})

        # Get budget lines for the version
        lines_result = budget_service.list_lines(tenant, version_id)
        if not lines_result.get("success"):
            return jsonify(lines_result), 400

        budget_lines = lines_result.get("data", [])

        # Apply scope filter if parent_code provided
        if scope and scope.get("parent_code"):
            parent_code = scope["parent_code"]
            # Get accounts under this parent
            try:
                child_accounts = budget_service.db.execute_query(
                    "SELECT Account FROM rekeningschema "
                    "WHERE administration = %s AND Parent = %s",
                    (tenant, parent_code),
                )
                if child_accounts:
                    valid_accounts = {a["Account"] for a in child_accounts}
                    budget_lines = [
                        line
                        for line in budget_lines
                        if line.get("account_code") in valid_accounts
                    ]
            except Exception as exc:
                # Account filtering is best-effort; fall back to the unfiltered
                # budget lines if the lookup fails.
                logger.debug("Could not filter budget lines by account: %s", exc)

        # Enrich lines with account names
        if budget_lines:
            account_codes = list(
                {line.get("account_code", "") for line in budget_lines}
            )
            try:
                if account_codes:
                    placeholders = ", ".join(["%s"] * len(account_codes))
                    names = budget_service.db.execute_query(
                        f"SELECT Account, AccountName FROM rekeningschema "
                        f"WHERE administration = %s AND Account IN ({placeholders})",
                        (tenant, *account_codes),
                    )
                    name_map = {n["Account"]: n["AccountName"] for n in (names or [])}
                    for line in budget_lines:
                        line["account_name"] = name_map.get(
                            line.get("account_code", ""), ""
                        )
            except Exception as exc:
                # Account-name enrichment is cosmetic; lines are usable without it.
                logger.debug("Could not enrich budget lines with names: %s", exc)

        # Check payload limit
        if len(budget_lines) > 100:
            return jsonify(
                {
                    "success": False,
                    "error": "Too many budget lines for AI analysis. Select a subset (max 100 lines).",
                }
            ), 400

        # Get AI suggestions
        result = budget_ai_service.suggest_adjustments(
            budget_lines=budget_lines,
            context_notes=context_notes,
            administration=tenant,
        )

        if result.get("success"):
            return jsonify(result)
        else:
            # Graceful degradation — return 200 even on AI failure
            return jsonify(result)
    except Exception as e:
        print(f"Budget AI draft suggestions error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


# =============================================================================
# AI Generate Lines Route (replaces template-based draft generation)
# =============================================================================


@budget_ai_bp.route("/api/budget/ai/generate-lines", methods=["POST"])
@cognito_required(required_permissions=["finance_write"])
@tenant_required()
def budget_ai_generate_lines(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """AI-powered budget line generation from prior-year actuals and context notes."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request body is required"}), 400

        fiscal_year = data.get("fiscal_year")
        if not fiscal_year or not isinstance(fiscal_year, int):
            return jsonify(
                {
                    "success": False,
                    "error": "fiscal_year is required and must be an integer",
                }
            ), 400

        context_notes = data.get("context_notes", "")

        # Get chart of accounts for tenant
        chart_of_accounts = []
        try:
            accounts = budget_service.db.execute_query(
                "SELECT DISTINCT Account AS account_code, AccountName AS account_name "
                "FROM rekeningschema WHERE administration = %s ORDER BY Account",
                (tenant,),
            )
            chart_of_accounts = accounts if accounts else []
        except Exception as exc:
            # Chart of accounts is optional context for line generation.
            logger.debug("Could not load chart of accounts for AI: %s", exc)

        # Get prior-year actuals summary
        prior_year = fiscal_year - 1
        prior_actuals = []
        try:
            actuals = budget_service.db.execute_query(
                """SELECT Reknum AS account_code, maand, SUM(Amount) AS amount
                   FROM vw_mutaties
                   WHERE administration = %s AND jaar = %s
                   GROUP BY Reknum, maand
                   ORDER BY Reknum, maand""",
                (tenant, prior_year),
            )
            prior_actuals = actuals if actuals else []
        except Exception as exc:
            # Prior-year actuals are optional context for line generation.
            logger.debug("Could not load prior-year actuals for AI: %s", exc)

        # Call AI to generate proposed lines
        result = budget_ai_service.generate_lines(
            chart_of_accounts=chart_of_accounts,
            prior_actuals=prior_actuals,
            fiscal_year=fiscal_year,
            context_notes=context_notes,
            administration=tenant,
        )

        if result.get("success"):
            return jsonify(result)
        else:
            return jsonify(result)
    except Exception as e:
        print(f"Budget AI generate lines error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500
