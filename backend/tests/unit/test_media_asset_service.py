"""
Unit tests for MediaAssetService internal helper methods.

Tests: _generate_asset_id, _resolve_bucket, _build_s3_key, _validate_file
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from db_exceptions import IntegrityError
from services.media_asset_service import MediaAssetService


# ============================================================================
# Module-level test environment
# ============================================================================
#
# Every test in this module exercises MediaAssetService, whose bucket
# resolution reads S3_SHARED_BUCKET / LANDING_PAGES_BUCKET from os.environ at
# CALL time (not at construction). Several tests also reach code paths that
# instantiate a real boto3 S3 client.
#
# On CI there is no .env file, so neither the bucket env vars nor AWS
# credentials are present. Previous per-class `service_with_env` fixtures set
# the env var inside a `with patch.dict(...)` block but returned the service
# from inside that block, so the patch was torn down before the test body ran
# — meaning the env var was never actually set during the test. Locally this
# went unnoticed because database.py calls load_dotenv() at import, leaking the
# developer's real .env (bucket names + AWS credentials) into os.environ.
#
# This autouse, module-scoped fixture fixes it once for the ENTIRE module: it
# guarantees the bucket env vars are set for the duration of every test and
# replaces boto3.client with a MagicMock so no real AWS credentials are ever
# required. Newly added test classes inherit this automatically, so the
# recurring S3_SHARED_BUCKET / NoCredentialsError failures cannot regress.
#
# Tests that patch `services.media_asset_service.boto3.client` themselves (e.g.
# TestUploadRaw, TestDeleteRaw, TestGetPresignedUrl) still work: their inner
# `with patch(...)` overrides this default mock for the test body and restores
# it on exit. TestResolveBucket::test_missing_env_var_raises_valueerror clears
# os.environ within its own `with patch.dict(..., clear=True)` block, so it is
# also unaffected.
@pytest.fixture(autouse=True)
def media_asset_test_env():
    """Set bucket env vars and mock boto3 for the whole media-asset test module.

    autouse so every test class (TestStoreAndRegister, TestLifecycle,
    TestReconcileReferences, TestImportLegacyAssets, TestImportIntegration, ...)
    inherits it without per-class wiring.
    """
    bucket_env = {
        'S3_SHARED_BUCKET': 'test-shared-bucket',
        'LANDING_PAGES_BUCKET': 'test-public-pages-bucket',
    }
    # LandingPageService talks to DynamoDB via a boto3 *resource* (not the s3
    # client), so mocking boto3.client alone is not enough for the reconcile
    # path that resolves landing_page references. Patch the service class where
    # it is imported (lazily, inside _reconcile_references) so no real AWS
    # resource / credentials are ever needed. get_draft returns a truthy value
    # by default (entity exists); tests that need a "missing" draft override the
    # instance on the service under test.
    mock_landing_page_service = MagicMock()
    mock_landing_page_service.get_draft.return_value = {'slug': 'exists'}
    with patch.dict(os.environ, bucket_env), \
            patch('services.media_asset_service.boto3.client', return_value=MagicMock()), \
            patch(
                'services.landing_page_service.LandingPageService',
                return_value=mock_landing_page_service,
            ):
        yield


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute_query.return_value = []
    return db


@pytest.fixture
def service(mock_db):
    with patch('services.media_asset_service.ParameterService'):
        return MediaAssetService(mock_db)


# ============================================================================
# _generate_asset_id
# ============================================================================

class TestGenerateAssetId:

    def test_starts_with_ast_prefix(self, service):
        asset_id = service._generate_asset_id()
        assert asset_id.startswith('ast_')

    def test_has_ulid_after_prefix(self, service):
        asset_id = service._generate_asset_id()
        ulid_part = asset_id[4:]  # strip 'ast_'
        # ULIDs are 26 characters in their canonical string representation
        assert len(ulid_part) == 26

    def test_generates_unique_ids(self, service):
        ids = {service._generate_asset_id() for _ in range(100)}
        assert len(ids) == 100

    def test_ulid_is_alphanumeric(self, service):
        asset_id = service._generate_asset_id()
        ulid_part = asset_id[4:]
        # ULID uses Crockford Base32: 0-9, A-Z (excluding I, L, O, U)
        assert all(c.isalnum() for c in ulid_part)


# ============================================================================
# _resolve_bucket
# ============================================================================

class TestResolveBucket:

    def test_invoices_uses_shared_bucket(self, service):
        with patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-prod'}):
            bucket = service._resolve_bucket('invoices')
            assert bucket == 'myadmin-shared-prod'

    def test_branding_uses_shared_bucket(self, service):
        with patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-dev'}):
            bucket = service._resolve_bucket('branding')
            assert bucket == 'myadmin-shared-dev'

    def test_templates_uses_shared_bucket(self, service):
        with patch.dict(os.environ, {'S3_SHARED_BUCKET': 'myadmin-shared-test'}):
            bucket = service._resolve_bucket('templates')
            assert bucket == 'myadmin-shared-test'

    def test_landing_pages_uses_public_pages_bucket(self, service):
        with patch.dict(os.environ, {'LANDING_PAGES_BUCKET': 'myadmin-public-pages-prod'}):
            bucket = service._resolve_bucket('landing-pages')
            assert bucket == 'myadmin-public-pages-prod'

    def test_unknown_category_raises_valueerror(self, service):
        with pytest.raises(ValueError, match="Unknown category 'photos'"):
            service._resolve_bucket('photos')

    def test_missing_env_var_raises_valueerror(self, service):
        with patch.dict(os.environ, {}, clear=True):
            # Remove the env var entirely
            os.environ.pop('S3_SHARED_BUCKET', None)
            with pytest.raises(ValueError, match="Environment variable 'S3_SHARED_BUCKET' is not set"):
                service._resolve_bucket('invoices')

    def test_error_lists_valid_categories(self, service):
        with pytest.raises(ValueError, match="Valid categories:"):
            service._resolve_bucket('unknown')


# ============================================================================
# _build_s3_key
# ============================================================================

class TestBuildS3Key:

    def test_basic_key_structure(self, service):
        key = service._build_s3_key('TenantA', 'invoices', 'ast_01ABC', 'report.pdf')
        assert key == 'TenantA/invoices/ast_01ABC_report.pdf'

    def test_branding_category(self, service):
        key = service._build_s3_key('GoodwinSolutions', 'branding', 'ast_XYZ123', 'logo.png')
        assert key == 'GoodwinSolutions/branding/ast_XYZ123_logo.png'

    def test_landing_pages_category(self, service):
        key = service._build_s3_key('my-slug', 'landing-pages', 'ast_01H5K3', 'hero.webp')
        assert key == 'my-slug/landing-pages/ast_01H5K3_hero.webp'

    def test_filename_with_spaces(self, service):
        key = service._build_s3_key('Tenant', 'invoices', 'ast_ID1', 'Q1 report final.pdf')
        assert key == 'Tenant/invoices/ast_ID1_Q1 report final.pdf'

    def test_templates_category(self, service):
        key = service._build_s3_key('Corp', 'templates', 'ast_T1', 'invoice_nl.html')
        assert key == 'Corp/templates/ast_T1_invoice_nl.html'


# ============================================================================
# _validate_file
# ============================================================================

class TestValidateFile:
    """Tests for file validation: extension, magic bytes, size."""

    # --- JPEG ---

    def test_valid_jpeg(self, service):
        data = b'\xff\xd8\xff\xe0' + b'\x00' * 100
        result = service._validate_file(data, 'photo.jpg')
        assert result['media_type'] == 'image'
        assert result['mime_type'] == 'image/jpeg'

    def test_valid_jpeg_extension(self, service):
        data = b'\xff\xd8\xff\xe1' + b'\x00' * 100
        result = service._validate_file(data, 'photo.jpeg')
        assert result['media_type'] == 'image'
        assert result['mime_type'] == 'image/jpeg'

    # --- PNG ---

    def test_valid_png(self, service):
        data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        result = service._validate_file(data, 'image.png')
        assert result['media_type'] == 'image'
        assert result['mime_type'] == 'image/png'

    # --- WebP ---

    def test_valid_webp(self, service):
        data = b'RIFF' + b'\x00' * 4 + b'WEBP' + b'\x00' * 100
        result = service._validate_file(data, 'photo.webp')
        assert result['media_type'] == 'image'
        assert result['mime_type'] == 'image/webp'

    # --- GIF ---

    def test_valid_gif87a(self, service):
        data = b'GIF87a' + b'\x00' * 100
        result = service._validate_file(data, 'animation.gif')
        assert result['media_type'] == 'image'
        assert result['mime_type'] == 'image/gif'

    def test_valid_gif89a(self, service):
        data = b'GIF89a' + b'\x00' * 100
        result = service._validate_file(data, 'animation.gif')
        assert result['media_type'] == 'image'
        assert result['mime_type'] == 'image/gif'

    # --- PDF ---

    def test_valid_pdf(self, service):
        data = b'%PDF-1.4' + b'\x00' * 100
        result = service._validate_file(data, 'document.pdf')
        assert result['media_type'] == 'document'
        assert result['mime_type'] == 'application/pdf'

    # --- MP4 ---

    def test_valid_mp4(self, service):
        # MP4 has ftyp at offset 4
        data = b'\x00\x00\x00\x20ftyp' + b'isom' + b'\x00' * 100
        result = service._validate_file(data, 'video.mp4')
        assert result['media_type'] == 'video'
        assert result['mime_type'] == 'video/mp4'

    # --- WebM ---

    def test_valid_webm(self, service):
        data = b'\x1aE\xdf\xa3' + b'\x00' * 100
        result = service._validate_file(data, 'clip.webm')
        assert result['media_type'] == 'video'
        assert result['mime_type'] == 'video/webm'

    # --- Web Content (no magic bytes) ---

    def test_valid_html(self, service):
        data = b'<!DOCTYPE html><html><head></head><body></body></html>'
        result = service._validate_file(data, 'index.html')
        assert result['media_type'] == 'web_content'
        assert result['mime_type'] == 'text/html'

    def test_valid_json(self, service):
        data = b'{"key": "value", "list": [1, 2, 3]}'
        result = service._validate_file(data, 'data.json')
        assert result['media_type'] == 'web_content'
        assert result['mime_type'] == 'application/json'

    def test_json_array(self, service):
        data = b'[{"id": 1}, {"id": 2}]'
        result = service._validate_file(data, 'items.json')
        assert result['media_type'] == 'web_content'
        assert result['mime_type'] == 'application/json'

    # --- Error cases ---

    def test_empty_file_raises(self, service):
        with pytest.raises(ValueError, match="A file is required"):
            service._validate_file(b'', 'empty.pdf')

    def test_none_data_raises(self, service):
        with pytest.raises(ValueError, match="A file is required"):
            service._validate_file(None, 'empty.pdf')

    def test_unsupported_extension_raises(self, service):
        with pytest.raises(ValueError, match="Unsupported file type '.exe'"):
            service._validate_file(b'\x00' * 100, 'malware.exe')

    def test_unsupported_extension_lists_allowed(self, service):
        with pytest.raises(ValueError, match="Allowed types"):
            service._validate_file(b'\x00' * 100, 'file.zip')

    def test_magic_bytes_mismatch_raises(self, service):
        # PDF extension but JPEG magic bytes (cross-category mismatch)
        data = b'\xff\xd8\xff\xe0' + b'\x00' * 100
        with pytest.raises(ValueError, match="does not match"):
            service._validate_file(data, 'fake.pdf')

    def test_no_magic_bytes_match_raises(self, service):
        # Valid extension (.pdf) but garbage content
        data = b'THIS IS NOT A PDF' + b'\x00' * 100
        with pytest.raises(ValueError, match="does not match any known format"):
            service._validate_file(data, 'document.pdf')

    def test_image_oversized_raises(self, service):
        # 11 MB JPEG
        data = b'\xff\xd8\xff\xe0' + b'\x00' * (11 * 1024 * 1024)
        with pytest.raises(ValueError, match="exceeds the 10 MB limit"):
            service._validate_file(data, 'huge.jpg')

    def test_video_oversized_raises(self, service):
        # 101 MB MP4
        data = b'\x00\x00\x00\x20ftyp' + b'isom' + b'\x00' * (101 * 1024 * 1024)
        with pytest.raises(ValueError, match="exceeds the 100 MB limit"):
            service._validate_file(data, 'huge.mp4')

    def test_document_oversized_raises(self, service):
        # 26 MB PDF
        data = b'%PDF-1.4' + b'\x00' * (26 * 1024 * 1024)
        with pytest.raises(ValueError, match="exceeds the 25 MB limit"):
            service._validate_file(data, 'huge.pdf')

    def test_web_content_oversized_raises(self, service):
        # 6 MB HTML
        data = b'<!DOCTYPE html><html>' + b'x' * (6 * 1024 * 1024)
        with pytest.raises(ValueError, match="exceeds the 5 MB limit"):
            service._validate_file(data, 'huge.html')

    def test_invalid_html_content_raises(self, service):
        data = b'This is just plain text with no HTML markers'
        with pytest.raises(ValueError, match="does not appear to contain valid HTML"):
            service._validate_file(data, 'fake.html')

    def test_invalid_json_content_raises(self, service):
        data = b'not json at all'
        with pytest.raises(ValueError, match="does not appear to contain valid JSON"):
            service._validate_file(data, 'fake.json')

    # --- SVG validation tests ---

    def test_valid_svg_with_svg_tag(self, service):
        """SVG starting with <svg> tag validates successfully."""
        data = b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="10"/></svg>'
        result = service._validate_file(data, 'logo.svg')
        assert result['media_type'] == 'image'
        assert result['mime_type'] == 'image/svg+xml'

    def test_valid_svg_with_xml_declaration(self, service):
        """SVG starting with <?xml ...> declaration validates successfully."""
        data = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>'
        result = service._validate_file(data, 'logo.svg')
        assert result['media_type'] == 'image'
        assert result['mime_type'] == 'image/svg+xml'

    def test_invalid_svg_content_raises(self, service):
        """File with .svg extension but non-SVG content raises ValueError."""
        data = b'This is just plain text, not SVG at all'
        with pytest.raises(ValueError, match="does not appear to contain valid SVG"):
            service._validate_file(data, 'fake.svg')

    # --- Size boundary tests ---

    def test_image_at_exactly_max_size_passes(self, service):
        # Exactly 10 MB JPEG (should pass)
        data = b'\xff\xd8\xff\xe0' + b'\x00' * (10 * 1024 * 1024 - 4)
        result = service._validate_file(data, 'exact.jpg')
        assert result['media_type'] == 'image'

    def test_web_content_at_max_size_passes(self, service):
        # Exactly 5 MB JSON (should pass)
        json_start = b'{"data": "'
        padding = b'x' * (5 * 1024 * 1024 - len(json_start) - 2)
        data = json_start + padding + b'"}'
        result = service._validate_file(data, 'large.json')
        assert result['media_type'] == 'web_content'


# ============================================================================
# store_and_register
# ============================================================================

class TestStoreAndRegister:
    """Tests for the store_and_register method with mocked S3 + DB."""

    @pytest.fixture
    def service_with_env(self, mock_db):
        """Service with required env vars set."""
        with patch('services.media_asset_service.ParameterService'):
            with patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-bucket'}):
                svc = MediaAssetService(mock_db)
                return svc

    @pytest.fixture
    def valid_jpeg(self):
        """Valid JPEG file data for testing."""
        return b'\xff\xd8\xff\xe0' + b'\x00' * 100

    @pytest.fixture
    def valid_pdf(self):
        """Valid PDF file data for testing."""
        return b'%PDF-1.4' + b'\x00' * 100

    # --- Happy path: upload without reference ---

    def test_store_and_register_success_no_reference(self, service_with_env, valid_jpeg, mock_db):
        """AC 1, AC 9: Upload file, register with ACTIVE status, no reference."""
        with patch.object(service_with_env, '_upload_raw', return_value=True):
            mock_db.execute_query.return_value = []  # no duplicates
            # Mock the transaction context manager
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_db.transaction.return_value.__enter__ = MagicMock(
                return_value=(mock_cursor, mock_conn)
            )
            mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

            result = service_with_env.store_and_register(
                tenant='TenantA',
                file_data=valid_jpeg,
                filename='photo.jpg',
                category='invoices',
            )

        assert result['success'] is True
        assert result['asset']['status'] == 'ACTIVE'
        assert result['asset']['category'] == 'invoices'
        assert result['asset']['media_type'] == 'image'
        assert result['asset']['mime_type'] == 'image/jpeg'
        assert result['asset']['original_filename'] == 'photo.jpg'
        assert result['asset']['reference_count'] == 0
        assert result['asset']['id'].startswith('ast_')
        assert result['asset']['content_hash'] is not None
        assert len(result['asset']['content_hash']) == 64  # SHA-256 hex

    # --- Happy path: upload with reference ---

    def test_store_and_register_with_reference(self, service_with_env, valid_jpeg, mock_db):
        """AC 1, AC 8: Upload file with entity_type/entity_id creates reference."""
        with patch.object(service_with_env, '_upload_raw', return_value=True):
            mock_db.execute_query.return_value = []
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_db.transaction.return_value.__enter__ = MagicMock(
                return_value=(mock_cursor, mock_conn)
            )
            mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

            result = service_with_env.store_and_register(
                tenant='TenantA',
                file_data=valid_jpeg,
                filename='invoice.jpg',
                category='invoices',
                entity_type='invoice',
                entity_id='12345',
            )

        assert result['success'] is True
        assert result['asset']['reference_count'] == 1
        # Verify both INSERT queries were executed
        assert mock_cursor.execute.call_count == 2

    # --- Asset ID generation ---

    def test_store_and_register_generates_unique_asset_id(self, service_with_env, valid_jpeg, mock_db):
        """AC 2: Each asset gets a unique ast_<ULID> id."""
        with patch.object(service_with_env, '_upload_raw', return_value=True):
            mock_db.execute_query.return_value = []
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_db.transaction.return_value.__enter__ = MagicMock(
                return_value=(mock_cursor, mock_conn)
            )
            mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

            result1 = service_with_env.store_and_register(
                tenant='TenantA', file_data=valid_jpeg,
                filename='a.jpg', category='invoices',
            )
            result2 = service_with_env.store_and_register(
                tenant='TenantA', file_data=valid_jpeg,
                filename='b.jpg', category='invoices',
            )

        assert result1['asset']['id'] != result2['asset']['id']
        assert result1['asset']['id'].startswith('ast_')
        assert result2['asset']['id'].startswith('ast_')

    # --- S3 key structure ---

    def test_store_and_register_s3_key_structure(self, service_with_env, valid_jpeg, mock_db):
        """S3 key follows {tenant}/{category}/{asset_id}_{filename} pattern."""
        with patch.object(service_with_env, '_upload_raw', return_value=True):
            mock_db.execute_query.return_value = []
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_db.transaction.return_value.__enter__ = MagicMock(
                return_value=(mock_cursor, mock_conn)
            )
            mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

            result = service_with_env.store_and_register(
                tenant='TenantA', file_data=valid_jpeg,
                filename='photo.jpg', category='invoices',
            )

        s3_key = result['asset']['s3_key']
        asset_id = result['asset']['id']
        assert s3_key == f"TenantA/invoices/{asset_id}_photo.jpg"

    # --- Content hash computation ---

    def test_store_and_register_computes_sha256(self, service_with_env, valid_jpeg, mock_db):
        """Content hash is SHA-256 of file data."""
        import hashlib
        expected_hash = hashlib.sha256(valid_jpeg).hexdigest()

        with patch.object(service_with_env, '_upload_raw', return_value=True):
            mock_db.execute_query.return_value = []
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_db.transaction.return_value.__enter__ = MagicMock(
                return_value=(mock_cursor, mock_conn)
            )
            mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

            result = service_with_env.store_and_register(
                tenant='TenantA', file_data=valid_jpeg,
                filename='photo.jpg', category='invoices',
            )

        assert result['asset']['content_hash'] == expected_hash

    # --- S3 upload is called with correct args ---

    def test_store_and_register_calls_upload_raw(self, service_with_env, valid_jpeg, mock_db):
        """_upload_raw is called with bucket, key, file_data, content_type."""
        with patch.object(service_with_env, '_upload_raw', return_value=True) as mock_upload:
            mock_db.execute_query.return_value = []
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_db.transaction.return_value.__enter__ = MagicMock(
                return_value=(mock_cursor, mock_conn)
            )
            mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

            result = service_with_env.store_and_register(
                tenant='TenantA', file_data=valid_jpeg,
                filename='photo.jpg', category='invoices',
            )

        mock_upload.assert_called_once()
        call_args = mock_upload.call_args
        assert call_args[0][1].startswith('TenantA/invoices/')  # key contains tenant/category
        assert call_args[0][2] == valid_jpeg  # file_data
        assert call_args[0][3] == 'image/jpeg'  # content_type

    # --- S3 upload failure ---

    def test_store_and_register_s3_failure_no_db_records(self, service_with_env, valid_jpeg, mock_db):
        """Req 9 AC 9: If S3 write fails, no registry records are created."""
        with patch.object(service_with_env, '_upload_raw', return_value=False):
            result = service_with_env.store_and_register(
                tenant='TenantA', file_data=valid_jpeg,
                filename='photo.jpg', category='invoices',
            )

        assert result['success'] is False
        assert 'S3 upload failed' in result['error']
        # transaction should not have been called
        mock_db.transaction.assert_not_called()

    # --- DB commit failure after S3 write ---

    def test_store_and_register_db_failure_logs_orphaned_key(self, service_with_env, valid_jpeg, mock_db):
        """Req 9 AC 10: If DB commit fails after S3 write, log orphaned key."""
        with patch.object(service_with_env, '_upload_raw', return_value=True):
            mock_db.transaction.return_value.__enter__ = MagicMock(
                side_effect=Exception("DB connection lost")
            )
            mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

            result = service_with_env.store_and_register(
                tenant='TenantA', file_data=valid_jpeg,
                filename='photo.jpg', category='invoices',
            )

        assert result['success'] is False
        assert 'orphaned_key' in result
        assert result['orphaned_key']['key'].startswith('TenantA/invoices/')

    # --- File validation errors pass through ---

    def test_store_and_register_rejects_empty_file(self, service_with_env, mock_db):
        """AC 7: Empty file is rejected before any S3 or DB operations."""
        with pytest.raises(ValueError, match="A file is required"):
            service_with_env.store_and_register(
                tenant='TenantA', file_data=b'',
                filename='empty.jpg', category='invoices',
            )

    def test_store_and_register_rejects_unsupported_type(self, service_with_env, mock_db):
        """AC 5: Unsupported file type is rejected."""
        with pytest.raises(ValueError, match="Unsupported file type"):
            service_with_env.store_and_register(
                tenant='TenantA', file_data=b'\x00' * 100,
                filename='malware.exe', category='invoices',
            )

    def test_store_and_register_rejects_oversized_file(self, service_with_env, mock_db):
        """AC 6: Oversized file is rejected."""
        # 11 MB JPEG
        data = b'\xff\xd8\xff\xe0' + b'\x00' * (11 * 1024 * 1024)
        with pytest.raises(ValueError, match="exceeds"):
            service_with_env.store_and_register(
                tenant='TenantA', file_data=data,
                filename='huge.jpg', category='invoices',
            )

    # --- Invalid category ---

    def test_store_and_register_rejects_invalid_category(self, service_with_env, valid_jpeg, mock_db):
        """Invalid category raises ValueError before S3 upload."""
        with pytest.raises(ValueError, match="Unknown category"):
            service_with_env.store_and_register(
                tenant='TenantA', file_data=valid_jpeg,
                filename='photo.jpg', category='unknown',
            )

    # --- Duplicate detection ---

    def test_store_and_register_returns_duplicate_info(self, service_with_env, valid_jpeg, mock_db):
        """When a duplicate content_hash exists, returns duplicate_of info."""
        with patch.object(service_with_env, '_upload_raw', return_value=True):
            # Simulate existing duplicate found
            mock_db.execute_query.return_value = [
                {'id': 'ast_EXISTING123', 'original_filename': 'original.jpg'}
            ]
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_db.transaction.return_value.__enter__ = MagicMock(
                return_value=(mock_cursor, mock_conn)
            )
            mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

            result = service_with_env.store_and_register(
                tenant='TenantA', file_data=valid_jpeg,
                filename='photo.jpg', category='invoices',
            )

        assert result['success'] is True
        assert result['duplicate_of'] == {
            'asset_id': 'ast_EXISTING123',
            'original_filename': 'original.jpg',
        }

    def test_store_and_register_no_duplicate(self, service_with_env, valid_jpeg, mock_db):
        """When no duplicate exists, duplicate_of is None."""
        with patch.object(service_with_env, '_upload_raw', return_value=True):
            mock_db.execute_query.return_value = []  # no duplicates
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_db.transaction.return_value.__enter__ = MagicMock(
                return_value=(mock_cursor, mock_conn)
            )
            mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

            result = service_with_env.store_and_register(
                tenant='TenantA', file_data=valid_jpeg,
                filename='photo.jpg', category='invoices',
            )

        assert result['duplicate_of'] is None

    # --- PDF category ---

    def test_store_and_register_pdf_document(self, service_with_env, valid_pdf, mock_db):
        """Store and register works for PDF documents."""
        with patch.object(service_with_env, '_upload_raw', return_value=True):
            mock_db.execute_query.return_value = []
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_db.transaction.return_value.__enter__ = MagicMock(
                return_value=(mock_cursor, mock_conn)
            )
            mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

            result = service_with_env.store_and_register(
                tenant='TenantA', file_data=valid_pdf,
                filename='invoice.pdf', category='invoices',
            )

        assert result['success'] is True
        assert result['asset']['media_type'] == 'document'
        assert result['asset']['mime_type'] == 'application/pdf'


# ============================================================================
# _upload_raw
# ============================================================================

class TestUploadRaw:
    """Tests for _upload_raw with mocked boto3."""

    def test_upload_raw_success(self, service):
        """Successful S3 upload returns True."""
        mock_s3 = MagicMock()
        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            result = service._upload_raw('my-bucket', 'tenant/cat/file.jpg', b'data', 'image/jpeg')

        assert result is True
        mock_s3.put_object.assert_called_once_with(
            Bucket='my-bucket',
            Key='tenant/cat/file.jpg',
            Body=b'data',
            ContentType='image/jpeg',
        )

    def test_upload_raw_client_error(self, service):
        """S3 ClientError returns False."""
        from botocore.exceptions import ClientError
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Forbidden'}},
            'PutObject'
        )
        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            result = service._upload_raw('my-bucket', 'key', b'data', 'image/jpeg')

        assert result is False

    def test_upload_raw_unexpected_error(self, service):
        """Unexpected exception returns False."""
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = RuntimeError("network timeout")
        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            result = service._upload_raw('my-bucket', 'key', b'data', 'image/jpeg')

        assert result is False


# ============================================================================
# _delete_raw
# ============================================================================

class TestDeleteRaw:
    """Tests for _delete_raw with mocked boto3."""

    def test_delete_raw_success(self, service):
        """Successful S3 delete returns True."""
        mock_s3 = MagicMock()
        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            result = service._delete_raw('my-bucket', 'tenant/cat/file.jpg')

        assert result is True
        mock_s3.delete_object.assert_called_once_with(
            Bucket='my-bucket',
            Key='tenant/cat/file.jpg',
        )

    def test_delete_raw_client_error(self, service):
        """S3 ClientError returns False."""
        from botocore.exceptions import ClientError
        mock_s3 = MagicMock()
        mock_s3.delete_object.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Forbidden'}},
            'DeleteObject'
        )
        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            result = service._delete_raw('my-bucket', 'tenant/cat/file.jpg')

        assert result is False

    def test_delete_raw_unexpected_error(self, service):
        """Unexpected exception returns False."""
        mock_s3 = MagicMock()
        mock_s3.delete_object.side_effect = RuntimeError("connection reset")
        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            result = service._delete_raw('my-bucket', 'tenant/cat/file.jpg')

        assert result is False

    def test_delete_raw_calls_boto3_correctly(self, service):
        """Verifies boto3.client('s3') is called and delete_object uses correct params."""
        mock_s3 = MagicMock()
        with patch('services.media_asset_service.boto3.client', return_value=mock_s3) as mock_client:
            service._delete_raw('prod-bucket', 'TenantA/invoices/ast_123_doc.pdf')

        mock_client.assert_called_once_with('s3')
        mock_s3.delete_object.assert_called_once_with(
            Bucket='prod-bucket',
            Key='TenantA/invoices/ast_123_doc.pdf',
        )

    def test_delete_raw_logs_client_error(self, service):
        """ClientError is logged with bucket, key, and error details."""
        from botocore.exceptions import ClientError
        mock_s3 = MagicMock()
        mock_s3.delete_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchBucket', 'Message': 'Bucket not found'}},
            'DeleteObject'
        )
        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch('services.media_asset_service.logger') as mock_logger:
                service._delete_raw('missing-bucket', 'some/key.pdf')

        mock_logger.error.assert_called_once()
        log_args = mock_logger.error.call_args[0]
        assert 'missing-bucket' in log_args[1]
        assert 'some/key.pdf' in log_args[2]

    def test_delete_raw_logs_unexpected_error(self, service):
        """Unexpected errors are logged with bucket, key, and error details."""
        mock_s3 = MagicMock()
        mock_s3.delete_object.side_effect = OSError("disk failure")
        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch('services.media_asset_service.logger') as mock_logger:
                service._delete_raw('my-bucket', 'tenant/key.jpg')

        mock_logger.error.assert_called_once()
        log_args = mock_logger.error.call_args[0]
        assert 'my-bucket' in log_args[1]
        assert 'tenant/key.jpg' in log_args[2]


# ============================================================================
# _check_duplicate
# ============================================================================

class TestCheckDuplicate:
    """Tests for _check_duplicate."""

    def test_returns_duplicate_info_when_found(self, service, mock_db):
        """Returns dict with asset_id and original_filename when duplicate exists."""
        mock_db.execute_query.return_value = [
            {'id': 'ast_DUP001', 'original_filename': 'older_file.jpg'}
        ]

        result = service._check_duplicate('TenantA', 'ast_NEW001', 'abc123hash')

        assert result == {
            'asset_id': 'ast_DUP001',
            'original_filename': 'older_file.jpg',
        }
        # Verify query includes tenant isolation
        call_args = mock_db.execute_query.call_args
        assert 'administration = %s' in call_args[0][0]
        assert call_args[0][1][0] == 'TenantA'

    def test_returns_none_when_no_duplicate(self, service, mock_db):
        """Returns None when no duplicate found."""
        mock_db.execute_query.return_value = []

        result = service._check_duplicate('TenantA', 'ast_NEW001', 'unique_hash')

        assert result is None

    def test_returns_none_on_db_error(self, service, mock_db):
        """Returns None (non-blocking) when DB query fails."""
        mock_db.execute_query.side_effect = Exception("DB error")

        result = service._check_duplicate('TenantA', 'ast_NEW001', 'hash123')

        assert result is None


# ============================================================================
# attach
# ============================================================================

class TestAttach:
    """Tests for attach method: create reference from entity to asset."""

    @pytest.fixture
    def service_with_transaction(self, mock_db):
        """Service with mocked transaction context manager."""
        with patch('services.media_asset_service.ParameterService'):
            svc = MediaAssetService(mock_db)
        return svc

    def _setup_transaction(self, mock_db, asset_row):
        """Helper to set up mock transaction with a cursor that returns asset_row on fetchone."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_cursor.fetchone.return_value = asset_row
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        return mock_cursor, mock_conn

    # --- Happy path: attach to ACTIVE asset ---

    def test_attach_success_active_asset(self, service_with_transaction, mock_db):
        """AC 1, AC 2: Insert reference row and update updated_at."""
        mock_cursor, _ = self._setup_transaction(
            mock_db, {'id': 'ast_ABC123', 'status': 'ACTIVE'}
        )

        result = service_with_transaction.attach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        assert result['success'] is True
        assert result['asset_id'] == 'ast_ABC123'
        assert result['entity_type'] == 'invoice'
        assert result['entity_id'] == '12345'
        assert result['status'] == 'ACTIVE'
        assert result['updated_at'] is not None

    def test_attach_inserts_reference_row(self, service_with_transaction, mock_db):
        """AC 1: INSERT into s3_asset_references with correct params."""
        mock_cursor, _ = self._setup_transaction(
            mock_db, {'id': 'ast_ABC123', 'status': 'ACTIVE'}
        )

        service_with_transaction.attach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        # Second call is the INSERT into s3_asset_references
        insert_call = mock_cursor.execute.call_args_list[1]
        query = insert_call[0][0]
        params = insert_call[0][1]
        assert 's3_asset_references' in query
        assert 'INSERT' in query.upper()
        assert params[0] == 'TenantA'  # administration
        assert params[1] == 'ast_ABC123'  # asset_id
        assert params[2] == 'invoice'  # entity_type
        assert params[3] == '12345'  # entity_id

    def test_attach_updates_updated_at(self, service_with_transaction, mock_db):
        """AC 2: UPDATE s3_assets.updated_at on attach."""
        mock_cursor, _ = self._setup_transaction(
            mock_db, {'id': 'ast_ABC123', 'status': 'ACTIVE'}
        )

        service_with_transaction.attach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        # Third call is the UPDATE s3_assets SET updated_at
        update_call = mock_cursor.execute.call_args_list[2]
        query = update_call[0][0]
        params = update_call[0][1]
        assert 'updated_at' in query
        assert 'ast_ABC123' in params
        assert 'TenantA' in params

    # --- Orphan reactivation ---

    def test_attach_reverts_orphan_to_active(self, service_with_transaction, mock_db):
        """AC 3: ORPHAN asset becomes ACTIVE when attached."""
        mock_cursor, _ = self._setup_transaction(
            mock_db, {'id': 'ast_ORPHAN1', 'status': 'ORPHAN'}
        )

        result = service_with_transaction.attach(
            tenant='TenantA',
            asset_id='ast_ORPHAN1',
            entity_type='invoice',
            entity_id='999',
        )

        assert result['success'] is True
        assert result['status'] == 'ACTIVE'

    def test_attach_orphan_clears_orphaned_at(self, service_with_transaction, mock_db):
        """AC 3: Attaching to orphan clears orphaned_at and sets updated_at."""
        mock_cursor, _ = self._setup_transaction(
            mock_db, {'id': 'ast_ORPHAN1', 'status': 'ORPHAN'}
        )

        service_with_transaction.attach(
            tenant='TenantA',
            asset_id='ast_ORPHAN1',
            entity_type='invoice',
            entity_id='999',
        )

        # Third call is the UPDATE with status='ACTIVE', orphaned_at=NULL
        update_call = mock_cursor.execute.call_args_list[2]
        query = update_call[0][0]
        assert 'ACTIVE' in query
        assert 'orphaned_at = NULL' in query

    def test_attach_reverts_deletion_eligible_to_active(self, service_with_transaction, mock_db):
        """AC 3: DELETION_ELIGIBLE asset becomes ACTIVE when attached."""
        mock_cursor, _ = self._setup_transaction(
            mock_db, {'id': 'ast_DEL1', 'status': 'DELETION_ELIGIBLE'}
        )

        result = service_with_transaction.attach(
            tenant='TenantA',
            asset_id='ast_DEL1',
            entity_type='branding',
            entity_id='logo_v2',
        )

        assert result['success'] is True
        assert result['status'] == 'ACTIVE'

    # --- Asset not found ---

    def test_attach_asset_not_found(self, service_with_transaction, mock_db):
        """AC 4: Return error if asset_id doesn't exist."""
        mock_cursor, _ = self._setup_transaction(mock_db, None)

        result = service_with_transaction.attach(
            tenant='TenantA',
            asset_id='ast_NONEXISTENT',
            entity_type='invoice',
            entity_id='12345',
        )

        assert result['success'] is False
        assert 'not found' in result['error'].lower()

    def test_attach_asset_wrong_tenant(self, service_with_transaction, mock_db):
        """AC 5: Asset exists but belongs to different tenant (query returns None)."""
        mock_cursor, _ = self._setup_transaction(mock_db, None)

        result = service_with_transaction.attach(
            tenant='WrongTenant',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        assert result['success'] is False
        assert 'not found' in result['error'].lower()

    # --- Idempotency ---

    def test_attach_idempotent_duplicate_reference(self, service_with_transaction, mock_db):
        """AC 6: If reference already exists, return success without duplicate."""
        from db_exceptions import IntegrityError as DbIntegrityError

        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 'ast_ABC123', 'status': 'ACTIVE'}

        # First execute (SELECT) succeeds, second (INSERT) raises IntegrityError
        call_count = [0]
        original_execute = mock_cursor.execute

        def side_effect_execute(query, params=None):
            call_count[0] += 1
            if call_count[0] == 2:  # INSERT call
                raise DbIntegrityError("Duplicate entry", error_code=1062)
            return original_execute(query, params)

        mock_cursor.execute = MagicMock(side_effect=side_effect_execute)

        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        result = service_with_transaction.attach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        assert result['success'] is True
        assert result['asset_id'] == 'ast_ABC123'

    # --- Tenant isolation in queries ---

    def test_attach_select_includes_tenant(self, service_with_transaction, mock_db):
        """AC 5: SELECT query includes administration filter."""
        mock_cursor, _ = self._setup_transaction(
            mock_db, {'id': 'ast_ABC123', 'status': 'ACTIVE'}
        )

        service_with_transaction.attach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        # First call is the SELECT with administration filter
        select_call = mock_cursor.execute.call_args_list[0]
        query = select_call[0][0]
        params = select_call[0][1]
        assert 'administration = %s' in query
        assert 'TenantA' in params

    def test_attach_insert_includes_tenant(self, service_with_transaction, mock_db):
        """AC 5: INSERT includes administration column."""
        mock_cursor, _ = self._setup_transaction(
            mock_db, {'id': 'ast_ABC123', 'status': 'ACTIVE'}
        )

        service_with_transaction.attach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        # Second call is the INSERT
        insert_call = mock_cursor.execute.call_args_list[1]
        query = insert_call[0][0]
        assert 'administration' in query


# ============================================================================
# detach
# ============================================================================

class TestDetach:
    """Tests for detach method: remove reference, orphan if zero refs remain."""

    @pytest.fixture
    def service_with_transaction(self, mock_db):
        """Service with mocked transaction context manager."""
        with patch('services.media_asset_service.ParameterService'):
            svc = MediaAssetService(mock_db)
        return svc

    def _setup_transaction(self, mock_db, asset_row, rowcount=1, remaining_count=0):
        """Helper to set up mock transaction cursor.

        Args:
            asset_row: Return value for first fetchone (asset lookup).
            rowcount: Simulated rowcount after DELETE.
            remaining_count: Remaining reference count after delete.
        """
        mock_cursor = MagicMock()
        mock_conn = MagicMock()

        # fetchone returns: 1st call = asset row, 2nd call = count row
        mock_cursor.fetchone.side_effect = [
            asset_row,
            {'cnt': remaining_count},
        ]
        mock_cursor.rowcount = rowcount

        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        return mock_cursor, mock_conn

    # --- Happy path: detach last reference → ORPHAN ---

    def test_detach_last_reference_marks_orphan(self, service_with_transaction, mock_db):
        """AC 2: When last reference removed, status becomes ORPHAN."""
        self._setup_transaction(
            mock_db,
            asset_row={'id': 'ast_ABC123', 'status': 'ACTIVE'},
            rowcount=1,
            remaining_count=0,
        )

        result = service_with_transaction.detach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        assert result['success'] is True
        assert result['asset']['id'] == 'ast_ABC123'
        assert result['asset']['status'] == 'ORPHAN'
        assert result['asset']['reference_count'] == 0
        assert result['asset']['updated_at'] is not None

    def test_detach_last_reference_sets_orphaned_at(self, service_with_transaction, mock_db):
        """AC 2: orphaned_at is set to NOW() when last reference removed."""
        mock_cursor, _ = self._setup_transaction(
            mock_db,
            asset_row={'id': 'ast_ABC123', 'status': 'ACTIVE'},
            rowcount=1,
            remaining_count=0,
        )

        service_with_transaction.detach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        # Find the UPDATE call that sets ORPHAN
        update_calls = [
            call for call in mock_cursor.execute.call_args_list
            if 'ORPHAN' in str(call)
        ]
        assert len(update_calls) == 1
        query = update_calls[0][0][0]
        assert 'orphaned_at' in query
        assert 'ORPHAN' in query

    # --- Happy path: detach with remaining references → stays ACTIVE ---

    def test_detach_with_remaining_refs_stays_active(self, service_with_transaction, mock_db):
        """AC 3: While references exist after detach, keep status ACTIVE."""
        self._setup_transaction(
            mock_db,
            asset_row={'id': 'ast_ABC123', 'status': 'ACTIVE'},
            rowcount=1,
            remaining_count=2,
        )

        result = service_with_transaction.detach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        assert result['success'] is True
        assert result['asset']['status'] == 'ACTIVE'
        assert result['asset']['reference_count'] == 2

    def test_detach_with_one_remaining_ref(self, service_with_transaction, mock_db):
        """AC 3: One reference remaining keeps ACTIVE status."""
        self._setup_transaction(
            mock_db,
            asset_row={'id': 'ast_ABC123', 'status': 'ACTIVE'},
            rowcount=1,
            remaining_count=1,
        )

        result = service_with_transaction.detach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='999',
        )

        assert result['success'] is True
        assert result['asset']['status'] == 'ACTIVE'
        assert result['asset']['reference_count'] == 1

    # --- Return format: AC 1 ---

    def test_detach_returns_updated_asset_with_reference_count(self, service_with_transaction, mock_db):
        """AC 1: Return updated asset record including reference_count and status."""
        self._setup_transaction(
            mock_db,
            asset_row={'id': 'ast_XYZ789', 'status': 'ACTIVE'},
            rowcount=1,
            remaining_count=3,
        )

        result = service_with_transaction.detach(
            tenant='TenantA',
            asset_id='ast_XYZ789',
            entity_type='branding',
            entity_id='logo_v1',
        )

        assert result['success'] is True
        asset = result['asset']
        assert 'id' in asset
        assert 'status' in asset
        assert 'reference_count' in asset
        assert 'updated_at' in asset
        assert asset['id'] == 'ast_XYZ789'
        assert asset['reference_count'] == 3

    # --- Error: asset not found ---

    def test_detach_asset_not_found(self, service_with_transaction, mock_db):
        """AC 5: Return error if asset_id doesn't exist."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        result = service_with_transaction.detach(
            tenant='TenantA',
            asset_id='ast_NONEXISTENT',
            entity_type='invoice',
            entity_id='12345',
        )

        assert result['success'] is False
        assert 'not found' in result['error'].lower()

    def test_detach_asset_wrong_tenant(self, service_with_transaction, mock_db):
        """AC 4: Asset belonging to different tenant returns not found."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_cursor.fetchone.return_value = None  # query scoped to wrong tenant
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        result = service_with_transaction.detach(
            tenant='WrongTenant',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        assert result['success'] is False
        assert 'not found' in result['error'].lower()

    # --- Error: reference not found ---

    def test_detach_reference_not_found(self, service_with_transaction, mock_db):
        """AC 5: Return error if reference entry doesn't match."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 'ast_ABC123', 'status': 'ACTIVE'}
        mock_cursor.rowcount = 0  # DELETE affected 0 rows
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        result = service_with_transaction.detach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='WRONG_ID',
        )

        assert result['success'] is False
        assert 'reference not found' in result['error'].lower()

    # --- Tenant isolation in queries ---

    def test_detach_select_includes_tenant(self, service_with_transaction, mock_db):
        """AC 4: SELECT query includes administration filter."""
        mock_cursor, _ = self._setup_transaction(
            mock_db,
            asset_row={'id': 'ast_ABC123', 'status': 'ACTIVE'},
            rowcount=1,
            remaining_count=0,
        )

        service_with_transaction.detach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        select_call = mock_cursor.execute.call_args_list[0]
        query = select_call[0][0]
        params = select_call[0][1]
        assert 'administration = %s' in query
        assert 'TenantA' in params

    def test_detach_delete_includes_tenant(self, service_with_transaction, mock_db):
        """AC 4: DELETE query includes administration filter."""
        mock_cursor, _ = self._setup_transaction(
            mock_db,
            asset_row={'id': 'ast_ABC123', 'status': 'ACTIVE'},
            rowcount=1,
            remaining_count=0,
        )

        service_with_transaction.detach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        delete_call = mock_cursor.execute.call_args_list[1]
        query = delete_call[0][0]
        params = delete_call[0][1]
        assert 'DELETE' in query.upper()
        assert 'administration = %s' in query
        assert 'TenantA' in params

    def test_detach_count_includes_tenant(self, service_with_transaction, mock_db):
        """AC 4: COUNT query includes administration filter."""
        mock_cursor, _ = self._setup_transaction(
            mock_db,
            asset_row={'id': 'ast_ABC123', 'status': 'ACTIVE'},
            rowcount=1,
            remaining_count=0,
        )

        service_with_transaction.detach(
            tenant='TenantA',
            asset_id='ast_ABC123',
            entity_type='invoice',
            entity_id='12345',
        )

        count_call = mock_cursor.execute.call_args_list[2]
        query = count_call[0][0]
        params = count_call[0][1]
        assert 'COUNT' in query.upper()
        assert 'administration = %s' in query
        assert 'TenantA' in params


# ============================================================================
# replace
# ============================================================================

class TestReplace:
    """Tests for replace method: atomically detach old + attach new (Req 2)."""

    @pytest.fixture
    def service_with_transaction(self, mock_db):
        """Service with mocked transaction context manager."""
        with patch('services.media_asset_service.ParameterService'):
            svc = MediaAssetService(mock_db)
        return svc

    def _setup_transaction(self, mock_db, fetchone_returns):
        """Helper to set up mock transaction with sequential fetchone returns.

        Args:
            fetchone_returns: List of values for sequential fetchone calls.
                Typical order:
                1. old reference lookup (dict or None)
                2. new asset lookup (dict or None)
                3. old asset remaining ref count (dict with 'cnt')
        """
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_cursor.fetchone.side_effect = fetchone_returns
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        return mock_cursor, mock_conn

    # --- AC 7: Atomic detach old + attach new ---

    def test_replace_success_basic(self, service_with_transaction, mock_db):
        """AC 7: Atomically detach old, attach new, return success."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 1},                              # old ref exists
            {'id': 'ast_NEW001', 'status': 'ACTIVE'},  # new asset exists
            {'cnt': 0},                             # old asset has 0 refs remaining
        ])

        result = service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id='ast_OLD001',
            new_asset_id='ast_NEW001',
        )

        assert result['success'] is True
        assert result['old_asset']['id'] == 'ast_OLD001'
        assert result['new_asset']['id'] == 'ast_NEW001'
        assert result['new_asset']['entity_type'] == 'invoice'
        assert result['new_asset']['entity_id'] == '12345'
        assert result['updated_at'] is not None

    def test_replace_deletes_old_reference(self, service_with_transaction, mock_db):
        """AC 7: DELETE old reference row within the transaction."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 1},
            {'id': 'ast_NEW001', 'status': 'ACTIVE'},
            {'cnt': 0},
        ])

        service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id='ast_OLD001',
            new_asset_id='ast_NEW001',
        )

        # Find the DELETE call for old reference
        delete_calls = [
            call for call in mock_cursor.execute.call_args_list
            if 'DELETE' in str(call[0][0]).upper()
        ]
        assert len(delete_calls) == 1
        query = delete_calls[0][0][0]
        params = delete_calls[0][0][1]
        assert 'ast_OLD001' in params
        assert 'invoice' in params
        assert '12345' in params
        assert 'administration = %s' in query

    def test_replace_inserts_new_reference(self, service_with_transaction, mock_db):
        """AC 7: INSERT new reference row within the transaction."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 1},
            {'id': 'ast_NEW001', 'status': 'ACTIVE'},
            {'cnt': 0},
        ])

        service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id='ast_OLD001',
            new_asset_id='ast_NEW001',
        )

        # Find the INSERT call
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list
            if 'INSERT' in str(call[0][0]).upper()
        ]
        assert len(insert_calls) == 1
        query = insert_calls[0][0][0]
        params = insert_calls[0][0][1]
        assert 'TenantA' in params
        assert 'ast_NEW001' in params
        assert 'invoice' in params
        assert '12345' in params

    def test_replace_uses_single_transaction(self, service_with_transaction, mock_db):
        """AC 7: All operations happen within one db.transaction() call."""
        self._setup_transaction(mock_db, [
            {'id': 1},
            {'id': 'ast_NEW001', 'status': 'ACTIVE'},
            {'cnt': 0},
        ])

        service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id='ast_OLD001',
            new_asset_id='ast_NEW001',
        )

        # transaction() should be called exactly once
        mock_db.transaction.assert_called_once()

    # --- AC 8: Rollback on failure ---

    def test_replace_rollback_on_exception(self, service_with_transaction, mock_db):
        """AC 8: If exception occurs within transaction, context manager handles rollback."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()

        # First fetchone succeeds (old ref found), then raise on second call
        mock_cursor.fetchone.side_effect = [
            {'id': 1},
            Exception("DB connection lost"),
        ]

        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(Exception, match="DB connection lost"):
            service_with_transaction.replace(
                tenant='TenantA',
                entity_type='invoice',
                entity_id='12345',
                old_asset_id='ast_OLD001',
                new_asset_id='ast_NEW001',
            )

    # --- AC 9: Null/empty old_asset_id → simple attach ---

    def test_replace_null_old_asset_delegates_to_attach(self, service_with_transaction, mock_db):
        """AC 9: When old_asset_id is None, treat as simple attach."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 'ast_NEW001', 'status': 'ACTIVE'}
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        result = service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id=None,
            new_asset_id='ast_NEW001',
        )

        assert result['success'] is True
        assert result['asset_id'] == 'ast_NEW001'

    def test_replace_empty_string_old_asset_delegates_to_attach(self, service_with_transaction, mock_db):
        """AC 9: When old_asset_id is empty string, treat as simple attach."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 'ast_NEW001', 'status': 'ACTIVE'}
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        result = service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id='',
            new_asset_id='ast_NEW001',
        )

        assert result['success'] is True
        assert result['asset_id'] == 'ast_NEW001'

    # --- AC 10: Old reference not found → error, do NOT attach new ---

    def test_replace_old_ref_not_found_returns_error(self, service_with_transaction, mock_db):
        """AC 10: If old_asset_id has no matching reference, return error."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            None,  # old ref not found
        ])

        result = service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id='ast_NONEXIST',
            new_asset_id='ast_NEW001',
        )

        assert result['success'] is False
        assert 'No reference found' in result['error']
        assert 'ast_NONEXIST' in result['error']

    def test_replace_old_ref_not_found_does_not_attach_new(self, service_with_transaction, mock_db):
        """AC 10: When old ref not found, do NOT insert new reference."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            None,  # old ref not found
        ])

        service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id='ast_NONEXIST',
            new_asset_id='ast_NEW001',
        )

        # No INSERT should have been called
        insert_calls = [
            call for call in mock_cursor.execute.call_args_list
            if 'INSERT' in str(call[0][0]).upper()
        ]
        assert len(insert_calls) == 0

    # --- New asset not found → error ---

    def test_replace_new_asset_not_found_returns_error(self, service_with_transaction, mock_db):
        """Return error if new_asset_id doesn't exist in s3_assets."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 1},  # old ref exists
            None,       # new asset not found
        ])

        result = service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id='ast_OLD001',
            new_asset_id='ast_NONEXIST',
        )

        assert result['success'] is False
        assert 'not found' in result['error'].lower()
        assert 'ast_NONEXIST' in result['error']

    # --- Old asset becomes ORPHAN when zero refs remain ---

    def test_replace_old_asset_becomes_orphan(self, service_with_transaction, mock_db):
        """Old asset with zero remaining refs is marked ORPHAN."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 1},
            {'id': 'ast_NEW001', 'status': 'ACTIVE'},
            {'cnt': 0},  # zero remaining refs for old asset
        ])

        result = service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id='ast_OLD001',
            new_asset_id='ast_NEW001',
        )

        assert result['old_asset']['status'] == 'ORPHAN'
        assert result['old_asset']['reference_count'] == 0

        # Verify ORPHAN update was executed
        orphan_calls = [
            call for call in mock_cursor.execute.call_args_list
            if 'ORPHAN' in str(call[0][0])
        ]
        assert len(orphan_calls) == 1

    def test_replace_old_asset_stays_active_with_refs(self, service_with_transaction, mock_db):
        """Old asset with remaining refs keeps ACTIVE status."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 1},
            {'id': 'ast_NEW001', 'status': 'ACTIVE'},
            {'cnt': 2},  # 2 remaining refs for old asset
        ])

        result = service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id='ast_OLD001',
            new_asset_id='ast_NEW001',
        )

        assert result['old_asset']['status'] == 'ACTIVE'
        assert result['old_asset']['reference_count'] == 2

    # --- New asset reactivation ---

    def test_replace_new_orphan_asset_reverts_to_active(self, service_with_transaction, mock_db):
        """New asset that was ORPHAN reverts to ACTIVE on attach."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 1},
            {'id': 'ast_NEW001', 'status': 'ORPHAN'},
            {'cnt': 0},
        ])

        result = service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id='ast_OLD001',
            new_asset_id='ast_NEW001',
        )

        assert result['new_asset']['status'] == 'ACTIVE'

        # Verify reactivation update
        reactivate_calls = [
            call for call in mock_cursor.execute.call_args_list
            if "status = 'ACTIVE'" in str(call[0][0]) and 'orphaned_at = NULL' in str(call[0][0])
        ]
        assert len(reactivate_calls) == 1

    def test_replace_new_deletion_eligible_reverts_to_active(self, service_with_transaction, mock_db):
        """New asset that was DELETION_ELIGIBLE reverts to ACTIVE on attach."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 1},
            {'id': 'ast_NEW001', 'status': 'DELETION_ELIGIBLE'},
            {'cnt': 0},
        ])

        result = service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id='ast_OLD001',
            new_asset_id='ast_NEW001',
        )

        assert result['new_asset']['status'] == 'ACTIVE'

    # --- Tenant isolation ---

    def test_replace_all_queries_include_tenant(self, service_with_transaction, mock_db):
        """All queries within replace use administration = %s for tenant isolation."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 1},
            {'id': 'ast_NEW001', 'status': 'ACTIVE'},
            {'cnt': 0},
        ])

        service_with_transaction.replace(
            tenant='TenantA',
            entity_type='invoice',
            entity_id='12345',
            old_asset_id='ast_OLD001',
            new_asset_id='ast_NEW001',
        )

        # Every execute call should have 'administration = %s' or include tenant
        for call in mock_cursor.execute.call_args_list:
            query = call[0][0]
            params = call[0][1]
            assert 'administration' in query.lower() or '%s' in query
            assert 'TenantA' in params


# ============================================================================
# _get_presigned_url
# ============================================================================

class TestGetPresignedUrl:
    """Tests for _get_presigned_url: presigned URL generation with caching."""

    @pytest.fixture
    def service_for_presigned(self, mock_db):
        """Service with a clean presigned cache."""
        with patch('services.media_asset_service.ParameterService'):
            svc = MediaAssetService(mock_db)
        return svc

    @pytest.fixture
    def sample_asset(self):
        """A sample asset dict for presigned URL generation."""
        return {
            'id': 'ast_TEST001',
            'bucket': 'test-bucket',
            's3_key': 'TenantA/invoices/ast_TEST001_report.pdf',
        }

    def test_generates_presigned_url(self, service_for_presigned, sample_asset):
        """Generates a new presigned URL when cache is empty."""
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/presigned-url'

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            url = service_for_presigned._get_presigned_url(sample_asset)

        assert url == 'https://s3.amazonaws.com/presigned-url'
        mock_s3.generate_presigned_url.assert_called_once_with(
            'get_object',
            Params={'Bucket': 'test-bucket', 'Key': 'TenantA/invoices/ast_TEST001_report.pdf'},
            ExpiresIn=3600,
        )

    def test_returns_cached_url_when_fresh(self, service_for_presigned, sample_asset):
        """Returns cached URL without calling S3 when cache entry is still fresh."""
        from datetime import datetime, timedelta, timezone

        # Pre-populate cache with a fresh entry (expires in 55 min → 45 min until safety margin)
        fresh_url = 'https://s3.amazonaws.com/cached-url'
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=55)
        service_for_presigned._presigned_cache['ast_TEST001'] = (fresh_url, expires_at)

        mock_s3 = MagicMock()
        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            url = service_for_presigned._get_presigned_url(sample_asset)

        assert url == fresh_url
        mock_s3.generate_presigned_url.assert_not_called()

    def test_regenerates_url_when_cache_near_expiry(self, service_for_presigned, sample_asset):
        """Regenerates URL when cached entry is within 10 minutes of expiry."""
        from datetime import datetime, timedelta, timezone

        # Pre-populate cache with entry expiring in 8 minutes (within 10-min safety margin)
        old_url = 'https://s3.amazonaws.com/old-url'
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=8)
        service_for_presigned._presigned_cache['ast_TEST001'] = (old_url, expires_at)

        mock_s3 = MagicMock()
        new_url = 'https://s3.amazonaws.com/new-url'
        mock_s3.generate_presigned_url.return_value = new_url

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            url = service_for_presigned._get_presigned_url(sample_asset)

        assert url == new_url
        mock_s3.generate_presigned_url.assert_called_once()

    def test_regenerates_url_when_cache_expired(self, service_for_presigned, sample_asset):
        """Regenerates URL when cached entry has already expired."""
        from datetime import datetime, timedelta, timezone

        # Pre-populate cache with expired entry
        old_url = 'https://s3.amazonaws.com/expired-url'
        expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        service_for_presigned._presigned_cache['ast_TEST001'] = (old_url, expires_at)

        mock_s3 = MagicMock()
        new_url = 'https://s3.amazonaws.com/fresh-url'
        mock_s3.generate_presigned_url.return_value = new_url

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            url = service_for_presigned._get_presigned_url(sample_asset)

        assert url == new_url

    def test_stores_url_in_cache_after_generation(self, service_for_presigned, sample_asset):
        """After generating, the URL is stored in the cache."""
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/new'

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            service_for_presigned._get_presigned_url(sample_asset)

        assert 'ast_TEST001' in service_for_presigned._presigned_cache
        cached_url, cached_expires = service_for_presigned._presigned_cache['ast_TEST001']
        assert cached_url == 'https://s3.amazonaws.com/new'
        # Expiry should be ~60 minutes from now
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        assert cached_expires > now + timedelta(minutes=59)
        assert cached_expires < now + timedelta(minutes=61)

    def test_custom_ttl(self, service_for_presigned, sample_asset):
        """Respects custom TTL parameter for presigned URL."""
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = 'https://s3.amazonaws.com/custom-ttl'

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            url = service_for_presigned._get_presigned_url(sample_asset, ttl=1800)

        mock_s3.generate_presigned_url.assert_called_once_with(
            'get_object',
            Params={'Bucket': 'test-bucket', 'Key': 'TenantA/invoices/ast_TEST001_report.pdf'},
            ExpiresIn=1800,
        )

    def test_different_assets_cached_independently(self, service_for_presigned):
        """Each asset_id has its own cache entry."""
        asset_a = {'id': 'ast_A', 'bucket': 'b', 's3_key': 'key_a'}
        asset_b = {'id': 'ast_B', 'bucket': 'b', 's3_key': 'key_b'}

        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.side_effect = [
            'https://url-a', 'https://url-b'
        ]

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            url_a = service_for_presigned._get_presigned_url(asset_a)
            url_b = service_for_presigned._get_presigned_url(asset_b)

        assert url_a == 'https://url-a'
        assert url_b == 'https://url-b'
        assert 'ast_A' in service_for_presigned._presigned_cache
        assert 'ast_B' in service_for_presigned._presigned_cache


# ============================================================================
# get_asset
# ============================================================================

class TestGetAsset:
    """Tests for get_asset: retrieve metadata + presigned URL + references."""

    @pytest.fixture
    def service_for_get(self, mock_db):
        """Service with mocked dependencies."""
        with patch('services.media_asset_service.ParameterService'):
            svc = MediaAssetService(mock_db)
        return svc

    @pytest.fixture
    def sample_asset_row(self):
        """A sample asset row as returned from the database."""
        return {
            'id': 'ast_GET001',
            'bucket': 'test-bucket',
            's3_key': 'TenantA/invoices/ast_GET001_invoice.pdf',
            'mime_type': 'application/pdf',
            'file_size': 245000,
            'category': 'invoices',
            'media_type': 'document',
            'original_filename': 'invoice.pdf',
            'status': 'ACTIVE',
            'created_at': '2025-03-15 10:30:00',
        }

    @pytest.fixture
    def sample_references(self):
        """Sample references for the asset."""
        return [
            {'entity_type': 'invoice', 'entity_id': '12345', 'created_at': '2025-03-15 10:30:00'},
            {'entity_type': 'invoice', 'entity_id': '67890', 'created_at': '2025-03-16 11:00:00'},
        ]

    # --- Happy path ---

    def test_get_asset_success(self, service_for_get, mock_db, sample_asset_row, sample_references):
        """AC 1: Returns asset metadata, presigned URL, and references."""
        mock_db.execute_query.side_effect = [
            [sample_asset_row],   # asset query
            sample_references,    # references query
        ]

        with patch.object(service_for_get, '_get_presigned_url', return_value='https://presigned-url'):
            result = service_for_get.get_asset('TenantA', 'ast_GET001')

        assert result['success'] is True
        asset = result['asset']
        assert asset['id'] == 'ast_GET001'
        assert asset['s3_key'] == 'TenantA/invoices/ast_GET001_invoice.pdf'
        assert asset['mime_type'] == 'application/pdf'
        assert asset['file_size'] == 245000
        assert asset['category'] == 'invoices'
        assert asset['media_type'] == 'document'
        assert asset['original_filename'] == 'invoice.pdf'
        assert asset['status'] == 'ACTIVE'
        assert asset['created_at'] == '2025-03-15 10:30:00'
        assert asset['presigned_url'] == 'https://presigned-url'
        assert asset['references'] == sample_references

    def test_get_asset_returns_all_metadata_fields(self, service_for_get, mock_db, sample_asset_row):
        """AC 1: All required metadata fields are present in response."""
        mock_db.execute_query.side_effect = [[sample_asset_row], []]

        with patch.object(service_for_get, '_get_presigned_url', return_value='https://url'):
            result = service_for_get.get_asset('TenantA', 'ast_GET001')

        asset = result['asset']
        required_fields = [
            'id', 's3_key', 'mime_type', 'file_size', 'category',
            'media_type', 'original_filename', 'status', 'created_at',
            'presigned_url', 'references',
        ]
        for field in required_fields:
            assert field in asset, f"Missing field: {field}"

    def test_get_asset_includes_presigned_url(self, service_for_get, mock_db, sample_asset_row):
        """AC 2: Response includes a presigned S3 URL."""
        mock_db.execute_query.side_effect = [[sample_asset_row], []]

        with patch.object(service_for_get, '_get_presigned_url', return_value='https://s3.presigned/url'):
            result = service_for_get.get_asset('TenantA', 'ast_GET001')

        assert result['asset']['presigned_url'] == 'https://s3.presigned/url'

    def test_get_asset_calls_presigned_url_with_asset(self, service_for_get, mock_db, sample_asset_row):
        """AC 2: _get_presigned_url is called with the asset dict."""
        mock_db.execute_query.side_effect = [[sample_asset_row], []]

        with patch.object(service_for_get, '_get_presigned_url', return_value='https://url') as mock_presigned:
            service_for_get.get_asset('TenantA', 'ast_GET001')

        mock_presigned.assert_called_once_with(sample_asset_row)

    # --- Tenant isolation ---

    def test_get_asset_scoped_to_tenant(self, service_for_get, mock_db, sample_asset_row):
        """AC 3: Asset query includes administration = %s."""
        mock_db.execute_query.side_effect = [[sample_asset_row], []]

        with patch.object(service_for_get, '_get_presigned_url', return_value='https://url'):
            service_for_get.get_asset('TenantA', 'ast_GET001')

        # First call is asset query
        asset_call = mock_db.execute_query.call_args_list[0]
        query = asset_call[0][0]
        params = asset_call[0][1]
        assert 'administration = %s' in query
        assert params == ('ast_GET001', 'TenantA')

    def test_get_asset_references_scoped_to_tenant(self, service_for_get, mock_db, sample_asset_row):
        """AC 3: References query also includes administration = %s."""
        mock_db.execute_query.side_effect = [[sample_asset_row], []]

        with patch.object(service_for_get, '_get_presigned_url', return_value='https://url'):
            service_for_get.get_asset('TenantA', 'ast_GET001')

        # Second call is references query
        refs_call = mock_db.execute_query.call_args_list[1]
        query = refs_call[0][0]
        params = refs_call[0][1]
        assert 'administration = %s' in query
        assert params == ('ast_GET001', 'TenantA')

    def test_get_asset_different_tenant_returns_not_found(self, service_for_get, mock_db):
        """AC 4: Asset belonging to different tenant returns not-found without revealing existence."""
        mock_db.execute_query.side_effect = [[]]  # query with wrong tenant returns empty

        result = service_for_get.get_asset('WrongTenant', 'ast_GET001')

        assert result['success'] is False
        assert 'not found' in result['error'].lower()

    # --- Asset not found ---

    def test_get_asset_nonexistent_returns_not_found(self, service_for_get, mock_db):
        """AC 5: If asset_id doesn't exist, return not-found."""
        mock_db.execute_query.side_effect = [[]]  # no results

        result = service_for_get.get_asset('TenantA', 'ast_NONEXISTENT')

        assert result['success'] is False
        assert 'not found' in result['error'].lower()

    # --- ORPHAN assets still retrievable ---

    def test_get_asset_orphan_still_returned(self, service_for_get, mock_db):
        """AC 6: ORPHAN assets are still retrievable."""
        orphan_asset = {
            'id': 'ast_ORPHAN001',
            'bucket': 'test-bucket',
            's3_key': 'TenantA/branding/ast_ORPHAN001_logo.png',
            'mime_type': 'image/png',
            'file_size': 50000,
            'category': 'branding',
            'media_type': 'image',
            'original_filename': 'logo.png',
            'status': 'ORPHAN',
            'created_at': '2025-01-10 08:00:00',
        }
        mock_db.execute_query.side_effect = [[orphan_asset], []]

        with patch.object(service_for_get, '_get_presigned_url', return_value='https://orphan-url'):
            result = service_for_get.get_asset('TenantA', 'ast_ORPHAN001')

        assert result['success'] is True
        assert result['asset']['status'] == 'ORPHAN'
        assert result['asset']['presigned_url'] == 'https://orphan-url'

    def test_get_asset_deletion_eligible_still_returned(self, service_for_get, mock_db):
        """AC 6: DELETION_ELIGIBLE assets are still retrievable until permanently deleted."""
        del_asset = {
            'id': 'ast_DEL001',
            'bucket': 'test-bucket',
            's3_key': 'TenantA/invoices/ast_DEL001_old.pdf',
            'mime_type': 'application/pdf',
            'file_size': 100000,
            'category': 'invoices',
            'media_type': 'document',
            'original_filename': 'old.pdf',
            'status': 'DELETION_ELIGIBLE',
            'created_at': '2024-06-01 12:00:00',
        }
        mock_db.execute_query.side_effect = [[del_asset], []]

        with patch.object(service_for_get, '_get_presigned_url', return_value='https://del-url'):
            result = service_for_get.get_asset('TenantA', 'ast_DEL001')

        assert result['success'] is True
        assert result['asset']['status'] == 'DELETION_ELIGIBLE'

    # --- References ---

    def test_get_asset_with_no_references(self, service_for_get, mock_db, sample_asset_row):
        """Asset with no references returns empty list."""
        mock_db.execute_query.side_effect = [[sample_asset_row], []]

        with patch.object(service_for_get, '_get_presigned_url', return_value='https://url'):
            result = service_for_get.get_asset('TenantA', 'ast_GET001')

        assert result['asset']['references'] == []

    def test_get_asset_with_multiple_references(self, service_for_get, mock_db, sample_asset_row, sample_references):
        """Asset with multiple references returns all of them."""
        mock_db.execute_query.side_effect = [[sample_asset_row], sample_references]

        with patch.object(service_for_get, '_get_presigned_url', return_value='https://url'):
            result = service_for_get.get_asset('TenantA', 'ast_GET001')

        assert len(result['asset']['references']) == 2
        assert result['asset']['references'][0]['entity_type'] == 'invoice'
        assert result['asset']['references'][0]['entity_id'] == '12345'
        assert result['asset']['references'][1]['entity_id'] == '67890'


# ============================================================================
# _get_retention_days
# ============================================================================

class TestGetRetentionDays:
    """Tests for _get_retention_days: resolution order and category/media_type mapping."""

    @pytest.fixture
    def service_with_ps(self, mock_db):
        """Service with a mocked ParameterService."""
        mock_ps = MagicMock()
        with patch('services.media_asset_service.ParameterService', return_value=mock_ps):
            svc = MediaAssetService(mock_db, parameter_service=mock_ps)
        return svc

    # --- Category → key mapping ---

    def test_invoices_maps_to_invoices_days(self, service_with_ps):
        """Invoices category resolves to 'invoices_days' key."""
        service_with_ps.ps.get_param.return_value = 2555
        result = service_with_ps._get_retention_days('TenantA', 'invoices', 'document')
        service_with_ps.ps.get_param.assert_called_once_with(
            'asset_retention', 'invoices_days', tenant='TenantA'
        )
        assert result == 2555

    def test_branding_maps_to_branding_days(self, service_with_ps):
        """Branding category resolves to 'branding_days' key."""
        service_with_ps.ps.get_param.return_value = 30
        result = service_with_ps._get_retention_days('TenantA', 'branding', 'image')
        service_with_ps.ps.get_param.assert_called_once_with(
            'asset_retention', 'branding_days', tenant='TenantA'
        )
        assert result == 30

    def test_templates_maps_to_templates_days(self, service_with_ps):
        """Templates category resolves to 'templates_days' key."""
        service_with_ps.ps.get_param.return_value = 90
        result = service_with_ps._get_retention_days('TenantA', 'templates', 'web_content')
        service_with_ps.ps.get_param.assert_called_once_with(
            'asset_retention', 'templates_days', tenant='TenantA'
        )
        assert result == 90

    # --- Landing pages: media_type dispatch ---

    def test_landing_pages_image_uses_media_days(self, service_with_ps):
        """Landing-pages + image → 'landing_pages_media_days'."""
        service_with_ps.ps.get_param.return_value = 30
        result = service_with_ps._get_retention_days('TenantA', 'landing-pages', 'image')
        service_with_ps.ps.get_param.assert_called_once_with(
            'asset_retention', 'landing_pages_media_days', tenant='TenantA'
        )
        assert result == 30

    def test_landing_pages_video_uses_media_days(self, service_with_ps):
        """Landing-pages + video → 'landing_pages_media_days'."""
        service_with_ps.ps.get_param.return_value = 30
        result = service_with_ps._get_retention_days('TenantA', 'landing-pages', 'video')
        service_with_ps.ps.get_param.assert_called_once_with(
            'asset_retention', 'landing_pages_media_days', tenant='TenantA'
        )
        assert result == 30

    def test_landing_pages_web_content_uses_pages_days(self, service_with_ps):
        """Landing-pages + web_content → 'landing_pages_days'."""
        service_with_ps.ps.get_param.return_value = 7
        result = service_with_ps._get_retention_days('TenantA', 'landing-pages', 'web_content')
        service_with_ps.ps.get_param.assert_called_once_with(
            'asset_retention', 'landing_pages_days', tenant='TenantA'
        )
        assert result == 7

    def test_landing_pages_document_uses_pages_days(self, service_with_ps):
        """Landing-pages + document → 'landing_pages_days'."""
        service_with_ps.ps.get_param.return_value = 7
        result = service_with_ps._get_retention_days('TenantA', 'landing-pages', 'document')
        service_with_ps.ps.get_param.assert_called_once_with(
            'asset_retention', 'landing_pages_days', tenant='TenantA'
        )
        assert result == 7

    # --- Tenant override takes precedence ---

    def test_tenant_override_returned(self, service_with_ps):
        """Tenant-level override (e.g., 60) is returned instead of system default."""
        service_with_ps.ps.get_param.return_value = 60
        result = service_with_ps._get_retention_days('CustomTenant', 'branding', 'image')
        assert result == 60

    # --- Fallback when get_param returns None ---

    def test_fallback_when_param_is_none(self, service_with_ps):
        """If get_param returns None (shouldn't normally happen), returns 30 as defensive default."""
        service_with_ps.ps.get_param.return_value = None
        result = service_with_ps._get_retention_days('TenantA', 'branding', 'image')
        assert result == 30

    # --- Value is coerced to int ---

    def test_string_value_coerced_to_int(self, service_with_ps):
        """String numeric values (from DB JSON) are coerced to int."""
        service_with_ps.ps.get_param.return_value = "365"
        result = service_with_ps._get_retention_days('TenantA', 'invoices', 'document')
        assert result == 365
        assert isinstance(result, int)


# ============================================================================
# _retention_param_key (static helper)
# ============================================================================

class TestRetentionParamKey:
    """Tests for the static _retention_param_key mapping method."""

    def test_invoices(self):
        assert MediaAssetService._retention_param_key('invoices', 'document') == 'invoices_days'

    def test_branding(self):
        assert MediaAssetService._retention_param_key('branding', 'image') == 'branding_days'

    def test_templates(self):
        assert MediaAssetService._retention_param_key('templates', 'web_content') == 'templates_days'

    def test_landing_pages_image(self):
        assert MediaAssetService._retention_param_key('landing-pages', 'image') == 'landing_pages_media_days'

    def test_landing_pages_video(self):
        assert MediaAssetService._retention_param_key('landing-pages', 'video') == 'landing_pages_media_days'

    def test_landing_pages_web_content(self):
        assert MediaAssetService._retention_param_key('landing-pages', 'web_content') == 'landing_pages_days'

    def test_landing_pages_document(self):
        assert MediaAssetService._retention_param_key('landing-pages', 'document') == 'landing_pages_days'


# ============================================================================
# transition_eligible
# ============================================================================

class TestTransitionEligible:
    """Tests for the transition_eligible lifecycle method (Req 5, AC 2)."""

    @pytest.fixture
    def service_with_ps(self, mock_db):
        """Service with a mocked ParameterService."""
        with patch('services.media_asset_service.ParameterService') as MockPS:
            mock_ps = MagicMock()
            MockPS.return_value = mock_ps
            svc = MediaAssetService(mock_db, mock_ps)
            return svc

    def test_returns_success_with_zero_when_no_orphans(self, service_with_ps, mock_db):
        """No orphans past retention → transitioned = 0."""
        mock_db.execute_query.return_value = 0
        service_with_ps.ps.get_param.return_value = 30

        result = service_with_ps.transition_eligible('TenantA')

        assert result == {'success': True, 'transitioned': 0}

    def test_sums_transitioned_across_categories(self, service_with_ps, mock_db):
        """Counts from all category UPDATEs are summed."""
        # invoices=2, branding=1, templates=0,
        # landing-pages web_content=3, landing-pages media=1
        mock_db.execute_query.side_effect = [2, 1, 0, 3, 1]
        service_with_ps.ps.get_param.return_value = 30

        result = service_with_ps.transition_eligible('TenantA')

        assert result == {'success': True, 'transitioned': 7}

    def test_uses_tenant_retention_for_each_category(self, service_with_ps, mock_db):
        """Each category resolves its own retention via ParameterService."""
        mock_db.execute_query.return_value = 0

        # Return different values per key
        def param_resolver(namespace, key, tenant=None):
            values = {
                'invoices_days': 2555,
                'branding_days': 30,
                'templates_days': 90,
                'landing_pages_days': 7,
                'landing_pages_media_days': 30,
            }
            return values.get(key, 30)

        service_with_ps.ps.get_param.side_effect = param_resolver

        service_with_ps.transition_eligible('TenantA')

        # 5 execute_query calls: invoices, branding, templates, LP web, LP media
        assert mock_db.execute_query.call_count == 5

        # Verify retention values passed in queries
        calls = mock_db.execute_query.call_args_list

        # invoices: (tenant, category, retention)
        assert calls[0][0][1] == ('TenantA', 'invoices', 2555)
        # branding
        assert calls[1][0][1] == ('TenantA', 'branding', 30)
        # templates
        assert calls[2][0][1] == ('TenantA', 'templates', 90)
        # landing-pages web_content
        assert calls[3][0][1] == ('TenantA', 'landing-pages', 7)
        # landing-pages media
        assert calls[4][0][1] == ('TenantA', 'landing-pages', 30)

    def test_tenant_isolation_in_queries(self, service_with_ps, mock_db):
        """Every UPDATE includes administration = tenant for isolation."""
        mock_db.execute_query.return_value = 0
        service_with_ps.ps.get_param.return_value = 30

        service_with_ps.transition_eligible('SpecificTenant')

        for call in mock_db.execute_query.call_args_list:
            query = call[0][0]
            params = call[0][1]
            assert 'administration = %s' in query
            assert params[0] == 'SpecificTenant'

    def test_only_transitions_orphan_status(self, service_with_ps, mock_db):
        """Query only targets assets with status = ORPHAN."""
        mock_db.execute_query.return_value = 0
        service_with_ps.ps.get_param.return_value = 30

        service_with_ps.transition_eligible('TenantA')

        for call in mock_db.execute_query.call_args_list:
            query = call[0][0]
            assert "status = 'ORPHAN'" in query

    def test_sets_status_to_deletion_eligible(self, service_with_ps, mock_db):
        """UPDATE sets status to DELETION_ELIGIBLE."""
        mock_db.execute_query.return_value = 0
        service_with_ps.ps.get_param.return_value = 30

        service_with_ps.transition_eligible('TenantA')

        for call in mock_db.execute_query.call_args_list:
            query = call[0][0]
            assert "SET status = 'DELETION_ELIGIBLE'" in query

    def test_uses_fetch_false_and_commit_true(self, service_with_ps, mock_db):
        """All queries use fetch=False and commit=True (write pattern)."""
        mock_db.execute_query.return_value = 0
        service_with_ps.ps.get_param.return_value = 30

        service_with_ps.transition_eligible('TenantA')

        for call in mock_db.execute_query.call_args_list:
            kwargs = call[1]
            assert kwargs.get('fetch') is False
            assert kwargs.get('commit') is True

    def test_landing_pages_splits_by_media_type(self, service_with_ps, mock_db):
        """Landing-pages issues two UPDATEs: web_content/document and image/video."""
        mock_db.execute_query.return_value = 0
        service_with_ps.ps.get_param.return_value = 30

        service_with_ps.transition_eligible('TenantA')

        calls = mock_db.execute_query.call_args_list
        # Total 5 calls: invoices, branding, templates, LP-web, LP-media
        assert len(calls) == 5

        # LP web_content query targets web_content + document
        lp_web_query = calls[3][0][0]
        assert "media_type IN ('web_content', 'document')" in lp_web_query

        # LP media query targets image + video
        lp_media_query = calls[4][0][0]
        assert "media_type IN ('image', 'video')" in lp_media_query

    def test_respects_asset_level_retention_override(self, service_with_ps, mock_db):
        """Query accounts for per-asset retention_days override (AC 8)."""
        mock_db.execute_query.return_value = 0
        service_with_ps.ps.get_param.return_value = 30

        service_with_ps.transition_eligible('TenantA')

        for call in mock_db.execute_query.call_args_list:
            query = call[0][0]
            # Check that asset-level override is checked first
            assert 'retention_days IS NOT NULL' in query
            assert 'retention_days IS NULL' in query

    def test_no_s3_deletion_occurs(self, service_with_ps, mock_db):
        """AC 2: No S3 object is deleted — only status changes."""
        mock_db.execute_query.return_value = 5
        service_with_ps.ps.get_param.return_value = 30

        with patch.object(service_with_ps, '_delete_raw') as mock_delete:
            service_with_ps.transition_eligible('TenantA')
            mock_delete.assert_not_called()


# ============================================================================
# delete_asset
# ============================================================================

class TestDeleteAsset:
    """Tests for delete_asset: reference guard, S3 deletion, audit logging (Req 5, Req 10)."""

    @pytest.fixture
    def service_with_transaction(self, mock_db):
        """Service with mocked transaction context manager."""
        with patch('services.media_asset_service.ParameterService'):
            svc = MediaAssetService(mock_db)
        return svc

    def _setup_transaction(self, mock_db, fetchone_returns):
        """Helper to set up mock transaction with sequential fetchone returns.

        Args:
            fetchone_returns: List of values for sequential fetchone calls.
                Typical order:
                1. asset row (SELECT FOR UPDATE)
                2. reference count row
        """
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_cursor.fetchone.side_effect = fetchone_returns
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        return mock_cursor, mock_conn

    # --- Happy path: ORPHAN with zero refs → deleted ---

    def test_delete_orphan_asset_success(self, service_with_transaction, mock_db):
        """Req 5 AC 4: ORPHAN asset with zero refs is deleted successfully."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_ORPHAN1', 'status': 'ORPHAN', 's3_key': 'TenantA/invoices/ast_ORPHAN1_doc.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 0},  # zero references
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            result = service_with_transaction.delete_asset(
                tenant='TenantA',
                asset_id='ast_ORPHAN1',
                approved_by='admin@tenant.com',
            )

        assert result['success'] is True
        assert result['asset_id'] == 'ast_ORPHAN1'

    def test_delete_deletion_eligible_asset_success(self, service_with_transaction, mock_db):
        """Req 5 AC 4: DELETION_ELIGIBLE asset with zero refs is deleted successfully."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_DEL1', 'status': 'DELETION_ELIGIBLE', 's3_key': 'TenantA/branding/ast_DEL1_logo.png',
             'bucket': 'shared-bucket', 'category': 'branding'},
            {'cnt': 0},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            result = service_with_transaction.delete_asset(
                tenant='TenantA',
                asset_id='ast_DEL1',
                approved_by='admin@tenant.com',
            )

        assert result['success'] is True
        assert result['asset_id'] == 'ast_DEL1'

    def test_delete_active_asset_with_zero_refs_success(self, service_with_transaction, mock_db):
        """Edge case: ACTIVE asset with zero refs is allowed (zero refs is the guard)."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_ACT1', 'status': 'ACTIVE', 's3_key': 'TenantA/invoices/ast_ACT1_old.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 0},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            result = service_with_transaction.delete_asset(
                tenant='TenantA',
                asset_id='ast_ACT1',
                approved_by='admin@tenant.com',
            )

        assert result['success'] is True
        assert result['asset_id'] == 'ast_ACT1'

    # --- Reference guard: asset with refs → error with count ---

    def test_delete_asset_with_references_rejected(self, service_with_transaction, mock_db):
        """Req 5 AC 12, Req 10 AC 2: Active references → reject with reference count."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_REF1', 'status': 'ACTIVE', 's3_key': 'TenantA/invoices/ast_REF1_doc.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 3},  # 3 active references
        ])

        result = service_with_transaction.delete_asset(
            tenant='TenantA',
            asset_id='ast_REF1',
            approved_by='admin@tenant.com',
        )

        assert result['success'] is False
        assert 'active references' in result['error']
        assert result['reference_count'] == 3

    def test_delete_orphan_reactivated_returns_reactivated(self, service_with_transaction, mock_db):
        """Req 5 AC 10: If ORPHAN asset regained a reference, report re-activated."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_REACTIVATED', 'status': 'ORPHAN', 's3_key': 'TenantA/invoices/ast_REACTIVATED_x.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 1},  # regained a reference between check and approval
        ])

        result = service_with_transaction.delete_asset(
            tenant='TenantA',
            asset_id='ast_REACTIVATED',
            approved_by='admin@tenant.com',
        )

        assert result['success'] is False
        assert result['error'] == 're-activated'
        assert result['reference_count'] == 1

    def test_delete_deletion_eligible_reactivated(self, service_with_transaction, mock_db):
        """Req 5 AC 10: DELETION_ELIGIBLE asset that regained reference → re-activated."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_DELREACT', 'status': 'DELETION_ELIGIBLE',
             's3_key': 'TenantA/branding/ast_DELREACT_logo.png',
             'bucket': 'shared-bucket', 'category': 'branding'},
            {'cnt': 2},
        ])

        result = service_with_transaction.delete_asset(
            tenant='TenantA',
            asset_id='ast_DELREACT',
            approved_by='admin@tenant.com',
        )

        assert result['success'] is False
        assert result['error'] == 're-activated'
        assert result['reference_count'] == 2

    # --- S3 failure → retain record, report failure ---

    def test_delete_s3_failure_retains_record(self, service_with_transaction, mock_db):
        """Req 5 AC 13: If S3 deletion fails, retain record and report failure."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_S3FAIL', 'status': 'ORPHAN', 's3_key': 'TenantA/invoices/ast_S3FAIL_doc.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 0},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=False):
            result = service_with_transaction.delete_asset(
                tenant='TenantA',
                asset_id='ast_S3FAIL',
                approved_by='admin@tenant.com',
            )

        assert result['success'] is False
        assert 'S3 deletion failed' in result['error']
        # Verify no DELETE queries were executed on the DB (records retained)
        delete_calls = [
            call for call in mock_cursor.execute.call_args_list
            if 'DELETE' in str(call[0][0]).upper()
        ]
        assert len(delete_calls) == 0

    # --- Asset not found → error ---

    def test_delete_asset_not_found(self, service_with_transaction, mock_db):
        """Return error when asset_id doesn't exist."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            None,  # asset not found
        ])

        result = service_with_transaction.delete_asset(
            tenant='TenantA',
            asset_id='ast_NONEXIST',
            approved_by='admin@tenant.com',
        )

        assert result['success'] is False
        assert 'not found' in result['error'].lower()

    def test_delete_asset_wrong_tenant_returns_not_found(self, service_with_transaction, mock_db):
        """Tenant isolation: asset belonging to different tenant → not found."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            None,  # query scoped to wrong tenant returns nothing
        ])

        result = service_with_transaction.delete_asset(
            tenant='WrongTenant',
            asset_id='ast_OTHER',
            approved_by='admin@wrong.com',
        )

        assert result['success'] is False
        assert 'not found' in result['error'].lower()

    # --- Tenant isolation in all queries ---

    def test_delete_select_for_update_includes_tenant(self, service_with_transaction, mock_db):
        """SELECT FOR UPDATE query includes administration filter."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_T1', 'status': 'ORPHAN', 's3_key': 'TenantA/invoices/ast_T1_x.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 0},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            service_with_transaction.delete_asset(
                tenant='TenantA',
                asset_id='ast_T1',
                approved_by='admin@tenant.com',
            )

        # First call is SELECT FOR UPDATE
        select_call = mock_cursor.execute.call_args_list[0]
        query = select_call[0][0]
        params = select_call[0][1]
        assert 'FOR UPDATE' in query.upper()
        assert 'administration = %s' in query
        assert params == ('ast_T1', 'TenantA')

    def test_delete_reference_count_includes_tenant(self, service_with_transaction, mock_db):
        """Reference count query includes administration filter for tenant isolation."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_T2', 'status': 'ORPHAN', 's3_key': 'TenantA/invoices/ast_T2_x.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 0},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            service_with_transaction.delete_asset(
                tenant='TenantA',
                asset_id='ast_T2',
                approved_by='admin@tenant.com',
            )

        # Second call is COUNT query
        count_call = mock_cursor.execute.call_args_list[1]
        query = count_call[0][0]
        params = count_call[0][1]
        assert 'COUNT' in query.upper()
        assert 'administration = %s' in query
        assert params == ('ast_T2', 'TenantA')

    def test_delete_db_removal_includes_tenant(self, service_with_transaction, mock_db):
        """DELETE queries include administration filter for tenant isolation."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_T3', 'status': 'ORPHAN', 's3_key': 'TenantA/invoices/ast_T3_x.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 0},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            service_with_transaction.delete_asset(
                tenant='TenantA',
                asset_id='ast_T3',
                approved_by='admin@tenant.com',
            )

        # Find DELETE calls (calls after the SELECT and COUNT)
        delete_calls = [
            call for call in mock_cursor.execute.call_args_list
            if 'DELETE' in str(call[0][0]).upper()
        ]
        assert len(delete_calls) == 2  # references + assets
        for call in delete_calls:
            query = call[0][0]
            params = call[0][1]
            assert 'administration = %s' in query
            assert 'TenantA' in params

    # --- S3 deletion called with correct params ---

    def test_delete_calls_delete_raw_with_correct_params(self, service_with_transaction, mock_db):
        """_delete_raw is called with the asset's bucket and s3_key."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_S3', 'status': 'DELETION_ELIGIBLE',
             's3_key': 'TenantA/branding/ast_S3_logo.png',
             'bucket': 'shared-bucket', 'category': 'branding'},
            {'cnt': 0},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True) as mock_del:
            service_with_transaction.delete_asset(
                tenant='TenantA',
                asset_id='ast_S3',
                approved_by='admin@tenant.com',
            )

        mock_del.assert_called_once_with('shared-bucket', 'TenantA/branding/ast_S3_logo.png')

    # --- DB records removed after successful S3 deletion ---

    def test_delete_removes_references_and_asset_records(self, service_with_transaction, mock_db):
        """After S3 deletion, both s3_asset_references and s3_assets rows are deleted."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_RM1', 'status': 'ORPHAN', 's3_key': 'TenantA/invoices/ast_RM1_x.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 0},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            service_with_transaction.delete_asset(
                tenant='TenantA',
                asset_id='ast_RM1',
                approved_by='admin@tenant.com',
            )

        delete_calls = [
            call for call in mock_cursor.execute.call_args_list
            if 'DELETE' in str(call[0][0]).upper()
        ]
        assert len(delete_calls) == 2

        # First DELETE: s3_asset_references
        ref_delete = delete_calls[0][0][0]
        assert 's3_asset_references' in ref_delete

        # Second DELETE: s3_assets
        asset_delete = delete_calls[1][0][0]
        assert 's3_assets' in asset_delete

    # --- Audit logging verification ---

    def test_delete_logs_audit_info(self, service_with_transaction, mock_db):
        """Req 5 AC 11: Log asset_id, administration, bucket, category, approved_by."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_LOG1', 'status': 'ORPHAN',
             's3_key': 'TenantA/invoices/ast_LOG1_doc.pdf',
             'bucket': 'audit-bucket', 'category': 'invoices'},
            {'cnt': 0},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            with patch('services.media_asset_service.logger') as mock_logger:
                service_with_transaction.delete_asset(
                    tenant='TenantA',
                    asset_id='ast_LOG1',
                    approved_by='admin@tenant.com',
                )

        mock_logger.info.assert_called_once()
        log_args = mock_logger.info.call_args[0]
        log_message = log_args[0] % log_args[1:]
        assert 'ast_LOG1' in log_message
        assert 'TenantA' in log_message
        assert 'audit-bucket' in log_message
        assert 'invoices' in log_message
        assert 'admin@tenant.com' in log_message

    def test_delete_no_audit_log_on_failure(self, service_with_transaction, mock_db):
        """Audit log is NOT written when deletion fails."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_NOLOG', 'status': 'ORPHAN',
             's3_key': 'TenantA/invoices/ast_NOLOG_x.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 0},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=False):
            with patch('services.media_asset_service.logger') as mock_logger:
                service_with_transaction.delete_asset(
                    tenant='TenantA',
                    asset_id='ast_NOLOG',
                    approved_by='admin@tenant.com',
                )

        mock_logger.info.assert_not_called()

    # --- SELECT FOR UPDATE locks the row ---

    def test_delete_uses_select_for_update(self, service_with_transaction, mock_db):
        """Row is locked with SELECT FOR UPDATE to prevent race conditions."""
        mock_cursor, _ = self._setup_transaction(mock_db, [
            {'id': 'ast_LOCK1', 'status': 'ORPHAN',
             's3_key': 'TenantA/invoices/ast_LOCK1_x.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 0},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            service_with_transaction.delete_asset(
                tenant='TenantA',
                asset_id='ast_LOCK1',
                approved_by='admin@tenant.com',
            )

        first_call = mock_cursor.execute.call_args_list[0]
        query = first_call[0][0]
        assert 'FOR UPDATE' in query.upper()

    # --- Uses single transaction for atomicity ---

    def test_delete_uses_single_transaction(self, service_with_transaction, mock_db):
        """All DB operations happen within one db.transaction() call."""
        self._setup_transaction(mock_db, [
            {'id': 'ast_TX1', 'status': 'ORPHAN',
             's3_key': 'TenantA/invoices/ast_TX1_x.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 0},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            service_with_transaction.delete_asset(
                tenant='TenantA',
                asset_id='ast_TX1',
                approved_by='admin@tenant.com',
            )

        mock_db.transaction.assert_called_once()


# ============================================================================
# force_delete
# ============================================================================

class TestForceDelete:
    """Tests for force_delete — emergency delete bypassing reference guard.

    Req 10 AC 7: Bypasses reference guard, logs warning.
    Req 10 AC 8: Audit entry with asset_id, administration, operator,
                 reference count, reason, timestamp.
    """

    @pytest.fixture
    def service_with_transaction(self, mock_db):
        """Service with mocked transaction context manager."""
        with patch('services.media_asset_service.ParameterService'):
            svc = MediaAssetService(mock_db)
            return svc

    def _setup_transaction(self, mock_db, fetchone_results):
        """Helper to configure mock_db.transaction() with sequential fetchone results."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_cursor.fetchone = MagicMock(side_effect=fetchone_results)
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        return mock_cursor

    # --- Happy path: force delete with active references ---

    def test_force_delete_bypasses_reference_guard(self, service_with_transaction, mock_db):
        """AC 7: force_delete succeeds even when references exist."""
        mock_cursor = self._setup_transaction(mock_db, [
            {'id': 'ast_FD1', 'status': 'ACTIVE',
             's3_key': 'TenantA/invoices/ast_FD1_report.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 3},  # 3 active references — would block normal delete
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            result = service_with_transaction.force_delete(
                tenant='TenantA',
                asset_id='ast_FD1',
                operator='sysadmin@example.com',
                reason='Emergency recovery — corrupted asset',
            )

        assert result['success'] is True
        assert result['asset_id'] == 'ast_FD1'
        assert result['reference_count'] == 3
        assert result['operator'] == 'sysadmin@example.com'
        assert result['reason'] == 'Emergency recovery — corrupted asset'

    # --- Happy path: force delete with zero references ---

    def test_force_delete_with_zero_references(self, service_with_transaction, mock_db):
        """Force delete works even with zero references (orphan asset)."""
        mock_cursor = self._setup_transaction(mock_db, [
            {'id': 'ast_FD2', 'status': 'ORPHAN',
             's3_key': 'TenantA/branding/ast_FD2_logo.png',
             'bucket': 'shared-bucket', 'category': 'branding'},
            {'cnt': 0},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            result = service_with_transaction.force_delete(
                tenant='TenantA',
                asset_id='ast_FD2',
                operator='admin@corp.com',
                reason='Cleanup orphaned asset',
            )

        assert result['success'] is True
        assert result['reference_count'] == 0

    # --- Asset not found ---

    def test_force_delete_asset_not_found(self, service_with_transaction, mock_db):
        """Returns error when asset does not exist."""
        mock_cursor = self._setup_transaction(mock_db, [
            None,  # asset not found
        ])

        result = service_with_transaction.force_delete(
            tenant='TenantA',
            asset_id='ast_NONEXIST',
            operator='admin@example.com',
            reason='Test',
        )

        assert result['success'] is False
        assert result['error'] == 'Asset not found'

    # --- S3 deletion failure ---

    def test_force_delete_s3_failure(self, service_with_transaction, mock_db):
        """Returns error when S3 deletion fails (same as delete_asset)."""
        self._setup_transaction(mock_db, [
            {'id': 'ast_FD3', 'status': 'ACTIVE',
             's3_key': 'TenantA/invoices/ast_FD3_file.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 2},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=False):
            result = service_with_transaction.force_delete(
                tenant='TenantA',
                asset_id='ast_FD3',
                operator='admin@example.com',
                reason='Emergency',
            )

        assert result['success'] is False
        assert result['error'] == 'S3 deletion failed'

    # --- Audit logging (WARNING level) ---

    def test_force_delete_logs_warning_with_audit_fields(self, service_with_transaction, mock_db):
        """AC 7/8: Logs WARNING with asset_id, administration, operator, ref_count, reason."""
        self._setup_transaction(mock_db, [
            {'id': 'ast_FD4', 'status': 'ACTIVE',
             's3_key': 'TenantA/invoices/ast_FD4_x.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 5},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            with patch('services.media_asset_service.logger') as mock_logger:
                service_with_transaction.force_delete(
                    tenant='TenantA',
                    asset_id='ast_FD4',
                    operator='sysadmin@corp.com',
                    reason='Corrupted file causing errors',
                )

                mock_logger.warning.assert_called_once()
                log_call_args = mock_logger.warning.call_args[0]
                log_message = log_call_args[0] % log_call_args[1:]

                assert 'ast_FD4' in log_message
                assert 'TenantA' in log_message
                assert 'sysadmin@corp.com' in log_message
                assert '5' in log_message  # reference_count
                assert 'Corrupted file causing errors' in log_message

    # --- DB operations: deletes both references and asset ---

    def test_force_delete_removes_references_and_asset(self, service_with_transaction, mock_db):
        """Removes s3_asset_references rows AND s3_assets row."""
        mock_cursor = self._setup_transaction(mock_db, [
            {'id': 'ast_FD5', 'status': 'ACTIVE',
             's3_key': 'TenantA/invoices/ast_FD5_doc.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 2},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            with patch('services.media_asset_service.logger'):
                service_with_transaction.force_delete(
                    tenant='TenantA',
                    asset_id='ast_FD5',
                    operator='admin@example.com',
                    reason='Emergency',
                )

        # Verify DELETE queries executed (after SELECT + COUNT = 2, so calls 3 and 4)
        execute_calls = mock_cursor.execute.call_args_list
        # Should have: SELECT FOR UPDATE, COUNT, DELETE refs, DELETE asset
        assert len(execute_calls) == 4

        # DELETE from s3_asset_references
        delete_refs_call = execute_calls[2]
        assert 's3_asset_references' in delete_refs_call[0][0]
        assert delete_refs_call[0][1] == ('ast_FD5', 'TenantA')

        # DELETE from s3_assets
        delete_asset_call = execute_calls[3]
        assert 's3_assets' in delete_asset_call[0][0]
        assert delete_asset_call[0][1] == ('ast_FD5', 'TenantA')

    # --- Uses transaction (atomicity) ---

    def test_force_delete_uses_transaction(self, service_with_transaction, mock_db):
        """All DB operations within one db.transaction() call."""
        self._setup_transaction(mock_db, [
            {'id': 'ast_FD6', 'status': 'ACTIVE',
             's3_key': 'TenantA/invoices/ast_FD6_x.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 1},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            with patch('services.media_asset_service.logger'):
                service_with_transaction.force_delete(
                    tenant='TenantA',
                    asset_id='ast_FD6',
                    operator='admin@example.com',
                    reason='Test',
                )

        mock_db.transaction.assert_called_once()

    # --- Return value includes reference_count for audit trail ---

    def test_force_delete_returns_reference_count(self, service_with_transaction, mock_db):
        """Return value includes ref count so caller can include in response/logs."""
        self._setup_transaction(mock_db, [
            {'id': 'ast_FD7', 'status': 'ACTIVE',
             's3_key': 'TenantA/invoices/ast_FD7_x.pdf',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 7},
        ])

        with patch.object(service_with_transaction, '_delete_raw', return_value=True):
            with patch('services.media_asset_service.logger'):
                result = service_with_transaction.force_delete(
                    tenant='TenantA',
                    asset_id='ast_FD7',
                    operator='admin@example.com',
                    reason='Recovery',
                )

        assert result['reference_count'] == 7


# ============================================================================
# Lifecycle integration tests
# ============================================================================

class TestLifecycle:
    """Integration-style lifecycle tests: exercises the full state machine in sequence.

    Tests the end-to-end flow through multiple service methods:
    ACTIVE → ORPHAN → DELETION_ELIGIBLE → deleted, re-activation paths,
    reference guard, retention period logic, and force delete.
    """

    @pytest.fixture
    def service_with_env(self, mock_db):
        """Service with required env vars and mocked ParameterService."""
        mock_ps = MagicMock()
        with patch('services.media_asset_service.ParameterService', return_value=mock_ps):
            with patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-bucket'}):
                svc = MediaAssetService(mock_db, parameter_service=mock_ps)
                return svc

    @pytest.fixture
    def valid_jpeg(self):
        """Valid JPEG file data for testing."""
        return b'\xff\xd8\xff\xe0' + b'\x00' * 100

    # --- Test 1: Full lifecycle ACTIVE → ORPHAN → DELETION_ELIGIBLE → deleted ---

    def test_full_lifecycle_active_to_deleted(self, service_with_env, valid_jpeg, mock_db):
        """Full lifecycle: store (ACTIVE) → detach (ORPHAN) → transition (DELETION_ELIGIBLE) → delete.

        Exercises the complete asset lifecycle from creation through permanent deletion.
        """
        # Phase 1: store_and_register with reference → ACTIVE
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.execute_query.return_value = []  # no duplicates

        with patch.object(service_with_env, '_upload_raw', return_value=True):
            store_result = service_with_env.store_and_register(
                tenant='TenantA',
                file_data=valid_jpeg,
                filename='lifecycle.jpg',
                category='invoices',
                entity_type='invoice',
                entity_id='INV-001',
            )

        assert store_result['success'] is True
        assert store_result['asset']['status'] == 'ACTIVE'
        assert store_result['asset']['reference_count'] == 1
        asset_id = store_result['asset']['id']

        # Phase 2: detach last reference → ORPHAN
        mock_cursor.fetchone.side_effect = [
            {'id': asset_id, 'status': 'ACTIVE'},  # asset lookup
            {'cnt': 0},  # zero remaining refs after delete
        ]
        mock_cursor.rowcount = 1  # DELETE affected 1 row

        detach_result = service_with_env.detach(
            tenant='TenantA',
            asset_id=asset_id,
            entity_type='invoice',
            entity_id='INV-001',
        )

        assert detach_result['success'] is True
        assert detach_result['asset']['status'] == 'ORPHAN'
        assert detach_result['asset']['reference_count'] == 0

        # Phase 3: transition_eligible → DELETION_ELIGIBLE
        service_with_env.ps.get_param.return_value = 30  # 30-day retention
        mock_db.execute_query.reset_mock()
        mock_db.execute_query.return_value = 1  # 1 asset transitioned

        transition_result = service_with_env.transition_eligible('TenantA')

        assert transition_result['success'] is True
        assert transition_result['transitioned'] > 0

        # Phase 4: delete_asset → permanently deleted
        mock_cursor.fetchone.side_effect = [
            {'id': asset_id, 'status': 'DELETION_ELIGIBLE',
             's3_key': f'TenantA/invoices/{asset_id}_lifecycle.jpg',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 0},  # zero references (guard passes)
        ]

        with patch.object(service_with_env, '_delete_raw', return_value=True):
            delete_result = service_with_env.delete_asset(
                tenant='TenantA',
                asset_id=asset_id,
                approved_by='admin@tenant.com',
            )

        assert delete_result['success'] is True
        assert delete_result['asset_id'] == asset_id

    # --- Test 2: Re-activation ACTIVE → ORPHAN → ACTIVE (via attach) ---

    def test_reactivation_orphan_to_active_via_attach(self, service_with_env, valid_jpeg, mock_db):
        """Re-activation: ACTIVE → ORPHAN → ACTIVE when a new reference is attached.

        Verifies that attaching a reference to an orphaned asset reverts it
        back to ACTIVE and clears orphaned_at.
        """
        # Phase 1: store_and_register → ACTIVE
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.execute_query.return_value = []

        with patch.object(service_with_env, '_upload_raw', return_value=True):
            store_result = service_with_env.store_and_register(
                tenant='TenantA',
                file_data=valid_jpeg,
                filename='reactivate.jpg',
                category='branding',
                entity_type='branding',
                entity_id='logo_v1',
            )

        assert store_result['success'] is True
        assert store_result['asset']['status'] == 'ACTIVE'
        asset_id = store_result['asset']['id']

        # Phase 2: detach → ORPHAN
        mock_cursor.fetchone.side_effect = [
            {'id': asset_id, 'status': 'ACTIVE'},
            {'cnt': 0},
        ]
        mock_cursor.rowcount = 1

        detach_result = service_with_env.detach(
            tenant='TenantA',
            asset_id=asset_id,
            entity_type='branding',
            entity_id='logo_v1',
        )

        assert detach_result['success'] is True
        assert detach_result['asset']['status'] == 'ORPHAN'

        # Phase 3: attach new reference → back to ACTIVE
        mock_cursor.fetchone.side_effect = None
        mock_cursor.fetchone.return_value = {'id': asset_id, 'status': 'ORPHAN'}

        attach_result = service_with_env.attach(
            tenant='TenantA',
            asset_id=asset_id,
            entity_type='branding',
            entity_id='logo_v2',
        )

        assert attach_result['success'] is True
        assert attach_result['status'] == 'ACTIVE'

        # Verify the UPDATE set ACTIVE and cleared orphaned_at
        reactivation_calls = [
            call for call in mock_cursor.execute.call_args_list
            if "status = 'ACTIVE'" in str(call[0][0]) and 'orphaned_at = NULL' in str(call[0][0])
        ]
        assert len(reactivation_calls) >= 1

    # --- Test 3: Re-activation ACTIVE → ORPHAN → DELETION_ELIGIBLE → ACTIVE (via attach) ---

    def test_reactivation_deletion_eligible_to_active_via_attach(self, service_with_env, valid_jpeg, mock_db):
        """Re-activation from DELETION_ELIGIBLE: even after transition, attaching reverts to ACTIVE.

        This tests the edge case where an asset has already been marked DELETION_ELIGIBLE
        but a new reference is created before actual deletion occurs.
        """
        # Phase 1: store_and_register → ACTIVE
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.execute_query.return_value = []

        with patch.object(service_with_env, '_upload_raw', return_value=True):
            store_result = service_with_env.store_and_register(
                tenant='TenantA',
                file_data=valid_jpeg,
                filename='eligible.jpg',
                category='invoices',
                entity_type='invoice',
                entity_id='INV-100',
            )

        assert store_result['success'] is True
        assert store_result['asset']['status'] == 'ACTIVE'
        asset_id = store_result['asset']['id']

        # Phase 2: detach → ORPHAN
        mock_cursor.fetchone.side_effect = [
            {'id': asset_id, 'status': 'ACTIVE'},
            {'cnt': 0},
        ]
        mock_cursor.rowcount = 1

        detach_result = service_with_env.detach(
            tenant='TenantA',
            asset_id=asset_id,
            entity_type='invoice',
            entity_id='INV-100',
        )

        assert detach_result['success'] is True
        assert detach_result['asset']['status'] == 'ORPHAN'

        # Phase 3: transition_eligible → DELETION_ELIGIBLE (simulated)
        service_with_env.ps.get_param.return_value = 30
        mock_db.execute_query.reset_mock()
        mock_db.execute_query.return_value = 1

        transition_result = service_with_env.transition_eligible('TenantA')
        assert transition_result['success'] is True

        # Phase 4: attach while DELETION_ELIGIBLE → ACTIVE
        mock_cursor.fetchone.side_effect = None
        mock_cursor.fetchone.return_value = {'id': asset_id, 'status': 'DELETION_ELIGIBLE'}

        attach_result = service_with_env.attach(
            tenant='TenantA',
            asset_id=asset_id,
            entity_type='invoice',
            entity_id='INV-200',
        )

        assert attach_result['success'] is True
        assert attach_result['status'] == 'ACTIVE'

    # --- Test 4: Reference guard blocks deletion of ACTIVE asset ---

    def test_reference_guard_blocks_deletion(self, service_with_env, valid_jpeg, mock_db):
        """Reference guard: ACTIVE asset with references cannot be deleted.

        delete_asset must fail with a reference count error when the asset
        still has active references.
        """
        # Phase 1: store_and_register with reference → ACTIVE
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.execute_query.return_value = []

        with patch.object(service_with_env, '_upload_raw', return_value=True):
            store_result = service_with_env.store_and_register(
                tenant='TenantA',
                file_data=valid_jpeg,
                filename='guarded.jpg',
                category='invoices',
                entity_type='invoice',
                entity_id='INV-GUARD',
            )

        assert store_result['success'] is True
        assert store_result['asset']['reference_count'] == 1
        asset_id = store_result['asset']['id']

        # Phase 2: attempt delete_asset while reference exists → BLOCKED
        mock_cursor.fetchone.side_effect = [
            {'id': asset_id, 'status': 'ACTIVE',
             's3_key': f'TenantA/invoices/{asset_id}_guarded.jpg',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 1},  # 1 active reference → guard blocks
        ]

        delete_result = service_with_env.delete_asset(
            tenant='TenantA',
            asset_id=asset_id,
            approved_by='admin@tenant.com',
        )

        assert delete_result['success'] is False
        assert 'active references' in delete_result['error']
        assert delete_result['reference_count'] == 1

    # --- Test 5: Retention period blocks early transition ---

    def test_retention_period_blocks_early_transition(self, service_with_env, mock_db):
        """Retention period: orphan created today with 30-day retention is NOT transitioned.

        transition_eligible should not transition an asset whose orphaned_at is recent
        when the category retention is 30 days. The DB query handles this via
        DATE_SUB comparison. When no rows match (orphan is too new), result is 0.
        """
        # Set up a 30-day retention
        service_with_env.ps.get_param.return_value = 30
        # No rows match — orphan is too recent
        mock_db.execute_query.return_value = 0

        result = service_with_env.transition_eligible('TenantA')

        assert result['success'] is True
        assert result['transitioned'] == 0

        # Verify that the retention value 30 is passed to the query
        for call in mock_db.execute_query.call_args_list:
            params = call[0][1]
            # Third param is the retention days
            assert params[2] == 30

    # --- Test 6: Force delete bypasses all guards ---

    def test_force_delete_bypasses_reference_guard(self, service_with_env, valid_jpeg, mock_db):
        """Force delete: ACTIVE asset with references is deleted via force_delete.

        force_delete bypasses the reference guard entirely, useful for
        emergency recovery scenarios.
        """
        # Phase 1: store_and_register with reference → ACTIVE
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        mock_db.execute_query.return_value = []

        with patch.object(service_with_env, '_upload_raw', return_value=True):
            store_result = service_with_env.store_and_register(
                tenant='TenantA',
                file_data=valid_jpeg,
                filename='force.jpg',
                category='invoices',
                entity_type='invoice',
                entity_id='INV-FORCE',
            )

        assert store_result['success'] is True
        assert store_result['asset']['reference_count'] == 1
        asset_id = store_result['asset']['id']

        # Phase 2: force_delete succeeds despite active references
        mock_cursor.fetchone.side_effect = [
            {'id': asset_id, 'status': 'ACTIVE',
             's3_key': f'TenantA/invoices/{asset_id}_force.jpg',
             'bucket': 'test-bucket', 'category': 'invoices'},
            {'cnt': 1},  # 1 reference — normal delete would fail
        ]

        with patch.object(service_with_env, '_delete_raw', return_value=True):
            with patch('services.media_asset_service.logger'):
                force_result = service_with_env.force_delete(
                    tenant='TenantA',
                    asset_id=asset_id,
                    operator='sysadmin@corp.com',
                    reason='Emergency: corrupted file',
                )

        assert force_result['success'] is True
        assert force_result['asset_id'] == asset_id
        assert force_result['reference_count'] == 1
        assert force_result['operator'] == 'sysadmin@corp.com'
        assert force_result['reason'] == 'Emergency: corrupted file'

# ============================================================================
# Reconciliation — Phase 1: S3 Scan
# ============================================================================

class TestReconcileS3Scan:
    """Tests for run_reconciliation Phase 1: S3 scan vs registry comparison.

    Req 6 AC 1: Identify unregistered S3 objects (in S3 but not in registry).
    Req 6 AC 2: Identify missing objects (in registry but not in S3).
    Req 6 AC 6: Process assets scoped per tenant (administration).
    """

    @pytest.fixture
    def service_with_env(self, mock_db):
        """Service with required env vars set, with phase2 and phase3 patched out."""
        with patch('services.media_asset_service.ParameterService'):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': 'myadmin-pages',
            }):
                svc = MediaAssetService(mock_db)
                # Patch out phase 2 so these tests focus purely on phase 1
                svc._reconcile_references = MagicMock(
                    return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
                )
                # Patch out phase 3 so these tests focus purely on phase 1
                svc.transition_eligible = MagicMock(
                    return_value={'transitioned': 0, 'assets': []}
                )
                return svc

    def _mock_paginator(self, pages):
        """Create a mock paginator that yields given pages.

        Args:
            pages: List of page dicts, each with 'Contents' list of objects.
        """
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = pages
        return mock_paginator

    # --- Happy path: finds unregistered and missing ---

    def test_identifies_unregistered_objects(self, service_with_env, mock_db):
        """AC 1: S3 objects not in registry are reported as unregistered."""
        # S3 has 3 objects, registry has 2
        shared_page = {'Contents': [
            {'Key': 'TenantA/invoices/ast_001_file.pdf', 'Size': 1000},
            {'Key': 'TenantA/invoices/ast_002_file.pdf', 'Size': 2000},
            {'Key': 'TenantA/branding/ast_003_logo.png', 'Size': 500},
        ]}

        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = self._mock_paginator([shared_page])

        # Registry only knows about 2 of the 3
        mock_db.execute_query.return_value = [
            {'s3_key': 'TenantA/invoices/ast_001_file.pdf', 'bucket': 'myadmin-shared'},
            {'s3_key': 'TenantA/invoices/ast_002_file.pdf', 'bucket': 'myadmin-shared'},
        ]

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': '',
            }):
                result = service_with_env.run_reconciliation('TenantA')

        phase1 = result['phase1']
        assert len(phase1['unregistered']) == 1
        assert phase1['unregistered'][0]['s3_key'] == 'TenantA/branding/ast_003_logo.png'
        assert phase1['unregistered'][0]['bucket'] == 'myadmin-shared'

    def test_identifies_missing_objects(self, service_with_env, mock_db):
        """AC 2: Registry records with no S3 object are reported as missing."""
        # S3 has 1 object, registry has 2
        shared_page = {'Contents': [
            {'Key': 'TenantA/invoices/ast_001_file.pdf', 'Size': 1000},
        ]}

        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = self._mock_paginator([shared_page])

        mock_db.execute_query.return_value = [
            {'s3_key': 'TenantA/invoices/ast_001_file.pdf', 'bucket': 'myadmin-shared'},
            {'s3_key': 'TenantA/invoices/ast_002_gone.pdf', 'bucket': 'myadmin-shared'},
        ]

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': '',
            }):
                result = service_with_env.run_reconciliation('TenantA')

        phase1 = result['phase1']
        assert len(phase1['missing']) == 1
        assert phase1['missing'][0]['s3_key'] == 'TenantA/invoices/ast_002_gone.pdf'
        assert phase1['missing'][0]['bucket'] == 'myadmin-shared'

    def test_all_registered_no_discrepancies(self, service_with_env, mock_db):
        """No unregistered or missing when S3 and registry match exactly."""
        shared_page = {'Contents': [
            {'Key': 'TenantA/invoices/ast_001_file.pdf', 'Size': 1000},
            {'Key': 'TenantA/branding/ast_002_logo.png', 'Size': 500},
        ]}

        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = self._mock_paginator([shared_page])

        mock_db.execute_query.return_value = [
            {'s3_key': 'TenantA/invoices/ast_001_file.pdf', 'bucket': 'myadmin-shared'},
            {'s3_key': 'TenantA/branding/ast_002_logo.png', 'bucket': 'myadmin-shared'},
        ]

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': '',
            }):
                result = service_with_env.run_reconciliation('TenantA')

        phase1 = result['phase1']
        assert phase1['unregistered'] == []
        assert phase1['missing'] == []
        assert phase1['total_s3'] == 2
        assert phase1['total_registry'] == 2

    # --- Folder marker filtering ---

    def test_filters_folder_markers(self, service_with_env, mock_db):
        """Zero-byte .folder objects are excluded from comparison."""
        shared_page = {'Contents': [
            {'Key': 'TenantA/invoices/2024-Q1/.folder', 'Size': 0},
            {'Key': 'TenantA/invoices/ast_001_file.pdf', 'Size': 1000},
        ]}

        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = self._mock_paginator([shared_page])

        mock_db.execute_query.return_value = [
            {'s3_key': 'TenantA/invoices/ast_001_file.pdf', 'bucket': 'myadmin-shared'},
        ]

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': '',
            }):
                result = service_with_env.run_reconciliation('TenantA')

        phase1 = result['phase1']
        assert phase1['unregistered'] == []
        assert phase1['missing'] == []
        assert phase1['total_s3'] == 1  # .folder excluded from count

    def test_non_zero_folder_marker_not_filtered(self, service_with_env, mock_db):
        """A .folder file with non-zero size is NOT filtered (edge case)."""
        shared_page = {'Contents': [
            {'Key': 'TenantA/invoices/data.folder', 'Size': 100},
        ]}

        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = self._mock_paginator([shared_page])

        mock_db.execute_query.return_value = []

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': '',
            }):
                result = service_with_env.run_reconciliation('TenantA')

        phase1 = result['phase1']
        assert len(phase1['unregistered']) == 1

    # --- Multi-bucket scanning ---

    def test_scans_both_shared_and_pages_buckets(self, service_with_env, mock_db):
        """AC 6: Scans shared bucket and public-pages bucket for the tenant."""
        shared_page = {'Contents': [
            {'Key': 'TenantA/invoices/ast_001_invoice.pdf', 'Size': 1000},
        ]}
        pages_page = {'Contents': [
            {'Key': 'TenantA/landing-pages/ast_002_hero.webp', 'Size': 5000},
        ]}

        mock_s3 = MagicMock()
        # Two calls to get_paginator: one for shared, one for pages
        mock_paginator_shared = self._mock_paginator([shared_page])
        mock_paginator_pages = self._mock_paginator([pages_page])
        mock_s3.get_paginator.side_effect = [
            mock_paginator_shared, mock_paginator_pages,
        ]

        mock_db.execute_query.return_value = [
            {'s3_key': 'TenantA/invoices/ast_001_invoice.pdf', 'bucket': 'myadmin-shared'},
            {'s3_key': 'TenantA/landing-pages/ast_002_hero.webp', 'bucket': 'myadmin-pages'},
        ]

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': 'myadmin-pages',
            }):
                result = service_with_env.run_reconciliation('TenantA')

        phase1 = result['phase1']
        assert phase1['unregistered'] == []
        assert phase1['missing'] == []
        assert phase1['total_s3'] == 2
        assert phase1['total_registry'] == 2

    # --- Pagination handling ---

    def test_handles_paginated_s3_results(self, service_with_env, mock_db):
        """Handles multi-page S3 listing correctly."""
        page1 = {'Contents': [
            {'Key': 'TenantA/invoices/ast_001_a.pdf', 'Size': 100},
            {'Key': 'TenantA/invoices/ast_002_b.pdf', 'Size': 200},
        ]}
        page2 = {'Contents': [
            {'Key': 'TenantA/invoices/ast_003_c.pdf', 'Size': 300},
        ]}

        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = self._mock_paginator([page1, page2])

        mock_db.execute_query.return_value = [
            {'s3_key': 'TenantA/invoices/ast_001_a.pdf', 'bucket': 'myadmin-shared'},
        ]

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': '',
            }):
                result = service_with_env.run_reconciliation('TenantA')

        phase1 = result['phase1']
        assert phase1['total_s3'] == 3
        assert len(phase1['unregistered']) == 2

    # --- Empty bucket / empty registry ---

    def test_empty_s3_bucket_all_registry_missing(self, service_with_env, mock_db):
        """All registry items reported as missing when S3 is empty."""
        empty_page = {}  # No 'Contents' key

        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = self._mock_paginator([empty_page])

        mock_db.execute_query.return_value = [
            {'s3_key': 'TenantA/invoices/ast_001_file.pdf', 'bucket': 'myadmin-shared'},
        ]

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': '',
            }):
                result = service_with_env.run_reconciliation('TenantA')

        phase1 = result['phase1']
        assert phase1['total_s3'] == 0
        assert len(phase1['missing']) == 1
        assert phase1['unregistered'] == []

    def test_empty_registry_all_s3_unregistered(self, service_with_env, mock_db):
        """All S3 objects reported as unregistered when registry is empty."""
        shared_page = {'Contents': [
            {'Key': 'TenantA/invoices/ast_001_file.pdf', 'Size': 1000},
            {'Key': 'TenantA/branding/ast_002_logo.png', 'Size': 500},
        ]}

        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = self._mock_paginator([shared_page])

        mock_db.execute_query.return_value = []  # empty registry

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': '',
            }):
                result = service_with_env.run_reconciliation('TenantA')

        phase1 = result['phase1']
        assert phase1['total_registry'] == 0
        assert len(phase1['unregistered']) == 2
        assert phase1['missing'] == []

    # --- Return structure ---

    def test_run_reconciliation_return_structure(self, service_with_env, mock_db):
        """Return dict has expected top-level structure."""
        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = self._mock_paginator([{}])
        mock_db.execute_query.return_value = []

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': '',
            }):
                result = service_with_env.run_reconciliation('TenantA')

        assert result['success'] is True
        assert result['tenant'] == 'TenantA'
        assert 'phase1' in result
        phase1 = result['phase1']
        assert 'unregistered' in phase1
        assert 'missing' in phase1
        assert 'total_s3' in phase1
        assert 'total_registry' in phase1

    # --- S3 error handling ---

    def test_s3_error_returns_empty_list(self, service_with_env, mock_db):
        """S3 ClientError results in empty object list (graceful degradation)."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Forbidden'}},
            'ListObjectsV2'
        )
        mock_s3.get_paginator.return_value = mock_paginator

        mock_db.execute_query.return_value = [
            {'s3_key': 'TenantA/invoices/ast_001_file.pdf', 'bucket': 'myadmin-shared'},
        ]

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': '',
            }):
                result = service_with_env.run_reconciliation('TenantA')

        # Should still succeed — S3 error means we get 0 S3 objects
        assert result['success'] is True
        phase1 = result['phase1']
        assert phase1['total_s3'] == 0
        assert len(phase1['missing']) == 1  # all registry items appear missing

    # --- Tenant isolation ---

    def test_registry_query_scoped_to_tenant(self, service_with_env, mock_db):
        """AC 6: DB query uses administration = %s for tenant isolation."""
        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = self._mock_paginator([{}])
        mock_db.execute_query.return_value = []

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': '',
            }):
                service_with_env.run_reconciliation('TenantA')

        # Verify the DB query includes tenant filter
        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'administration = %s' in query
        assert params == ('TenantA',)

    def test_s3_prefix_uses_tenant(self, service_with_env, mock_db):
        """AC 6: S3 listing uses {tenant}/ as prefix."""
        mock_s3 = MagicMock()
        mock_paginator = self._mock_paginator([{}])
        mock_s3.get_paginator.return_value = mock_paginator
        mock_db.execute_query.return_value = []

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': '',
            }):
                service_with_env.run_reconciliation('MyTenant')

        # Verify paginate was called with Prefix='MyTenant/'
        paginate_call = mock_paginator.paginate.call_args
        assert paginate_call[1]['Prefix'] == 'MyTenant/'
        assert paginate_call[1]['Bucket'] == 'myadmin-shared'


# ============================================================================
# _reconcile_references (Phase 2)
# ============================================================================

class TestReconcileReferences:
    """Tests for reconciliation Phase 2: Reference verification.

    Req 6 AC 3: Identify stale references pointing to non-existent entities.
    Req 6 AC 7: Remove stale refs and update asset status to ORPHAN when zero refs remain.
    """

    @pytest.fixture
    def service_with_env(self, mock_db):
        """Service with required env vars set."""
        with patch('services.media_asset_service.ParameterService'):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': 'myadmin-pages',
            }):
                svc = MediaAssetService(mock_db)
                return svc

    # --- Happy path: identifies and removes stale references ---

    def test_removes_stale_references_entity_not_found(self, service_with_env, mock_db):
        """AC 3: References pointing to non-existent entities are removed."""
        # execute_query call 1: get all references
        # execute_query call 2: existence check → entity not found
        mock_db.execute_query.side_effect = [
            # Call 1: all references for tenant
            [{'id': 1, 'asset_id': 'ast_001', 'entity_type': 'invoice', 'entity_id': '999'}],
            # Call 2: existence check → not found (empty result)
            [],
        ]

        # Mock transaction for deletion
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_cursor.fetchone.return_value = {'cnt': 0}
        mock_conn = MagicMock()
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        result = service_with_env._reconcile_references('TenantA')

        assert result['stale_removed'] == 1
        assert result['newly_orphaned'] == 1

    def test_keeps_valid_references(self, service_with_env, mock_db):
        """References to existing entities are not removed."""
        mock_db.execute_query.side_effect = [
            # Call 1: references
            [{'id': 1, 'asset_id': 'ast_001', 'entity_type': 'invoice', 'entity_id': '100'}],
            # Call 2: existence check → entity found
            [{'1': 1}],
        ]

        result = service_with_env._reconcile_references('TenantA')

        assert result['stale_removed'] == 0
        assert result['newly_orphaned'] == 0
        # No transaction should be started since no stale refs
        mock_db.transaction.assert_not_called()

    def test_skips_ephemeral_entity_types(self, service_with_env, mock_db):
        """Ephemeral types (report) are skipped, no existence check."""
        mock_db.execute_query.side_effect = [
            # Call 1: references with ephemeral type
            [{'id': 1, 'asset_id': 'ast_001', 'entity_type': 'report', 'entity_id': 'rpt_123'}],
        ]

        result = service_with_env._reconcile_references('TenantA')

        assert result['stale_removed'] == 0
        assert result['newly_orphaned'] == 0
        assert 'report' in result['skipped_types']
        # Only 1 execute_query call (the initial refs query), no existence check
        assert mock_db.execute_query.call_count == 1

    def test_skips_unknown_entity_types(self, service_with_env, mock_db):
        """Unknown entity_types are skipped with warning."""
        mock_db.execute_query.side_effect = [
            # Call 1: references with unknown type
            [{'id': 1, 'asset_id': 'ast_001', 'entity_type': 'unknown_module', 'entity_id': '42'}],
        ]

        result = service_with_env._reconcile_references('TenantA')

        assert result['stale_removed'] == 0
        assert result['newly_orphaned'] == 0
        assert 'unknown_module' in result['skipped_types']

    # --- Orphan status update ---

    def test_asset_marked_orphan_when_all_refs_stale(self, service_with_env, mock_db):
        """AC 7: Asset becomes ORPHAN when its last reference is stale."""
        mock_db.execute_query.side_effect = [
            # Call 1: references — two refs, both for same asset
            [
                {'id': 1, 'asset_id': 'ast_001', 'entity_type': 'invoice', 'entity_id': '100'},
                {'id': 2, 'asset_id': 'ast_001', 'entity_type': 'invoice', 'entity_id': '200'},
            ],
            # Call 2: existence check for entity_id=100 → not found
            [],
            # Call 3: existence check for entity_id=200 → not found
            [],
        ]

        mock_cursor = MagicMock()
        mock_cursor.rowcount = 2  # first call: 2 refs deleted
        mock_cursor.fetchone.return_value = {'cnt': 0}
        mock_conn = MagicMock()

        # Two transactions: one for deletion, one for orphan update
        call_count = [0]

        def mock_enter(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                mock_cursor.rowcount = 2
            elif call_count[0] == 2:
                mock_cursor.rowcount = 1
            return (mock_cursor, mock_conn)

        mock_db.transaction.return_value.__enter__ = MagicMock(side_effect=mock_enter)
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        result = service_with_env._reconcile_references('TenantA')

        assert result['stale_removed'] == 2
        assert result['newly_orphaned'] == 1

    def test_asset_not_orphaned_when_refs_remain(self, service_with_env, mock_db):
        """Asset stays ACTIVE when some references remain after stale removal."""
        mock_db.execute_query.side_effect = [
            # Call 1: references — two refs for same asset, one valid, one stale
            [
                {'id': 1, 'asset_id': 'ast_001', 'entity_type': 'invoice', 'entity_id': '100'},
                {'id': 2, 'asset_id': 'ast_001', 'entity_type': 'invoice', 'entity_id': '200'},
            ],
            # Call 2: existence check for entity_id=100 → found
            [{'1': 1}],
            # Call 3: existence check for entity_id=200 → not found (stale)
            [],
        ]

        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1  # 1 ref deleted
        mock_cursor.fetchone.return_value = {'cnt': 1}  # 1 ref remains
        mock_conn = MagicMock()

        call_count = [0]

        def mock_enter(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                mock_cursor.rowcount = 1
            elif call_count[0] == 2:
                mock_cursor.rowcount = 0  # no orphan update needed
            return (mock_cursor, mock_conn)

        mock_db.transaction.return_value.__enter__ = MagicMock(side_effect=mock_enter)
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        result = service_with_env._reconcile_references('TenantA')

        assert result['stale_removed'] == 1
        assert result['newly_orphaned'] == 0

    # --- No references ---

    def test_no_references_returns_zero_counts(self, service_with_env, mock_db):
        """No references in the tenant — nothing to do."""
        mock_db.execute_query.side_effect = [
            [],  # No references
        ]

        result = service_with_env._reconcile_references('TenantA')

        assert result['stale_removed'] == 0
        assert result['newly_orphaned'] == 0
        assert result['skipped_types'] == []

    # --- Multiple entity types ---

    def test_handles_multiple_entity_types(self, service_with_env, mock_db):
        """Processes references across different entity types correctly."""
        mock_db.execute_query.side_effect = [
            # Call 1: mixed references
            [
                {'id': 1, 'asset_id': 'ast_001', 'entity_type': 'invoice', 'entity_id': '100'},
                {'id': 2, 'asset_id': 'ast_002', 'entity_type': 'branding', 'entity_id': 'logo_key'},
                {'id': 3, 'asset_id': 'ast_003', 'entity_type': 'report', 'entity_id': 'rpt_1'},
                {'id': 4, 'asset_id': 'ast_004', 'entity_type': 'landing_page', 'entity_id': '55'},
            ],
            # Call 2: invoice existence → found
            [{'1': 1}],
            # Call 3: branding existence → not found (stale)
            [],
            # Call 4: landing_page existence → found
            [{'1': 1}],
        ]

        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_cursor.fetchone.return_value = {'cnt': 0}
        mock_conn = MagicMock()
        mock_db.transaction.return_value.__enter__ = MagicMock(
            return_value=(mock_cursor, mock_conn)
        )
        mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        result = service_with_env._reconcile_references('TenantA')

        assert result['stale_removed'] == 1  # only branding ref is stale
        assert 'report' in result['skipped_types']

    # --- Return structure ---

    def test_return_structure(self, service_with_env, mock_db):
        """Return dict has expected keys."""
        mock_db.execute_query.side_effect = [
            [],  # No references
        ]

        result = service_with_env._reconcile_references('TenantA')

        assert 'stale_removed' in result
        assert 'newly_orphaned' in result
        assert 'skipped_types' in result
        assert isinstance(result['skipped_types'], list)

    # --- Integration: phase2 in run_reconciliation ---

    def test_phase2_included_in_run_reconciliation(self, service_with_env, mock_db):
        """run_reconciliation result includes phase2."""
        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = MagicMock()
        mock_s3.get_paginator.return_value.paginate.return_value = [{}]

        # First call is phase1 registry query, second is phase2 refs query
        mock_db.execute_query.side_effect = [
            [],  # phase1: registry rows
            [],  # phase2: references
        ]

        # Patch phase3 so this test focuses on phase2
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': '',
            }):
                result = service_with_env.run_reconciliation('TenantA')

        assert 'phase2' in result
        assert result['phase2']['stale_removed'] == 0
        assert result['phase2']['newly_orphaned'] == 0

    # --- Tenant isolation ---

    def test_refs_query_scoped_to_tenant(self, service_with_env, mock_db):
        """Phase 2 queries are scoped to the tenant's administration."""
        mock_db.execute_query.side_effect = [
            [],  # No references
        ]

        service_with_env._reconcile_references('SpecificTenant')

        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'administration = %s' in query
        assert params == ('SpecificTenant',)


# ============================================================================
# Reconciliation — Phase 3: Transition Eligible
# ============================================================================

class TestReconcilePhase3:
    """Tests for run_reconciliation Phase 3: transition_eligible integration.

    Verifies that run_reconciliation includes phase3 which calls
    transition_eligible to move orphans past retention to DELETION_ELIGIBLE.
    """

    @pytest.fixture
    def service_with_env(self, mock_db):
        """Service with required env vars set."""
        with patch('services.media_asset_service.ParameterService'):
            with patch.dict(os.environ, {
                'S3_SHARED_BUCKET': 'myadmin-shared',
                'LANDING_PAGES_BUCKET': 'myadmin-pages',
            }):
                svc = MediaAssetService(mock_db)
                return svc

    def test_phase3_included_in_run_reconciliation(self, service_with_env, mock_db):
        """run_reconciliation result includes phase3 from transition_eligible."""
        mock_s3 = MagicMock()
        mock_s3.get_paginator.return_value = MagicMock()
        mock_s3.get_paginator.return_value.paginate.return_value = [{}]

        # Patch phase1 and phase2 so this test focuses on phase3 integration
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 0, 'total_registry': 0}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 3}
        )

        result = service_with_env.run_reconciliation('TenantA')

        assert 'phase3' in result
        assert result['phase3']['success'] is True
        assert result['phase3']['transitioned'] == 3

    def test_phase3_calls_transition_eligible_with_tenant(self, service_with_env, mock_db):
        """phase3 calls transition_eligible with the correct tenant argument."""
        # Patch phase1 and phase2
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 0, 'total_registry': 0}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        service_with_env.run_reconciliation('MyTenant')

        service_with_env.transition_eligible.assert_called_once_with('MyTenant')


# ============================================================================
# _build_reconciliation_report
# ============================================================================

class TestBuildReconciliationReport:
    """Tests for the reconciliation report format (Req 6 AC 4)."""

    @pytest.fixture
    def service_with_env(self, mock_db):
        with patch('services.media_asset_service.ParameterService'):
            with patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-bucket'}):
                return MediaAssetService(mock_db)

    def test_report_contains_all_required_keys(self, service_with_env):
        """Report contains all keys from AC 4."""
        phase1 = {'unregistered': [], 'missing': [], 'total_s3': 50, 'total_registry': 45}
        phase2 = {'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        phase3 = {'success': True, 'transitioned': 0}

        report = service_with_env._build_reconciliation_report('TenantA', phase1, phase2, phase3)

        expected_keys = {
            'administration', 'timestamp', 'total_assets',
            'consistent', 'unregistered', 'missing',
            'stale_references', 'newly_eligible',
        }
        assert set(report.keys()) == expected_keys

    def test_report_administration_matches_tenant(self, service_with_env):
        """Report includes the correct administration value."""
        phase1 = {'unregistered': [], 'missing': [], 'total_s3': 10, 'total_registry': 10}
        phase2 = {'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        phase3 = {'success': True, 'transitioned': 0}

        report = service_with_env._build_reconciliation_report('GoodwinSolutions', phase1, phase2, phase3)

        assert report['administration'] == 'GoodwinSolutions'

    def test_report_timestamp_is_iso8601(self, service_with_env):
        """Report timestamp is in ISO 8601 format."""
        phase1 = {'unregistered': [], 'missing': [], 'total_s3': 0, 'total_registry': 0}
        phase2 = {'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        phase3 = {'success': True, 'transitioned': 0}

        report = service_with_env._build_reconciliation_report('TenantA', phase1, phase2, phase3)

        # Should match YYYY-MM-DDTHH:MM:SSZ format
        from datetime import datetime as dt
        ts = report['timestamp']
        assert ts.endswith('Z')
        # Should parse without error
        dt.strptime(ts, '%Y-%m-%dT%H:%M:%SZ')

    def test_report_total_assets_from_phase1_registry(self, service_with_env):
        """total_assets equals phase1 total_registry count."""
        phase1 = {'unregistered': [{'s3_key': 'a'}], 'missing': [], 'total_s3': 250, 'total_registry': 245}
        phase2 = {'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        phase3 = {'success': True, 'transitioned': 0}

        report = service_with_env._build_reconciliation_report('TenantA', phase1, phase2, phase3)

        assert report['total_assets'] == 245

    def test_report_consistent_is_total_minus_missing(self, service_with_env):
        """consistent = total_assets - missing count."""
        missing_list = [
            {'s3_key': 'key1', 'bucket': 'b'},
            {'s3_key': 'key2', 'bucket': 'b'},
            {'s3_key': 'key3', 'bucket': 'b'},
        ]
        phase1 = {'unregistered': [], 'missing': missing_list, 'total_s3': 200, 'total_registry': 245}
        phase2 = {'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        phase3 = {'success': True, 'transitioned': 0}

        report = service_with_env._build_reconciliation_report('TenantA', phase1, phase2, phase3)

        assert report['consistent'] == 242  # 245 - 3

    def test_report_unregistered_count(self, service_with_env):
        """unregistered equals the length of phase1 unregistered list."""
        unregistered_list = [
            {'s3_key': 'u1', 'bucket': 'b'},
            {'s3_key': 'u2', 'bucket': 'b'},
        ]
        phase1 = {'unregistered': unregistered_list, 'missing': [], 'total_s3': 100, 'total_registry': 98}
        phase2 = {'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        phase3 = {'success': True, 'transitioned': 0}

        report = service_with_env._build_reconciliation_report('TenantA', phase1, phase2, phase3)

        assert report['unregistered'] == 2

    def test_report_missing_count(self, service_with_env):
        """missing equals the length of phase1 missing list."""
        missing_list = [
            {'s3_key': 'm1', 'bucket': 'b'},
        ]
        phase1 = {'unregistered': [], 'missing': missing_list, 'total_s3': 50, 'total_registry': 51}
        phase2 = {'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        phase3 = {'success': True, 'transitioned': 0}

        report = service_with_env._build_reconciliation_report('TenantA', phase1, phase2, phase3)

        assert report['missing'] == 1

    def test_report_stale_references_from_phase2(self, service_with_env):
        """stale_references equals phase2 stale_removed count."""
        phase1 = {'unregistered': [], 'missing': [], 'total_s3': 100, 'total_registry': 100}
        phase2 = {'stale_removed': 5, 'newly_orphaned': 2, 'skipped_types': []}
        phase3 = {'success': True, 'transitioned': 0}

        report = service_with_env._build_reconciliation_report('TenantA', phase1, phase2, phase3)

        assert report['stale_references'] == 5

    def test_report_newly_eligible_from_phase3(self, service_with_env):
        """newly_eligible equals phase3 transitioned count."""
        phase1 = {'unregistered': [], 'missing': [], 'total_s3': 100, 'total_registry': 100}
        phase2 = {'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        phase3 = {'success': True, 'transitioned': 7}

        report = service_with_env._build_reconciliation_report('TenantA', phase1, phase2, phase3)

        assert report['newly_eligible'] == 7

    def test_report_full_scenario(self, service_with_env):
        """Full scenario with all non-zero counts from the spec example."""
        phase1 = {
            'unregistered': [{'s3_key': f'u{i}', 'bucket': 'b'} for i in range(10)],
            'missing': [{'s3_key': f'm{i}', 'bucket': 'b'} for i in range(3)],
            'total_s3': 252,
            'total_registry': 245,
        }
        phase2 = {'stale_removed': 5, 'newly_orphaned': 3, 'skipped_types': ['report']}
        phase3 = {'success': True, 'transitioned': 2}

        report = service_with_env._build_reconciliation_report('TenantA', phase1, phase2, phase3)

        assert report['administration'] == 'TenantA'
        assert report['total_assets'] == 245
        assert report['consistent'] == 242  # 245 - 3 missing
        assert report['unregistered'] == 10
        assert report['missing'] == 3
        assert report['stale_references'] == 5
        assert report['newly_eligible'] == 2


# ============================================================================
# run_reconciliation — summary and cache
# ============================================================================

class TestReconciliationReportIntegration:
    """Tests that run_reconciliation includes summary and stores in cache."""

    @pytest.fixture
    def service_with_env(self, mock_db):
        with patch('services.media_asset_service.ParameterService'):
            with patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-bucket'}):
                return MediaAssetService(mock_db)

    def test_run_reconciliation_includes_summary(self, service_with_env, mock_db):
        """run_reconciliation result includes a 'summary' key."""
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 10, 'total_registry': 10}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        result = service_with_env.run_reconciliation('TenantA')

        assert 'summary' in result
        assert result['summary']['administration'] == 'TenantA'
        assert result['summary']['total_assets'] == 10

    def test_run_reconciliation_stores_in_cache(self, service_with_env, mock_db):
        """run_reconciliation stores summary in _last_reconciliation cache."""
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 20, 'total_registry': 20}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 1, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        service_with_env.run_reconciliation('TenantA')

        assert 'TenantA' in service_with_env._last_reconciliation
        cached = service_with_env._last_reconciliation['TenantA']
        assert cached['administration'] == 'TenantA'
        assert cached['total_assets'] == 20
        assert cached['stale_references'] == 1

    def test_run_reconciliation_cache_per_tenant(self, service_with_env, mock_db):
        """Each tenant gets its own cached report."""
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 5, 'total_registry': 5}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        service_with_env.run_reconciliation('TenantA')
        service_with_env.run_reconciliation('TenantB')

        assert 'TenantA' in service_with_env._last_reconciliation
        assert 'TenantB' in service_with_env._last_reconciliation
        assert service_with_env._last_reconciliation['TenantA']['administration'] == 'TenantA'
        assert service_with_env._last_reconciliation['TenantB']['administration'] == 'TenantB'

    def test_run_reconciliation_cache_overwrites_previous(self, service_with_env, mock_db):
        """Running reconciliation again for same tenant overwrites cached report."""
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 5, 'total_registry': 5}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        service_with_env.run_reconciliation('TenantA')

        # Run again with different results
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [{'s3_key': 'x'}], 'missing': [], 'total_s3': 6, 'total_registry': 5}
        )
        service_with_env.run_reconciliation('TenantA')

        cached = service_with_env._last_reconciliation['TenantA']
        assert cached['unregistered'] == 1  # updated value


# ============================================================================
# SSE Progress Events — run_reconciliation_with_progress
# ============================================================================

class TestRunReconciliationWithProgress:
    """Tests for the SSE progress generator method.

    Verifies that run_reconciliation_with_progress yields the correct sequence
    of progress events matching the defined phases:
    scanning_s3, checking_registry, verifying_references, transitioning, complete
    """

    @pytest.fixture
    def service_with_env(self, mock_db):
        with patch.dict(os.environ, {
            'S3_SHARED_BUCKET': 'test-shared-bucket',
            'LANDING_PAGES_BUCKET': 'test-pages-bucket',
        }):
            with patch('services.media_asset_service.ParameterService'):
                return MediaAssetService(mock_db)

    def test_yields_five_events_in_correct_order(self, service_with_env, mock_db):
        """Generator yields exactly 5 events in the prescribed phase order."""
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 10, 'total_registry': 10}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        events = list(service_with_env.run_reconciliation_with_progress('TenantA'))

        assert len(events) == 5
        assert events[0]['phase'] == 'scanning_s3'
        assert events[1]['phase'] == 'checking_registry'
        assert events[2]['phase'] == 'verifying_references'
        assert events[3]['phase'] == 'transitioning'
        assert events[4]['phase'] == 'complete'

    def test_first_four_events_are_progress_type(self, service_with_env, mock_db):
        """First four events have type='progress'."""
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 5, 'total_registry': 5}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        events = list(service_with_env.run_reconciliation_with_progress('TenantA'))

        for event in events[:4]:
            assert event['type'] == 'progress'

    def test_last_event_is_complete_type(self, service_with_env, mock_db):
        """Final event has type='complete' and includes summary."""
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 5, 'total_registry': 5}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        events = list(service_with_env.run_reconciliation_with_progress('TenantA'))

        last = events[-1]
        assert last['type'] == 'complete'
        assert last['phase'] == 'complete'
        assert 'summary' in last
        assert last['summary']['administration'] == 'TenantA'

    def test_scanning_s3_event_has_message(self, service_with_env, mock_db):
        """scanning_s3 event includes a human-readable message."""
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 0, 'total_registry': 0}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        events = list(service_with_env.run_reconciliation_with_progress('TenantA'))

        assert events[0]['message'] == 'Scanning S3 buckets...'

    def test_checking_registry_includes_totals(self, service_with_env, mock_db):
        """checking_registry event includes total_s3 and total_registry from phase1."""
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [{'s3_key': 'a'}], 'missing': [{'s3_key': 'b'}],
                          'total_s3': 42, 'total_registry': 40}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        events = list(service_with_env.run_reconciliation_with_progress('TenantA'))

        registry_event = events[1]
        assert registry_event['total_s3'] == 42
        assert registry_event['total_registry'] == 40
        assert registry_event['unregistered'] == 1
        assert registry_event['missing'] == 1

    def test_verifying_references_includes_stale_count(self, service_with_env, mock_db):
        """verifying_references event includes stale_found from phase2."""
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 5, 'total_registry': 5}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 3, 'newly_orphaned': 2, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        events = list(service_with_env.run_reconciliation_with_progress('TenantA'))

        ref_event = events[2]
        assert ref_event['stale_found'] == 3
        assert ref_event['newly_orphaned'] == 2

    def test_transitioning_includes_count(self, service_with_env, mock_db):
        """transitioning event includes the number of assets transitioned."""
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 5, 'total_registry': 5}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 7}
        )

        events = list(service_with_env.run_reconciliation_with_progress('TenantA'))

        transition_event = events[3]
        assert transition_event['transitioned'] == 7

    def test_complete_summary_matches_build_report(self, service_with_env, mock_db):
        """Complete event summary has same structure as _build_reconciliation_report."""
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [{'s3_key': 'x'}], 'missing': [],
                          'total_s3': 11, 'total_registry': 10}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 2, 'newly_orphaned': 1, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 3}
        )

        events = list(service_with_env.run_reconciliation_with_progress('TenantA'))

        summary = events[-1]['summary']
        assert summary['administration'] == 'TenantA'
        assert summary['total_assets'] == 10
        assert summary['consistent'] == 10  # total_registry - missing
        assert summary['unregistered'] == 1
        assert summary['missing'] == 0
        assert summary['stale_references'] == 2
        assert summary['newly_eligible'] == 3
        assert 'timestamp' in summary

    def test_stores_summary_in_cache(self, service_with_env, mock_db):
        """After generator is fully consumed, summary is cached in _last_reconciliation."""
        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 5, 'total_registry': 5}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        # Consume all events
        list(service_with_env.run_reconciliation_with_progress('TenantA'))

        assert 'TenantA' in service_with_env._last_reconciliation
        cached = service_with_env._last_reconciliation['TenantA']
        assert cached['administration'] == 'TenantA'

    def test_is_a_generator(self, service_with_env, mock_db):
        """Method returns a generator (lazy evaluation for SSE streaming)."""
        import types

        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 0, 'total_registry': 0}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        gen = service_with_env.run_reconciliation_with_progress('TenantA')
        assert isinstance(gen, types.GeneratorType)

    def test_events_emitted_between_phases(self, service_with_env, mock_db):
        """Progress events are yielded between phase executions (lazy/streaming).

        Verifies that _reconcile_s3_scan is not called until after the first
        event is consumed, confirming lazy evaluation.
        """
        call_order = []

        def mock_s3_scan(tenant):
            call_order.append('s3_scan')
            return {'unregistered': [], 'missing': [], 'total_s3': 0, 'total_registry': 0}

        def mock_refs(tenant):
            call_order.append('refs')
            return {'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}

        def mock_transition(tenant):
            call_order.append('transition')
            return {'success': True, 'transitioned': 0}

        service_with_env._reconcile_s3_scan = mock_s3_scan
        service_with_env._reconcile_references = mock_refs
        service_with_env.transition_eligible = mock_transition

        gen = service_with_env.run_reconciliation_with_progress('TenantA')

        # After creating generator, no phases have run
        assert call_order == []

        # First next() yields scanning_s3 event, before s3_scan runs
        event1 = next(gen)
        assert event1['phase'] == 'scanning_s3'
        assert call_order == []  # s3_scan not yet called

        # Second next() runs s3_scan, then yields checking_registry
        event2 = next(gen)
        assert event2['phase'] == 'checking_registry'
        assert call_order == ['s3_scan']

        # Third next() runs refs, yields verifying_references
        event3 = next(gen)
        assert event3['phase'] == 'verifying_references'
        assert call_order == ['s3_scan', 'refs']

        # Fourth next() runs transition, yields transitioning
        event4 = next(gen)
        assert event4['phase'] == 'transitioning'
        assert call_order == ['s3_scan', 'refs', 'transition']

        # Fifth next() yields complete
        event5 = next(gen)
        assert event5['phase'] == 'complete'

    def test_all_events_are_json_serializable(self, service_with_env, mock_db):
        """All yielded events can be serialized with json.dumps (SSE requirement)."""
        import json

        service_with_env._reconcile_s3_scan = MagicMock(
            return_value={'unregistered': [], 'missing': [], 'total_s3': 5, 'total_registry': 5}
        )
        service_with_env._reconcile_references = MagicMock(
            return_value={'stale_removed': 0, 'newly_orphaned': 0, 'skipped_types': []}
        )
        service_with_env.transition_eligible = MagicMock(
            return_value={'success': True, 'transitioned': 0}
        )

        events = list(service_with_env.run_reconciliation_with_progress('TenantA'))

        for event in events:
            # Should not raise
            serialized = json.dumps(event, default=str)
            assert isinstance(serialized, str)


# ============================================================================
# search_assets
# ============================================================================

class TestSearchAssets:
    """Tests for search_assets service method."""

    @pytest.fixture
    def service_with_env(self, mock_db):
        """Service with required env vars set."""
        with patch('services.media_asset_service.ParameterService'):
            with patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-bucket'}):
                svc = MediaAssetService(mock_db)
                return svc

    # --- Basic search returns paginated results ---

    def test_search_returns_success_with_empty_results(self, service_with_env, mock_db):
        """Empty result set returns success with empty data array."""
        mock_db.execute_query.side_effect = [
            [{'total': 0}],  # count query
            [],               # data query
        ]

        result = service_with_env.search_assets('TenantA', {})

        assert result['success'] is True
        assert result['data'] == []
        assert result['pagination']['total'] == 0
        assert result['pagination']['total_pages'] == 0
        assert result['pagination']['page'] == 1
        assert result['pagination']['page_size'] == 20

    def test_search_returns_assets_with_reference_count(self, service_with_env, mock_db):
        """Results include reference_count from subquery."""
        mock_db.execute_query.side_effect = [
            [{'total': 1}],
            [{
                'id': 'ast_ABC123',
                'original_filename': 'invoice.pdf',
                'mime_type': 'application/pdf',
                'file_size': 245000,
                'category': 'invoices',
                'media_type': 'document',
                'status': 'ACTIVE',
                'created_at': '2025-03-15 10:30:00',
                'bucket': 'test-bucket',
                's3_key': 'TenantA/invoices/ast_ABC123_invoice.pdf',
                'reference_count': 2,
            }],
        ]

        result = service_with_env.search_assets('TenantA', {})

        assert result['success'] is True
        assert len(result['data']) == 1
        asset = result['data'][0]
        assert asset['id'] == 'ast_ABC123'
        assert asset['reference_count'] == 2
        assert asset['presigned_url'] is None  # documents don't get presigned URLs

    def test_search_image_includes_presigned_url(self, service_with_env, mock_db):
        """Image assets include a presigned_url in results."""
        mock_db.execute_query.side_effect = [
            [{'total': 1}],
            [{
                'id': 'ast_IMG001',
                'original_filename': 'logo.png',
                'mime_type': 'image/png',
                'file_size': 50000,
                'category': 'branding',
                'media_type': 'image',
                'status': 'ACTIVE',
                'created_at': '2025-03-15 10:30:00',
                'bucket': 'test-bucket',
                's3_key': 'TenantA/branding/ast_IMG001_logo.png',
                'reference_count': 1,
            }],
        ]

        with patch.object(service_with_env, '_get_presigned_url', return_value='https://presigned.example.com/logo.png'):
            result = service_with_env.search_assets('TenantA', {})

        assert result['data'][0]['presigned_url'] == 'https://presigned.example.com/logo.png'

    # --- Filter: q (text search) ---

    def test_search_with_q_filter(self, service_with_env, mock_db):
        """The q filter adds a LIKE clause on original_filename."""
        mock_db.execute_query.side_effect = [
            [{'total': 0}],
            [],
        ]

        service_with_env.search_assets('TenantA', {'q': 'invoice'})

        # Verify the count query included the LIKE param
        count_call = mock_db.execute_query.call_args_list[0]
        assert '%invoice%' in count_call[0][1]

    # --- Filter: category (exact match) ---

    def test_search_with_category_filter(self, service_with_env, mock_db):
        """Category filter restricts results to a single category."""
        mock_db.execute_query.side_effect = [
            [{'total': 0}],
            [],
        ]

        service_with_env.search_assets('TenantA', {'category': 'branding'})

        count_call = mock_db.execute_query.call_args_list[0]
        assert 'branding' in count_call[0][1]

    # --- Filter: media_type (exact match) ---

    def test_search_with_media_type_filter(self, service_with_env, mock_db):
        """Media type filter restricts results to a single media type."""
        mock_db.execute_query.side_effect = [
            [{'total': 0}],
            [],
        ]

        service_with_env.search_assets('TenantA', {'media_type': 'document'})

        count_call = mock_db.execute_query.call_args_list[0]
        assert 'document' in count_call[0][1]

    # --- Pagination ---

    def test_search_pagination_defaults(self, service_with_env, mock_db):
        """Default pagination: page 1, page_size 20."""
        mock_db.execute_query.side_effect = [
            [{'total': 50}],
            [],
        ]

        result = service_with_env.search_assets('TenantA', {})

        assert result['pagination']['page'] == 1
        assert result['pagination']['page_size'] == 20
        assert result['pagination']['total'] == 50
        assert result['pagination']['total_pages'] == 3

    def test_search_pagination_custom_page_and_size(self, service_with_env, mock_db):
        """Custom page and page_size are respected."""
        mock_db.execute_query.side_effect = [
            [{'total': 100}],
            [],
        ]

        result = service_with_env.search_assets('TenantA', {'page': '3', 'page_size': '10'})

        assert result['pagination']['page'] == 3
        assert result['pagination']['page_size'] == 10
        assert result['pagination']['total_pages'] == 10

    def test_search_page_size_capped_at_100(self, service_with_env, mock_db):
        """page_size is capped at 100 regardless of input."""
        mock_db.execute_query.side_effect = [
            [{'total': 0}],
            [],
        ]

        result = service_with_env.search_assets('TenantA', {'page_size': '500'})

        assert result['pagination']['page_size'] == 100

    def test_search_page_minimum_is_1(self, service_with_env, mock_db):
        """page is at minimum 1, even if 0 or negative is passed."""
        mock_db.execute_query.side_effect = [
            [{'total': 0}],
            [],
        ]

        result = service_with_env.search_assets('TenantA', {'page': '0'})

        assert result['pagination']['page'] == 1

    # --- Sort ---

    def test_search_sort_default_created_at_desc(self, service_with_env, mock_db):
        """Default sort is created_at DESC."""
        mock_db.execute_query.side_effect = [
            [{'total': 0}],
            [],
        ]

        service_with_env.search_assets('TenantA', {})

        data_call = mock_db.execute_query.call_args_list[1]
        query = data_call[0][0]
        assert 'ORDER BY a.created_at DESC' in query

    def test_search_sort_by_filename_asc(self, service_with_env, mock_db):
        """Sort by original_filename ascending."""
        mock_db.execute_query.side_effect = [
            [{'total': 0}],
            [],
        ]

        service_with_env.search_assets('TenantA', {'sort': 'original_filename', 'order': 'asc'})

        data_call = mock_db.execute_query.call_args_list[1]
        query = data_call[0][0]
        assert 'ORDER BY a.original_filename ASC' in query

    def test_search_sort_invalid_column_defaults_to_created_at(self, service_with_env, mock_db):
        """Invalid sort column falls back to created_at."""
        mock_db.execute_query.side_effect = [
            [{'total': 0}],
            [],
        ]

        service_with_env.search_assets('TenantA', {'sort': 'DROP TABLE; --'})

        data_call = mock_db.execute_query.call_args_list[1]
        query = data_call[0][0]
        assert 'ORDER BY a.created_at' in query

    def test_search_invalid_order_defaults_to_desc(self, service_with_env, mock_db):
        """Invalid order value falls back to DESC."""
        mock_db.execute_query.side_effect = [
            [{'total': 0}],
            [],
        ]

        service_with_env.search_assets('TenantA', {'order': 'INVALID'})

        data_call = mock_db.execute_query.call_args_list[1]
        query = data_call[0][0]
        assert 'DESC' in query

    # --- Tenant isolation ---

    def test_search_always_filters_by_tenant(self, service_with_env, mock_db):
        """All queries include administration = tenant for isolation."""
        mock_db.execute_query.side_effect = [
            [{'total': 0}],
            [],
        ]

        service_with_env.search_assets('TenantA', {})

        # Both count and data queries should include tenant
        for call in mock_db.execute_query.call_args_list:
            assert 'TenantA' in call[0][1]

    # --- Non-image types get null presigned_url ---

    def test_search_document_has_null_presigned_url(self, service_with_env, mock_db):
        """Document and video types return null for presigned_url."""
        mock_db.execute_query.side_effect = [
            [{'total': 2}],
            [
                {
                    'id': 'ast_DOC1',
                    'original_filename': 'report.pdf',
                    'mime_type': 'application/pdf',
                    'file_size': 100000,
                    'category': 'invoices',
                    'media_type': 'document',
                    'status': 'ACTIVE',
                    'created_at': '2025-01-01 00:00:00',
                    'bucket': 'test-bucket',
                    's3_key': 'TenantA/invoices/ast_DOC1_report.pdf',
                    'reference_count': 1,
                },
                {
                    'id': 'ast_VID1',
                    'original_filename': 'clip.mp4',
                    'mime_type': 'video/mp4',
                    'file_size': 5000000,
                    'category': 'landing-pages',
                    'media_type': 'video',
                    'status': 'ACTIVE',
                    'created_at': '2025-01-02 00:00:00',
                    'bucket': 'test-bucket',
                    's3_key': 'TenantA/landing-pages/ast_VID1_clip.mp4',
                    'reference_count': 0,
                },
            ],
        ]

        result = service_with_env.search_assets('TenantA', {})

        assert result['data'][0]['presigned_url'] is None
        assert result['data'][1]['presigned_url'] is None

    # --- Combined filters ---

    def test_search_with_multiple_filters(self, service_with_env, mock_db):
        """Multiple filters are combined with AND."""
        mock_db.execute_query.side_effect = [
            [{'total': 0}],
            [],
        ]

        service_with_env.search_assets('TenantA', {
            'q': 'logo',
            'category': 'branding',
            'media_type': 'image',
        })

        count_call = mock_db.execute_query.call_args_list[0]
        query = count_call[0][0]
        assert 'original_filename LIKE' in query
        assert 'category' in query
        assert 'media_type' in query


# ============================================================================
# get_retention_settings
# ============================================================================

class TestGetRetentionSettings:
    """Tests for get_retention_settings: resolves values and source indicators."""

    @pytest.fixture
    def service_with_ps(self, mock_db):
        """Service with a mocked ParameterService."""
        mock_ps = MagicMock()
        with patch('services.media_asset_service.ParameterService', return_value=mock_ps):
            svc = MediaAssetService(mock_db, parameter_service=mock_ps)
        return svc

    def test_all_system_defaults(self, service_with_ps):
        """When no tenant overrides exist, all values come from CODE_DEFAULTS."""
        service_with_ps.ps._resolve_from_db.return_value = None

        result = service_with_ps.get_retention_settings('TenantA')

        assert result['success'] is True
        assert result['data']['invoices_days'] == {'value': 2555, 'source': 'system_default'}
        assert result['data']['branding_days'] == {'value': 30, 'source': 'system_default'}
        assert result['data']['templates_days'] == {'value': 90, 'source': 'system_default'}
        assert result['data']['landing_pages_days'] == {'value': 7, 'source': 'system_default'}
        assert result['data']['landing_pages_media_days'] == {'value': 30, 'source': 'system_default'}

    def test_tenant_override_detected(self, service_with_ps):
        """When tenant has an override in DB, source is 'tenant_override'."""
        def resolve_side_effect(scope, scope_id, namespace, key):
            if key == 'branding_days':
                return 60
            return None

        service_with_ps.ps._resolve_from_db.side_effect = resolve_side_effect

        result = service_with_ps.get_retention_settings('TenantA')

        assert result['data']['branding_days'] == {'value': 60, 'source': 'tenant_override'}
        assert result['data']['invoices_days']['source'] == 'system_default'

    def test_multiple_overrides(self, service_with_ps):
        """Multiple tenant overrides are correctly identified."""
        def resolve_side_effect(scope, scope_id, namespace, key):
            overrides = {'branding_days': 60, 'templates_days': 120}
            return overrides.get(key)

        service_with_ps.ps._resolve_from_db.side_effect = resolve_side_effect

        result = service_with_ps.get_retention_settings('TenantA')

        assert result['data']['branding_days'] == {'value': 60, 'source': 'tenant_override'}
        assert result['data']['templates_days'] == {'value': 120, 'source': 'tenant_override'}
        assert result['data']['invoices_days']['source'] == 'system_default'

    def test_returns_all_five_keys(self, service_with_ps):
        """Result always contains all 5 retention keys."""
        service_with_ps.ps._resolve_from_db.return_value = None

        result = service_with_ps.get_retention_settings('TenantA')

        assert len(result['data']) == 5
        expected_keys = {'invoices_days', 'branding_days', 'templates_days',
                         'landing_pages_days', 'landing_pages_media_days'}
        assert set(result['data'].keys()) == expected_keys

    def test_calls_resolve_from_db_with_tenant_scope(self, service_with_ps):
        """Verifies the DB lookup uses tenant scope."""
        service_with_ps.ps._resolve_from_db.return_value = None

        service_with_ps.get_retention_settings('MyTenant')

        for call in service_with_ps.ps._resolve_from_db.call_args_list:
            assert call[0][0] == 'tenant'
            assert call[0][1] == 'MyTenant'
            assert call[0][2] == 'asset_retention'


# ============================================================================
# update_retention_settings
# ============================================================================

class TestUpdateRetentionSettings:
    """Tests for update_retention_settings: validates and saves tenant overrides."""

    @pytest.fixture
    def service_with_ps(self, mock_db):
        """Service with a mocked ParameterService."""
        mock_ps = MagicMock()
        with patch('services.media_asset_service.ParameterService', return_value=mock_ps):
            svc = MediaAssetService(mock_db, parameter_service=mock_ps)
        return svc

    def test_valid_single_update(self, service_with_ps):
        """Single valid key updates successfully."""
        result = service_with_ps.update_retention_settings('TenantA', {'branding_days': 60})

        assert result == {'success': True, 'updated': ['branding_days']}
        service_with_ps.ps.set_param.assert_called_once_with(
            scope='tenant',
            scope_id='TenantA',
            namespace='asset_retention',
            key='branding_days',
            value=60,
            value_type='number',
        )

    def test_valid_multiple_updates(self, service_with_ps):
        """Multiple valid keys update successfully."""
        result = service_with_ps.update_retention_settings(
            'TenantA', {'branding_days': 60, 'templates_days': 120}
        )

        assert result['success'] is True
        assert set(result['updated']) == {'branding_days', 'templates_days'}
        assert service_with_ps.ps.set_param.call_count == 2

    def test_invalid_key_raises_valueerror(self, service_with_ps):
        """Invalid key raises ValueError."""
        with pytest.raises(ValueError, match="Invalid retention keys"):
            service_with_ps.update_retention_settings('TenantA', {'invalid_key': 30})

    def test_negative_value_raises_valueerror(self, service_with_ps):
        """Negative value raises ValueError."""
        with pytest.raises(ValueError, match="must be a positive integer"):
            service_with_ps.update_retention_settings('TenantA', {'branding_days': -1})

    def test_zero_value_raises_valueerror(self, service_with_ps):
        """Zero value raises ValueError."""
        with pytest.raises(ValueError, match="must be a positive integer"):
            service_with_ps.update_retention_settings('TenantA', {'branding_days': 0})

    def test_non_numeric_value_raises_valueerror(self, service_with_ps):
        """Non-numeric value raises ValueError."""
        with pytest.raises(ValueError, match="must be a positive integer"):
            service_with_ps.update_retention_settings('TenantA', {'branding_days': 'abc'})

    def test_float_value_coerced_to_int(self, service_with_ps):
        """Float value is accepted and coerced to int."""
        result = service_with_ps.update_retention_settings('TenantA', {'branding_days': 60.5})

        assert result['success'] is True
        service_with_ps.ps.set_param.assert_called_once_with(
            scope='tenant',
            scope_id='TenantA',
            namespace='asset_retention',
            key='branding_days',
            value=60,
            value_type='number',
        )

    def test_all_keys_are_valid(self, service_with_ps):
        """All 5 retention keys can be updated."""
        updates = {
            'invoices_days': 3650,
            'branding_days': 60,
            'templates_days': 180,
            'landing_pages_days': 14,
            'landing_pages_media_days': 60,
        }
        result = service_with_ps.update_retention_settings('TenantA', updates)

        assert result['success'] is True
        assert len(result['updated']) == 5


# ============================================================================
# import_legacy_assets
# ============================================================================

class TestImportLegacyAssets:
    """Tests for import_legacy_assets (Req 8)."""

    @pytest.fixture
    def service_with_env(self, mock_db):
        """Service with required env vars set."""
        with patch('services.media_asset_service.ParameterService'):
            with patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-bucket'}):
                svc = MediaAssetService(mock_db)
                return svc

    # --- Happy path: new objects imported ---

    def test_import_registers_new_objects(self, service_with_env, mock_db):
        """AC 1, AC 2: Scans S3, inserts new assets with status=ACTIVE."""
        s3_objects = [
            {'key': 'TenantA/invoices/report.pdf', 'size': 12345},
            {'key': 'TenantA/invoices/photo.jpg', 'size': 67890},
        ]
        with patch.object(service_with_env, '_list_s3_objects_detailed', return_value=s3_objects):
            # No existing keys in registry
            mock_db.execute_query.side_effect = [
                [],  # existing_keys query returns empty
                None,  # INSERT for report.pdf
                None,  # INSERT for photo.jpg
            ]

            result = service_with_env.import_legacy_assets('TenantA', 'invoices')

        assert result['success'] is True
        assert result['newly_registered'] == 2
        assert result['already_registered'] == 0
        assert result['total_scanned'] == 2
        assert result['administration'] == 'TenantA'
        assert result['category'] == 'invoices'

    # --- Idempotent: skips already-registered keys ---

    def test_import_skips_existing_keys(self, service_with_env, mock_db):
        """AC 5: Objects whose s3_key already matches are skipped."""
        s3_objects = [
            {'key': 'TenantA/invoices/report.pdf', 'size': 12345},
            {'key': 'TenantA/invoices/old.pdf', 'size': 5000},
        ]
        with patch.object(service_with_env, '_list_s3_objects_detailed', return_value=s3_objects):
            # 'old.pdf' is already registered
            mock_db.execute_query.side_effect = [
                [{'s3_key': 'TenantA/invoices/old.pdf'}],  # existing_keys
                None,  # INSERT for report.pdf only
            ]

            result = service_with_env.import_legacy_assets('TenantA', 'invoices')

        assert result['newly_registered'] == 1
        assert result['already_registered'] == 1

    # --- All objects already registered ---

    def test_import_all_already_registered(self, service_with_env, mock_db):
        """AC 5: When all objects are already registered, nothing is inserted."""
        s3_objects = [
            {'key': 'TenantA/invoices/report.pdf', 'size': 12345},
        ]
        with patch.object(service_with_env, '_list_s3_objects_detailed', return_value=s3_objects):
            mock_db.execute_query.side_effect = [
                [{'s3_key': 'TenantA/invoices/report.pdf'}],  # already registered
            ]

            result = service_with_env.import_legacy_assets('TenantA', 'invoices')

        assert result['newly_registered'] == 0
        assert result['already_registered'] == 1
        assert result['total_scanned'] == 1

    # --- Unclassifiable extension is skipped ---

    def test_import_skips_unclassifiable_objects(self, service_with_env, mock_db):
        """AC 8: Objects with unknown extension are skipped and reported."""
        s3_objects = [
            {'key': 'TenantA/invoices/data.csv', 'size': 5000},
            {'key': 'TenantA/invoices/report.pdf', 'size': 12345},
        ]
        with patch.object(service_with_env, '_list_s3_objects_detailed', return_value=s3_objects):
            mock_db.execute_query.side_effect = [
                [],  # no existing keys
                None,  # INSERT for report.pdf only
            ]

            result = service_with_env.import_legacy_assets('TenantA', 'invoices')

        assert result['newly_registered'] == 1
        assert len(result['unclassified']) == 1
        assert result['unclassified'][0]['s3_key'] == 'TenantA/invoices/data.csv'
        assert result['unclassified'][0]['filename'] == 'data.csv'
        assert "Unknown extension" in result['unclassified'][0]['reason']

    # --- Empty prefix (no objects in S3) ---

    def test_import_empty_prefix(self, service_with_env, mock_db):
        """When S3 prefix has no objects, return zeroed summary."""
        with patch.object(service_with_env, '_list_s3_objects_detailed', return_value=[]):
            mock_db.execute_query.side_effect = [
                [],  # existing_keys query
            ]

            result = service_with_env.import_legacy_assets('TenantA', 'invoices')

        assert result['success'] is True
        assert result['total_scanned'] == 0
        assert result['newly_registered'] == 0
        assert result['already_registered'] == 0
        assert result['unclassified'] == []

    # --- Summary report structure ---

    def test_import_returns_complete_summary(self, service_with_env, mock_db):
        """AC 6: Return summary with all required fields."""
        s3_objects = [
            {'key': 'TenantA/invoices/a.pdf', 'size': 1000},
            {'key': 'TenantA/invoices/b.jpg', 'size': 2000},
            {'key': 'TenantA/invoices/c.xyz', 'size': 3000},
            {'key': 'TenantA/invoices/d.pdf', 'size': 4000},
        ]
        with patch.object(service_with_env, '_list_s3_objects_detailed', return_value=s3_objects):
            mock_db.execute_query.side_effect = [
                [{'s3_key': 'TenantA/invoices/d.pdf'}],  # d.pdf already registered
                None,  # INSERT a.pdf
                None,  # INSERT b.jpg
            ]

            result = service_with_env.import_legacy_assets('TenantA', 'invoices')

        assert result == {
            'success': True,
            'administration': 'TenantA',
            'category': 'invoices',
            'total_scanned': 4,
            'newly_registered': 2,
            'already_registered': 1,
            'unclassified': [
                {
                    's3_key': 'TenantA/invoices/c.xyz',
                    'filename': 'c.xyz',
                    'reason': "Unknown extension '.xyz'",
                }
            ],
        }

    # --- Asset ID generation (AC 4) ---

    def test_import_generates_ast_ulid_ids(self, service_with_env, mock_db):
        """AC 4: Each imported asset gets an ast_<ULID> id."""
        s3_objects = [
            {'key': 'TenantA/invoices/report.pdf', 'size': 12345},
        ]
        with patch.object(service_with_env, '_list_s3_objects_detailed', return_value=s3_objects):
            mock_db.execute_query.side_effect = [
                [],  # no existing keys
                None,  # INSERT
            ]

            result = service_with_env.import_legacy_assets('TenantA', 'invoices')

        # Verify the INSERT was called with an ast_ prefixed id
        insert_call = mock_db.execute_query.call_args_list[1]
        insert_params = insert_call[0][1]
        asset_id = insert_params[0]
        assert asset_id.startswith('ast_')
        assert len(asset_id) == 30  # 'ast_' + 26-char ULID

    # --- Media type detection ---

    def test_import_detects_image_media_type(self, service_with_env, mock_db):
        """AC 2: Detects image media_type for .jpg files."""
        s3_objects = [
            {'key': 'TenantA/invoices/photo.jpg', 'size': 5000},
        ]
        with patch.object(service_with_env, '_list_s3_objects_detailed', return_value=s3_objects):
            mock_db.execute_query.side_effect = [
                [],  # no existing keys
                None,  # INSERT
            ]

            service_with_env.import_legacy_assets('TenantA', 'invoices')

        insert_call = mock_db.execute_query.call_args_list[1]
        insert_params = insert_call[0][1]
        # Params: (id, tenant, bucket, key, mime_type, size, category, media_type, filename, status, migrated_at, created_at)
        mime_type = insert_params[4]
        media_type = insert_params[7]
        assert mime_type == 'image/jpeg'
        assert media_type == 'image'

    def test_import_detects_document_media_type(self, service_with_env, mock_db):
        """AC 2: Detects document media_type for .pdf files."""
        s3_objects = [
            {'key': 'TenantA/invoices/doc.pdf', 'size': 9000},
        ]
        with patch.object(service_with_env, '_list_s3_objects_detailed', return_value=s3_objects):
            mock_db.execute_query.side_effect = [
                [],
                None,
            ]

            service_with_env.import_legacy_assets('TenantA', 'invoices')

        insert_call = mock_db.execute_query.call_args_list[1]
        insert_params = insert_call[0][1]
        mime_type = insert_params[4]
        media_type = insert_params[7]
        assert mime_type == 'application/pdf'
        assert media_type == 'document'

    def test_import_detects_video_media_type(self, service_with_env, mock_db):
        """AC 2: Detects video media_type for .mp4 files."""
        s3_objects = [
            {'key': 'TenantA/invoices/clip.mp4', 'size': 50000},
        ]
        with patch.object(service_with_env, '_list_s3_objects_detailed', return_value=s3_objects):
            mock_db.execute_query.side_effect = [
                [],
                None,
            ]

            service_with_env.import_legacy_assets('TenantA', 'invoices')

        insert_call = mock_db.execute_query.call_args_list[1]
        insert_params = insert_call[0][1]
        mime_type = insert_params[4]
        media_type = insert_params[7]
        assert mime_type == 'video/mp4'
        assert media_type == 'video'

    def test_import_detects_web_content_media_type(self, service_with_env, mock_db):
        """AC 2: Detects web_content media_type for .html files."""
        s3_objects = [
            {'key': 'TenantA/invoices/page.html', 'size': 2000},
        ]
        with patch.object(service_with_env, '_list_s3_objects_detailed', return_value=s3_objects):
            mock_db.execute_query.side_effect = [
                [],
                None,
            ]

            service_with_env.import_legacy_assets('TenantA', 'invoices')

        insert_call = mock_db.execute_query.call_args_list[1]
        insert_params = insert_call[0][1]
        mime_type = insert_params[4]
        media_type = insert_params[7]
        assert mime_type == 'text/html'
        assert media_type == 'web_content'

    # --- Filename extraction from key ---

    def test_import_extracts_filename_from_key(self, service_with_env, mock_db):
        """AC 2: original_filename extracted from the last path segment."""
        s3_objects = [
            {'key': 'TenantA/invoices/subfolder/my_report.pdf', 'size': 1000},
        ]
        with patch.object(service_with_env, '_list_s3_objects_detailed', return_value=s3_objects):
            mock_db.execute_query.side_effect = [
                [],
                None,
            ]

            service_with_env.import_legacy_assets('TenantA', 'invoices')

        insert_call = mock_db.execute_query.call_args_list[1]
        insert_params = insert_call[0][1]
        original_filename = insert_params[8]
        assert original_filename == 'my_report.pdf'

    # --- Invalid category raises ValueError ---

    def test_import_invalid_category_raises(self, service_with_env):
        """Invalid category raises ValueError before any S3 call."""
        with pytest.raises(ValueError, match="Unknown category"):
            service_with_env.import_legacy_assets('TenantA', 'unknown')

    # --- Tenant isolation (AC 7) ---

    def test_import_scoped_to_tenant(self, service_with_env, mock_db):
        """AC 7: Import uses tenant-scoped prefix and query."""
        s3_objects = [
            {'key': 'MyTenant/invoices/file.pdf', 'size': 1000},
        ]
        with patch.object(service_with_env, '_resolve_bucket', return_value='test-bucket'):
            with patch.object(
                service_with_env, '_list_s3_objects_detailed', return_value=s3_objects
            ) as mock_list:
                mock_db.execute_query.side_effect = [
                    [],  # existing_keys query
                    None,  # INSERT
                ]

                service_with_env.import_legacy_assets('MyTenant', 'invoices')

        # Verify _list_s3_objects_detailed was called with tenant prefix
        mock_list.assert_called_once_with('test-bucket', 'MyTenant/invoices/')

        # Verify the existing_keys query used tenant and category params
        first_query_call = mock_db.execute_query.call_args_list[0]
        assert first_query_call[0][1] == ('MyTenant', 'invoices')

    # --- INSERT params validation ---

    def test_import_insert_params_correct(self, service_with_env, mock_db):
        """AC 2: INSERT contains all required fields with correct values."""
        s3_objects = [
            {'key': 'TenantA/invoices/invoice_2024.pdf', 'size': 45000},
        ]
        with patch.object(service_with_env, '_resolve_bucket', return_value='test-bucket'):
            with patch.object(service_with_env, '_list_s3_objects_detailed', return_value=s3_objects):
                mock_db.execute_query.side_effect = [
                    [],
                    None,
                ]

                service_with_env.import_legacy_assets('TenantA', 'invoices')

        insert_call = mock_db.execute_query.call_args_list[1]
        query = insert_call[0][0]
        params = insert_call[0][1]

        # Verify query contains key fields
        assert 'INSERT INTO s3_assets' in query
        assert 'migrated_at' in query

        # Params: (id, tenant, bucket, key, mime_type, size, category, media_type, filename, status, migrated_at, created_at)
        assert params[0].startswith('ast_')  # id
        assert params[1] == 'TenantA'  # administration
        assert params[2] == 'test-bucket'  # bucket
        assert params[3] == 'TenantA/invoices/invoice_2024.pdf'  # s3_key
        assert params[4] == 'application/pdf'  # mime_type
        assert params[5] == 45000  # file_size
        assert params[6] == 'invoices'  # category
        assert params[7] == 'document'  # media_type
        assert params[8] == 'invoice_2024.pdf'  # original_filename
        assert params[9] == 'ACTIVE'  # status

        # Verify fetch=False and commit=True for INSERT
        kwargs = insert_call[1]
        assert kwargs.get('fetch') is False
        assert kwargs.get('commit') is True


# ============================================================================
# _list_s3_objects_detailed
# ============================================================================

class TestListS3ObjectsDetailed:
    """Tests for _list_s3_objects_detailed helper."""

    def test_returns_key_and_size(self, service):
        """Returns list of dicts with key and size."""
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {'Contents': [
                {'Key': 'TenantA/invoices/file.pdf', 'Size': 12345},
                {'Key': 'TenantA/invoices/image.jpg', 'Size': 67890},
            ]}
        ]
        mock_s3.get_paginator.return_value = mock_paginator

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            result = service._list_s3_objects_detailed('bucket', 'TenantA/invoices/')

        assert result == [
            {'key': 'TenantA/invoices/file.pdf', 'size': 12345},
            {'key': 'TenantA/invoices/image.jpg', 'size': 67890},
        ]

    def test_filters_folder_markers(self, service):
        """Zero-byte .folder markers are excluded."""
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {'Contents': [
                {'Key': 'TenantA/invoices/.folder', 'Size': 0},
                {'Key': 'TenantA/invoices/real.pdf', 'Size': 5000},
            ]}
        ]
        mock_s3.get_paginator.return_value = mock_paginator

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            result = service._list_s3_objects_detailed('bucket', 'TenantA/invoices/')

        assert len(result) == 1
        assert result[0]['key'] == 'TenantA/invoices/real.pdf'

    def test_empty_bucket_returns_empty_list(self, service):
        """Empty prefix returns empty list."""
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{}]  # No Contents key
        mock_s3.get_paginator.return_value = mock_paginator

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            result = service._list_s3_objects_detailed('bucket', 'TenantA/invoices/')

        assert result == []

    def test_handles_multiple_pages(self, service):
        """Paginates across multiple pages."""
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {'Contents': [{'Key': 'TenantA/invoices/page1.pdf', 'Size': 100}]},
            {'Contents': [{'Key': 'TenantA/invoices/page2.pdf', 'Size': 200}]},
        ]
        mock_s3.get_paginator.return_value = mock_paginator

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            result = service._list_s3_objects_detailed('bucket', 'TenantA/invoices/')

        assert len(result) == 2
        assert result[0] == {'key': 'TenantA/invoices/page1.pdf', 'size': 100}
        assert result[1] == {'key': 'TenantA/invoices/page2.pdf', 'size': 200}

    def test_client_error_returns_empty_list(self, service):
        """S3 ClientError returns empty list without raising."""
        from botocore.exceptions import ClientError
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchBucket', 'Message': 'Not found'}},
            'ListObjectsV2'
        )
        mock_s3.get_paginator.return_value = mock_paginator

        with patch('services.media_asset_service.boto3.client', return_value=mock_s3):
            result = service._list_s3_objects_detailed('bad-bucket', 'prefix/')

        assert result == []


# ============================================================================
# discover_invoice_references
# ============================================================================

class TestDiscoverInvoiceReferences:
    """Tests for discover_invoice_references (Req 11 Phase 1, AC 2).

    Scans mutaties.Ref3 for values matching registered s3_keys in the
    invoices category, and creates s3_asset_references rows.
    """

    def test_no_assets_returns_zero(self, service, mock_db):
        """When no invoice assets exist, returns zero counts."""
        mock_db.execute_query.return_value = []

        result = service.discover_invoice_references('TenantA')

        assert result == {
            'success': True,
            'references_created': 0,
            'already_linked': 0,
        }

    def test_no_matching_mutaties_returns_zero(self, service, mock_db):
        """When assets exist but no mutaties.Ref3 matches, zero references created."""
        # First call: get invoice assets
        # Second call: scan mutaties for the s3_key — no matches
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_ABC', 's3_key': 'TenantA/invoices/ast_ABC_inv.pdf'}],
            [],  # no mutaties match
        ]

        result = service.discover_invoice_references('TenantA')

        assert result['success'] is True
        assert result['references_created'] == 0
        assert result['already_linked'] == 0

    def test_single_match_creates_reference(self, service, mock_db):
        """A single mutaties row matching a registered s3_key creates one reference."""
        mock_db.execute_query.side_effect = [
            # Step 1: registered assets
            [{'id': 'ast_001', 's3_key': 'TenantA/invoices/ast_001_report.pdf'}],
            # Step 3: mutaties matching s3_key
            [{'ID': 42}],
            # INSERT reference (returns None for non-fetch)
            None,
        ]

        result = service.discover_invoice_references('TenantA')

        assert result['success'] is True
        assert result['references_created'] == 1
        assert result['already_linked'] == 0

    def test_multiple_assets_multiple_matches(self, service, mock_db):
        """Multiple assets with multiple mutaties matches creates correct count."""
        mock_db.execute_query.side_effect = [
            # Step 1: registered assets
            [
                {'id': 'ast_001', 's3_key': 'TenantA/invoices/ast_001_inv1.pdf'},
                {'id': 'ast_002', 's3_key': 'TenantA/invoices/ast_002_inv2.pdf'},
            ],
            # mutaties matching asset 1 s3_key
            [{'ID': 10}, {'ID': 11}],
            # INSERT for mutatie 10
            None,
            # INSERT for mutatie 11
            None,
            # mutaties matching asset 2 s3_key
            [{'ID': 20}],
            # INSERT for mutatie 20
            None,
        ]

        result = service.discover_invoice_references('TenantA')

        assert result['success'] is True
        assert result['references_created'] == 3
        assert result['already_linked'] == 0

    def test_integrity_error_counts_as_already_linked(self, service, mock_db):
        """IntegrityError (unique constraint) is caught and counted as already_linked."""
        mock_db.execute_query.side_effect = [
            # Step 1: registered assets
            [{'id': 'ast_001', 's3_key': 'TenantA/invoices/ast_001_inv.pdf'}],
            # mutaties matching
            [{'ID': 99}],
            # INSERT raises IntegrityError (already exists)
            IntegrityError("Duplicate entry"),
        ]

        result = service.discover_invoice_references('TenantA')

        assert result['success'] is True
        assert result['references_created'] == 0
        assert result['already_linked'] == 1

    def test_mixed_new_and_existing_references(self, service, mock_db):
        """Mix of new and existing references counted correctly."""
        mock_db.execute_query.side_effect = [
            # Step 1: registered assets
            [{'id': 'ast_001', 's3_key': 'TenantA/invoices/ast_001_a.pdf'}],
            # mutaties matching
            [{'ID': 1}, {'ID': 2}, {'ID': 3}],
            # INSERT for mutatie 1 — success
            None,
            # INSERT for mutatie 2 — already linked
            IntegrityError("Duplicate entry"),
            # INSERT for mutatie 3 — success
            None,
        ]

        result = service.discover_invoice_references('TenantA')

        assert result['success'] is True
        assert result['references_created'] == 2
        assert result['already_linked'] == 1

    def test_uses_correct_tenant_isolation(self, service, mock_db):
        """Queries are tenant-scoped (administration = %s)."""
        mock_db.execute_query.side_effect = [
            [],  # no assets for this tenant
        ]

        service.discover_invoice_references('SpecificTenant')

        # Verify the first query uses the correct tenant
        first_call = mock_db.execute_query.call_args_list[0]
        assert first_call[0][1] == ('SpecificTenant',)

    def test_insert_uses_entity_type_invoice(self, service, mock_db):
        """INSERT uses entity_type='invoice' and entity_id=str(mutaties.ID)."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_X', 's3_key': 'T/invoices/ast_X_file.pdf'}],
            [{'ID': 555}],
            None,  # INSERT success
        ]

        service.discover_invoice_references('T')

        # The third call is the INSERT
        insert_call = mock_db.execute_query.call_args_list[2]
        params = insert_call[0][1]
        assert params[0] == 'T'             # administration
        assert params[1] == 'ast_X'         # asset_id
        assert params[2] == 'invoice'       # entity_type
        assert params[3] == '555'           # entity_id (stringified)

    def test_mutatie_id_is_stringified(self, service, mock_db):
        """mutaties.ID (integer) is converted to string for entity_id."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_A', 's3_key': 'T/invoices/ast_A_doc.pdf'}],
            [{'ID': 12345}],
            None,
        ]

        service.discover_invoice_references('T')

        insert_call = mock_db.execute_query.call_args_list[2]
        entity_id = insert_call[0][1][3]
        assert entity_id == '12345'
        assert isinstance(entity_id, str)


# ============================================================================
# discover_branding_references
# ============================================================================

class TestDiscoverBrandingReferences:
    """Tests for discover_branding_references (Req 11 Phase 1, AC 2).

    Scans parameter_values (namespace='branding') for values matching registered
    s3_keys in the branding category, and creates s3_asset_references rows.
    """

    def test_no_assets_returns_zero(self, service, mock_db):
        """When no branding assets exist, returns zero counts."""
        mock_db.execute_query.return_value = []

        result = service.discover_branding_references('TenantA')

        assert result == {
            'success': True,
            'references_created': 0,
            'already_linked': 0,
        }

    def test_no_matching_params_returns_zero(self, service, mock_db):
        """When assets exist but no parameter_values match, zero references created."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_B1', 's3_key': 'TenantA/branding/ast_B1_logo.png'}],
            [],  # no parameter_values match
        ]

        result = service.discover_branding_references('TenantA')

        assert result['success'] is True
        assert result['references_created'] == 0
        assert result['already_linked'] == 0

    def test_single_match_creates_reference(self, service, mock_db):
        """A single parameter_values row matching creates one reference."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_B1', 's3_key': 'TenantA/branding/ast_B1_logo.png'}],
            [{'key': 'company_logo'}],
            None,  # INSERT success
        ]

        result = service.discover_branding_references('TenantA')

        assert result['success'] is True
        assert result['references_created'] == 1
        assert result['already_linked'] == 0

    def test_entity_id_format_is_tenant_colon_key(self, service, mock_db):
        """entity_id format is '{tenant}:{key}'."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_B1', 's3_key': 'MyTenant/branding/ast_B1_logo.png'}],
            [{'key': 'company_logo'}],
            None,
        ]

        service.discover_branding_references('MyTenant')

        insert_call = mock_db.execute_query.call_args_list[2]
        params = insert_call[0][1]
        assert params[0] == 'MyTenant'          # administration
        assert params[1] == 'ast_B1'            # asset_id
        assert params[2] == 'branding'          # entity_type
        assert params[3] == 'MyTenant:company_logo'  # entity_id

    def test_integrity_error_counts_as_already_linked(self, service, mock_db):
        """IntegrityError (unique constraint) is caught and counted as already_linked."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_B1', 's3_key': 'T/branding/ast_B1_logo.png'}],
            [{'key': 'logo'}],
            IntegrityError("Duplicate entry"),
        ]

        result = service.discover_branding_references('T')

        assert result['success'] is True
        assert result['references_created'] == 0
        assert result['already_linked'] == 1

    def test_multiple_assets_multiple_matches(self, service, mock_db):
        """Multiple assets with multiple param matches creates correct count."""
        mock_db.execute_query.side_effect = [
            [
                {'id': 'ast_B1', 's3_key': 'T/branding/ast_B1_logo.png'},
                {'id': 'ast_B2', 's3_key': 'T/branding/ast_B2_header.png'},
            ],
            # matches for asset 1
            [{'key': 'company_logo'}, {'key': 'email_logo'}],
            None,  # INSERT company_logo
            None,  # INSERT email_logo
            # matches for asset 2
            [{'key': 'header_image'}],
            None,  # INSERT header_image
        ]

        result = service.discover_branding_references('T')

        assert result['success'] is True
        assert result['references_created'] == 3
        assert result['already_linked'] == 0

    def test_uses_correct_tenant_isolation(self, service, mock_db):
        """Queries are tenant-scoped."""
        mock_db.execute_query.side_effect = [
            [],  # no assets
        ]

        service.discover_branding_references('SpecificTenant')

        first_call = mock_db.execute_query.call_args_list[0]
        assert first_call[0][1] == ('SpecificTenant',)


# ============================================================================
# discover_landing_page_references
# ============================================================================

class TestDiscoverLandingPageReferences:
    """Tests for discover_landing_page_references (Req 11 Phase 1, AC 2).

    Scans landing_pages content for s3_key matches and creates
    s3_asset_references rows with entity_type='landing_page'.
    """

    def test_no_assets_returns_zero(self, service, mock_db):
        """When no landing-pages assets exist, returns zero counts."""
        mock_db.execute_query.return_value = []

        result = service.discover_landing_page_references('TenantA')

        assert result == {
            'success': True,
            'references_created': 0,
            'already_linked': 0,
        }

    def test_no_landing_pages_returns_zero(self, service, mock_db):
        """When assets exist but no landing pages found, returns zero."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_LP1', 's3_key': 'slug/landing-pages/ast_LP1_hero.webp'}],
            [],  # no landing pages
        ]

        result = service.discover_landing_page_references('TenantA')

        assert result['success'] is True
        assert result['references_created'] == 0
        assert result['already_linked'] == 0

    def test_no_content_match_returns_zero(self, service, mock_db):
        """When pages exist but content doesn't contain s3_key, zero references."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_LP1', 's3_key': 'slug/landing-pages/ast_LP1_hero.webp'}],
            [{'id': 10, 'content': '{"sections": [{"image": "other_image.png"}]}'}],
        ]

        result = service.discover_landing_page_references('TenantA')

        assert result['success'] is True
        assert result['references_created'] == 0
        assert result['already_linked'] == 0

    def test_content_contains_s3_key_creates_reference(self, service, mock_db):
        """When page content contains the s3_key, creates a reference."""
        s3_key = 'slug/landing-pages/ast_LP1_hero.webp'
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_LP1', 's3_key': s3_key}],
            [{'id': 7, 'content': f'{{"hero_image": "{s3_key}"}}'}],
            None,  # INSERT success
        ]

        result = service.discover_landing_page_references('TenantA')

        assert result['success'] is True
        assert result['references_created'] == 1
        assert result['already_linked'] == 0

    def test_entity_id_is_stringified_page_id(self, service, mock_db):
        """entity_id is str(landing_pages.id)."""
        s3_key = 'slug/landing-pages/ast_LP1_img.png'
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_LP1', 's3_key': s3_key}],
            [{'id': 42, 'content': f'contains {s3_key} here'}],
            None,
        ]

        service.discover_landing_page_references('T')

        insert_call = mock_db.execute_query.call_args_list[2]
        params = insert_call[0][1]
        assert params[0] == 'T'             # administration
        assert params[1] == 'ast_LP1'       # asset_id
        assert params[2] == 'landing_page'  # entity_type
        assert params[3] == '42'            # entity_id (stringified)

    def test_integrity_error_counts_as_already_linked(self, service, mock_db):
        """IntegrityError is caught and counted as already_linked."""
        s3_key = 'slug/landing-pages/ast_LP1_bg.jpg'
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_LP1', 's3_key': s3_key}],
            [{'id': 5, 'content': f'has {s3_key}'}],
            IntegrityError("Duplicate entry"),
        ]

        result = service.discover_landing_page_references('T')

        assert result['success'] is True
        assert result['references_created'] == 0
        assert result['already_linked'] == 1

    def test_multiple_pages_multiple_assets(self, service, mock_db):
        """Multiple pages referencing multiple assets counted correctly."""
        key1 = 'slug/landing-pages/ast_LP1_hero.webp'
        key2 = 'slug/landing-pages/ast_LP2_banner.png'
        mock_db.execute_query.side_effect = [
            # registered assets
            [
                {'id': 'ast_LP1', 's3_key': key1},
                {'id': 'ast_LP2', 's3_key': key2},
            ],
            # landing pages — page 1 has both keys, page 2 has only key2
            [
                {'id': 1, 'content': f'{{"img1": "{key1}", "img2": "{key2}"}}'},
                {'id': 2, 'content': f'{{"banner": "{key2}"}}'},
            ],
            None,  # INSERT page1 + ast_LP1
            None,  # INSERT page1 + ast_LP2
            None,  # INSERT page2 + ast_LP2
        ]

        result = service.discover_landing_page_references('T')

        assert result['success'] is True
        assert result['references_created'] == 3
        assert result['already_linked'] == 0

    def test_null_content_handled_gracefully(self, service, mock_db):
        """Pages with None content don't cause errors."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_LP1', 's3_key': 'slug/landing-pages/ast_LP1_hero.webp'}],
            [{'id': 3, 'content': None}],
        ]

        result = service.discover_landing_page_references('T')

        assert result['success'] is True
        assert result['references_created'] == 0
        assert result['already_linked'] == 0


# ============================================================================
# discover_template_references
# ============================================================================

class TestDiscoverTemplateReferences:
    """Tests for discover_template_references (Req 11 Phase 1, AC 2).

    Scans parameter_values (namespace='templates') for values matching registered
    s3_keys in the templates category, and creates s3_asset_references rows.
    """

    def test_no_assets_returns_zero(self, service, mock_db):
        """When no template assets exist, returns zero counts."""
        mock_db.execute_query.return_value = []

        result = service.discover_template_references('TenantA')

        assert result == {
            'success': True,
            'references_created': 0,
            'already_linked': 0,
        }

    def test_no_matching_params_returns_zero(self, service, mock_db):
        """When assets exist but no parameter_values match, zero references."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_T1', 's3_key': 'TenantA/templates/ast_T1_tmpl.html'}],
            [],  # no matches
        ]

        result = service.discover_template_references('TenantA')

        assert result['success'] is True
        assert result['references_created'] == 0
        assert result['already_linked'] == 0

    def test_single_match_creates_reference(self, service, mock_db):
        """A single parameter_values row matching creates one reference."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_T1', 's3_key': 'T/templates/ast_T1_invoice.html'}],
            [{'key': 'invoice_template'}],
            None,  # INSERT success
        ]

        result = service.discover_template_references('T')

        assert result['success'] is True
        assert result['references_created'] == 1
        assert result['already_linked'] == 0

    def test_entity_id_is_template_key(self, service, mock_db):
        """entity_id is the template parameter key (not tenant-prefixed)."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_T1', 's3_key': 'T/templates/ast_T1_inv.html'}],
            [{'key': 'invoice_nl'}],
            None,
        ]

        service.discover_template_references('T')

        insert_call = mock_db.execute_query.call_args_list[2]
        params = insert_call[0][1]
        assert params[0] == 'T'             # administration
        assert params[1] == 'ast_T1'        # asset_id
        assert params[2] == 'template'      # entity_type
        assert params[3] == 'invoice_nl'    # entity_id (key only, no tenant prefix)

    def test_integrity_error_counts_as_already_linked(self, service, mock_db):
        """IntegrityError (unique constraint) is caught and counted as already_linked."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_T1', 's3_key': 'T/templates/ast_T1_tmpl.html'}],
            [{'key': 'report_template'}],
            IntegrityError("Duplicate entry"),
        ]

        result = service.discover_template_references('T')

        assert result['success'] is True
        assert result['references_created'] == 0
        assert result['already_linked'] == 1

    def test_multiple_assets_multiple_matches(self, service, mock_db):
        """Multiple assets with multiple param matches creates correct count."""
        mock_db.execute_query.side_effect = [
            [
                {'id': 'ast_T1', 's3_key': 'T/templates/ast_T1_inv.html'},
                {'id': 'ast_T2', 's3_key': 'T/templates/ast_T2_report.html'},
            ],
            # matches for asset 1
            [{'key': 'invoice_nl'}, {'key': 'invoice_en'}],
            None,  # INSERT invoice_nl
            None,  # INSERT invoice_en
            # matches for asset 2
            [{'key': 'report_q1'}],
            None,  # INSERT report_q1
        ]

        result = service.discover_template_references('T')

        assert result['success'] is True
        assert result['references_created'] == 3
        assert result['already_linked'] == 0

    def test_uses_correct_tenant_isolation(self, service, mock_db):
        """Queries are tenant-scoped."""
        mock_db.execute_query.side_effect = [
            [],  # no assets
        ]

        service.discover_template_references('SpecificTenant')

        first_call = mock_db.execute_query.call_args_list[0]
        assert first_call[0][1] == ('SpecificTenant',)

    def test_mixed_new_and_existing_references(self, service, mock_db):
        """Mix of new and existing references counted correctly."""
        mock_db.execute_query.side_effect = [
            [{'id': 'ast_T1', 's3_key': 'T/templates/ast_T1_tmpl.html'}],
            [{'key': 'tmpl_a'}, {'key': 'tmpl_b'}, {'key': 'tmpl_c'}],
            None,                             # INSERT tmpl_a — success
            IntegrityError("Duplicate entry"),  # INSERT tmpl_b — already linked
            None,                             # INSERT tmpl_c — success
        ]

        result = service.discover_template_references('T')

        assert result['success'] is True
        assert result['references_created'] == 2
        assert result['already_linked'] == 1


# ============================================================================
# mark_unreferenced_as_orphans
# ============================================================================

class TestMarkUnreferencedAsOrphans:
    """Tests for mark_unreferenced_as_orphans (Req 11 Phase 1, AC 3).

    After import + reference discovery, assets with zero references
    should be marked ORPHAN with orphaned_at = migrated_at.
    """

    @pytest.fixture
    def service(self, mock_db):
        with patch('services.media_asset_service.ParameterService'):
            return MediaAssetService(mock_db)

    def test_returns_success_with_orphan_count(self, service, mock_db):
        """Returns success dict with count of orphaned assets."""
        mock_db.execute_query.return_value = 5

        result = service.mark_unreferenced_as_orphans('TenantA')

        assert result['success'] is True
        assert result['orphaned'] == 5

    def test_zero_orphans_when_all_have_references(self, service, mock_db):
        """Returns 0 when no assets qualify for orphaning."""
        mock_db.execute_query.return_value = 0

        result = service.mark_unreferenced_as_orphans('TenantA')

        assert result['success'] is True
        assert result['orphaned'] == 0

    def test_query_targets_imported_active_assets_only(self, service, mock_db):
        """UPDATE targets only ACTIVE assets with migrated_at IS NOT NULL."""
        mock_db.execute_query.return_value = 3

        service.mark_unreferenced_as_orphans('TenantA')

        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        # Verify query conditions
        assert 'migrated_at IS NOT NULL' in query
        assert "status = 'ACTIVE'" in query
        assert "SET a.status = 'ORPHAN'" in query
        assert 'a.orphaned_at = a.migrated_at' in query

    def test_uses_not_exists_for_zero_references(self, service, mock_db):
        """Uses NOT EXISTS subquery to find assets with zero references."""
        mock_db.execute_query.return_value = 2

        service.mark_unreferenced_as_orphans('TenantA')

        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        assert 'NOT EXISTS' in query
        assert 's3_asset_references' in query

    def test_tenant_isolation(self, service, mock_db):
        """Query is scoped to the provided tenant."""
        mock_db.execute_query.return_value = 1

        service.mark_unreferenced_as_orphans('SpecificTenant')

        call_args = mock_db.execute_query.call_args
        params = call_args[0][1]
        # Both params should be the tenant (main WHERE + subquery)
        assert params == ('SpecificTenant', 'SpecificTenant')

    def test_uses_commit_and_no_fetch(self, service, mock_db):
        """Executes as a write operation (fetch=False, commit=True)."""
        mock_db.execute_query.return_value = 0

        service.mark_unreferenced_as_orphans('TenantA')

        call_args = mock_db.execute_query.call_args
        assert call_args[1]['fetch'] is False
        assert call_args[1]['commit'] is True

    def test_orphaned_at_uses_migrated_at_not_now(self, service, mock_db):
        """Req 11 AC 3: orphaned_at = migrated_at (not NOW())."""
        mock_db.execute_query.return_value = 1

        service.mark_unreferenced_as_orphans('TenantA')

        call_args = mock_db.execute_query.call_args
        query = call_args[0][0]
        # Must set orphaned_at = migrated_at, not NOW() or CURRENT_TIMESTAMP
        assert 'a.orphaned_at = a.migrated_at' in query
        assert 'NOW()' not in query
        assert 'CURRENT_TIMESTAMP' not in query


# ============================================================================
# Integration Test: Import Workflow
# ============================================================================

class TestImportIntegration:
    """Integration test: full import → discover references → mark orphans workflow.

    Simulates the complete import pipeline:
    1. import_legacy_assets registers S3 objects
    2. discover_invoice_references finds matching mutaties.Ref3
    3. mark_unreferenced_as_orphans marks leftovers ORPHAN
    """

    @pytest.fixture
    def service(self, mock_db):
        with patch('services.media_asset_service.ParameterService'):
            with patch.dict(os.environ, {'S3_SHARED_BUCKET': 'test-bucket'}):
                return MediaAssetService(mock_db)

    def test_full_import_workflow(self, service, mock_db):
        """End-to-end: import → discover → orphan marking produces expected results."""
        # --- Phase 1: import_legacy_assets ---
        # Mock S3 returns 3 objects, 1 already registered
        s3_objects = [
            {'key': 'TenantA/invoices/invoice1.pdf', 'size': 1000},
            {'key': 'TenantA/invoices/invoice2.pdf', 'size': 2000},
            {'key': 'TenantA/invoices/invoice3.pdf', 'size': 3000},
        ]

        with patch.object(service, '_list_s3_objects_detailed', return_value=s3_objects):
            # execute_query calls:
            # 1. SELECT existing keys → 1 already registered
            # 2. INSERT asset 1 (new)
            # 3. INSERT asset 2 (new)
            mock_db.execute_query.side_effect = [
                [{'s3_key': 'TenantA/invoices/invoice3.pdf'}],  # already registered
                None,  # INSERT invoice1
                None,  # INSERT invoice2
            ]

            import_result = service.import_legacy_assets('TenantA', 'invoices')

        assert import_result['success'] is True
        assert import_result['newly_registered'] == 2
        assert import_result['already_registered'] == 1

        # --- Phase 2: discover_invoice_references ---
        # Mock: 2 registered assets, 1 has matching mutatie Ref3
        mock_db.execute_query.reset_mock()
        mock_db.execute_query.side_effect = [
            # SELECT assets
            [
                {'id': 'ast_A1', 's3_key': 'TenantA/invoices/invoice1.pdf'},
                {'id': 'ast_A2', 's3_key': 'TenantA/invoices/invoice2.pdf'},
            ],
            # Ref3 matches for invoice1.pdf → found 1 mutatie
            [{'ID': 101}],
            None,  # INSERT reference for ast_A1 → invoice 101
            # Ref3 matches for invoice2.pdf → no matches
            [],
        ]

        discover_result = service.discover_invoice_references('TenantA')

        assert discover_result['success'] is True
        assert discover_result['references_created'] == 1
        assert discover_result['already_linked'] == 0

        # --- Phase 3: mark_unreferenced_as_orphans ---
        # Mock: UPDATE returns 1 (invoice2 has no references)
        mock_db.execute_query.reset_mock()
        mock_db.execute_query.side_effect = None
        mock_db.execute_query.return_value = 1

        orphan_result = service.mark_unreferenced_as_orphans('TenantA')

        assert orphan_result['success'] is True
        assert orphan_result['orphaned'] == 1

    def test_import_workflow_no_orphans_when_all_referenced(self, service, mock_db):
        """When all imported assets have references, no orphans are created."""
        # import returns 2 new assets
        s3_objects = [
            {'key': 'TenantA/invoices/inv1.pdf', 'size': 1000},
            {'key': 'TenantA/invoices/inv2.pdf', 'size': 2000},
        ]

        with patch.object(service, '_list_s3_objects_detailed', return_value=s3_objects):
            mock_db.execute_query.side_effect = [
                [],     # no existing keys
                None,   # INSERT inv1
                None,   # INSERT inv2
            ]
            import_result = service.import_legacy_assets('TenantA', 'invoices')

        assert import_result['newly_registered'] == 2

        # discover finds references for both
        mock_db.execute_query.reset_mock()
        mock_db.execute_query.side_effect = [
            [
                {'id': 'ast_B1', 's3_key': 'TenantA/invoices/inv1.pdf'},
                {'id': 'ast_B2', 's3_key': 'TenantA/invoices/inv2.pdf'},
            ],
            [{'ID': 201}],   # mutatie for inv1
            None,            # INSERT ref
            [{'ID': 202}],   # mutatie for inv2
            None,            # INSERT ref
        ]
        discover_result = service.discover_invoice_references('TenantA')
        assert discover_result['references_created'] == 2

        # mark orphans returns 0
        mock_db.execute_query.reset_mock()
        mock_db.execute_query.side_effect = None
        mock_db.execute_query.return_value = 0
        orphan_result = service.mark_unreferenced_as_orphans('TenantA')
        assert orphan_result['orphaned'] == 0

    def test_import_workflow_all_orphaned_when_none_referenced(self, service, mock_db):
        """When no imported assets have references, all become orphans."""
        s3_objects = [
            {'key': 'TenantA/invoices/old1.pdf', 'size': 500},
            {'key': 'TenantA/invoices/old2.pdf', 'size': 600},
        ]

        with patch.object(service, '_list_s3_objects_detailed', return_value=s3_objects):
            mock_db.execute_query.side_effect = [
                [],     # no existing
                None,   # INSERT old1
                None,   # INSERT old2
            ]
            import_result = service.import_legacy_assets('TenantA', 'invoices')

        assert import_result['newly_registered'] == 2

        # discover finds NO references
        mock_db.execute_query.reset_mock()
        mock_db.execute_query.side_effect = [
            [
                {'id': 'ast_C1', 's3_key': 'TenantA/invoices/old1.pdf'},
                {'id': 'ast_C2', 's3_key': 'TenantA/invoices/old2.pdf'},
            ],
            [],  # no Ref3 match for old1
            [],  # no Ref3 match for old2
        ]
        discover_result = service.discover_invoice_references('TenantA')
        assert discover_result['references_created'] == 0

        # mark orphans returns 2
        mock_db.execute_query.reset_mock()
        mock_db.execute_query.side_effect = None
        mock_db.execute_query.return_value = 2
        orphan_result = service.mark_unreferenced_as_orphans('TenantA')
        assert orphan_result['orphaned'] == 2
