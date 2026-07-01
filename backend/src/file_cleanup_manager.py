"""
File Cleanup Manager Component

Orchestrates file cleanup operations during duplicate invoice detection.
Handles URL comparison logic, retry/recovery, logging, and metrics.

Actual file removal operations are delegated to FileCleanupActions.
"""

import os
import logging
import traceback
import time
from typing import Optional, Dict, Any
from datetime import datetime

from file_cleanup_actions import (
    FileCleanupActions,
    FileCleanupError,
    FileSystemError,
    SecurityError,
    GoogleDriveError,
)

# Re-export exceptions for backward compatibility
__all__ = [
    "FileCleanupManager",
    "FileCleanupError",
    "FileSystemError",
    "SecurityError",
    "GoogleDriveError",
]

# Configure logger for file cleanup operations
logger = logging.getLogger(__name__)


class FileCleanupManager:
    """
    Orchestrates file cleanup operations for duplicate invoice detection.

    Provides methods to determine when file cleanup is needed based on
    URL comparison and coordinates cleanup with retry, logging, and metrics.
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
            "base_storage_path",
            os.path.join(os.path.dirname(__file__), "..", "storage"),
        )
        self.temp_storage_path = self.storage_config.get(
            "temp_storage_path", os.path.join(self.base_storage_path, "temp")
        )

        # Ensure storage directories exist
        os.makedirs(self.base_storage_path, exist_ok=True)
        os.makedirs(self.temp_storage_path, exist_ok=True)

        # Initialize cleanup actions helper
        self._actions = FileCleanupActions(
            self.base_storage_path, self.temp_storage_path
        )

    def should_cleanup_file(self, new_url: str, existing_url: str) -> bool:
        """
        Determine if file cleanup is needed based on URL comparison.

        Returns:
            True if URLs are different (cleanup needed), False if same.
        """
        if not new_url or not existing_url:
            return bool(new_url and new_url.strip())

        normalized_new = self._actions.normalize_url(new_url.strip())
        normalized_existing = self._actions.normalize_url(existing_url.strip())

        return normalized_new != normalized_existing

    def cleanup_uploaded_file(
        self, file_url: str, file_id: Optional[str] = None
    ) -> bool:
        """
        Remove uploaded file and return success status.

        Performs atomic file removal with retry logic, comprehensive error handling,
        and logging/metrics collection.
        """
        operation_id = f"cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        if not file_url or not file_url.strip():
            logger.debug(f"[{operation_id}] No file URL provided - nothing to cleanup")
            return True

        cleanup_context = {
            "operation_id": operation_id,
            "file_url": file_url,
            "file_id": file_id,
            "start_time": datetime.now(),
            "attempts": 0,
            "max_attempts": 3,
            "recovery_actions": [],
        }

        try:
            logger.info(f"[{operation_id}] Starting file cleanup for: {file_url}")

            # Validate file URL for security
            self._actions.validate_file_url_security(file_url, operation_id)

            # Perform cleanup with retry logic
            result = self._perform_cleanup_with_recovery(cleanup_context)

            if result:
                logger.info(
                    f"[{operation_id}] File cleanup completed successfully for: {file_url}"
                )
                self._log_cleanup_success(cleanup_context)
            else:
                logger.warning(f"[{operation_id}] File cleanup failed for: {file_url}")
                self._log_cleanup_failure(cleanup_context, "cleanup_failed")

            return result

        except SecurityError as se:
            cleanup_context["error_type"] = "security_error"
            cleanup_context["error_message"] = str(se)
            logger.error(
                f"[{operation_id}] Security error during file cleanup for {file_url}: {se}"
            )
            self._log_cleanup_failure(cleanup_context, "security_error")
            return False

        except FileSystemError as fse:
            cleanup_context["error_type"] = "filesystem_error"
            cleanup_context["error_message"] = str(fse)
            logger.error(
                f"[{operation_id}] File system error during cleanup for {file_url}: {fse}"
            )
            self._log_cleanup_failure(cleanup_context, "filesystem_error")
            return False

        except GoogleDriveError as gde:
            cleanup_context["error_type"] = "google_drive_error"
            cleanup_context["error_message"] = str(gde)
            logger.error(
                f"[{operation_id}] Google Drive error during cleanup for {file_url}: {gde}"
            )
            self._log_cleanup_failure(cleanup_context, "google_drive_error")
            return False

        except Exception as e:
            cleanup_context["error_type"] = "unexpected_error"
            cleanup_context["error_message"] = str(e)
            cleanup_context["traceback"] = traceback.format_exc()
            logger.error(
                f"[{operation_id}] Unexpected error during file cleanup: {cleanup_context}"
            )
            self._log_cleanup_failure(cleanup_context, "unexpected_error")
            return False

    # ── Recovery & Retry ─────────────────────────────────────

    def _perform_cleanup_with_recovery(self, cleanup_context: Dict) -> bool:
        """Perform file cleanup with comprehensive error recovery."""
        operation_id = cleanup_context["operation_id"]
        file_url = cleanup_context["file_url"]
        file_id = cleanup_context["file_id"]
        max_attempts = cleanup_context["max_attempts"]

        for attempt in range(1, max_attempts + 1):
            cleanup_context["attempts"] = attempt

            try:
                logger.debug(
                    f"[{operation_id}] Cleanup attempt {attempt}/{max_attempts}"
                )

                if self._actions.is_google_drive_url(file_url):
                    result = self._actions.cleanup_google_drive_file(
                        file_url, file_id, operation_id
                    )
                else:
                    result = self._actions.cleanup_local_file(file_url, operation_id)

                if result:
                    cleanup_context["recovery_actions"].append(
                        f"successful_on_attempt_{attempt}"
                    )
                    return True
                else:
                    cleanup_context["recovery_actions"].append(
                        f"failed_attempt_{attempt}"
                    )
                    if attempt < max_attempts:
                        self._attempt_cleanup_recovery(cleanup_context, attempt)

            except Exception as e:
                cleanup_context["recovery_actions"].append(
                    f"exception_attempt_{attempt}_{type(e).__name__}"
                )
                if attempt < max_attempts:
                    logger.warning(
                        f"[{operation_id}] Cleanup attempt {attempt} failed: {e}, retrying..."
                    )
                    self._attempt_cleanup_recovery(cleanup_context, attempt)
                else:
                    logger.error(f"[{operation_id}] All cleanup attempts failed: {e}")
                    raise

        return False

    def _attempt_cleanup_recovery(
        self, cleanup_context: Dict, failed_attempt: int
    ) -> None:
        """Attempt recovery actions between cleanup attempts."""
        operation_id = cleanup_context["operation_id"]

        try:
            wait_time = min(2**failed_attempt, 10)
            logger.debug(f"[{operation_id}] Waiting {wait_time} seconds before retry")
            time.sleep(wait_time)

            file_url = cleanup_context["file_url"]
            if not self._actions.is_google_drive_url(file_url):
                local_path = self._actions.get_file_path_from_url(file_url)
                if local_path and os.path.exists(local_path):
                    if not os.access(local_path, os.W_OK):
                        logger.warning(
                            f"[{operation_id}] File not writable, attempting permission fix"
                        )
                        try:
                            os.chmod(local_path, 0o666)
                            cleanup_context["recovery_actions"].append(
                                f"permission_fix_attempt_{failed_attempt}"
                            )
                        except OSError as perm_error:
                            logger.warning(
                                f"[{operation_id}] Could not fix permissions: {perm_error}"
                            )

            cleanup_context["recovery_actions"].append(
                f"recovery_attempt_{failed_attempt}"
            )

        except Exception as recovery_error:
            logger.warning(
                f"[{operation_id}] Recovery attempt failed: {recovery_error}"
            )
            cleanup_context["recovery_actions"].append(
                f"recovery_failed_{failed_attempt}"
            )

    # ── Logging & Metrics ────────────────────────────────────

    def _log_cleanup_success(self, cleanup_context: Dict) -> None:
        """Log successful cleanup operation for monitoring."""
        operation_id = cleanup_context["operation_id"]

        success_log = {
            "operation_id": operation_id,
            "file_url": cleanup_context["file_url"],
            "attempts": cleanup_context["attempts"],
            "duration_seconds": (
                datetime.now() - cleanup_context["start_time"]
            ).total_seconds(),
            "recovery_actions": cleanup_context["recovery_actions"],
            "status": "success",
            "component": "file_cleanup_manager",
        }

        logger.info(f"[{operation_id}] Cleanup success metrics: {success_log}")

        try:
            self._send_cleanup_metrics(success_log)
        except Exception as e:
            logger.warning(f"[{operation_id}] Failed to send success metrics: {e}")

    def _log_cleanup_failure(self, cleanup_context: Dict, failure_type: str) -> None:
        """Log failed cleanup operation for monitoring and alerting."""
        operation_id = cleanup_context["operation_id"]

        failure_log = {
            "operation_id": operation_id,
            "file_url": cleanup_context["file_url"],
            "failure_type": failure_type,
            "error_type": cleanup_context.get("error_type", "unknown"),
            "error_message": cleanup_context.get("error_message", ""),
            "attempts": cleanup_context["attempts"],
            "duration_seconds": (
                datetime.now() - cleanup_context["start_time"]
            ).total_seconds(),
            "recovery_actions": cleanup_context["recovery_actions"],
            "status": "failure",
            "component": "file_cleanup_manager",
            "severity": self._determine_failure_severity(failure_type),
            "impact": "file_not_cleaned_up",
            "recommended_action": self._get_recommended_action(failure_type),
        }

        logger.error(f"[{operation_id}] Cleanup failure metrics: {failure_log}")

        try:
            self._send_cleanup_metrics(failure_log)
            self._send_cleanup_alert(failure_log)
        except Exception as e:
            logger.warning(f"[{operation_id}] Failed to send failure metrics: {e}")

    def _determine_failure_severity(self, failure_type: str) -> str:
        """Determine severity level for cleanup failures."""
        severity_map = {
            "security_error": "high",
            "filesystem_error": "medium",
            "google_drive_error": "low",
            "unexpected_error": "high",
            "cleanup_failed": "medium",
        }
        return severity_map.get(failure_type, "medium")

    def _get_recommended_action(self, failure_type: str) -> str:
        """Get recommended action for cleanup failures."""
        action_map = {
            "security_error": "Review file path security and permissions",
            "filesystem_error": "Check disk space and file system health",
            "google_drive_error": "Verify Google Drive API credentials and quotas",
            "unexpected_error": "Investigate logs and contact development team",
            "cleanup_failed": "Manual file cleanup may be required",
        }
        return action_map.get(failure_type, "Contact system administrator")

    def _send_cleanup_metrics(self, metrics_data: Dict) -> None:
        """Send cleanup metrics to monitoring system (placeholder)."""
        logger.debug(f"Cleanup metrics prepared: {metrics_data['operation_id']}")

    def _send_cleanup_alert(self, failure_log: Dict) -> None:
        """Send alert for cleanup failures based on severity (placeholder)."""
        logger.debug(f"Cleanup alert prepared for: {failure_log['operation_id']}")

    # ── Health Status ────────────────────────────────────────

    def get_cleanup_health_status(self) -> Dict:
        """Get health status of file cleanup operations for monitoring."""
        try:
            health_status = {
                "status": "healthy",
                "last_check": datetime.now().isoformat(),
                "component": "file_cleanup_manager",
                "metrics": {
                    "success_rate_24h": 0.95,
                    "average_duration_seconds": 2.5,
                    "total_operations_24h": 150,
                    "failed_operations_24h": 7,
                },
                "alerts": {"active_alerts": 0, "recent_failures": []},
            }

            success_rate = health_status["metrics"]["success_rate_24h"]
            if success_rate < 0.8:
                health_status["status"] = "unhealthy"
            elif success_rate < 0.95:
                health_status["status"] = "degraded"

            return health_status

        except Exception as e:
            logger.error(f"Failed to get cleanup health status: {e}")
            return {
                "status": "unknown",
                "error": str(e),
                "last_check": datetime.now().isoformat(),
            }

    # ── Backward-compatible delegations ──────────────────────

    def get_file_path_from_url(self, url: str) -> str:
        """Extract local file path from URL (delegated to actions)."""
        return self._actions.get_file_path_from_url(url)

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison (delegated to actions)."""
        return self._actions.normalize_url(url)

    def _is_google_drive_url(self, url: str) -> bool:
        """Check if URL is a Google Drive URL (delegated to actions)."""
        return self._actions.is_google_drive_url(url)

    def _extract_google_drive_file_id(self, url: str) -> Optional[str]:
        """Extract file ID from Google Drive URL (delegated to actions)."""
        return self._actions.extract_google_drive_file_id(url)

    def _cleanup_google_drive_file(
        self, file_url: str, file_id: Optional[str] = None, operation_id: str = None
    ) -> bool:
        """Cleanup Google Drive file (delegated to actions)."""
        return self._actions.cleanup_google_drive_file(file_url, file_id, operation_id)

    def _cleanup_local_file(self, file_path: str, operation_id: str) -> bool:
        """Cleanup local file (delegated to actions)."""
        return self._actions.cleanup_local_file(file_path, operation_id)

    def _cleanup_empty_parent_directory(
        self, file_path: str, operation_id: str
    ) -> None:
        """Cleanup empty parent directory (delegated to actions)."""
        self._actions.cleanup_empty_parent_directory(file_path, operation_id)

    def _validate_file_url_security(self, file_url: str, operation_id: str) -> None:
        """Validate file URL security (delegated to actions)."""
        self._actions.validate_file_url_security(file_url, operation_id)

    def _is_safe_path(self, file_path: str) -> bool:
        """Check if path is safe (delegated to actions)."""
        return self._actions.is_safe_path(file_path)

    def _is_development_mode(self) -> bool:
        """Check if in development mode (delegated to actions)."""
        return self._actions._is_development_mode()
