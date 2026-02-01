"""
Test suite for AI vision image processing
"""
import pytest
import sys
import os
from unittest.mock import Mock, patch, mock_open
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from image_ai_processor import ImageAIProcessor

class TestImageAIProcessor:
    """Test cases for ImageAIProcessor"""
    
    def test_processor_initialization(self):
        """Test ImageAIProcessor can be initialized"""
        processor = ImageAIProcessor()
        assert processor is not None
        assert hasattr(processor, 'api_key')
        assert hasattr(processor, 'base_url')
    
    @patch('image_ai_processor.os.path.exists')
    @patch('image_ai_processor.open', new_callable=mock_open, read_data=b'fake_image_data')
    @patch('image_ai_processor.base64.b64encode')
    def test_process_image_with_valid_file(self, mock_b64encode, mock_file, mock_exists):
        """Test processing image with valid file"""
        mock_exists.return_value = True
        mock_b64encode.return_value = b'encoded_image_data'
        
        processor = ImageAIProcessor()
        
        # Mock the AI vision method to return a result
        with patch.object(processor, '_try_ai_vision') as mock_ai_vision:
            mock_ai_vision.return_value = {
                'date': '2023-01-01',
                'total_amount': 100.0,
                'vat_amount': 21.0,
                'description': 'Test transaction',
                'vendor': 'Test Vendor'
            }
            
            result = processor.process_image('test_image.jpg', vendor_hint="Test Vendor")
            
            assert result is not None
            assert result['total_amount'] == 100.0
            assert result['vendor'] == 'Test Vendor'
    
    @patch('image_ai_processor.os.path.exists')
    def test_process_image_with_invalid_file(self, mock_exists):
        """Test processing image with invalid file path"""
        mock_exists.return_value = False
        
        processor = ImageAIProcessor()
        
        # Mock both AI vision and tesseract to return None for invalid file
        with patch.object(processor, '_try_ai_vision') as mock_ai_vision, \
             patch.object(processor, '_try_tesseract') as mock_tesseract:
            mock_ai_vision.return_value = None
            mock_tesseract.return_value = {
                'date': '',
                'total_amount': 0.0,
                'vat_amount': 0.0,
                'description': '',
                'vendor': ''
            }
            
            result = processor.process_image('nonexistent.jpg')
            
            assert result is not None
            assert result['total_amount'] == 0.0
    
    def test_processor_without_api_key(self):
        """Test processor behavior without API key"""
        with patch.dict(os.environ, {}, clear=True):
            processor = ImageAIProcessor()
            assert processor.api_key is None
    
    @patch('image_ai_processor.requests.post')
    def test_ai_vision_api_call(self, mock_post):
        """Test AI vision API call handling"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'choices': [{
                'message': {
                    'content': '{"date": "2023-01-01", "total_amount": 100.0, "vat_amount": 21.0, "description": "Test", "vendor": "Test Vendor"}'
                }
            }]
        }
        mock_post.return_value = mock_response
        
        processor = ImageAIProcessor()
        processor.api_key = 'test_key'
        
        with patch('image_ai_processor.open', mock_open(read_data=b'fake_image')), \
             patch('image_ai_processor.base64.b64encode', return_value=b'encoded_data'):
            
            result = processor._try_ai_vision('test.jpg', 'Test Vendor', None)
            
            # Should make API call
            mock_post.assert_called_once()
    
    def test_fallback_to_tesseract(self):
        """Test fallback to Tesseract when AI vision fails"""
        processor = ImageAIProcessor()
        
        with patch.object(processor, '_try_ai_vision') as mock_ai_vision, \
             patch.object(processor, '_try_tesseract') as mock_tesseract:
            
            # AI vision returns None (failure)
            mock_ai_vision.return_value = None
            
            # Tesseract returns a result
            mock_tesseract.return_value = {
                'date': '2023-01-01',
                'total_amount': 50.0,
                'vat_amount': 10.5,
                'description': 'OCR extracted text',
                'vendor': 'OCR Vendor'
            }
            
            result = processor.process_image('test.jpg')
            
            # Should try AI vision first, then fall back to Tesseract
            mock_ai_vision.assert_called_once()
            mock_tesseract.assert_called_once()
            assert result['total_amount'] == 50.0
            assert result['description'] == 'OCR extracted text'
