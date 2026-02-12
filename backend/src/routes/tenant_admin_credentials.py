"""
Tenant Admin Credentials Management Routes

This module provides API endpoints for Tenant_Admin role to manage credentials
for their tenant (Google Drive, OAuth tokens, etc.)

Endpoints:
- POST /api/tenant-admin/credentials - Upload credentials file
- GET /api/tenant-admin/credentials - Get credential status
- POST /api/tenant-admin/credentials/test - Test connectivity
- POST /api/tenant-admin/credentials/oauth/start - Start OAuth flow
- POST /api/tenant-admin/credentials/oauth/callback - OAuth callback
"""

from flask import Blueprint, jsonify, request
import os
import json
import logging
from werkzeug.utils import secure_filename

from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant
from database import DatabaseManager
from services.credential_service import CredentialService

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
tenant_admin_credentials_bp = Blueprint('tenant_admin_credentials', __name__, url_prefix='/api/tenant-admin')

# Allowed file extensions
ALLOWED_EXTENSIONS = {'json'}


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@tenant_admin_credentials_bp.route('/credentials', methods=['POST'])
@cognito_required(required_roles=['Tenant_Admin'])
def upload_credentials(user_email, user_roles):
    """
    Upload credentials file (JSON)
    
    Authorization: Tenant_Admin role required
    
    Request: multipart/form-data
    - file: JSON file with credentials
    - credential_type: Type of credential (google_drive, s3, etc.)
    
    Returns:
        JSON with upload status and test results
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get credential type
        credential_type = request.form.get('credential_type', 'google_drive')
        
        # Validate file type
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Only JSON files are allowed'}), 400
        
        # Read and parse JSON
        try:
            content = file.read().decode('utf-8')
            credentials_data = json.loads(content)
        except json.JSONDecodeError as e:
            return jsonify({'error': f'Invalid JSON file: {str(e)}'}), 400
        except Exception as e:
            return jsonify({'error': f'Failed to read file: {str(e)}'}), 400
        
        # Initialize credential service
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        credential_service = CredentialService(db)
        
        # Store encrypted credentials
        credential_service.store_credential(tenant, credential_type, credentials_data)
        
        # Test connectivity (for Google Drive)
        test_result = None
        if credential_type == 'google_drive':
            test_result = _test_google_drive_connectivity(credentials_data)
        
        logger.info(f"Credentials uploaded for tenant {tenant}, type {credential_type} by {user_email}")
        
        return jsonify({
            'success': True,
            'message': f'Credentials uploaded successfully for {credential_type}',
            'credential_type': credential_type,
            'tenant': tenant,
            'test_result': test_result
        }), 201
        
    except Exception as e:
        logger.error(f"Error uploading credentials: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@tenant_admin_credentials_bp.route('/credentials', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def get_credentials_status(user_email, user_roles):
    """
    Get credential status (without decrypted values)
    
    Authorization: Tenant_Admin role required
    
    Returns:
        JSON with list of credential types and their status
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Initialize credential service
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        credential_service = CredentialService(db)
        
        # Get list of credential types
        credentials = credential_service.list_credential_types(tenant)
        
        return jsonify({
            'success': True,
            'tenant': tenant,
            'credentials': credentials,
            'count': len(credentials)
        })
        
    except Exception as e:
        logger.error(f"Error getting credentials status: {e}")
        return jsonify({'error': str(e)}), 500


@tenant_admin_credentials_bp.route('/credentials/test', methods=['POST'])
@cognito_required(required_roles=['Tenant_Admin'])
def test_credentials(user_email, user_roles):
    """
    Test credential connectivity
    
    Authorization: Tenant_Admin role required
    
    Request body:
    {
        "credential_type": "google_drive"  // or specific type
    }
    
    Returns:
        JSON with test results
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Get request data
        data = request.get_json()
        credential_type = data.get('credential_type', 'google_drive')
        
        # Initialize credential service
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        credential_service = CredentialService(db)
        
        # Get client credentials from google_drive_credentials for OAuth token testing
        client_creds = credential_service.get_credential(tenant, 'google_drive_credentials')
        client_id = None
        client_secret = None
        
        if client_creds:
            if 'installed' in client_creds:
                client_id = client_creds['installed'].get('client_id')
                client_secret = client_creds['installed'].get('client_secret')
            elif 'web' in client_creds:
                client_id = client_creds['web'].get('client_id')
                client_secret = client_creds['web'].get('client_secret')
        
        # If testing google_drive (generic), try all google_drive_* types
        if credential_type.startswith('google_drive'):
            # Try to find a working credential
            # Priority: google_drive_token > google_drive_oauth > google_drive_credentials
            types_to_try = ['google_drive_token', 'google_drive_oauth', 'google_drive_credentials']
            
            for cred_type in types_to_try:
                credentials = credential_service.get_credential(tenant, cred_type)
                if credentials:
                    logger.info(f"Testing {cred_type}")
                    test_result = _test_google_drive_connectivity(credentials, client_id, client_secret)
                    
                    # If successful or not a client secrets file, return result
                    if test_result['success'] or 'client secrets' not in test_result.get('message', ''):
                        return jsonify({
                            'success': True,
                            'credential_type': cred_type,
                            'tenant': tenant,
                            'test_result': test_result
                        })
            
            # If we get here, no working credentials found
            return jsonify({
                'success': False,
                'error': 'No testable Google Drive credentials found. Please upload token.json or use OAuth flow.'
            }), 404
        else:
            # Test specific credential type
            credentials = credential_service.get_credential(tenant, credential_type)
            
            if not credentials:
                return jsonify({
                    'success': False,
                    'error': f'No credentials found for {credential_type}'
                }), 404
            
            # Test connectivity based on type
            # Map credential types to test functions
            if credential_type.startswith('google_drive'):
                test_result = _test_google_drive_connectivity(credentials, client_id, client_secret)
            elif credential_type == 's3':
                test_result = {
                    'success': False,
                    'message': 'S3 testing not yet implemented'
                }
            elif credential_type == 'azure_blob':
                test_result = {
                    'success': False,
                    'message': 'Azure Blob testing not yet implemented'
                }
            else:
                test_result = {
                    'success': False,
                    'message': f'Testing not implemented for {credential_type}'
                }
            
            return jsonify({
                'success': True,
                'credential_type': credential_type,
                'tenant': tenant,
                'test_result': test_result
            })
        
    except Exception as e:
        logger.error(f"Error testing credentials: {e}")
        return jsonify({'error': str(e)}), 500


@tenant_admin_credentials_bp.route('/credentials/oauth/start', methods=['POST'])
@cognito_required(required_roles=['Tenant_Admin'])
def start_oauth_flow(user_email, user_roles):
    """
    Start OAuth flow for Google Drive
    
    Authorization: Tenant_Admin role required
    
    Request body:
    {
        "service": "google_drive"
    }
    
    Returns:
        JSON with OAuth URL and state token
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Get request data
        data = request.get_json()
        service = data.get('service', 'google_drive')
        
        if service != 'google_drive':
            return jsonify({
                'error': f'OAuth not supported for {service}'
            }), 400
        
        # Get client credentials from database
        test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
        db = DatabaseManager(test_mode=test_mode)
        credential_service = CredentialService(db)
        
        client_creds = credential_service.get_credential(tenant, 'google_drive_credentials')
        
        if not client_creds:
            return jsonify({
                'error': 'Google Drive credentials not found. Please upload credentials.json first.'
            }), 400
        
        # Extract client_id from credentials
        client_id = None
        if 'installed' in client_creds:
            client_id = client_creds['installed'].get('client_id')
        elif 'web' in client_creds:
            client_id = client_creds['web'].get('client_id')
        
        if not client_id:
            return jsonify({
                'error': 'Invalid credentials.json format - missing client_id'
            }), 400
        
        # Generate OAuth URL
        import secrets
        state_token = secrets.token_urlsafe(32)
        
        # Store state token in session or database
        # For now, we'll return it and expect it back in callback
        
        # Build OAuth URL (Google Drive)
        redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/api/tenant-admin/credentials/oauth/callback')
        
        oauth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"response_type=code&"
            f"scope=https://www.googleapis.com/auth/drive&"
            f"access_type=offline&"
            f"state={state_token}&"
            f"prompt=consent"
        )
        
        logger.info(f"OAuth flow started for tenant {tenant}, service {service} by {user_email}")
        
        return jsonify({
            'success': True,
            'oauth_url': oauth_url,
            'state_token': state_token,
            'service': service,
            'tenant': tenant
        })
        
    except Exception as e:
        logger.error(f"Error starting OAuth flow: {e}")
        return jsonify({'error': str(e)}), 500


@tenant_admin_credentials_bp.route('/credentials/oauth/callback', methods=['GET'])
def oauth_callback_public():
    """
    Handle OAuth callback from Google (public endpoint)
    
    This endpoint is called by Google's OAuth redirect, so it cannot require authentication.
    It just displays a success page and sends the code to the parent window.
    
    Query parameters (GET):
        code: Authorization code from Google
        state: State token for CSRF protection
        
    Returns:
        HTML page that closes the popup and notifies the parent window
    """
    try:
        # Get request data from query params
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        
        if error:
            # OAuth was denied or failed
            return f"""
            <html>
                <body>
                    <h2>Authorization Failed</h2>
                    <p>Error: {error}</p>
                    <p>You can close this window.</p>
                    <script>
                        window.opener.postMessage({{
                            type: 'oauth_error',
                            error: '{error}'
                        }}, '*');
                        setTimeout(() => window.close(), 2000);
                    </script>
                </body>
            </html>
            """, 400
        
        if not code or not state:
            return """
            <html>
                <body>
                    <h2>Missing Parameters</h2>
                    <p>Missing code or state parameter.</p>
                    <p>You can close this window.</p>
                    <script>
                        window.opener.postMessage({
                            type: 'oauth_error',
                            error: 'missing_parameters'
                        }, '*');
                        setTimeout(() => window.close(), 2000);
                    </script>
                </body>
            </html>
            """, 400
        
        # Return success page that will notify the parent window with the code
        # The parent window will then call the /complete endpoint to exchange the code
        return f"""
        <html>
            <body>
                <h2>Authorization Successful!</h2>
                <p>Google Drive has been connected successfully.</p>
                <p>This window will close automatically...</p>
                <script>
                    // Send success message to parent window
                    window.opener.postMessage({{
                        type: 'oauth_success',
                        code: '{code}',
                        state: '{state}'
                    }}, '*');
                    
                    // Close window after 2 seconds
                    setTimeout(() => window.close(), 2000);
                </script>
            </body>
        </html>
        """
        
    except Exception as e:
        logger.error(f"Error in OAuth callback: {e}")
        import traceback
        traceback.print_exc()
        return f"""
        <html>
            <body>
                <h2>Error</h2>
                <p>{str(e)}</p>
                <p>You can close this window.</p>
                <script>
                    window.opener.postMessage({{
                        type: 'oauth_error',
                        error: '{str(e)}'
                    }}, '*');
                    setTimeout(() => window.close(), 2000);
                </script>
            </body>
        </html>
        """, 500


@tenant_admin_credentials_bp.route('/credentials/oauth/complete', methods=['POST'])
@cognito_required(required_roles=['Tenant_Admin'])
def oauth_complete(user_email, user_roles):
    """
    Complete OAuth flow by storing tokens (authenticated endpoint)
    
    This is called by the frontend after receiving the success message from the popup.
    
    Authorization: Tenant_Admin role required
    
    Request body:
    {
        "code": "authorization_code",
        "state": "state_token",
        "service": "google_drive"
    }
    
    Returns:
        JSON with success status
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Get request data
        data = request.get_json()
        code = data.get('code')
        state = data.get('state')
        service = data.get('service', 'google_drive')
        
        if not code:
            return jsonify({'error': 'Authorization code is required'}), 400
        
        if not state:
            return jsonify({'error': 'State token is required'}), 400
        
        # Validate state token (in production, check against stored token)
        # For now, we'll accept any state token
        
        # Exchange code for tokens
        if service == 'google_drive':
            # Get client credentials from database
            test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
            db = DatabaseManager(test_mode=test_mode)
            credential_service = CredentialService(db)
            
            client_creds = credential_service.get_credential(tenant, 'google_drive_credentials')
            
            if not client_creds:
                return jsonify({
                    'error': 'Google Drive credentials not found. Please upload credentials.json first.'
                }), 400
            
            # Extract client_id and client_secret
            client_id = None
            client_secret = None
            if 'installed' in client_creds:
                client_id = client_creds['installed'].get('client_id')
                client_secret = client_creds['installed'].get('client_secret')
            elif 'web' in client_creds:
                client_id = client_creds['web'].get('client_id')
                client_secret = client_creds['web'].get('client_secret')
            
            if not client_id or not client_secret:
                return jsonify({
                    'error': 'Invalid credentials.json format - missing client_id or client_secret'
                }), 400
            
            # Exchange code for tokens with proper structure
            tokens = _exchange_google_code_for_tokens(code, client_id, client_secret)
            
            if not tokens:
                return jsonify({'error': 'Failed to exchange code for tokens'}), 500
            
            # Store tokens (use google_drive_token type for consistency with GoogleDriveService)
            credential_service.store_credential(tenant, 'google_drive_token', tokens)
            
            logger.info(f"OAuth tokens stored for tenant {tenant}, service {service} by {user_email}")
            
            return jsonify({
                'success': True,
                'message': 'OAuth tokens stored successfully',
                'service': service,
                'tenant': tenant
            })
        else:
            return jsonify({'error': f'OAuth not supported for {service}'}), 400
        
    except Exception as e:
        logger.error(f"Error in OAuth callback: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Helper Functions
# ============================================================================


def _test_google_drive_connectivity(credentials, client_id=None, client_secret=None):
    """
    Test Google Drive connectivity with provided credentials
    
    Args:
        credentials: Google Drive credentials (service account JSON or OAuth token)
        client_id: OAuth client ID (from google_drive_credentials or env)
        client_secret: OAuth client secret (from google_drive_credentials or env)
    
    Returns:
        Dict with test results
    """
    try:
        from google.oauth2 import service_account
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        # Log credential structure for debugging
        logger.info(f"Testing credentials with keys: {list(credentials.keys()) if isinstance(credentials, dict) else 'not a dict'}")
        
        # Determine credential type and create appropriate credentials object
        if isinstance(credentials, dict):
            if 'type' in credentials and credentials.get('type') == 'service_account':
                # Service account credentials
                logger.info("Using service account credentials")
                creds = service_account.Credentials.from_service_account_info(
                    credentials,
                    scopes=['https://www.googleapis.com/auth/drive']
                )
            elif 'installed' in credentials or 'web' in credentials:
                # This is a client secrets file (credentials.json), not actual tokens
                # We can't test with this - need actual OAuth tokens
                logger.warning("Found client secrets file, not OAuth tokens")
                return {
                    'success': False,
                    'message': 'This is a client secrets file. Please use OAuth flow to generate tokens, or upload token.json instead.',
                    'accessible': False
                }
            elif 'token' in credentials or 'access_token' in credentials:
                # OAuth token credentials (token.json format)
                logger.info("Using OAuth token credentials")
                
                # Use provided client credentials or fall back to credentials
                cid = client_id or credentials.get('client_id')
                csecret = client_secret or credentials.get('client_secret')
                
                # Check if we have all required fields
                if not credentials.get('refresh_token'):
                    return {
                        'success': False,
                        'message': 'OAuth token is missing refresh_token. Cannot test expired tokens.',
                        'accessible': False
                    }
                
                if not cid or not csecret:
                    return {
                        'success': False,
                        'message': 'Missing client_id or client_secret. Please ensure google_drive_credentials is uploaded.',
                        'accessible': False
                    }
                
                # Build token data with all required fields
                token_data = {
                    'token': credentials.get('token') or credentials.get('access_token'),
                    'refresh_token': credentials.get('refresh_token'),
                    'token_uri': credentials.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    'client_id': cid,
                    'client_secret': csecret,
                    'scopes': credentials.get('scopes', ['https://www.googleapis.com/auth/drive'])
                }
                
                # Add expiry if present
                if 'expiry' in credentials:
                    token_data['expiry'] = credentials['expiry']
                
                logger.info(f"Token data keys: {list(token_data.keys())}")
                
                # Use from_authorized_user_info like GoogleDriveService does
                creds = Credentials.from_authorized_user_info(
                    token_data,
                    scopes=token_data['scopes']
                )
                
                # If token is expired, try to refresh it
                if creds.expired and creds.refresh_token:
                    logger.info("Token expired, attempting refresh...")
                    from google.auth.transport.requests import Request
                    try:
                        creds.refresh(Request())
                        logger.info("Token refreshed successfully")
                        
                        # TODO: Save refreshed token back to database
                        # This would require passing tenant and credential_service to this function
                        # For now, just log that refresh was successful
                        
                    except Exception as refresh_error:
                        logger.error(f"Token refresh failed: {refresh_error}")
                        return {
                            'success': False,
                            'message': f'Token expired and refresh failed: {str(refresh_error)}',
                            'accessible': False
                        }
            else:
                logger.warning(f"Unknown credential format. Keys: {list(credentials.keys())}")
                return {
                    'success': False,
                    'message': f'Unknown credential format. Found keys: {", ".join(list(credentials.keys())[:5])}',
                    'accessible': False
                }
        else:
            return {
                'success': False,
                'message': 'Invalid credential type (not a dictionary)',
                'accessible': False
            }
        
        # Build Drive service
        service = build('drive', 'v3', credentials=creds)
        
        # Test by listing files (limit 1)
        results = service.files().list(
            pageSize=1,
            fields="files(id, name)"
        ).execute()
        
        return {
            'success': True,
            'message': 'Google Drive connection successful',
            'accessible': True
        }
        
    except ImportError:
        return {
            'success': False,
            'message': 'Google Drive libraries not installed',
            'accessible': False
        }
    except Exception as e:
        logger.error(f"Google Drive connectivity test failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'message': f'Connection failed: {str(e)}',
            'accessible': False
        }


def _exchange_google_code_for_tokens(code, client_id, client_secret):
    """
    Exchange Google OAuth authorization code for tokens
    
    Args:
        code: Authorization code from OAuth callback
        client_id: OAuth client ID from google_drive_credentials
        client_secret: OAuth client secret from google_drive_credentials
    
    Returns:
        Dict with complete token structure compatible with Credentials.from_authorized_user_info()
        or None if failed
    """
    try:
        import requests
        from datetime import datetime, timedelta
        
        redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/api/tenant-admin/credentials/oauth/callback')
        
        # Exchange code for tokens
        response = requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'code': code,
                'client_id': client_id,
                'client_secret': client_secret,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code'
            }
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to exchange code: {response.status_code} - {response.text}")
            return None
        
        # Get raw token response
        token_response = response.json()
        logger.info(f"Received token response with keys: {list(token_response.keys())}")
        
        # Build complete token structure that matches what Credentials.from_authorized_user_info() expects
        # Reference: backend/src/google_drive_service.py lines 85-160
        
        # Calculate expiry datetime
        expires_in = token_response.get('expires_in', 3600)  # Default 1 hour
        expiry = datetime.utcnow() + timedelta(seconds=expires_in)
        
        # Build complete token structure
        complete_token = {
            'token': token_response.get('access_token'),
            'refresh_token': token_response.get('refresh_token'),
            'token_uri': 'https://oauth2.googleapis.com/token',
            'client_id': client_id,
            'client_secret': client_secret,
            'scopes': ['https://www.googleapis.com/auth/drive'],
            'expiry': expiry.isoformat() + 'Z'  # ISO format with Z suffix
        }
        
        logger.info(f"Built complete token structure with keys: {list(complete_token.keys())}")
        
        return complete_token
            
    except Exception as e:
        logger.error(f"Error exchanging code for tokens: {e}")
        import traceback
        traceback.print_exc()
        return None
