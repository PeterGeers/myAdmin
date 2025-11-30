from flask import Blueprint, request, jsonify
from saltedge_service import SaltEdgeService

saltedge_bp = Blueprint('saltedge', __name__, url_prefix='/api/saltedge')
service = SaltEdgeService()

@saltedge_bp.route('/providers', methods=['GET'])
def get_providers():
    country = request.args.get('country', 'NL')
    result = service.get_providers(country)
    return jsonify(result)

@saltedge_bp.route('/customer/create', methods=['POST'])
def create_customer():
    data = request.json
    identifier = data.get('identifier')
    result = service.create_customer(identifier)
    return jsonify(result)

@saltedge_bp.route('/connect/start', methods=['POST'])
def start_connection():
    data = request.json
    customer_id = data.get('customer_id')
    provider_code = data.get('provider_code')
    return_url = data.get('return_url', 'http://localhost:3000/banking/callback')
    
    result = service.create_connect_session(customer_id, provider_code, return_url)
    return jsonify(result)

@saltedge_bp.route('/connections', methods=['GET'])
def get_connections():
    customer_id = request.args.get('customer_id')
    result = service.get_connections(customer_id)
    return jsonify(result)

@saltedge_bp.route('/accounts/<connection_id>', methods=['GET'])
def get_accounts(connection_id):
    result = service.get_accounts(connection_id)
    return jsonify(result)

@saltedge_bp.route('/transactions/<account_id>', methods=['GET'])
def get_transactions(account_id):
    from_date = request.args.get('from_date')
    result = service.get_transactions(account_id, from_date)
    return jsonify(result)

@saltedge_bp.route('/import/transactions', methods=['POST'])
def import_transactions():
    from database import DatabaseManager
    
    data = request.json
    account_id = data.get('account_id')
    iban = data.get('iban')
    account_code = data.get('account_code')
    administration = data.get('administration')
    from_date = data.get('from_date')
    test_mode = data.get('test_mode', False)
    
    txn_result = service.get_transactions(account_id, from_date)
    
    if 'data' in txn_result:
        formatted = service.format_transactions(
            txn_result['data'],
            iban,
            account_code,
            administration
        )
        
        # Check for duplicates using Ref2 (Salt Edge transaction ID)
        db = DatabaseManager(test_mode=test_mode)
        table_name = 'mutaties'
        existing_sequences = db.get_existing_sequences(iban, table_name)
        
        # Filter out duplicates
        new_transactions = [t for t in formatted if t['Ref2'] not in existing_sequences]
        duplicate_count = len(formatted) - len(new_transactions)
        
        return jsonify({
            'success': True, 
            'transactions': new_transactions,
            'total_fetched': len(formatted),
            'duplicates_filtered': duplicate_count
        })
    
    return jsonify({'success': False, 'error': 'Failed to fetch transactions'})
