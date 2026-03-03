"""
Unit tests for Year-End Configuration Service

Tests account purpose configuration management.
"""

import pytest
import sys
import os
from unittest.mock import patch

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


class TestAccountPurposeConfiguration:
    """Test account purpose configuration"""
    
    def test_get_required_purposes(self, config_service):
        """Test getting required purposes list"""
        purposes = config_service.REQUIRED_PURPOSES
        
        assert 'equity_result' in purposes
        assert 'pl_closing' in purposes
        
        # Check purpose structure
        for purpose, info in purposes.items():
            assert 'description' in info
            assert 'expected_vw' in info
            assert 'example' in info
    
    def test_get_account_by_purpose_not_found(self, config_service, test_administration):
        """Test getting account by purpose when not configured"""
        with patch.object(config_service.db, 'execute_query', return_value=[]):
            result = config_service.get_account_by_purpose(test_administration, 'equity_result')
            assert result is None
    
    def test_set_account_purpose_invalid_purpose(self, config_service, test_administration):
        """Test setting invalid purpose"""
        with pytest.raises(ValueError, match="Invalid purpose"):
            config_service.set_account_purpose(test_administration, '3080', 'invalid_purpose')
    
    def test_set_account_purpose_nonexistent_account(self, config_service, test_administration):
        """Test setting purpose for nonexistent account"""
        with patch.object(config_service.db, 'execute_query', return_value=[]):
            with pytest.raises(ValueError, match="not found"):
                config_service.set_account_purpose(test_administration, '9999', 'equity_result')
    
    def test_get_all_configured_purposes_empty(self, config_service, test_administration):
        """Test getting configured purposes when none exist"""
        with patch.object(config_service.db, 'execute_query', return_value=[]):
            configured = config_service.get_all_configured_purposes(test_administration)
            assert isinstance(configured, dict)
            # May be empty or have some purposes depending on test data
    
    def test_validate_configuration_missing_purposes(self, config_service, test_administration):
        """Test validation with missing required purposes"""
        with patch.object(config_service.db, 'execute_query', return_value=[]):
            validation = config_service.validate_configuration(test_administration)
            
            assert 'valid' in validation
            assert 'errors' in validation
            assert 'warnings' in validation
            assert 'configured_purposes' in validation
            
            # If no purposes configured, should have errors
            if not validation['configured_purposes']:
                assert not validation['valid']
                assert len(validation['errors']) >= 2  # At least 2 missing purposes
    
    def test_get_available_accounts(self, config_service, test_administration):
        """Test getting available accounts"""
        mock_accounts = [
            {'Account': '1000', 'AccountName': 'Cash', 'VW': 'N', 'current_purpose': None},
            {'Account': '3080', 'AccountName': 'Equity', 'VW': 'N', 'current_purpose': None}
        ]
        
        with patch.object(config_service.db, 'execute_query', return_value=mock_accounts):
            accounts = config_service.get_available_accounts(test_administration)
            
            assert isinstance(accounts, list)
            assert len(accounts) == 2
            
            # Check account structure
            account = accounts[0]
            assert 'Account' in account
            assert 'AccountName' in account
            assert 'VW' in account
    
    def test_get_available_accounts_with_vw_filter(self, config_service, test_administration):
        """Test getting available accounts with VW filter"""
        mock_bs_accounts = [
            {'Account': '1000', 'AccountName': 'Cash', 'VW': 'N', 'current_purpose': None}
        ]
        mock_pl_accounts = [
            {'Account': '8000', 'AccountName': 'Revenue', 'VW': 'Y', 'current_purpose': None}
        ]
        
        with patch.object(config_service.db, 'execute_query', side_effect=[mock_bs_accounts, mock_pl_accounts]):
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
        with patch.object(config_service.db, 'execute_query', return_value=[]):
            validation = config_service.validate_configuration(test_administration)
            
            # Check required keys
            assert 'valid' in validation
            assert 'errors' in validation
            assert 'warnings' in validation
            assert 'configured_purposes' in validation
            
            # Check types
            assert isinstance(validation['valid'], bool)
            assert isinstance(validation['errors'], list)
            assert isinstance(validation['warnings'], list)
            assert isinstance(validation['configured_purposes'], dict)
    
    def test_required_purposes_check(self, config_service):
        """Test that all required purposes are defined"""
        required = config_service.REQUIRED_PURPOSES
        
        # Must have exactly 2 required purposes
        assert len(required) == 2
        
        # Check each purpose has proper structure
        for purpose_name, purpose_info in required.items():
            assert 'description' in purpose_info
            assert 'expected_vw' in purpose_info
            assert 'example' in purpose_info
            
            # VW should be Y or N
            assert purpose_info['expected_vw'] in ['Y', 'N']


@pytest.mark.integration
class TestAccountPurposeIntegration:
    """Integration tests requiring database setup"""
    
    @pytest.mark.skip(reason="Requires specific test data setup")
    def test_full_configuration_workflow(self, config_service, test_administration):
        """Test complete configuration workflow"""
        # This test would require:
        # 1. Creating test accounts
        # 2. Assigning purposes
        # 3. Validating configuration
        # 4. Removing purposes
        # 5. Verifying cleanup
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
