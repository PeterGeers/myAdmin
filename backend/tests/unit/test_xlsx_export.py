import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
import pandas as pd
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from xlsx_export import XLSXExportProcessor

class TestXLSXExportProcessor:
    
    @patch('xlsx_export.DatabaseManager')
    def test_init(self, mock_db):
        processor = XLSXExportProcessor(test_mode=True)
        
        assert processor.test_mode is True
        mock_db.assert_called_once_with(test_mode=True)
        # Should use Docker path if in container, otherwise Windows path
        if os.getenv('DOCKER_ENV') or os.path.exists('/.dockerenv'):
            expected_path = '/app/reports'
        else:
            expected_path = r'C:\Users\peter\OneDrive\Admin\reports'
        assert processor.default_output_base_path == expected_path
        assert processor.folder_search_log == []
        assert processor.template_service is not None
    
    @patch('xlsx_export.DatabaseManager')
    def test_make_ledgers_with_data(self, mock_db):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.side_effect = [
            [{'Reknum': '1000', 'AccountName': 'Cash', 'Parent': 'Assets', 'Administration': 'Test', 'Amount': 1000.0}],
            [{'TransactionNumber': 'T001', 'TransactionDate': '2023-01-15', 'TransactionDescription': 'Test transaction', 
              'Amount': 500.0, 'Reknum': '1000', 'AccountName': 'Cash', 'Parent': 'Assets', 'Administration': 'Test',
              'VW': 'N', 'jaar': 2023, 'kwartaal': 1, 'maand': 1, 'week': 3, 'ReferenceNumber': 'REF001',
              'DocUrl': 'https://drive.google.com/file/d/123', 'Document': 'receipt.pdf'}]
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_db.return_value.get_connection.return_value = mock_conn
        
        processor = XLSXExportProcessor()
        result = processor.make_ledgers(2023, 'Test')
        
        assert len(result) == 2
        assert result[0]['TransactionNumber'] == 'Beginbalans 2023'
        assert result[0]['Amount'] == 1000.0
        assert result[1]['TransactionNumber'] == 'T001'
        assert result[1]['Amount'] == 500.0
        mock_cursor.execute.assert_called()
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('xlsx_export.DatabaseManager')
    def test_make_ledgers_no_data(self, mock_db):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.side_effect = [[], []]
        mock_conn.cursor.return_value = mock_cursor
        mock_db.return_value.get_connection.return_value = mock_conn
        
        processor = XLSXExportProcessor()
        result = processor.make_ledgers(2023, 'Test')
        
        assert result == []
    
    @patch('xlsx_export.os.makedirs')
    def test_export_files_no_drive_urls(self, mock_makedirs):
        processor = XLSXExportProcessor()
        data = [{'TransactionNumber': 'T001', 'Amount': 100}]
        
        result = processor.export_files(data, 2023, 'Test')
        
        assert result == 0
        mock_makedirs.assert_called_once()
    
    @patch('xlsx_export.os.makedirs')
    @patch.object(XLSXExportProcessor, '_get_drive_service')
    @patch.object(XLSXExportProcessor, '_download_drive_file')
    def test_export_files_with_drive_urls(self, mock_download, mock_get_service, mock_makedirs):
        mock_get_service.return_value = Mock()
        mock_download.return_value = True
        
        processor = XLSXExportProcessor()
        data = [{'DocUrl': 'https://drive.google.com/file/d/123', 'ReferenceNumber': 'REF001', 'Document': 'test.pdf'}]
        
        with patch('builtins.open', mock_open()):
            result = processor.export_files(data, 2023, 'Test')
        
        assert result == 1
    
    @patch.object(XLSXExportProcessor, 'write_workbook')
    def test_write_workbook_basic(self, mock_write):
        mock_write.return_value = 'test.xlsx'
        
        processor = XLSXExportProcessor()
        data = [{'Amount': 100, 'TransactionNumber': 'T001'}]
        
        result = processor.write_workbook(data, 'test.xlsx')
        
        assert result == 'test.xlsx'
        mock_write.assert_called_once_with(data, 'test.xlsx')
    
    @patch.object(XLSXExportProcessor, 'make_ledgers')
    @patch.object(XLSXExportProcessor, 'write_workbook')
    @patch.object(XLSXExportProcessor, 'export_files')
    def test_generate_xlsx_export_success(self, mock_export, mock_write, mock_ledgers):
        mock_ledgers.return_value = [{'Amount': 100, 'TransactionNumber': 'T001'}]
        mock_write.return_value = 'test.xlsx'
        mock_export.return_value = 5
        
        processor = XLSXExportProcessor()
        result = processor.generate_xlsx_export(['Test'], [2023])
        
        assert len(result) == 1
        assert result[0]['success'] is True
        assert result[0]['administration'] == 'Test'
        assert result[0]['year'] == 2023
        assert result[0]['records'] == 1
        assert result[0]['files_processed'] == 5
    
    @patch.object(XLSXExportProcessor, 'make_ledgers')
    def test_generate_xlsx_export_no_data(self, mock_ledgers):
        mock_ledgers.return_value = []
        
        processor = XLSXExportProcessor()
        result = processor.generate_xlsx_export(['Test'], [2023])
        
        assert len(result) == 1
        assert result[0]['success'] is False
        assert 'No data found' in result[0]['error']
    
    @patch.object(XLSXExportProcessor, 'make_ledgers')
    def test_generate_xlsx_export_error(self, mock_ledgers):
        mock_ledgers.side_effect = Exception("Database error")
        
        processor = XLSXExportProcessor()
        result = processor.generate_xlsx_export(['Test'], [2023])
        
        assert len(result) == 1
        assert result[0]['success'] is False
        assert result[0]['error'] == "Database error"
    
    def test_find_document_in_folder_exact_match(self):
        mock_service = Mock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            'files': [
                {'id': 'file1', 'name': 'test.pdf', 'mimeType': 'application/pdf'},
                {'id': 'file2', 'name': 'other.pdf', 'mimeType': 'application/pdf'}
            ]
        }
        
        processor = XLSXExportProcessor()
        with patch.object(processor, '_download_single_file', return_value=True):
            result = processor._find_document_in_folder(mock_service, 'folder123', '/dest', 'test.pdf')
        
        assert result is True
    
    def test_find_document_in_folder_no_match(self):
        mock_service = Mock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            'files': [
                {'id': 'file1', 'name': 'other.pdf', 'mimeType': 'application/pdf'}
            ]
        }
        
        processor = XLSXExportProcessor()
        result = processor._find_document_in_folder(mock_service, 'folder123', '/dest', 'test.pdf')
        
        assert result is False
        assert len(processor.folder_search_log) == 1
        assert processor.folder_search_log[0]['document_searched'] == 'test.pdf'
    
    def test_find_document_in_folder_error(self):
        mock_service = Mock()
        mock_service.files.return_value.list.return_value.execute.side_effect = Exception("API Error")
        
        processor = XLSXExportProcessor()
        result = processor._find_document_in_folder(mock_service, 'folder123', '/dest', 'test.pdf')
        
        assert result is False
    
    @patch('xlsx_export.io.FileIO')
    @patch('xlsx_export.MediaIoBaseDownload')
    def test_download_single_file_success(self, mock_download, mock_fileio):
        mock_service = Mock()
        mock_service.files.return_value.get_media.return_value = Mock()
        mock_downloader = Mock()
        mock_downloader.next_chunk.side_effect = [(None, False), (None, True)]
        mock_download.return_value = mock_downloader
        
        processor = XLSXExportProcessor()
        result = processor._download_single_file(mock_service, 'file123', 'test.pdf', 'C:\\dest')
        
        assert result is True
        mock_fileio.assert_called_once_with('C:\\dest\\test.pdf', 'wb')
    
    @patch('xlsx_export.io.FileIO')
    def test_download_single_file_error(self, mock_fileio):
        mock_service = Mock()
        mock_service.files.return_value.get_media.side_effect = Exception("Download error")
        
        processor = XLSXExportProcessor()
        result = processor._download_single_file(mock_service, 'file123', 'test.pdf', '/dest')
        
        assert result is False
    
    @patch('xlsx_export.GoogleDriveService')
    def test_get_drive_service_success(self, mock_drive_service):
        mock_service = Mock()
        mock_drive_service.return_value.service = mock_service
        
        processor = XLSXExportProcessor()
        result = processor._get_drive_service()
        
        assert result == mock_service
    
    @patch('xlsx_export.GoogleDriveService')
    def test_get_drive_service_error(self, mock_drive_service):
        mock_drive_service.side_effect = Exception("Auth error")
        
        processor = XLSXExportProcessor()
        result = processor._get_drive_service()
        
        assert result is None
    
    def test_download_drive_file_basic(self):
        processor = XLSXExportProcessor()
        mock_service = Mock()
        mock_service.files.return_value.get.side_effect = Exception("File not found")
        
        result = processor._download_drive_file(mock_service, 'invalid_url', 'C:\\dest')
        
        assert result is False
    
    def test_download_drive_file_folder_type(self):
        processor = XLSXExportProcessor()
        mock_service = Mock()
        mock_service.files.return_value.get.return_value.execute.return_value = {
            'name': 'folder',
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        with patch.object(processor, '_find_document_in_folder', return_value=True):
            result = processor._download_drive_file(mock_service, 'https://drive.google.com/folders/abc123', '/dest', 'test.pdf')
        
        assert result is True
    
    def test_download_drive_file_error(self):
        processor = XLSXExportProcessor()
        mock_service = Mock()
        mock_service.files.return_value.get.side_effect = Exception("File not found")
        
        result = processor._download_drive_file(mock_service, 'invalid_url', '/dest')
        
        assert result is False