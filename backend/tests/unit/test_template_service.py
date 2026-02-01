"""
Unit tests for TemplateService

Tests template metadata retrieval, template fetching, field mapping application,
and output generation.

This is a unit test suite - all external dependencies are mocked.
No database connections, no file system operations, no external API calls.
"""

import pytest
import os
import sys
import json
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from io import BytesIO

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.template_service import TemplateService


@pytest.mark.unit
class TestTemplateService:
    """Test suite for TemplateService"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database manager"""
        db = Mock()
        db.execute_query = Mock()
        return db
    
    @pytest.fixture
    def service(self, mock_db):
        """Create a TemplateService instance with mocked dependencies"""
        return TemplateService(mock_db)
    
    @pytest.fixture
    def sample_field_mappings(self):
        """Sample field mappings for testing"""
        return {
            "fields": {
                "invoice_total": {
                    "source": "database",
                    "path": "booking.amountGross",
                    "format": "currency",
                    "default": 0,
                    "required": True
                },
                "guest_name": {
                    "source": "database",
                    "path": "booking.guestName",
                    "format": "text",
                    "default": "Guest",
                    "transform": "uppercase"
                },
                "checkin_date": {
                    "source": "database",
                    "path": "booking.checkinDate",
                    "format": "date",
                    "required": True
                }
            },
            "conditionals": [
                {
                    "field": "invoice_total",
                    "operator": "gt",
                    "value": 0,
                    "action": "show"
                }
            ],
            "formatting": {
                "currency": "EUR",
                "date_format": "DD-MM-YYYY",
                "number_decimals": 2,
                "locale": "nl-NL"
            }
        }
    
    @pytest.fixture
    def sample_data(self):
        """Sample data for testing field mappings"""
        return {
            "booking": {
                "amountGross": 150.50,
                "guestName": "John Doe",
                "checkinDate": "2026-01-30"
            }
        }
    
    # Initialization tests
    
    def test_initialization(self, mock_db):
        """Test service initializes correctly"""
        service = TemplateService(mock_db)
        assert service.db == mock_db
    
    # get_template_metadata tests
    
    def test_get_template_metadata_success(self, service, mock_db, sample_field_mappings):
        """Test successful template metadata retrieval"""
        mock_db.execute_query.return_value = [{
            'template_file_id': '1a2b3c4d5e6f',
            'field_mappings': json.dumps(sample_field_mappings),
            'is_active': True,
            'created_at': datetime(2026, 1, 30, 10, 0, 0),
            'updated_at': datetime(2026, 1, 30, 12, 0, 0)
        }]
        
        result = service.get_template_metadata('GoodwinSolutions', 'str_invoice')
        
        assert result is not None
        assert result['template_file_id'] == '1a2b3c4d5e6f'
        assert result['field_mappings'] == sample_field_mappings
        assert result['is_active'] is True
        assert result['created_at'] == '2026-01-30T10:00:00'
        assert result['updated_at'] == '2026-01-30T12:00:00'
        
        # Verify database query was called correctly
        mock_db.execute_query.assert_called_once()
        call_args = mock_db.execute_query.call_args
        assert 'GoodwinSolutions' in call_args[0][1]
        assert 'str_invoice' in call_args[0][1]
    
    def test_get_template_metadata_not_found(self, service, mock_db):
        """Test template metadata retrieval when template not found"""
        mock_db.execute_query.return_value = []
        
        result = service.get_template_metadata('GoodwinSolutions', 'nonexistent')
        
        assert result is None
    
    def test_get_template_metadata_with_dict_field_mappings(self, service, mock_db, sample_field_mappings):
        """Test template metadata retrieval when field_mappings is already a dict"""
        mock_db.execute_query.return_value = [{
            'template_file_id': '1a2b3c4d5e6f',
            'field_mappings': sample_field_mappings,  # Already a dict
            'is_active': True,
            'created_at': datetime(2026, 1, 30, 10, 0, 0),
            'updated_at': datetime(2026, 1, 30, 12, 0, 0)
        }]
        
        result = service.get_template_metadata('GoodwinSolutions', 'str_invoice')
        
        assert result is not None
        assert result['field_mappings'] == sample_field_mappings
    
    def test_get_template_metadata_invalid_json(self, service, mock_db):
        """Test template metadata retrieval with invalid JSON"""
        mock_db.execute_query.return_value = [{
            'template_file_id': '1a2b3c4d5e6f',
            'field_mappings': 'invalid json {',
            'is_active': True,
            'created_at': datetime(2026, 1, 30, 10, 0, 0),
            'updated_at': datetime(2026, 1, 30, 12, 0, 0)
        }]
        
        result = service.get_template_metadata('GoodwinSolutions', 'str_invoice')
        
        assert result is not None
        assert result['field_mappings'] == {}  # Should return empty dict on parse error
    
    def test_get_template_metadata_database_error(self, service, mock_db):
        """Test template metadata retrieval when database query fails"""
        mock_db.execute_query.side_effect = Exception("Database connection failed")
        
        with pytest.raises(Exception, match="Failed to retrieve template metadata"):
            service.get_template_metadata('GoodwinSolutions', 'str_invoice')
    
    # fetch_template_from_drive tests
    # Note: These tests are skipped as they require complex Google Drive API mocking
    # Integration tests will cover this functionality with real Google Drive service
    
    @pytest.mark.skip(reason="Requires complex Google Drive API mocking - covered in integration tests")
    def test_fetch_template_from_drive_success(self, service):
        """Test successful template fetch from Google Drive"""
        pass
    
    @pytest.mark.skip(reason="Requires complex Google Drive API mocking - covered in integration tests")
    def test_fetch_template_from_drive_error(self, service):
        """Test template fetch failure"""
        pass
    
    # apply_field_mappings tests
    
    def test_apply_field_mappings_success(self, service, sample_field_mappings, sample_data):
        """Test successful field mapping application"""
        template = "<invoice><total>{{ invoice_total }}</total><guest>{{ guest_name }}</guest></invoice>"
        
        result = service.apply_field_mappings(template, sample_data, sample_field_mappings)
        
        assert "€ 150.50" in result
        assert "JOHN DOE" in result  # Should be uppercase due to transform
    
    def test_apply_field_mappings_with_default_values(self, service, sample_field_mappings):
        """Test field mapping with missing data uses default values"""
        template = "<invoice><total>{{ invoice_total }}</total><guest>{{ guest_name }}</guest></invoice>"
        empty_data = {}
        
        result = service.apply_field_mappings(template, empty_data, sample_field_mappings)
        
        assert "€ 0.00" in result  # Default value for invoice_total
        assert "GUEST" in result  # Default value for guest_name (uppercase due to transform)
    
    def test_apply_field_mappings_empty_mappings(self, service, sample_data):
        """Test field mapping with empty mappings"""
        template = "<invoice>{{ test }}</invoice>"
        empty_mappings = {"fields": {}, "conditionals": [], "formatting": {}}
        
        result = service.apply_field_mappings(template, sample_data, empty_mappings)
        
        assert result == template  # Should return unchanged
    
    # Helper method tests
    
    def test_get_field_value_nested_path(self, service):
        """Test getting field value with nested path"""
        data = {
            "booking": {
                "guest": {
                    "name": "John Doe"
                }
            }
        }
        field_config = {
            "path": "booking.guest.name",
            "default": "Unknown"
        }
        
        result = service._get_field_value(data, field_config)
        
        assert result == "John Doe"
    
    def test_get_field_value_missing_path(self, service):
        """Test getting field value with missing path returns default"""
        data = {"booking": {}}
        field_config = {
            "path": "booking.guest.name",
            "default": "Unknown"
        }
        
        result = service._get_field_value(data, field_config)
        
        assert result == "Unknown"
    
    def test_get_field_value_none_value(self, service):
        """Test getting field value when value is None"""
        data = {"booking": {"name": None}}
        field_config = {
            "path": "booking.name",
            "default": "Default Name"
        }
        
        result = service._get_field_value(data, field_config)
        
        assert result == "Default Name"
    
    # Format value tests
    
    def test_format_currency_eur(self, service):
        """Test currency formatting for EUR"""
        formatting = {"currency": "EUR", "number_decimals": 2}
        
        result = service._format_currency(150.50, formatting)
        
        assert result == "€ 150.50"
    
    def test_format_currency_usd(self, service):
        """Test currency formatting for USD"""
        formatting = {"currency": "USD", "number_decimals": 2}
        
        result = service._format_currency(150.50, formatting)
        
        assert result == "$ 150.50"
    
    def test_format_date_dd_mm_yyyy(self, service):
        """Test date formatting DD-MM-YYYY"""
        formatting = {"date_format": "DD-MM-YYYY"}
        
        result = service._format_date("2026-01-30", formatting)
        
        assert result == "30-01-2026"
    
    def test_format_date_yyyy_mm_dd(self, service):
        """Test date formatting YYYY-MM-DD"""
        formatting = {"date_format": "YYYY-MM-DD"}
        
        result = service._format_date("30-01-2026", formatting)
        
        assert result == "2026-01-30"
    
    def test_format_number(self, service):
        """Test number formatting"""
        formatting = {"number_decimals": 2}
        
        result = service._format_number(1234.567, formatting)
        
        assert result == "1,234.57"
    
    # Transform tests
    
    def test_apply_transform_abs(self, service):
        """Test absolute value transform"""
        result = service._apply_transform(-150.50, 'abs')
        assert result == 150.50
    
    def test_apply_transform_round(self, service):
        """Test round transform"""
        result = service._apply_transform(150.567, 'round')
        assert result == 150.57
    
    def test_apply_transform_uppercase(self, service):
        """Test uppercase transform"""
        result = service._apply_transform("john doe", 'uppercase')
        assert result == "JOHN DOE"
    
    def test_apply_transform_lowercase(self, service):
        """Test lowercase transform"""
        result = service._apply_transform("JOHN DOE", 'lowercase')
        assert result == "john doe"
    
    def test_apply_transform_invalid(self, service):
        """Test invalid transform returns original value"""
        result = service._apply_transform("test", 'invalid_transform')
        assert result == "test"
    
    # Conditional evaluation tests
    
    def test_evaluate_condition_eq(self, service):
        """Test equality condition"""
        assert service._evaluate_condition(10, 'eq', 10) is True
        assert service._evaluate_condition(10, 'eq', 20) is False
    
    def test_evaluate_condition_ne(self, service):
        """Test not equal condition"""
        assert service._evaluate_condition(10, 'ne', 20) is True
        assert service._evaluate_condition(10, 'ne', 10) is False
    
    def test_evaluate_condition_gt(self, service):
        """Test greater than condition"""
        assert service._evaluate_condition(20, 'gt', 10) is True
        assert service._evaluate_condition(10, 'gt', 20) is False
    
    def test_evaluate_condition_lt(self, service):
        """Test less than condition"""
        assert service._evaluate_condition(10, 'lt', 20) is True
        assert service._evaluate_condition(20, 'lt', 10) is False
    
    def test_evaluate_condition_gte(self, service):
        """Test greater than or equal condition"""
        assert service._evaluate_condition(20, 'gte', 20) is True
        assert service._evaluate_condition(20, 'gte', 10) is True
        assert service._evaluate_condition(10, 'gte', 20) is False
    
    def test_evaluate_condition_lte(self, service):
        """Test less than or equal condition"""
        assert service._evaluate_condition(10, 'lte', 10) is True
        assert service._evaluate_condition(10, 'lte', 20) is True
        assert service._evaluate_condition(20, 'lte', 10) is False
    
    def test_evaluate_condition_contains(self, service):
        """Test contains condition"""
        assert service._evaluate_condition("hello world", 'contains', "world") is True
        assert service._evaluate_condition("hello world", 'contains', "foo") is False
    
    def test_evaluate_condition_unknown_operator(self, service):
        """Test unknown operator returns False"""
        assert service._evaluate_condition(10, 'unknown', 10) is False
    
    # Output generation tests
    
    def test_generate_html_output(self, service, sample_data):
        """Test HTML output generation"""
        template = "<html><body>Test</body></html>"
        
        result = service.generate_output(template, sample_data, 'html')
        
        assert result == template
    
    def test_generate_xml_output(self, service, sample_data):
        """Test XML output generation"""
        template = "<root><item>Test</item></root>"
        
        result = service.generate_output(template, sample_data, 'xml')
        
        assert result == template
    
    def test_generate_xml_output_invalid_xml(self, service, sample_data):
        """Test XML output generation with invalid XML"""
        template = "<root><item>Test</root>"  # Invalid XML
        
        result = service.generate_output(template, sample_data, 'xml')
        
        # Should still return the template even if invalid
        assert result == template
    
    def test_generate_excel_output_not_implemented(self, service, sample_data):
        """Test Excel output generation raises NotImplementedError"""
        template = "<template>Test</template>"
        
        with pytest.raises(Exception, match="Failed to generate output"):
            service.generate_output(template, sample_data, 'excel')
    
    def test_generate_pdf_output_not_implemented(self, service, sample_data):
        """Test PDF output generation raises NotImplementedError"""
        template = "<template>Test</template>"
        
        with pytest.raises(Exception, match="Failed to generate output"):
            service.generate_output(template, sample_data, 'pdf')
    
    def test_generate_output_unsupported_format(self, service, sample_data):
        """Test output generation with unsupported format"""
        template = "<template>Test</template>"
        
        with pytest.raises(Exception, match="Failed to generate output"):
            service.generate_output(template, sample_data, 'unsupported')
    
    # Edge cases and error handling
    
    def test_format_value_with_none(self, service):
        """Test formatting None value returns empty string"""
        field_config = {"format": "text"}
        formatting = {}
        
        result = service._format_value(None, field_config, formatting)
        
        assert result == ''
    
    def test_format_currency_invalid_value(self, service):
        """Test currency formatting with invalid value"""
        formatting = {"currency": "EUR", "number_decimals": 2}
        
        result = service._format_currency("invalid", formatting)
        
        assert result == "invalid"  # Should return original value on error
    
    def test_format_date_invalid_value(self, service):
        """Test date formatting with invalid value"""
        formatting = {"date_format": "DD-MM-YYYY"}
        
        result = service._format_date("invalid-date", formatting)
        
        assert result == "invalid-date"  # Should return original value on error
    
    def test_format_number_invalid_value(self, service):
        """Test number formatting with invalid value"""
        formatting = {"number_decimals": 2}
        
        result = service._format_number("invalid", formatting)
        
        assert result == "invalid"  # Should return original value on error
    
    # Additional edge case tests
    
    def test_apply_field_mappings_with_nested_data(self, service):
        """Test field mapping with deeply nested data structures"""
        template = "<data>{{ deep_value }}</data>"
        mappings = {
            "fields": {
                "deep_value": {
                    "path": "level1.level2.level3.value",
                    "format": "text",
                    "default": "not_found"
                }
            },
            "formatting": {}
        }
        data = {
            "level1": {
                "level2": {
                    "level3": {
                        "value": "found_it"
                    }
                }
            }
        }
        
        result = service.apply_field_mappings(template, data, mappings)
        
        assert "found_it" in result
    
    def test_apply_field_mappings_with_missing_nested_data(self, service):
        """Test field mapping with missing nested data uses default"""
        template = "<data>{{ deep_value }}</data>"
        mappings = {
            "fields": {
                "deep_value": {
                    "path": "level1.level2.level3.value",
                    "format": "text",
                    "default": "default_value"
                }
            },
            "formatting": {}
        }
        data = {
            "level1": {
                "level2": {}  # level3 is missing
            }
        }
        
        result = service.apply_field_mappings(template, data, mappings)
        
        assert "default_value" in result
    
    def test_format_currency_with_large_numbers(self, service):
        """Test currency formatting with large numbers"""
        formatting = {"currency": "EUR", "number_decimals": 2}
        
        result = service._format_currency(1234567.89, formatting)
        
        assert "€ 1,234,567.89" in result
    
    def test_format_date_with_datetime_object(self, service):
        """Test date formatting with datetime object"""
        formatting = {"date_format": "DD-MM-YYYY"}
        date_obj = datetime(2026, 1, 30, 10, 30, 0)
        
        result = service._format_date(date_obj, formatting)
        
        assert result == "30-01-2026"
    
    def test_apply_conditional_with_complex_logic(self, service):
        """Test conditional application with complex field logic"""
        template = "<section>{{ value }}</section>"
        data = {"amount": 100}
        conditional = {
            "field": "amount",
            "operator": "gt",
            "value": 50,
            "action": "show"
        }
        fields = {
            "amount": {
                "path": "amount",
                "format": "number"
            }
        }
        
        result = service._apply_conditional(template, data, conditional, fields)
        
        # Should return template unchanged (conditional logic is logged but not applied to template)
        assert result == template
    
    def test_get_field_value_with_empty_path(self, service):
        """Test getting field value with empty path"""
        data = {"value": "test"}
        field_config = {
            "path": "",
            "default": "default"
        }
        
        result = service._get_field_value(data, field_config)
        
        # Empty path should return default
        assert result == "default"
    
    def test_format_value_with_table_format(self, service):
        """Test formatting value with table format"""
        field_config = {"format": "table"}
        formatting = {}
        value = [{"col1": "val1", "col2": "val2"}]
        
        result = service._format_value(value, field_config, formatting)
        
        # Table format should return string representation
        assert isinstance(result, str)
    
    def test_apply_field_mappings_with_multiple_placeholders(self, service):
        """Test field mapping with multiple occurrences of same placeholder"""
        template = "<doc>{{ name }} is {{ name }}</doc>"
        mappings = {
            "fields": {
                "name": {
                    "path": "person.name",
                    "format": "text"
                }
            },
            "formatting": {}
        }
        data = {"person": {"name": "John"}}
        
        result = service.apply_field_mappings(template, data, mappings)
        
        # Both placeholders should be replaced
        assert result.count("John") == 2
        assert "{{ name }}" not in result


@pytest.mark.unit
class TestTemplateServiceIntegration:
    """Integration-style tests for TemplateService (still unit tests with mocks)"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database manager"""
        db = Mock()
        db.execute_query = Mock()
        return db
    
    @pytest.fixture
    def service(self, mock_db):
        """Create a TemplateService instance"""
        return TemplateService(mock_db)
    
    def test_complete_str_invoice_workflow(self, service, mock_db):
        """Test complete STR invoice template workflow"""
        # Setup mock database response
        field_mappings = {
            "fields": {
                "reservationCode": {
                    "source": "database",
                    "path": "booking.reservationCode",
                    "format": "text",
                    "required": True
                },
                "guestName": {
                    "source": "database",
                    "path": "booking.guestName",
                    "format": "text",
                    "transform": "uppercase"
                },
                "amountGross": {
                    "source": "database",
                    "path": "booking.amountGross",
                    "format": "currency"
                }
            },
            "formatting": {
                "currency": "EUR",
                "date_format": "DD-MM-YYYY",
                "number_decimals": 2
            }
        }
        
        mock_db.execute_query.return_value = [{
            'template_file_id': '1a2b3c4d5e6f',
            'field_mappings': json.dumps(field_mappings),
            'is_active': True,
            'created_at': datetime(2026, 1, 30, 10, 0, 0),
            'updated_at': datetime(2026, 1, 30, 12, 0, 0)
        }]
        
        # Get template metadata
        metadata = service.get_template_metadata('GoodwinSolutions', 'str_invoice')
        assert metadata is not None
        
        # Apply field mappings
        template = """
        <invoice>
            <code>{{ reservationCode }}</code>
            <guest>{{ guestName }}</guest>
            <total>{{ amountGross }}</total>
        </invoice>
        """
        
        data = {
            "booking": {
                "reservationCode": "RES-12345",
                "guestName": "John Doe",
                "amountGross": 250.75
            }
        }
        
        result = service.apply_field_mappings(template, data, metadata['field_mappings'])
        
        # Verify results
        assert "RES-12345" in result
        assert "JOHN DOE" in result
        assert "€ 250.75" in result
        
        # Generate HTML output
        html_output = service.generate_output(result, data, 'html')
        assert html_output == result
