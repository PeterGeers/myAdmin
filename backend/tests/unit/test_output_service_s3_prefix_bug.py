"""
Property Tests — S3 Report Output via MediaAssetService

Tests for output_service._handle_s3_upload after migration to MediaAssetService:

1. URL Consistency (TestS3UploadUrlConsistency):
   Verifies that the url and reference fields both contain the plain S3 key
   returned by MediaAssetService, with no s3:// prefix wrapping.

2. Entity ID Format (TestS3UploadEntityIdFormat):
   Verifies that entity_id follows the format 'report_type:timestamp'
   where report_type is the filename without extension.
"""

import pytest
from unittest.mock import Mock, patch
from hypothesis import given, settings
from hypothesis import strategies as st

from services.output_service import OutputService


# --- Strategies ---

# Tenant names: lowercase alphanumeric, 3-20 chars (realistic tenant identifiers)
tenant_strategy = st.from_regex(r"[a-z][a-z0-9]{2,19}", fullmatch=True)

# Filenames: realistic report filenames
filename_strategy = st.builds(
    lambda name, ext: f"{name}.{ext}",
    name=st.from_regex(r"[a-z][a-z0-9_]{2,30}", fullmatch=True),
    ext=st.sampled_from(["pdf", "html", "xlsx", "json"]),
)

# S3 key patterns returned by MediaAssetService
s3_key_strategy = st.builds(
    lambda tenant, asset_id, filename: f"{tenant}/invoices/{asset_id}_{filename}",
    tenant=tenant_strategy,
    asset_id=st.from_regex(r"ast_[a-z0-9]{20}", fullmatch=True),
    filename=filename_strategy,
)


class TestS3UploadUrlConsistency:
    """
    Verifies that _handle_s3_upload returns url and reference as plain S3 keys
    from MediaAssetService.store_and_register result, with no URI wrapping.
    """

    @given(
        tenant=tenant_strategy,
        filename=filename_strategy,
        s3_key=s3_key_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_url_equals_reference_and_is_plain_key(self, tenant, filename, s3_key):
        """
        Property: url and reference must both equal the s3_key from the asset
        result. Neither should contain 's3://' prefix or any URI wrapping.
        """
        mock_db = Mock()
        service = OutputService(mock_db)

        mock_asset_svc = Mock()
        mock_asset_svc.store_and_register.return_value = {
            'success': True,
            'asset': {
                'id': 'ast_test123',
                's3_key': s3_key,
                'bucket': 'myadmin-shared-dev',
                'mime_type': 'application/pdf',
                'file_size': 100,
                'category': 'invoices',
                'media_type': 'document',
                'original_filename': filename,
                'content_hash': 'abc123',
                'status': 'ACTIVE',
                'created_at': '2026-01-01 00:00:00',
                'reference_count': 1,
            },
            'duplicate_of': None,
        }

        with patch(
            "services.media_asset_service.MediaAssetService",
            return_value=mock_asset_svc,
        ):
            result = service._handle_s3_upload(
                content=b"fake-content",
                filename=filename,
                administration=tenant,
                content_type="application/pdf",
            )

        # url and reference must be the plain S3 key
        assert result["url"] == s3_key, (
            f"url mismatch: expected {s3_key!r}, got {result['url']!r}"
        )
        assert result["reference"] == s3_key, (
            f"reference mismatch: expected {s3_key!r}, got {result['reference']!r}"
        )
        assert result["url"] == result["reference"], (
            f"url != reference: {result['url']!r} != {result['reference']!r}"
        )
        assert not result["url"].startswith("s3://"), (
            f"url has s3:// prefix: {result['url']!r}"
        )


class TestS3UploadEntityIdFormat:
    """
    Verifies that entity_id passed to store_and_register follows
    the format 'report_type:YYYYMMDD_HHMMSS'.
    """

    @given(
        tenant=tenant_strategy,
        filename=filename_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_entity_id_is_report_type_colon_timestamp(self, tenant, filename):
        """
        Property: entity_id must be '{filename_without_extension}:{timestamp}'
        where timestamp is YYYYMMDD_HHMMSS (15 chars).
        """
        mock_db = Mock()
        service = OutputService(mock_db)

        mock_asset_svc = Mock()
        mock_asset_svc.store_and_register.return_value = {
            'success': True,
            'asset': {
                'id': 'ast_test123',
                's3_key': f'{tenant}/invoices/ast_test123_{filename}',
                'bucket': 'myadmin-shared-dev',
                'mime_type': 'application/pdf',
                'file_size': 100,
                'category': 'invoices',
                'media_type': 'document',
                'original_filename': filename,
                'content_hash': 'abc123',
                'status': 'ACTIVE',
                'created_at': '2026-01-01 00:00:00',
                'reference_count': 1,
            },
            'duplicate_of': None,
        }

        with patch(
            "services.media_asset_service.MediaAssetService",
            return_value=mock_asset_svc,
        ):
            service._handle_s3_upload(
                content=b"fake-content",
                filename=filename,
                administration=tenant,
                content_type="application/pdf",
            )

        # Extract entity_id from the call
        call_kwargs = mock_asset_svc.store_and_register.call_args[1]
        entity_id = call_kwargs['entity_id']
        entity_type = call_kwargs['entity_type']

        # entity_type must be 'report'
        assert entity_type == 'report', (
            f"Expected entity_type='report', got {entity_type!r}"
        )

        # entity_id format: report_type:timestamp
        assert ':' in entity_id, (
            f"entity_id missing colon separator: {entity_id!r}"
        )
        parts = entity_id.split(':', 1)
        report_type = parts[0]
        timestamp = parts[1]

        # report_type should be filename without extension
        expected_report_type = filename.rsplit('.', 1)[0] if '.' in filename else filename
        assert report_type == expected_report_type, (
            f"report_type mismatch: expected {expected_report_type!r}, got {report_type!r}"
        )

        # timestamp should be YYYYMMDD_HHMMSS (15 chars)
        assert len(timestamp) == 15, (
            f"timestamp length should be 15 (YYYYMMDD_HHMMSS), got {len(timestamp)}: {timestamp!r}"
        )
        assert timestamp[8] == '_', (
            f"timestamp separator at pos 8 should be '_': {timestamp!r}"
        )

    @given(
        tenant=tenant_strategy,
    )
    @settings(max_examples=20, deadline=None)
    def test_entity_id_filename_without_extension(self, tenant):
        """
        Property: For a filename without extension, the entire filename
        becomes the report_type in entity_id.
        """
        filename = "report_no_ext"  # No dot — no extension
        mock_db = Mock()
        service = OutputService(mock_db)

        mock_asset_svc = Mock()
        mock_asset_svc.store_and_register.return_value = {
            'success': True,
            'asset': {
                'id': 'ast_test123',
                's3_key': f'{tenant}/invoices/ast_test123_{filename}',
                'bucket': 'myadmin-shared-dev',
                'mime_type': 'application/octet-stream',
                'file_size': 100,
                'category': 'invoices',
                'media_type': 'document',
                'original_filename': filename,
                'content_hash': 'abc123',
                'status': 'ACTIVE',
                'created_at': '2026-01-01 00:00:00',
                'reference_count': 1,
            },
            'duplicate_of': None,
        }

        with patch(
            "services.media_asset_service.MediaAssetService",
            return_value=mock_asset_svc,
        ):
            service._handle_s3_upload(
                content=b"fake-content",
                filename=filename,
                administration=tenant,
                content_type="application/octet-stream",
            )

        call_kwargs = mock_asset_svc.store_and_register.call_args[1]
        entity_id = call_kwargs['entity_id']
        report_type = entity_id.split(':', 1)[0]

        assert report_type == filename, (
            f"For extensionless filename, report_type should be the full "
            f"filename: expected {filename!r}, got {report_type!r}"
        )
