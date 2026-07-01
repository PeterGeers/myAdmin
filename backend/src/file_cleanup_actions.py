"""
File Cleanup Actions

Performs the actual file removal operations for both local storage and Google Drive.
Includes URL parsing/normalization, security validation, and file system operations.

Extracted from file_cleanup_manager.py to separate actions from orchestration/logging.
"""

import os
import re
import logging
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class FileCleanupError(Exception):
    """Custom exception for file cleanup errors."""

    pass


class FileSystemError(FileCleanupError):
    """Exception for file system operation failures."""

    pass


class SecurityError(FileCleanupError):
    """Exception for security-related file operation failures."""

    pass


class GoogleDriveError(FileCleanupError):
    """Exception for Google Drive operation failures."""

    pass


class FileCleanupActions:
    """Performs actual file cleanup operations (local and Google Drive)."""

    def __init__(self, base_storage_path: str, temp_storage_path: str) -> None:
        self.base_storage_path = base_storage_path
        self.temp_storage_path = temp_storage_path

    # ── URL Handling ─────────────────────────────────────────

    def get_file_path_from_url(self, url: str) -> str:
        """
        Extract local file path from Google Drive or storage URL.

        Converts various URL formats into local file system paths.
        """
        if not url or not url.strip():
            return ""

        url = url.strip()

        # Handle Google Drive URLs
        if self.is_google_drive_url(url):
            return url

        # Handle local file paths (absolute or relative)
        if os.path.isabs(url) or not url.startswith(("http://", "https://")):
            return os.path.normpath(url)

        # Handle web URLs that might reference local storage
        try:
            parsed = urlparse(url)
            if parsed.path:
                path_parts = parsed.path.strip("/").split("/")
                if path_parts and path_parts[0]:
                    local_path = os.path.join(self.base_storage_path, *path_parts)
                    return os.path.normpath(local_path)
        except Exception as e:
            print(f"Error parsing URL {url}: {e}")

        return ""

    def normalize_url(self, url: str) -> str:
        """Normalize URL for consistent comparison."""
        if not url:
            return ""

        # Handle Google Drive URLs - extract file ID for comparison
        if self.is_google_drive_url(url):
            file_id = self.extract_google_drive_file_id(url)
            return f"gdrive:{file_id}" if file_id else url.lower()

        # Handle local file paths
        if not url.startswith(("http://", "https://")):
            return os.path.normpath(url).lower()

        # Handle web URLs
        try:
            parsed = urlparse(url.lower())
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            return normalized.rstrip("/")
        except Exception:
            return url.lower()

    def is_google_drive_url(self, url: str) -> bool:
        """Check if URL is a Google Drive URL."""
        if not url:
            return False

        google_drive_patterns = [
            "drive.google.com",
            "docs.google.com",
            "googleapis.com",
        ]

        return any(pattern in url.lower() for pattern in google_drive_patterns)

    def extract_google_drive_file_id(self, url: str) -> Optional[str]:
        """Extract file ID from Google Drive URL."""
        if not url:
            return None

        # Pattern 1: /d/{file_id}/
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
        if match:
            return match.group(1)

        # Pattern 2: id={file_id}
        match = re.search(r"[?&]id=([a-zA-Z0-9-_]+)", url)
        if match:
            return match.group(1)

        # Pattern 3: file ID at start (from xlsx_export.py pattern)
        if "&" in url:
            file_id = url.split("&")[0]
            if "/d/" in file_id:
                file_id = file_id.split("/d/")[1].split("/")[0]
                return file_id

        return None

    # ── Cleanup Actions ──────────────────────────────────────

    def cleanup_google_drive_file(
        self, file_url: str, file_id: Optional[str] = None, operation_id: str = None
    ) -> bool:
        """
        Cleanup Google Drive file.

        Currently a placeholder — Google Drive files are not physically deleted
        as they may be referenced by other transactions.

        Raises:
            GoogleDriveError: If Google Drive operations fail
        """
        try:
            logger.info(
                f"[{operation_id}] Google Drive file cleanup requested for: {file_url}"
            )

            if not file_id:
                file_id = self.extract_google_drive_file_id(file_url)
                if not file_id:
                    raise GoogleDriveError(
                        f"Could not extract file ID from Google Drive URL: {file_url}"
                    )

            logger.debug(f"[{operation_id}] Google Drive file ID: {file_id}")

            # Placeholder — Google Drive files remain as they may be referenced elsewhere
            logger.info(
                f"[{operation_id}] Google Drive file cleanup completed (placeholder): {file_url}"
            )
            return True

        except GoogleDriveError:
            raise

        except Exception as e:
            raise GoogleDriveError(f"Unexpected error in Google Drive cleanup: {e}")

    def cleanup_local_file(self, file_path: str, operation_id: str) -> bool:
        """
        Cleanup local file with atomic operations.

        Raises:
            SecurityError: If file path is unsafe
            FileSystemError: If file system operations fail
        """
        try:
            # Convert URL to local file path if needed
            local_path = self.get_file_path_from_url(file_path)

            if not local_path or local_path == file_path:
                local_path = file_path

            logger.debug(f"[{operation_id}] Resolved local path: {local_path}")

            # Ensure path is within allowed storage directories
            if not self.is_safe_path(local_path):
                raise SecurityError(f"Unsafe file path rejected: {local_path}")

            # Check if file exists before attempting removal
            if os.path.exists(local_path):
                if not os.path.isfile(local_path):
                    raise FileSystemError(
                        f"Path exists but is not a file: {local_path}"
                    )

                file_size = os.path.getsize(local_path)
                logger.debug(
                    f"[{operation_id}] Removing file: {local_path} (size: {file_size} bytes)"
                )

                # Atomic file removal with retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        os.remove(local_path)
                        logger.info(
                            f"[{operation_id}] Successfully removed file: {local_path}"
                        )
                        break
                    except OSError as ose:
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"[{operation_id}] Retry {attempt + 1}/{max_retries} "
                                f"for file removal failed: {ose}"
                            )
                            continue
                        else:
                            raise FileSystemError(
                                f"Failed to remove file after {max_retries} attempts: {ose}"
                            )

                # Try to remove empty parent directory
                self.cleanup_empty_parent_directory(local_path, operation_id)

                return True
            else:
                # File doesn't exist - consider this successful cleanup
                logger.info(
                    f"[{operation_id}] File not found (already cleaned up?): {local_path}"
                )
                return True

        except (SecurityError, FileSystemError):
            raise

        except OSError as ose:
            raise FileSystemError(f"OS error removing file {file_path}: {ose}")

        except Exception as e:
            raise FileSystemError(f"Unexpected error removing file {file_path}: {e}")

    def cleanup_empty_parent_directory(self, file_path: str, operation_id: str) -> None:
        """Attempt to remove empty parent directory if it's within storage."""
        try:
            parent_dir = os.path.dirname(file_path)

            if (
                parent_dir != self.base_storage_path
                and parent_dir.startswith(self.base_storage_path)
                and os.path.exists(parent_dir)
            ):
                if not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
                    logger.info(
                        f"[{operation_id}] Removed empty directory: {parent_dir}"
                    )
                else:
                    logger.debug(
                        f"[{operation_id}] Parent directory not empty, keeping: {parent_dir}"
                    )

        except OSError as ose:
            logger.debug(f"[{operation_id}] Could not remove parent directory: {ose}")
        except Exception as e:
            logger.debug(
                f"[{operation_id}] Unexpected error in parent directory cleanup: {e}"
            )

    # ── Security Validation ──────────────────────────────────

    def validate_file_url_security(self, file_url: str, operation_id: str) -> None:
        """
        Validate file URL for security concerns.

        Raises:
            SecurityError: If URL contains security risks
        """
        dangerous_patterns = ["../", "..\\", "/..", "\\..", "%2e%2e", "%2E%2E"]

        url_lower = file_url.lower()
        for pattern in dangerous_patterns:
            if pattern in url_lower:
                raise SecurityError(
                    f"Path traversal attempt detected in URL: {file_url}"
                )

        if file_url.startswith(("file://", "ftp://", "sftp://")):
            if not file_url.startswith("file://") or not self._is_development_mode():
                raise SecurityError(f"Suspicious protocol in URL: {file_url}")

        logger.debug(
            f"[{operation_id}] File URL security validation passed: {file_url}"
        )

    def is_safe_path(self, file_path: str) -> bool:
        """Check if file path is within allowed storage directories."""
        try:
            abs_path = os.path.abspath(file_path)
            abs_storage = os.path.abspath(self.base_storage_path)
            abs_temp = os.path.abspath(self.temp_storage_path)

            return abs_path.startswith(abs_storage) or abs_path.startswith(abs_temp)
        except Exception:
            return False

    def _is_development_mode(self) -> bool:
        """Check if application is running in development mode."""
        return (
            os.getenv("FLASK_ENV") == "development"
            or os.getenv("ENVIRONMENT") == "development"
            or os.getenv("DEBUG") == "True"
        )
