"""
Tenant Admin Storage Configuration Routes

This module provides API endpoints for Tenant_Admin role to configure
storage settings (Google Drive folders, etc.)

Endpoints:
- GET /api/tenant-admin/storage/folders - List available folders
- PUT /api/tenant-admin/storage/config - Update storage configuration
- POST /api/tenant-admin/storage/test - Test folder accessibility
- GET /api/tenant-admin/storage/usage - Get storage usage statistics
"""

from flask import Blueprint, jsonify, request
import os
import logging

from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant
from database import DatabaseManager
from google_drive_service import GoogleDriveService

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
tenant_admin_storage_bp = Blueprint('tenant_admin_storage', __name__, url_prefix='/api/tenant-admin/storage')


@tenant_admin_storage_bp.route('/folders', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def list_folders(user_email, user_roles):
    """
    List available Google Drive folders
    
    Authorization: Tenant_Admin role required
    
    Returns:
        JSON with folder tree structure
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Initialize Google Drive service for this tenant
        drive_service = GoogleDriveService(tenant)
        
        # Get list of subfolders
        folders = drive_service.list_subfolders()
        
        logger.info(f"Listed {len(folders)} folders for tenant {tenant} by {user_email}")
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'folders': folders,
            'count': len(folders)
        })
        
    except Exception as e:
        logger.error(f"Error listing folders: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@tenant_admin_storage_bp.route('/config', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def get_storage_config(user_email, user_roles):
    """
    Get current storage configuration
    
    Authorization: Tenant_Admin role required
    
    Returns:
        JSON with storage configuration
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Get configuration from tenant_config table
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        query = """
            SELECT config_key, config_value, is_secret
            FROM tenant_config
            WHERE administration = %s
            AND config_key LIKE 'storage_%'
        """
        
        results = db.execute_query(query, (tenant,))
        
        # Build config dict from key-value pairs
        storage_config = {}
        for row in results:
            key = row['config_key'].replace('storage_', '')  # Remove 'storage_' prefix
            storage_config[key] = row['config_value']
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'config': storage_config
        })
        
    except Exception as e:
        logger.error(f"Error getting storage config: {e}")
        return jsonify({'error': str(e)}), 500


@tenant_admin_storage_bp.route('/config', methods=['PUT'])
@cognito_required(required_roles=['Tenant_Admin'])
def update_storage_config(user_email, user_roles):
    """
    Update storage configuration
    
    Authorization: Tenant_Admin role required
    
    Request body:
    {
        "facturen_folder_id": "folder_id",
        "invoices_folder_id": "folder_id",
        "reports_folder_id": "folder_id"
    }
    
    Returns:
        JSON with success status
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Get request data
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No configuration data provided'}), 400
        
        # Validate folder IDs (optional - test accessibility)
        folder_ids = [v for k, v in data.items() if k.endswith('_folder_id') and v]
        
        # Test folder accessibility if requested
        if data.get('validate', False) and folder_ids:
            try:
                drive_service = GoogleDriveService(tenant)
                for folder_id in folder_ids:
                    # Try to list files in folder (limit 1)
                    drive_service.service.files().list(
                        q=f"'{folder_id}' in parents",
                        pageSize=1,
                        fields="files(id)"
                    ).execute()
            except Exception as e:
                return jsonify({
                    'error': f'Folder validation failed: {str(e)}'
                }), 400
        
        # Update configuration in tenant_config table
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        # Insert or update each config key
        for key, value in data.items():
            if key == 'validate':
                continue  # Skip the validate flag
            
            config_key = f'storage_{key}'
            
            query = """
                INSERT INTO tenant_config (administration, config_key, config_value, is_secret, created_by)
                VALUES (%s, %s, %s, FALSE, %s)
                ON DUPLICATE KEY UPDATE
                    config_value = VALUES(config_value),
                    updated_at = CURRENT_TIMESTAMP
            """
            
            db.execute_query(
                query,
                (tenant, config_key, value, user_email),
                fetch=False,
                commit=True
            )
        
        logger.info(f"Updated storage config for tenant {tenant} by {user_email}")
        
        # Get updated config
        query = """
            SELECT config_key, config_value
            FROM tenant_config
            WHERE administration = %s
            AND config_key LIKE 'storage_%'
        """
        
        results = db.execute_query(query, (tenant,))
        updated_config = {
            row['config_key'].replace('storage_', ''): row['config_value']
            for row in results
        }
        
        return jsonify({
            'success': True,
            'message': 'Storage configuration updated successfully',
            'tenant': tenant,
            'config': updated_config
        })
        
    except Exception as e:
        logger.error(f"Error updating storage config: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@tenant_admin_storage_bp.route('/test', methods=['POST'])
@cognito_required(required_roles=['Tenant_Admin'])
def test_folder_access(user_email, user_roles):
    """
    Test folder accessibility and write permissions
    
    Authorization: Tenant_Admin role required
    
    Request body:
    {
        "folder_id": "google_drive_folder_id"
    }
    
    Returns:
        JSON with test results
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Get request data
        data = request.get_json()
        folder_id = data.get('folder_id')
        
        if not folder_id:
            return jsonify({'error': 'folder_id is required'}), 400
        
        # Initialize Google Drive service
        drive_service = GoogleDriveService(tenant)
        
        # Test 1: Read access - list files in folder
        try:
            results = drive_service.service.files().list(
                q=f"'{folder_id}' in parents",
                pageSize=10,
                fields="files(id, name)"
            ).execute()
            
            files = results.get('files', [])
            read_access = True
            file_count = len(files)
        except Exception as e:
            read_access = False
            file_count = 0
            read_error = str(e)
        
        # Test 2: Write access - try to create a test file
        write_access = False
        write_error = None
        
        try:
            # Create a small test file
            test_content = "Test file created by myAdmin storage configuration test"
            test_filename = f"_test_access_{tenant}.txt"
            
            result = drive_service.upload_text_file(
                test_content,
                test_filename,
                folder_id,
                mime_type='text/plain'
            )
            
            write_access = True
            test_file_id = result['id']
            
            # Clean up - delete test file
            try:
                drive_service.service.files().delete(fileId=test_file_id).execute()
            except:
                pass  # Ignore cleanup errors
                
        except Exception as e:
            write_error = str(e)
        
        # Build response
        test_result = {
            'folder_id': folder_id,
            'read_access': read_access,
            'write_access': write_access,
            'file_count': file_count if read_access else None,
            'accessible': read_access and write_access
        }
        
        if not read_access:
            test_result['read_error'] = read_error
        
        if not write_access:
            test_result['write_error'] = write_error
        
        logger.info(f"Tested folder {folder_id} for tenant {tenant} by {user_email}: {test_result}")
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'test_result': test_result
        })
        
    except Exception as e:
        logger.error(f"Error testing folder access: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@tenant_admin_storage_bp.route('/usage', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def get_storage_usage(user_email, user_roles):
    """
    Get storage usage statistics
    
    Authorization: Tenant_Admin role required
    
    Returns:
        JSON with storage usage by type
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Get storage configuration from tenant_config
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        query = """
            SELECT config_key, config_value
            FROM tenant_config
            WHERE administration = %s
            AND config_key LIKE 'storage_%_folder_id'
        """
        
        results = db.execute_query(query, (tenant,))
        
        storage_config = {}
        for row in results:
            key = row['config_key'].replace('storage_', '').replace('_folder_id', '')
            storage_config[key] = row['config_value']
        
        if not storage_config:
            return jsonify({
                'success': True,
                'tenant': tenant,
                'usage': {},
                'message': 'No storage folders configured'
            })
        
        # Initialize Google Drive service
        drive_service = GoogleDriveService(tenant)
        
        # Calculate usage for each configured folder
        usage_stats = {}
        
        for folder_name, folder_id in storage_config.items():
            if not folder_id:
                continue
                
            try:
                # Get folder metadata (name, URL)
                folder_metadata = drive_service.service.files().get(
                    fileId=folder_id,
                    fields='id, name, webViewLink'
                ).execute()
                
                # List all files in folder
                all_files = []
                page_token = None
                
                while True:
                    results = drive_service.service.files().list(
                        q=f"'{folder_id}' in parents and trashed=false",
                        pageSize=1000,
                        fields="nextPageToken, files(id, name, size, mimeType)",
                        pageToken=page_token
                    ).execute()
                    
                    files = results.get('files', [])
                    all_files.extend(files)
                    
                    page_token = results.get('nextPageToken')
                    if not page_token:
                        break
                
                # Calculate statistics
                total_size = sum(int(f.get('size', 0)) for f in all_files if f.get('size'))
                file_count = len(all_files)
                
                usage_stats[folder_name] = {
                    'folder_id': folder_id,
                    'folder_name': folder_metadata.get('name', folder_name),
                    'folder_url': folder_metadata.get('webViewLink', ''),
                    'file_count': file_count,
                    'total_size_bytes': total_size,
                    'total_size_mb': round(total_size / (1024 * 1024), 2),
                    'accessible': True
                }
                
            except Exception as e:
                logger.error(f"Error getting usage for folder {folder_name}: {e}")
                usage_stats[folder_name] = {
                    'folder_id': folder_id,
                    'folder_name': folder_name,
                    'accessible': False,
                    'error': str(e)
                }
        
        logger.info(f"Retrieved storage usage for tenant {tenant} by {user_email}")
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'usage': usage_stats
        })
        
    except Exception as e:
        logger.error(f"Error getting storage usage: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
