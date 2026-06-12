from flask import Blueprint, request, jsonify
import os
from database import DatabaseManager
from google_drive_service import GoogleDriveService
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from services.storage_resolver import resolve_storage_provider, list_s3_folders, create_s3_folder, get_s3_storage
from services.function_guard import function_guard

missing_invoices_bp = Blueprint('missing_invoices', __name__)
db = DatabaseManager()

@missing_invoices_bp.route('/api/transactions', methods=['POST'])
@cognito_required(required_permissions=['transactions_read'])
def get_transactions(user_email, user_roles):
    data = request.get_json()
    ids = data.get('ids', [])
    
    if not ids:
        return jsonify([])
    
    placeholders = ','.join(['%s'] * len(ids))
    query = f"""
    SELECT ID, TransactionAmount, TransactionDate, TransactionDescription, ReferenceNumber
    FROM mutaties 
    WHERE ID IN ({placeholders})
    """
    
    results = db.execute_query(query, ids)
    
    transactions = []
    for row in results:
        transactions.append({
            'ID': row['ID'],
            'TransactionAmount': float(row['TransactionAmount']),
            'TransactionDate': row['TransactionDate'].isoformat(),
            'TransactionDescription': row['TransactionDescription'],
            'ReferenceNumber': row['ReferenceNumber']
        })
    
    return jsonify(transactions)

@missing_invoices_bp.route('/api/upload-receipt', methods=['POST'])
@cognito_required(required_permissions=['invoices_create'])
@tenant_required()
@function_guard('generate_invoice', 'FIN')
def upload_receipt(user_email, user_roles, tenant, user_tenants):
    file = request.files.get('file')
    supplier_name = request.form.get('supplierName')
    
    if not file or not supplier_name:
        return jsonify({'error': 'Missing file or supplier name'}), 400
    
    # Get administration from tenant context
    administration = tenant
    
    try:
        # Resolve storage provider for this tenant
        provider = resolve_storage_provider(administration)

        if provider == 's3_shared':
            # S3 tenant: use S3 for folder listing and file upload
            s3_folders = list_s3_folders(administration)

            # Check if supplier folder exists
            folder_exists = supplier_name in s3_folders

            if not folder_exists:
                # Create folder marker in S3
                create_s3_folder(administration, supplier_name)

            # Read file data and upload via S3SharedStorage
            file_data = file.read()
            storage = get_s3_storage(administration)
            s3_key = storage.upload(
                file_data, file.filename,
                metadata={'reference_number': supplier_name}
            )

            return jsonify({'driveUrl': s3_key})
        else:
            # Google Drive tenant: use existing Drive service
            drive_service = GoogleDriveService(administration)
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
            os.unlink(temp_path)

            return jsonify({'driveUrl': drive_result['url']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@missing_invoices_bp.route('/api/update-transaction-refs', methods=['POST'])
@cognito_required(required_permissions=['transactions_update'])
@tenant_required()
@function_guard('generate_invoice', 'FIN')
def update_transaction_refs(user_email, user_roles, tenant, user_tenants):
    data = request.get_json()
    ids = data.get('ids', [])
    drive_url = data.get('driveUrl')
    filename = data.get('filename')
    
    if not ids or not drive_url:
        print(f"Missing data - IDs: {ids}, URL: {drive_url}")
        return jsonify({'error': 'Missing IDs or drive URL'}), 400
    
    placeholders = ','.join(['%s'] * len(ids))
    
    if filename:
        # Update both Ref3 and Ref4
        query = f"UPDATE mutaties SET Ref3 = %s, Ref4 = %s WHERE ID IN ({placeholders})"
        db.execute_query(query, [drive_url, filename] + ids, fetch=False, commit=True)
    else:
        # Update only Ref3
        query = f"UPDATE mutaties SET Ref3 = %s WHERE ID IN ({placeholders})"
        db.execute_query(query, [drive_url] + ids, fetch=False, commit=True)
    
    return jsonify({'success': True})