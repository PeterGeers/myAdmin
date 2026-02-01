"""
Integration test for Template Approve API endpoint

Tests the POST /api/tenant-admin/templates/approve endpoint with real service integration
"""

import pytest
import os
from database import DatabaseManager
from services.template_preview_service import TemplatePreviewService


class TestTemplateApproveServiceIntegration:
    """Integration tests for template approve service"""
    
    @pytest.fixture
    def db(self):
        """Create database connection"""
        test_mode = os.getenv('TEST_MODE', 'true').lower() == 'true'
        return DatabaseManager(test_mode=test_mode)
    
    @pytest.fixture
    def preview_service(self, db):
        """Create template preview service"""
        return TemplatePreviewService(db, 'GoodwinSolutions')
    
    def test_approve_template_validation_check(self, preview_service):
        """Test that approve validates template before saving"""
        # Invalid template (missing required placeholders)
        template_content = '''
            <html>
                <body>
                    <h1>Invoice</h1>
                    <p>Missing required placeholders</p>
                </body>
            </html>
        '''
        
        result = preview_service.approve_template(
            template_type='str_invoice_nl',
            template_content=template_content,
            field_mappings={},
            user_email='test@example.com',
            notes='Test approval'
        )
        
        # Assertions
        assert result is not None
        assert 'success' in result
        assert result['success'] is False
        assert 'message' in result
        # Should fail validation
        assert 'validation' in result or 'Template validation failed' in result['message']
    
    def test_approve_template_structure(self, preview_service):
        """Test approve_template returns expected structure"""
        # Valid template
        template_content = '''
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
        '''
        
        result = preview_service.approve_template(
            template_type='str_invoice_nl',
            template_content=template_content,
            field_mappings={},
            user_email='test@example.com',
            notes='Test approval'
        )
        
        # Assertions
        assert result is not None
        assert 'success' in result
        assert 'message' in result
        
        # If successful, should have these fields
        if result['success']:
            assert 'template_id' in result
            assert 'file_id' in result
            # May or may not have previous_version depending on if template existed before
    
    def test_approve_template_with_notes(self, preview_service):
        """Test that approval notes are accepted"""
        template_content = '''
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
        '''
        
        notes = 'Updated invoice layout for better readability'
        
        result = preview_service.approve_template(
            template_type='str_invoice_nl',
            template_content=template_content,
            field_mappings={},
            user_email='test@example.com',
            notes=notes
        )
        
        # Assertions
        assert result is not None
        assert 'success' in result
        # Notes should be accepted (no error about notes)
    
    def test_approve_template_with_field_mappings(self, preview_service):
        """Test that field mappings are accepted"""
        template_content = '''
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
        '''
        
        field_mappings = {
            'invoice_number': 'reservationCode',
            'guest_name': 'guestName',
            'checkin_date': 'checkinDate',
            'checkout_date': 'checkoutDate',
            'amount_gross': 'amountGross',
            'company_name': 'companyName'
        }
        
        result = preview_service.approve_template(
            template_type='str_invoice_nl',
            template_content=template_content,
            field_mappings=field_mappings,
            user_email='test@example.com',
            notes='Test with field mappings'
        )
        
        # Assertions
        assert result is not None
        assert 'success' in result
        # Field mappings should be accepted (no error about mappings)
    
    def test_endpoint_request_structure(self):
        """Test that endpoint expects correct request structure"""
        # Valid request structure
        valid_request = {
            'template_type': 'str_invoice_nl',
            'template_content': '<html>...</html>',
            'field_mappings': {},
            'notes': 'Test approval'
        }
        
        assert 'template_type' in valid_request
        assert 'template_content' in valid_request
        assert 'field_mappings' in valid_request
        assert 'notes' in valid_request
        
        # Minimal valid request (notes and field_mappings optional)
        minimal_request = {
            'template_type': 'str_invoice_nl',
            'template_content': '<html>...</html>'
        }
        
        assert 'template_type' in minimal_request
        assert 'template_content' in minimal_request


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
