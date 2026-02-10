"""
Simple Unit Tests for InvitationService

Tests the InvitationService password generation and basic functionality.
"""

import pytest
import os
import string

# Add src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.invitation_service import InvitationService


class TestInvitationServiceSimple:
    """Simple test suite for InvitationService"""
    
    @pytest.fixture
    def invitation_service(self):
        """Create InvitationService instance"""
        return InvitationService(test_mode=True)
    
    # Test 1: Service initialization
    def test_service_initialization(self, invitation_service):
        """Test service initializes correctly"""
        assert invitation_service is not None
        assert invitation_service.invitation_expiry_days == 7
    
    # Test 2: Generate temporary password - default length
    def test_generate_password_default(self, invitation_service):
        """Test password generation with default length"""
        password = invitation_service.generate_temporary_password()
        
        assert len(password) == 12
        assert isinstance(password, str)
    
    # Test 3: Password has uppercase
    def test_password_has_uppercase(self, invitation_service):
        """Test password contains uppercase letters"""
        password = invitation_service.generate_temporary_password()
        assert any(c.isupper() for c in password)
    
    # Test 4: Password has lowercase
    def test_password_has_lowercase(self, invitation_service):
        """Test password contains lowercase letters"""
        password = invitation_service.generate_temporary_password()
        assert any(c.islower() for c in password)
    
    # Test 5: Password has digit
    def test_password_has_digit(self, invitation_service):
        """Test password contains digits"""
        password = invitation_service.generate_temporary_password()
        assert any(c.isdigit() for c in password)
    
    # Test 6: Password has special character
    def test_password_has_special(self, invitation_service):
        """Test password contains special characters"""
        password = invitation_service.generate_temporary_password()
        assert any(c in '!@#$%^&*' for c in password)
    
    # Test 7: Password meets all requirements
    def test_password_meets_all_requirements(self, invitation_service):
        """Test password meets all Cognito requirements"""
        password = invitation_service.generate_temporary_password()
        
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in '!@#$%^&*' for c in password)
        
        assert all([has_upper, has_lower, has_digit, has_special])
    
    # Test 8: Custom length password
    def test_generate_password_custom_length(self, invitation_service):
        """Test password generation with custom length"""
        password = invitation_service.generate_temporary_password(length=16)
        assert len(password) == 16
    
    # Test 9: Minimum length enforcement
    def test_password_minimum_length(self, invitation_service):
        """Test password enforces minimum length of 8"""
        password = invitation_service.generate_temporary_password(length=4)
        assert len(password) == 8
    
    # Test 10: Multiple passwords are different
    def test_passwords_are_unique(self, invitation_service):
        """Test that generated passwords are unique"""
        passwords = [invitation_service.generate_temporary_password() for _ in range(10)]
        assert len(set(passwords)) == 10  # All should be unique
    
    # Test 11: Password only contains valid characters
    def test_password_valid_characters(self, invitation_service):
        """Test password only contains expected characters"""
        password = invitation_service.generate_temporary_password()
        valid_chars = string.ascii_letters + string.digits + '!@#$%^&*'
        assert all(c in valid_chars for c in password)
    
    # Test 12: Expiry days configuration
    def test_expiry_days_configuration(self, invitation_service):
        """Test expiry days is configurable"""
        assert invitation_service.invitation_expiry_days == 7
        invitation_service.invitation_expiry_days = 14
        assert invitation_service.invitation_expiry_days == 14
    
    # Test 13: Password generation is consistent in length
    def test_password_length_consistency(self, invitation_service):
        """Test all generated passwords have consistent length"""
        passwords = [invitation_service.generate_temporary_password() for _ in range(20)]
        assert all(len(p) == 12 for p in passwords)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
