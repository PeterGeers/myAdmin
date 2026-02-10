"""
Folder Management Routes Blueprint

Handles folder listing and creation endpoints for Google Drive integration.
Extracted from app.py during refactoring (Phase 1.4)
"""

from flask import Blueprint, jsonify, request
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from google_drive_service import GoogleDriveService
from config import Config
import os

folder_bp = Blueprint('folders', __name__)

# Access to config and flag from app.py
# These will be set by app.py after blueprint registration
config = None
flag = False

def set_config_and_flag(app_config, test_mode):
    """Set the config and test mode flag from app.py"""
    global config, flag
    config = app_config
    flag = test_mode


@folder_bp.route('/api/folders', methods=['GET'])
@cognito_required(required_permissions=['invoices_read'])
def get_folders(user_email, user_roles):
    """Return available vendor folders with optional regex filtering"""
    try:
        # Get tenant from request header
        from auth.tenant_context import get_current_tenant
        tenant = get_current_tenant(request)
        
        if not tenant:
            return jsonify({'error': 'No tenant specified. Please select a tenant.'}), 400
        
        regex_pattern = request.args.get('regex')
        print(f"get_folders called for tenant={tenant}, flag={flag}, regex={regex_pattern}", flush=True)
        
        if flag:  # Test mode - use local folders
            folders = list(config.vendor_folders.values())
            print(f"Test mode: returning {len(folders)} local folders", flush=True)
        else:  # Production mode - use Google Drive folders
            try:
                print(f"Production mode: fetching Google Drive folders for tenant={tenant}", flush=True)
                drive_service = GoogleDriveService(administration=tenant)
                drive_folders = drive_service.list_subfolders()
                print(f"Raw drive_folders result: {type(drive_folders)}, length: {len(drive_folders) if drive_folders else 0}", flush=True)
                
                # Extract folder names and deduplicate (Google Drive allows duplicate folder names)
                folder_names = [folder['name'] for folder in drive_folders]
                # Use dict.fromkeys() to preserve order while removing duplicates
                folders = list(dict.fromkeys(folder_names))
                
                if len(folder_names) != len(folders):
                    print(f"Warning: Deduplicated {len(folder_names)} folders to {len(folders)} unique names", flush=True)
                    # Log which folders were duplicated
                    from collections import Counter
                    duplicates = [name for name, count in Counter(folder_names).items() if count > 1]
                    print(f"Duplicate folder names found: {duplicates}", flush=True)
                
                print(f"Google Drive: found {len(folders)} unique folders for tenant={tenant}", flush=True)
            except Exception as e:
                print(f"Google Drive error for tenant={tenant}: {type(e).__name__}: {e}", flush=True)
                import traceback
                traceback.print_exc()
                # Fallback to local folders if Google Drive fails
                folders = list(config.vendor_folders.values())
                print(f"Fallback: returning {len(folders)} local folders", flush=True)
        
        # Apply regex filter if provided
        if regex_pattern:
            import re
            try:
                compiled_regex = re.compile(regex_pattern, re.IGNORECASE)
                filtered_folders = [folder for folder in folders if compiled_regex.search(folder)]
                print(f"Regex '{regex_pattern}' filtered {len(folders)} folders to {len(filtered_folders)}", flush=True)
                folders = filtered_folders
            except re.error as e:
                print(f"Invalid regex pattern '{regex_pattern}': {e}", flush=True)
                return jsonify({'error': f'Invalid regex pattern: {e}'}), 400
        
        return jsonify(folders)
    except Exception as e:
        print(f"Error in get_folders: {e}", flush=True)
        return jsonify({'error': str(e)}), 500


@folder_bp.route('/api/create-folder', methods=['POST'])
@cognito_required(required_permissions=['invoices_create'])
@tenant_required()
def create_folder(user_email, user_roles, tenant, user_tenants):
    """Create a new folder in Google Drive"""
    try:
        data = request.get_json()
        folder_name = data.get('folderName')
        if folder_name:
            # Create local folder
            folder_path = config.get_storage_folder(folder_name)
            config.ensure_folder_exists(folder_path)
            
            # Create Google Drive folder in correct parent
            try:
                print(f"Creating Google Drive folder for tenant: {tenant}", flush=True)
                drive_service = GoogleDriveService(administration=tenant)
                use_test = os.getenv('TEST_MODE', 'false').lower() == 'true'
                parent_folder_id = os.getenv('TEST_FACTUREN_FOLDER_ID') if use_test else os.getenv('FACTUREN_FOLDER_ID')
                
                if parent_folder_id:
                    drive_result = drive_service.create_folder(folder_name, parent_folder_id)
                    print(f"Created Google Drive folder: {folder_name} in {'test' if use_test else 'production'} parent for tenant {tenant}", flush=True)
                    return jsonify({'success': True, 'path': folder_path, 'drive_folder': drive_result})
            except Exception as drive_error:
                print(f"Google Drive folder creation failed for tenant {tenant}: {drive_error}", flush=True)
            
            return jsonify({'success': True, 'path': folder_path})
        return jsonify({'success': False, 'error': 'No folder name provided'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
