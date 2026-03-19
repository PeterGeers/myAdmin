"""
Signup Service

Business logic for trial signup flow:
- Create signup (Cognito user + pending_signups record)
- Verify signup (Cognito confirm + DB update)
- Resend verification code

Uses a separate myadmin_promo database for signup data isolation.
"""

import os
import re
import html
import boto3
import logging
import mysql.connector
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Valid property ranges
VALID_PROPERTY_RANGES = ['1-5', '6-20', '21-50', '50+']
VALID_LOCALES = ['nl', 'en']


class SignupService:
    """Service for trial signup operations"""

    def __init__(self):
        """Initialize Cognito client and promo DB config"""
        self.region = os.getenv('AWS_REGION', 'eu-west-1')
        self.user_pool_id = os.getenv('SIGNUP_COGNITO_USER_POOL_ID', os.getenv('COGNITO_USER_POOL_ID'))
        self.app_client_id = os.getenv('SIGNUP_COGNITO_APP_CLIENT_ID')
        self.csrf_secret = os.getenv('CSRF_SECRET', '')
        self.redirect_url = os.getenv('SIGNUP_REDIRECT_URL', 'https://app.myadmin.jabaki.nl/welcome')

        if not self.app_client_id:
            logger.warning("SIGNUP_COGNITO_APP_CLIENT_ID not set — signup will fail")

        self.cognito = boto3.client('cognito-idp', region_name=self.region)

        # Promo DB config (same server, different database)
        self.db_config = {
            'host': os.getenv('DB_HOST', os.getenv('RAILWAY_PRIVATE_DOMAIN', 'localhost')),
            'user': os.getenv('DB_USER', os.getenv('MYSQL_USER', 'root')),
            'password': os.getenv('DB_PASSWORD', os.getenv('MYSQL_PASSWORD', '')),
            'database': os.getenv('PROMO_DB_NAME', 'myadmin_promo'),
            'port': int(os.getenv('DB_PORT', '3306'))
        }


    def _get_connection(self):
        """Get a direct connection to the promo database"""
        return mysql.connector.connect(**self.db_config)

    # ========================================================================
    # Input Validation
    # ========================================================================

    def validate_signup_input(self, data: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, str]]]:
        """
        Validate signup input fields.
        Returns (is_valid, errors_dict or None)
        """
        errors = {}

        # Required fields
        first_name = self._sanitize(data.get('firstName', ''))
        if not first_name or len(first_name) > 50:
            errors['firstName'] = 'Required, max 50 characters'

        last_name = self._sanitize(data.get('lastName', ''))
        if not last_name or len(last_name) > 50:
            errors['lastName'] = 'Required, max 50 characters'

        email = data.get('email', '').strip().lower()
        if not email or not self._is_valid_email(email):
            errors['email'] = 'Valid email required'

        password = data.get('password', '')
        if not password or len(password) < 8:
            errors['password'] = 'Minimum 8 characters required'

        accepted_terms = data.get('acceptedTerms')
        if accepted_terms is not True:
            errors['acceptedTerms'] = 'Must accept terms and conditions'

        locale = data.get('locale', '')
        if locale not in VALID_LOCALES:
            errors['locale'] = f"Must be one of: {', '.join(VALID_LOCALES)}"

        # Optional fields with validation
        company_name = self._sanitize(data.get('companyName', '') or '')
        if len(company_name) > 100:
            errors['companyName'] = 'Max 100 characters'

        property_range = data.get('propertyRange', '')
        if property_range and property_range not in VALID_PROPERTY_RANGES:
            errors['propertyRange'] = f"Must be one of: {', '.join(VALID_PROPERTY_RANGES)}"

        referral_source = self._sanitize(data.get('referralSource', '') or '')
        if len(referral_source) > 50:
            errors['referralSource'] = 'Max 50 characters'

        if errors:
            return False, errors
        return True, None

    def _sanitize(self, value: str) -> str:
        """Strip HTML tags and escape special characters"""
        if not value:
            return ''
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', value)
        # Escape HTML entities
        clean = html.escape(clean)
        return clean.strip()

    def _is_valid_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def validate_csrf_token(self, token: str) -> bool:
        """Validate CSRF token against secret"""
        if not self.csrf_secret:
            logger.warning("CSRF_SECRET not configured — skipping validation")
            return True
        # Simple validation: token should match the secret
        # In production, use HMAC-based tokens with timestamps
        return token == self.csrf_secret

    def is_honeypot_filled(self, data: Dict[str, Any]) -> bool:
        """Check if honeypot field is filled (indicates bot)"""
        honeypot = data.get('honeypot', '')
        return bool(honeypot)


    # ========================================================================
    # Core Operations
    # ========================================================================

    def create_signup(self, data: Dict[str, Any], ip_address: str = None, user_agent: str = None) -> Dict[str, Any]:
        """
        Create a new trial signup:
        1. Create Cognito user
        2. Insert pending_signups record
        3. Send admin notification

        Returns dict with userId on success.
        Raises ValueError for validation errors, specific exceptions for Cognito errors.
        """
        email = data.get('email', '').strip().lower()
        first_name = self._sanitize(data.get('firstName', ''))
        last_name = self._sanitize(data.get('lastName', ''))
        password = data.get('password', '')
        company_name = self._sanitize(data.get('companyName', '') or '')
        property_range = data.get('propertyRange', '') or None
        referral_source = self._sanitize(data.get('referralSource', '') or '') or None
        locale = data.get('locale', 'nl')

        # 1. Create Cognito user
        try:
            response = self.cognito.sign_up(
                ClientId=self.app_client_id,
                Username=email,
                Password=password,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'name', 'Value': f"{first_name} {last_name}"},
                    {'Name': 'given_name', 'Value': first_name},
                    {'Name': 'family_name', 'Value': last_name}
                ]
            )
            cognito_user_id = response.get('UserSub')
            logger.info(f"Cognito user created: {email} (sub: {cognito_user_id})")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'UsernameExistsException':
                raise UsernameExistsError(f"Email {email} is already registered")
            logger.error(f"Cognito sign_up failed: {e}")
            raise

        # 2. Insert into pending_signups
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO pending_signups 
                   (cognito_user_id, email, first_name, last_name, company_name, 
                    property_range, referral_source, locale, ip_address, user_agent)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (cognito_user_id, email, first_name, last_name, company_name,
                 property_range, referral_source, locale, ip_address, user_agent)
            )
            conn.commit()
            logger.info(f"Pending signup inserted for {email}")
        except Exception as e:
            logger.error(f"DB insert failed for {email}: {e}")
            # Cognito user was created but DB failed — log for manual cleanup
            raise
        finally:
            cursor.close()
            conn.close()

        # 3. Send admin notification (non-blocking)
        try:
            self._send_admin_notification(
                'New Trial Signup',
                f"New signup from {first_name} {last_name} ({email})",
                {
                    'email': email,
                    'name': f"{first_name} {last_name}",
                    'company': company_name or 'N/A',
                    'property_range': property_range or 'N/A',
                    'referral': referral_source or 'N/A',
                    'locale': locale
                }
            )
        except Exception as e:
            logger.warning(f"Admin notification failed (non-critical): {e}")

        return {'userId': cognito_user_id}

    def verify_signup(self, email: str, code: str) -> Dict[str, Any]:
        """
        Verify email with Cognito confirmation code.
        Updates pending_signups status to 'verified'.
        """
        email = email.strip().lower()

        # Check pending_signups
        signup = self._get_pending_signup(email)
        if not signup:
            raise SignupNotFoundError(f"No pending signup for {email}")
        if signup['status'] == 'verified':
            raise AlreadyVerifiedError(f"Signup for {email} is already verified")

        # Confirm with Cognito
        try:
            self.cognito.confirm_sign_up(
                ClientId=self.app_client_id,
                Username=email,
                ConfirmationCode=code
            )
            logger.info(f"Cognito email verified: {email}")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'CodeMismatchException':
                raise InvalidCodeError("Invalid verification code")
            if error_code == 'ExpiredCodeException':
                raise InvalidCodeError("Verification code has expired")
            logger.error(f"Cognito confirm_sign_up failed: {e}")
            raise

        # Update DB
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE pending_signups 
                   SET status = 'verified', verified_at = NOW() 
                   WHERE email = %s""",
                (email,)
            )
            conn.commit()
            logger.info(f"Signup verified in DB: {email}")
        except Exception as e:
            logger.error(f"DB update failed for verification of {email}: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

        # Admin notification
        try:
            self._send_admin_notification(
                'Signup Verified — Ready for Provisioning',
                f"{email} has verified their email. Ready for tenant provisioning.",
                {'email': email, 'name': f"{signup['first_name']} {signup['last_name']}"}
            )
        except Exception as e:
            logger.warning(f"Admin notification failed (non-critical): {e}")

        return {'redirectUrl': self.redirect_url}

    def resend_verification(self, email: str) -> Dict[str, Any]:
        """
        Resend Cognito verification code.
        Rate limited: 1 per 60 seconds per email.
        """
        email = email.strip().lower()

        # Check pending_signups
        signup = self._get_pending_signup(email)
        if not signup:
            raise SignupNotFoundError(f"No pending signup for {email}")
        if signup['status'] == 'verified':
            raise AlreadyVerifiedError(f"Signup for {email} is already verified")

        # Rate limit: 60 seconds between resends
        last_resend = signup.get('last_resend_at')
        if last_resend:
            elapsed = (datetime.utcnow() - last_resend).total_seconds()
            if elapsed < 60:
                raise ResendRateLimitError(f"Please wait {int(60 - elapsed)} seconds before resending")

        # Resend via Cognito
        try:
            self.cognito.resend_confirmation_code(
                ClientId=self.app_client_id,
                Username=email
            )
            logger.info(f"Verification code resent for {email}")
        except ClientError as e:
            logger.error(f"Cognito resend_confirmation_code failed: {e}")
            raise

        # Update last_resend_at
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE pending_signups SET last_resend_at = NOW() WHERE email = %s",
                (email,)
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"DB update for last_resend_at failed: {e}")
        finally:
            cursor.close()
            conn.close()

        return {'message': 'Verification email resent'}

    # ========================================================================
    # Helpers
    # ========================================================================

    def _get_pending_signup(self, email: str) -> Optional[Dict[str, Any]]:
        """Look up a pending signup by email"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM pending_signups WHERE email = %s",
                (email,)
            )
            result = cursor.fetchone()
            return result
        except Exception as e:
            logger.error(f"DB lookup failed for {email}: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def _send_admin_notification(self, title: str, message: str, data: Dict[str, Any] = None):
        """Send admin notification via SNS (reuses existing pattern)"""
        try:
            from aws_notifications import get_notification_service
            service = get_notification_service()
            if service and service.is_enabled():
                service.send_business_notification(title, message, data)
            else:
                logger.info(f"SNS disabled — would send: {title}: {message}")
        except Exception as e:
            logger.warning(f"Notification send failed: {e}")


# ========================================================================
# Custom Exceptions
# ========================================================================

class UsernameExistsError(Exception):
    """Email already registered in Cognito"""
    pass

class SignupNotFoundError(Exception):
    """No pending signup found for email"""
    pass

class AlreadyVerifiedError(Exception):
    """Signup already verified"""
    pass

class InvalidCodeError(Exception):
    """Invalid or expired verification code"""
    pass

class ResendRateLimitError(Exception):
    """Resend attempted too soon"""
    pass
