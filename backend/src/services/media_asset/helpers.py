"""Internal helpers: validation, raw S3, presigned URLs, retention, bucket resolution."""

import mimetypes
import os
from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError
from ulid import ULID

from services.media_asset.base import _mas_boto3, _maslog


class HelpersMixin:
    def _generate_asset_id(self) -> str:
        """Generate ast_<ULID> identifier.

        Returns:
            String in format 'ast_' followed by a ULID.
        """
        return f"ast_{ULID()}"

    def _resolve_bucket(self, category: str) -> str:
        """Resolve bucket name from env var based on category.

        Args:
            category: One of the keys in CATEGORY_BUCKETS.

        Returns:
            The bucket name from the corresponding environment variable.

        Raises:
            ValueError: If category is not recognized or env var is not set.
        """
        env_var = self.CATEGORY_BUCKETS.get(category)
        if env_var is None:
            valid_categories = ", ".join(sorted(self.CATEGORY_BUCKETS.keys()))
            raise ValueError(
                f"Unknown category '{category}'. Valid categories: {valid_categories}"
            )

        bucket = os.environ.get(env_var)
        if not bucket:
            raise ValueError(
                f"Environment variable '{env_var}' is not set "
                f"(required for category '{category}')"
            )

        return bucket

    def _build_s3_key(
        self, tenant: str, category: str, asset_id: str, filename: str
    ) -> str:
        """Build S3 key path: {tenant}/{category}/{asset_id}_{filename}.

        Args:
            tenant: Tenant identifier (administration).
            category: Asset category (e.g., 'invoices', 'branding').
            asset_id: Generated asset ID (ast_<ULID>).
            filename: Original filename.

        Returns:
            The full S3 key string.
        """
        return f"{tenant}/{category}/{asset_id}_{filename}"

    def _validate_file(self, file_data: bytes, filename: str) -> dict:
        """Validate file type (extension + magic bytes) and size.

        Checks:
        1. File is not empty
        2. Extension matches a known media type
        3. Content headers (magic bytes) match the expected type
           (skipped for web content: .html, .json)
        4. File size is within limits for the detected media type

        Args:
            file_data: Raw file bytes.
            filename: Original filename with extension.

        Returns:
            Dict with 'media_type' and 'mime_type' on success.

        Raises:
            ValueError: If validation fails (empty file, bad type, oversized).
        """
        # AC 7: Check empty file
        if not file_data:
            raise ValueError(
                "A file is required. The upload contained no file or an empty file body."
            )

        ext = os.path.splitext(filename)[1].lower()

        # Find which media_type this extension belongs to
        detected_media_type = None
        for media_type, rules in self.MEDIA_TYPES.items():
            if ext in rules["extensions"]:
                detected_media_type = media_type
                break

        # AC 5: Unsupported extension
        if detected_media_type is None:
            allowed_summary = "; ".join(
                f"{mt}: {', '.join(sorted(rules['extensions']))}"
                for mt, rules in self.MEDIA_TYPES.items()
            )
            raise ValueError(
                f"Unsupported file type '{ext}'. Allowed types — {allowed_summary}"
            )

        # AC 3: Validate magic bytes (skip for web content)
        if detected_media_type == "web_content":
            mime_type = self._sniff_web_content(file_data, ext)
        elif ext == ".svg":
            # SVG is text-based XML — validate by content sniffing, not magic bytes
            mime_type = self._validate_svg_content(file_data)
        else:
            mime_type = self._validate_magic_bytes(file_data, ext, detected_media_type)

        # AC 4 & 6: Validate file size
        max_size = self.MEDIA_TYPES[detected_media_type]["max_size"]
        if len(file_data) > max_size:
            max_mb = max_size / (1024 * 1024)
            file_mb = len(file_data) / (1024 * 1024)
            raise ValueError(
                f"File size ({file_mb:.1f} MB) exceeds the {max_mb:.0f} MB "
                f"limit for media type '{detected_media_type}'."
            )

        return {
            "media_type": detected_media_type,
            "mime_type": mime_type,
        }

    def _validate_magic_bytes(self, file_data: bytes, ext: str, media_type: str) -> str:
        """Validate binary file content against known magic byte signatures.

        Args:
            file_data: Raw file bytes.
            ext: File extension (lowercase, with dot).
            media_type: Expected media type category.

        Returns:
            Detected MIME type string.

        Raises:
            ValueError: If magic bytes don't match any known signature for the type.
        """
        detected_mime = self._detect_mime_from_bytes(file_data)

        if detected_mime is None:
            raise ValueError(
                f"File content does not match any known format for "
                f"media type '{media_type}'. The file may be corrupted or "
                f"the extension '{ext}' does not match the actual content."
            )

        # Cross-check: detected MIME should match the media type's expected prefixes
        expected_prefixes = self.MEDIA_TYPES[media_type]["mime_prefixes"]
        if not any(detected_mime.startswith(prefix) for prefix in expected_prefixes):
            raise ValueError(
                f"File content detected as '{detected_mime}' does not match "
                f"the expected type for extension '{ext}' "
                f"(expected: {', '.join(expected_prefixes)}). "
                f"The file extension may not match its actual content."
            )

        return detected_mime

    def _detect_mime_from_bytes(self, file_data: bytes) -> str | None:
        """Detect MIME type from file content using magic bytes.

        Args:
            file_data: Raw file bytes (at least first 12 bytes needed).

        Returns:
            Detected MIME type string, or None if no match found.
        """
        if len(file_data) < 4:
            return None

        # Check each signature against the file header
        for signature, mime_type in self.MAGIC_BYTES.items():
            if mime_type == "image/webp":
                # WEBP: starts with RIFF, then has WEBP at offset 8
                if (
                    file_data[:4] == b"RIFF"
                    and len(file_data) >= 12
                    and file_data[8:12] == b"WEBP"
                ):
                    return "image/webp"
            elif mime_type == "video/mp4":
                # MP4: has 'ftyp' at offset 4
                if len(file_data) >= 8 and file_data[4:8] == b"ftyp":
                    return "video/mp4"
            else:
                if file_data[: len(signature)] == signature:
                    return mime_type

        return None

    def _sniff_web_content(self, file_data: bytes, ext: str) -> str:
        """Validate web content files by extension + basic content check.

        Web content (.html, .json) has no reliable magic bytes.
        Validation is by extension match and basic content sniffing.

        Args:
            file_data: Raw file bytes.
            ext: File extension (lowercase, with dot).

        Returns:
            MIME type for the web content.

        Raises:
            ValueError: If content doesn't appear to be valid for the extension.
        """
        if ext == ".html":
            # Basic check: should contain HTML-like content
            try:
                text = file_data[:1024].decode("utf-8", errors="ignore").lower()
            except Exception:
                text = ""
            if not any(
                marker in text
                for marker in ["<html", "<!doctype", "<head", "<body", "<div"]
            ):
                raise ValueError(
                    "File with .html extension does not appear to contain valid HTML content."
                )
            return "text/html"
        elif ext == ".json":
            # Basic check: should start with { or [ after whitespace
            try:
                text = file_data[:256].decode("utf-8", errors="ignore").strip()
            except Exception:
                text = ""
            if not text or text[0] not in ("{", "["):
                raise ValueError(
                    "File with .json extension does not appear to contain valid JSON content."
                )
            return "application/json"

        # Should not reach here since we only call for web_content extensions
        return mimetypes.guess_type(f"file{ext}")[0] or "application/octet-stream"

    def _validate_svg_content(self, file_data: bytes) -> str:
        """Validate SVG file content by checking for XML/SVG markers.

        SVG files are text-based XML and don't have binary magic bytes.
        Validates by checking the content starts with expected SVG/XML markers.

        Args:
            file_data: Raw file bytes.

        Returns:
            'image/svg+xml' on success.

        Raises:
            ValueError: If content doesn't appear to be valid SVG.
        """
        try:
            text = file_data[:1024].decode("utf-8", errors="ignore").strip().lower()
        except Exception:
            text = ""

        if not any(marker in text for marker in ["<svg", "<?xml"]):
            raise ValueError(
                "File with .svg extension does not appear to contain valid SVG content."
            )
        return "image/svg+xml"

    def _upload_raw(
        self, bucket: str, key: str, file_data: bytes, content_type: str
    ) -> bool:
        """Raw S3 put_object. Only called from store_and_register.

        Args:
            bucket: S3 bucket name.
            key: Full S3 key path.
            file_data: Raw file bytes to upload.
            content_type: MIME type for the object.

        Returns:
            True if upload succeeded, False otherwise.
        """
        try:
            s3_client = _mas_boto3().client("s3")
            s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=file_data,
                ContentType=content_type,
            )
            return True
        except ClientError as e:
            _maslog().error(
                "S3 upload failed: bucket=%s, key=%s, error=%s", bucket, key, str(e)
            )
            return False
        except Exception as e:
            _maslog().error(
                "Unexpected error during S3 upload: bucket=%s, key=%s, error=%s",
                bucket,
                key,
                str(e),
            )
            return False

    def _delete_raw(self, bucket: str, key: str) -> bool:
        """Raw S3 delete_object. Only called from delete_asset/force_delete.

        Args:
            bucket: S3 bucket name.
            key: Full S3 key path of the object to delete.

        Returns:
            True if deletion succeeded, False otherwise.
        """
        try:
            s3_client = _mas_boto3().client("s3")
            s3_client.delete_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            _maslog().error(
                "S3 delete failed: bucket=%s, key=%s, error=%s", bucket, key, str(e)
            )
            return False
        except Exception as e:
            _maslog().error(
                "Unexpected error during S3 delete: bucket=%s, key=%s, error=%s",
                bucket,
                key,
                str(e),
            )
            return False

    def _get_retention_days(self, tenant: str, category: str, media_type: str) -> int:
        """Resolve retention days for a given category and media type.

        Resolution order (Req 5, AC 8):
        1. Asset-level retention_days override (handled at caller level)
        2. Tenant-level parameter (via ParameterService scope chain)
        3. System default (via CODE_DEFAULTS)

        For landing-pages category, the key depends on media_type:
        - image/video → 'landing_pages_media_days'
        - other (web_content, document) → 'landing_pages_days'

        Args:
            tenant: Tenant identifier (administration).
            category: Asset category (invoices, branding, templates, landing-pages).
            media_type: Asset media type (image, video, document, web_content).

        Returns:
            Integer number of retention days.
        """
        key = self._retention_param_key(category, media_type)
        value = self.ps.get_param("asset_retention", key, tenant=tenant)
        if value is not None:
            return int(value)
        # Shouldn't happen if CODE_DEFAULTS is populated, but defensive fallback
        return 30

    @staticmethod
    def _retention_param_key(category: str, media_type: str) -> str:
        """Map category + media_type to the asset_retention parameter key.

        Args:
            category: Asset category.
            media_type: Asset media type.

        Returns:
            The parameter key string for use with namespace 'asset_retention'.
        """
        if category == "landing-pages":
            if media_type in ("image", "video"):
                return "landing_pages_media_days"
            return "landing_pages_days"

        # Normalize category for param key lookup (e.g., 'landing-pages' → 'landing_pages')
        key_prefix = category.replace("-", "_")
        return f"{key_prefix}_days"

    def _get_presigned_url(self, asset: dict, ttl: int = 3600) -> str:
        """Return cached presigned URL or generate new one.

        Caches presigned URLs in memory with a safety margin of 10 minutes
        before expiry. For 60-minute URLs (ttl=3600), this means the cache
        effectively has a ~50-minute TTL.

        AC 7: Cache presigned URLs in memory with TTL of 50 minutes.

        Args:
            asset: Dict with 'id', 'bucket', and 's3_key' keys.
            ttl: URL validity in seconds (default 3600 = 60 minutes).

        Returns:
            Presigned URL string for the S3 object.
        """
        asset_id = asset["id"]
        now = datetime.now(timezone.utc)

        # Check cache (50-min effective TTL for 60-min URLs)
        if asset_id in self._presigned_cache:
            url, expires_at = self._presigned_cache[asset_id]
            if now < expires_at - timedelta(minutes=10):
                return url

        # Generate new presigned URL
        s3_client = _mas_boto3().client("s3")
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": asset["bucket"], "Key": asset["s3_key"]},
            ExpiresIn=ttl,
        )

        self._presigned_cache[asset_id] = (url, now + timedelta(seconds=ttl))
        return url

    def _check_duplicate(
        self, tenant: str, current_asset_id: str, content_hash: str
    ) -> dict | None:
        """Check if another asset in the same tenant has the same content_hash.

        This is a non-blocking check — duplicates are reported but do not
        prevent the upload.

        Args:
            tenant: Tenant identifier (administration).
            current_asset_id: The just-created asset's ID (to exclude from search).
            content_hash: SHA-256 hex digest to search for.

        Returns:
            Dict with 'asset_id' and 'original_filename' of the duplicate,
            or None if no duplicate found.
        """
        try:
            query = """
                SELECT id, original_filename
                FROM s3_assets
                WHERE administration = %s
                  AND content_hash = %s
                  AND id != %s
                ORDER BY created_at ASC
                LIMIT 1
            """
            results = self.db.execute_query(
                query, (tenant, content_hash, current_asset_id)
            )
            if results:
                return {
                    "asset_id": results[0]["id"],
                    "original_filename": results[0]["original_filename"],
                }
        except Exception as e:
            # Duplicate detection is non-blocking — log and continue
            _maslog().warning(
                "Duplicate check failed for asset %s: %s", current_asset_id, str(e)
            )
        return None
