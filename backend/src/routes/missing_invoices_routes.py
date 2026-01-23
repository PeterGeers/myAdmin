from flask import Blueprint, request, jsonify
import mysql.connector
import os
from google_drive_service import GoogleDriveService
from auth.cognito_utils import cognito_required

missing_invoices_bp = Blueprint('missing_invoices', __name__)

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )

@missing_invoices_bp.route('/api/transactions', methods=['POST'])
@cognito_required(required_permissions=['transactions_read'])
def get_transactions(user_email, user_roles):
    data = request.get_json()
    ids = data.get('ids', [])
    
    if not ids:
        return jsonify([])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    placeholders = ','.join(['%s'] * len(ids))
    query = f"""
    SELECT ID, TransactionAmount, TransactionDate, TransactionDescription, ReferenceNumber
    FROM mutaties 
    WHERE ID IN ({placeholders})
    """
    
    cursor.execute(query, ids)
    results = cursor.fetchall()
    
    transactions = []
    for row in results:
        transactions.append({
            'ID': row[0],
            'TransactionAmount': float(row[1]),
            'TransactionDate': row[2].isoformat(),
            'TransactionDescription': row[3],
            'ReferenceNumber': row[4]
        })
    
    cursor.close()
    conn.close()
    
    return jsonify(transactions)

@missing_invoices_bp.route('/api/upload-receipt', methods=['POST'])
@cognito_required(required_permissions=['invoices_create'])
def upload_receipt(user_email, user_roles):
    file = request.files.get('file')
    supplier_name = request.form.get('supplierName')
    
    if not file or not supplier_name:
        return jsonify({'error': 'Missing file or supplier name'}), 400
    
    try:
        drive_service = GoogleDriveService()
        drive_folders = drive_service.list_subfolders()
        
        # Find folder ID for supplier
        folder_id = None
        for folder in drive_folders:
            if folder['name'] == supplier_name:
                folder_id = folder['id']
                break
        
        if not folder_id:
            # Create folder if it doesn't exist
            use_test = os.getenv('TEST_MODE', 'false').lower() == 'true'
            parent_folder_id = os.getenv('TEST_FACTUREN_FOLDER_ID') if use_test else os.getenv('FACTUREN_FOLDER_ID')
            folder_result = drive_service.create_folder(supplier_name, parent_folder_id)
            folder_id = folder_result['id']
        
        # Save file temporarily and upload
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(file.read())
            temp_path = temp_file.name
        
        drive_result = drive_service.upload_file(temp_path, file.filename, folder_id)
        
        # Clean up temp file
        import os
        os.unlink(temp_path)
        
        return jsonify({'driveUrl': drive_result['url']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@missing_invoices_bp.route('/api/update-transaction-refs', methods=['POST'])
@cognito_required(required_permissions=['transactions_update'])
def update_transaction_refs(user_email, user_roles):
    data = request.get_json()
    ids = data.get('ids', [])
    drive_url = data.get('driveUrl')
    filename = data.get('filename')
    
    if not ids or not drive_url:
        print(f"Missing data - IDs: {ids}, URL: {drive_url}")
        return jsonify({'error': 'Missing IDs or drive URL'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    placeholders = ','.join(['%s'] * len(ids))
    
    if filename:
        # Update both Ref3 and Ref4
        query = f"UPDATE mutaties SET Ref3 = %s, Ref4 = %s WHERE ID IN ({placeholders})"
        cursor.execute(query, [drive_url, filename] + ids)
    else:
        # Update only Ref3
        query = f"UPDATE mutaties SET Ref3 = %s WHERE ID IN ({placeholders})"
        cursor.execute(query, [drive_url] + ids)
    
    conn.commit()
    
    cursor.close()
    conn.close()
    
    return jsonify({'success': True})