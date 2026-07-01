"""
Email Verification Service

Manages SES email identity verification per tenant. Handles initiating verification,
checking status, resending verification emails, updating email addresses, and
providing fast DB lookups for verified sender resolution during invoice sending.
"""

import os
import re
import logging
from datetime import datetime
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from database import DatabaseManager
from db_exceptions import DatabaseError

logger = logging.getLogger(__name__)

# Rate limit: 60 seconds between resend requests
RESEND_COOLDOWN_SECONDS = 60


class EmailVerificationService:
    """Manages SES email identity verification per tenant."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None, region: str = None,
                 test_mode: bool = False):
        """Initialize the service with database manager and SES client.

        Args:
            db_manager: DatabaseManager instance. If None, creates one using test_mode.
            region: AWS region for SES. Defaults to AWS_REGION env var or 'eu-west-1'.
            test_mode: Whether to use test database.
        """
        self.db = db_manager or DatabaseManager(test_mode=test_mode)
        self.region = region or os.getenv('AWS_REGION', 'eu-west-1')
        self.ses_client = boto3.client('ses', region_name=self.region)

    def _validate_email(self, email: str) -> bool:
        """RFC 5322 basic email format validation.

        Checks:
        - Contains exactly one '@'
        - Non-empty local part
        - Non-empty domain part with at least one dot
        - No spaces

        Args:
            email: Email address string to validate.

        Returns:
            True if valid, False otherwise.
        """
        if not email or not isinstance(email, str):
            return False

        email = email.strip()

        if ' ' in email:
            return False

        # Basic RFC 5322 pattern: local@domain.tld
        pattern = r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def initiate_verification(self, administration: str, email: str) -> dict:
        """Call SES VerifyEmailIdentity and store pending record.

        Non-blocking: logs errors and stores failed status without raising exceptions.

        Args:
            administration: Tenant identifier.
            email: Email address to verify.

        Returns:
            {'success': bool, 'status': str, 'error': str|None}
        """
        if not self._validate_email(email):
            return {
                'success': False,
                'status': 'failed',
                'error': 'Invalid email format'
            }

        try:
            self.ses_client.verify_email_identity(EmailAddress=email)
            logger.info(
                f"SES VerifyEmailIdentity called for {email} "
                f"(tenant: {administration})"
            )
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = e.response['Error']['Message']
            logger.error(
                f"SES VerifyEmailIdentity failed for {email} "
                f"(tenant: {administration}): [{error_code}] {error_msg}"
            )
            # Store failed record — non-blocking
            self._store_verification_record(administration, email, 'failed')
            return {
                'success': False,
                'status': 'failed',
                'error': f"{error_code}: {error_msg}"
            }
        except Exception as e:
            logger.error(
                f"Unexpected error calling SES for {email} "
                f"(tenant: {administration}): {e}"
            )
            self._store_verification_record(administration, email, 'failed')
            return {
                'success': False,
                'status': 'failed',
                'error': str(e)
            }

        # Store pending record
        self._store_verification_record(administration, email, 'pending')
        return {
            'success': True,
            'status': 'pending',
            'error': None
        }

    def check_status(self, administration: str) -> dict:
        """Query SES GetIdentityVerificationAttributes, sync DB, return current state.

        Args:
            administration: Tenant identifier.

        Returns:
            {'success': bool, 'email': str|None, 'status': str|None, 'last_checked': str|None}
        """
        # Get current active record from DB
        record = self._get_active_record(administration)
        if not record:
            return {
                'success': True,
                'email': None,
                'status': None,
                'last_checked': None
            }

        email = record['email']

        try:
            response = self.ses_client.get_identity_verification_attributes(
                Identities=[email]
            )
            attributes = response.get('VerificationAttributes', {})
            identity_info = attributes.get(email, {})
            ses_status = identity_info.get('VerificationStatus', '')

            # Map SES status to local status
            status = self._map_ses_status(ses_status)

            # Update DB with new status and last_checked timestamp
            now = datetime.utcnow()
            self._update_verification_status(administration, email, status, now)

            last_checked_str = now.strftime('%Y-%m-%dT%H:%M:%SZ')

            return {
                'success': True,
                'email': email,
                'status': status,
                'last_checked': last_checked_str
            }

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = e.response['Error']['Message']
            logger.error(
                f"SES GetIdentityVerificationAttributes failed for {email} "
                f"(tenant: {administration}): [{error_code}] {error_msg}"
            )
            # Return cached DB status with warning
            last_checked = record.get('last_checked_at')
            last_checked_str = (
                last_checked.strftime('%Y-%m-%dT%H:%M:%SZ')
                if last_checked else None
            )
            return {
                'success': True,
                'email': email,
                'status': record['status'],
                'last_checked': last_checked_str
            }
        except Exception as e:
            logger.error(
                f"Unexpected error checking status for {email} "
                f"(tenant: {administration}): {e}"
            )
            last_checked = record.get('last_checked_at')
            last_checked_str = (
                last_checked.strftime('%Y-%m-%dT%H:%M:%SZ')
                if last_checked else None
            )
            return {
                'success': True,
                'email': email,
                'status': record['status'],
                'last_checked': last_checked_str
            }

    def resend_verification(self, administration: str) -> dict:
        """Re-call VerifyEmailIdentity with rate limiting (60s cooldown).

        Args:
            administration: Tenant identifier.

        Returns:
            {'success': bool, 'error': str|None}
        """
        record = self._get_active_record(administration)
        if not record:
            return {
                'success': False,
                'error': 'No verification record found'
            }

        # Rate limiting check
        last_resend = record.get('last_resend_at')
        if last_resend:
            elapsed = (datetime.utcnow() - last_resend).total_seconds()
            if elapsed < RESEND_COOLDOWN_SECONDS:
                return {
                    'success': False,
                    'error': 'Please wait 60 seconds before resending'
                }

        email = record['email']

        try:
            self.ses_client.verify_email_identity(EmailAddress=email)
            logger.info(
                f"SES VerifyEmailIdentity resent for {email} "
                f"(tenant: {administration})"
            )
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = e.response['Error']['Message']
            logger.error(
                f"SES resend failed for {email} "
                f"(tenant: {administration}): [{error_code}] {error_msg}"
            )
            return {
                'success': False,
                'error': f"{error_code}: {error_msg}"
            }
        except Exception as e:
            logger.error(
                f"Unexpected error resending for {email} "
                f"(tenant: {administration}): {e}"
            )
            return {
                'success': False,
                'error': str(e)
            }

        # Update record: set status to pending, update last_resend_at
        now = datetime.utcnow()
        try:
            self.db.execute_query(
                """UPDATE email_verifications
                   SET status = 'pending', last_resend_at = %s
                   WHERE administration = %s AND email = %s
                   AND status IN ('pending', 'failed', 'expired')""",
                (now, administration, email),
                fetch=False, commit=True
            )
        except DatabaseError as e:
            logger.error(f"DB error updating resend timestamp: {e}")

        return {
            'success': True,
            'error': None
        }

    def update_email(self, administration: str, new_email: str) -> dict:
        """Validate new email, initiate verification, mark old as 'replaced'.

        Args:
            administration: Tenant identifier.
            new_email: New email address to verify.

        Returns:
            {'success': bool, 'status': str, 'error': str|None}
        """
        if not self._validate_email(new_email):
            return {
                'success': False,
                'status': 'failed',
                'error': 'Invalid email format'
            }

        # Mark all existing active records as 'replaced'
        try:
            self.db.execute_query(
                """UPDATE email_verifications
                   SET status = 'replaced'
                   WHERE administration = %s
                   AND status IN ('pending', 'verified', 'failed', 'expired')""",
                (administration,),
                fetch=False, commit=True
            )
        except DatabaseError as e:
            logger.error(
                f"DB error marking old records as replaced "
                f"(tenant: {administration}): {e}"
            )
            return {
                'success': False,
                'status': 'failed',
                'error': 'Database error updating existing records'
            }

        # Initiate verification for the new email
        result = self.initiate_verification(administration, new_email)
        return result

    def get_verified_sender(self, administration: str) -> dict:
        """Fast DB lookup for invoice sending. No SES call.

        Returns the verified email and company name for the tenant,
        or indicates that the tenant is not verified.

        Args:
            administration: Tenant identifier.

        Returns:
            {'verified': bool, 'email': str|None, 'company_name': str|None}
        """
        try:
            rows = self.db.execute_query(
                """SELECT email FROM email_verifications
                   WHERE administration = %s AND status = 'verified'
                   ORDER BY verified_at DESC
                   LIMIT 1""",
                (administration,)
            )
        except DatabaseError as e:
            logger.error(f"DB error in get_verified_sender: {e}")
            return {'verified': False, 'email': None, 'company_name': None}

        if not rows:
            return {'verified': False, 'email': None, 'company_name': None}

        email = rows[0]['email']

        # Get company name from parameters
        company_name = self._get_company_name(administration)

        return {
            'verified': True,
            'email': email,
            'company_name': company_name
        }

    def mark_expired(self, administration: str, email: str) -> None:
        """Mark a verification record as expired (called on SES send failure).

        Args:
            administration: Tenant identifier.
            email: Email address to mark as expired.
        """
        try:
            self.db.execute_query(
                """UPDATE email_verifications
                   SET status = 'expired'
                   WHERE administration = %s AND email = %s
                   AND status = 'verified'""",
                (administration, email),
                fetch=False, commit=True
            )
            logger.warning(
                f"Verification marked as expired for {email} "
                f"(tenant: {administration})"
            )
        except DatabaseError as e:
            logger.error(
                f"DB error marking expired for {email} "
                f"(tenant: {administration}): {e}"
            )

    # -------------------------------------------------------------------------
    # Private helper methods
    # -------------------------------------------------------------------------

    def _store_verification_record(self, administration: str, email: str,
                                   status: str) -> None:
        """Insert or update a verification record in the database.

        Args:
            administration: Tenant identifier.
            email: Email address.
            status: Verification status to set.
        """
        now = datetime.utcnow()
        verified_at = now if status == 'verified' else None

        try:
            self.db.execute_query(
                """INSERT INTO email_verifications
                   (administration, email, status, initiated_at, verified_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (administration, email, status, now, verified_at),
                fetch=False, commit=True
            )
        except DatabaseError as e:
            logger.error(
                f"DB error storing verification record for {email} "
                f"(tenant: {administration}): {e}"
            )

    def _get_active_record(self, administration: str) -> Optional[dict]:
        """Get the most recent active verification record for a tenant.

        Active means status is not 'replaced'.

        Args:
            administration: Tenant identifier.

        Returns:
            Dict with record data or None if no active record exists.
        """
        try:
            rows = self.db.execute_query(
                """SELECT email, status, last_checked_at, last_resend_at,
                          initiated_at, verified_at
                   FROM email_verifications
                   WHERE administration = %s
                   AND status IN ('pending', 'verified', 'failed', 'expired')
                   ORDER BY initiated_at DESC
                   LIMIT 1""",
                (administration,)
            )
            return rows[0] if rows else None
        except DatabaseError as e:
            logger.error(
                f"DB error getting active record (tenant: {administration}): {e}"
            )
            return None

    def _update_verification_status(self, administration: str, email: str,
                                    status: str, checked_at: datetime) -> None:
        """Update the verification status and last_checked_at timestamp.

        Args:
            administration: Tenant identifier.
            email: Email address.
            status: New status value.
            checked_at: Timestamp of the status check.
        """
        verified_at_clause = ", verified_at = %s" if status == 'verified' else ""
        params = [status, checked_at]
        if status == 'verified':
            params.append(checked_at)
        params.extend([administration, email])

        try:
            self.db.execute_query(
                f"""UPDATE email_verifications
                    SET status = %s, last_checked_at = %s{verified_at_clause}
                    WHERE administration = %s AND email = %s
                    AND status IN ('pending', 'verified', 'failed', 'expired')""",
                tuple(params),
                fetch=False, commit=True
            )
        except DatabaseError as e:
            logger.error(
                f"DB error updating status for {email} "
                f"(tenant: {administration}): {e}"
            )

    def _map_ses_status(self, ses_status: str) -> str:
        """Map SES verification status to local status.

        Args:
            ses_status: SES status string ('Success', 'Pending', 'Failed', etc.)

        Returns:
            Local status string ('verified', 'pending', 'failed').
        """
        mapping = {
            'Success': 'verified',
            'Pending': 'pending',
            'Failed': 'failed',
            'TemporaryFailure': 'pending',
            'NotStarted': 'failed',
        }
        return mapping.get(ses_status, 'failed')

    def _get_company_name(self, administration: str) -> Optional[str]:
        """Get the company name for a tenant from parameters.

        Attempts to read zzp_branding.company_name from the parameters table.

        Args:
            administration: Tenant identifier.

        Returns:
            Company name string or None.
        """
        try:
            rows = self.db.execute_query(
                """SELECT value FROM parameters
                   WHERE namespace = 'zzp_branding'
                   AND `key` = 'company_name'
                   AND scope = 'tenant'
                   AND scope_id = %s
                   LIMIT 1""",
                (administration,)
            )
            if rows:
                # Value is stored as JSON string, strip quotes if present
                val = rows[0]['value']
                if isinstance(val, str) and val.startswith('"') and val.endswith('"'):
                    val = val[1:-1]
                return val
            return None
        except DatabaseError as e:
            logger.error(f"DB error getting company name (tenant: {administration}): {e}")
            return None
