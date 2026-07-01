"""
Google OAuth Service

Business logic for Google Drive OAuth flow and connectivity testing.
Split from tenant_admin_credentials.py for file size management.

Provides:
- test_google_drive_connectivity(): Test Drive access with credentials
- exchange_google_code_for_tokens(): Exchange OAuth code for tokens
"""

import os
import logging

logger = logging.getLogger(__name__)


def test_google_drive_connectivity(credentials, client_id=None, client_secret=None,
                                   tenant=None, credential_service=None) -> dict:
    """Test Google Drive connectivity with provided credentials.

    Args:
        credentials: Google Drive credentials (service account JSON or OAuth token)
        client_id: OAuth client ID (from google_drive_credentials or env)
        client_secret: OAuth client secret (from google_drive_credentials or env)
        tenant: Tenant identifier (needed for persisting refreshed tokens)
        credential_service: CredentialService instance (needed for persisting refreshed tokens)

    Returns:
        Dict with test results: success, message, accessible
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

                        # Persist refreshed token back to database
                        if tenant and credential_service:
                            try:
                                refreshed_token = {
                                    'token': creds.token,
                                    'refresh_token': creds.refresh_token,
                                    'token_uri': creds.token_uri,
                                    'client_id': creds.client_id,
                                    'client_secret': creds.client_secret,
                                    'scopes': list(creds.scopes) if creds.scopes else ['https://www.googleapis.com/auth/drive'],
                                    'expiry': creds.expiry.isoformat() + 'Z' if creds.expiry else None
                                }
                                credential_service.store_credential(tenant, 'google_drive_token', refreshed_token)
                                logger.info(f"Refreshed token persisted for tenant {tenant}")
                            except Exception as persist_error:
                                logger.warning(f"Token refresh succeeded but persistence failed: {persist_error}")

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


def exchange_google_code_for_tokens(code, client_id, client_secret) -> dict | None:
    """Exchange Google OAuth authorization code for tokens.

    Args:
        code: Authorization code from OAuth callback
        client_id: OAuth client ID from google_drive_credentials
        client_secret: OAuth client secret from google_drive_credentials

    Returns:
        Dict with complete token structure compatible with
        Credentials.from_authorized_user_info() or None if failed
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
