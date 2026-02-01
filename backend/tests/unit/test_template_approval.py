"""
Unit tests for Template Approval Workflow
Tests template approval, Google Drive integration, and metadata management
"""

import sys
import os
import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

# Add backend/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.template_preview_service import TemplatePreviewService


class TestTemplateApproval:
    """Test template approval workflow"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()
        self.administration = 'TestAdmin'
        self.service = TemplatePreviewService(self.mock_db, self.administration)
    
    @patch('google_drive_service.GoogleDriveService')
    def test_approve_template_success(self, mock_drive_service):
        """Test successful template approval"""
        # Setup
        template_type = 'str_invoice_nl'
        template_content = """
        <html>
            <body>
                <h1>Invoice {{ invoice_number }}</h1>
                <p>Guest: {{ guest_name }}</p>
                <p>Check-in: {{ checkin_date }}</p>
                <p>Check-out: {{ checkout_date }}</p>
                <p>Amount: {{ amount_gross }}</p>
                <p>Company: {{ company_name }}</p>
            </body>
        </html>
        """
        field_mappings = {'custom_field': 'value'}
        user_email = 'admin@example.com'
        notes = 'Approved for production'
        
        # Mock Google Drive upload
        mock_drive_instance = Mock()
        mock_drive_instance.service.files().create().execute.return_value = {'id': 'file123'}
        mock_drive_service.return_value = mock_drive_instance
        
        # Mock template service get_template_metadata to return None (no existing template)
        with patch.object(self.service.template_service, 'get_template_metadata', return_value=None):
            # Mock internal methods
            with patch.object(self.service, '_update_template_metadata') as mock_update:
                with patch.object(self.service, '_log_template_approval') as mock_log:
                    # Execute
                    result = self.service.approve_template(
                        template_type,
                        template_content,
                        field_mappings,
                        user_email,
                        notes
                    )
        
        # Assert
        assert result['success'] is True, "Approval should succeed"
        assert 'template_id' in result, "Should return template_id"
        assert 'file_id' in result, "Should return file_id"
        assert result['file_id'] == 'file123', "Should return correct file_id"
        assert 'message' in result, "Should return success message"
        
        # Verify Google Drive was called
        assert mock_drive_service.called, "Should initialize Google Drive service"
        
        # Verify metadata update was called
        assert mock_update.called, "Should update metadata"
        assert mock_log.called, "Should log approval"
    
    def test_approve_template_validation_failure(self):
        """Test approval fails for invalid template"""
        # Setup
        template_type = 'str_invoice_nl'
        invalid_template = """
        <html>
            <body>
                <div>
                    <p>Missing closing div
                <script>alert('bad');</script>
            </body>
        </html>
        """
        field_mappings = {}
        user_email = 'admin@example.com'
        notes = ''
        
        # Execute
        result = self.service.approve_template(
            template_type,
            invalid_template,
            field_mappings,
            user_email,
            notes
        )
        
        # Assert
        assert result['success'] is False, "Approval should fail for invalid template"
        assert 'message' in result, "Should return error message"
        assert 'validation' in result, "Should return validation results"
        assert result['validation']['is_valid'] is False, "Template should be invalid"
    
    @patch('google_drive_service.GoogleDriveService')
    def test_approve_template_with_previous_version(self, mock_drive_service):
        """Test approval archives previous version"""
        # Setup
        template_type = 'btw_aangifte'
        template_content = """
        <html>
            <body>
                <h1>BTW Aangifte {{ year }} Q{{ quarter }}</h1>
                <p>Administration: {{ administration }}</p>
                <table>{{ balance_rows }}</table>
                <table>{{ quarter_rows }}</table>
                <p>{{ payment_instruction }}</p>
            </body>
        </html>
        """
        field_mappings = {}
        user_email = 'admin@example.com'
        notes = 'Updated template'
        
        # Mock Google Drive upload
        mock_drive_instance = Mock()
        mock_drive_instance.service.files().create().execute.return_value = {'id': 'file456'}
        mock_drive_service.return_value = mock_drive_instance
        
        # Mock database queries - existing template found
        self.mock_db.execute_query = Mock(side_effect=[
            [{'id': 1, 'template_file_id': 'old_file123', 'version': 1}],  # Existing template
            None  # Update successful
        ])
        
        # Mock template service
        with patch.object(self.service.template_service, 'get_template_metadata') as mock_get_metadata:
            mock_get_metadata.return_value = {
                'template_file_id': 'old_file123',
                'version': 1
            }
            
            # Execute
            result = self.service.approve_template(
                template_type,
                template_content,
                field_mappings,
                user_email,
                notes
            )
        
        # Assert
        assert result['success'] is True, "Approval should succeed"
        assert 'previous_version' in result, "Should include previous version info"
        assert result['previous_version']['file_id'] == 'old_file123', \
            "Should reference old file_id"
        assert 'archived_at' in result['previous_version'], \
            "Should include archive timestamp"
    
    @patch('google_drive_service.GoogleDriveService')
    def test_approve_template_google_drive_error(self, mock_drive_service):
        """Test handling of Google Drive upload errors"""
        # Setup
        template_type = 'aangifte_ib'
        template_content = """
        <html>
            <body>
                <h1>Aangifte IB {{ year }}</h1>
                <p>Administration: {{ administration }}</p>
                <table>{{ table_rows }}</table>
                <p>Generated: {{ generated_date }}</p>
            </body>
        </html>
        """
        field_mappings = {}
        user_email = 'admin@example.com'
        notes = ''
        
        # Mock Google Drive to raise exception
        mock_drive_service.side_effect = Exception("Google Drive connection failed")
        
        # Mock database queries
        self.mock_db.execute_query = Mock(return_value=[])
        
        # Execute
        result = self.service.approve_template(
            template_type,
            template_content,
            field_mappings,
            user_email,
            notes
        )
        
        # Assert
        assert result['success'] is False, "Approval should fail on Google Drive error"
        assert 'message' in result, "Should return error message"
        assert 'Google Drive' in result['message'] or 'Failed' in result['message'], \
            "Error message should mention the failure"
    
    @patch('google_drive_service.GoogleDriveService')
    def test_approve_template_database_error(self, mock_drive_service):
        """Test handling of database update errors"""
        # Setup
        template_type = 'toeristenbelasting'
        template_content = """
        <html>
            <body>
                <h1>Toeristenbelasting {{ year }}</h1>
                <p>Contact: {{ contact_name }} ({{ contact_email }})</p>
                <p>Nights: {{ nights_total }}</p>
                <p>Revenue: {{ revenue_total }}</p>
                <p>Tourist Tax: {{ tourist_tax_total }}</p>
            </body>
        </html>
        """
        field_mappings = {}
        user_email = 'admin@example.com'
        notes = ''
        
        # Mock Google Drive upload (succeeds)
        mock_drive_instance = Mock()
        mock_drive_instance.service.files().create().execute.return_value = {'id': 'file789'}
        mock_drive_service.return_value = mock_drive_instance
        
        # Mock database to raise exception
        self.mock_db.execute_query = Mock(side_effect=Exception("Database connection lost"))
        
        # Execute
        result = self.service.approve_template(
            template_type,
            template_content,
            field_mappings,
            user_email,
            notes
        )
        
        # Assert
        assert result['success'] is False, "Approval should fail on database error"
        assert 'message' in result, "Should return error message"
    
    @patch('google_drive_service.GoogleDriveService')
    def test_approve_template_with_field_mappings(self, mock_drive_service):
        """Test approval with custom field mappings"""
        # Setup
        template_type = 'str_invoice_en'
        template_content = """
        <html>
            <body>
                <h1>Invoice {{ invoice_number }}</h1>
                <p>Guest: {{ guest_name }}</p>
                <p>Check-in: {{ checkin_date }}</p>
                <p>Check-out: {{ checkout_date }}</p>
                <p>Amount: {{ amount_gross }}</p>
                <p>Company: {{ company_name }}</p>
            </body>
        </html>
        """
        field_mappings = {
            'invoice_number': 'custom_invoice_field',
            'guest_name': 'booking_guest_name',
            'amount_gross': 'total_amount'
        }
        user_email = 'admin@example.com'
        notes = 'Custom field mappings applied'
        
        # Mock Google Drive upload
        mock_drive_instance = Mock()
        mock_drive_instance.service.files().create().execute.return_value = {'id': 'file999'}
        mock_drive_service.return_value = mock_drive_instance
        
        # Mock template service
        with patch.object(self.service.template_service, 'get_template_metadata', return_value=None):
            # Mock internal methods
            with patch.object(self.service, '_update_template_metadata') as mock_update:
                with patch.object(self.service, '_log_template_approval') as mock_log:
                    # Execute
                    result = self.service.approve_template(
                        template_type,
                        template_content,
                        field_mappings,
                        user_email,
                        notes
                    )
        
        # Assert
        assert result['success'] is True, "Approval should succeed with field mappings"
        assert result['file_id'] == 'file999', "Should return correct file_id"
        
        # Verify metadata update was called with field mappings
        assert mock_update.called, "Should update metadata"
        call_args = mock_update.call_args[0]
        assert call_args[2] == field_mappings, "Should pass field mappings to metadata update"
    
    @patch('google_drive_service.GoogleDriveService')
    def test_approve_template_with_notes(self, mock_drive_service):
        """Test approval with approval notes"""
        # Setup
        template_type = 'financial_report'
        template_content = """
        <html>
            <body>
                <h1>Financial Report {{ year }}</h1>
                <p>Administration: {{ administration }}</p>
                <p>Report Type: {{ report_type }}</p>
            </body>
        </html>
        """
        field_mappings = {}
        user_email = 'admin@example.com'
        notes = 'Approved after review by finance team. Changes include updated logo and formatting.'
        
        # Mock Google Drive upload
        mock_drive_instance = Mock()
        mock_drive_instance.service.files().create().execute.return_value = {'id': 'file111'}
        mock_drive_service.return_value = mock_drive_instance
        
        # Mock template service
        with patch.object(self.service.template_service, 'get_template_metadata', return_value=None):
            # Mock internal methods
            with patch.object(self.service, '_update_template_metadata') as mock_update:
                with patch.object(self.service, '_log_template_approval') as mock_log:
                    # Execute
                    result = self.service.approve_template(
                        template_type,
                        template_content,
                        field_mappings,
                        user_email,
                        notes
                    )
        
        # Assert
        assert result['success'] is True, "Approval should succeed with notes"
        
        # Verify notes were passed to metadata update
        assert mock_update.called, "Should update metadata"
        call_args = mock_update.call_args[0]
        assert call_args[4] == notes, "Should pass notes to metadata update"
    
    @patch('google_drive_service.GoogleDriveService')
    def test_approve_template_empty_field_mappings(self, mock_drive_service):
        """Test approval with empty field mappings"""
        # Setup
        template_type = 'str_invoice_nl'
        template_content = """
        <html>
            <body>
                <h1>Invoice {{ invoice_number }}</h1>
                <p>Guest: {{ guest_name }}</p>
                <p>Check-in: {{ checkin_date }}</p>
                <p>Check-out: {{ checkout_date }}</p>
                <p>Amount: {{ amount_gross }}</p>
                <p>Company: {{ company_name }}</p>
            </body>
        </html>
        """
        field_mappings = {}  # Empty mappings
        user_email = 'admin@example.com'
        notes = ''
        
        # Mock Google Drive upload
        mock_drive_instance = Mock()
        mock_drive_instance.service.files().create().execute.return_value = {'id': 'file222'}
        mock_drive_service.return_value = mock_drive_instance
        
        # Mock template service
        with patch.object(self.service.template_service, 'get_template_metadata', return_value=None):
            # Mock internal methods
            with patch.object(self.service, '_update_template_metadata') as mock_update:
                with patch.object(self.service, '_log_template_approval') as mock_log:
                    # Execute
                    result = self.service.approve_template(
                        template_type,
                        template_content,
                        field_mappings,
                        user_email,
                        notes
                    )
        
        # Assert
        assert result['success'] is True, "Approval should succeed with empty field mappings"
        assert result['file_id'] == 'file222', "Should return correct file_id"


class TestTemplateMetadataUpdate:
    """Test template metadata database operations"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()
        self.administration = 'TestAdmin'
        self.service = TemplatePreviewService(self.mock_db, self.administration)
    
    def test_update_template_metadata_new_template(self):
        """Test metadata update for new template"""
        # Setup
        template_type = 'str_invoice_nl'
        file_id = 'file123'
        field_mappings = {'field1': 'value1'}
        user_email = 'admin@example.com'
        notes = 'Initial version'
        previous_file_id = None
        version = 1
        
        # Mock database - no existing template
        self.mock_db.execute_query = Mock(side_effect=[
            [],  # No existing template
            None  # Insert successful
        ])
        
        # Execute
        self.service._update_template_metadata(
            template_type,
            file_id,
            field_mappings,
            user_email,
            notes,
            previous_file_id,
            version
        )
        
        # Assert
        assert self.mock_db.execute_query.call_count == 2, "Should check and insert"
        
        # Verify INSERT query was used
        insert_call = self.mock_db.execute_query.call_args_list[1]
        query = insert_call[0][0]
        assert 'INSERT INTO' in query, "Should use INSERT for new template"
        assert 'tenant_template_config' in query, "Should insert into correct table"
    
    def test_update_template_metadata_existing_template(self):
        """Test metadata update for existing template"""
        # Setup
        template_type = 'btw_aangifte'
        file_id = 'file456'
        field_mappings = {'field2': 'value2'}
        user_email = 'admin@example.com'
        notes = 'Updated version'
        previous_file_id = 'old_file123'
        version = 2
        
        # Mock database - existing template found
        self.mock_db.execute_query = Mock(side_effect=[
            [{'id': 1}],  # Existing template
            None  # Update successful
        ])
        
        # Execute
        self.service._update_template_metadata(
            template_type,
            file_id,
            field_mappings,
            user_email,
            notes,
            previous_file_id,
            version
        )
        
        # Assert
        assert self.mock_db.execute_query.call_count == 2, "Should check and update"
        
        # Verify UPDATE query was used
        update_call = self.mock_db.execute_query.call_args_list[1]
        query = update_call[0][0]
        assert 'UPDATE' in query, "Should use UPDATE for existing template"
        assert 'tenant_template_config' in query, "Should update correct table"
    
    def test_update_template_metadata_database_error(self):
        """Test metadata update handles database errors"""
        # Setup
        template_type = 'aangifte_ib'
        file_id = 'file789'
        field_mappings = {}
        user_email = 'admin@example.com'
        notes = ''
        previous_file_id = None
        version = 1
        
        # Mock database to raise exception
        self.mock_db.execute_query = Mock(side_effect=Exception("Database error"))
        
        # Execute and assert exception is raised
        with pytest.raises(Exception) as exc_info:
            self.service._update_template_metadata(
                template_type,
                file_id,
                field_mappings,
                user_email,
                notes,
                previous_file_id,
                version
            )
        
        assert "Failed to update template metadata" in str(exc_info.value), \
            "Should raise exception with descriptive message"


class TestGoogleDriveIntegration:
    """Test Google Drive upload functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()
        self.administration = 'TestAdmin'
        self.service = TemplatePreviewService(self.mock_db, self.administration)
    
    @patch('google_drive_service.GoogleDriveService')
    @patch('googleapiclient.http.MediaIoBaseUpload')
    def test_save_template_to_drive_success(self, mock_media_upload, mock_drive_service):
        """Test successful template upload to Google Drive"""
        # Setup
        template_type = 'str_invoice_nl'
        template_content = '<html><body>Test</body></html>'
        version = 1
        
        # Mock Google Drive service
        mock_drive_instance = Mock()
        mock_drive_instance.service.files().create().execute.return_value = {'id': 'file123'}
        mock_drive_service.return_value = mock_drive_instance
        
        # Execute
        file_id = self.service._save_template_to_drive(
            template_type,
            template_content,
            version
        )
        
        # Assert
        assert file_id == 'file123', "Should return correct file_id"
        assert mock_drive_service.called, "Should initialize Google Drive service"
        assert mock_drive_instance.service.files().create().execute.called, \
            "Should call Google Drive API"
    
    @patch('google_drive_service.GoogleDriveService')
    def test_save_template_to_drive_error(self, mock_drive_service):
        """Test handling of Google Drive upload errors"""
        # Setup
        template_type = 'btw_aangifte'
        template_content = '<html><body>Test</body></html>'
        version = 1
        
        # Mock Google Drive to raise exception
        mock_drive_service.side_effect = Exception("Google Drive API error")
        
        # Execute and assert exception is raised
        with pytest.raises(Exception) as exc_info:
            self.service._save_template_to_drive(
                template_type,
                template_content,
                version
            )
        
        assert "Failed to save template to Google Drive" in str(exc_info.value), \
            "Should raise exception with descriptive message"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
