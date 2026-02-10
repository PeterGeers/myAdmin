"""
Unit Tests for InvitationService

Tests the InvitationService methods for invitation management.
"""

import pytest
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.invitation_service import InvitationService


class TestInvitationService:
    """Test suite for InvitationService"""
    
    @pytest.fixture
    def invitation_service(self):
        """Create InvitationService instance"""
        return InvitationService(test_mode=True)
    
    @pytest.fixture
    def mock_db(self):
        """Mock database manager"""
        with patch('services.invitation_service.DatabaseManager') as mock_db_class:
            mock_db_instance = Mock()
            mock_db_class.return_value = mock_db_instance
            yield mock_db_instance
    
    # Test 1: Generate temporary password
    def test_generate_temporary_password(self, invitation_service):
        """Test temporary password generation"""
        password = invitation_service.generate_temporary_password()
        
        assert len(password) == 12
        assert any(c.isupper() for c in password)
        assert any(c.islower() for c in password)
        assert any(c.isdigit() for c in password)
        assert any(c in '!@#$%^&*' for c in password)
    
    # Test 2: Generate password with custom length
    def test_generate_password_custom_length(self, invitation_service):
        """Test password generation with custom length"""
        password = invitation_service.generate_temporary_password(length=16)
        
        assert len(password) == 16
    
    # Test 3: Generate password minimum length
    def test_generate_password_minimum_length(self, invitation_service):
        """Test password generation enforces minimum length"""
        password = invitation_service.generate_temporary_password(length=4)
        
        # Should enforce minimum of 8
        assert len(password) == 8
    
    # Test 4: Create invitation
    def test_create_invitation_success(self, invitation_service, mock_db):
        """Test creating new invitation"""
        mock_db.execute_query.return_value = None
        
        result = invitation_service.create_invitation(
            administration='TestTenant',
            email='test@example.com',
            username='test-uuid',
            created_by='admin@example.com'
        )
        
        assert result['success'] is True
        assert 'temporary_password' in result
        assert 'expires_at' in result
        assert result['expiry_days'] == 7
    
    # Test 5: Mark invitation as sent
    def test_mark_invitation_sent(self, invitation_service, mock_db):
        """Test marking invitation as sent"""
        mock_db.execute_query.return_value = None
        
        result = invitation_service.mark_invitation_sent(
            administration='TestTenant',
            email='test@example.com'
        )
        
        assert result is True
        mock_db.execute_query.assert_called_once()
    
    # Test 6: Mark invitation as accepted
    def test_mark_invitation_accepted(self, invitation_service, mock_db):
        """Test marking invitation as accepted"""
        mock_db.execute_query.return_value = None
        
        result = invitation_service.mark_invitation_accepted(
            administration='TestTenant',
            email='test@example.com'
        )
        
        assert result is True
        mock_db.execute_query.assert_called_once()
    
    # Test 7: Mark invitation as failed
    def test_mark_invitation_failed(self, invitation_service, mock_db):
        """Test marking invitation as failed"""
        mock_db.execute_query.return_value = None
        
        result = invitation_service.mark_invitation_failed(
            administration='TestTenant',
            email='test@example.com',
            error_message='Email delivery failed'
        )
        
        assert result is True
        mock_db.execute_query.assert_called_once()
    
    # Test 8: Get invitation
    def test_get_invitation_found(self, invitation_service, mock_db):
        """Test getting invitation details"""
        mock_db.execute_query.return_value = [{
            'id': 1,
            'administration': 'TestTenant',
            'email': 'test@example.com',
            'invitation_status': 'sent',
            'created_at': datetime.now()
        }]
        
        result = invitation_service.get_invitation(
            administration='TestTenant',
            email='test@example.com'
        )
        
        assert result is not None
        assert result['email'] == 'test@example.com'
        assert result['invitation_status'] == 'sent'
    
    # Test 9: Get invitation not found
    def test_get_invitation_not_found(self, invitation_service, mock_db):
        """Test getting non-existent invitation"""
        mock_db.execute_query.return_value = []
        
        result = invitation_service.get_invitation(
            administration='TestTenant',
            email='nonexistent@example.com'
        )
        
        assert result is None
    
    # Test 10: List invitations
    def test_list_invitations_all(self, invitation_service, mock_db):
        """Test listing all invitations for tenant"""
        mock_db.execute_query.return_value = [
            {'id': 1, 'email': 'user1@example.com', 'invitation_status': 'sent'},
            {'id': 2, 'email': 'user2@example.com', 'invitation_status': 'pending'}
        ]
        
        result = invitation_service.list_invitations(
            administration='TestTenant'
        )
        
        assert len(result) == 2
        assert result[0]['email'] == 'user1@example.com'
    
    # Test 11: List invitations by status
    def test_list_invitations_by_status(self, invitation_service, mock_db):
        """Test listing invitations filtered by status"""
        mock_db.execute_query.return_value = [
            {'id': 1, 'email': 'user1@example.com', 'invitation_status': 'sent'}
        ]
        
        result = invitation_service.list_invitations(
            administration='TestTenant',
            status='sent'
        )
        
        assert len(result) == 1
        assert result[0]['invitation_status'] == 'sent'
    
    # Test 12: Expire old invitations
    def test_expire_old_invitations(self, invitation_service, mock_db):
        """Test expiring old invitations"""
        mock_db.execute_query.return_value = 3  # 3 invitations expired
        
        result = invitation_service.expire_old_invitations()
        
        assert result == 3
        mock_db.execute_query.assert_called_once()
    
    # Test 13: Resend invitation
    def test_resend_invitation(self, invitation_service, mock_db):
        """Test resending invitation"""
        mock_db.execute_query.return_value = None
        
        result = invitation_service.resend_invitation(
            administration='TestTenant',
            email='test@example.com',
            created_by='admin@example.com'
        )
        
        assert result['success'] is True
        assert 'temporary_password' in result
        assert 'expires_at' in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
