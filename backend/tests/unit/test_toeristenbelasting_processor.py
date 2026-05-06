"""
Unit tests for toeristenbelasting_processor module.

Tests tourist tax calculation with various rates and periods,
report data preparation, and template rendering output.

Requirements: 1.4, 2.2, 8.5
"""

import pytest
from unittest.mock import patch, MagicMock

from toeristenbelasting_processor import ToeristenbelastingProcessor


class TestGenerateToeristenbelastingReport:
    """Tests for generate_toeristenbelasting_report method."""

    @pytest.fixture
    def processor(self, mock_db):
        """Create ToeristenbelastingProcessor with mocked DatabaseManager."""
        with patch('toeristenbelasting_processor.DatabaseManager', return_value=mock_db):
            proc = ToeristenbelastingProcessor(test_mode=True)
        return proc

    @patch('toeristenbelasting_processor.get_bnb_cache')
    @patch('toeristenbelasting_processor.get_cache')
    @patch('toeristenbelasting_processor.toeristenbelasting_generator.generate_toeristenbelasting_report')
    def test_generate_report_success_returns_html(
        self, mock_generator, mock_get_cache, mock_get_bnb_cache, processor
    ):
        """Test successful report generation returns HTML report."""
        mock_cache = MagicMock()
        mock_bnb_cache = MagicMock()
        mock_get_cache.return_value = mock_cache
        mock_get_bnb_cache.return_value = mock_bnb_cache

        mock_generator.return_value = {
            'success': True,
            'template_data': {
                'year': 2024,
                'total_nights': 120,
                'total_guests': 200,
                'tax_rate': 3.0,
                'total_tax': 600.0,
            },
            'raw_data': {
                'administration': 'TestAdmin',
                'bookings': [],
            }
        }

        # Mock TemplateService
        with patch('toeristenbelasting_processor.TemplateService') as MockTS:
            mock_ts = MagicMock()
            MockTS.return_value = mock_ts
            mock_ts.get_template_metadata.return_value = None

            # Mock filesystem template
            template_html = '<html><body>{{year}} - {{total_tax}}</body></html>'
            with patch('builtins.open', MagicMock(return_value=MagicMock(
                __enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=template_html))),
                __exit__=MagicMock(return_value=False)
            ))):
                with patch('os.path.exists', return_value=True):
                    mock_ts.apply_field_mappings.return_value = '<html><body>2024 - 600.0</body></html>'
                    result = processor.generate_toeristenbelasting_report(2024)

        assert result['success'] is True
        assert 'html_report' in result
        assert 'data' in result

    @patch('toeristenbelasting_processor.get_bnb_cache')
    @patch('toeristenbelasting_processor.get_cache')
    @patch('toeristenbelasting_processor.toeristenbelasting_generator.generate_toeristenbelasting_report')
    def test_generate_report_generator_failure_returns_error(
        self, mock_generator, mock_get_cache, mock_get_bnb_cache, processor
    ):
        """Test that generator failure returns error result."""
        mock_get_cache.return_value = MagicMock()
        mock_get_bnb_cache.return_value = MagicMock()

        mock_generator.return_value = {
            'success': False,
            'error': 'No booking data found for year 2024'
        }

        result = processor.generate_toeristenbelasting_report(2024)

        assert result['success'] is False
        assert 'No booking data' in result['error']

    @patch('toeristenbelasting_processor.get_bnb_cache')
    @patch('toeristenbelasting_processor.get_cache')
    @patch('toeristenbelasting_processor.toeristenbelasting_generator.generate_toeristenbelasting_report')
    def test_generate_report_template_not_found_returns_error(
        self, mock_generator, mock_get_cache, mock_get_bnb_cache, processor
    ):
        """Test that missing template returns error."""
        mock_get_cache.return_value = MagicMock()
        mock_get_bnb_cache.return_value = MagicMock()

        mock_generator.return_value = {
            'success': True,
            'template_data': {'year': 2024},
            'raw_data': {'administration': None}
        }

        with patch('toeristenbelasting_processor.TemplateService') as MockTS:
            mock_ts = MagicMock()
            MockTS.return_value = mock_ts
            mock_ts.get_template_metadata.side_effect = Exception("No metadata")

            with patch('os.path.exists', return_value=False):
                result = processor.generate_toeristenbelasting_report(2024)

        assert result['success'] is False
        assert 'Template not found' in result['error']

    @patch('toeristenbelasting_processor.get_bnb_cache')
    @patch('toeristenbelasting_processor.get_cache')
    @patch('toeristenbelasting_processor.toeristenbelasting_generator.generate_toeristenbelasting_report')
    def test_generate_report_with_google_drive_template(
        self, mock_generator, mock_get_cache, mock_get_bnb_cache, processor
    ):
        """Test report generation using Google Drive template."""
        mock_get_cache.return_value = MagicMock()
        mock_get_bnb_cache.return_value = MagicMock()

        mock_generator.return_value = {
            'success': True,
            'template_data': {'year': 2024, 'total_tax': 450.0},
            'raw_data': {'administration': 'TestAdmin'}
        }

        with patch('toeristenbelasting_processor.TemplateService') as MockTS:
            mock_ts = MagicMock()
            MockTS.return_value = mock_ts
            mock_ts.get_template_metadata.return_value = {
                'template_file_id': 'drive-file-123',
                'field_mappings': {'fields': {}}
            }
            mock_ts.fetch_template_from_drive.return_value = '<html>Drive Template</html>'
            mock_ts.apply_field_mappings.return_value = '<html>Rendered Drive Template</html>'

            result = processor.generate_toeristenbelasting_report(2024)

        assert result['success'] is True
        assert result['html_report'] == '<html>Rendered Drive Template</html>'
        mock_ts.fetch_template_from_drive.assert_called_once_with('drive-file-123', 'TestAdmin')

    @patch('toeristenbelasting_processor.get_bnb_cache')
    @patch('toeristenbelasting_processor.get_cache')
    @patch('toeristenbelasting_processor.toeristenbelasting_generator.generate_toeristenbelasting_report')
    def test_generate_report_drive_failure_falls_back_to_filesystem(
        self, mock_generator, mock_get_cache, mock_get_bnb_cache, processor
    ):
        """Test that Google Drive failure falls back to filesystem template."""
        mock_get_cache.return_value = MagicMock()
        mock_get_bnb_cache.return_value = MagicMock()

        mock_generator.return_value = {
            'success': True,
            'template_data': {'year': 2024},
            'raw_data': {'administration': 'TestAdmin'}
        }

        with patch('toeristenbelasting_processor.TemplateService') as MockTS:
            mock_ts = MagicMock()
            MockTS.return_value = mock_ts
            mock_ts.get_template_metadata.return_value = {
                'template_file_id': 'drive-file-123',
                'field_mappings': {}
            }
            mock_ts.fetch_template_from_drive.side_effect = Exception("Drive unavailable")
            mock_ts.apply_field_mappings.return_value = '<html>Filesystem Fallback</html>'

            with patch('os.path.exists', return_value=True):
                with patch('builtins.open', MagicMock(return_value=MagicMock(
                    __enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value='<html>FS</html>'))),
                    __exit__=MagicMock(return_value=False)
                ))):
                    result = processor.generate_toeristenbelasting_report(2024)

        assert result['success'] is True
        assert result['html_report'] == '<html>Filesystem Fallback</html>'

    @patch('toeristenbelasting_processor.get_bnb_cache')
    @patch('toeristenbelasting_processor.get_cache')
    def test_generate_report_exception_returns_error(
        self, mock_get_cache, mock_get_bnb_cache, processor
    ):
        """Test that unhandled exceptions return error result."""
        mock_get_cache.side_effect = Exception("Cache initialization failed")

        result = processor.generate_toeristenbelasting_report(2024)

        assert result['success'] is False
        assert 'Cache initialization failed' in result['error']

    def test_processor_init_sets_test_mode(self, mock_db):
        """Test that test_mode is properly set on initialization."""
        with patch('toeristenbelasting_processor.DatabaseManager', return_value=mock_db):
            proc = ToeristenbelastingProcessor(test_mode=True)

        assert proc.test_mode is True

    @patch('toeristenbelasting_processor.get_bnb_cache')
    @patch('toeristenbelasting_processor.get_cache')
    @patch('toeristenbelasting_processor.toeristenbelasting_generator.generate_toeristenbelasting_report')
    def test_generate_report_passes_year_to_generator(
        self, mock_generator, mock_get_cache, mock_get_bnb_cache, processor
    ):
        """Test that the year parameter is passed to the generator."""
        mock_get_cache.return_value = MagicMock()
        mock_get_bnb_cache.return_value = MagicMock()
        mock_generator.return_value = {'success': False, 'error': 'No data'}

        processor.generate_toeristenbelasting_report(2023)

        # Verify year was passed to generator
        call_kwargs = mock_generator.call_args[1]
        assert call_kwargs['year'] == 2023
