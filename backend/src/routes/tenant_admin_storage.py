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
from flask.typing import ResponseReturnValue
import os
import logging

from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant
from database import DatabaseManager
from google_drive_service import GoogleDriveService
from services.storage_resolver import resolve_storage_provider, get_s3_storage

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
tenant_admin_storage_bp = Blueprint('tenant_admin_storage', __name__, url_prefix='/api/tenant-admin/storage')


@tenant_admin_storage_bp.route('/folders', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def list_folders(user_email, user_roles) -> ResponseReturnValue:
    """
    List available storage folders (Google Drive or S3 prefixes)
    
    Authorization: Tenant_Admin role required
    
    Returns:
        JSON with folder tree structure
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Resolve storage provider for this tenant
        provider = resolve_storage_provider(tenant)
        
        if provider == 's3_shared':
            # S3 path: list top-level prefixes under {tenant}/
            storage = get_s3_storage(tenant)
            prefix = f"{tenant}/"
            folders = []
            
            continuation_token = None
            while True:
                kwargs = {
                    'Bucket': storage.bucket,
                    'Prefix': prefix,
                    'Delimiter': '/',
                }
                if continuation_token:
                    kwargs['ContinuationToken'] = continuation_token
                
                response = storage._client.list_objects_v2(**kwargs)
                
                for cp in response.get('CommonPrefixes', []):
                    folder_path = cp['Prefix']
                    # Strip base prefix and trailing slash to get folder name
                    folder_name = folder_path[len(prefix):].rstrip('/')
                    if folder_name:
                        folders.append({
                            'id': folder_path,
                            'name': folder_name
                        })
                
                if response.get('IsTruncated'):
                    continuation_token = response.get('NextContinuationToken')
                else:
                    break
            
            logger.info(f"Listed {len(folders)} S3 prefixes for tenant {tenant} by {user_email}")
        else:
            # Google Drive path: unchanged
            drive_service = GoogleDriveService(tenant)
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
def get_storage_config(user_email, user_roles) -> ResponseReturnValue:
    """
    Get current storage configuration
    
    Authorization: Tenant_Admin role required
    
    Returns:
        JSON with storage configuration (keys without prefix, values are folder IDs)
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
            AND (config_key LIKE '%_folder_id')
        """
        
        results = db.execute_query(query, (tenant,))
        
        # Build config dict from key-value pairs
        # Return keys as-is (e.g., "google_drive_invoices_folder_id" -> "google_drive_invoices_folder_id")
        storage_config = {}
        for row in results:
            storage_config[row['config_key']] = row['config_value']
        
        logger.info(f"Retrieved storage config for tenant {tenant}: {list(storage_config.keys())}")
        
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
def update_storage_config(user_email, user_roles) -> ResponseReturnValue:
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
        if data.get('validate', False):
            # Resolve storage provider for this tenant
            provider = resolve_storage_provider(tenant)
            
            if provider == 's3_shared':
                # S3 validation: head_bucket + put/delete cycle
                try:
                    storage = get_s3_storage(tenant)
                    # Verify bucket exists and is accessible
                    storage._client.head_bucket(Bucket=storage.bucket)
                    # Test write access with put/delete cycle
                    test_key = f"{tenant}/_test_access"
                    storage._client.put_object(
                        Bucket=storage.bucket,
                        Key=test_key,
                        Body=b'access_test',
                    )
                    storage._client.delete_object(
                        Bucket=storage.bucket,
                        Key=test_key,
                    )
                except Exception as e:
                    return jsonify({
                        'error': f'S3 storage validation failed: {str(e)}'
                    }), 400
            elif folder_ids:
                # Google Drive validation: test folder accessibility
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
def test_folder_access(user_email, user_roles) -> ResponseReturnValue:
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
        
        # Resolve storage provider for this tenant
        provider = resolve_storage_provider(tenant)
        
        if provider == 's3_shared':
            # S3 path: head_bucket for read access, put/delete cycle for write access
            read_access = False
            write_access = False
            read_error = None
            write_error = None
            
            try:
                storage = get_s3_storage(tenant)
                # Test read access via head_bucket
                storage._client.head_bucket(Bucket=storage.bucket)
                read_access = True
            except Exception as e:
                read_error = str(e)
            
            # Test write access via put_object/delete_object cycle
            if read_access:
                try:
                    test_key = f"{tenant}/_test_access"
                    storage._client.put_object(
                        Bucket=storage.bucket,
                        Key=test_key,
                        Body=b'access_test',
                    )
                    storage._client.delete_object(
                        Bucket=storage.bucket,
                        Key=test_key,
                    )
                    write_access = True
                except Exception as e:
                    write_error = str(e)
            
            # Build response
            test_result = {
                'folder_id': folder_id,
                'read_access': read_access,
                'write_access': write_access,
                'accessible': read_access and write_access
            }
            
            if not read_access:
                test_result['read_error'] = read_error
            
            if not write_access:
                test_result['write_error'] = write_error
            
            logger.info(f"Tested S3 access for tenant {tenant} by {user_email}: {test_result}")
            
            return jsonify({
                'success': True,
                'tenant': tenant,
                'test_result': test_result
            })
        
        # Google Drive path: unchanged
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
            except Exception:
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
def get_storage_usage(user_email, user_roles) -> ResponseReturnValue:
    """
    Get storage usage statistics
    
    Authorization: Tenant_Admin role required
    
    Returns:
        JSON with storage usage by folder (keyed by config_key)
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Resolve storage provider for this tenant
        provider = resolve_storage_provider(tenant)
        
        if provider == 's3_shared':
            # S3 path: list all objects under {tenant}/ prefix and sum sizes
            storage = get_s3_storage(tenant)
            prefix = f"{tenant}/"
            total_size_bytes = 0
            file_count = 0
            
            continuation_token = None
            while True:
                kwargs = {
                    'Bucket': storage.bucket,
                    'Prefix': prefix,
                }
                if continuation_token:
                    kwargs['ContinuationToken'] = continuation_token
                
                response = storage._client.list_objects_v2(**kwargs)
                
                for obj in response.get('Contents', []):
                    # Skip .folder marker objects (zero-byte directory markers)
                    if obj['Key'].endswith('/.folder') and obj.get('Size', 0) == 0:
                        continue
                    total_size_bytes += obj.get('Size', 0)
                    file_count += 1
                
                if response.get('IsTruncated'):
                    continuation_token = response.get('NextContinuationToken')
                else:
                    break
            
            usage_stats = {
                'file_count': file_count,
                'total_size_bytes': total_size_bytes,
                'total_size_mb': round(total_size_bytes / (1024 * 1024), 2),
            }
            
            logger.info(f"Retrieved S3 storage usage for tenant {tenant} by {user_email}: {file_count} files, {total_size_bytes} bytes")
            
            return jsonify({
                'success': True,
                'tenant': tenant,
                'usage': usage_stats
            })
        
        # Google Drive path: unchanged
        # Get storage configuration from tenant_config
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        
        query = """
            SELECT config_key, config_value
            FROM tenant_config
            WHERE administration = %s
            AND config_key LIKE '%_folder_id'
        """
        
        results = db.execute_query(query, (tenant,))
        
        # Build dict: config_key -> folder_id
        storage_config = {}
        for row in results:
            storage_config[row['config_key']] = row['config_value']
        
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
        # Key by config_key (e.g., "google_drive_invoices_folder_id")
        usage_stats = {}
        
        for config_key, folder_id in storage_config.items():
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
                
                usage_stats[config_key] = {
                    'folder_id': folder_id,
                    'folder_name': folder_metadata.get('name', config_key),
                    'folder_url': folder_metadata.get('webViewLink', ''),
                    'file_count': file_count,
                    'total_size_bytes': total_size,
                    'total_size_mb': round(total_size / (1024 * 1024), 2),
                    'accessible': True
                }
                
            except Exception as e:
                logger.error(f"Error getting usage for folder {config_key}: {e}")
                usage_stats[config_key] = {
                    'folder_id': folder_id,
                    'folder_name': config_key,
                    'accessible': False,
                    'error': str(e)
                }
        
        logger.info(f"Retrieved storage usage for tenant {tenant} by {user_email}: {len(usage_stats)} folders")
        
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
