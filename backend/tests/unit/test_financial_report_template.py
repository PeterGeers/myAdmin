"""
Unit tests for Financial Report Template

Tests the financial report XML template and field mappings to ensure
they work correctly with the TemplateService.

NOTE: These tests are currently skipped as the financial report template
feature is not yet implemented. Remove the skip decorator when the
template files are created.
"""

import pytest
import json
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.template_service import TemplateService
from database import DatabaseManager


@pytest.mark.skip(reason="Financial report template files not yet implemented")
class TestFinancialReportTemplate:
    """Test suite for financial report template"""
    
    @pytest.fixture
    def template_service(self):
        """Create TemplateService instance for testing"""
        db = DatabaseManager(test_mode=True)
        return TemplateService(db)
    
    @pytest.fixture
    def template_xml(self):
        """Load financial report template XML"""
        template_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            '..',
            'templates',
            'xml',
            'financial_report_template.xml'
        )
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    @pytest.fixture
    def field_mappings(self):
        """Load financial report field mappings"""
        mappings_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            '..',
            'templates',
            'xml',
            'financial_report_field_mappings.json'
        )
        with open(mappings_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @pytest.fixture
    def sample_data(self):
        """Generate sample financial data for testing"""
        return {
            "metadata": {
                "title": "Test Financial Report",
                "administration": "TestAdmin",
                "period": {
                    "start_date": "2026-01-01",
                    "end_date": "2026-03-31"
                },
                "generated_date": "2026-01-30",
                "generated_by": "test@example.com"
            },
            "summary": {
                "total_revenue": 150000.00,
                "total_expenses": 95000.00,
                "net_income": 55000.00,
                "total_assets": 250000.00,
                "total_liabilities": 75000.00,
                "equity": 175000.00
            },
            "profit_loss": {
                "revenue": {
                    "categories": [
                        {"account": "4000", "account_name": "Sales", "amount": 150000.00}
                    ],
                    "total": 150000.00
                },
                "expenses": {
                    "operating": {
                        "categories": [
                            {"account": "6000", "account_name": "Salaries", "amount": 60000.00}
                        ],
                        "total": 60000.00
                    },
                    "other": {
                        "categories": [
                            {"account": "7000", "account_name": "Interest", "amount": 5000.00}
                        ],
                        "total": 5000.00
                    },
                    "total": 65000.00
                },
                "vat": {
                    "payable": 15000.00,
                    "receivable": 10000.00,
                    "net": 5000.00
                }
            },
            "balance_sheet": {
                "assets": {
                    "current": {
                        "bank_accounts": [
                            {"account": "1000", "account_name": "Bank", "balance": 50000.00}
                        ],
                        "total": 50000.00
                    },
                    "fixed": {
                        "categories": [
                            {"account": "0100", "account_name": "Equipment", "amount": 200000.00}
                        ],
                        "total": 200000.00
                    },
                    "total": 250000.00
                },
                "liabilities": {
                    "current": {
                        "categories": [
                            {"account": "2000", "account_name": "Payables", "amount": 25000.00}
                        ],
                        "total": 25000.00
                    },
                    "long_term": {
                        "categories": [
                            {"account": "3000", "account_name": "Loan", "amount": 50000.00}
                        ],
                        "total": 50000.00
                    },
                    "total": 75000.00
                },
                "equity": {
                    "categories": [
                        {"account": "9000", "account_name": "Equity", "amount": 175000.00}
                    ],
                    "total": 175000.00
                }
            },
            "account_details": {
                "accounts": [
                    {
                        "account": "1000",
                        "account_name": "Bank",
                        "parent": "Assets",
                        "debit": 100000.00,
                        "credit": 50000.00,
                        "balance": 50000.00
                    }
                ]
            },
            "transactions": {
                "list": [
                    {
                        "date": "2026-01-15",
                        "description": "Test transaction",
                        "account": "1000",
                        "account_name": "Bank",
                        "debit": 5000.00,
                        "credit": 0.00,
                        "reference": "TEST-001"
                    }
                ],
                "count": 1
            }
        }
    
    def test_template_file_exists(self):
        """Test that template XML file exists"""
        template_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            '..',
            'templates',
            'xml',
            'financial_report_template.xml'
        )
        assert os.path.exists(template_path), "Template XML file not found"
    
    def test_field_mappings_file_exists(self):
        """Test that field mappings JSON file exists"""
        mappings_path = os.path.join(
            os.path.dirname(__file__),
            '..',
            '..',
            'templates',
            'xml',
            'financial_report_field_mappings.json'
        )
        assert os.path.exists(mappings_path), "Field mappings JSON file not found"
    
    def test_field_mappings_structure(self, field_mappings):
        """Test that field mappings have correct structure"""
        assert 'template_type' in field_mappings
        assert field_mappings['template_type'] == 'financial_report'
        assert 'fields' in field_mappings
        assert 'formatting' in field_mappings
        assert 'account_ranges' in field_mappings
    
    def test_required_fields_present(self, field_mappings):
        """Test that all required fields are defined in mappings"""
        required_fields = [
            'report_title', 'administration', 'period_start', 'period_end',
            'total_revenue', 'total_expenses', 'net_income',
            'total_assets', 'total_liabilities', 'equity'
        ]
        
        for field in required_fields:
            assert field in field_mappings['fields'], f"Required field '{field}' not found"
    
    def test_apply_field_mappings(self, template_service, template_xml, field_mappings, sample_data):
        """Test applying field mappings to template"""
        result = template_service.apply_field_mappings(
            template_xml=template_xml,
            data=sample_data,
            mappings=field_mappings
        )
        
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_metadata_fields_mapped(self, template_service, template_xml, field_mappings, sample_data):
        """Test that metadata fields are correctly mapped"""
        result = template_service.apply_field_mappings(
            template_xml=template_xml,
            data=sample_data,
            mappings=field_mappings
        )
        
        assert "Test Financial Report" in result
        assert "TestAdmin" in result
        assert "2026-01-01" in result or "01-01-2026" in result
    
    def test_summary_fields_mapped(self, template_service, template_xml, field_mappings, sample_data):
        """Test that summary fields are correctly mapped"""
        result = template_service.apply_field_mappings(
            template_xml=template_xml,
            data=sample_data,
            mappings=field_mappings
        )
        
        # Check for currency formatted values
        assert "150" in result  # Revenue (in thousands)
        assert "95" in result   # Expenses (in thousands)
        assert "55" in result   # Net income (in thousands)
    
    def test_currency_formatting(self, template_service, field_mappings):
        """Test currency formatting"""
        field_config = field_mappings['fields']['total_revenue']
        formatting = field_mappings['formatting']
        
        formatted = template_service._format_currency(150000.00, formatting)
        
        assert "€" in formatted or "EUR" in formatted
        assert "150" in formatted
    
    def test_date_formatting(self, template_service, field_mappings):
        """Test date formatting"""
        field_config = field_mappings['fields']['period_start']
        formatting = field_mappings['formatting']
        
        formatted = template_service._format_date("2026-01-30", formatting)
        
        assert "30" in formatted
        assert "01" in formatted
        assert "2026" in formatted
    
    def test_generate_xml_output(self, template_service, template_xml, field_mappings, sample_data):
        """Test generating XML output"""
        processed = template_service.apply_field_mappings(
            template_xml=template_xml,
            data=sample_data,
            mappings=field_mappings
        )
        
        output = template_service.generate_output(
            template=processed,
            data=sample_data,
            output_format='xml'
        )
        
        assert output is not None
        assert isinstance(output, str)
        assert "<?xml" in output or "<FinancialReport>" in output
    
    def test_generate_html_output(self, template_service, template_xml, field_mappings, sample_data):
        """Test generating HTML output"""
        processed = template_service.apply_field_mappings(
            template_xml=template_xml,
            data=sample_data,
            mappings=field_mappings
        )
        
        output = template_service.generate_output(
            template=processed,
            data=sample_data,
            output_format='html'
        )
        
        assert output is not None
        assert isinstance(output, str)
    
    def test_account_ranges_defined(self, field_mappings):
        """Test that account ranges are properly defined"""
        account_ranges = field_mappings['account_ranges']
        
        required_ranges = [
            'revenue', 'operating_expenses', 'other_expenses',
            'vat', 'bank_cash', 'current_assets', 'fixed_assets',
            'current_liabilities', 'long_term_liabilities', 'equity'
        ]
        
        for range_name in required_ranges:
            assert range_name in account_ranges, f"Account range '{range_name}' not defined"
    
    def test_conditionals_defined(self, field_mappings):
        """Test that conditionals are defined"""
        assert 'conditionals' in field_mappings
        assert isinstance(field_mappings['conditionals'], list)
        assert len(field_mappings['conditionals']) > 0
    
    def test_missing_field_uses_default(self, template_service, template_xml, field_mappings):
        """Test that missing fields use default values"""
        # Data with missing fields
        minimal_data = {
            "metadata": {
                "title": "Test"
            },
            "summary": {}
        }
        
        result = template_service.apply_field_mappings(
            template_xml=template_xml,
            data=minimal_data,
            mappings=field_mappings
        )
        
        # Should not raise exception and should use defaults
        assert result is not None
    
    def test_field_path_navigation(self, template_service, field_mappings):
        """Test nested field path navigation"""
        data = {
            "metadata": {
                "period": {
                    "start_date": "2026-01-01"
                }
            }
        }
        
        field_config = field_mappings['fields']['period_start']
        value = template_service._get_field_value(data, field_config)
        
        assert value == "2026-01-01"
    
    def test_transform_abs(self, template_service):
        """Test absolute value transformation"""
        result = template_service._apply_transform(-100.50, 'abs')
        assert result == 100.50
    
    def test_transform_round(self, template_service):
        """Test rounding transformation"""
        result = template_service._apply_transform(100.567, 'round')
        assert result == 100.57
    
    def test_transform_uppercase(self, template_service):
        """Test uppercase transformation"""
        result = template_service._apply_transform("test", 'uppercase')
        assert result == "TEST"
    
    def test_evaluate_condition_eq(self, template_service):
        """Test equality condition"""
        result = template_service._evaluate_condition(100, 'eq', 100)
        assert result is True
        
        result = template_service._evaluate_condition(100, 'eq', 200)
        assert result is False
    
    def test_evaluate_condition_gt(self, template_service):
        """Test greater than condition"""
        result = template_service._evaluate_condition(200, 'gt', 100)
        assert result is True
        
        result = template_service._evaluate_condition(50, 'gt', 100)
        assert result is False
    
    def test_evaluate_condition_lt(self, template_service):
        """Test less than condition"""
        result = template_service._evaluate_condition(50, 'lt', 100)
        assert result is True
        
        result = template_service._evaluate_condition(200, 'lt', 100)
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
