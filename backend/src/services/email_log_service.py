"""
Email Log Service

Tracks all emails sent via SES and updates delivery status from SNS notifications.
Provides query interface for SysAdmin (all tenants) and Tenant Admin (own tenant only).
"""

import logging
from typing import Optional, List, Dict
from database import DatabaseManager

logger = logging.getLogger(__name__)


class EmailLogService:
    """Log and query email delivery events"""

    def __init__(self, test_mode: bool = False):
        self.db = DatabaseManager(test_mode=test_mode)

    def log_sent(
        self,
        recipient: str,
        email_type: str,
        administration: Optional[str],
        ses_message_id: Optional[str],
        subject: Optional[str] = None,
        sent_by: Optional[str] = None,
    ) -> Optional[int]:
        """Log an email that was successfully handed to SES."""
        try:
            return self.db.execute_query(
                """INSERT INTO email_log
                   (recipient, email_type, administration, status,
                    ses_message_id, subject, sent_by)
                   VALUES (%s, %s, %s, 'sent', %s, %s, %s)""",
                (recipient, email_type, administration,
                 ses_message_id, subject, sent_by),
                fetch=False, commit=True,
            )
        except Exception as e:
            logger.error(f"Failed to log email send: {e}")
            return None

    def log_failed(
        self,
        recipient: str,
        email_type: str,
        administration: Optional[str],
        error_message: str,
        sent_by: Optional[str] = None,
    ) -> Optional[int]:
        """Log an email that failed to send."""
        try:
            return self.db.execute_query(
                """INSERT INTO email_log
                   (recipient, email_type, administration, status,
                    error_message, sent_by)
                   VALUES (%s, %s, %s, 'failed', %s, %s)""",
                (recipient, email_type, administration,
                 error_message, sent_by),
                fetch=False, commit=True,
            )
        except Exception as e:
            logger.error(f"Failed to log email failure: {e}")
            return None

    def update_status(
        self,
        ses_message_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update delivery status from SNS notification (delivered/bounced/complained)."""
        try:
            self.db.execute_query(
                """UPDATE email_log
                   SET status = %s, error_message = %s
                   WHERE ses_message_id = %s""",
                (status, error_message, ses_message_id),
                fetch=False, commit=True,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update email status: {e}")
            return False

    def get_logs(
        self,
        administration: Optional[str] = None,
        recipient: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Query email logs.

        Args:
            administration: Filter by tenant (None = all, for SysAdmin)
            recipient: Filter by recipient email
            limit: Max rows to return
        """
        try:
            conditions = []
            params: list = []

            if administration:
                conditions.append("administration = %s")
                params.append(administration)
            if recipient:
                conditions.append("recipient = %s")
                params.append(recipient)

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.append(min(limit, 500))

            rows = self.db.execute_query(
                f"""SELECT id, recipient, email_type, administration,
                           status, ses_message_id, subject, sent_by,
                           error_message, created_at, updated_at
                    FROM email_log {where}
                    ORDER BY created_at DESC
                    LIMIT %s""",
                tuple(params),
                fetch=True,
            )
            return rows or []
        except Exception as e:
            logger.error(f"Failed to query email logs: {e}")
            return []
