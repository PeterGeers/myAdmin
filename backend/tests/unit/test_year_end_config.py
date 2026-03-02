"""
Unit tests for Year-End Configuration Service

Tests account role configuration management.
"""

import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.year_end_config import YearEndConfigService


@pytest.fixture
def config_service():
    """Create config service with test mode"""
    return YearEndConfigService(test_mode=True)


@pytest.fixture
def test_administration():
    """Test administration name"""
    return 'TestAdmin'


class TestAccountRoleConfiguration:
    """Test account role configuration"""
    
    def test_get_required_roles(self, config_service):
        """Test getting required roles list"""
        roles = config_service.REQUIRED_ROLES
        
        assert 'equity_result' in roles
        assert 'pl_closing' in roles
        assert 'interim_opening_balance' in roles
        
        # Check role structure
        for role, info in roles.items():
            assert 'description' in info
            assert 'expected_vw' in info
            assert 'example' in info
    
    def test_get_account_by_role_not_found(self, config_service, test_administration):
        """Test getting account by role when not configured"""
        result = config_service.get_account_by_role(test_administration, 'equity_result')
        assert result is None
    
    def test_set_account_role_invalid_role(self, config_service, test_administration):
        """Test setting invalid role"""
        with pytest.raises(ValueError, match="Invalid role"):
            config_service.set_account_role(test_administration, '3080', 'invalid_role')
    
    def test_set_account_role_nonexistent_account(self, config_service, test_administration):
        """Test setting role for nonexistent account"""
        with pytest.raises(ValueError, match="not found"):
            config_service.set_account_role(test_administration, '9999', 'equity_result')
    
    def test_get_all_configured_roles_empty(self, config_service, test_administration):
        """Test getting configured roles when none exist"""
        configured = config_service.get_all_configured_roles(test_administration)
        assert isinstance(configured, dict)
        # May be empty or have some roles depending on test data
    
    def test_validate_configuration_missing_roles(self, config_service, test_administration):
        """Test validation with missing required roles"""
        validation = config_service.validate_configuration(test_administration)
        
        assert 'valid' in validation
        assert 'errors' in validation
        assert 'warnings' in validation
        assert 'configured_roles' in validation
        
        # If no roles configured, should have errors
        if not validation['configured_roles']:
            assert not validation['valid']
            assert len(validation['errors']) >= 3  # At least 3 missing roles
    
    def test_get_available_accounts(self, config_service, test_administration):
        """Test getting available accounts"""
        accounts = config_service.get_available_accounts(test_administration)
        
        assert isinstance(accounts, list)
        # Should have some accounts in test database
        
        if accounts:
            # Check account structure
            account = accounts[0]
            assert 'Reknum' in account
            assert 'AccountName' in account
            assert 'VW' in account
    
    def test_get_available_accounts_with_vw_filter(self, config_service, test_administration):
        """Test getting available accounts with VW filter"""
        # Get balance sheet accounts (VW='N')
        bs_accounts = config_service.get_available_accounts(test_administration, vw_filter='N')
        
        # Get P&L accounts (VW='Y')
        pl_accounts = config_service.get_available_accounts(test_administration, vw_filter='Y')
        
        # Both should be lists
        assert isinstance(bs_accounts, list)
        assert isinstance(pl_accounts, list)
        
        # Verify VW filter worked
        for account in bs_accounts:
            assert account['VW'] == 'N'
        
        for account in pl_accounts:
            assert account['VW'] == 'Y'


class TestConfigurationValidation:
    """Test configuration validation logic"""
    
    def test_validation_structure(self, config_service, test_administration):
        """Test validation result structure"""
        validation = config_service.validate_configuration(test_administration)
        
        # Check required keys
        assert 'valid' in validation
        assert 'errors' in validation
        assert 'warnings' in validation
        assert 'configured_roles' in validation
        
        # Check types
        assert isinstance(validation['valid'], bool)
        assert isinstance(validation['errors'], list)
        assert isinstance(validation['warnings'], list)
        assert isinstance(validation['configured_roles'], dict)
    
    def test_required_roles_check(self, config_service):
        """Test that all required roles are defined"""
        required = config_service.REQUIRED_ROLES
        
        # Must have exactly 3 required roles
        assert len(required) == 3
        
        # Check each role has proper structure
        for role_name, role_info in required.items():
            assert 'description' in role_info
            assert 'expected_vw' in role_info
            assert 'example' in role_info
            
            # VW should be Y or N
            assert role_info['expected_vw'] in ['Y', 'N']


@pytest.mark.integration
class TestAccountRoleIntegration:
    """Integration tests requiring database setup"""
    
    @pytest.mark.skip(reason="Requires specific test data setup")
    def test_full_configuration_workflow(self, config_service, test_administration):
        """Test complete configuration workflow"""
        # This test would require:
        # 1. Creating test accounts
        # 2. Assigning roles
        # 3. Validating configuration
        # 4. Removing roles
        # 5. Verifying cleanup
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
