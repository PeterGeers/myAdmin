"""
Property-based tests for FileCleanupManager component.

These tests verify the correctness properties of file cleanup functionality
using property-based testing with hypothesis to generate test cases.
"""

import sys
import os
import pytest
import tempfile
import shutil
from unittest.mock import Mock, patch
from pathlib import Path
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from file_cleanup_manager import FileCleanupManager


class TestFileCleanupManager:
    """Test suite for FileCleanupManager component."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def file_cleanup_manager(self, temp_storage):
        """Create FileCleanupManager instance with temporary storage."""
        config = {
            'base_storage_path': temp_storage,
            'temp_storage_path': os.path.join(temp_storage, 'temp')
        }
        return FileCleanupManager(config)
    
    def test_init_default_config(self):
        """Test FileCleanupManager initialization with default configuration."""
        manager = FileCleanupManager()
        assert manager.storage_config == {}
        assert os.path.exists(manager.base_storage_path)
        assert os.path.exists(manager.temp_storage_path)
    
    def test_init_custom_config(self, temp_storage):
        """Test FileCleanupManager initialization with custom configuration."""
        config = {
            'base_storage_path': temp_storage,
            'temp_storage_path': os.path.join(temp_storage, 'temp')
        }
        manager = FileCleanupManager(config)
        assert manager.storage_config == config
        assert manager.base_storage_path == temp_storage
    
    def test_should_cleanup_file_same_urls(self, file_cleanup_manager):
        """Test URL comparison when URLs are the same."""
        url1 = "http://example.com/file.pdf"
        url2 = "http://example.com/file.pdf"
        
        result = file_cleanup_manager.should_cleanup_file(url1, url2)
        assert result == False
    
    def test_should_cleanup_file_different_urls(self, file_cleanup_manager):
        """Test URL comparison when URLs are different."""
        url1 = "http://example.com/file1.pdf"
        url2 = "http://example.com/file2.pdf"
        
        result = file_cleanup_manager.should_cleanup_file(url1, url2)
        assert result == True
    
    def test_should_cleanup_file_empty_urls(self, file_cleanup_manager):
        """Test URL comparison with empty URLs."""
        # New URL exists, existing is empty - should cleanup
        assert file_cleanup_manager.should_cleanup_file("http://example.com/file.pdf", "") == True
        assert file_cleanup_manager.should_cleanup_file("http://example.com/file.pdf", None) == True
        
        # New URL is empty - should not cleanup
        assert file_cleanup_manager.should_cleanup_file("", "http://example.com/file.pdf") == False
        assert file_cleanup_manager.should_cleanup_file(None, "http://example.com/file.pdf") == False
        
        # Both empty - should not cleanup
        assert file_cleanup_manager.should_cleanup_file("", "") == False
        assert file_cleanup_manager.should_cleanup_file(None, None) == False
    
    def test_should_cleanup_file_google_drive_urls(self, file_cleanup_manager):
        """Test URL comparison with Google Drive URLs."""
        # Same Google Drive file ID - should not cleanup
        url1 = "https://drive.google.com/file/d/1ABC123/view"
        url2 = "https://docs.google.com/document/d/1ABC123/edit"
        result = file_cleanup_manager.should_cleanup_file(url1, url2)
        assert result == False
        
        # Different Google Drive file IDs - should cleanup
        url1 = "https://drive.google.com/file/d/1ABC123/view"
        url2 = "https://drive.google.com/file/d/2DEF456/view"
        result = file_cleanup_manager.should_cleanup_file(url1, url2)
        assert result == True
    
    def test_cleanup_uploaded_file_empty_url(self, file_cleanup_manager):
        """Test file cleanup with empty URL."""
        result = file_cleanup_manager.cleanup_uploaded_file("")
        assert result == True
        
        result = file_cleanup_manager.cleanup_uploaded_file(None)
        assert result == True
    
    def test_cleanup_uploaded_file_local_file(self, file_cleanup_manager, temp_storage):
        """Test cleanup of local file."""
        # Create a test file
        test_file = os.path.join(temp_storage, "test_file.pdf")
        with open(test_file, 'w') as f:
            f.write("test content")
        
        assert os.path.exists(test_file)
        
        # Cleanup the file
        result = file_cleanup_manager.cleanup_uploaded_file(test_file)
        assert result == True
        assert not os.path.exists(test_file)
    
    def test_cleanup_uploaded_file_nonexistent_file(self, file_cleanup_manager, temp_storage):
        """Test cleanup of non-existent file."""
        test_file = os.path.join(temp_storage, "nonexistent.pdf")
        
        result = file_cleanup_manager.cleanup_uploaded_file(test_file)
        assert result == True  # Should succeed even if file doesn't exist
    
    def test_cleanup_uploaded_file_google_drive(self, file_cleanup_manager):
        """Test cleanup of Google Drive file."""
        google_drive_url = "https://drive.google.com/file/d/1ABC123/view"
        
        result = file_cleanup_manager.cleanup_uploaded_file(google_drive_url)
        assert result == True  # Should succeed (placeholder implementation)
    
    def test_get_file_path_from_url_empty(self, file_cleanup_manager):
        """Test file path extraction with empty URL."""
        assert file_cleanup_manager.get_file_path_from_url("") == ""
        assert file_cleanup_manager.get_file_path_from_url(None) == ""
    
    def test_get_file_path_from_url_local_path(self, file_cleanup_manager):
        """Test file path extraction with local path."""
        local_path = "/path/to/file.pdf"
        result = file_cleanup_manager.get_file_path_from_url(local_path)
        assert result == os.path.normpath(local_path)
    
    def test_get_file_path_from_url_google_drive(self, file_cleanup_manager):
        """Test file path extraction with Google Drive URL."""
        google_url = "https://drive.google.com/file/d/1ABC123/view"
        result = file_cleanup_manager.get_file_path_from_url(google_url)
        assert result == google_url  # Should return URL as-is for Google Drive
    
    def test_get_file_path_from_url_web_url(self, file_cleanup_manager, temp_storage):
        """Test file path extraction with web URL."""
        web_url = "http://example.com/storage/vendor/file.pdf"
        result = file_cleanup_manager.get_file_path_from_url(web_url)
        expected = os.path.join(temp_storage, "storage", "vendor", "file.pdf")
        assert result == os.path.normpath(expected)


# Property-Based Tests
class TestFileCleanupManagerProperties:
    """
    **Feature: duplicate-invoice-detection, Property 3: File Management Correctness**
    
    Property-based tests that verify the file cleanup manager correctly determines
    whether to remove files based on URL comparison and executes cleanup operations
    atomically without affecting other system files.
    """
    
    def create_file_cleanup_manager(self, temp_storage):
        """Create FileCleanupManager with temporary storage for property tests."""
        config = {
            'base_storage_path': temp_storage,
            'temp_storage_path': os.path.join(temp_storage, 'temp')
        }
        return FileCleanupManager(config)
    
    # Generate realistic URL patterns for property testing
    url_components = st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='.-_'),
        min_size=1,
        max_size=20
    ).filter(lambda x: x and not x.startswith('.') and not x.endswith('.'))
    
    file_extensions = st.sampled_from(['.pdf', '.jpg', '.png', '.csv', '.xlsx', '.doc'])
    
    local_paths = st.builds(
        lambda dir, file, ext: f"{dir}/{file}{ext}",
        dir=st.sampled_from(['storage', 'temp', 'uploads']),
        file=url_components,
        ext=file_extensions
    )
    
    web_urls = st.builds(
        lambda domain, path, file, ext: f"http://{domain}.com/{path}/{file}{ext}",
        domain=url_components,
        path=st.sampled_from(['storage', 'files', 'documents']),
        file=url_components,
        ext=file_extensions
    )
    
    google_drive_file_ids = st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-_'),
        min_size=10,
        max_size=50
    )
    
    google_drive_urls = st.builds(
        lambda file_id: f"https://drive.google.com/file/d/{file_id}/view",
        file_id=google_drive_file_ids
    )
    
    all_urls = st.one_of(local_paths, web_urls, google_drive_urls)
    
    @given(
        new_url=all_urls,
        existing_url=all_urls
    )
    @settings(max_examples=100, deadline=None)
    def test_property_url_comparison_consistency(
        self,
        new_url,
        existing_url
    ):
        """
        **Feature: duplicate-invoice-detection, Property 3: File Management Correctness**
        **Validates: Requirements 4.2, 4.3, 4.4**
        
        Property: For any two URLs, the cleanup decision should be consistent and
        based on normalized URL comparison, with same URLs resulting in no cleanup
        and different URLs resulting in cleanup.
        """
        # Create manager for this test with temporary storage
        with tempfile.TemporaryDirectory() as temp_storage:
            manager = self.create_file_cleanup_manager(temp_storage)
            
            # Test URL comparison consistency
            result1 = manager.should_cleanup_file(new_url, existing_url)
            result2 = manager.should_cleanup_file(new_url, existing_url)
            
            # Property 1: Comparison should be deterministic
            assert result1 == result2, "URL comparison should be deterministic"
            
            # Property 2: Same URLs should not require cleanup
            same_url_result = manager.should_cleanup_file(new_url, new_url)
            assert same_url_result == False, "Same URLs should not require cleanup"
            
            # Property 3: URL normalization should be consistent
            normalized_new = manager._normalize_url(new_url)
            normalized_existing = manager._normalize_url(existing_url)
            
            expected_result = (normalized_new != normalized_existing)
            assert result1 == expected_result, "Cleanup decision should match normalized URL comparison"
            
            # Property 4: Symmetric comparison for different URLs
            if new_url != existing_url:
                reverse_result = manager.should_cleanup_file(existing_url, new_url)
                assert result1 == reverse_result, "URL comparison should be symmetric for different URLs"


if __name__ == '__main__':
    pytest.main([__file__])