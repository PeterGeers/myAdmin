"""
ZZP Debtor/Creditor Routes

Provides receivables, payables, aging analysis, reminders,
booking account validation, and invoice ledger endpoints.
Split from zzp_routes.py for file size management.

Reference: .kiro/specs/zzp-module/design.md §12 (Debtor Management)
"""

import logging

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from database import DatabaseManager
from dialect_helpers import dialect
from services.module_registry import module_required
from services.parameter_service import ParameterService

logger = logging.getLogger(__name__)

zzp_debtor_bp = Blueprint("zzp_debtor", __name__)

_test_mode = False


def set_test_mode(flag: bool) -> None:
    global _test_mode
    _test_mode = flag


# ── Helpers ──────────────────────────────────────────────────


def _resolve_debtor_account(db, tenant: str) -> str:
    """Resolve the tenant's debtor account code.

    Resolution order:
    1. ParameterService: ``zzp.debtor_account`` for the tenant
    2. Chart of accounts: account flagged with ``zzp_debtor_account = true``
    """
    try:
        param_service = ParameterService(db)
        value = param_service.get_param("zzp", "debtor_account", tenant=tenant)
        if value:
            return value
    except Exception as e:
        logger.debug("ParameterService lookup for debtor_account failed: %s", e)

    # Fallback: look up from chart of accounts (rekeningschema)
    try:
        rows = db.execute_query(
            """SELECT Account FROM rekeningschema
               WHERE administration = %s
                 AND JSON_EXTRACT(parameters, '$.zzp_debtor_account') = true
               LIMIT 1""",
            (tenant,),
        )
        if rows:
            return str(rows[0]["Account"])
    except Exception as e:
        logger.debug("Chart of accounts lookup for debtor_account failed: %s", e)

    logger.warning("No debtor account configured for tenant %s", tenant)
    return "1600"


def _resolve_creditor_account(db, tenant: str) -> str:
    """Resolve the tenant's creditor account code.

    Resolution order:
    1. ParameterService: ``zzp.creditor_account`` for the tenant
    2. Chart of accounts: account flagged with ``zzp_creditor_account = true``
    """
    try:
        param_service = ParameterService(db)
        value = param_service.get_param("zzp", "creditor_account", tenant=tenant)
        if value:
            return value
    except Exception as e:
        logger.debug("ParameterService lookup for creditor_account failed: %s", e)

    # Fallback: look up from chart of accounts (rekeningschema)
    try:
        rows = db.execute_query(
            """SELECT Account FROM rekeningschema
               WHERE administration = %s
                 AND JSON_EXTRACT(parameters, '$.zzp_creditor_account') = true
               LIMIT 1""",
            (tenant,),
        )
        if rows:
            return str(rows[0]["Account"])
    except Exception as e:
        logger.debug("Chart of accounts lookup for creditor_account failed: %s", e)

    logger.warning("No creditor account configured for tenant %s", tenant)
    return "1300"


# ── Debtor/Creditor Endpoints (Req 12) ─────────────────────


@zzp_debtor_bp.route("/api/zzp/debtors/receivables", methods=["GET"])
@cognito_required(required_permissions=["zzp_read"])
@tenant_required()
@module_required("ZZP")
def get_receivables(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Accounts receivable: ledger-balance-driven, grouped by client.

    Computes outstanding balances from the mutaties table using the debtor account
    (typically 1300). Only clients with a positive ledger balance are returned.
    The ledger is the single source of truth — invoices.status is not used to
    determine what is shown as outstanding.
    """
    try:
        db = DatabaseManager(test_mode=_test_mode)

        # Resolve tenant-configurable debtor account for ledger queries
        debtor_account = _resolve_debtor_account(db, tenant)

        # Compute per-client ledger balance on the debtor account.
        # Positive balance = client still owes money.
        ledger_rows = (
            db.execute_query(
                """SELECT ReferenceNumber AS client_id,
                       SUM(CASE WHEN Debet = %s THEN TransactionAmount ELSE 0 END) -
                       SUM(CASE WHEN Credit = %s THEN TransactionAmount ELSE 0 END) AS ledger_balance
                FROM mutaties
                WHERE administration = %s
                GROUP BY ReferenceNumber
                HAVING SUM(CASE WHEN Debet = %s THEN TransactionAmount ELSE 0 END) -
                       SUM(CASE WHEN Credit = %s THEN TransactionAmount ELSE 0 END) > 0""",
                (
                    debtor_account,
                    debtor_account,
                    tenant,
                    debtor_account,
                    debtor_account,
                ),
            )
            or []
        )

        # Build a map of client_id → ledger_balance for clients with positive balance
        balance_by_client = {
            row["client_id"]: float(row["ledger_balance"])
            for row in ledger_rows
            if row.get("client_id")
        }

        # ── Automatic Status Reconciliation (Req 2.4) ──────────────────
        # Update invoices.status to 'paid' for clients that are NOT in the
        # positive-balance list. If a client has no positive ledger balance
        # on the debtor account, their invoices should be marked as paid.
        # Only touches 'sent'/'overdue' invoices — never 'draft' or 'paid'.
        try:
            if balance_by_client:
                placeholders_recon = ", ".join(["%s"] * len(balance_by_client))
                db.execute_query(
                    f"""UPDATE invoices i
                       JOIN contacts c ON i.contact_id = c.id
                       SET i.status = 'paid'
                       WHERE i.administration = %s
                         AND i.status IN ('sent', 'overdue')
                         AND i.invoice_type = 'invoice'
                         AND c.client_id NOT IN ({placeholders_recon})""",
                    (tenant, *balance_by_client.keys()),
                    fetch=False,
                    commit=True,
                )
            else:
                db.execute_query(
                    """UPDATE invoices i
                       SET i.status = 'paid'
                       WHERE i.administration = %s
                         AND i.status IN ('sent', 'overdue')
                         AND i.invoice_type = 'invoice'""",
                    (tenant,),
                    fetch=False,
                    commit=True,
                )
        except Exception as recon_err:
            logger.warning("Status reconciliation failed for %s: %s", tenant, recon_err)

        if not balance_by_client:
            return jsonify({"success": True, "data": [], "total_outstanding": 0.0})
        # to provide display data (invoice numbers, dates, company names)
        placeholders = ", ".join(["%s"] * len(balance_by_client))
        invoice_rows = (
            db.execute_query(
                f"""SELECT i.id, i.invoice_number, i.invoice_date, i.due_date,
                       i.grand_total, i.currency, i.status,
                       c.id as contact_id, c.client_id, c.company_name
                FROM invoices i
                JOIN contacts c ON i.contact_id = c.id
                WHERE i.administration = %s
                  AND c.client_id IN ({placeholders})
                  AND i.status IN ('sent', 'overdue')
                  AND i.invoice_type = 'invoice'
                ORDER BY c.company_name, i.due_date""",
                (tenant, *balance_by_client.keys()),
            )
            or []
        )

        # Group by client, using ledger balance as the total (not grand_total sum)
        grouped = {}
        for row in invoice_rows:
            client_id = row["client_id"]
            if client_id not in grouped:
                grouped[client_id] = {
                    "contact": {
                        "id": row["contact_id"],
                        "client_id": client_id,
                        "company_name": row["company_name"],
                    },
                    "invoices": [],
                    "total": balance_by_client.get(client_id, 0.0),
                }
            grouped[client_id]["invoices"].append(row)

        # Include clients that have ledger balance but no matching invoices
        # (edge case: transactions without invoice records)
        for client_id, balance in balance_by_client.items():
            if client_id not in grouped:
                grouped[client_id] = {
                    "contact": {
                        "id": None,
                        "client_id": client_id,
                        "company_name": client_id,
                    },
                    "invoices": [],
                    "total": balance,
                }

        total_outstanding = round(sum(entry["total"] for entry in grouped.values()), 2)

        return jsonify(
            {
                "success": True,
                "data": list(grouped.values()),
                "total_outstanding": total_outstanding,
            }
        )
    except Exception as e:
        logger.error("get_receivables error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_debtor_bp.route("/api/zzp/debtors/payables", methods=["GET"])
@cognito_required(required_permissions=["zzp_read"])
@tenant_required()
@module_required("ZZP")
def get_payables(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Accounts payable: ledger-balance-driven, grouped by supplier.

    Computes outstanding balances from the mutaties table using the creditor account
    (typically 1300). Only suppliers with a positive ledger balance are returned.
    The ledger is the single source of truth — incoming invoices are booked by the
    FIN invoice processor and payments are recorded via banking.
    """
    try:
        db = DatabaseManager(test_mode=_test_mode)

        # Resolve tenant-configurable creditor account for ledger queries
        creditor_account = _resolve_creditor_account(db, tenant)

        # Compute per-supplier ledger balance on the creditor account.
        # Positive balance (credit > debit) = we still owe the supplier.
        # Negative balance (debit > credit) = overpayment (paid more than booked).
        # Creditor account: credits = invoices booked, debits = payments made.
        ledger_rows = (
            db.execute_query(
                """SELECT ReferenceNumber AS client_id,
                       SUM(CASE WHEN Credit = %s THEN TransactionAmount ELSE 0 END) -
                       SUM(CASE WHEN Debet = %s THEN TransactionAmount ELSE 0 END) AS ledger_balance
                FROM mutaties
                WHERE administration = %s
                GROUP BY ReferenceNumber
                HAVING SUM(CASE WHEN Credit = %s THEN TransactionAmount ELSE 0 END) -
                       SUM(CASE WHEN Debet = %s THEN TransactionAmount ELSE 0 END) != 0""",
                (
                    creditor_account,
                    creditor_account,
                    tenant,
                    creditor_account,
                    creditor_account,
                ),
            )
            or []
        )

        # Build a map of client_id → ledger_balance for suppliers with positive balance
        balance_by_client = {
            row["client_id"]: float(row["ledger_balance"])
            for row in ledger_rows
            if row.get("client_id")
        }

        if not balance_by_client:
            return jsonify({"success": True, "data": [], "total_outstanding": 0.0})

        # Try to enrich with contact details from the contacts table
        placeholders = ", ".join(["%s"] * len(balance_by_client))
        contact_rows = (
            db.execute_query(
                f"""SELECT id, client_id, company_name
                FROM contacts
                WHERE administration = %s
                  AND client_id IN ({placeholders})""",
                (tenant, *balance_by_client.keys()),
            )
            or []
        )

        # Map client_id → contact info
        contact_by_client = {
            row["client_id"]: {
                "id": row["id"],
                "client_id": row["client_id"],
                "company_name": row["company_name"],
            }
            for row in contact_rows
        }

        # Build grouped response
        grouped = {}
        for client_id, balance in balance_by_client.items():
            contact = contact_by_client.get(
                client_id,
                {
                    "id": None,
                    "client_id": client_id,
                    "company_name": client_id,
                },
            )
            grouped[client_id] = {
                "contact": contact,
                "invoices": [],
                "total": balance,
            }

        total_outstanding = round(sum(entry["total"] for entry in grouped.values()), 2)

        return jsonify(
            {
                "success": True,
                "data": list(grouped.values()),
                "total_outstanding": total_outstanding,
            }
        )
    except Exception as e:
        logger.error("get_payables error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_debtor_bp.route("/api/zzp/debtors/aging", methods=["GET"])
@cognito_required(required_permissions=["zzp_read"])
@tenant_required()
@module_required("ZZP")
def get_aging(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """Aging analysis with buckets: current, 1-30, 31-60, 61-90, 90+.

    Only includes invoices for clients with a positive ledger balance on the
    debtor account (consistent with the receivables endpoint).
    """
    try:
        db = DatabaseManager(test_mode=_test_mode)

        # Resolve debtor account to filter by ledger balance
        debtor_account = _resolve_debtor_account(db, tenant)

        # Get clients with positive ledger balance
        ledger_rows = (
            db.execute_query(
                """SELECT ReferenceNumber AS client_id,
                       SUM(CASE WHEN Debet = %s THEN TransactionAmount ELSE 0 END) -
                       SUM(CASE WHEN Credit = %s THEN TransactionAmount ELSE 0 END) AS ledger_balance
                FROM mutaties
                WHERE administration = %s
                GROUP BY ReferenceNumber
                HAVING SUM(CASE WHEN Debet = %s THEN TransactionAmount ELSE 0 END) -
                       SUM(CASE WHEN Credit = %s THEN TransactionAmount ELSE 0 END) > 0""",
                (
                    debtor_account,
                    debtor_account,
                    tenant,
                    debtor_account,
                    debtor_account,
                ),
            )
            or []
        )

        balance_by_client = {
            row["client_id"]: float(row["ledger_balance"])
            for row in ledger_rows
            if row.get("client_id")
        }

        if not balance_by_client:
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "total_outstanding": 0.0,
                        "buckets": {
                            "current": 0.0,
                            "1_30_days": 0.0,
                            "31_60_days": 0.0,
                            "61_90_days": 0.0,
                            "90_plus_days": 0.0,
                        },
                        "by_contact": [],
                    },
                }
            )

        # Fetch invoices only for clients with positive ledger balance
        placeholders = ", ".join(["%s"] * len(balance_by_client))
        rows = (
            db.execute_query(
                f"""SELECT i.id, i.invoice_number, i.due_date, i.grand_total,
                      i.status, {dialect.date_diff(dialect.current_date(), "i.due_date")} as days_overdue,
                      c.id as contact_id, c.client_id, c.company_name
               FROM invoices i
               JOIN contacts c ON i.contact_id = c.id
               WHERE i.administration = %s
                 AND c.client_id IN ({placeholders})
                 AND i.status IN ('sent', 'overdue')
                 AND i.invoice_type = 'invoice'
               ORDER BY c.company_name, i.due_date""",
                (tenant, *balance_by_client.keys()),
            )
            or []
        )

        buckets = {
            "current": 0.0,
            "1_30_days": 0.0,
            "31_60_days": 0.0,
            "61_90_days": 0.0,
            "90_plus_days": 0.0,
        }
        by_contact = {}

        for row in rows:
            days = int(row.get("days_overdue", 0))
            amount = float(row["grand_total"])

            if days <= 0:
                bucket = "current"
            elif days <= 30:
                bucket = "1_30_days"
            elif days <= 60:
                bucket = "31_60_days"
            elif days <= 90:
                bucket = "61_90_days"
            else:
                bucket = "90_plus_days"

            buckets[bucket] += amount
            row["bucket"] = bucket

            cid = row["contact_id"]
            if cid not in by_contact:
                by_contact[cid] = {
                    "contact": {
                        "id": cid,
                        "client_id": row["client_id"],
                        "company_name": row["company_name"],
                    },
                    "total": 0.0,
                    "invoices": [],
                }
            by_contact[cid]["invoices"].append(
                {
                    "invoice_number": row["invoice_number"],
                    "grand_total": amount,
                    "due_date": str(row["due_date"]),
                    "days_overdue": days,
                    "bucket": bucket,
                }
            )
            by_contact[cid]["total"] += amount

        total = round(sum(buckets.values()), 2)
        buckets = {k: round(v, 2) for k, v in buckets.items()}

        return jsonify(
            {
                "success": True,
                "data": {
                    "total_outstanding": total,
                    "buckets": buckets,
                    "by_contact": list(by_contact.values()),
                },
            }
        )
    except Exception as e:
        logger.error("get_aging error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


@zzp_debtor_bp.route(
    "/api/zzp/debtors/send-reminder/<int:invoice_id>", methods=["POST"]
)
@cognito_required(required_permissions=["zzp_crud"])
@tenant_required()
@module_required("ZZP")
def send_reminder(
    user_email, user_roles, tenant, user_tenants, invoice_id
) -> ResponseReturnValue:
    """Send payment reminder for an overdue invoice."""
    try:
        from services.tax_rate_service import TaxRateService
        from services.zzp_invoice_service import ZZPInvoiceService

        db = DatabaseManager(test_mode=_test_mode)
        tax_svc = TaxRateService(db)
        param_svc = ParameterService(db)
        svc = ZZPInvoiceService(
            db=db, tax_rate_service=tax_svc, parameter_service=param_svc
        )

        invoice = svc.get_invoice(tenant, invoice_id)
        if not invoice:
            return jsonify({"success": False, "error": "Invoice not found"}), 404
        if invoice["status"] not in ("sent", "overdue"):
            return jsonify(
                {"success": False, "error": "Can only remind for sent/overdue invoices"}
            ), 400

        from services.contact_service import ContactService
        from services.email_verification_service import EmailVerificationService
        from services.invoice_email_service import InvoiceEmailService
        from services.ses_email_service import SESEmailService

        contact_svc = ContactService(db=db, parameter_service=param_svc)
        ses = SESEmailService()
        verification_svc = EmailVerificationService(db_manager=db)
        email_svc = InvoiceEmailService(
            ses, contact_svc, param_svc, email_verification_service=verification_svc
        )

        result = email_svc.send_reminder_email(tenant, invoice, sent_by=user_email)
        if result.get("success"):
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        logger.error("send_reminder error for %s/%s: %s", tenant, invoice_id, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


# ── Booking Account Validation (Req 19.6, Design §14.4) ────

# Maps ZZP parameter keys to the ledger flag in rekeningschema.parameters
_BOOKING_ACCOUNT_FLAG_MAP = {
    "debtor_account": "zzp_debtor_account",
    "creditor_account": "zzp_creditor_account",
    "revenue_account": "zzp_revenue_ledger",
}


def _validate_booking_account(tenant: str, key: str, account_code: str) -> None:
    """Validate that an account exists in rekeningschema with the required ledger flag.

    Args:
        tenant: The administration identifier.
        key: The parameter key without namespace (e.g. 'debtor_account').
        account_code: The account number to validate.

    Raises:
        ValueError: If the account is not found or not flagged.
    """
    flag = _BOOKING_ACCOUNT_FLAG_MAP.get(key)
    if not flag:
        return  # No validation for unknown keys

    db = DatabaseManager(test_mode=_test_mode)
    rows = db.execute_query(
        f"""SELECT Account FROM rekeningschema
           WHERE administration = %s AND Account = %s
             AND {dialect.json_extract("parameters", f"$.{flag}")} = true""",
        (tenant, account_code),
    )
    if not rows:
        raise ValueError(
            f"Account {account_code} is not flagged as '{flag}' in the chart of accounts. "
            f"Enable the '{flag}' toggle on this account first."
        )


@zzp_debtor_bp.route("/api/zzp/accounts/validate-booking-param", methods=["POST"])
@cognito_required(required_permissions=["zzp_tenant"])
@tenant_required()
@module_required("ZZP")
def validate_booking_param(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """Validate and save a ZZP booking account parameter.

    Request body:
        { "key": "debtor_account", "value": "1300" }

    Valid keys: debtor_account, creditor_account, revenue_account
    """
    try:
        data = request.get_json()
        key = data.get("key")
        value = data.get("value")

        if not key or not value:
            return jsonify(
                {"success": False, "error": "key and value are required"}
            ), 400

        if key not in _BOOKING_ACCOUNT_FLAG_MAP:
            return jsonify(
                {
                    "success": False,
                    "error": f"Invalid key '{key}'. Must be one of: {', '.join(_BOOKING_ACCOUNT_FLAG_MAP.keys())}",
                }
            ), 400

        _validate_booking_account(tenant, key, value)

        # Validation passed — save the parameter
        db = DatabaseManager(test_mode=_test_mode)
        param_svc = ParameterService(db)
        param_svc.set_param(
            "tenant",
            tenant,
            "zzp",
            key,
            value,
            value_type="string",
            created_by=user_email,
        )

        return jsonify(
            {"success": True, "message": f"Parameter zzp.{key} set to {value}"}
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("validate_booking_param error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500


# ── Account Endpoints (Req 17) ─────────────────────────────


@zzp_debtor_bp.route("/api/zzp/accounts/invoice-ledgers", methods=["GET"])
@cognito_required(required_permissions=["zzp_read"])
@tenant_required()
def get_invoice_ledger_accounts(
    user_email, user_roles, tenant, user_tenants
) -> ResponseReturnValue:
    """List accounts flagged as ZZP revenue ledger for the tenant.

    Returns accounts from rekeningschema where zzp_revenue_ledger = true.
    Falls back to the zzp.revenue_account parameter if no accounts are flagged.
    """
    try:
        db = DatabaseManager(test_mode=_test_mode)
        rows = db.execute_query(
            f"""SELECT Account AS nummer, AccountName AS naam
               FROM rekeningschema
               WHERE administration = %s
                 AND {dialect.json_extract("parameters", "$.zzp_revenue_ledger")} = true
               ORDER BY Account""",
            (tenant,),
        )
        accounts = [
            {"account_code": r["nummer"], "account_name": r["naam"]}
            for r in (rows or [])
        ]

        # Fallback: if no flagged accounts, return the default revenue account
        if not accounts:
            param_svc = ParameterService(db)
            default_acct = (
                param_svc.get_param("zzp", "revenue_account", tenant=tenant) or "8001"
            )
            fallback = db.execute_query(
                "SELECT Account AS nummer, AccountName AS naam FROM rekeningschema WHERE administration = %s AND Account = %s",
                (tenant, default_acct),
            )
            if fallback:
                accounts = [
                    {
                        "account_code": fallback[0]["nummer"],
                        "account_name": fallback[0]["naam"],
                    }
                ]

        return jsonify({"success": True, "data": accounts})
    except Exception as e:
        logger.error("get_invoice_ledger_accounts error for %s: %s", tenant, e)
        return jsonify({"success": False, "error": "An internal error occurred"}), 500
