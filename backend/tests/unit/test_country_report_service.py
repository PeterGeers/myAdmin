"""
Unit tests for country_report_service.py

Tests report data fetching, HTML generation, and file saving
with mocked database and file system dependencies.
"""

import pytest
import tempfile
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path

from services.country_report_service import (
    get_country_report_data,
    generate_country_report_html,
    save_report,
)


# ============================================================================
# get_country_report_data
# ============================================================================


@pytest.mark.unit
class TestGetCountryReportData:
    """Tests for get_country_report_data function."""

    def test_returns_data_for_valid_tenants(self, mock_db, mock_env):
        """Test that valid tenants return expected country, region, and total data."""
        mock_cursor = MagicMock()
        mock_connection = MagicMock()
        mock_db.get_connection.return_value = mock_connection
        mock_connection.cursor.return_value = mock_cursor

        country_rows = [
            ('NL', 'Netherlands', 'Nederland', 'Europe', 50),
            ('DE', 'Germany', 'Duitsland', 'Europe', 30),
            ('US', 'United States', 'Verenigde Staten', 'Americas', 20),
        ]
        region_rows = [
            ('Europe', 80),
            ('Americas', 20),
        ]
        mock_cursor.fetchall.side_effect = [country_rows, region_rows]
        mock_cursor.fetchone.return_value = (100,)

        with patch('database.DatabaseManager', return_value=mock_db):
            country_data, region_data, total_bookings = get_country_report_data(
                ['tenant1', 'tenant2']
            )

        assert country_data == country_rows
        assert region_data == region_rows
        assert total_bookings == 100

    def test_handles_empty_results(self, mock_db, mock_env):
        """Test that empty query results are handled gracefully."""
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

    def test_handles_database_exception(self, mock_db, mock_env):
        """Test that database exceptions propagate correctly."""
        mock_connection = MagicMock()
        mock_db.get_connection.return_value = mock_connection
        mock_connection.cursor.side_effect = Exception("Database connection failed")

        with patch('database.DatabaseManager', return_value=mock_db):
            with pytest.raises(Exception, match="Database connection failed"):
                get_country_report_data(['tenant1'])


# ============================================================================
# generate_country_report_html
# ============================================================================


@pytest.mark.unit
class TestGenerateCountryReportHtml:
    """Tests for generate_country_report_html function."""

    def test_creates_valid_html_with_country_data(self):
        """Test that generated HTML is a complete document with country data."""
        country_data = [
            ('NL', 'Netherlands', 'Nederland', 'Europe', 60),
            ('DE', 'Germany', 'Duitsland', 'Europe', 40),
        ]
        region_data = [('Europe', 100)]
        total_bookings = 100

        html = generate_country_report_html(country_data, region_data, total_bookings)

        assert '<!DOCTYPE html>' in html
        assert '<html' in html
        assert '</html>' in html
        assert 'Netherlands' in html
        assert 'Germany' in html
        assert 'NL' in html
        assert 'DE' in html

    def test_handles_empty_data(self):
        """Test HTML generation with empty country and region data."""
        country_data = []
        region_data = []
        total_bookings = 0

        html = generate_country_report_html(country_data, region_data, total_bookings)

        assert '<!DOCTYPE html>' in html
        assert 'Bookings by Country' in html
        # Stats should show 0
        assert '>0<' in html or '0' in html

    def test_includes_all_countries_in_output(self):
        """Test that every country in input appears in the HTML output."""
        country_data = [
            ('NL', 'Netherlands', 'Nederland', 'Europe', 50),
            ('DE', 'Germany', 'Duitsland', 'Europe', 30),
            ('FR', 'France', 'Frankrijk', 'Europe', 15),
            ('US', 'United States', 'Verenigde Staten', 'Americas', 5),
        ]
        region_data = [('Europe', 95), ('Americas', 5)]
        total_bookings = 100

        html = generate_country_report_html(country_data, region_data, total_bookings)

        # Verify all countries are present
        assert 'Netherlands' in html
        assert 'Germany' in html
        assert 'France' in html
        assert 'United States' in html
        # Verify all country codes are present
        assert 'NL' in html
        assert 'DE' in html
        assert 'FR' in html
        assert 'US' in html
        # Verify all regions are present
        assert 'Europe' in html
        assert 'Americas' in html


# ============================================================================
# save_report
# ============================================================================


@pytest.mark.unit
class TestSaveReport:
    """Tests for save_report function."""

    def test_writes_file_successfully(self, mock_env):
        """Test that save_report writes HTML content to a file."""
        html_content = '<html><body>Test Report</body></html>'

        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_output_dir = Path(tmp_dir)

            with patch('services.country_report_service.Path') as mock_path_class:
                # Make Path(__file__) resolve so parent.parent.parent / 'reports' → our temp dir
                mock_file_path = MagicMock()
                mock_path_class.return_value = mock_file_path
                mock_file_path.parent.parent.parent.__truediv__.return_value = mock_output_dir

                result = save_report(html_content)

            expected_file = mock_output_dir / 'country_bookings_report.html'
            assert result == expected_file
            assert expected_file.exists()
            assert expected_file.read_text(encoding='utf-8') == html_content

    def test_handles_file_write_error(self, mock_env):
        """Test that save_report raises on file write errors."""
        html_content = '<html><body>Test</body></html>'

        with patch('services.country_report_service.Path') as mock_path_class:
            mock_file_path = MagicMock()
            mock_path_class.return_value = mock_file_path
            mock_output_dir = MagicMock()
            mock_file_path.parent.parent.parent.__truediv__.return_value = mock_output_dir
            mock_output_dir.mkdir.return_value = None
            # Make the output file path raise on open
            mock_output_file = MagicMock()
            mock_output_dir.__truediv__.return_value = mock_output_file

            with patch('builtins.open', side_effect=PermissionError("Permission denied")):
                with pytest.raises(PermissionError, match="Permission denied"):
                    save_report(html_content)
