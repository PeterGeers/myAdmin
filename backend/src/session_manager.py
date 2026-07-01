"""
Session Manager Component

This module provides session management functionality for duplicate detection operations,
including session validation, timeout handling, and cleanup operations.
"""

import logging
import time
import threading
from typing import Dict, Optional
from datetime import datetime
from dataclasses import dataclass

# Configure logger for session management
logger = logging.getLogger(__name__)


class SessionTimeoutError(Exception):
    """Exception for session timeout scenarios."""

    pass


class SessionValidationError(Exception):
    """Exception for session validation failures."""

    pass


@dataclass
class SessionInfo:
    """Session information data class."""

    session_id: str
    created_at: datetime
    last_accessed: datetime
    user_id: Optional[str] = None
    operation_type: Optional[str] = None
    timeout_seconds: int = 1800  # 30 minutes default


class SessionManager:
    """
    Manages user sessions for duplicate detection operations.

    This class provides session validation, timeout handling, and cleanup
    operations to ensure secure and reliable session management.
    """

    def __init__(self, default_timeout_seconds: int = 1800):
        """
        Initialize the SessionManager.

        Args:
            default_timeout_seconds: Default session timeout in seconds (30 minutes)
        """
        self.default_timeout_seconds = default_timeout_seconds
        self.sessions: Dict[str, SessionInfo] = {}
        self.cleanup_interval = 300  # 5 minutes
        self.lock = threading.RLock()

        # Start background cleanup thread
        self._start_cleanup_thread()

    def validate_session(
        self, session_id: str, operation_id: Optional[str] = None
    ) -> bool:
        """
        Validate session and check for timeout.

        Args:
            session_id: Session identifier to validate
            operation_id: Optional operation identifier for logging

        Returns:
            Boolean indicating if session is valid and not timed out

        Raises:
            SessionTimeoutError: If session has timed out
            SessionValidationError: If session is invalid
        """
        if not session_id or not session_id.strip():
            raise SessionValidationError("Session ID cannot be empty")

        session_id = session_id.strip()
        operation_log = f"[{operation_id}]" if operation_id else ""

        with self.lock:
            if session_id not in self.sessions:
                logger.warning(f"{operation_log} Session not found: {session_id}")
                raise SessionValidationError(f"Session not found: {session_id}")

            session_info = self.sessions[session_id]
            now = datetime.now()

            # Check if session has timed out
            time_since_access = (now - session_info.last_accessed).total_seconds()
            if time_since_access > session_info.timeout_seconds:
                logger.warning(
                    f"{operation_log} Session timed out: {session_id} (inactive for {time_since_access:.1f}s)"
                )
                # Remove timed out session
                del self.sessions[session_id]
                raise SessionTimeoutError(
                    f"Session {session_id} has timed out after {time_since_access:.1f} seconds"
                )

            # Update last accessed time
            session_info.last_accessed = now
            logger.debug(f"{operation_log} Session validated: {session_id}")

            return True

    def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions.

        Returns:
            Number of sessions that were cleaned up
        """
        expired_sessions = []
        now = datetime.now()

        with self.lock:
            for session_id, session_info in self.sessions.items():
                time_since_access = (now - session_info.last_accessed).total_seconds()
                if time_since_access > session_info.timeout_seconds:
                    expired_sessions.append(session_id)

            # Remove expired sessions
            for session_id in expired_sessions:
                del self.sessions[session_id]

        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

        return len(expired_sessions)

    def _start_cleanup_thread(self) -> None:
        """Start background thread for periodic session cleanup."""

        def cleanup_worker():
            while True:
                try:
                    time.sleep(self.cleanup_interval)
                    self.cleanup_expired_sessions()
                except Exception as e:
                    logger.error(f"Error in session cleanup thread: {e}")

        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        logger.info("Started session cleanup background thread")


# Global session manager instance
session_manager = SessionManager()
