"""
Google Drive OAuth Routes
Handles OAuth authentication flow for Google Drive integration
"""

from flask import Blueprint, request, jsonify, redirect, session
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import os
import json
import logging
from auth.cognito_utils import cognito_required
from services.credential_service import CredentialService
from database import DatabaseManager

logger = logging.getLogger(__name__)

google_drive_oauth_bp = Blueprint('google_drive_oauth', __name__)

# OAuth configuration
SCOPES = ['https://www.googleapis.com/auth/drive']
CLIENT_SECRETS_FILE = os.path.join(os.path.dirname(__file__), '..', 'credentials.json')

# Get the redirect URI from environment or use default
REDIRECT_URI = os.getenv('GOOGLE_OAUTH_REDIRECT_URI', 'http://localhost:3000/oauth/google-drive/callback')


@google_drive_oauth_bp.route('/api/google-drive/oauth/initiate', methods=['POST'])
@cognito_required(required_permissions=['admin'])
def initiate_oauth(user_email, user_roles):
    """
    Initiate OAuth flow for Google Drive
    
    Returns authorization URL for user to visit
    """
    try:
        data = request.get_json()
        administration = data.get('administration')
        
        if not administration:
            return jsonify({'error': 'Administration is required'}), 400
        
        # Create flow instance
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        # Generate authorization URL
        authorization_url, state = flow.authorization_url(
            access_type='offline',  # Request refresh token
            include_granted_scopes='true',
            prompt='consent'  # Force consent screen to get refresh token
        )
        
        # Store state and administration in session for callback
        session['oauth_state'] = state
        session['oauth_administration'] = administration
        session['oauth_user_email'] = user_email
        
        logger.info(f"OAuth flow initiated for administration: {administration}")
        
        return jsonify({
            'success': True,
            'authorization_url': authorization_url,
            'state': state
        })
        
    except Exception as e:
        logger.error(f"Error initiating OAuth: {e}")
        return jsonify({'error': str(e)}), 500


@google_drive_oauth_bp.route('/api/google-drive/oauth/callback', methods=['GET'])
def oauth_callback():
    """
    Handle OAuth callback from Google
    
    This endpoint receives the authorization code and exchanges it for tokens
    """
    try:
        # Get state from session
        state = session.get('oauth_state')
        administration = session.get('oauth_administration')
        user_email = session.get('oauth_user_email')
        
        if not state or not administration:
            return jsonify({'error': 'Invalid OAuth state'}), 400
        
        # Verify state parameter
        if request.args.get('state') != state:
            return jsonify({'error': 'State mismatch'}), 400
        
        # Create flow instance
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            state=state,
            redirect_uri=REDIRECT_URI
        )
        
        # Exchange authorization code for tokens
        flow.fetch_token(authorization_response=request.url)
        
        # Get credentials
        credentials = flow.credentials
        
        # Store credentials in database
        db = DatabaseManager(test_mode=os.getenv('TEST_MODE', 'false').lower() == 'true')
        credential_service = CredentialService(db)
        
        # Store OAuth credentials
        oauth_creds = json.loads(open(CLIENT_SECRETS_FILE).read())
        credential_service.store_credential(
            administration,
            'google_drive_oauth',
            oauth_creds['installed']
        )
        
        # Store token
        token_info = json.loads(credentials.to_json())
        credential_service.store_credential(
            administration,
            'google_drive_token',
            token_info
        )
        
        logger.info(f"✅ OAuth completed successfully for administration: {administration}")
        logger.info(f"✅ Tokens stored in database for: {administration}")
        
        # Clear session
        session.pop('oauth_state', None)
        session.pop('oauth_administration', None)
        session.pop('oauth_user_email', None)
        
        # Redirect to success page
        return redirect(f'{os.getenv("FRONTEND_URL", "http://localhost:3000")}/oauth/success?service=google-drive')
        
    except Exception as e:
        logger.error(f"Error in OAuth callback: {e}")
        return redirect(f'{os.getenv("FRONTEND_URL", "http://localhost:3000")}/oauth/error?service=google-drive&error={str(e)}')


@google_drive_oauth_bp.route('/api/google-drive/oauth/status', methods=['GET'])
@cognito_required(required_permissions=['admin'])
def oauth_status(user_email, user_roles):
    """
    Check OAuth status for an administration
    
    Returns whether Google Drive is connected and token health
    """
    try:
        administration = request.args.get('administration')
        
        if not administration:
            return jsonify({'error': 'Administration is required'}), 400
        
        db = DatabaseManager(test_mode=os.getenv('TEST_MODE', 'false').lower() == 'true')
        credential_service = CredentialService(db)
        
        # Check if credentials exist
        oauth_creds = credential_service.get_credential(administration, 'google_drive_oauth')
        token_data = credential_service.get_credential(administration, 'google_drive_token')
        
        if not oauth_creds or not token_data:
            return jsonify({
                'connected': False,
                'message': 'Google Drive not configured'
            })
        
        # Check token validity
        try:
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            
            if creds.valid:
                status = 'valid'
                message = 'Google Drive connected and working'
            elif creds.expired and creds.refresh_token:
                status = 'expired_but_refreshable'
                message = 'Token expired but can be refreshed automatically'
            else:
                status = 'invalid'
                message = 'Token invalid - reconnection required'
            
            return jsonify({
                'connected': True,
                'status': status,
                'message': message,
                'needs_reconnect': status == 'invalid'
            })
            
        except Exception as e:
            logger.error(f"Error checking token status: {e}")
            return jsonify({
                'connected': True,
                'status': 'error',
                'message': 'Error checking token status',
                'needs_reconnect': True
            })
        
    except Exception as e:
        logger.error(f"Error checking OAuth status: {e}")
        return jsonify({'error': str(e)}), 500
