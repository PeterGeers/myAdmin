import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
import re

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from pdf_validation import PDFValidator


def _cursor_context(mock_db, mock_cursor, mock_conn=None):
    """Wire ``mock_db.return_value.get_cursor()`` as a context manager yielding
    ``(cursor, conn)`` and return the context-manager mock so a test can assert
    it was entered/exited exactly once (connection-lifetime safety)."""
    if mock_conn is None:
        mock_conn = Mock()
    cursor_cm = MagicMock()
    cursor_cm.__enter__.return_value = (mock_cursor, mock_conn)
    cursor_cm.__exit__.return_value = False
    mock_db.return_value.get_cursor.return_value = cursor_cm
    return cursor_cm


def _transaction_context(mock_db, mock_cursor, mock_conn=None):
    """Wire ``mock_db.return_value.transaction()`` as a context manager yielding
    ``(cursor, conn)`` and return the context-manager mock. Entering + exiting the
    context manager IS the commit (transaction() commits on clean __exit__), so a
    write-durability test asserts __enter__/__exit__ were called."""
    if mock_conn is None:
        mock_conn = Mock()
    tx_cm = MagicMock()
    tx_cm.__enter__.return_value = (mock_cursor, mock_conn)
    tx_cm.__exit__.return_value = False
    mock_db.return_value.transaction.return_value = tx_cm
    return tx_cm


class TestPDFValidator:
    
    @patch('pdf_validation.DatabaseManager')
    def test_init_success(self, mock_db):
        validator = PDFValidator(test_mode=True)
        
        assert validator.test_mode is True
        assert validator.drive_service is None
        mock_db.assert_called_once_with(test_mode=True)
    
    @patch('google_drive_service.GoogleDriveService', side_effect=Exception("Auth error"))
    @patch('pdf_validation.DatabaseManager')
    def test_init_drive_service_error(self, mock_db, mock_drive):
        validator = PDFValidator()
        
        assert validator.drive_service is None
        mock_db.assert_called_once_with(test_mode=False)
    
    @patch('pdf_validation.DatabaseManager')
    def test_validate_pdf_urls_success(self, mock_db):
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'ID': 1, 'ReferenceNumber': 'REF001', 'Ref3': 'https://drive.google.com/file/d/123', 'Ref4': 'test.pdf'}
        ]
        cursor_cm = _cursor_context(mock_db, mock_cursor, mock_conn)
        
        validator = PDFValidator()
        with patch.object(validator, '_validate_single_record', return_value={'status': 'ok'}):
            result = validator.validate_pdf_urls()
        
        assert result['total_records'] == 1
        assert result['ok_count'] == 1
        assert result['failed_count'] == 0
        assert result['validation_results'] == []
        # The context manager owns connection lifecycle: acquired once, released once.
        cursor_cm.__enter__.assert_called_once()
        cursor_cm.__exit__.assert_called_once()
    
    @patch('pdf_validation.DatabaseManager')
    def test_validate_pdf_urls_with_failures(self, mock_db):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'ID': 1, 'ReferenceNumber': 'REF001', 'Ref3': 'invalid_url', 'Ref4': 'test.pdf'}
        ]
        _cursor_context(mock_db, mock_cursor)
        
        validator = PDFValidator()
        failed_result = {'status': 'file_not_found', 'record': {'ID': 1}}
        with patch.object(validator, '_validate_single_record', return_value=failed_result):
            result = validator.validate_pdf_urls()
        
        assert result['total_records'] == 1
        assert result['ok_count'] == 0
        assert result['failed_count'] == 1
        assert len(result['validation_results']) == 1
    
    @patch('pdf_validation.DatabaseManager')
    def test_validate_pdf_urls_with_progress_no_records(self, mock_db):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = []
        _cursor_context(mock_db, mock_cursor)
        
        validator = PDFValidator()
        progress_gen = validator.validate_pdf_urls_with_progress(year=2023, administration='Test')
        result = next(progress_gen)
        
        assert result['current'] == 0
        assert result['total'] == 0
        assert result['ok_count'] == 0
        assert result['failed_count'] == 0
    
    @patch('pdf_validation.DatabaseManager')
    def test_validate_pdf_urls_with_progress_with_records(self, mock_db):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'ID': i, 'ReferenceNumber': f'REF{i:03d}', 'Ref3': f'url{i}', 'Ref4': f'file{i}.pdf'}
            for i in range(1, 16)  # 15 records
        ]
        _cursor_context(mock_db, mock_cursor)
        
        validator = PDFValidator()
        with patch.object(validator, '_validate_single_record', return_value={'status': 'ok'}):
            progress_gen = validator.validate_pdf_urls_with_progress()
            results = list(progress_gen)
        
        # Should yield progress at 10 and 15 records
        assert len(results) == 2
        assert results[0]['current'] == 10
        assert results[1]['current'] == 15
        assert results[1]['total'] == 15
        assert results[1]['ok_count'] == 15

    # ------------------------------------------------------------------
    # Generator connection-lifetime safety (Shape 5 / Property 3, Req 5.3):
    # for every consumption pattern — full iteration, early close/break
    # (GeneratorExit), and exception mid-iteration — exactly ONE connection is
    # acquired (get_cursor entered once) and released exactly once (exited once).
    # ------------------------------------------------------------------

    @patch('pdf_validation.DatabaseManager')
    def test_progress_generator_full_iteration_acquires_and_releases_once(self, mock_db):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'ID': i, 'ReferenceNumber': f'REF{i:03d}', 'Ref3': f'url{i}', 'Ref4': f'file{i}.pdf'}
            for i in range(1, 16)  # 15 records -> yields at 10 and 15
        ]
        cursor_cm = _cursor_context(mock_db, mock_cursor)

        validator = PDFValidator()
        with patch.object(validator, '_validate_single_record', return_value={'status': 'ok'}):
            list(validator.validate_pdf_urls_with_progress())  # fully consume

        mock_db.return_value.get_cursor.assert_called_once()
        cursor_cm.__enter__.assert_called_once()
        cursor_cm.__exit__.assert_called_once()

    @patch('pdf_validation.DatabaseManager')
    def test_progress_generator_early_close_releases_once(self, mock_db):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'ID': i, 'ReferenceNumber': f'REF{i:03d}', 'Ref3': f'url{i}', 'Ref4': f'file{i}.pdf'}
            for i in range(1, 31)  # 30 records
        ]
        cursor_cm = _cursor_context(mock_db, mock_cursor)

        validator = PDFValidator()
        with patch.object(validator, '_validate_single_record', return_value={'status': 'ok'}):
            gen = validator.validate_pdf_urls_with_progress()
            next(gen)              # pull only the first progress yield (at 10)
            gen.close()            # consumer stops early -> GeneratorExit

        # Connection acquired once and released exactly once despite early close.
        cursor_cm.__enter__.assert_called_once()
        cursor_cm.__exit__.assert_called_once()

    @patch('pdf_validation.DatabaseManager')
    def test_progress_generator_exception_mid_iteration_releases_once(self, mock_db):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'ID': i, 'ReferenceNumber': f'REF{i:03d}', 'Ref3': f'url{i}', 'Ref4': f'file{i}.pdf'}
            for i in range(1, 16)
        ]
        cursor_cm = _cursor_context(mock_db, mock_cursor)

        validator = PDFValidator()
        # _validate_single_record raising propagates out of the generator body;
        # the with-block must still release the connection exactly once.
        with patch.object(validator, '_validate_single_record', side_effect=RuntimeError("boom")):
            gen = validator.validate_pdf_urls_with_progress()
            with pytest.raises(RuntimeError):
                list(gen)

        cursor_cm.__enter__.assert_called_once()
        cursor_cm.__exit__.assert_called_once()
    
    @patch('pdf_validation.DatabaseManager')
    def test_get_administrations_for_year(self, mock_db):
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            {'Administration': 'Test1'},
            {'Administration': 'Test2'},
            {'Administration': None}  # Should be filtered out
        ]
        _cursor_context(mock_db, mock_cursor)
        
        validator = PDFValidator()
        result = validator.get_administrations_for_year(2023)
        
        assert result == ['Test1', 'Test2']
        mock_cursor.execute.assert_called_once()
        assert '2023' in str(mock_cursor.execute.call_args)
    
    def test_validate_single_record_gmail_url(self):
        validator = PDFValidator()
        record = {'Ref3': 'https://mail.google.com/mail/u/0/#inbox/123', 'Ref4': 'test.pdf'}
        
        result = validator._validate_single_record(record)
        
        assert result['status'] == 'gmail_manual_check'
        assert result['record'] == record
    
    def test_validate_single_record_file_url_exists(self):
        validator = PDFValidator()
        record = {'Ref3': 'https://drive.google.com/file/d/abc123/view', 'Ref4': 'test.pdf'}
        
        with patch.object(validator, '_extract_file_id', return_value='abc123'):
            with patch.object(validator, '_file_exists', return_value=True):
                result = validator._validate_single_record(record)
        
        assert result['status'] == 'ok'
    
    def test_validate_single_record_file_url_not_exists(self):
        validator = PDFValidator()
        record = {'Ref3': 'https://drive.google.com/file/d/abc123/view', 'Ref4': 'test.pdf'}
        
        with patch.object(validator, '_extract_file_id', return_value='abc123'):
            with patch.object(validator, '_file_exists', return_value=False):
                result = validator._validate_single_record(record)
        
        assert result['status'] == 'file_not_found'
    
    def test_validate_single_record_folder_url_file_found(self):
        validator = PDFValidator()
        record = {'ID': 1, 'Ref3': 'https://drive.google.com/folders/folder123', 'Ref4': 'test.pdf'}
        
        with patch.object(validator, '_extract_folder_id', return_value='folder123'):
            with patch.object(validator, '_find_file_in_folder', return_value='https://drive.google.com/file/d/file123'):
                with patch.object(validator, '_update_ref3'):
                    result = validator._validate_single_record(record)
        
        assert result['status'] == 'updated'
        assert result['new_url'] == 'https://drive.google.com/file/d/file123'
    
    def test_validate_single_record_folder_url_file_not_found(self):
        validator = PDFValidator()
        record = {'Ref3': 'https://drive.google.com/folders/folder123', 'Ref4': 'test.pdf'}
        
        with patch.object(validator, '_extract_folder_id', return_value='folder123'):
            with patch.object(validator, '_find_file_in_folder', return_value=None):
                result = validator._validate_single_record(record)
        
        assert result['status'] == 'file_not_in_folder'
    
    def test_validate_single_record_error(self):
        validator = PDFValidator()
        record = {'Ref3': 'invalid_url', 'Ref4': 'test.pdf', 'ReferenceNumber': 'REF001'}
        
        with patch.object(validator, '_find_folder_by_reference', side_effect=Exception("Parse error")):
            result = validator._validate_single_record(record)
        
        assert result['status'] == 'error'
        assert 'error' in result
    
    def test_extract_file_id_file_d_format(self):
        validator = PDFValidator()
        url = 'https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit'
        
        result = validator._extract_file_id(url)
        
        assert result == '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms'
    
    def test_extract_file_id_open_format(self):
        validator = PDFValidator()
        url = 'https://drive.google.com/open?id=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms'
        
        result = validator._extract_file_id(url)
        
        assert result == '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms'
    
    def test_extract_file_id_html_encoded(self):
        validator = PDFValidator()
        url = 'https://drive.google.com/open?id=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms&amp;usp=sharing'
        
        result = validator._extract_file_id(url)
        
        assert result == '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms'
    
    def test_extract_file_id_invalid_url(self):
        validator = PDFValidator()
        url = 'https://example.com/invalid'
        
        result = validator._extract_file_id(url)
        
        assert result is None
    
    def test_extract_folder_id_success(self):
        validator = PDFValidator()
        url = 'https://drive.google.com/folders/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms'
        
        result = validator._extract_folder_id(url)
        
        assert result == '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms'
    
    def test_extract_folder_id_invalid_url(self):
        validator = PDFValidator()
        url = 'https://example.com/invalid'
        
        result = validator._extract_folder_id(url)
        
        assert result is None
    
    def test_file_exists_no_drive_service(self):
        validator = PDFValidator()
        validator.drive_service = None
        
        result = validator._file_exists('file123')
        
        assert result is False
    
    def test_file_exists_success(self):
        validator = PDFValidator()
        mock_service = Mock()
        mock_service.files.return_value.get.return_value.execute.return_value = {'name': 'test.pdf'}
        validator.drive_service = Mock()
        validator.drive_service.service = mock_service
        
        result = validator._file_exists('file123')
        
        assert result is True
        mock_service.files.return_value.get.assert_called_once_with(fileId='file123')
    
    def test_file_exists_not_found(self):
        validator = PDFValidator()
        mock_service = Mock()
        mock_service.files.return_value.get.return_value.execute.side_effect = Exception("Not found")
        validator.drive_service = Mock()
        validator.drive_service.service = mock_service
        
        result = validator._file_exists('file123')
        
        assert result is False
    
    def test_find_file_in_folder_no_drive_service(self):
        validator = PDFValidator()
        validator.drive_service = None
        
        result = validator._find_file_in_folder('folder123', 'test.pdf')
        
        assert result is None
    
    def test_find_file_in_folder_found(self):
        validator = PDFValidator()
        mock_service = Mock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            'files': [
                {'id': 'file123', 'name': 'test.pdf'},
                {'id': 'file456', 'name': 'other.pdf'}
            ]
        }
        validator.drive_service = Mock()
        validator.drive_service.service = mock_service
        
        result = validator._find_file_in_folder('folder123', 'test.pdf')
        
        assert result == 'https://drive.google.com/file/d/file123/view'
    
    def test_find_file_in_folder_not_found(self):
        validator = PDFValidator()
        mock_service = Mock()
        mock_service.files.return_value.list.return_value.execute.return_value = {
            'files': [{'id': 'file456', 'name': 'other.pdf'}]
        }
        validator.drive_service = Mock()
        validator.drive_service.service = mock_service
        
        result = validator._find_file_in_folder('folder123', 'test.pdf')
        
        assert result is None
    
    def test_find_file_in_folder_error(self):
        validator = PDFValidator()
        mock_service = Mock()
        mock_service.files.return_value.list.return_value.execute.side_effect = Exception("API error")
        validator.drive_service = Mock()
        validator.drive_service.service = mock_service
        
        result = validator._find_file_in_folder('folder123', 'test.pdf')
        
        assert result is None
    
    @patch('pdf_validation.DatabaseManager')
    def test_update_ref3(self, mock_db):
        mock_cursor = Mock()
        tx_cm = _transaction_context(mock_db, mock_cursor)
        
        validator = PDFValidator()
        validator._update_ref3(123, 'https://new-url.com')
        
        mock_cursor.execute.assert_called_once_with(
            "UPDATE mutaties SET Ref3 = %s WHERE ID = %s",
            ['https://new-url.com', 123]
        )
        # Commit-durability (Req 3.6): the UPDATE runs inside transaction(), which
        # commits on clean exit. One transaction opened and committed exactly once.
        mock_db.return_value.transaction.assert_called_once()
        tx_cm.__enter__.assert_called_once()
        tx_cm.__exit__.assert_called_once()
        # No raw-connection commit path should be used anymore.
        mock_db.return_value.get_connection.assert_not_called()
    
    @patch('pdf_validation.DatabaseManager')
    def test_update_record_success(self, mock_db):
        mock_cursor = Mock()
        mock_cursor.rowcount = 2
        tx_cm = _transaction_context(mock_db, mock_cursor)
        
        validator = PDFValidator()
        result = validator.update_record('old_url', reference_number='REF001', ref3='new_url', ref4='new_file.pdf', administration='test-tenant')
        
        assert result is True
        mock_cursor.execute.assert_called_once()
        # Verify the query includes administration scoping
        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'AND administration = %s' in query
        assert params[-1] == 'test-tenant'
        # Commit-durability (Req 3.6): the UPDATE runs inside transaction(),
        # which commits exactly once on clean exit.
        mock_db.return_value.transaction.assert_called_once()
        tx_cm.__enter__.assert_called_once()
        tx_cm.__exit__.assert_called_once()
    
    @patch('pdf_validation.DatabaseManager')
    def test_update_record_no_updates(self, mock_db):
        validator = PDFValidator()
        result = validator.update_record('old_url', administration='test-tenant')
        
        assert result is False
        # No updatable fields -> no transaction is ever opened (no empty commit).
        mock_db.return_value.transaction.assert_not_called()
    
    @patch('pdf_validation.DatabaseManager')
    def test_update_record_error(self, mock_db):
        mock_cursor = Mock()
        mock_cursor.execute.side_effect = Exception("Database error")
        tx_cm = _transaction_context(mock_db, mock_cursor)
        
        validator = PDFValidator()
        result = validator.update_record('old_url', ref3='new_url', administration='test-tenant')
        
        assert result is False
        # transaction() handles rollback on error; its __exit__ is invoked with the
        # raised exception so the write is rolled back, not committed.
        tx_cm.__enter__.assert_called_once()
        tx_cm.__exit__.assert_called_once()
        exit_exc_type = tx_cm.__exit__.call_args[0][0]
        assert exit_exc_type is not None

    @patch('pdf_validation.DatabaseManager')
    def test_update_record_own_tenant_succeeds(self, mock_db):
        """Verify update succeeds when administration matches the record's tenant."""
        mock_cursor = Mock()
        mock_cursor.rowcount = 1
        _transaction_context(mock_db, mock_cursor)
        
        validator = PDFValidator()
        result = validator.update_record(
            'https://drive.google.com/file/d/old123',
            ref3='https://drive.google.com/file/d/new456',
            administration='MyTenant'
        )
        
        assert result is True
        call_args = mock_cursor.execute.call_args[0]
        query = call_args[0]
        params = call_args[1]
        assert 'WHERE Ref3 = %s AND administration = %s' in query
        assert params[-2] == 'https://drive.google.com/file/d/old123'
        assert params[-1] == 'MyTenant'

    @patch('pdf_validation.DatabaseManager')
    def test_update_record_other_tenant_returns_false(self, mock_db):
        """Verify update returns False when no records match the administration filter."""
        mock_cursor = Mock()
        mock_cursor.rowcount = 0  # No rows matched — wrong tenant
        _transaction_context(mock_db, mock_cursor)
        
        validator = PDFValidator()
        result = validator.update_record(
            'https://drive.google.com/file/d/old123',
            ref3='https://drive.google.com/file/d/new456',
            administration='WrongTenant'
        )
        
        assert result is False
    
    def test_find_folder_by_reference(self):
        validator = PDFValidator()
        result = validator._find_folder_by_reference('REF001')
        
        # Currently returns None as it's a placeholder
        assert result is None