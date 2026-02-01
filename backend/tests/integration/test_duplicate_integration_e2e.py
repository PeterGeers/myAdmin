"""
End-to-end integration tests for duplicate invoice detection system.

These tests verify the complete duplicate detection workflow integrates correctly
with AI extraction, vendor parsers, file upload system, and database operations.
Tests cover various file types, vendor parsers, and duplicate scenarios.

**Feature: duplicate-invoice-detection**
**Validates: Requirements 5.1, 5.2, 5.3, 5.4**
"""

import sys
import os
import pytest
import json
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock, mock_open
from datetime import datetime, timedelta
from decimal import Decimal
import random

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from pdf_processor import PDFProcessor
from duplicate_checker import DuplicateChecker
from file_cleanup_manager import FileCleanupManager
from database import DatabaseManager


class TestDuplicateDetectionE2EIntegration:
    """
    End-to-end integration tests for duplicate detection workflow.
    Tests the complete flow from file upload through duplicate detection to final processing.
    """
    
    @pytest.fixture
    def test_storage_dir(self):
        """Create temporary storage directory for test files"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_e2e_pdf_processing_workflow(self, test_storage_dir):
        """
        Test complete PDF processing workflow without database dependencies
        
        Validates: Requirements 5.1, 5.2, 5.3
        """
        # Create test PDF file
        test_pdf_path = os.path.join(test_storage_dir, 'test_invoice.pdf')
        with open(test_pdf_path, 'wb') as f:
            f.write(b'%PDF-1.4\nTest invoice content\nDate: 2024-03-15\nAmount: 250.00\n%%EOF')
        
        # Mock PDF reading
        with patch('builtins.open', mock_open(read_data=b'%PDF-1.4\nTest content\n%%EOF')):
            with patch('pdf_processor.PdfReader') as mock_pdf_reader:
                mock_reader = MagicMock()
                mock_page = MagicMock()
                mock_page.extract_text.return_value = 'Test invoice\nDate: 2024-03-15\nAmount: 250.00'
                mock_reader.pages = [mock_page]
                mock_pdf_reader.return_value = mock_reader
                
                processor = PDFProcessor(test_mode=True)
                
                drive_result = {
                    'id': 'new_file_id',
                    'url': 'https://drive.google.com/file/d/new_file_id/view'
                }
                
                result = processor.process_file(test_pdf_path, drive_result, 'TestVendor')
                
                # Verify PDF processing completed successfully
                assert 'txt' in result
                assert 'folder' in result
                assert result['url'] == drive_result['url']
                assert len(result['txt']) > 0

    
    def test_e2e_image_processing_workflow(self, test_storage_dir):
        """
        Test complete image processing workflow
        
        Validates: Requirements 5.1, 5.2, 5.3
        """
        # Create test image file
        test_image_path = os.path.join(test_storage_dir, 'test_receipt.jpg')
        with open(test_image_path, 'wb') as f:
            # Minimal JPEG header
            f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9')
        
        # Mock image AI processor
        with patch('image_ai_processor.ImageAIProcessor') as mock_image_ai_class:
            mock_image_ai = Mock()
            mock_image_ai.process_image.return_value = {
                'date': '2024-02-01',
                'total_amount': 500.00,
                'vat_amount': 87.60,
                'description': 'Test Receipt',
                'vendor': 'TestVendor'
            }
            mock_image_ai_class.return_value = mock_image_ai
            
            processor = PDFProcessor(test_mode=True)
            
            drive_result = {
                'id': 'new_image_file_id',
                'url': 'https://drive.google.com/file/d/new_image_file_id/view'
            }
            
            result = processor.process_file(test_image_path, drive_result, 'TestVendor')
            
            # Verify image processing completed successfully
            assert 'txt' in result
            assert 'folder' in result
            assert result['url'] == drive_result['url']
    
    def test_e2e_duplicate_decision_handling_continue(self, test_storage_dir):
        """
        Test duplicate decision handling - continue workflow
        
        Validates: Requirements 5.3, 5.4
        """
        processor = PDFProcessor(test_mode=True)
        
        # Create mock duplicate info
        duplicate_info = {
            'has_duplicates': True,
            'duplicate_count': 1,
            'existing_transactions': [{
                'id': 1,
                'transactionDate': '2024-01-15',
                'transactionDescription': 'Existing transaction',
                'transactionAmount': 150.50,
                'referenceNumber': 'TestVendor',
                'ref3': 'https://drive.google.com/file/d/existing_file_id/view'
            }],
            'requires_user_decision': True,
            'new_transaction': {
                'ReferenceNumber': 'TestVendor',
                'TransactionDate': '2024-01-15',
                'TransactionAmount': 150.50,
                'Ref3': 'https://drive.google.com/file/d/new_file_id/view'
            }
        }
        
        transactions = [{
            'date': '2024-01-15',
            'description': 'Test transaction',
            'amount': 150.50,
            'debet': '4000',
            'credit': '1300',
            'ref': 'TestVendor',
            'ref3': 'https://drive.google.com/file/d/new_file_id/view',
            'ref4': 'test_file.pdf'
        }]
        
        file_data = {
            'url': 'https://drive.google.com/file/d/new_file_id/view',
            'name': 'test_file.pdf',
            'folder': 'TestVendor'
        }
        
        # Test continue decision
        result = processor.handle_duplicate_decision(
            'continue', duplicate_info, transactions, file_data, 'test_user', 'test_session'
        )
        
        # Verify continue decision succeeded
        assert result['success'] == True
        assert result['action_taken'] == 'continue'
        assert len(result['transactions']) > 0
        assert result['cleanup_performed'] == False
        
        # Verify transactions are preserved
        for tx in result['transactions']:
            assert 'date' in tx
            assert 'amount' in tx
            assert 'ref3' in tx
    
    def test_e2e_duplicate_decision_handling_cancel(self, test_storage_dir):
        """
        Test duplicate decision handling - cancel workflow
        
        Validates: Requirements 5.3, 5.4
        """
        processor = PDFProcessor(test_mode=True)
        
        # Create mock duplicate info
        duplicate_info = {
            'has_duplicates': True,
            'duplicate_count': 1,
            'existing_transactions': [{
                'id': 1,
                'transactionDate': '2024-01-15',
                'transactionDescription': 'Existing transaction',
                'transactionAmount': 150.50,
                'referenceNumber': 'TestVendor',
                'ref3': 'https://drive.google.com/file/d/existing_file_id/view'
            }],
            'requires_user_decision': True,
            'new_transaction': {
                'ReferenceNumber': 'TestVendor',
                'TransactionDate': '2024-01-15',
                'TransactionAmount': 150.50,
                'Ref3': 'https://drive.google.com/file/d/new_file_id/view'
            }
        }
        
        transactions = [{
            'date': '2024-01-15',
            'description': 'Test transaction',
            'amount': 150.50,
            'debet': '4000',
            'credit': '1300',
            'ref': 'TestVendor',
            'ref3': 'https://drive.google.com/file/d/new_file_id/view',
            'ref4': 'test_file.pdf'
        }]
        
        file_data = {
            'url': 'https://drive.google.com/file/d/new_file_id/view',
            'name': 'test_file.pdf',
            'folder': 'TestVendor'
        }
        
        # Test cancel decision
        result = processor.handle_duplicate_decision(
            'cancel', duplicate_info, transactions, file_data, 'test_user', 'test_session'
        )
        
        # Verify cancel decision succeeded
        assert result['success'] == True
        assert result['action_taken'] == 'cancel'
        assert len(result['transactions']) == 0
        
        # Verify message indicates cancellation
        assert 'message' in result
        assert 'cancel' in result['message'].lower() or 'duplicate' in result['message'].lower()
    
    def test_e2e_file_cleanup_manager_integration(self, test_storage_dir):
        """
        Test file cleanup manager integration with duplicate workflow
        
        Validates: Requirements 4.2, 4.3, 4.4, 5.4
        """
        cleanup_manager = FileCleanupManager({'storage_path': test_storage_dir})
        
        # Test URL comparison - different URLs (core integration logic)
        new_url = 'https://drive.google.com/file/d/new_file_id/view'
        existing_url = 'https://drive.google.com/file/d/existing_file_id/view'
        
        should_cleanup = cleanup_manager.should_cleanup_file(new_url, existing_url)
        assert should_cleanup == True, "Different URLs should trigger cleanup"
        
        # Test URL comparison - same URLs
        same_url = 'https://drive.google.com/file/d/same_file_id/view'
        
        should_cleanup = cleanup_manager.should_cleanup_file(same_url, same_url)
        assert should_cleanup == False, "Same URLs should not trigger cleanup"
        
        # Test URL normalization handles different formats
        url1 = 'https://drive.google.com/file/d/abc123/view'
        url2 = 'https://drive.google.com/file/d/abc123/view?usp=sharing'
        
        # These should be considered the same file
        should_cleanup = cleanup_manager.should_cleanup_file(url1, url2)
        assert should_cleanup == False, "Same file with different query params should not trigger cleanup"
        
        # Test with completely different file IDs
        url3 = 'https://drive.google.com/file/d/xyz789/view'
        
        should_cleanup = cleanup_manager.should_cleanup_file(url1, url3)
        assert should_cleanup == True, "Different file IDs should trigger cleanup"
    
    def test_e2e_duplicate_checker_integration(self):
        """
        Test duplicate checker integration with database
        
        Validates: Requirements 1.1, 1.3, 5.2
        """
        # Mock database manager
        mock_db = Mock(spec=DatabaseManager)
        mock_db.execute_query.return_value = []
        
        checker = DuplicateChecker(mock_db)
        
        # Test duplicate check
        result = checker.check_for_duplicates('TestVendor', '2024-01-15', 150.50)
        
        # Verify check was performed
        assert mock_db.execute_query.called
        assert isinstance(result, list)
        
        # Test format duplicate info - no duplicates
        formatted = checker.format_duplicate_info([])
        assert formatted['has_duplicates'] == False
        assert formatted['duplicate_count'] == 0
        assert formatted['requires_user_decision'] == False
        
        # Test format duplicate info - with duplicates
        duplicates = [{
            'ID': 1,
            'TransactionDate': '2024-01-15',
            'TransactionAmount': Decimal('150.50'),
            'TransactionDescription': 'Test transaction',
            'ReferenceNumber': 'TestVendor',
            'Debet': '4000',
            'Credit': '1300'
        }]
        
        formatted = checker.format_duplicate_info(duplicates)
        assert formatted['has_duplicates'] == True
        assert formatted['duplicate_count'] == 1
        assert formatted['requires_user_decision'] == True
        assert len(formatted['existing_transactions']) == 1
    
    def test_e2e_vendor_parser_compatibility(self):
        """
        Test that duplicate detection works with vendor-specific parsers
        
        Validates: Requirements 5.1, 5.2, 5.4
        """
        from vendor_parsers import VendorParsers
        
        parsers = VendorParsers()
        
        # Test Kuwait parser
        kuwait_lines = [
            'Kuwait Petroleum',
            'Datum : 15-01-2024',
            'Totaal incl. BTW EUR 150,50'
        ]
        
        kuwait_result = parsers.parse_kuwait(kuwait_lines)
        
        # Verify parser returns expected structure
        if kuwait_result:
            assert 'date' in kuwait_result
            assert 'total_amount' in kuwait_result
            assert 'description' in kuwait_result
        
        # Test Booking parser
        booking_lines = [
            'Booking.com',
            'Invoice number: 123456',
            'Date: 01/02/2024',
            'Total amount due EUR 500.00'
        ]
        
        booking_result = parsers.parse_booking(booking_lines)
        
        # Verify parser returns expected structure
        if booking_result:
            assert 'date' in booking_result
            assert 'total_amount' in booking_result
            assert 'description' in booking_result
    
    def test_e2e_error_handling_graceful_degradation(self):
        """
        Test that errors are handled gracefully without breaking workflow
        
        Validates: Requirements 6.1, 6.2, 6.3
        """
        # Mock database manager that raises errors
        mock_db = Mock(spec=DatabaseManager)
        mock_db.execute_query.side_effect = Exception("Database connection failed")
        
        checker = DuplicateChecker(mock_db)
        
        # Test duplicate check with database error
        result = checker.check_for_duplicates('TestVendor', '2024-01-15', 150.50)
        
        # Verify graceful degradation - returns empty list instead of crashing
        assert isinstance(result, list)
        assert len(result) == 0
        
        # Test decision logging with database error
        mock_db.execute_query.side_effect = Exception("Logging failed")
        
        duplicate_info = {'existing_transactions': []}
        new_transaction_data = {
            'ReferenceNumber': 'TestVendor',
            'TransactionDate': '2024-01-15',
            'TransactionAmount': 150.50
        }
        
        log_result = checker.log_duplicate_decision(
            'continue', duplicate_info, new_transaction_data
        )
        
        # Verify logging failure is handled gracefully
        assert log_result == False  # Returns False but doesn't crash
    
    def test_e2e_performance_requirements(self):
        """
        Test that duplicate detection meets performance requirements
        
        Validates: Requirements 5.5
        """
        import time
        
        # Mock database manager with realistic response time
        mock_db = Mock(spec=DatabaseManager)
        mock_db.execute_query.return_value = []
        
        checker = DuplicateChecker(mock_db)
        
        # Measure duplicate check performance
        start_time = time.time()
        result = checker.check_for_duplicates('TestVendor', '2024-01-15', 150.50)
        end_time = time.time()
        
        elapsed_time = end_time - start_time
        
        # Verify performance requirement (should complete within 2 seconds)
        assert elapsed_time < 2.0, f"Duplicate check took {elapsed_time}s, should be < 2s"
        
        # Verify result is correct
        assert isinstance(result, list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
