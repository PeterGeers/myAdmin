"""Financial reporting endpoints for balance data, trends, and reference analysis.

Extracted from reporting_routes.py for file size management.
All endpoints are prefixed with /api/reports via blueprint registration.
"""

from flask import Blueprint, request, jsonify
from flask.typing import ResponseReturnValue
from database import DatabaseManager
from datetime import datetime
from contextlib import contextmanager
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required

financial_reporting_bp = Blueprint("financial_reporting", __name__)

# Global variables set by app.py
flag = False
logger = None


def set_test_mode(test_mode) -> None:
    """Set test mode flag"""
    global flag
    flag = test_mode


def set_logger(log_instance) -> None:
    """Set logger instance"""
    global logger
    logger = log_instance


class FinancialReportingService:
    """Service class for financial reporting database operations."""

    def __init__(self, test_mode=False) -> None:
        self.db = DatabaseManager(test_mode=test_mode)
        self.table_name = "mutaties_test" if test_mode else "mutaties"

    @contextmanager
    def get_cursor(self):
        """Context manager for database operations"""
        connection = self.db.get_connection()
        cursor = connection.cursor(dictionary=True)
        try:
            yield cursor
        finally:
            cursor.close()
            connection.close()

    def build_where_clause(self, conditions) -> tuple:
        """Build WHERE clause from conditions dict"""
        where_parts = []
        params = []

        for key, value in conditions.items():
            if value == "all" or not value:
                continue

            if key == "date_range":
                if value.get("from") and value.get("to"):
                    where_parts.append("TransactionDate BETWEEN %s AND %s")
                    params.extend([value["from"], value["to"]])
                elif value.get("to"):
                    where_parts.append("TransactionDate <= %s")
                    params.append(value["to"])
            elif key == "years":
                if isinstance(value, list) and value:
                    placeholders = ",".join(["%s"] * len(value))
                    where_parts.append(f"jaar IN ({placeholders})")
                    params.extend(value)
            elif key == "administration":
                where_parts.append("administration = %s")
                params.append(value)
            elif key == "profit_loss":
                where_parts.append("VW = %s")
                params.append(value)

        return " AND ".join(where_parts) if where_parts else "1=1", params


@financial_reporting_bp.route("/balance-data", methods=["GET"])
@cognito_required(required_permissions=["reports_read"])
@tenant_required()
def get_balance_data(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Get balance data grouped by Parent and ledger with tenant filtering"""
    try:
        service = FinancialReportingService(
            request.args.get("testMode", "false").lower() == "true"
        )

        # Get administration parameter, default to current tenant
        administration = request.args.get("administration", tenant)

        # Validate user has access to requested administration
        if administration != "all" and administration not in user_tenants:
            return jsonify(
                {"success": False, "error": "Access denied to administration"}
            ), 403

        # If 'all' is requested, filter by user_tenants
        if administration == "all":
            # Build WHERE clause with tenant filtering
            where_parts = []
            params = []

            # Date range
            date_from = request.args.get("dateFrom")
            date_to = request.args.get("dateTo", datetime.now().strftime("%Y-%m-%d"))
            if date_from:
                where_parts.append("TransactionDate BETWEEN %s AND %s")
                params.extend([date_from, date_to])
            else:
                where_parts.append("TransactionDate <= %s")
                params.append(date_to)

            # Tenant filtering - only show data from user's accessible tenants
            placeholders = ",".join(["%s"] * len(user_tenants))
            where_parts.append(f"administration IN ({placeholders})")
            params.extend(user_tenants)

            # Profit/Loss filter
            profit_loss = request.args.get("profitLoss", "all")
            if profit_loss != "all":
                where_parts.append("VW = %s")
                params.append(profit_loss)

            where_clause = " AND ".join(where_parts)
        else:
            # Single administration requested
            conditions = {
                "date_range": {
                    "from": request.args.get("dateFrom"),
                    "to": request.args.get(
                        "dateTo", datetime.now().strftime("%Y-%m-%d")
                    ),
                },
                "administration": administration,
                "profit_loss": request.args.get("profitLoss", "all"),
            }

            where_clause, params = service.build_where_clause(conditions)

        with service.get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT Parent, ledger, SUM(Amount) as total_amount
                FROM vw_mutaties
                WHERE {where_clause}
                GROUP BY Parent, ledger
                ORDER BY Parent, ledger
            """,
                params,
            )
            results = cursor.fetchall()

        return jsonify({"success": True, "data": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@financial_reporting_bp.route("/trends-data", methods=["GET"])
@cognito_required(required_permissions=["reports_read"])
@tenant_required()
def get_trends_data(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Get P&L trends data by year"""
    try:
        service = FinancialReportingService(
            request.args.get("testMode", "false").lower() == "true"
        )

        years = [
            int(y)
            for y in request.args.get("years", str(datetime.now().year)).split(",")
            if y
        ]

        # Get administration parameter, default to current tenant
        administration = request.args.get("administration", tenant)

        # Validate user has access to requested administration
        if administration not in user_tenants:
            return jsonify(
                {"success": False, "error": "Access denied to administration"}
            ), 403

        conditions = {
            "years": years,
            "administration": administration,
            "profit_loss": request.args.get("profitLoss", "Y"),
        }

        where_clause, params = service.build_where_clause(conditions)

        with service.get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT Parent, ledger, jaar as year, SUM(Amount) as total_amount
                FROM vw_mutaties
                WHERE {where_clause}
                GROUP BY Parent, ledger, jaar
                ORDER BY Parent, ledger, jaar
            """,
                params,
            )
            results = cursor.fetchall()

        return jsonify({"success": True, "data": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@financial_reporting_bp.route("/reference-analysis", methods=["GET"])
@cognito_required(required_permissions=["reports_read"])
@tenant_required()
def get_reference_analysis(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Get reference analysis data with trend and available accounts - filtered by user tenants"""
    try:
        service = FinancialReportingService()
        years = [
            y
            for y in request.args.get("years", str(datetime.now().year)).split(",")
            if y
        ]
        reference_number = request.args.get("reference_number", "")
        accounts = [a for a in request.args.get("accounts", "").split(",") if a]

        # Get administration parameter, default to current tenant
        administration = request.args.get("administration", tenant)

        # Validate user has access to requested administration
        if administration != "all" and administration not in user_tenants:
            return jsonify(
                {"success": False, "error": "Access denied to administration"}
            ), 403

        with service.get_cursor() as cursor:
            # Get available accounts with tenant filtering
            account_conditions = {
                "years": years,
                "administration": administration if administration != "all" else None,
            }
            account_where, account_params = service.build_where_clause(
                account_conditions
            )

            # Add tenant filtering for 'all' case
            if administration == "all":
                placeholders = ",".join(["%s"] * len(user_tenants))
                if account_where == "1=1":
                    account_where = f"administration IN ({placeholders})"
                else:
                    account_where += f" AND administration IN ({placeholders})"
                account_params.extend(user_tenants)

            # Get available accounts from vw_mutaties (already has Reknum and AccountName)
            account_where_view = account_where

            cursor.execute(
                f"""
                SELECT DISTINCT Reknum, AccountName
                FROM vw_mutaties
                WHERE {account_where_view} AND Reknum IS NOT NULL AND Reknum != ''
                      AND AccountName IS NOT NULL AND AccountName != ''
                ORDER BY Reknum
            """,
                account_params,
            )
            available_accounts = cursor.fetchall()

            transactions = []
            trend_data = []

            if reference_number:
                conditions = {
                    "years": years,
                    "administration": administration
                    if administration != "all"
                    else None,
                }
                where_clause, params = service.build_where_clause(conditions)

                # Add tenant filtering for 'all' case
                if administration == "all":
                    placeholders = ",".join(["%s"] * len(user_tenants))
                    if where_clause == "1=1":
                        where_clause = f"administration IN ({placeholders})"
                    else:
                        where_clause += f" AND administration IN ({placeholders})"
                    params.extend(user_tenants)

                # Add reference pattern and accounts
                where_clause += " AND ReferenceNumber REGEXP %s"
                params.append(reference_number)

                if accounts:
                    placeholders = ",".join(["%s"] * len(accounts))
                    where_clause += f" AND Reknum IN ({placeholders})"
                    params.extend(accounts)

                # Get transactions
                cursor.execute(
                    f"""
                    SELECT TransactionDate, TransactionDescription, Amount, Reknum,
                           AccountName, ReferenceNumber, Administration
                    FROM vw_mutaties
                    WHERE {where_clause}
                    ORDER BY TransactionDate DESC
                """,
                    params,
                )
                transactions = cursor.fetchall()

                # Get trend data
                cursor.execute(
                    f"""
                    SELECT jaar, kwartaal, SUM(Amount) as total_amount
                    FROM vw_mutaties
                    WHERE {where_clause}
                    GROUP BY jaar, kwartaal
                    ORDER BY jaar, kwartaal
                """,
                    params,
                )
                trend_data = cursor.fetchall()

        return jsonify(
            {
                "success": True,
                "transactions": transactions,
                "trend_data": trend_data,
                "available_accounts": available_accounts,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
