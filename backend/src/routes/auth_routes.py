"""
Auth Routes — Password Reset via SES

Replaces Cognito's built-in forgot-password email flow with our own SES-based
flow so all emails go through one system and are tracked in email_log.

Flow:
1. POST /api/auth/forgot-password  — generates a 6-digit code, stores it, sends via SES
2. POST /api/auth/confirm-reset    — validates code, sets new password via Cognito admin API

Endpoints are public (no JWT required — user is locked out).
Rate-limited by code expiry (10 minutes) and max 3 attempts.
"""

import os
import secrets
import logging
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
import boto3
from botocore.exceptions import ClientError
from database import DatabaseManager

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

AWS_REGION = os.getenv('AWS_REGION', 'eu-west-1')
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
CODE_EXPIRY_MINUTES = 10
MAX_ATTEMPTS = 3


def _generate_code() -> str:
    """Generate a cryptographically secure 6-digit code."""
    return f"{secrets.randbelow(1000000):06d}"


def _get_db():
    test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
    return DatabaseManager(test_mode=test_mode)


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """
    Send a password reset code via SES.

    Request: { "email": "user@example.com" }
    Response: { "success": true, "message": "..." }

    Always returns success (even if user doesn't exist) to prevent
    user enumeration attacks.
    """
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()

        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400

        # Verify user exists in Cognito (silently — don't reveal to caller)
        cognito = boto3.client('cognito-idp', region_name=AWS_REGION)
        try:
            user_response = cognito.admin_get_user(
                UserPoolId=USER_POOL_ID, Username=email
            )
            user_status = user_response.get('UserStatus', '')
        except ClientError:
            # User doesn't exist — return success anyway (anti-enumeration)
            logger.info(f"Password reset requested for non-existent user: {email}")
            return jsonify({
                'success': True,
                'message': 'If an account exists, a reset code has been sent.'
            })

        # Don't send reset codes to users in FORCE_CHANGE_PASSWORD status
        # They need a "Resend Invitation" from their Tenant Admin instead
        if user_status == 'FORCE_CHANGE_PASSWORD':
            logger.info(f"Password reset blocked for {email} (status: {user_status})")
            return jsonify({
                'success': True,
                'message': 'If an account exists, a reset code has been sent.'
            })

        # Get user's tenant for email logging
        administration = None
        for attr in user_response.get('UserAttributes', []):
            if attr['Name'] == 'custom:tenants':
                try:
                    import json
                    tenants = json.loads(attr['Value'])
                    administration = tenants[0] if tenants else None
                except Exception:
                    pass

        # Generate code and store in password_reset_codes table
        code = _generate_code()
        expires_at = datetime.utcnow() + timedelta(minutes=CODE_EXPIRY_MINUTES)
        db = _get_db()

        # Upsert: delete any existing code for this email, then insert new one
        db.execute_query(
            "DELETE FROM password_reset_codes WHERE email = %s",
            (email,), fetch=False, commit=True,
        )
        db.execute_query(
            """INSERT INTO password_reset_codes (email, code, expires_at, attempts)
               VALUES (%s, %s, %s, 0)""",
            (email, code, expires_at), fetch=False, commit=True,
        )

        # Send code via SES
        from services.ses_email_service import SESEmailService
        from services.email_template_service import EmailTemplateService

        ses = SESEmailService()
        email_service = EmailTemplateService(administration=administration)

        # Try to render a template, fall back to plain text
        try:
            html_content = email_service.render_template(
                template_name='password_reset',
                variables={
                    'email': email,
                    'code': code,
                    'expiry_minutes': CODE_EXPIRY_MINUTES,
                },
                format='html',
            )
        except Exception:
            html_content = None

        text_content = (
            f"Your password reset code is: {code}\n\n"
            f"This code expires in {CODE_EXPIRY_MINUTES} minutes.\n"
            f"If you did not request this, please ignore this email."
        )

        subject = "Password Reset Code — myAdmin"

        ses.send_email(
            to_email=email,
            subject=subject,
            html_body=html_content,
            text_body=text_content,
            email_type='password_reset',
            administration=administration,
        )

        logger.info(f"Password reset code sent to {email}")
        return jsonify({
            'success': True,
            'message': 'If an account exists, a reset code has been sent.'
        })

    except Exception as e:
        logger.error(f"Error in forgot-password: {e}")
        return jsonify({
            'success': True,
            'message': 'If an account exists, a reset code has been sent.'
        })


@auth_bp.route('/confirm-reset', methods=['POST'])
def confirm_reset_password():
    """
    Validate reset code and set new password.

    Request: { "email": "...", "code": "123456", "new_password": "..." }
    Response: { "success": true } or { "success": false, "error": "..." }
    """
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()
        code = (data.get('code') or '').strip()
        new_password = data.get('new_password') or data.get('newPassword', '')

        if not email or not code or not new_password:
            return jsonify({
                'success': False,
                'error': 'Email, code, and new password are required'
            }), 400

        db = _get_db()

        # Look up the code
        rows = db.execute_query(
            """SELECT code, expires_at, attempts
               FROM password_reset_codes
               WHERE email = %s""",
            (email,), fetch=True,
        )

        if not rows:
            return jsonify({
                'success': False,
                'error': 'No reset code found. Please request a new one.'
            }), 400

        row = rows[0]
        stored_code = row['code'] if isinstance(row, dict) else row[0]
        expires_at = row['expires_at'] if isinstance(row, dict) else row[1]
        attempts = row['attempts'] if isinstance(row, dict) else row[2]

        # Check expiry
        if datetime.utcnow() > expires_at:
            db.execute_query(
                "DELETE FROM password_reset_codes WHERE email = %s",
                (email,), fetch=False, commit=True,
            )
            return jsonify({
                'success': False,
                'error': 'Reset code has expired. Please request a new one.'
            }), 400

        # Check max attempts
        if attempts >= MAX_ATTEMPTS:
            db.execute_query(
                "DELETE FROM password_reset_codes WHERE email = %s",
                (email,), fetch=False, commit=True,
            )
            return jsonify({
                'success': False,
                'error': 'Too many attempts. Please request a new code.'
            }), 429

        # Validate code
        if code != stored_code:
            db.execute_query(
                """UPDATE password_reset_codes
                   SET attempts = attempts + 1
                   WHERE email = %s""",
                (email,), fetch=False, commit=True,
            )
            remaining = MAX_ATTEMPTS - attempts - 1
            return jsonify({
                'success': False,
                'error': f'Invalid code. {remaining} attempt(s) remaining.'
            }), 400

        # Code is valid — set new password via Cognito admin API
        cognito = boto3.client('cognito-idp', region_name=AWS_REGION)
        try:
            cognito.admin_set_user_password(
                UserPoolId=USER_POOL_ID,
                Username=email,
                Password=new_password,
                Permanent=True,
            )
        except ClientError as e:
            error_msg = e.response['Error']['Message']
            logger.error(f"Cognito password set failed for {email}: {error_msg}")
            return jsonify({
                'success': False,
                'error': f'Password update failed: {error_msg}'
            }), 400

        # Clean up the used code
        db.execute_query(
            "DELETE FROM password_reset_codes WHERE email = %s",
            (email,), fetch=False, commit=True,
        )

        logger.info(f"Password reset completed for {email}")
        return jsonify({
            'success': True,
            'message': 'Password has been reset successfully.'
        })

    except Exception as e:
        logger.error(f"Error in confirm-reset: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
