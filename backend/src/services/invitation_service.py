"""
Invitation Service

Manages user invitation lifecycle including:
- Temporary password generation
- Invitation status tracking
- Resend functionality
- Expiry handling
"""

import os
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

from database import DatabaseManager

logger = logging.getLogger(__name__)


class InvitationService:
    """Service for managing user invitations"""
    
    def __init__(self, test_mode: bool = False):
        """
        Initialize invitation service
        
        Args:
            test_mode: Whether to use test database
        """
        self.db = DatabaseManager(test_mode=test_mode)
        self.invitation_expiry_days = 7
    
    def generate_temporary_password(self, length: int = 12) -> str:
        """
        Generate a secure temporary password
        
        Args:
            length: Password length (minimum 8)
        
        Returns:
            Secure random password meeting Cognito requirements
        """
        if length < 8:
            length = 8
        
        # Cognito requires: uppercase, lowercase, number, special character
        uppercase = string.ascii_uppercase
        lowercase = string.ascii_lowercase
        digits = string.digits
        special = '!@#$%^&*'
        
        # Ensure at least one of each required character type
        password = [
            secrets.choice(uppercase),
            secrets.choice(lowercase),
            secrets.choice(digits),
            secrets.choice(special)
        ]
        
        # Fill the rest with random characters from all categories
        all_chars = uppercase + lowercase + digits + special
        password.extend(secrets.choice(all_chars) for _ in range(length - 4))
        
        # Shuffle to avoid predictable patterns
        secrets.SystemRandom().shuffle(password)
        
        return ''.join(password)
    
    def create_invitation(
        self,
        administration: str,
        email: str,
        username: Optional[str] = None,
        created_by: str = '',
        template_type: str = 'user_invitation'
    ) -> Dict[str, Any]:
        """
        Create a new invitation record
        
        Args:
            administration: Tenant name
            email: User email
            username: Cognito username (optional)
            created_by: Email of user creating invitation
            template_type: Email template to use
        
        Returns:
            Dictionary with invitation details including temporary password
        """
        try:
            # Generate temporary password
            temp_password = self.generate_temporary_password()
            
            # Calculate expiry date (7 days from now)
            expires_at = datetime.now() + timedelta(days=self.invitation_expiry_days)
            
            # Check if there's an existing invitation (any status)
            existing = self.get_invitation(administration, email)
            if existing:
                # Update existing invitation regardless of status
                query = """
                    UPDATE user_invitations
                    SET temporary_password = %s,
                        expires_at = %s,
                        invitation_status = 'pending',
                        resend_count = resend_count + 1,
                        last_resent_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP,
                        username = COALESCE(%s, username),
                        template_type = %s,
                        created_by = %s
                    WHERE administration = %s AND email = %s
                """
                self.db.execute_query(
                    query,
                    (temp_password, expires_at, username, template_type, created_by, administration, email),
                    fetch=False,
                    commit=True
                )
                
                logger.info(f"Updated existing invitation for {email} in {administration}")
            else:
                # Create new invitation
                query = """
                    INSERT INTO user_invitations 
                    (administration, email, username, temporary_password, invitation_status,
                     template_type, expires_at, created_by)
                    VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s)
                """
                self.db.execute_query(
                    query,
                    (administration, email, username, temp_password, template_type, expires_at, created_by),
                    fetch=False,
                    commit=True
                )
                
                logger.info(f"Created new invitation for {email} in {administration}")
            
            return {
                'success': True,
                'email': email,
                'temporary_password': temp_password,
                'expires_at': expires_at.isoformat(),
                'expiry_days': self.invitation_expiry_days
            }
            
        except Exception as e:
            logger.error(f"Error creating invitation: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def mark_invitation_sent(
        self,
        administration: str,
        email: str
    ) -> bool:
        """
        Mark invitation as sent
        
        Args:
            administration: Tenant name
            email: User email
        
        Returns:
            True if successful
        """
        try:
            query = """
                UPDATE user_invitations
                SET invitation_status = 'sent',
                    sent_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE administration = %s AND email = %s AND invitation_status = 'pending'
            """
            self.db.execute_query(query, (administration, email), fetch=False, commit=True)
            logger.info(f"Marked invitation as sent for {email} in {administration}")
            return True
            
        except Exception as e:
            logger.error(f"Error marking invitation as sent: {e}")
            return False
    
    def mark_invitation_accepted(
        self,
        administration: str,
        email: str
    ) -> bool:
        """
        Mark invitation as accepted (user logged in)
        
        Args:
            administration: Tenant name
            email: User email
        
        Returns:
            True if successful
        """
        try:
            query = """
                UPDATE user_invitations
                SET invitation_status = 'accepted',
                    accepted_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE administration = %s AND email = %s 
                  AND invitation_status IN ('pending', 'sent')
            """
            self.db.execute_query(query, (administration, email), fetch=False, commit=True)
            logger.info(f"Marked invitation as accepted for {email} in {administration}")
            return True
            
        except Exception as e:
            logger.error(f"Error marking invitation as accepted: {e}")
            return False
    
    def mark_invitation_failed(
        self,
        administration: str,
        email: str,
        error_message: str = ''
    ) -> bool:
        """
        Mark invitation as failed
        
        Args:
            administration: Tenant name
            email: User email
            error_message: Reason for failure
        
        Returns:
            True if successful
        """
        try:
            query = """
                UPDATE user_invitations
                SET invitation_status = 'failed',
                    updated_at = CURRENT_TIMESTAMP
                WHERE administration = %s AND email = %s AND invitation_status = 'pending'
            """
            self.db.execute_query(query, (administration, email), fetch=False, commit=True)
            logger.warning(f"Marked invitation as failed for {email} in {administration}: {error_message}")
            return True
            
        except Exception as e:
            logger.error(f"Error marking invitation as failed: {e}")
            return False
    
    def get_invitation(
        self,
        administration: str,
        email: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get invitation details
        
        Args:
            administration: Tenant name
            email: User email
        
        Returns:
            Invitation details or None
        """
        try:
            query = """
                SELECT *
                FROM user_invitations
                WHERE administration = %s AND email = %s
                ORDER BY created_at DESC
                LIMIT 1
            """
            results = self.db.execute_query(query, (administration, email), fetch=True)
            
            if results and len(results) > 0:
                return results[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting invitation: {e}")
            return None
    
    def list_invitations(
        self,
        administration: str,
        status: Optional[str] = None
    ) -> list:
        """
        List invitations for a tenant
        
        Args:
            administration: Tenant name
            status: Filter by status (optional)
        
        Returns:
            List of invitations
        """
        try:
            if status:
                query = """
                    SELECT *
                    FROM user_invitations
                    WHERE administration = %s AND invitation_status = %s
                    ORDER BY created_at DESC
                """
                results = self.db.execute_query(query, (administration, status), fetch=True)
            else:
                query = """
                    SELECT *
                    FROM user_invitations
                    WHERE administration = %s
                    ORDER BY created_at DESC
                """
                results = self.db.execute_query(query, (administration,), fetch=True)
            
            return results or []
            
        except Exception as e:
            logger.error(f"Error listing invitations: {e}")
            return []
    
    def expire_old_invitations(self) -> int:
        """
        Mark expired invitations as expired
        
        Returns:
            Number of invitations expired
        """
        try:
            query = """
                UPDATE user_invitations
                SET invitation_status = 'expired',
                    updated_at = CURRENT_TIMESTAMP
                WHERE invitation_status IN ('pending', 'sent')
                  AND expires_at < CURRENT_TIMESTAMP
            """
            result = self.db.execute_query(query, fetch=False, commit=True)
            
            # Get count of affected rows (this is database-specific)
            count = result if isinstance(result, int) else 0
            
            if count > 0:
                logger.info(f"Expired {count} old invitations")
            
            return count
            
        except Exception as e:
            logger.error(f"Error expiring invitations: {e}")
            return 0
    
    def resend_invitation(
        self,
        administration: str,
        email: str,
        created_by: str = ''
    ) -> Dict[str, Any]:
        """
        Resend an invitation (generates new password and extends expiry)
        
        Args:
            administration: Tenant name
            email: User email
            created_by: Email of user resending invitation
        
        Returns:
            Dictionary with new invitation details
        """
        # This is essentially the same as creating a new invitation
        # but increments the resend counter
        return self.create_invitation(administration, email, created_by=created_by)
