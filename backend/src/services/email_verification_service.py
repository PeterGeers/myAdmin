"""
Email Verification Service

Manages SES email identity verification per tenant. Handles initiating verification,
checking status, resending verification emails, updating email addresses, and
providing fast DB lookups for verified sender resolution during invoice sending.
"""

import logging
import os
import re
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

from database import DatabaseManager
from db_exceptions import DatabaseError

logger = logging.getLogger(__name__)

# Rate limit: 60 seconds between resend requests
RESEND_COOLDOWN_SECONDS = 60


class EmailVerificationService:
    """Manages SES email identity verification per tenant."""

    def __init__(
        self,
        db_manager: DatabaseManager | None = None,
        region: str | None = None,
        ses_client=None,
    ):
        """Initialize the service with database manager and SES client.

        The SES client is injectable and resolved lazily (mirrors the SAM
        ``SesBotoSender`` seam): a real ``boto3.client("ses", ...)`` is built ONLY
        when no client is injected AND the lazy ``ses_client`` property is first
        accessed on an explicitly production-wired path. Tests / scripts / fuzz
        harnesses pass a fake (or never touch SES), so a non-production-wired
        construction never resolves a real client — closing the identity-burst seam.

        Args:
            db_manager: DatabaseManager instance. If None, creates one.
            region: AWS region for SES. Defaults to AWS_REGION env var or 'eu-west-1'.
            ses_client: Optional injected boto3 SES client (or compatible fake).
                Resolved lazily otherwise.
        """
        self.db = db_manager or DatabaseManager()
        self.region = region or os.getenv("AWS_REGION", "eu-west-1")
        self._ses_client = ses_client

    @property
    def ses_client(self):
        """The boto3 SES client, resolved lazily on first use.

        Resolves a real ``boto3.client("ses", region_name=self.region)`` ONLY when
        no client was injected (``self._ses_client is None``) — the explicitly
        production-wired path. Returns the injected/fake client otherwise. Internal
        callers use ``self.ses_client`` unchanged, so no call-site churn.
        """
        if self._ses_client is None:
            self._ses_client = boto3.client("ses", region_name=self.region)
        return self._ses_client

    def _validate_email(self, email: str) -> bool:
        """Deliverable-sender email validation (defense-in-depth, Concern B).

        This is deliberately NARROWER than the full RFC 5322 grammar. SES
        ``verify_email_identity`` creates a permanent, billable identity for
        whatever it is handed, so the one app path that legitimately reaches it
        must only accept plausible, deliverable sender addresses — never
        prototype-pollution keys, exploit special characters, or oversized /
        implausible domains that the broad RFC class would wave through.

        Rejected (returns False, never raises):
        - prototype-pollution keys anywhere in the local part
          (``__proto__``, ``constructor``, ``prototype``)
        - exploit / unsafe special characters in the local part
          (anything outside ``A-Z a-z 0-9 . + _ -``), which excludes
          ``| ^ # { } = ! ~ % & ' * / = ? $`` and friends
        - a domain without a sane dotted structure / plausible alpha TLD
        - oversized input: overall > 254, local part > 64, any domain label > 63

        Accepted: genuine deliverable addresses such as ``user@example.com``,
        ``first.last@example.com``, ``user+tag@example.com``,
        ``user@mail.example.co.uk``, ``info@h-dcn.nl`` — so
        ``initiate_verification`` / ``update_email`` still reach SES for real
        senders, preserving the existing success path and the
        ``{'success': False, 'status': 'failed', 'error': 'Invalid email format'}``
        shape for anything rejected here.

        Args:
            email: Email address string to validate.

        Returns:
            True if the address is a plausible deliverable sender, False otherwise.
        """
        if not email or not isinstance(email, str):
            return False

        email = email.strip()

        if " " in email:
            return False

        # Exactly one '@', both sides non-empty.
        if email.count("@") != 1:
            return False
        local, domain = email.split("@")
        if not local or not domain:
            return False

        # Overall / per-part length caps (RFC 5321 limits) — reject oversized.
        if len(email) > 254 or len(local) > 64:
            return False

        # Reject prototype-pollution keys anywhere in the local part.
        local_lower = local.lower()
        if any(key in local_lower for key in ("__proto__", "constructor", "prototype")):
            return False

        # Local part: narrow, deliverable-safe class only. Letters/digits plus the
        # common non-exploit separators (dot / plus / underscore / hyphen), with an
        # alphanumeric anchor at each end and no consecutive dots. This excludes the
        # exploit special characters (| ^ # { } = ! ~ % & ' * / = ? $ ...) that the
        # full RFC 5322 class accepts.
        local_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9._+-]*[a-zA-Z0-9])?$"
        if not re.match(local_pattern, local) or ".." in local:
            return False

        # Domain: one or more alphanumeric/hyphen labels (not starting/ending with a
        # hyphen, each <= 63 chars) separated by dots, ending in a plausible alpha TLD
        # of at least two letters. Guarantees a sane dotted domain.
        domain_pattern = (
            r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
            r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*"
            r"\.[a-zA-Z]{2,}$"
        )
        return bool(re.match(domain_pattern, domain))

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
                "success": False,
                "status": "failed",
                "error": "Invalid email format",
            }

        try:
            self.ses_client.verify_email_identity(EmailAddress=email)
            logger.info(
                f"SES VerifyEmailIdentity called for {email} (tenant: {administration})"
            )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_msg = e.response["Error"]["Message"]
            logger.error(
                f"SES VerifyEmailIdentity failed for {email} "
                f"(tenant: {administration}): [{error_code}] {error_msg}"
            )
            # Store failed record — non-blocking
            self._store_verification_record(administration, email, "failed")
            return {
                "success": False,
                "status": "failed",
                "error": f"{error_code}: {error_msg}",
            }
        except Exception:
            logger.exception(
                "Unexpected error calling SES for %s (tenant: %s)",
                email,
                administration,
            )
            self._store_verification_record(administration, email, "failed")
            return {
                "success": False,
                "status": "failed",
                "error": "Email verification failed. Please try again later.",
            }

        # Store pending record
        self._store_verification_record(administration, email, "pending")
        return {"success": True, "status": "pending", "error": None}

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
                "success": True,
                "email": None,
                "status": None,
                "last_checked": None,
            }

        email = record["email"]

        try:
            response = self.ses_client.get_identity_verification_attributes(
                Identities=[email]
            )
            attributes = response.get("VerificationAttributes", {})
            identity_info = attributes.get(email, {})
            ses_status = identity_info.get("VerificationStatus", "")

            # Map SES status to local status
            status = self._map_ses_status(ses_status)

            # Update DB with new status and last_checked timestamp
            now = datetime.utcnow()
            self._update_verification_status(administration, email, status, now)

            last_checked_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

            return {
                "success": True,
                "email": email,
                "status": status,
                "last_checked": last_checked_str,
            }

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_msg = e.response["Error"]["Message"]
            logger.error(
                f"SES GetIdentityVerificationAttributes failed for {email} "
                f"(tenant: {administration}): [{error_code}] {error_msg}"
            )
            # Return cached DB status with warning
            last_checked = record.get("last_checked_at")
            last_checked_str = (
                last_checked.strftime("%Y-%m-%dT%H:%M:%SZ") if last_checked else None
            )
            return {
                "success": True,
                "email": email,
                "status": record["status"],
                "last_checked": last_checked_str,
            }
        except Exception as e:
            logger.error(
                f"Unexpected error checking status for {email} "
                f"(tenant: {administration}): {e}"
            )
            last_checked = record.get("last_checked_at")
            last_checked_str = (
                last_checked.strftime("%Y-%m-%dT%H:%M:%SZ") if last_checked else None
            )
            return {
                "success": True,
                "email": email,
                "status": record["status"],
                "last_checked": last_checked_str,
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
            return {"success": False, "error": "No verification record found"}

        # Rate limiting check
        last_resend = record.get("last_resend_at")
        if last_resend:
            elapsed = (datetime.utcnow() - last_resend).total_seconds()
            if elapsed < RESEND_COOLDOWN_SECONDS:
                return {
                    "success": False,
                    "error": "Please wait 60 seconds before resending",
                }

        email = record["email"]

        try:
            self.ses_client.verify_email_identity(EmailAddress=email)
            logger.info(
                f"SES VerifyEmailIdentity resent for {email} (tenant: {administration})"
            )
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_msg = e.response["Error"]["Message"]
            logger.error(
                f"SES resend failed for {email} "
                f"(tenant: {administration}): [{error_code}] {error_msg}"
            )
            return {"success": False, "error": f"{error_code}: {error_msg}"}
        except Exception:
            logger.exception(
                "Unexpected error resending for %s (tenant: %s)",
                email,
                administration,
            )
            return {
                "success": False,
                "error": "Resend failed. Please try again later.",
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
                fetch=False,
                commit=True,
            )
        except DatabaseError as e:
            logger.error(f"DB error updating resend timestamp: {e}")

        return {"success": True, "error": None}

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
                "success": False,
                "status": "failed",
                "error": "Invalid email format",
            }

        # Mark all existing active records as 'replaced'
        try:
            self.db.execute_query(
                """UPDATE email_verifications
                   SET status = 'replaced'
                   WHERE administration = %s
                   AND status IN ('pending', 'verified', 'failed', 'expired')""",
                (administration,),
                fetch=False,
                commit=True,
            )
        except DatabaseError as e:
            logger.error(
                f"DB error marking old records as replaced "
                f"(tenant: {administration}): {e}"
            )
            return {
                "success": False,
                "status": "failed",
                "error": "Database error updating existing records",
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
                (administration,),
            )
        except DatabaseError as e:
            logger.error(f"DB error in get_verified_sender: {e}")
            return {"verified": False, "email": None, "company_name": None}

        if not rows:
            return {"verified": False, "email": None, "company_name": None}

        email = rows[0]["email"]

        # Get company name from parameters
        company_name = self._get_company_name(administration)

        return {"verified": True, "email": email, "company_name": company_name}

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
                fetch=False,
                commit=True,
            )
            logger.warning(
                f"Verification marked as expired for {email} (tenant: {administration})"
            )
        except DatabaseError as e:
            logger.error(
                f"DB error marking expired for {email} (tenant: {administration}): {e}"
            )

    # -------------------------------------------------------------------------
    # Private helper methods
    # -------------------------------------------------------------------------

    def _store_verification_record(
        self, administration: str, email: str, status: str
    ) -> None:
        """Insert or update a verification record in the database.

        Args:
            administration: Tenant identifier.
            email: Email address.
            status: Verification status to set.
        """
        now = datetime.utcnow()
        verified_at = now if status == "verified" else None

        try:
            self.db.execute_query(
                """INSERT INTO email_verifications
                   (administration, email, status, initiated_at, verified_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (administration, email, status, now, verified_at),
                fetch=False,
                commit=True,
            )
        except DatabaseError as e:
            logger.error(
                f"DB error storing verification record for {email} "
                f"(tenant: {administration}): {e}"
            )

    def _get_active_record(self, administration: str) -> dict | None:
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
                (administration,),
            )
            return rows[0] if rows else None
        except DatabaseError as e:
            logger.error(
                f"DB error getting active record (tenant: {administration}): {e}"
            )
            return None

    def _update_verification_status(
        self, administration: str, email: str, status: str, checked_at: datetime
    ) -> None:
        """Update the verification status and last_checked_at timestamp.

        Args:
            administration: Tenant identifier.
            email: Email address.
            status: New status value.
            checked_at: Timestamp of the status check.
        """
        verified_at_clause = ", verified_at = %s" if status == "verified" else ""
        params = [status, checked_at]
        if status == "verified":
            params.append(checked_at)
        params.extend([administration, email])

        try:
            self.db.execute_query(
                f"""UPDATE email_verifications
                    SET status = %s, last_checked_at = %s{verified_at_clause}
                    WHERE administration = %s AND email = %s
                    AND status IN ('pending', 'verified', 'failed', 'expired')""",
                tuple(params),
                fetch=False,
                commit=True,
            )
        except DatabaseError as e:
            logger.error(
                f"DB error updating status for {email} (tenant: {administration}): {e}"
            )

    def _map_ses_status(self, ses_status: str) -> str:
        """Map SES verification status to local status.

        Args:
            ses_status: SES status string ('Success', 'Pending', 'Failed', etc.)

        Returns:
            Local status string ('verified', 'pending', 'failed').
        """
        mapping = {
            "Success": "verified",
            "Pending": "pending",
            "Failed": "failed",
            "TemporaryFailure": "pending",
            "NotStarted": "failed",
        }
        return mapping.get(ses_status, "failed")

    def _get_company_name(self, administration: str) -> str | None:
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
                (administration,),
            )
            if rows:
                # Value is stored as JSON string, strip quotes if present
                val = rows[0]["value"]
                if isinstance(val, str) and val.startswith('"') and val.endswith('"'):
                    val = val[1:-1]
                return val
            return None
        except DatabaseError as e:
            logger.error(
                f"DB error getting company name (tenant: {administration}): {e}"
            )
            return None
