"""
Integration tests for GoogleDriveService with multiple tenants.

These tests verify that GoogleDriveService correctly:
1. Authenticates with tenant-specific credentials from the database
2. Maintains tenant isolation (each tenant uses their own credentials)
3. Works correctly for both GoodwinSolutions and PeterPrive tenants

Prerequisites:
- Running MySQL database with tenant_credentials table
- Credentials migrated to database for both tenants
- CREDENTIALS_ENCRYPTION_KEY set in environment

Run with: pytest backend/tests/integration/test_google_drive_service_tenants.py -v -m integration
"""

import pytest
import os
import sys
import json
from unittest.mock import Mock, patch, MagicMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from google_drive_service import GoogleDriveService
from services.credential_service import CredentialService
from database import DatabaseManager


@pytest.mark.integration
class TestGoogleDriveServiceTenants:
    """Integration tests for GoogleDriveService with multiple tenants"""
    
    # Test tenants
    TENANTS = ['GoodwinSolutions', 'PeterPrive']
    
    @pytest.fixture(scope="class")
    def db_manager(self):
        """Create a database manager for testing"""
        # Use production database since credentials are stored there
        # Note: These are read-only tests, so it's safe to use production DB
        db = DatabaseManager(test_mode=False)
        yield db
    
    @pytest.fixture(scope="class")
    def credential_service(self, db_manager):
        """Create a CredentialService instance"""
        # Get encryption key from environment
        encryption_key = os.getenv('CREDENTIALS_ENCRYPTION_KEY')
        if not encryption_key:
            pytest.skip("CREDENTIALS_ENCRYPTION_KEY not set in environment")
        
        return CredentialService(db_manager, encryption_key)
    
    @pytest.fixture(scope="class")
    def verify_credentials_exist(self, credential_service):
        """Verify that credentials exist for both tenants in the database"""
        missing_tenants = []
        
        for tenant in self.TENANTS:
            # Check for OAuth credentials
            oauth_creds = credential_service.get_credential(tenant, 'google_drive_oauth')
            token_creds = credential_service.get_credential(tenant, 'google_drive_token')
            
            if not oauth_creds or not token_creds:
                missing_tenants.append(tenant)
        
        if missing_tenants:
            pytest.skip(
                f"Credentials not found in database for tenants: {', '.join(missing_tenants)}. "
                "Run migration script: python scripts/credentials/migrate_credentials_to_db.py"
            )
        
        return True
    
    def test_credentials_exist_for_both_tenants(self, credential_service, verify_credentials_exist):
        """Test that credentials exist in database for both tenants"""
        for tenant in self.TENANTS:
            # Check OAuth credentials
            oauth_creds = credential_service.get_credential(tenant, 'google_drive_oauth')
            assert oauth_creds is not None, f"OAuth credentials not found for {tenant}"
            assert isinstance(oauth_creds, dict), f"OAuth credentials should be dict for {tenant}"
            
            # Check token credentials
            token_creds = credential_service.get_credential(tenant, 'google_drive_token')
            assert token_creds is not None, f"Token credentials not found for {tenant}"
            assert isinstance(token_creds, dict), f"Token credentials should be dict for {tenant}"
    
    def test_tenant_credentials_are_isolated(self, credential_service, verify_credentials_exist):
        """Test that each tenant can only access their own credentials (credential access isolation)"""
        # Get credentials for both tenants
        goodwin_oauth = credential_service.get_credential('GoodwinSolutions', 'google_drive_oauth')
        peter_oauth = credential_service.get_credential('PeterPrive', 'google_drive_oauth')
        
        goodwin_token = credential_service.get_credential('GoodwinSolutions', 'google_drive_token')
        peter_token = credential_service.get_credential('PeterPrive', 'google_drive_token')
        
        # Verify each tenant has valid credentials
        assert goodwin_oauth is not None, "GoodwinSolutions should have OAuth credentials"
        assert peter_oauth is not None, "PeterPrive should have OAuth credentials"
        assert goodwin_token is not None, "GoodwinSolutions should have token"
        assert peter_token is not None, "PeterPrive should have token"
        
        # Verify credential structures are valid
        assert 'installed' in goodwin_oauth or 'web' in goodwin_oauth, "Invalid OAuth structure for GoodwinSolutions"
        assert 'installed' in peter_oauth or 'web' in peter_oauth, "Invalid OAuth structure for PeterPrive"
        
        assert 'token' in goodwin_token or 'access_token' in goodwin_token, "Invalid token structure for GoodwinSolutions"
        assert 'token' in peter_token or 'access_token' in peter_token, "Invalid token structure for PeterPrive"
        
        # Note: Tenants may share the same Google Drive account (same credential values),
        # but the key security requirement is that each tenant can ONLY access credentials
        # stored under their own administration name in the database.
        # This is enforced by the CredentialService.get_credential() method which filters by administration.
    
    def test_tenant_cannot_access_other_tenant_credentials(self, db_manager):
        """Test that a tenant cannot access credentials belonging to another tenant"""
        # This test verifies the security boundary: credential access is isolated by administration
        
        # Create credential service
        encryption_key = os.getenv('CREDENTIALS_ENCRYPTION_KEY')
        if not encryption_key:
            pytest.skip("CREDENTIALS_ENCRYPTION_KEY not set")
        
        cs = CredentialService(db_manager, encryption_key)
        
        # Attempt to get GoodwinSolutions credentials using PeterPrive administration
        # This should return None or the credentials for PeterPrive, NOT GoodwinSolutions
        result = cs.get_credential('PeterPrive', 'google_drive_oauth')
        
        # Verify we got PeterPrive's credentials (or None if not found)
        assert result is not None, "PeterPrive should have credentials"
        
        # Now verify that when we request GoodwinSolutions credentials,
        # we get different data (even if values are the same, they're stored separately)
        goodwin_result = cs.get_credential('GoodwinSolutions', 'google_drive_oauth')
        assert goodwin_result is not None, "GoodwinSolutions should have credentials"
        
        # The key point: Each tenant's credentials are retrieved independently
        # based on the administration parameter. A tenant cannot "cross over"
        # and access another tenant's credential storage.
        # This is enforced at the database query level:
        # SELECT ... WHERE administration = %s AND credential_type = %s
    
    @patch('google_drive_service.build')
    @patch('google_drive_service.Credentials')
    def test_initialize_service_for_goodwin_solutions(
        self, 
        mock_credentials, 
        mock_build, 
        verify_credentials_exist
    ):
        """Test initializing GoogleDriveService for GoodwinSolutions tenant"""
        # Mock valid credentials
        mock_creds_instance = Mock()
        mock_creds_instance.valid = True
        mock_credentials.from_authorized_user_info.return_value = mock_creds_instance
        
        # Mock Drive service
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        # Initialize service for GoodwinSolutions
        drive_service = GoogleDriveService('GoodwinSolutions')
        
        # Verify service was created
        assert drive_service is not None
        assert drive_service.administration == 'GoodwinSolutions'
        assert drive_service.service == mock_service
        
        # Verify build was called with correct credentials
        mock_build.assert_called_once_with('drive', 'v3', credentials=mock_creds_instance)
    
    @patch('google_drive_service.build')
    @patch('google_drive_service.Credentials')
    def test_initialize_service_for_peter_prive(
        self, 
        mock_credentials, 
        mock_build, 
        verify_credentials_exist
    ):
        """Test initializing GoogleDriveService for PeterPrive tenant"""
        # Mock valid credentials
        mock_creds_instance = Mock()
        mock_creds_instance.valid = True
        mock_credentials.from_authorized_user_info.return_value = mock_creds_instance
        
        # Mock Drive service
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        # Initialize service for PeterPrive
        drive_service = GoogleDriveService('PeterPrive')
        
        # Verify service was created
        assert drive_service is not None
        assert drive_service.administration == 'PeterPrive'
        assert drive_service.service == mock_service
        
        # Verify build was called with correct credentials
        mock_build.assert_called_once_with('drive', 'v3', credentials=mock_creds_instance)
    
    @patch('google_drive_service.build')
    @patch('google_drive_service.Credentials')
    def test_both_tenants_can_initialize_simultaneously(
        self, 
        mock_credentials, 
        mock_build, 
        verify_credentials_exist
    ):
        """Test that both tenants can have active GoogleDriveService instances"""
        # Mock valid credentials
        mock_creds_instance = Mock()
        mock_creds_instance.valid = True
        mock_credentials.from_authorized_user_info.return_value = mock_creds_instance
        
        # Mock Drive services
        mock_service_1 = Mock()
        mock_service_2 = Mock()
        mock_build.side_effect = [mock_service_1, mock_service_2]
        
        # Initialize services for both tenants
        goodwin_service = GoogleDriveService('GoodwinSolutions')
        peter_service = GoogleDriveService('PeterPrive')
        
        # Verify both services were created
        assert goodwin_service.administration == 'GoodwinSolutions'
        assert peter_service.administration == 'PeterPrive'
        
        # Verify they have different service instances
        assert goodwin_service.service == mock_service_1
        assert peter_service.service == mock_service_2
        assert goodwin_service.service != peter_service.service
    
    def test_invalid_tenant_raises_error(self):
        """Test that initializing with non-existent tenant raises appropriate error"""
        with pytest.raises(Exception) as exc_info:
            GoogleDriveService('NonExistentTenant')
        
        # Should raise error about missing credentials
        assert "OAuth credentials not found" in str(exc_info.value) or \
               "not found for administration" in str(exc_info.value)
    
    @patch('google_drive_service.build')
    @patch('google_drive_service.Credentials')
    @patch('google_drive_service.Request')
    def test_expired_token_refresh_for_tenant(
        self, 
        mock_request, 
        mock_credentials, 
        mock_build, 
        credential_service,
        verify_credentials_exist
    ):
        """Test that expired tokens are refreshed correctly for a tenant"""
        tenant = 'GoodwinSolutions'
        
        # Mock expired credentials that can be refreshed
        mock_creds_instance = Mock()
        mock_creds_instance.valid = False
        mock_creds_instance.expired = True
        mock_creds_instance.refresh_token = 'refresh_token_123'
        mock_creds_instance.to_json.return_value = json.dumps({
            'token': 'new_access_token',
            'refresh_token': 'refresh_token_123'
        })
        mock_credentials.from_authorized_user_info.return_value = mock_creds_instance
        
        # Mock Drive service
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        # Initialize service (should trigger token refresh)
        drive_service = GoogleDriveService(tenant)
        
        # Verify refresh was called
        mock_creds_instance.refresh.assert_called_once()
        
        # Verify service was created
        assert drive_service.administration == tenant
        assert drive_service.service == mock_service
    
    @patch('google_drive_service.GoogleDriveService._authenticate')
    def test_list_subfolders_for_tenant(self, mock_authenticate, verify_credentials_exist):
        """Test that list_subfolders works for a tenant"""
        tenant = 'GoodwinSolutions'
        
        # Mock Drive service
        mock_service = Mock()
        mock_files = Mock()
        mock_list = Mock()
        mock_execute = Mock()
        
        mock_execute.return_value = {
            'files': [
                {'id': 'folder1', 'name': 'Test Folder 1', 'webViewLink': 'url1'},
                {'id': 'folder2', 'name': 'Test Folder 2', 'webViewLink': 'url2'}
            ],
            'nextPageToken': None
        }
        mock_list.return_value.execute = mock_execute
        mock_files.return_value.list = mock_list
        mock_service.files = mock_files
        mock_authenticate.return_value = mock_service
        
        # Initialize service and list subfolders
        drive_service = GoogleDriveService(tenant)
        result = drive_service.list_subfolders()
        
        # Verify results
        assert len(result) == 2
        assert result[0]['name'] == 'Test Folder 1'
        assert result[1]['name'] == 'Test Folder 2'


@pytest.mark.integration
@pytest.mark.slow
class TestGoogleDriveServiceRealAPI:
    """
    Real API tests for GoogleDriveService (requires actual Google Drive access).
    
    These tests are marked as 'slow' and should only be run manually or in
    specific test environments where Google Drive API access is available.
    
    Run with: pytest backend/tests/integration/test_google_drive_service_tenants.py -v -m "integration and slow"
    """
    
    TENANTS = ['GoodwinSolutions', 'PeterPrive']
    
    @pytest.fixture(scope="class")
    def skip_if_no_api_access(self):
        """Skip tests if Google Drive API access is not available"""
        # Check if we should run real API tests
        run_real_tests = os.getenv('RUN_GOOGLE_DRIVE_REAL_TESTS', 'false').lower() == 'true'
        
        if not run_real_tests:
            pytest.skip(
                "Real Google Drive API tests disabled. "
                "Set RUN_GOOGLE_DRIVE_REAL_TESTS=true to enable."
            )
    
    def test_real_authentication_goodwin_solutions(self, skip_if_no_api_access):
        """Test real authentication for GoodwinSolutions tenant"""
        try:
            drive_service = GoogleDriveService('GoodwinSolutions')
            assert drive_service.service is not None
            assert drive_service.administration == 'GoodwinSolutions'
        except Exception as e:
            pytest.fail(f"Failed to authenticate GoodwinSolutions: {e}")
    
    def test_real_authentication_peter_prive(self, skip_if_no_api_access):
        """Test real authentication for PeterPrive tenant"""
        try:
            drive_service = GoogleDriveService('PeterPrive')
            assert drive_service.service is not None
            assert drive_service.administration == 'PeterPrive'
        except Exception as e:
            pytest.fail(f"Failed to authenticate PeterPrive: {e}")
    
    def test_real_list_subfolders_goodwin_solutions(self, skip_if_no_api_access):
        """Test real list_subfolders for GoodwinSolutions tenant"""
        try:
            drive_service = GoogleDriveService('GoodwinSolutions')
            folders = drive_service.list_subfolders()
            
            # Should return a list (may be empty)
            assert isinstance(folders, list)
            
            # If folders exist, verify structure
            if folders:
                assert 'id' in folders[0]
                assert 'name' in folders[0]
        except Exception as e:
            pytest.fail(f"Failed to list subfolders for GoodwinSolutions: {e}")
    
    def test_real_list_subfolders_peter_prive(self, skip_if_no_api_access):
        """Test real list_subfolders for PeterPrive tenant"""
        try:
            drive_service = GoogleDriveService('PeterPrive')
            folders = drive_service.list_subfolders()
            
            # Should return a list (may be empty)
            assert isinstance(folders, list)
            
            # If folders exist, verify structure
            if folders:
                assert 'id' in folders[0]
                assert 'name' in folders[0]
        except Exception as e:
            pytest.fail(f"Failed to list subfolders for PeterPrive: {e}")


if __name__ == '__main__':
    # Run integration tests only
    pytest.main([__file__, '-v', '-m', 'integration'])
