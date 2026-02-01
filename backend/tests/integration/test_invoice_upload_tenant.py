"""
Test invoice upload with multi-tenant support

Verifies that invoices are uploaded with the correct tenant/administration
based on the X-Tenant header in the request.
"""

import pytest
import json
import base64
from flask import Flask
from transaction_logic import TransactionLogic


class TestInvoiceUploadTenant:
    """Test invoice upload respects tenant context"""
    
    @pytest.fixture
    def transaction_logic(self):
        """Create transaction logic for testing"""
        return TransactionLogic(test_mode=True)
    
    def test_get_last_transactions_with_tenant(self, transaction_logic):
        """Test get_last_transactions filters by tenant"""
        # This test verifies the method accepts the administration parameter
        # In a real scenario, you would have test data for different tenants
        
        # Test with GoodwinSolutions
        transactions_goodwin = transaction_logic.get_last_transactions(
            "Gamma", 
            administration="GoodwinSolutions"
        )
        
        # Verify all transactions have correct administration
        for trans in transactions_goodwin:
            assert trans['Administration'] == 'GoodwinSolutions'
        
        print(f"✅ get_last_transactions correctly filters by tenant")
    
    def test_prepare_new_transactions_uses_provided_administration(self, transaction_logic):
        """Test prepare_new_transactions uses administration from new_data"""
        # Create template transactions
        template_transactions = [
            {
                'ID': 1,
                'TransactionNumber': 'TestVendor',
                'TransactionDate': '2024-01-01',
                'TransactionDescription': 'Test',
                'TransactionAmount': 100.00,
                'Debet': '6000',
                'Credit': '1600',
                'ReferenceNumber': 'TestVendor',
                'Ref1': None,
                'Ref2': None,
                'Ref3': None,
                'Ref4': None,
                'Administration': 'GoodwinSolutions'  # Template has GoodwinSolutions
            }
        ]
        
        # Create new_data with PeterPrive as administration
        new_data = {
            'folder_name': 'TestVendor',
            'description': 'Test invoice',
            'amount': 150.00,
            'drive_url': 'https://drive.google.com/test',
            'filename': 'test.pdf',
            'vendor_data': None,
            'administration': 'PeterPrive'  # Override with PeterPrive
        }
        
        # Prepare new transactions
        new_transactions = transaction_logic.prepare_new_transactions(
            template_transactions, 
            new_data
        )
        
        # Verify all new transactions have PeterPrive administration
        for trans in new_transactions:
            assert trans['Administration'] == 'PeterPrive', \
                f"Expected 'PeterPrive' but got '{trans['Administration']}'"
        
        print(f"✅ prepare_new_transactions correctly uses provided administration")
    
    def test_prepare_new_transactions_fallback_to_template(self, transaction_logic):
        """Test prepare_new_transactions falls back to template administration if not provided"""
        # Create template transactions
        template_transactions = [
            {
                'ID': 1,
                'TransactionNumber': 'TestVendor',
                'TransactionDate': '2024-01-01',
                'TransactionDescription': 'Test',
                'TransactionAmount': 100.00,
                'Debet': '6000',
                'Credit': '1600',
                'ReferenceNumber': 'TestVendor',
                'Ref1': None,
                'Ref2': None,
                'Ref3': None,
                'Ref4': None,
                'Administration': 'InterimManagement'  # Template has InterimManagement
            }
        ]
        
        # Create new_data WITHOUT administration
        new_data = {
            'folder_name': 'TestVendor',
            'description': 'Test invoice',
            'amount': 150.00,
            'drive_url': 'https://drive.google.com/test',
            'filename': 'test.pdf',
            'vendor_data': None
            # No 'administration' key
        }
        
        # Prepare new transactions
        new_transactions = transaction_logic.prepare_new_transactions(
            template_transactions, 
            new_data
        )
        
        # Verify all new transactions have InterimManagement administration from template
        for trans in new_transactions:
            assert trans['Administration'] == 'InterimManagement', \
                f"Expected 'InterimManagement' but got '{trans['Administration']}'"
        
        print(f"✅ prepare_new_transactions correctly falls back to template administration")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
