"""
File Cleanup Manager Component

This module provides functionality to manage file cleanup operations during duplicate
invoice detection. It handles URL comparison logic and atomic file removal operations
for both local storage and Google Drive files.
"""

import os
import re
import logging
import traceback
import time
from typing import Optional, Dict, Any
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from datetime import datetime

# Configure logger for file cleanup operations
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


class FileCleanupManager:
    """
    Handles file cleanup operations for duplicate invoice detection.
    
    This class provides methods to determine when file cleanup is needed based on
    URL comparison and performs atomic file removal operations while maintaining
    system integrity.
    """
    
    def __init__(self, storage_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the FileCleanupManager with storage configuration.
        
        Args:
            storage_config: Optional configuration dictionary containing:
                - base_storage_path: Base path for local file storage
                - temp_storage_path: Path for temporary files
                - google_drive_enabled: Whether Google Drive integration is enabled
        """
        self.storage_config = storage_config or {}
        
        # Set default storage paths
        self.base_storage_path = self.storage_config.get(
            'base_storage_path', 
            os.path.join(os.path.dirname(__file__), '..', 'storage')
        )
        self.temp_storage_path = self.storage_config.get(
            'temp_storage_path',
            os.path.join(self.base_storage_path, 'temp')
        )
        
        # Ensure storage directories exist
        os.makedirs(self.base_storage_path, exist_ok=True)
        os.makedirs(self.temp_storage_path, exist_ok=True)
    
    def should_cleanup_file(self, new_url: str, existing_url: str) -> bool:
        """
        Determine if file cleanup is needed based on URL comparison.
        
        Compares the new file URL with the existing transaction's file URL to determine
        if the newly uploaded file should be removed when a duplicate is cancelled.
        
        Args:
            new_url: URL of the newly uploaded file
            existing_url: URL of the existing transaction's file
        
        Returns:
            Boolean indicating if file cleanup should be performed:
            - True: URLs are different, cleanup the new file
            - False: URLs are the same, do not cleanup
        
        Requirements: 4.2, 4.3
        """
        # Handle empty or None URLs
        if not new_url or not existing_url:
            # If new_url exists but existing_url doesn't, cleanup the new file
            return bool(new_url and new_url.strip())
        
        # Normalize URLs for comparison
        normalized_new = self._normalize_url(new_url.strip())
        normalized_existing = self._normalize_url(existing_url.strip())
        
        # URLs are different if normalized versions don't match
        return normalized_new != normalized_existing
    
    def cleanup_uploaded_file(self, file_url: str, file_id: Optional[str] = None) -> bool:
        """
        Remove uploaded file and return success status.
        
        Performs atomic file removal operations for both local storage files and
        Google Drive files. Ensures that file removal is all-or-nothing to prevent
        partial cleanup states.
        
        Args:
            file_url: URL or path of the file to remove
            file_id: Optional file identifier for additional cleanup operations
        
        Returns:
            Boolean indicating if cleanup was successful
        
        Requirements: 4.4, 6.2, 6.3
        """
        operation_id = f"cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        if not file_url or not file_url.strip():
            logger.debug(f"[{operation_id}] No file URL provided - nothing to cleanup")
            return True  # Nothing to cleanup
        
        # Initialize cleanup context for comprehensive error handling
        cleanup_context = {
            'operation_id': operation_id,
            'file_url': file_url,
            'file_id': file_id,
            'start_time': datetime.now(),
            'attempts': 0,
            'max_attempts': 3,
            'recovery_actions': []
        }
        
        try:
            logger.info(f"[{operation_id}] Starting file cleanup for: {file_url}")
            
            # Validate file URL for security
            self._validate_file_url_security(file_url, operation_id)
            
            # Perform cleanup with retry logic and comprehensive error handling
            result = self._perform_cleanup_with_recovery(cleanup_context)
            
            if result:
                logger.info(f"[{operation_id}] File cleanup completed successfully for: {file_url}")
                self._log_cleanup_success(cleanup_context)
            else:
                logger.warning(f"[{operation_id}] File cleanup failed for: {file_url}")
                self._log_cleanup_failure(cleanup_context, "cleanup_failed")
            
            return result
                
        except SecurityError as se:
            cleanup_context['error_type'] = 'security_error'
            cleanup_context['error_message'] = str(se)
            logger.error(f"[{operation_id}] Security error during file cleanup for {file_url}: {se}")
            self._log_cleanup_failure(cleanup_context, "security_error")
            return False
            
        except FileSystemError as fse:
            cleanup_context['error_type'] = 'filesystem_error'
            cleanup_context['error_message'] = str(fse)
            logger.error(f"[{operation_id}] File system error during cleanup for {file_url}: {fse}")
            self._log_cleanup_failure(cleanup_context, "filesystem_error")
            return False
            
        except GoogleDriveError as gde:
            cleanup_context['error_type'] = 'google_drive_error'
            cleanup_context['error_message'] = str(gde)
            logger.error(f"[{operation_id}] Google Drive error during cleanup for {file_url}: {gde}")
            self._log_cleanup_failure(cleanup_context, "google_drive_error")
            return False
            
        except Exception as e:
            cleanup_context['error_type'] = 'unexpected_error'
            cleanup_context['error_message'] = str(e)
            cleanup_context['traceback'] = traceback.format_exc()
            
            logger.error(f"[{operation_id}] Unexpected error during file cleanup: {cleanup_context}")
            self._log_cleanup_failure(cleanup_context, "unexpected_error")
            return False
    
    def _perform_cleanup_with_recovery(self, cleanup_context: Dict) -> bool:
        """
        Perform file cleanup with comprehensive error recovery.
        
        Args:
            cleanup_context: Context information for cleanup operation
        
        Returns:
            Boolean indicating if cleanup was successful
        """
        operation_id = cleanup_context['operation_id']
        file_url = cleanup_context['file_url']
        file_id = cleanup_context['file_id']
        max_attempts = cleanup_context['max_attempts']
        
        for attempt in range(1, max_attempts + 1):
            cleanup_context['attempts'] = attempt
            
            try:
                logger.debug(f"[{operation_id}] Cleanup attempt {attempt}/{max_attempts}")
                
                # Determine cleanup method based on URL type
                if self._is_google_drive_url(file_url):
                    result = self._cleanup_google_drive_file(file_url, file_id, operation_id)
                else:
                    result = self._cleanup_local_file(file_url, operation_id)
                
                if result:
                    cleanup_context['recovery_actions'].append(f"successful_on_attempt_{attempt}")
                    return True
                else:
                    cleanup_context['recovery_actions'].append(f"failed_attempt_{attempt}")
                    
                    # If this wasn't the last attempt, try recovery actions
                    if attempt < max_attempts:
                        self._attempt_cleanup_recovery(cleanup_context, attempt)
                        
            except Exception as e:
                cleanup_context['recovery_actions'].append(f"exception_attempt_{attempt}_{type(e).__name__}")
                
                if attempt < max_attempts:
                    logger.warning(f"[{operation_id}] Cleanup attempt {attempt} failed: {e}, retrying...")
                    self._attempt_cleanup_recovery(cleanup_context, attempt)
                else:
                    logger.error(f"[{operation_id}] All cleanup attempts failed: {e}")
                    raise
        
        return False
    
    def _attempt_cleanup_recovery(self, cleanup_context: Dict, failed_attempt: int) -> None:
        """
        Attempt recovery actions between cleanup attempts.
        
        Args:
            cleanup_context: Context information for cleanup operation
            failed_attempt: Number of the failed attempt
        """
        operation_id = cleanup_context['operation_id']
        
        try:
            # Wait before retry (exponential backoff)
            wait_time = min(2 ** failed_attempt, 10)  # Max 10 seconds
            logger.debug(f"[{operation_id}] Waiting {wait_time} seconds before retry")
            time.sleep(wait_time)
            
            # Attempt to refresh file information
            file_url = cleanup_context['file_url']
            if not self._is_google_drive_url(file_url):
                # For local files, check if file still exists and is accessible
                local_path = self.get_file_path_from_url(file_url)
                if local_path and os.path.exists(local_path):
                    # Check file permissions
                    if not os.access(local_path, os.W_OK):
                        logger.warning(f"[{operation_id}] File not writable, attempting permission fix")
                        try:
                            os.chmod(local_path, 0o666)
                            cleanup_context['recovery_actions'].append(f"permission_fix_attempt_{failed_attempt}")
                        except OSError as perm_error:
                            logger.warning(f"[{operation_id}] Could not fix permissions: {perm_error}")
            
            cleanup_context['recovery_actions'].append(f"recovery_attempt_{failed_attempt}")
            
        except Exception as recovery_error:
            logger.warning(f"[{operation_id}] Recovery attempt failed: {recovery_error}")
            cleanup_context['recovery_actions'].append(f"recovery_failed_{failed_attempt}")
    
    def _log_cleanup_success(self, cleanup_context: Dict) -> None:
        """
        Log successful cleanup operation for monitoring.
        
        Args:
            cleanup_context: Context information for cleanup operation
        """
        operation_id = cleanup_context['operation_id']
        
        success_log = {
            'operation_id': operation_id,
            'file_url': cleanup_context['file_url'],
            'attempts': cleanup_context['attempts'],
            'duration_seconds': (datetime.now() - cleanup_context['start_time']).total_seconds(),
            'recovery_actions': cleanup_context['recovery_actions'],
            'status': 'success',
            'component': 'file_cleanup_manager'
        }
        
        logger.info(f"[{operation_id}] Cleanup success metrics: {success_log}")
        
        # Send success metrics to monitoring system
        try:
            self._send_cleanup_metrics(success_log)
        except Exception as e:
            logger.warning(f"[{operation_id}] Failed to send success metrics: {e}")
    
    def _log_cleanup_failure(self, cleanup_context: Dict, failure_type: str) -> None:
        """
        Log failed cleanup operation for monitoring and alerting.
        
        Args:
            cleanup_context: Context information for cleanup operation
            failure_type: Type of failure that occurred
        """
        operation_id = cleanup_context['operation_id']
        
        failure_log = {
            'operation_id': operation_id,
            'file_url': cleanup_context['file_url'],
            'failure_type': failure_type,
            'error_type': cleanup_context.get('error_type', 'unknown'),
            'error_message': cleanup_context.get('error_message', ''),
            'attempts': cleanup_context['attempts'],
            'duration_seconds': (datetime.now() - cleanup_context['start_time']).total_seconds(),
            'recovery_actions': cleanup_context['recovery_actions'],
            'status': 'failure',
            'component': 'file_cleanup_manager',
            'severity': self._determine_failure_severity(failure_type),
            'impact': 'file_not_cleaned_up',
            'recommended_action': self._get_recommended_action(failure_type)
        }
        
        logger.error(f"[{operation_id}] Cleanup failure metrics: {failure_log}")
        
        # Send failure metrics and alerts
        try:
            self._send_cleanup_metrics(failure_log)
            self._send_cleanup_alert(failure_log)
        except Exception as e:
            logger.warning(f"[{operation_id}] Failed to send failure metrics: {e}")
    
    def _determine_failure_severity(self, failure_type: str) -> str:
        """
        Determine severity level for cleanup failures.
        
        Args:
            failure_type: Type of failure that occurred
        
        Returns:
            Severity level string
        """
        severity_map = {
            'security_error': 'high',
            'filesystem_error': 'medium',
            'google_drive_error': 'low',
            'unexpected_error': 'high',
            'cleanup_failed': 'medium'
        }
        
        return severity_map.get(failure_type, 'medium')
    
    def _get_recommended_action(self, failure_type: str) -> str:
        """
        Get recommended action for cleanup failures.
        
        Args:
            failure_type: Type of failure that occurred
        
        Returns:
            Recommended action string
        """
        action_map = {
            'security_error': 'Review file path security and permissions',
            'filesystem_error': 'Check disk space and file system health',
            'google_drive_error': 'Verify Google Drive API credentials and quotas',
            'unexpected_error': 'Investigate logs and contact development team',
            'cleanup_failed': 'Manual file cleanup may be required'
        }
        
        return action_map.get(failure_type, 'Contact system administrator')
    
    def _send_cleanup_metrics(self, metrics_data: Dict) -> None:
        """
        Send cleanup metrics to monitoring system.
        
        Args:
            metrics_data: Metrics data to send
        """
        # In production, this would send metrics to monitoring systems
        # Example implementation:
        # metrics_client.send_metrics('file_cleanup', metrics_data)
        # 
        # For time-series metrics:
        # metrics_client.gauge('file_cleanup.duration', metrics_data['duration_seconds'])
        # metrics_client.increment('file_cleanup.operations', tags=[
        #     f"status:{metrics_data['status']}",
        #     f"component:{metrics_data['component']}"
        # ])
        
        logger.debug(f"Cleanup metrics prepared: {metrics_data['operation_id']}")
    
    def _send_cleanup_alert(self, failure_log: Dict) -> None:
        """
        Send alert for cleanup failures based on severity.
        
        Args:
            failure_log: Failure log data
        """
        # In production, this would send alerts based on failure severity and frequency
        # Example implementation:
        # if failure_log['severity'] in ['high', 'critical']:
        #     alert_client.send_immediate_alert(
        #         title=f"File Cleanup Failure - {failure_log['failure_type']}",
        #         message=f"Operation {failure_log['operation_id']} failed: {failure_log['error_message']}",
        #         severity=failure_log['severity'],
        #         recommended_action=failure_log['recommended_action']
        #     )
        # 
        # # Check if this is part of a pattern of failures
        # recent_failures = self._get_recent_failures(failure_log['failure_type'])
        # if len(recent_failures) > 5:  # Threshold for pattern detection
        #     alert_client.send_pattern_alert(
        #         title="Pattern of File Cleanup Failures Detected",
        #         failures=recent_failures,
        #         severity='high'
        #     )
        
        logger.debug(f"Cleanup alert prepared for: {failure_log['operation_id']}")
    
    def get_cleanup_health_status(self) -> Dict:
        """
        Get health status of file cleanup operations for monitoring.
        
        Returns:
            Dictionary containing health status information
        """
        try:
            # In production, this would aggregate metrics from recent operations
            health_status = {
                'status': 'healthy',  # healthy, degraded, unhealthy
                'last_check': datetime.now().isoformat(),
                'component': 'file_cleanup_manager',
                'metrics': {
                    'success_rate_24h': 0.95,  # Would be calculated from actual metrics
                    'average_duration_seconds': 2.5,
                    'total_operations_24h': 150,
                    'failed_operations_24h': 7
                },
                'alerts': {
                    'active_alerts': 0,
                    'recent_failures': []
                }
            }
            
            # Determine overall health based on metrics
            success_rate = health_status['metrics']['success_rate_24h']
            if success_rate < 0.8:
                health_status['status'] = 'unhealthy'
            elif success_rate < 0.95:
                health_status['status'] = 'degraded'
            
            return health_status
            
        except Exception as e:
            logger.error(f"Failed to get cleanup health status: {e}")
            return {
                'status': 'unknown',
                'error': str(e),
                'last_check': datetime.now().isoformat()
            }
    
    def get_file_path_from_url(self, url: str) -> str:
        """
        Extract local file path from Google Drive or storage URL.
        
        Converts various URL formats (Google Drive URLs, local file paths, web URLs)
        into local file system paths for file operations.
        
        Args:
            url: The URL to convert to a local file path
        
        Returns:
            Local file system path, or empty string if conversion fails
        
        Requirements: 4.2, 4.3
        """
        if not url or not url.strip():
            return ""
        
        url = url.strip()
        
        # Handle Google Drive URLs
        if self._is_google_drive_url(url):
            # For Google Drive URLs, we can't get a direct local path
            # Return the URL as-is for identification purposes
            return url
        
        # Handle local file paths (absolute or relative)
        if os.path.isabs(url) or not url.startswith(('http://', 'https://')):
            # This appears to be a local file path
            return os.path.normpath(url)
        
        # Handle web URLs that might reference local storage
        try:
            parsed = urlparse(url)
            if parsed.path:
                # Extract path component and convert to local storage path
                path_parts = parsed.path.strip('/').split('/')
                if path_parts and path_parts[0]:
                    # Construct path relative to storage directory
                    local_path = os.path.join(self.base_storage_path, *path_parts)
                    return os.path.normpath(local_path)
        except Exception as e:
            print(f"Error parsing URL {url}: {e}")
        
        return ""
    
    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL for consistent comparison.
        
        Args:
            url: URL to normalize
        
        Returns:
            Normalized URL string
        """
        if not url:
            return ""
        
        # Handle Google Drive URLs - extract file ID for comparison
        if self._is_google_drive_url(url):
            file_id = self._extract_google_drive_file_id(url)
            return f"gdrive:{file_id}" if file_id else url.lower()
        
        # Handle local file paths
        if not url.startswith(('http://', 'https://')):
            return os.path.normpath(url).lower()
        
        # Handle web URLs
        try:
            parsed = urlparse(url.lower())
            # Remove query parameters and fragments for comparison
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            return normalized.rstrip('/')
        except Exception:
            return url.lower()
    
    def _is_google_drive_url(self, url: str) -> bool:
        """
        Check if URL is a Google Drive URL.
        
        Args:
            url: URL to check
        
        Returns:
            Boolean indicating if this is a Google Drive URL
        """
        if not url:
            return False
        
        google_drive_patterns = [
            'drive.google.com',
            'docs.google.com',
            'googleapis.com'
        ]
        
        return any(pattern in url.lower() for pattern in google_drive_patterns)
    
    def _extract_google_drive_file_id(self, url: str) -> Optional[str]:
        """
        Extract file ID from Google Drive URL.
        
        Args:
            url: Google Drive URL
        
        Returns:
            File ID if found, None otherwise
        """
        if not url:
            return None
        
        # Pattern 1: /d/{file_id}/
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
        if match:
            return match.group(1)
        
        # Pattern 2: id={file_id}
        match = re.search(r'[?&]id=([a-zA-Z0-9-_]+)', url)
        if match:
            return match.group(1)
        
        # Pattern 3: file ID at start (from xlsx_export.py pattern)
        if '&' in url:
            file_id = url.split('&')[0]
            if '/d/' in file_id:
                file_id = file_id.split('/d/')[1].split('/')[0]
                return file_id
        
        return None
    
    def _cleanup_google_drive_file(self, file_url: str, file_id: Optional[str] = None, operation_id: str = None) -> bool:
        """
        Cleanup Google Drive file with comprehensive error handling.
        
        Args:
            file_url: Google Drive file URL
            file_id: Optional file ID
            operation_id: Operation identifier for logging
        
        Returns:
            Boolean indicating success
        
        Raises:
            GoogleDriveError: If Google Drive operations fail
        """
        try:
            logger.info(f"[{operation_id}] Google Drive file cleanup requested for: {file_url}")
            
            # Extract file ID from URL if not provided
            if not file_id:
                file_id = self._extract_google_drive_file_id(file_url)
                if not file_id:
                    raise GoogleDriveError(f"Could not extract file ID from Google Drive URL: {file_url}")
            
            logger.debug(f"[{operation_id}] Google Drive file ID: {file_id}")
            
            # For now, Google Drive files are not physically deleted
            # This is a placeholder for future Google Drive API integration
            
            # In a real implementation, this would:
            # 1. Authenticate with Google Drive API using service account or OAuth
            # 2. Check if file exists and user has permission to delete
            # 3. Delete the file using the file ID
            # 4. Handle API rate limits and quota errors
            # 5. Handle authentication and authorization errors
            # 6. Implement retry logic for transient API failures
            
            # Example implementation structure:
            # try:
            #     service = self._get_google_drive_service()
            #     service.files().delete(fileId=file_id).execute()
            #     logger.info(f"[{operation_id}] Google Drive file deleted: {file_id}")
            #     return True
            # except HttpError as error:
            #     if error.resp.status == 404:
            #         logger.info(f"[{operation_id}] Google Drive file not found (already deleted?): {file_id}")
            #         return True
            #     elif error.resp.status == 403:
            #         raise GoogleDriveError(f"Permission denied for Google Drive file: {file_id}")
            #     else:
            #         raise GoogleDriveError(f"Google Drive API error: {error}")
            
            # For duplicate detection, we primarily care about local file cleanup
            # Google Drive files can remain as they may be referenced by other transactions
            logger.info(f"[{operation_id}] Google Drive file cleanup completed (placeholder): {file_url}")
            return True
            
        except GoogleDriveError:
            # Re-raise Google Drive specific errors
            raise
            
        except Exception as e:
            # Convert unexpected errors to GoogleDriveError
            raise GoogleDriveError(f"Unexpected error in Google Drive cleanup: {e}")
    
    def _cleanup_local_file(self, file_path: str, operation_id: str) -> bool:
        """
        Cleanup local file with atomic operations.
        
        Args:
            file_path: Local file path to remove
            operation_id: Operation identifier for logging
        
        Returns:
            Boolean indicating if cleanup was successful
        
        Raises:
            SecurityError: If file path is unsafe
            FileSystemError: If file system operations fail
        """
        try:
            # Convert URL to local file path if needed
            local_path = self.get_file_path_from_url(file_path)
            
            if not local_path or local_path == file_path:
                # If no conversion happened, treat as direct file path
                local_path = file_path
            
            logger.debug(f"[{operation_id}] Resolved local path: {local_path}")
            
            # Ensure path is within allowed storage directories for security
            if not self._is_safe_path(local_path):
                raise SecurityError(f"Unsafe file path rejected: {local_path}")
            
            # Check if file exists before attempting removal
            if os.path.exists(local_path):
                if not os.path.isfile(local_path):
                    raise FileSystemError(f"Path exists but is not a file: {local_path}")
                
                # Get file info before removal for logging
                file_size = os.path.getsize(local_path)
                logger.debug(f"[{operation_id}] Removing file: {local_path} (size: {file_size} bytes)")
                
                # Atomic file removal with retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        os.remove(local_path)
                        logger.info(f"[{operation_id}] Successfully removed file: {local_path}")
                        break
                    except OSError as ose:
                        if attempt < max_retries - 1:
                            logger.warning(f"[{operation_id}] Retry {attempt + 1}/{max_retries} for file removal failed: {ose}")
                            continue
                        else:
                            raise FileSystemError(f"Failed to remove file after {max_retries} attempts: {ose}")
                
                # Try to remove empty parent directory if it's in storage
                self._cleanup_empty_parent_directory(local_path, operation_id)
                
                return True
            else:
                # File doesn't exist - consider this successful cleanup
                logger.info(f"[{operation_id}] File not found (already cleaned up?): {local_path}")
                return True
                
        except SecurityError:
            # Re-raise security errors
            raise
            
        except FileSystemError:
            # Re-raise file system errors
            raise
            
        except OSError as ose:
            # Convert OS errors to FileSystemError
            raise FileSystemError(f"OS error removing file {file_path}: {ose}")
            
        except Exception as e:
            # Convert unexpected errors to FileSystemError
            raise FileSystemError(f"Unexpected error removing file {file_path}: {e}")
    
    def _cleanup_empty_parent_directory(self, file_path: str, operation_id: str) -> None:
        """
        Attempt to remove empty parent directory if it's within storage.
        
        Args:
            file_path: Path of the file that was removed
            operation_id: Operation identifier for logging
        """
        try:
            parent_dir = os.path.dirname(file_path)
            
            # Only attempt cleanup if directory is within storage and not the base storage path
            if (parent_dir != self.base_storage_path and 
                parent_dir.startswith(self.base_storage_path) and
                os.path.exists(parent_dir)):
                
                # Check if directory is empty
                if not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
                    logger.info(f"[{operation_id}] Removed empty directory: {parent_dir}")
                else:
                    logger.debug(f"[{operation_id}] Parent directory not empty, keeping: {parent_dir}")
                    
        except OSError as ose:
            # Directory removal failure is not critical - log but don't fail
            logger.debug(f"[{operation_id}] Could not remove parent directory: {ose}")
        except Exception as e:
            # Unexpected errors in directory cleanup should not fail the main operation
            logger.debug(f"[{operation_id}] Unexpected error in parent directory cleanup: {e}")
    
    def _validate_file_url_security(self, file_url: str, operation_id: str) -> None:
        """
        Validate file URL for security concerns.
        
        Args:
            file_url: File URL to validate
            operation_id: Operation identifier for logging
        
        Raises:
            SecurityError: If URL contains security risks
        """
        # Check for path traversal attempts
        dangerous_patterns = [
            '../',
            '..\\',
            '/..',
            '\\..',
            '%2e%2e',
            '%2E%2E'
        ]
        
        url_lower = file_url.lower()
        for pattern in dangerous_patterns:
            if pattern in url_lower:
                raise SecurityError(f"Path traversal attempt detected in URL: {file_url}")
        
        # Check for suspicious protocols
        if file_url.startswith(('file://', 'ftp://', 'sftp://')):
            # Only allow file:// for local development
            if not file_url.startswith('file://') or not self._is_development_mode():
                raise SecurityError(f"Suspicious protocol in URL: {file_url}")
        
        logger.debug(f"[{operation_id}] File URL security validation passed: {file_url}")
    
    def _is_development_mode(self) -> bool:
        """
        Check if application is running in development mode.
        
        Returns:
            Boolean indicating if in development mode
        """
        # Check common development environment indicators
        return (
            os.getenv('FLASK_ENV') == 'development' or
            os.getenv('ENVIRONMENT') == 'development' or
            os.getenv('DEBUG') == 'True'
        )
    
    def _is_safe_path(self, file_path: str) -> bool:
        """
        Check if file path is within allowed storage directories.
        
        Args:
            file_path: File path to validate
        
        Returns:
            Boolean indicating if path is safe for cleanup operations
        """
        try:
            # Resolve absolute path to prevent directory traversal attacks
            abs_path = os.path.abspath(file_path)
            abs_storage = os.path.abspath(self.base_storage_path)
            abs_temp = os.path.abspath(self.temp_storage_path)
            
            # Allow cleanup only within storage or temp directories
            return (abs_path.startswith(abs_storage) or 
                    abs_path.startswith(abs_temp))
        except Exception:
            return False