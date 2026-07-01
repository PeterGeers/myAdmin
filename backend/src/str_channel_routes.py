"""
STR Channel Revenue Routes
Handles monthly STR channel revenue calculations based on account 1600 transactions
"""

import logging
from flask import Blueprint, request, jsonify
from datetime import datetime
import calendar
from database import DatabaseManager
from dialect_helpers import dialect
from services.tax_rate_service import TaxRateService
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.function_guard import function_guard

logger = logging.getLogger(__name__)

str_channel_bp = Blueprint("str_channel", __name__)


@str_channel_bp.route("/calculate", methods=["POST"])
@cognito_required(required_permissions=["str_read"])
@tenant_required()
@function_guard("str_channel_revenue", "STR")
def calculate_str_channel_revenue(user_email, user_roles, tenant, user_tenants):
    """Calculate STR channel revenue for a specific month and year"""
    try:
        data = request.get_json()
        year = data.get("year", datetime.now().year)
        month = data.get("month", datetime.now().month)
        administration = data.get("administration", tenant)  # Default to current tenant
        test_mode = data.get("test_mode", True)

        # Validate user has access to requested administration
        if administration not in user_tenants:
            return jsonify(
                {"success": False, "error": "Access denied to administration"}
            ), 403

        # Calculate last day of month
        last_day = calendar.monthrange(year, month)[1]
        end_date = f"{year}-{month:02d}-{last_day}"

        # Reference number for transactions
        ref1 = f"BnB {year}{month:02d}"

        # Pattern for STR channels
        pattern = "AirBnB|Booking.com|dfDirect|Stripe|VRBO"

        # Get database connection
        db = DatabaseManager(test_mode=test_mode)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Query to get channel revenue data - EXACT match on administration
        query = """
        SELECT 
            administration,
            CASE 
                WHEN ReferenceNumber LIKE '%AIRBNB%' THEN 'AirBnB'
                ELSE ReferenceNumber
            END as ReferenceNumber,
            Reknum,
            SUM(Amount) as TransactionAmount
        FROM vw_mutaties 
        WHERE TransactionDate <= %s
        AND administration = %s
        AND Reknum LIKE '1600%'
        AND (ReferenceNumber REGEXP %s)
        GROUP BY administration, 
                 CASE 
                     WHEN ReferenceNumber LIKE '%AIRBNB%' THEN 'AirBnB'
                     ELSE ReferenceNumber
                 END,
                 Reknum
        HAVING ABS(SUM(Amount)) > 0.01
        """

        cursor.execute(query, (end_date, administration, pattern))
        channel_data = cursor.fetchall()

        # Resolve STR revenue account from rekeningschema.parameters
        str_revenue_query = f"""
            SELECT Account FROM rekeningschema
            WHERE administration = %s
              AND {dialect.json_extract("parameters", "$.str_revenue_account")} = true
            ORDER BY Account LIMIT 1
        """
        cursor.execute(str_revenue_query, (administration,))
        str_revenue_rows = cursor.fetchall()

        if not str_revenue_rows:
            cursor.close()
            conn.close()
            return jsonify(
                {
                    "success": False,
                    "error": "No STR revenue account configured. "
                    "Set $.str_revenue_account flag in rekeningschema.",
                }
            ), 400

        str_revenue_account = str_revenue_rows[0]["Account"]

        # Resolve VAT rate and account from TaxRateService
        # btw_accommodation rates are stored with tax_type='btw_accommodation'
        # and tax_code='high' or 'low' depending on the effective date.
        # We query all active btw_accommodation codes and pick the one valid for this date.
        transaction_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        tax_svc = TaxRateService(db)

        # Try btw_accommodation codes (high, low) for the transaction date
        rate_info = None
        for code in ("high", "low"):
            rate_info = tax_svc.get_tax_rate(
                administration, "btw_accommodation", code, transaction_date
            )
            if rate_info:
                break

        # Fallback: try legacy format (btw / accommodation)
        if not rate_info:
            rate_info = tax_svc.get_tax_rate(
                administration, "btw", "accommodation", transaction_date
            )

        if not rate_info:
            cursor.close()
            conn.close()
            return jsonify(
                {
                    "success": False,
                    "error": f"No BTW accommodation rate configured for {end_date}",
                }
            ), 400

        vat_rate = rate_info["rate"]
        vat_base = 100.0 + vat_rate
        vat_account = rate_info["ledger_account"]

        # Process the data to create transactions
        transactions = []

        for row in channel_data:
            amount = round(float(row["TransactionAmount"]) * -1, 2)  # Reverse sign
            if amount == 0:
                continue

            # Main revenue transaction
            revenue_transaction = {
                "TransactionDate": end_date,
                "TransactionNumber": f"{row['ReferenceNumber']} {end_date}",
                "TransactionDescription": f"{row['ReferenceNumber']} omzet {end_date}",
                "TransactionAmount": amount,
                "Debet": row["Reknum"],
                "Credit": str_revenue_account,
                "ReferenceNumber": row["ReferenceNumber"],
                "Ref1": ref1,
                "Ref2": "",
                "Ref3": "",
                "Ref4": "",
                "Administration": row["administration"],
            }
            transactions.append(revenue_transaction)

            # VAT transaction using resolved rate and account
            vat_amount = round((amount / vat_base) * vat_rate, 2)
            vat_transaction = {
                "TransactionDate": end_date,
                "TransactionNumber": f"{row['ReferenceNumber']} {end_date}",
                "TransactionDescription": f"{row['ReferenceNumber']} Btw {end_date}",
                "TransactionAmount": vat_amount,
                "Debet": str_revenue_account,
                "Credit": vat_account,
                "ReferenceNumber": row["ReferenceNumber"],
                "Ref1": ref1,
                "Ref2": "",
                "Ref3": "",
                "Ref4": "",
                "Administration": row["administration"],
            }
            transactions.append(vat_transaction)

        cursor.close()
        conn.close()

        return jsonify(
            {
                "success": True,
                "transactions": transactions,
                "summary": {
                    "year": year,
                    "month": month,
                    "administration": administration,
                    "end_date": end_date,
                    "ref1": ref1,
                    "transaction_count": len(transactions),
                },
            }
        )

    except Exception as e:
        logging.error(f"Error calculating STR channel revenue: {str(e)}")
        logger.error(f"Error in endpoint: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@str_channel_bp.route("/save", methods=["POST"])
@cognito_required(required_permissions=["bookings_create"])
@tenant_required()
@function_guard("str_channel_revenue", "STR")
def save_str_channel_transactions(user_email, user_roles, tenant, user_tenants):
    """Save STR channel revenue transactions to database"""
    try:
        data = request.get_json()
        transactions = data.get("transactions", [])
        test_mode = data.get("test_mode", True)

        if not transactions:
            return jsonify({"success": False, "error": "No transactions to save"}), 400

        # Validate all transactions Administration field is in user_tenants
        for i, transaction in enumerate(transactions):
            administration = transaction.get("Administration") or transaction.get(
                "administration"
            )
            if not administration:
                return jsonify(
                    {
                        "success": False,
                        "error": f"Transaction {i + 1} missing Administration field",
                    }
                ), 400

            if administration not in user_tenants:
                return jsonify(
                    {
                        "success": False,
                        "error": f"Access denied to administration: {administration}",
                    }
                ), 403

        # Get database connection and determine correct table
        db = DatabaseManager(test_mode=test_mode)

        # Use mutaties table in both test and production databases
        # Test mode uses testfinance.mutaties, production uses finance.mutaties
        table_name = "mutaties"

        conn = db.get_connection()
        cursor = conn.cursor()

        # Insert transactions
        insert_query = f"""
        INSERT INTO {table_name} 
        (TransactionDate, TransactionNumber, TransactionDescription, TransactionAmount,
         Debet, Credit, ReferenceNumber, Ref1, Ref2, Ref3, Ref4, Administration)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        saved_count = 0
        for transaction in transactions:
            cursor.execute(
                insert_query,
                (
                    transaction["TransactionDate"],
                    transaction["TransactionNumber"],
                    transaction["TransactionDescription"],
                    transaction["TransactionAmount"],
                    transaction["Debet"],
                    transaction["Credit"],
                    transaction["ReferenceNumber"],
                    transaction["Ref1"],
                    transaction["Ref2"],
                    transaction["Ref3"],
                    transaction["Ref4"],
                    transaction["Administration"],
                ),
            )
            saved_count += 1

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(
            {"success": True, "saved_count": saved_count, "table": table_name}
        )

    except Exception as e:
        logging.error(f"Error saving STR channel transactions: {str(e)}")
        logger.error(f"Error in endpoint: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@str_channel_bp.route("/preview", methods=["GET"])
@cognito_required(required_permissions=["str_read"])
@tenant_required()
@function_guard("str_channel_revenue", "STR")
def preview_str_channel_data(user_email, user_roles, tenant, user_tenants):
    """Preview STR channel data for a specific month"""
    try:
        year = int(request.args.get("year", datetime.now().year))
        month = int(request.args.get("month", datetime.now().month))
        administration = request.args.get(
            "administration", tenant
        )  # Default to current tenant
        test_mode = request.args.get("test_mode", "true").lower() == "true"

        # Validate user has access to requested administration
        if administration not in user_tenants:
            return jsonify(
                {"success": False, "error": "Access denied to administration"}
            ), 403

        # Calculate last day of month
        last_day = calendar.monthrange(year, month)[1]
        end_date = f"{year}-{month:02d}-{last_day}"

        # Pattern for STR channels
        pattern = "AirBnB|Booking.com|dfDirect|Stripe|VRBO"

        # Get database connection
        db = DatabaseManager(test_mode=test_mode)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)

        # Query to get raw channel data - EXACT match on administration
        query = """
        SELECT 
            administration,
            ReferenceNumber,
            Reknum,
            COUNT(*) as transaction_count,
            SUM(Amount) as total_amount,
            MIN(TransactionDate) as first_date,
            MAX(TransactionDate) as last_date
        FROM vw_mutaties 
        WHERE TransactionDate <= %s
        AND administration = %s
        AND Reknum LIKE '1600%'
        AND (ReferenceNumber REGEXP %s)
        GROUP BY administration, ReferenceNumber, Reknum
        HAVING ABS(SUM(Amount)) > 0.01
        ORDER BY administration, ReferenceNumber
        """

        cursor.execute(query, (end_date, administration, pattern))
        preview_data = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify(
            {
                "success": True,
                "preview_data": preview_data,
                "summary": {
                    "year": year,
                    "month": month,
                    "administration": administration,
                    "end_date": end_date,
                    "channels_found": len(preview_data),
                },
            }
        )

    except Exception as e:
        logging.error(f"Error previewing STR channel data: {str(e)}")
        logger.error(f"Error in endpoint: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500
