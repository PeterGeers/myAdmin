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

import json
import logging
import os

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant
from database import DatabaseManager
from routes.error_responses import error_response
from services.credential_service import CredentialService

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
tenant_admin_credentials_bp = Blueprint(
    "tenant_admin_credentials", __name__, url_prefix="/api/tenant-admin"
)

# Allowed file extensions
ALLOWED_EXTENSIONS = {"json"}


def allowed_file(filename) -> bool:
    """Check if file extension is allowed"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@tenant_admin_credentials_bp.route("/credentials", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
def upload_credentials(user_email, user_roles) -> ResponseReturnValue:
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
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]

        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        # Get credential type
        credential_type = request.form.get("credential_type", "google_drive")

        # Validate file type
        if not allowed_file(file.filename):
            return jsonify(
                {"error": "Invalid file type. Only JSON files are allowed"}
            ), 400

        # Read and parse JSON
        try:
            content = file.read().decode("utf-8")
            credentials_data = json.loads(content)
        except json.JSONDecodeError:
            # Do not echo the parser message (may contain uploaded-content fragments).
            return jsonify({"error": "Invalid JSON file"}), 400
        except Exception:
            return jsonify({"error": "Failed to read file"}), 400

        # Initialize credential service
        db = DatabaseManager()
        credential_service = CredentialService(db)

        # Store encrypted credentials
        credential_service.store_credential(tenant, credential_type, credentials_data)

        # Test connectivity (for Google Drive)
        test_result = None
        if credential_type == "google_drive":
            test_result = _test_google_drive_connectivity(credentials_data)

        logger.info(
            f"Credentials uploaded for tenant {tenant}, type {credential_type} by {user_email}"
        )

        return jsonify(
            {
                "success": True,
                "message": f"Credentials uploaded successfully for {credential_type}",
                "credential_type": credential_type,
                "tenant": tenant,
                "test_result": test_result,
            }
        ), 201

    except Exception as e:
        return error_response(
            e,
            "Failed to upload credentials",
            status=500,
            include_success=False,
            log_context="Error uploading credentials",
        )


@tenant_admin_credentials_bp.route("/credentials", methods=["GET"])
@cognito_required(required_roles=["Tenant_Admin"])
def get_credentials_status(user_email, user_roles) -> ResponseReturnValue:
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
        db = DatabaseManager()
        credential_service = CredentialService(db)

        # Get list of credential types
        credentials = credential_service.list_credential_types(tenant)

        return jsonify(
            {
                "success": True,
                "tenant": tenant,
                "credentials": credentials,
                "count": len(credentials),
            }
        )

    except Exception as e:
        return error_response(
            e,
            "Failed to get credentials status",
            status=500,
            include_success=False,
            log_context="Error getting credentials status",
        )


@tenant_admin_credentials_bp.route("/credentials/test", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
def test_credentials(user_email, user_roles) -> ResponseReturnValue:
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
        credential_type = data.get("credential_type", "google_drive")

        # Initialize credential service
        db = DatabaseManager()
        credential_service = CredentialService(db)

        # Get client credentials from google_drive_credentials for OAuth token testing
        client_creds = credential_service.get_credential(
            tenant, "google_drive_credentials"
        )
        client_id = None
        client_secret = None

        if client_creds:
            if "installed" in client_creds:
                client_id = client_creds["installed"].get("client_id")
                client_secret = client_creds["installed"].get("client_secret")
            elif "web" in client_creds:
                client_id = client_creds["web"].get("client_id")
                client_secret = client_creds["web"].get("client_secret")

        # If testing google_drive (generic), try all google_drive_* types
        if credential_type.startswith("google_drive"):
            # Try to find a working credential
            # Priority: google_drive_token > google_drive_oauth > google_drive_credentials
            types_to_try = [
                "google_drive_token",
                "google_drive_oauth",
                "google_drive_credentials",
            ]

            for cred_type in types_to_try:
                credentials = credential_service.get_credential(tenant, cred_type)
                if credentials:
                    logger.info(f"Testing {cred_type}")
                    test_result = _test_google_drive_connectivity(
                        credentials,
                        client_id,
                        client_secret,
                        tenant=tenant,
                        credential_service=credential_service,
                    )

                    # If successful or not a client secrets file, return result
                    if test_result[
                        "success"
                    ] or "client secrets" not in test_result.get("message", ""):
                        return jsonify(
                            {
                                "success": True,
                                "credential_type": cred_type,
                                "tenant": tenant,
                                "test_result": test_result,
                            }
                        )

            # If we get here, no working credentials found
            return jsonify(
                {
                    "success": False,
                    "error": "No testable Google Drive credentials found. Please upload token.json or use OAuth flow.",
                }
            ), 404
        else:
            # Test specific credential type
            credentials = credential_service.get_credential(tenant, credential_type)

            if not credentials:
                return jsonify(
                    {
                        "success": False,
                        "error": f"No credentials found for {credential_type}",
                    }
                ), 404

            # Test connectivity based on type
            # Map credential types to test functions
            if credential_type.startswith("google_drive"):
                test_result = _test_google_drive_connectivity(
                    credentials,
                    client_id,
                    client_secret,
                    tenant=tenant,
                    credential_service=credential_service,
                )
            elif credential_type == "s3":
                test_result = {
                    "success": False,
                    "message": "S3 testing not yet implemented",
                }
            elif credential_type == "azure_blob":
                test_result = {
                    "success": False,
                    "message": "Azure Blob testing not yet implemented",
                }
            else:
                test_result = {
                    "success": False,
                    "message": f"Testing not implemented for {credential_type}",
                }

            return jsonify(
                {
                    "success": True,
                    "credential_type": credential_type,
                    "tenant": tenant,
                    "test_result": test_result,
                }
            )

    except Exception as e:
        return error_response(
            e,
            "Failed to test credentials",
            status=500,
            include_success=False,
            log_context="Error testing credentials",
        )


@tenant_admin_credentials_bp.route("/credentials/oauth/start", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
def start_oauth_flow(user_email, user_roles) -> ResponseReturnValue:
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
        service = data.get("service", "google_drive")

        if service != "google_drive":
            return jsonify({"error": f"OAuth not supported for {service}"}), 400

        # Get client credentials from database
        db = DatabaseManager()
        credential_service = CredentialService(db)

        client_creds = credential_service.get_credential(
            tenant, "google_drive_credentials"
        )

        if not client_creds:
            return jsonify(
                {
                    "error": "Google Drive credentials not found. Please upload credentials.json first."
                }
            ), 400

        # Extract client_id from credentials
        client_id = None
        if "installed" in client_creds:
            client_id = client_creds["installed"].get("client_id")
        elif "web" in client_creds:
            client_id = client_creds["web"].get("client_id")

        if not client_id:
            return jsonify(
                {"error": "Invalid credentials.json format - missing client_id"}
            ), 400

        # Generate OAuth URL
        import secrets

        state_token = secrets.token_urlsafe(32)

        # Store state token in session or database
        # For now, we'll return it and expect it back in callback

        # Build OAuth URL (Google Drive). All query params MUST be URL-encoded —
        # `redirect_uri` contains `://` and `/` which, if inserted raw, corrupt the
        # query string so Google receives a different redirect_uri than is registered
        # on the OAuth client → "Error 400: redirect_uri_mismatch". urlencode() does
        # the correct percent-encoding for every value.
        from urllib.parse import urlencode

        redirect_uri = os.getenv(
            "GOOGLE_REDIRECT_URI",
            "http://localhost:5000/api/tenant-admin/credentials/oauth/callback",
        )

        oauth_params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/drive",
            "access_type": "offline",
            "state": state_token,
            "prompt": "consent",
        }
        oauth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            oauth_params
        )

        logger.info(
            f"OAuth flow started for tenant {tenant}, service {service} by {user_email}"
        )

        return jsonify(
            {
                "success": True,
                "oauth_url": oauth_url,
                "state_token": state_token,
                "service": service,
                "tenant": tenant,
            }
        )

    except Exception as e:
        return error_response(
            e,
            "Failed to start OAuth flow",
            status=500,
            include_success=False,
            log_context="Error starting OAuth flow",
        )


@tenant_admin_credentials_bp.route("/credentials/oauth/callback", methods=["GET"])
def oauth_callback_public() -> ResponseReturnValue:
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
        code = request.args.get("code")
        state = request.args.get("state")
        error = request.args.get("error")

        if error:
            # OAuth was denied or failed. Do NOT reflect the attacker-controllable
            # `error` query param into the page at all (reflected-XSS defense): the
            # parent window only needs a fixed `oauth_error` signal, and the real
            # reason is logged server-side. A static page carries no user input.
            logger.warning("OAuth callback returned error for tenant")
            return (
                """
            <html>
                <body>
                    <h2>Authorization Failed</h2>
                    <p>Authorization was not completed. You can close this window.</p>
                    <script>
                        window.opener.postMessage({
                            type: 'oauth_error',
                            error: 'authorization_failed'
                        }, '*');
                        setTimeout(() => window.close(), 2000);
                    </script>
                </body>
            </html>
            """,
                400,
            )

        if not code or not state:
            return (
                """
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
            """,
                400,
            )

        # Return success page that will notify the parent window with the code
        # The parent window will then call the /complete endpoint to exchange the code
        # code/state come from the query string; JSON-encode them for the JS-string
        # context so they cannot break out of the literal (reflected-XSS defense).
        safe_code_js = json.dumps(code)
        safe_state_js = json.dumps(state)
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
                        code: {safe_code_js},
                        state: {safe_state_js}
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
        # Do NOT leak str(e) into the client HTML/JS (CodeQL information-exposure +
        # reflected-XSS). The full exception is logged above; show a generic message.
        return (
            """
        <html>
            <body>
                <h2>Error</h2>
                <p>An error occurred completing authorization. You can close this window.</p>
                <script>
                    window.opener.postMessage({
                        type: 'oauth_error',
                        error: 'callback_error'
                    }, '*');
                    setTimeout(() => window.close(), 2000);
                </script>
            </body>
        </html>
        """,
            500,
        )


@tenant_admin_credentials_bp.route("/credentials/oauth/complete", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
def oauth_complete(user_email, user_roles) -> ResponseReturnValue:
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
        code = data.get("code")
        state = data.get("state")
        service = data.get("service", "google_drive")

        if not code:
            return jsonify({"error": "Authorization code is required"}), 400

        if not state:
            return jsonify({"error": "State token is required"}), 400

        # Validate state token (in production, check against stored token)
        # For now, we'll accept any state token

        # Exchange code for tokens
        if service == "google_drive":
            # Get client credentials from database
            db = DatabaseManager()
            credential_service = CredentialService(db)

            client_creds = credential_service.get_credential(
                tenant, "google_drive_credentials"
            )

            if not client_creds:
                return jsonify(
                    {
                        "error": "Google Drive credentials not found. Please upload credentials.json first."
                    }
                ), 400

            # Extract client_id and client_secret
            client_id = None
            client_secret = None
            if "installed" in client_creds:
                client_id = client_creds["installed"].get("client_id")
                client_secret = client_creds["installed"].get("client_secret")
            elif "web" in client_creds:
                client_id = client_creds["web"].get("client_id")
                client_secret = client_creds["web"].get("client_secret")

            if not client_id or not client_secret:
                return jsonify(
                    {
                        "error": "Invalid credentials.json format - missing client_id or client_secret"
                    }
                ), 400

            # Exchange code for tokens with proper structure
            tokens = _exchange_google_code_for_tokens(code, client_id, client_secret)

            if not tokens:
                return jsonify({"error": "Failed to exchange code for tokens"}), 500

            # Store tokens (use google_drive_token type for consistency with GoogleDriveService)
            credential_service.store_credential(tenant, "google_drive_token", tokens)

            logger.info(
                f"OAuth tokens stored for tenant {tenant}, service {service} by {user_email}"
            )

            return jsonify(
                {
                    "success": True,
                    "message": "OAuth tokens stored successfully",
                    "service": service,
                    "tenant": tenant,
                }
            )
        else:
            return jsonify({"error": f"OAuth not supported for {service}"}), 400

    except Exception as e:
        return error_response(
            e,
            "OAuth callback failed",
            status=500,
            include_success=False,
            log_context="Error in OAuth callback",
        )


# ============================================================================
# Helper Functions
# ============================================================================


def _test_google_drive_connectivity(
    credentials,
    client_id=None,
    client_secret=None,
    tenant=None,
    credential_service=None,
) -> dict:
    """Test Google Drive connectivity. Delegates to google_oauth_service."""
    from services.google_oauth_service import test_google_drive_connectivity

    return test_google_drive_connectivity(
        credentials,
        client_id=client_id,
        client_secret=client_secret,
        tenant=tenant,
        credential_service=credential_service,
    )


def _exchange_google_code_for_tokens(code, client_id, client_secret) -> dict | None:
    """Exchange OAuth code for tokens. Delegates to google_oauth_service."""
    from services.google_oauth_service import exchange_google_code_for_tokens

    return exchange_google_code_for_tokens(code, client_id, client_secret)
