"""
Output Service for Railway Migration
Handles output destination management for generated reports.

Supports multiple output destinations:
- download: Return content to frontend for download
- gdrive: Upload to tenant's Google Drive
- s3: Upload to AWS S3 (future implementation)
"""

import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class OutputService:
    """
    Service for managing report output destinations.

    Supports multiple output destinations including local download,
    Google Drive upload, and S3 upload (future).
    """

    def __init__(self, db_manager):
        """
        Initialize the output service.

        Args:
            db_manager: DatabaseManager instance for database operations
        """
        self.db = db_manager
        logger.info("OutputService initialized successfully")

    def handle_output(
        self,
        content,
        filename: str,
        destination: str,
        administration: str,
        content_type: str = "text/html",
        folder_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Handle output based on destination type.

        Args:
            content: Generated content (str or bytes)
            filename: Output filename
            destination: Output destination ('download', 'gdrive', 's3')
            administration: Tenant/administration identifier
            content_type: MIME type of content (default: 'text/html')
            folder_id: Optional Google Drive folder ID for gdrive destination

        Returns:
            Dictionary containing output result:
            {
                'success': bool,
                'destination': str,
                'content': str (for download),
                'url': str (for gdrive/s3),
                'filename': str,
                'message': str
            }

        Raises:
            ValueError: If destination is invalid
            NotImplementedError: If destination is not yet implemented
            Exception: If output handling fails
        """
        destination = destination.lower()

        if destination == "download":
            return self._handle_download(content, filename, content_type)
        elif destination == "gdrive":
            # Check provider: S3 tenants should route to S3 upload, not Google Drive
            from services.storage_resolver import resolve_storage_provider

            provider = resolve_storage_provider(administration)
            if provider in ("s3_shared", "s3_tenant"):
                return self._handle_s3_upload(
                    content, filename, administration, content_type
                )
            return self._handle_gdrive_upload(
                content, filename, administration, content_type, folder_id
            )
        elif destination == "s3":
            return self._handle_s3_upload(
                content, filename, administration, content_type
            )
        else:
            raise ValueError(
                f"Invalid destination: {destination}. "
                "Valid options: 'download', 'gdrive', 's3'"
            )

    def _handle_download(
        self, content: str, filename: str, content_type: str
    ) -> dict[str, Any]:
        """
        Handle download destination (return content to frontend).

        Args:
            content: Report content
            filename: Output filename
            content_type: MIME type

        Returns:
            Dictionary with content for frontend download
        """
        try:
            logger.info(f"Preparing content for download: {filename}")

            return {
                "success": True,
                "destination": "download",
                "content": content,
                "filename": filename,
                "content_type": content_type,
                "message": f"Report ready for download: {filename}",
            }

        except Exception as e:
            logger.error(f"Failed to prepare download: {e}")
            raise Exception(f"Failed to prepare download: {e!s}")

    def _handle_gdrive_upload(
        self,
        content: str,
        filename: str,
        administration: str,
        content_type: str,
        folder_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Handle Google Drive upload destination.

        Args:
            content: Report content
            filename: Output filename
            administration: Tenant identifier
            content_type: MIME type
            folder_id: Optional folder ID (defaults to Reports folder)

        Returns:
            Dictionary with Google Drive URL
        """
        try:
            from google_drive_service import GoogleDriveService

            logger.info(
                f"Uploading to Google Drive for administration '{administration}': {filename}"
            )

            # Initialize Google Drive service for this tenant
            drive_service = GoogleDriveService(administration)

            # Determine target folder
            if not folder_id:
                # Use default Reports folder for this tenant
                # Try to get from environment or create
                folder_id = self._get_or_create_reports_folder(
                    drive_service, administration
                )

            # Check if file already exists
            existing = drive_service.check_file_exists(filename, folder_id)

            if existing["exists"]:
                logger.warning(
                    f"File already exists in Google Drive: {filename}. "
                    "Creating new version with timestamp."
                )
                # Add timestamp to filename to avoid overwrite
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name_parts = filename.rsplit(".", 1)
                if len(name_parts) == 2:
                    filename = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
                else:
                    filename = f"{filename}_{timestamp}"

            # Upload file
            upload_result = drive_service.upload_text_file(
                content, filename, folder_id, content_type
            )

            logger.info(
                f"Successfully uploaded to Google Drive: {filename} "
                f"(URL: {upload_result['url']})"
            )

            return {
                "success": True,
                "destination": "gdrive",
                "url": upload_result["url"],
                "file_id": upload_result["id"],
                "filename": filename,
                "folder_id": folder_id,
                "message": f"Report uploaded to Google Drive: {filename}",
            }

        except Exception as e:
            logger.error(f"Failed to upload to Google Drive: {e}")
            raise Exception(f"Failed to upload to Google Drive: {e!s}")

    def _handle_s3_upload(
        self, content, filename: str, administration: str, content_type: str
    ) -> dict[str, Any]:
        """
        Handle S3 upload destination using MediaAssetService.

        Uploads report output via the asset management service, registering
        the file in the asset registry with entity_type='report'.

        Args:
            content: File content (str or bytes)
            filename: Output filename
            administration: Tenant identifier
            content_type: MIME type

        Returns:
            Dictionary with S3 reference and URL
        """
        try:
            from services.media_asset_service import MediaAssetService

            logger.info(
                f"Uploading to S3 for administration '{administration}': {filename}"
            )

            asset_svc = MediaAssetService(self.db)

            # Ensure content is bytes
            if isinstance(content, str):
                file_data = content.encode("utf-8")
            else:
                file_data = content

            # Generate entity_id from report name + timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_type = filename.rsplit(".", 1)[0] if "." in filename else filename
            entity_id = f"{report_type}:{timestamp}"

            result = asset_svc.store_and_register(
                tenant=administration,
                file_data=file_data,
                filename=filename,
                category="invoices",
                entity_type="report",
                entity_id=entity_id,
                metadata={"content_type": content_type},
            )

            if not result["success"]:
                raise Exception(result.get("error", "Asset registration failed"))

            s3_key = result["asset"]["s3_key"]
            logger.info(f"Successfully uploaded to S3: {filename} (ref: {s3_key})")

            return {
                "success": True,
                "destination": "s3",
                "url": s3_key,
                "reference": s3_key,
                "filename": filename,
                "message": f"File uploaded to S3: {filename}",
            }

        except Exception as e:
            logger.error(f"Failed to upload to S3: {e}")
            raise Exception(f"Failed to upload to S3: {e!s}")

    def check_health(self, destination: str, administration: str) -> dict[str, Any]:
        """
        Lightweight connectivity test for the configured storage provider.

        Used as a pre-flight check before the invoice send flow to catch
        storage issues early (Req 22.7).

        Args:
            destination: Storage destination to check ('download', 'gdrive', 's3')
            administration: Tenant/administration identifier

        Returns:
            Dictionary with health status:
            {
                'healthy': bool,
                'reason': str
            }
        """
        destination = destination.lower()

        if destination == "download":
            # Download is always available — no external dependency
            return {
                "healthy": True,
                "reason": "Download destination is always available",
            }

        if destination == "gdrive":
            return self._check_gdrive_health(administration)

        if destination == "s3":
            return self._check_s3_health(administration)

        return {"healthy": False, "reason": f"Unknown destination: {destination}"}

    def _check_gdrive_health(self, administration: str) -> dict[str, Any]:
        """Check Google Drive connectivity by listing the root folder."""
        try:
            from google_drive_service import GoogleDriveService

            drive_service = GoogleDriveService(administration)
            # Lightweight call: list 1 file to verify API access
            drive_service.service.files().list(pageSize=1, fields="files(id)").execute()
            return {"healthy": True, "reason": "Google Drive is accessible"}
        except Exception as e:
            logger.warning(
                f"Google Drive health check failed for '{administration}': {e}"
            )
            return {"healthy": False, "reason": f"Google Drive unavailable: {e!s}"}

    def _check_s3_health(self, administration: str) -> dict[str, Any]:
        """Check S3 connectivity by calling HeadBucket on the configured bucket."""
        try:
            from services.parameter_service import ParameterService
            from storage.storage_provider import get_storage_provider

            param_svc = ParameterService(self.db)
            provider = get_storage_provider(administration, param_svc)

            bucket = getattr(provider, "bucket", None)
            if not bucket:
                return {"healthy": False, "reason": "S3 bucket not configured"}

            client = getattr(provider, "_client", None)
            if not client:
                return {"healthy": False, "reason": "S3 client not initialized"}

            client.head_bucket(Bucket=bucket)
            return {"healthy": True, "reason": f"S3 bucket '{bucket}' is accessible"}
        except Exception as e:
            logger.warning(f"S3 health check failed for '{administration}': {e}")
            return {"healthy": False, "reason": f"S3 unavailable: {e!s}"}

    def _get_or_create_reports_folder(self, drive_service, administration: str) -> str:
        """
        Get or create Reports folder for tenant in Google Drive.

        Args:
            drive_service: GoogleDriveService instance
            administration: Tenant identifier

        Returns:
            Folder ID for Reports folder
        """
        try:
            # Get parent folder ID from environment
            use_test = os.getenv("TEST_MODE", "false")
            if use_test:
                use_test = use_test.lower() == "true"
            else:
                use_test = False

            parent_folder_id = (
                os.getenv("TEST_FACTUREN_FOLDER_ID")
                if use_test
                else os.getenv("FACTUREN_FOLDER_ID")
            )

            if not parent_folder_id:
                raise Exception("Parent folder ID not configured in environment")

            # Check if Reports folder exists
            reports_folder_name = f"Reports_{administration}"
            existing = drive_service.check_file_exists(
                reports_folder_name, parent_folder_id
            )

            if existing["exists"]:
                logger.info(f"Using existing Reports folder: {reports_folder_name}")
                return existing["file"]["id"]

            # Create Reports folder
            logger.info(f"Creating Reports folder: {reports_folder_name}")
            folder_result = drive_service.create_folder(
                reports_folder_name, parent_folder_id
            )

            return folder_result["id"]

        except Exception as e:
            logger.error(f"Failed to get or create Reports folder: {e}")
            raise Exception(f"Failed to get or create Reports folder: {e!s}")
