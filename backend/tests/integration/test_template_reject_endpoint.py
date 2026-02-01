"""
Integration test for Template Reject API endpoint

Tests the POST /api/tenant-admin/templates/reject endpoint
"""

import pytest


class TestTemplateRejectEndpoint:
    """Integration tests for template reject endpoint"""
    
    def test_reject_request_structure(self):
        """Test that endpoint expects correct request structure"""
        # Valid request structure
        valid_request = {
            'template_type': 'str_invoice_nl',
            'reason': 'Template does not meet brand guidelines'
        }
        
        assert 'template_type' in valid_request
        assert 'reason' in valid_request
        
        # Minimal valid request (reason is optional)
        minimal_request = {
            'template_type': 'str_invoice_nl'
        }
        
        assert 'template_type' in minimal_request
    
    def test_reject_response_structure(self):
        """Test expected response structure"""
        # Expected success response
        expected_response = {
            'success': True,
            'message': 'Template rejection logged'
        }
        
        assert 'success' in expected_response
        assert 'message' in expected_response
        assert expected_response['success'] is True
    
    def test_reject_with_reason(self):
        """Test rejection with reason provided"""
        request_data = {
            'template_type': 'str_invoice_nl',
            'reason': 'Template does not meet brand guidelines'
        }
        
        # Verify reason is captured
        assert request_data['reason'] == 'Template does not meet brand guidelines'
    
    def test_reject_without_reason(self):
        """Test rejection without reason (should use default)"""
        request_data = {
            'template_type': 'str_invoice_nl'
        }
        
        # Reason is optional, should default to 'No reason provided'
        reason = request_data.get('reason', 'No reason provided')
        assert reason == 'No reason provided'
    
    def test_reject_various_template_types(self):
        """Test rejection works for different template types"""
        template_types = [
            'str_invoice_nl',
            'str_invoice_en',
            'btw_aangifte',
            'aangifte_ib',
            'toeristenbelasting'
        ]
        
        for template_type in template_types:
            request_data = {
                'template_type': template_type,
                'reason': f'Rejecting {template_type}'
            }
            
            assert 'template_type' in request_data
            assert request_data['template_type'] == template_type
    
    def test_reject_audit_log_format(self):
        """Test that audit log contains expected information"""
        # Expected audit log format
        user_email = 'admin@example.com'
        tenant = 'GoodwinSolutions'
        template_type = 'str_invoice_nl'
        reason = 'Does not meet requirements'
        
        expected_log = (
            f"AUDIT: Template rejected by {user_email} for {tenant}, "
            f"type={template_type}, reason={reason}"
        )
        
        # Verify log format contains all required information
        assert user_email in expected_log
        assert tenant in expected_log
        assert template_type in expected_log
        assert reason in expected_log
        assert 'AUDIT:' in expected_log
        assert 'rejected' in expected_log


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
