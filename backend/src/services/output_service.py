"""
Output Service for Railway Migration
Handles output destination management for generated reports.

Supports multiple output destinations:
- download: Return content to frontend for download
- gdrive: Upload to tenant's Google Drive
- s3: Upload to AWS S3 (future implementation)
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from io import BytesIO

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
        content: str,
        filename: str,
        destination: str,
        administration: str,
        content_type: str = 'text/html',
        folder_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle output based on destination type.
        
        Args:
            content: Generated report content (HTML, XML, etc.)
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
        
        if destination == 'download':
            return self._handle_download(content, filename, content_type)
        elif destination == 'gdrive':
            return self._handle_gdrive_upload(
                content, filename, administration, content_type, folder_id
            )
        elif destination == 's3':
            return self._handle_s3_upload(
                content, filename, administration, content_type
            )
        else:
            raise ValueError(
                f"Invalid destination: {destination}. "
                "Valid options: 'download', 'gdrive', 's3'"
            )
    
    def _handle_download(
        self,
        content: str,
        filename: str,
        content_type: str
    ) -> Dict[str, Any]:
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
                'success': True,
                'destination': 'download',
                'content': content,
                'filename': filename,
                'content_type': content_type,
                'message': f'Report ready for download: {filename}'
            }
            
        except Exception as e:
            logger.error(f"Failed to prepare download: {e}")
            raise Exception(f"Failed to prepare download: {str(e)}")
    
    def _handle_gdrive_upload(
        self,
        content: str,
        filename: str,
        administration: str,
        content_type: str,
        folder_id: Optional[str] = None
    ) -> Dict[str, Any]:
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
            
            if existing['exists']:
                logger.warning(
                    f"File already exists in Google Drive: {filename}. "
                    "Creating new version with timestamp."
                )
                # Add timestamp to filename to avoid overwrite
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                name_parts = filename.rsplit('.', 1)
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
                'success': True,
                'destination': 'gdrive',
                'url': upload_result['url'],
                'file_id': upload_result['id'],
                'filename': filename,
                'folder_id': folder_id,
                'message': f'Report uploaded to Google Drive: {filename}'
            }
            
        except Exception as e:
            logger.error(f"Failed to upload to Google Drive: {e}")
            raise Exception(f"Failed to upload to Google Drive: {str(e)}")
    
    def _handle_s3_upload(
        self,
        content: str,
        filename: str,
        administration: str,
        content_type: str
    ) -> Dict[str, Any]:
        """
        Handle S3 upload destination (future implementation).
        
        Args:
            content: Report content
            filename: Output filename
            administration: Tenant identifier
            content_type: MIME type
            
        Returns:
            Dictionary with S3 URL
            
        Raises:
            NotImplementedError: S3 upload not yet implemented
        """
        logger.warning("S3 upload not yet implemented")
        raise NotImplementedError(
            "S3 upload destination is not yet implemented. "
            "Please use 'download' or 'gdrive' destinations."
        )
    
    def _get_or_create_reports_folder(
        self,
        drive_service,
        administration: str
    ) -> str:
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
            use_test = os.getenv('TEST_MODE', 'false')
            if use_test:
                use_test = use_test.lower() == 'true'
            else:
                use_test = False
            
            parent_folder_id = (
                os.getenv('TEST_FACTUREN_FOLDER_ID') if use_test 
                else os.getenv('FACTUREN_FOLDER_ID')
            )
            
            if not parent_folder_id:
                raise Exception("Parent folder ID not configured in environment")
            
            # Check if Reports folder exists
            reports_folder_name = f"Reports_{administration}"
            existing = drive_service.check_file_exists(
                reports_folder_name, parent_folder_id
            )
            
            if existing['exists']:
                logger.info(f"Using existing Reports folder: {reports_folder_name}")
                return existing['file']['id']
            
            # Create Reports folder
            logger.info(f"Creating Reports folder: {reports_folder_name}")
            folder_result = drive_service.create_folder(
                reports_folder_name, parent_folder_id
            )
            
            return folder_result['id']
            
        except Exception as e:
            logger.error(f"Failed to get or create Reports folder: {e}")
            raise Exception(f"Failed to get or create Reports folder: {str(e)}")
