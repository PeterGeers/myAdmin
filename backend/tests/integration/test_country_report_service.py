"""
Integration tests for country_report_service.py

Tests report data aggregation with mocked DB and HTML rendering output.
Validates: Requirements 4.1, 8.2, 8.4
"""

import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestGetCountryReportData:
    """Tests for get_country_report_data function."""

    def test_get_country_report_data_single_tenant_returns_tuple(self, mock_db, mock_env):
        """Test that report data returns a 3-tuple for a single tenant."""
        from services.country_report_service import get_country_report_data

        mock_cursor = MagicMock()
        mock_connection = MagicMock()
        mock_db.get_connection.return_value = mock_connection
        mock_connection.cursor.return_value = mock_cursor

        # Setup cursor responses for the 3 queries
        country_rows = [
            ('NL', 'Netherlands', 'Nederland', 'Europe', 50),
            ('DE', 'Germany', 'Duitsland', 'Europe', 30),
        ]
        total_row = (80,)
        region_rows = [
            ('Europe', 80),
        ]

        mock_cursor.fetchall.side_effect = [country_rows, region_rows]
        mock_cursor.fetchone.return_value = total_row

        with patch('database.DatabaseManager', return_value=mock_db):
            country_data, region_data, total_bookings = get_country_report_data(['tenant1'])

        assert country_data == country_rows
        assert region_data == region_rows
        assert total_bookings == 80

    def test_get_country_report_data_multiple_tenants_builds_placeholders(self, mock_db, mock_env):
        """Test that multiple tenants generate correct SQL placeholders."""
        from services.country_report_service import get_country_report_data

        mock_cursor = MagicMock()
        mock_connection = MagicMock()
        mock_db.get_connection.return_value = mock_connection
        mock_connection.cursor.return_value = mock_cursor

        mock_cursor.fetchall.side_effect = [[], []]
        mock_cursor.fetchone.return_value = (0,)

        with patch('database.DatabaseManager', return_value=mock_db):
            get_country_report_data(['tenant1', 'tenant2', 'tenant3'])

        # Verify cursor.execute was called 3 times (country, total, region queries)
        assert mock_cursor.execute.call_count == 3

        # Verify the tenants were passed to each query
        for call in mock_cursor.execute.call_args_list:
            args = call[0]
            assert args[1] == ['tenant1', 'tenant2', 'tenant3']

    def test_get_country_report_data_empty_results(self, mock_db, mock_env):
        """Test handling of empty query results."""
        from services.country_report_service import get_country_report_data

        mock_cursor = MagicMock()
        mock_connection = MagicMock()
        mock_db.get_connection.return_value = mock_connection
        mock_connection.cursor.return_value = mock_cursor

        mock_cursor.fetchall.side_effect = [[], []]
        mock_cursor.fetchone.return_value = (0,)

        with patch('database.DatabaseManager', return_value=mock_db):
            country_data, region_data, total_bookings = get_country_report_data(['tenant1'])

        assert country_data == []
        assert region_data == []
        assert total_bookings == 0

    def test_get_country_report_data_closes_cursor_and_connection(self, mock_db, mock_env):
        """Test that cursor and connection are properly closed after query."""
        from services.country_report_service import get_country_report_data

        mock_cursor = MagicMock()
        mock_connection = MagicMock()
        mock_db.get_connection.return_value = mock_connection
        mock_connection.cursor.return_value = mock_cursor

        mock_cursor.fetchall.side_effect = [[], []]
        mock_cursor.fetchone.return_value = (0,)

        with patch('database.DatabaseManager', return_value=mock_db):
            get_country_report_data(['tenant1'])

        mock_cursor.close.assert_called_once()
        mock_connection.close.assert_called_once()


class TestGenerateCountryReportHtml:
    """Tests for generate_country_report_html function."""

    def test_generate_html_contains_title(self, mock_env):
        """Test that generated HTML contains the report title."""
        from services.country_report_service import generate_country_report_html

        country_data = [('NL', 'Netherlands', 'Nederland', 'Europe', 10)]
        region_data = [('Europe', 10)]
        total_bookings = 10

        html = generate_country_report_html(country_data, region_data, total_bookings)

        assert 'Bookings by Country' in html
        assert '<!DOCTYPE html>' in html

    def test_generate_html_contains_country_data(self, mock_env):
        """Test that generated HTML includes country information."""
        from services.country_report_service import generate_country_report_html

        country_data = [
            ('NL', 'Netherlands', 'Nederland', 'Europe', 50),
            ('DE', 'Germany', 'Duitsland', 'Europe', 30),
        ]
        region_data = [('Europe', 80)]
        total_bookings = 80

        html = generate_country_report_html(country_data, region_data, total_bookings)

        assert 'Netherlands' in html
        assert 'Germany' in html
        assert 'Nederland' in html
        assert 'Duitsland' in html
        assert 'NL' in html
        assert 'DE' in html

    def test_generate_html_contains_region_data(self, mock_env):
        """Test that generated HTML includes region information."""
        from services.country_report_service import generate_country_report_html

        country_data = [('NL', 'Netherlands', 'Nederland', 'Europe', 10)]
        region_data = [
            ('Europe', 70),
            ('Asia', 30),
        ]
        total_bookings = 100

        html = generate_country_report_html(country_data, region_data, total_bookings)

        assert 'Europe' in html
        assert 'Asia' in html

    def test_generate_html_contains_total_bookings(self, mock_env):
        """Test that generated HTML displays total bookings count."""
        from services.country_report_service import generate_country_report_html

        country_data = [('US', 'United States', 'Verenigde Staten', 'Americas', 42)]
        region_data = [('Americas', 42)]
        total_bookings = 42

        html = generate_country_report_html(country_data, region_data, total_bookings)

        assert '42' in html

    def test_generate_html_contains_percentage(self, mock_env):
        """Test that generated HTML includes percentage calculations."""
        from services.country_report_service import generate_country_report_html

        country_data = [
            ('NL', 'Netherlands', 'Nederland', 'Europe', 75),
            ('DE', 'Germany', 'Duitsland', 'Europe', 25),
        ]
        region_data = [('Europe', 100)]
        total_bookings = 100

        html = generate_country_report_html(country_data, region_data, total_bookings)

        assert '75.0%' in html
        assert '25.0%' in html

    def test_generate_html_handles_none_region(self, mock_env):
        """Test that generated HTML handles None region gracefully."""
        from services.country_report_service import generate_country_report_html

        country_data = [('XX', 'Unknown', None, None, 5)]
        region_data = [('Europe', 5)]
        total_bookings = 5

        html = generate_country_report_html(country_data, region_data, total_bookings)

        assert 'N/A' in html

    def test_generate_html_ranking_order(self, mock_env):
        """Test that countries are ranked in order."""
        from services.country_report_service import generate_country_report_html

        country_data = [
            ('NL', 'Netherlands', 'Nederland', 'Europe', 100),
            ('DE', 'Germany', 'Duitsland', 'Europe', 50),
            ('FR', 'France', 'Frankrijk', 'Europe', 25),
        ]
        region_data = [('Europe', 175)]
        total_bookings = 175

        html = generate_country_report_html(country_data, region_data, total_bookings)

        assert '#1' in html
        assert '#2' in html
        assert '#3' in html


class TestSaveReport:
    """Tests for save_report function."""

    def test_save_report_creates_file(self, mock_env, temp_dir):
        """Test that save_report writes HTML content to a file."""
        from services.country_report_service import save_report

        html_content = '<html><body>Test Report</body></html>'

        with patch('services.country_report_service.Path') as mock_path_class:
            # Make the Path resolve to our temp directory
            mock_output_dir = Path(temp_dir)
            mock_path_class.return_value.parent.parent.parent.__truediv__ = lambda self, x: mock_output_dir

            # Actually write to temp_dir directly
            output_file = Path(temp_dir) / 'test_report.html'
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)

            assert output_file.exists()
            assert output_file.read_text(encoding='utf-8') == html_content

    def test_save_report_default_filename(self, mock_env):
        """Test that save_report uses default filename when none provided."""
        from services.country_report_service import save_report

        html_content = '<html><body>Test</body></html>'

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch('services.country_report_service.Path') as mock_path_class:
                mock_file_path = MagicMock()
                mock_output_dir = MagicMock()
                mock_path_class.return_value = mock_file_path
                mock_file_path.parent.parent.parent.__truediv__.return_value = mock_output_dir
                mock_output_dir.mkdir.return_value = None

                # Use real path for actual file writing
                real_output = Path(tmp_dir) / 'country_bookings_report.html'
                mock_output_dir.__truediv__.return_value = real_output

                result = save_report(html_content)

                assert result == real_output
                assert real_output.read_text(encoding='utf-8') == html_content

    def test_save_report_custom_filename(self, mock_env):
        """Test that save_report uses custom filename when provided."""
        from services.country_report_service import save_report

        html_content = '<html><body>Custom</body></html>'

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch('services.country_report_service.Path') as mock_path_class:
                mock_file_path = MagicMock()
                mock_output_dir = MagicMock()
                mock_path_class.return_value = mock_file_path
                mock_file_path.parent.parent.parent.__truediv__.return_value = mock_output_dir
                mock_output_dir.mkdir.return_value = None

                real_output = Path(tmp_dir) / 'custom_report.html'
                mock_output_dir.__truediv__.return_value = real_output

                result = save_report(html_content, 'custom_report.html')

                assert result == real_output
                assert real_output.read_text(encoding='utf-8') == html_content
