"""
Banking Routes Blueprint

Handles all banking transaction processing endpoints including:
- CSV file scanning and processing
- Pattern matching and account assignment
- Transaction saving and retrieval
- Account balance checking
- Revolut balance validation

Extracted from app.py during refactoring (Phase 3.2)
"""

from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.banking_service import BankingService

# Create blueprint
banking_bp = Blueprint('banking', __name__)

# Service instance (will be set by set_test_mode)
banking_service = None


def set_test_mode(test_mode):
    """Set test mode for banking service"""
    global banking_service
    banking_service = BankingService(test_mode=test_mode)


@banking_bp.route('/api/banking/scan-files', methods=['GET'])
@cognito_required(required_permissions=['banking_read'])
@tenant_required()
def banking_scan_files(user_email, user_roles, tenant, user_tenants):
    """Scan download folder for CSV files"""
    try:
        folder_path = request.args.get('folder', None)
        result = banking_service.scan_banking_files(folder_path)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 500
    except Exception as e:
        print(f"Banking scan files error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@banking_bp.route('/api/banking/process-files', methods=['POST'])
@cognito_required(required_permissions=['banking_process'])
@tenant_required()
def banking_process_files(user_email, user_roles, tenant, user_tenants):
    """Process selected CSV files"""
    try:
        data = request.get_json()
        file_paths = data.get('files', [])
        test_mode = data.get('test_mode', True)
        
        result = banking_service.process_banking_files(file_paths, tenant, test_mode)
        
        if result['success']:
            return jsonify(result)
        else:
            status_code = 403 if 'Access denied' in result.get('error', '') else 400
            return jsonify(result), status_code
        
    except Exception as e:
        print(f"Banking process files error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@banking_bp.route('/api/banking/check-sequences', methods=['POST'])
@cognito_required(required_permissions=['banking_read'])
def banking_check_sequences(user_email, user_roles):
    """Check sequence numbers against database"""
    try:
        data = request.get_json()
        iban = data.get('iban')
        sequences = data.get('sequences', [])
        test_mode = data.get('test_mode', True)
        
        result = banking_service.check_sequences(iban, sequences, test_mode)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@banking_bp.route('/api/banking/apply-patterns', methods=['POST'])
@cognito_required(required_permissions=['banking_process'])
@tenant_required()
def banking_apply_patterns(user_email, user_roles, tenant, user_tenants):
    """Apply enhanced pattern matching to predict debet/credit accounts"""
    try:
        data = request.get_json()
        transactions = data.get('transactions', [])
        test_mode = data.get('test_mode', True)
        use_enhanced = data.get('use_enhanced', True)
        
        result = banking_service.apply_patterns(transactions, tenant, use_enhanced, test_mode)
        return jsonify(result)
        
    except Exception as e:
        print(f"Pattern matching error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@banking_bp.route('/api/banking/save-transactions', methods=['POST'])
@cognito_required(required_permissions=['transactions_create'])
@tenant_required()
def banking_save_transactions(user_email, user_roles, tenant, user_tenants):
    """Save approved transactions to database with duplicate filtering"""
    try:
        data = request.get_json()
        transactions = data.get('transactions', [])
        test_mode = data.get('test_mode', True)
        
        result = banking_service.save_transactions(transactions, tenant, test_mode)
        return jsonify(result)
        
    except Exception as e:
        print(f"Banking save transactions error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@banking_bp.route('/api/banking/lookups', methods=['GET'])
@cognito_required(required_permissions=['banking_read'])
@tenant_required()
def banking_lookups(user_email, user_roles, tenant, user_tenants):
    """Get mapping data for account codes and descriptions"""
    try:
        result = banking_service.get_lookups(tenant)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 500
        
    except Exception as e:
        print(f"Banking lookups error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@banking_bp.route('/api/banking/mutaties', methods=['GET'])
@cognito_required(required_permissions=['transactions_read'])
@tenant_required()
def banking_mutaties(user_email, user_roles, tenant, user_tenants):
    """Get mutaties with filters"""
    try:
        # Get filter parameters
        years = request.args.get('years', '').split(',') if request.args.get('years') else []
        administration = request.args.get('administration', 'all')
        
        filters = {
            'years': years,
            'administration': administration
        }
        
        result = banking_service.get_mutaties(filters, tenant, user_tenants)
        
        if result['success']:
            return jsonify(result)
        else:
            status_code = 403 if 'Access denied' in result.get('error', '') else 500
            return jsonify(result), status_code
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@banking_bp.route('/api/banking/filter-options', methods=['GET'])
@cognito_required(required_permissions=['transactions_read'])
@tenant_required()
def banking_filter_options(user_email, user_roles, tenant, user_tenants):
    """Get filter options for mutaties"""
    try:
        from database import DatabaseManager
        from datetime import datetime
        
        db = DatabaseManager(test_mode=banking_service.test_mode)
        table_name = 'mutaties_test' if banking_service.test_mode else 'mutaties'
        
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build administration filter based on user's accessible tenants
        if len(user_tenants) == 1:
            admin_filter = "AND administration = %s"
            admin_params = [user_tenants[0]]
        else:
            placeholders = ','.join(['%s'] * len(user_tenants))
            admin_filter = f"AND administration IN ({placeholders})"
            admin_params = user_tenants
        
        # Get distinct years (filtered by tenant)
        cursor.execute(f"SELECT DISTINCT YEAR(TransactionDate) as year FROM {table_name} WHERE TransactionDate IS NOT NULL {admin_filter} ORDER BY year DESC", admin_params)
        years = [str(row['year']) for row in cursor.fetchall()]
        
        # Get distinct administrations (only those user has access to)
        cursor.execute(f"SELECT DISTINCT administration FROM {table_name} WHERE administration IS NOT NULL {admin_filter} ORDER BY administration", admin_params)
        administrations = [row['administration'] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'years': years,
            'administrations': administrations
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@banking_bp.route('/api/banking/update-mutatie', methods=['POST'])
@cognito_required(required_permissions=['transactions_update'])
@tenant_required()
def banking_update_mutatie(user_email, user_roles, tenant, user_tenants):
    """Update a mutatie record"""
    try:
        data = request.get_json()
        record_id = data.get('ID')
        
        print(f"Update request for ID: {record_id}", flush=True)
        print(f"Data received: {data}", flush=True)
        print(f"Current tenant: {tenant}", flush=True)
        
        if not record_id:
            return jsonify({'success': False, 'error': 'No ID provided'}), 400
        
        result = banking_service.update_mutatie(record_id, data, tenant)
        
        if result['success']:
            return jsonify(result)
        else:
            status_code = 404 if 'not found' in result.get('error', '').lower() else 403
            return jsonify(result), status_code
        
    except Exception as e:
        print(f"Update error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@banking_bp.route('/api/banking/check-accounts', methods=['GET'])
@cognito_required(required_permissions=['banking_read'])
@tenant_required()
def banking_check_accounts(user_email, user_roles, tenant, user_tenants):
    """Check banking account balances"""
    try:
        end_date = request.args.get('end_date')
        result = banking_service.check_accounts(tenant, end_date)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 500
        
    except Exception as e:
        print(f"Banking check accounts error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@banking_bp.route('/api/banking/check-sequence', methods=['GET'])
@cognito_required(required_permissions=['banking_read'])
def banking_check_sequence(user_email, user_roles):
    """Check sequence numbers for account"""
    try:
        from banking_processor import BankingProcessor
        
        processor = BankingProcessor(test_mode=banking_service.test_mode)
        account_code = request.args.get('account_code')
        administration = request.args.get('administration')
        start_date = request.args.get('start_date', '2025-01-01')
        
        result = processor.check_sequence_numbers(account_code, administration, start_date)
        return jsonify(result)
        
    except Exception as e:
        print(f"Check sequence error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@banking_bp.route('/api/banking/check-revolut-balance', methods=['GET'])
@cognito_required(required_permissions=['banking_read'])
@tenant_required()
def banking_check_revolut_balance(user_email, user_roles, tenant, user_tenants):
    """Check Revolut balance gaps by comparing calculated vs Ref3 balance"""
    try:
        iban = request.args.get('iban', 'NL08REVO7549383472')
        account_code = request.args.get('account_code', '1022')
        start_date = request.args.get('start_date', '2025-05-01')
        expected_balance = float(request.args.get('expected_balance', '262.54'))
        
        result = banking_service.check_revolut_balance(iban, account_code, start_date, expected_balance)
        return jsonify(result)
        
    except Exception as e:
        print(f"Check Revolut balance error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@banking_bp.route('/api/banking/check-revolut-balance-debug', methods=['GET'])
@cognito_required(required_permissions=['banking_read'])
def banking_check_revolut_balance_debug(user_email, user_roles):
    """Debug endpoint - returns only first 10 transactions with full details"""
    try:
        from banking_processor import BankingProcessor
        
        processor = BankingProcessor(test_mode=banking_service.test_mode)
        iban = request.args.get('iban', 'NL08REVO7549383472')
        account_code = request.args.get('account_code', '1022')
        start_date = request.args.get('start_date', '2025-05-01')
        expected_balance = float(request.args.get('expected_balance', '262.54'))
        
        result = processor.check_revolut_balance_gaps(
            iban=iban,
            account_code=account_code,
            start_date=start_date,
            expected_final_balance=expected_balance
        )
        
        # Return only first 10 transactions for debugging
        if result.get('success'):
            return jsonify({
                'success': True,
                'iban': result.get('iban'),
                'start_date': result.get('start_date'),
                'starting_balance_debug': result.get('starting_balance_debug'),
                'first_10_transactions': result.get('first_10_transactions', []),
                'total_transactions': result.get('total_transactions', 0),
                'note': 'Debug endpoint - showing first 10 transactions only'
            })
        else:
            return jsonify(result)
        
    except Exception as e:
        print(f"Check Revolut balance debug error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@banking_bp.route('/api/banking/migrate-revolut-ref2', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def banking_migrate_revolut_ref2(user_email, user_roles):
    """Migrate Revolut Ref2 to new format"""
    try:
        from migrate_revolut_ref2 import migrate_revolut_ref2
        result = migrate_revolut_ref2(test_mode=banking_service.test_mode)
        return jsonify(result)
    except Exception as e:
        print(f"Migration error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
