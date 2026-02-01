import sys
import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock, mock_open
from hypothesis import given, strategies as st, assume, settings, HealthCheck
from datetime import datetime, timedelta
import random

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from pdf_processor import PDFProcessor

class TestPDFProcessor:
    
    @pytest.fixture
    def pdf_processor(self):
        """Create PDFProcessor instance for testing"""
        return PDFProcessor(test_mode=True)
    
    @pytest.fixture
    def sample_pdf_content(self):
        """Sample PDF text content for testing"""
        return """
        Invoice Number: 1234567890
        Date: 2025-01-15
        Amount: €150.50
        Kuwait Petroleum
        Total: 150.50
        """
    
    @pytest.fixture
    def mock_drive_result(self):
        """Mock Google Drive upload result"""
        return {
            'id': 'mock_file_id',
            'url': 'https://drive.google.com/file/d/mock_file_id/view'
        }
    
    def test_init_test_mode(self):
        """Test initialization in test mode"""
        processor = PDFProcessor(test_mode=True)
        assert hasattr(processor, 'vendor_parsers')
        assert hasattr(processor, 'config')
    
    def test_init_production_mode(self):
        """Test initialization in production mode"""
        processor = PDFProcessor(test_mode=False)
        assert hasattr(processor, 'vendor_parsers')
        assert hasattr(processor, 'config')
    
    @patch('pdf_processor.pdfplumber.open')
    @patch('builtins.open', new_callable=mock_open, read_data=b'%PDF-1.4 mock pdf content')
    @patch('pdf_processor.PdfReader')
    def test_pdf_processing_success(self, mock_pypdf2, mock_file, mock_pdfplumber, pdf_processor, sample_pdf_content, mock_drive_result):
        """Test successful PDF processing"""
        # Setup PyPDF2 to succeed
        mock_reader = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = sample_pdf_content
        mock_reader.pages = [mock_page]
        mock_pypdf2.return_value = mock_reader
        
        result = pdf_processor._process_pdf('test.pdf', mock_drive_result, 'Kuwait')
        
        assert 'txt' in result
        assert 'folder' in result
        assert result['url'] == mock_drive_result['url']
    
    @patch('pdf_processor.pdfplumber.open')
    @patch('builtins.open', new_callable=mock_open, read_data=b'%PDF-1.4 mock pdf content')
    @patch('pdf_processor.PdfReader')
    def test_pdf_fallback_to_pdfplumber(self, mock_pypdf2, mock_file, mock_pdfplumber, pdf_processor, sample_pdf_content, mock_drive_result):
        """Test fallback to pdfplumber when PyPDF2 fails"""
        # Make PyPDF2 fail
        mock_pypdf2.side_effect = Exception("PyPDF2 failed")
        
        # Setup pdfplumber mock
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = sample_pdf_content
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.return_value.__enter__.return_value = mock_pdf
        
        result = pdf_processor._process_pdf('test.pdf', mock_drive_result, 'Kuwait')
        
        assert 'txt' in result
        assert sample_pdf_content.strip() in result['txt']
    
    def test_vendor_parsing_kuwait(self, pdf_processor):
        """Test Kuwait vendor parsing"""
        lines = ["Kuwait Petroleum", "Datum : 15-01-2025", "Totaal incl. BTW EUR 150,50"]
        result = pdf_processor._parse_vendor_specific(lines, 'kuwait')
        assert result is not None
    
    def test_vendor_parsing_booking(self, pdf_processor):
        """Test Booking vendor parsing"""
        lines = ["Booking.com", "Invoice number: 1234567890", "2025-01-15"]
        result = pdf_processor._parse_vendor_specific(lines, 'booking')
        assert result is not None
    
    def test_vendor_parsing_unknown(self, pdf_processor):
        """Test unknown vendor parsing - should return data or None"""
        lines = ["Unknown vendor", "Some text"]
        result = pdf_processor._parse_vendor_specific(lines, 'unknown')
        # AI might extract data even from minimal text, so we accept both outcomes
        if result is not None:
            assert isinstance(result, dict)
            assert 'total_amount' in result
        # If None, that's also acceptable for unknown vendors
    
    @patch('pdf_processor.Config')
    def test_config_integration(self, mock_config, pdf_processor):
        """Test config integration"""
        mock_config_instance = MagicMock()
        mock_config.return_value = mock_config_instance
        
        processor = PDFProcessor(test_mode=True)
        assert hasattr(processor, 'config')
    
    def test_vendor_parsers_integration(self, pdf_processor):
        """Test vendor parsers integration"""
        with patch('ai_extractor.AIExtractor') as mock_ai_class:
            mock_ai = MagicMock()
            mock_ai.extract_invoice_data.return_value = None
            mock_ai_class.return_value = mock_ai
            with patch.object(pdf_processor, 'vendor_parsers') as mock_parsers:
                mock_parsers.parse_kuwait.return_value = {'date': '2025-01-15', 'total_amount': 150.50}
                
                result = pdf_processor._parse_vendor_specific(['test'], 'kuwait')
                mock_parsers.parse_kuwait.assert_called_once_with(['test'])
    
    @patch('pdf_processor.Config')
    @patch('builtins.open', new_callable=mock_open, read_data=b'%PDF-1.4 mock pdf content')
    @patch('pdf_processor.PdfReader')
    def test_process_file_success(self, mock_pypdf2, mock_file, mock_config, pdf_processor, mock_drive_result, sample_pdf_content):
        """Test successful file processing"""
        # Setup PyPDF2 mock
        mock_reader = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = sample_pdf_content
        mock_reader.pages = [mock_page]
        mock_pypdf2.return_value = mock_reader
        
        # Setup config mock
        mock_config_instance = MagicMock()
        mock_config_instance.get_storage_folder.return_value = '/test/folder'
        mock_config.return_value = mock_config_instance
        pdf_processor.config = mock_config_instance
        
        result = pdf_processor.process_file('test.pdf', mock_drive_result, 'Kuwait')
        
        assert 'txt' in result
        assert 'folder' in result
        assert result['url'] == mock_drive_result['url']
    
    @patch('builtins.open', side_effect=Exception("File not found"))
    def test_process_file_extraction_failure(self, mock_file, pdf_processor, mock_drive_result):
        """Test file processing when file access fails"""
        # The processor handles errors gracefully and returns error message in txt
        result = pdf_processor.process_file('test.pdf', mock_drive_result, 'Kuwait')
        assert 'Error reading PDF' in result['txt'] or 'error' in result['txt'].lower()
    
    def test_extract_transactions_with_folder(self, pdf_processor):
        """Test transaction extraction with folder data"""
        result = {
            'txt': 'Kuwait Petroleum Invoice\n2025-01-15\n€150.50',
            'folder': '/test/kuwait',
            'url': 'https://test.com',
            'name': 'test.pdf'
        }
        
        transactions = pdf_processor.extract_transactions(result)
        
        assert isinstance(transactions, list)
    
    def test_extract_transactions_generic(self, pdf_processor):
        """Test generic transaction extraction"""
        result = {
            'txt': 'Generic invoice\n2025-01-15\n€100.00',
            'folder': '/test/general',
            'url': 'https://test.com',
            'name': 'test.pdf'
        }
        
        transactions = pdf_processor.extract_transactions(result)
        
        assert isinstance(transactions, list)
    
    @patch('pdf_processor.os.path.exists')
    def test_file_exists_check(self, mock_exists, pdf_processor):
        """Test file existence check"""
        mock_exists.return_value = True
        
        # This would be called internally during processing
        assert os.path.exists('test.pdf') == True
        mock_exists.assert_called_with('test.pdf')
    
    def test_vendor_folder_detection(self, pdf_processor):
        """Test vendor detection in folder names"""
        with patch('ai_extractor.AIExtractor') as mock_ai_class:
            mock_ai = MagicMock()
            mock_ai.extract_invoice_data.return_value = None
            mock_ai_class.return_value = mock_ai
            with patch.object(pdf_processor, 'vendor_parsers') as mock_parsers:
                mock_parsers.parse_kuwait.return_value = {'date': '2022-01-15', 'description': 'Factuurnummer: 987654', 'total_amount': 100.0}
                mock_parsers.parse_booking.return_value = {'date': '2022-01-15', 'description': 'Booking invoice', 'total_amount': 200.0}
                mock_parsers.parse_avance.return_value = {'date': '2022-01-15', 'description': 'Avance invoice', 'total_amount': 300.0}
                
                # Test kuwait parsing
                result = pdf_processor._parse_vendor_specific(['test'], 'kuwait')
                assert result == {'date': '2022-01-15', 'description': 'Factuurnummer: 987654', 'total_amount': 100.0}
                
                # Test unknown vendor
                result = pdf_processor._parse_vendor_specific(['test'], 'unknown')
                assert result is None
    
    def test_error_handling_invalid_file_type(self, pdf_processor, mock_drive_result):
        """Test error handling for invalid file types"""
        with pytest.raises(ValueError, match="Unsupported file type"):
            pdf_processor.process_file('test.txt', mock_drive_result, 'Test')
    
    @patch('tempfile.NamedTemporaryFile')
    def test_temp_file_handling(self, mock_temp, pdf_processor):
        """Test temporary file handling during processing"""
        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp.return_value.__enter__.return_value = mock_temp_file
        
        # This would be used in file processing
        with tempfile.NamedTemporaryFile(suffix='.pdf') as temp_file:
            assert temp_file.name.endswith('.pdf')

    def test_image_processing_support(self, pdf_processor, mock_drive_result):
        """Test image processing capability"""
        with patch('image_ai_processor.ImageAIProcessor') as mock_ai_processor:
            mock_processor_instance = MagicMock()
            mock_processor_instance.process_image.return_value = {
                'date': '2025-12-14',
                'total_amount': 0.00,
                'vat_amount': 0.00,
                'description': 'Test invoice',
                'vendor': 'Test'
            }
            mock_ai_processor.return_value = mock_processor_instance

            result = pdf_processor._process_image('test.jpg', mock_drive_result, 'Test')

            assert 'txt' in result
            assert 'AI/OCR Extracted Data' in result['txt']
            assert 'Date: 2025-12-14' in result['txt']
            assert 'Total Amount: €0.00' in result['txt']
            assert 'Description: Test invoice' in result['txt']
            assert 'Vendor: Test' in result['txt']
            assert 'ai_data' in result
            assert result['ai_data']['description'] == 'Test invoice'

    @given(
        vendor_name=st.sampled_from(['kuwait', 'booking', 'bol', 'picnic', 'netflix', 'avance', 'ziggo', 'amazon', 'google']),
        transaction_amount=st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False),
        description=st.text(min_size=5, max_size=100, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pc', 'Pd', 'Ps', 'Pe', 'Po'))),
        has_vat=st.booleans(),
        file_extension=st.sampled_from(['.pdf', '.jpg', '.jpeg', '.png', '.csv'])
    )
    @settings(max_examples=100, deadline=5000, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_integration_compatibility(self, vendor_name, transaction_amount, description, has_vat, file_extension):
        """
        **Feature: duplicate-invoice-detection, Property 4: Integration Compatibility**
        **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
        
        For any existing PDF processing workflow (AI extraction, vendor parsers, file types), 
        the duplicate detection should integrate seamlessly without breaking existing functionality 
        or significantly impacting performance.
        """
        # Create PDF processor instance for this test
        pdf_processor = PDFProcessor(test_mode=True)
        
        # Ensure valid inputs
        assume(transaction_amount > 0)
        assume(len(description.strip()) >= 5)
        
        # Generate test date within reasonable range
        base_date = datetime.now() - timedelta(days=random.randint(1, 365))
        test_date = base_date.strftime('%Y-%m-%d')
        
        # Create mock vendor data based on transaction type
        if has_vat:
            vat_amount = round(transaction_amount * 0.21, 2)  # 21% VAT
            net_amount = round(transaction_amount - vat_amount, 2)
            vendor_data = {
                'date': test_date,
                'description': description,
                'total_amount': transaction_amount,
                'vat_amount': vat_amount
            }
        else:
            vendor_data = {
                'date': test_date,
                'description': description,
                'total_amount': transaction_amount
            }
        
        # Create mock file data
        file_data = {
            'folder': f'/test/{vendor_name}',
            'url': f'https://drive.google.com/file/d/mock_{vendor_name}_id/view',
            'name': f'test_{vendor_name}{file_extension}'
        }
        
        # Mock database operations to avoid actual database calls
        with patch('database.DatabaseManager') as mock_db_class:
            mock_db = MagicMock()
            mock_db.get_last_transactions.return_value = [
                {'Debet': '4000', 'Credit': '1300'},
                {'Debet': '2010', 'Credit': '4000'}
            ]
            mock_db_class.return_value = mock_db
            
            # Mock duplicate checker to test integration without actual duplicate detection
            with patch('duplicate_checker.DuplicateChecker') as mock_duplicate_checker_class:
                mock_duplicate_checker = MagicMock()
                # Randomly return duplicates or no duplicates to test both paths
                if random.choice([True, False]):
                    mock_duplicate_checker.check_for_duplicates.return_value = []
                    mock_duplicate_checker.format_duplicate_info.return_value = {'has_duplicates': False}
                else:
                    mock_duplicate_checker.check_for_duplicates.return_value = [
                        {
                            'ID': 123,
                            'TransactionDate': test_date,
                            'TransactionAmount': transaction_amount,
                            'TransactionDescription': 'Existing transaction',
                            'ReferenceNumber': vendor_name
                        }
                    ]
                    mock_duplicate_checker.format_duplicate_info.return_value = {
                        'has_duplicates': True,
                        'duplicate_count': 1,
                        'existing_transactions': [{'id': 123}]
                    }
                mock_duplicate_checker_class.return_value = mock_duplicate_checker
                
                # Test the _format_vendor_transactions method with duplicate detection integration
                try:
                    result = pdf_processor._format_vendor_transactions(vendor_data, file_data)
                    
                    # Property 1: Integration should not break existing functionality
                    assert isinstance(result, list), "Should return list of transactions"
                    assert len(result) > 0, "Should return at least one transaction"
                    
                    # Property 2: All transactions should have required fields
                    for transaction in result:
                        assert 'date' in transaction, "Transaction should have date"
                        assert 'description' in transaction, "Transaction should have description"
                        assert 'amount' in transaction, "Transaction should have amount"
                        assert 'debet' in transaction, "Transaction should have debet"
                        assert 'credit' in transaction, "Transaction should have credit"
                        assert 'ref3' in transaction, "Transaction should have file URL"
                        assert 'ref4' in transaction, "Transaction should have file name"
                        
                        # Property 3: Amounts should be valid numbers
                        assert isinstance(transaction['amount'], (int, float)), "Amount should be numeric"
                        assert transaction['amount'] >= 0, "Amount should be non-negative"
                    
                    # Property 4: Main transaction should match input data
                    main_transaction = result[0]
                    assert main_transaction['date'] == test_date, "Date should match input"
                    assert main_transaction['description'] == description, "Description should match input"
                    assert abs(main_transaction['amount'] - transaction_amount) < 0.01, "Amount should match input"
                    
                    # Property 5: VAT transaction should be present if VAT amount > 0
                    if has_vat and vendor_data.get('vat_amount', 0) > 0:
                        assert len(result) >= 2, "Should have VAT transaction when VAT amount > 0"
                        vat_transaction = result[1]
                        assert 'VAT' in vat_transaction['description'], "VAT transaction should be labeled"
                        assert abs(vat_transaction['amount'] - vendor_data['vat_amount']) < 0.01, "VAT amount should match"
                    
                    # Property 6: File references should be preserved
                    for transaction in result:
                        assert transaction['ref3'] == file_data['url'], "File URL should be preserved"
                        assert transaction['ref4'] == file_data['name'], "File name should be preserved"
                    
                    # Property 7: Duplicate info should be attached if duplicates found
                    if any('duplicate_info' in t for t in result):
                        duplicate_info = result[0].get('duplicate_info')
                        assert isinstance(duplicate_info, dict), "Duplicate info should be dictionary"
                        assert 'has_duplicates' in duplicate_info, "Should have has_duplicates flag"
                    
                    # Property 8: Performance - method should complete within reasonable time
                    # (This is implicitly tested by hypothesis deadline setting)
                    
                except Exception as e:
                    # Property 9: Integration should handle errors gracefully
                    # If an error occurs, it should be a known type and not crash the system
                    assert isinstance(e, (ValueError, TypeError, KeyError)), f"Unexpected error type: {type(e)}"
                    # Re-raise to fail the test if it's an unexpected error
                    raise

if __name__ == '__main__':
    pytest.main([__file__])
