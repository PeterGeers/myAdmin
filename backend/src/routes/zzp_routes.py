"""
ZZP Routes: ZZP module-specific endpoints.

Phase 1: Field config API.
Later phases add invoice, time tracking, debtor, and payment check routes.

Reference: .kiro/specs/zzp-module/design.md §2 (Field Config API)
"""

import logging
from flask import Blueprint, request, jsonify, send_file
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.module_registry import module_required, MODULE_REGISTRY
from database import DatabaseManager
from services.parameter_service import ParameterService
from services.tax_rate_service import TaxRateService
from services.zzp_invoice_service import ZZPInvoiceService

logger = logging.getLogger(__name__)

zzp_bp = Blueprint('zzp', __name__)

_test_mode = False

VALID_ENTITIES = ('contacts', 'products', 'invoices', 'time_entries')

# Map entity name → field config param key
ENTITY_CONFIG_KEYS = {
    'contacts': 'contact_field_config',
    'products': 'product_field_config',
    'invoices': 'invoice_field_config',
    'time_entries': 'time_entry_field_config',
}

# Fields that cannot be set to hidden (DB NOT NULL constraints)
ENTITY_ALWAYS_REQUIRED = {
    'contacts': ['client_id', 'company_name'],
    'products': ['product_code', 'name'],
    'invoices': ['contact_id', 'invoice_date'],
    'time_entries': ['contact_id', 'entry_date', 'hours', 'hourly_rate'],
}


def set_test_mode(flag: bool):
    global _test_mode
    _test_mode = flag


def _get_param_service() -> ParameterService:
    db = DatabaseManager(test_mode=_test_mode)
    return ParameterService(db)


# ── Field Config Endpoints ──────────────────────────────────


@zzp_bp.route('/api/zzp/field-config/<entity>', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def get_field_config(user_email, user_roles, tenant, user_tenants, entity):
    """Get field config for an entity, merged defaults + tenant overrides."""
    try:
        if entity not in VALID_ENTITIES:
            return jsonify({
                'success': False,
                'error': f"Invalid entity '{entity}'. Must be one of: {', '.join(VALID_ENTITIES)}"
            }), 400

        param_svc = _get_param_service()
        config_key = ENTITY_CONFIG_KEYS[entity]

        # Try tenant override first
        config = param_svc.get_param('zzp', config_key, tenant=tenant)

        # Fall back to registry defaults
        if not config:
            param_def = MODULE_REGISTRY['ZZP']['required_params'].get(f'zzp.{config_key}', {})
            config = dict(param_def.get('default', {}))
        else:
            config = dict(config)

        # Enforce always-required fields
        for field in ENTITY_ALWAYS_REQUIRED.get(entity, []):
            config[field] = 'required'

        return jsonify({'success': True, 'data': config})

    except Exception as e:
        logger.error("get_field_config error for %s/%s: %s", tenant, entity, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@zzp_bp.route('/api/zzp/field-config/<entity>', methods=['PUT'])
@cognito_required(required_permissions=['zzp_tenant'])
@tenant_required()
@module_required('ZZP')
def update_field_config(user_email, user_roles, tenant, user_tenants, entity):
    """Update field config for an entity (tenant admin only)."""
    try:
        if entity not in VALID_ENTITIES:
            return jsonify({
                'success': False,
                'error': f"Invalid entity '{entity}'. Must be one of: {', '.join(VALID_ENTITIES)}"
            }), 400

        data = request.get_json()
        if not data or not isinstance(data, dict):
            return jsonify({'success': False, 'error': 'Request body must be a JSON object'}), 400

        valid_levels = {'required', 'optional', 'hidden'}
        for field, level in data.items():
            if level not in valid_levels:
                return jsonify({
                    'success': False,
                    'error': f"Invalid level '{level}' for field '{field}'. Must be one of: {', '.join(valid_levels)}"
                }), 400

        # Prevent hiding always-required fields
        always_req = ENTITY_ALWAYS_REQUIRED.get(entity, [])
        for field in always_req:
            if data.get(field) == 'hidden':
                return jsonify({
                    'success': False,
                    'error': f"Field '{field}' cannot be set to hidden (database constraint)"
                }), 400

        param_svc = _get_param_service()
        config_key = ENTITY_CONFIG_KEYS[entity]
        param_svc.set_param(
            'tenant', tenant, 'zzp', config_key,
            data, value_type='json', created_by=user_email,
        )

        return jsonify({'success': True, 'message': f'Field config updated for {entity}'})

    except Exception as e:
        logger.error("update_field_config error for %s/%s: %s", tenant, entity, e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Invoice service factory ─────────────────────────────────


def _get_invoice_service() -> ZZPInvoiceService:
    db = DatabaseManager(test_mode=_test_mode)
    tax_svc = TaxRateService(db)
    param_svc = ParameterService(db)

    # Import send-flow dependencies (booking, PDF, email)
    try:
        from services.invoice_booking_helper import InvoiceBookingHelper
        from transaction_logic import TransactionLogic
        txn_logic = TransactionLogic(test_mode=_test_mode)
        booking_helper = InvoiceBookingHelper(db, txn_logic, tax_svc, param_svc)
    except Exception as e:
        logger.warning("Could not initialize InvoiceBookingHelper: %s", e)
        booking_helper = None

    try:
        from services.pdf_generator_service import PDFGeneratorService
        pdf_generator = PDFGeneratorService(db, parameter_service=param_svc)
    except Exception as e:
        logger.warning("Could not initialize PDFGeneratorService: %s", e)
        pdf_generator = None

    try:
        from services.invoice_email_service import InvoiceEmailService
        from services.ses_email_service import SESEmailService
        from services.contact_service import ContactService
        ses_svc = SESEmailService()
        contact_svc = ContactService(db, param_svc)
        email_service = InvoiceEmailService(ses_svc, contact_svc, param_svc)
    except Exception as e:
        logger.warning("Could not initialize InvoiceEmailService: %s", e)
        email_service = None

    return ZZPInvoiceService(
        db=db, tax_rate_service=tax_svc, parameter_service=param_svc,
        booking_helper=booking_helper, pdf_generator=pdf_generator,
        email_service=email_service,
    )


# ── Invoice Endpoints (Req 4) ──────────────────────────────


@zzp_bp.route('/api/zzp/invoices', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def list_invoices(user_email, user_roles, tenant, user_tenants):
    """List invoices with optional filters."""
    try:
        svc = _get_invoice_service()
        filters = {
            'status': request.args.get('status'),
            'contact_id': request.args.get('contact_id'),
            'invoice_type': request.args.get('invoice_type'),
            'date_from': request.args.get('date_from'),
            'date_to': request.args.get('date_to'),
            'limit': int(request.args.get('limit', 50)),
            'offset': int(request.args.get('offset', 0)),
        }
        # Remove None values
        filters = {k: v for k, v in filters.items() if v is not None}
        invoices = svc.list_invoices(tenant, filters)
        return jsonify({'success': True, 'data': invoices})
    except Exception as e:
        logger.error("list_invoices error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@zzp_bp.route('/api/zzp/invoices/<int:invoice_id>', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def get_invoice(user_email, user_roles, tenant, user_tenants, invoice_id):
    """Get invoice with lines and VAT summary."""
    try:
        svc = _get_invoice_service()
        invoice = svc.get_invoice(tenant, invoice_id)
        if not invoice:
            return jsonify({'success': False, 'error': 'Invoice not found'}), 404
        return jsonify({'success': True, 'data': invoice})
    except Exception as e:
        logger.error("get_invoice error for %s/%s: %s", tenant, invoice_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@zzp_bp.route('/api/zzp/invoices', methods=['POST'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def create_invoice(user_email, user_roles, tenant, user_tenants):
    """Create a draft invoice."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400
        svc = _get_invoice_service()
        invoice = svc.create_invoice(tenant, data, created_by=user_email)
        return jsonify({'success': True, 'data': invoice}), 201
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("create_invoice error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@zzp_bp.route('/api/zzp/invoices/<int:invoice_id>', methods=['PUT'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def update_invoice(user_email, user_roles, tenant, user_tenants, invoice_id):
    """Update a draft invoice."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400
        svc = _get_invoice_service()
        invoice = svc.update_invoice(tenant, invoice_id, data)
        return jsonify({'success': True, 'data': invoice})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("update_invoice error for %s/%s: %s", tenant, invoice_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Send & PDF Endpoints (Req 6, 8, 9) ─────────────────────


@zzp_bp.route('/api/zzp/invoices/<int:invoice_id>/send', methods=['POST'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def send_invoice(user_email, user_roles, tenant, user_tenants, invoice_id):
    """Generate PDF, book in FIN, optionally email, update status to sent."""
    try:
        data = request.get_json() or {}
        svc = _get_invoice_service()
        result = svc.send_invoice(tenant, invoice_id, data)
        if result.get('success'):
            return jsonify(result)
        return jsonify(result), 400
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("send_invoice error for %s/%s: %s", tenant, invoice_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@zzp_bp.route('/api/zzp/invoices/<int:invoice_id>/pdf', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def get_invoice_pdf(user_email, user_roles, tenant, user_tenants, invoice_id):
    """Download or regenerate invoice PDF."""
    try:
        svc = _get_invoice_service()
        result = svc.get_invoice_pdf(tenant, invoice_id)
        if not result:
            return jsonify({'success': False, 'error': 'Invoice not found'}), 404

        # If we have a URL, redirect or return it
        if result.get('url'):
            return jsonify({'success': True, 'data': result})

        # If we have content (regenerated copy), return as file
        if result.get('content'):
            return send_file(
                result['content'],
                mimetype=result.get('content_type', 'application/pdf'),
                as_attachment=True,
                download_name=result['filename'],
            )

        return jsonify({'success': False, 'error': 'PDF not available'}), 404
    except Exception as e:
        logger.error("get_invoice_pdf error for %s/%s: %s", tenant, invoice_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Credit Note Endpoint (Req 10) ──────────────────────────


@zzp_bp.route('/api/zzp/invoices/<int:invoice_id>/credit', methods=['POST'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def create_credit_note(user_email, user_roles, tenant, user_tenants, invoice_id):
    """Create a credit note for an existing invoice."""
    try:
        svc = _get_invoice_service()
        credit_note = svc.create_credit_note(tenant, invoice_id, created_by=user_email)
        return jsonify({'success': True, 'data': credit_note}), 201
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("create_credit_note error for %s/%s: %s", tenant, invoice_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Payment Check Endpoints (Req 7) ────────────────────────


@zzp_bp.route('/api/zzp/payment-check/run', methods=['POST'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def run_payment_check(user_email, user_roles, tenant, user_tenants):
    """Run payment matching against open invoices."""
    try:
        from services.payment_check_helper import PaymentCheckHelper
        db = DatabaseManager(test_mode=_test_mode)
        helper = PaymentCheckHelper(db)
        result = helper.run_payment_check(tenant)
        return jsonify(result)
    except Exception as e:
        logger.error("run_payment_check error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@zzp_bp.route('/api/zzp/payment-check/status', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def get_payment_check_status(user_email, user_roles, tenant, user_tenants):
    """Get summary of open/matched invoices."""
    try:
        db = DatabaseManager(test_mode=_test_mode)
        open_count = db.execute_query(
            """SELECT COUNT(*) as cnt FROM invoices
               WHERE administration = %s AND status IN ('sent', 'overdue')
                 AND invoice_type = 'invoice'""",
            (tenant,),
        )
        paid_count = db.execute_query(
            """SELECT COUNT(*) as cnt FROM invoices
               WHERE administration = %s AND status = 'paid'
                 AND invoice_type = 'invoice'""",
            (tenant,),
        )
        return jsonify({
            'success': True,
            'open_invoices': open_count[0]['cnt'] if open_count else 0,
            'paid_invoices': paid_count[0]['cnt'] if paid_count else 0,
        })
    except Exception as e:
        logger.error("get_payment_check_status error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Debtor/Creditor Endpoints (Req 12) ─────────────────────


@zzp_bp.route('/api/zzp/debtors/receivables', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def get_receivables(user_email, user_roles, tenant, user_tenants):
    """Accounts receivable: outgoing invoices with status sent/overdue, grouped by contact."""
    try:
        db = DatabaseManager(test_mode=_test_mode)
        rows = db.execute_query(
            """SELECT i.id, i.invoice_number, i.invoice_date, i.due_date,
                      i.grand_total, i.currency, i.status,
                      c.id as contact_id, c.client_id, c.company_name
               FROM invoices i
               JOIN contacts c ON i.contact_id = c.id
               WHERE i.administration = %s
                 AND i.status IN ('sent', 'overdue')
                 AND i.invoice_type = 'invoice'
               ORDER BY c.company_name, i.due_date""",
            (tenant,),
        ) or []

        # Group by contact
        grouped = {}
        total_outstanding = 0.0
        for row in rows:
            cid = row['contact_id']
            if cid not in grouped:
                grouped[cid] = {
                    'contact': {'id': cid, 'client_id': row['client_id'],
                                'company_name': row['company_name']},
                    'invoices': [], 'total': 0.0,
                }
            grouped[cid]['invoices'].append(row)
            grouped[cid]['total'] += float(row['grand_total'])
            total_outstanding += float(row['grand_total'])

        return jsonify({
            'success': True,
            'data': list(grouped.values()),
            'total_outstanding': round(total_outstanding, 2),
        })
    except Exception as e:
        logger.error("get_receivables error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@zzp_bp.route('/api/zzp/debtors/payables', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def get_payables(user_email, user_roles, tenant, user_tenants):
    """Accounts payable: incoming invoices with unpaid status, grouped by contact."""
    try:
        db = DatabaseManager(test_mode=_test_mode)
        rows = db.execute_query(
            """SELECT i.id, i.invoice_number, i.invoice_date, i.due_date,
                      i.grand_total, i.currency, i.status,
                      c.id as contact_id, c.client_id, c.company_name
               FROM invoices i
               JOIN contacts c ON i.contact_id = c.id
               WHERE i.administration = %s
                 AND i.status IN ('sent', 'overdue')
                 AND i.invoice_type = 'credit_note'
               ORDER BY c.company_name, i.due_date""",
            (tenant,),
        ) or []

        grouped = {}
        total_outstanding = 0.0
        for row in rows:
            cid = row['contact_id']
            if cid not in grouped:
                grouped[cid] = {
                    'contact': {'id': cid, 'client_id': row['client_id'],
                                'company_name': row['company_name']},
                    'invoices': [], 'total': 0.0,
                }
            grouped[cid]['invoices'].append(row)
            amt = abs(float(row['grand_total']))
            grouped[cid]['total'] += amt
            total_outstanding += amt

        return jsonify({
            'success': True,
            'data': list(grouped.values()),
            'total_outstanding': round(total_outstanding, 2),
        })
    except Exception as e:
        logger.error("get_payables error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@zzp_bp.route('/api/zzp/debtors/aging', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def get_aging(user_email, user_roles, tenant, user_tenants):
    """Aging analysis with buckets: current, 1-30, 31-60, 61-90, 90+."""
    try:
        db = DatabaseManager(test_mode=_test_mode)
        rows = db.execute_query(
            """SELECT i.id, i.invoice_number, i.due_date, i.grand_total,
                      i.status, DATEDIFF(CURDATE(), i.due_date) as days_overdue,
                      c.id as contact_id, c.client_id, c.company_name
               FROM invoices i
               JOIN contacts c ON i.contact_id = c.id
               WHERE i.administration = %s
                 AND i.status IN ('sent', 'overdue')
                 AND i.invoice_type = 'invoice'
               ORDER BY c.company_name, i.due_date""",
            (tenant,),
        ) or []

        buckets = {'current': 0.0, '1_30_days': 0.0, '31_60_days': 0.0,
                   '61_90_days': 0.0, '90_plus_days': 0.0}
        by_contact = {}

        for row in rows:
            days = int(row.get('days_overdue', 0))
            amount = float(row['grand_total'])

            if days <= 0:
                bucket = 'current'
            elif days <= 30:
                bucket = '1_30_days'
            elif days <= 60:
                bucket = '31_60_days'
            elif days <= 90:
                bucket = '61_90_days'
            else:
                bucket = '90_plus_days'

            buckets[bucket] += amount
            row['bucket'] = bucket

            cid = row['contact_id']
            if cid not in by_contact:
                by_contact[cid] = {
                    'contact': {'id': cid, 'client_id': row['client_id'],
                                'company_name': row['company_name']},
                    'total': 0.0, 'invoices': [],
                }
            by_contact[cid]['invoices'].append({
                'invoice_number': row['invoice_number'],
                'grand_total': amount,
                'due_date': str(row['due_date']),
                'days_overdue': days,
                'bucket': bucket,
            })
            by_contact[cid]['total'] += amount

        total = round(sum(buckets.values()), 2)
        buckets = {k: round(v, 2) for k, v in buckets.items()}

        return jsonify({
            'success': True,
            'data': {
                'total_outstanding': total,
                'buckets': buckets,
                'by_contact': list(by_contact.values()),
            },
        })
    except Exception as e:
        logger.error("get_aging error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@zzp_bp.route('/api/zzp/debtors/send-reminder/<int:invoice_id>', methods=['POST'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def send_reminder(user_email, user_roles, tenant, user_tenants, invoice_id):
    """Send payment reminder for an overdue invoice."""
    try:
        svc = _get_invoice_service()
        invoice = svc.get_invoice(tenant, invoice_id)
        if not invoice:
            return jsonify({'success': False, 'error': 'Invoice not found'}), 404
        if invoice['status'] not in ('sent', 'overdue'):
            return jsonify({'success': False, 'error': 'Can only remind for sent/overdue invoices'}), 400

        from services.invoice_email_service import InvoiceEmailService
        from services.contact_service import ContactService
        from services.ses_email_service import SESEmailService

        db = DatabaseManager(test_mode=_test_mode)
        param_svc = ParameterService(db)
        contact_svc = ContactService(db=db, parameter_service=param_svc)
        ses = SESEmailService()
        email_svc = InvoiceEmailService(ses, contact_svc, param_svc)

        result = email_svc.send_reminder_email(tenant, invoice, sent_by=user_email)
        if result.get('success'):
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        logger.error("send_reminder error for %s/%s: %s", tenant, invoice_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Time Tracking Endpoints (Req 11) ───────────────────────


def _get_time_service():
    from services.time_tracking_service import TimeTrackingService
    db = DatabaseManager(test_mode=_test_mode)
    param_svc = ParameterService(db)
    return TimeTrackingService(db=db, parameter_service=param_svc)


@zzp_bp.route('/api/zzp/time-entries', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def list_time_entries(user_email, user_roles, tenant, user_tenants):
    """List time entries with optional filters."""
    try:
        svc = _get_time_service()
        if not svc.is_enabled(tenant):
            return jsonify({'success': False, 'error': 'Time tracking is disabled'}), 404
        filters = {
            'contact_id': request.args.get('contact_id'),
            'project_name': request.args.get('project_name'),
            'date_from': request.args.get('date_from'),
            'date_to': request.args.get('date_to'),
            'limit': int(request.args.get('limit', 50)),
            'offset': int(request.args.get('offset', 0)),
        }
        if request.args.get('is_billable') is not None:
            filters['is_billable'] = request.args.get('is_billable').lower() == 'true'
        if request.args.get('is_billed') is not None:
            filters['is_billed'] = request.args.get('is_billed').lower() == 'true'
        filters = {k: v for k, v in filters.items() if v is not None}
        entries = svc.list_entries(tenant, filters)
        return jsonify({'success': True, 'data': entries})
    except Exception as e:
        logger.error("list_time_entries error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@zzp_bp.route('/api/zzp/time-entries', methods=['POST'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def create_time_entry(user_email, user_roles, tenant, user_tenants):
    """Create a time entry."""
    try:
        svc = _get_time_service()
        if not svc.is_enabled(tenant):
            return jsonify({'success': False, 'error': 'Time tracking is disabled'}), 404
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400
        entry = svc.create_entry(tenant, data, created_by=user_email)
        return jsonify({'success': True, 'data': entry}), 201
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("create_time_entry error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@zzp_bp.route('/api/zzp/time-entries/<int:entry_id>', methods=['PUT'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def update_time_entry(user_email, user_roles, tenant, user_tenants, entry_id):
    """Update a time entry."""
    try:
        svc = _get_time_service()
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400
        entry = svc.update_entry(tenant, entry_id, data)
        return jsonify({'success': True, 'data': entry})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("update_time_entry error for %s/%s: %s", tenant, entry_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@zzp_bp.route('/api/zzp/time-entries/<int:entry_id>', methods=['DELETE'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def delete_time_entry(user_email, user_roles, tenant, user_tenants, entry_id):
    """Delete a time entry."""
    try:
        svc = _get_time_service()
        svc.delete_entry(tenant, entry_id)
        return jsonify({'success': True, 'message': 'Time entry deleted'})
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("delete_time_entry error for %s/%s: %s", tenant, entry_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


@zzp_bp.route('/api/zzp/time-entries/summary', methods=['GET'])
@cognito_required(required_permissions=['zzp_read'])
@tenant_required()
@module_required('ZZP')
def get_time_summary(user_email, user_roles, tenant, user_tenants):
    """Get time entry summary grouped by contact, project, or period."""
    try:
        svc = _get_time_service()
        if not svc.is_enabled(tenant):
            return jsonify({'success': False, 'error': 'Time tracking is disabled'}), 404
        group_by = request.args.get('group_by', 'contact')
        period = request.args.get('period', 'month')
        summary = svc.get_summary(tenant, group_by=group_by, period=period)
        return jsonify({'success': True, 'data': summary})
    except Exception as e:
        logger.error("get_time_summary error for %s: %s", tenant, e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Supporting Document Upload (Req 11.8–11.10) ────────────


@zzp_bp.route('/api/zzp/invoices/<int:invoice_id>/documents', methods=['POST'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def upload_supporting_document(user_email, user_roles, tenant, user_tenants, invoice_id):
    """Upload a supporting document and link it to an invoice.

    Stores via OutputService (Google Drive) and records the reference
    on the invoice for later attachment when sending.
    """
    try:
        svc = _get_invoice_service()
        invoice = svc.get_invoice(tenant, invoice_id)
        if not invoice:
            return jsonify({'success': False, 'error': 'Invoice not found'}), 404

        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['file']
        if not file.filename:
            return jsonify({'success': False, 'error': 'Empty filename'}), 400

        # Read file content
        file_content = file.read()
        filename = file.filename

        # Store via tenant's configured storage provider
        from storage.storage_provider import get_storage_provider
        db = DatabaseManager(test_mode=_test_mode)
        param_svc = ParameterService(db)
        provider = get_storage_provider(tenant, param_svc)

        doc_path = f"zzp/invoices/{invoice['invoice_number']}/{filename}"
        url = provider.upload(file_content, doc_path, metadata={
            'administration': tenant,
            'invoice_id': invoice_id,
            'content_type': file.content_type or 'application/octet-stream',
        })

        return jsonify({
            'success': True,
            'data': {
                'filename': filename,
                'url': url,
                'invoice_id': invoice_id,
            },
        }), 201

    except Exception as e:
        logger.error("upload_supporting_document error for %s/%s: %s",
                     tenant, invoice_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Copy Last Invoice Endpoint (Req 13) ────────────────────


@zzp_bp.route('/api/zzp/invoices/copy-last/<int:contact_id>', methods=['POST'])
@cognito_required(required_permissions=['zzp_crud'])
@tenant_required()
@module_required('ZZP')
def copy_last_invoice(user_email, user_roles, tenant, user_tenants, contact_id):
    """Create a draft by copying the last invoice for a contact."""
    try:
        svc = _get_invoice_service()
        invoice = svc.copy_last_invoice(tenant, contact_id, created_by=user_email)
        return jsonify({'success': True, 'data': invoice}), 201
    except ValueError as ve:
        return jsonify({'success': False, 'error': str(ve)}), 400
    except Exception as e:
        logger.error("copy_last_invoice error for %s/contact %s: %s", tenant, contact_id, e)
        return jsonify({'success': False, 'error': str(e)}), 500
