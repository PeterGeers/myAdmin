"""
Property Tests — S3 Ref3 Prefix Bug

Tests for the S3 prefix bug fix in output_service._handle_s3_upload:

1. Bug Condition Exploration (TestS3PrefixBugExploration):
   Demonstrates the bug where 'url' was wrapped as f"s3://{bucket}/{reference}".
   **Validates: Requirements 2.1, 2.2, 2.3**

2. Preservation (TestS3PrefixPreservation):
   Verifies that when provider has NO bucket (test/local mode),
   behavior remains unchanged — url equals reference directly.
   **Validates: Requirements 3.3, 3.4, 3.5**
"""

import pytest
from unittest.mock import Mock, patch
from hypothesis import given, settings
from hypothesis import strategies as st

from services.output_service import OutputService


# --- Strategies ---

# Tenant names: lowercase alphanumeric, 3-20 chars (realistic tenant identifiers)
tenant_strategy = st.from_regex(r"[a-z][a-z0-9]{2,19}", fullmatch=True)

# Filenames: realistic invoice filenames with UUID prefix
filename_strategy = st.builds(
    lambda uuid_part, name: f"{uuid_part}_{name}.pdf",
    uuid_part=st.from_regex(r"[0-9a-f]{12}", fullmatch=True),
    name=st.from_regex(r"INV-20[2-3][0-9]-[0-9]{4}", fullmatch=True),
)

# Bucket names: valid S3 bucket names (lowercase, hyphens, 3-63 chars)
bucket_strategy = st.from_regex(r"[a-z][a-z0-9\-]{2,30}[a-z0-9]", fullmatch=True)


class TestS3PrefixBugExploration:
    """
    Bug condition exploration: demonstrates that _handle_s3_upload wraps
    the S3 key with s3://bucket/ prefix when provider has a non-empty bucket.

    This test SHOULD FAIL on unfixed code (proving the bug exists).
    """

    @given(
        tenant=tenant_strategy,
        filename=filename_strategy,
        bucket=bucket_strategy,
    )
    @settings(max_examples=50)
    def test_s3_upload_returns_plain_key_not_uri(self, tenant, filename, bucket):
        """
        **Validates: Requirements 2.1, 2.2, 2.3**

        Property: When _handle_s3_upload is called with a provider that has a
        non-empty bucket, the result['url'] must equal result['reference']
        (the plain S3 key), NOT an s3:// URI.

        On UNFIXED code this will FAIL because the code constructs:
            url = f"s3://{bucket}/{reference}"
        instead of:
            url = reference
        """
        # Arrange
        mock_db = Mock()
        service = OutputService(mock_db)

        # The plain S3 key that provider.upload() returns
        plain_s3_key = f"{tenant}/invoices/general/{filename}"

        # Mock the storage provider with a non-empty bucket
        mock_provider = Mock()
        mock_provider.bucket = bucket
        mock_provider.upload.return_value = plain_s3_key

        with patch(
            "services.parameter_service.ParameterService"
        ), patch(
            "storage.storage_provider.get_storage_provider",
            return_value=mock_provider,
        ):
            # Act
            result = service._handle_s3_upload(
                content=b"fake-pdf-content",
                filename=filename,
                administration=tenant,
                content_type="application/pdf",
            )

        # Assert — the url must be the plain key, same as reference
        assert result["url"] == result["reference"], (
            f"Bug detected: url={result['url']!r} != reference={result['reference']!r}. "
            f"The url field contains an s3:// URI instead of the plain S3 key."
        )
        assert not result["url"].startswith("s3://"), (
            f"Bug detected: url starts with 's3://' prefix: {result['url']!r}. "
            f"Expected plain key: {result['reference']!r}"
        )


class TestS3PrefixPreservation:
    """
    Preservation property test: verifies that when the provider does NOT have
    a non-empty bucket (test/local mode), the fix does not change behavior.

    The url field must equal the reference value directly — same as before the fix.

    **Validates: Requirements 3.3, 3.4, 3.5**
    """

    @given(
        tenant=tenant_strategy,
        filename=filename_strategy,
    )
    @settings(max_examples=50)
    def test_no_bucket_provider_url_equals_reference(self, tenant, filename):
        """
        **Validates: Requirements 3.3, 3.4, 3.5**

        Property: When _handle_s3_upload is called with a provider that has
        NO bucket attribute (or empty string), the result['url'] must equal
        result['reference']. This preserves existing test/local mode behavior.

        FOR ALL X WHERE NOT isBugCondition(X) DO
          ASSERT output_service.upload_to_storage(X) = output_service.upload_to_storage'(X)
        END FOR
        """
        # Arrange
        mock_db = Mock()
        service = OutputService(mock_db)

        # The plain S3 key that provider.upload() returns
        plain_s3_key = f"{tenant}/invoices/general/{filename}"

        # Mock the storage provider WITHOUT a bucket attribute
        mock_provider = Mock(spec=[])  # spec=[] means no attributes defined
        mock_provider.upload = Mock(return_value=plain_s3_key)
        # Ensure no 'bucket' attribute exists
        assert not hasattr(mock_provider, 'bucket')

        with patch(
            "services.parameter_service.ParameterService"
        ), patch(
            "storage.storage_provider.get_storage_provider",
            return_value=mock_provider,
        ):
            # Act
            result = service._handle_s3_upload(
                content=b"fake-pdf-content",
                filename=filename,
                administration=tenant,
                content_type="application/pdf",
            )

        # Assert — url must equal reference (preservation of existing behavior)
        assert result["url"] == result["reference"], (
            f"Preservation broken: url={result['url']!r} != reference={result['reference']!r}. "
            f"When provider has no bucket, url should equal reference directly."
        )
        # Also verify the reference is the expected plain key
        assert result["reference"] == plain_s3_key, (
            f"Reference mismatch: expected {plain_s3_key!r}, got {result['reference']!r}"
        )

    @given(
        tenant=tenant_strategy,
        filename=filename_strategy,
    )
    @settings(max_examples=50)
    def test_empty_bucket_provider_url_equals_reference(self, tenant, filename):
        """
        **Validates: Requirements 3.3, 3.4, 3.5**

        Property: When _handle_s3_upload is called with a provider that has
        an empty string bucket, the result['url'] must equal result['reference'].
        This covers the edge case where bucket exists but is empty.
        """
        # Arrange
        mock_db = Mock()
        service = OutputService(mock_db)

        # The plain S3 key that provider.upload() returns
        plain_s3_key = f"{tenant}/invoices/general/{filename}"

        # Mock the storage provider with an EMPTY bucket string
        mock_provider = Mock()
        mock_provider.bucket = ""
        mock_provider.upload.return_value = plain_s3_key

        with patch(
            "services.parameter_service.ParameterService"
        ), patch(
            "storage.storage_provider.get_storage_provider",
            return_value=mock_provider,
        ):
            # Act
            result = service._handle_s3_upload(
                content=b"fake-pdf-content",
                filename=filename,
                administration=tenant,
                content_type="application/pdf",
            )

        # Assert — url must equal reference (preservation of existing behavior)
        assert result["url"] == result["reference"], (
            f"Preservation broken: url={result['url']!r} != reference={result['reference']!r}. "
            f"When provider has empty bucket, url should equal reference directly."
        )
        assert result["reference"] == plain_s3_key, (
            f"Reference mismatch: expected {plain_s3_key!r}, got {result['reference']!r}"
        )
