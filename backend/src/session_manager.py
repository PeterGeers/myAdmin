"""
Session Manager Component

This module provides session management functionality for duplicate detection operations,
including session validation, timeout handling, and cleanup operations.
"""

import logging
import time
import threading
from typing import Dict, Optional, Set
from datetime import datetime, timedelta
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
    
    def create_session(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        operation_type: Optional[str] = None,
        timeout_seconds: Optional[int] = None
    ) -> SessionInfo:
        """
        Create a new session with specified parameters.
        
        Args:
            session_id: Unique session identifier
            user_id: Optional user identifier
            operation_type: Optional operation type (e.g., 'duplicate_detection')
            timeout_seconds: Optional custom timeout in seconds
        
        Returns:
            SessionInfo object for the created session
        
        Raises:
            SessionValidationError: If session_id is invalid or already exists
        """
        if not session_id or not session_id.strip():
            raise SessionValidationError("Session ID cannot be empty")
        
        session_id = session_id.strip()
        
        with self.lock:
            if session_id in self.sessions:
                # Update existing session instead of creating duplicate
                existing_session = self.sessions[session_id]
                existing_session.last_accessed = datetime.now()
                logger.info(f"Updated existing session: {session_id}")
                return existing_session
            
            # Create new session
            now = datetime.now()
            session_info = SessionInfo(
                session_id=session_id,
                created_at=now,
                last_accessed=now,
                user_id=user_id,
                operation_type=operation_type,
                timeout_seconds=timeout_seconds or self.default_timeout_seconds
            )
            
            self.sessions[session_id] = session_info
            logger.info(f"Created new session: {session_id} for user: {user_id}")
            
            return session_info
    
    def validate_session(self, session_id: str, operation_id: Optional[str] = None) -> bool:
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
                logger.warning(f"{operation_log} Session timed out: {session_id} (inactive for {time_since_access:.1f}s)")
                # Remove timed out session
                del self.sessions[session_id]
                raise SessionTimeoutError(f"Session {session_id} has timed out after {time_since_access:.1f} seconds")
            
            # Update last accessed time
            session_info.last_accessed = now
            logger.debug(f"{operation_log} Session validated: {session_id}")
            
            return True
    
    def extend_session(self, session_id: str, additional_seconds: int = 0) -> bool:
        """
        Extend session timeout by updating last accessed time.
        
        Args:
            session_id: Session identifier to extend
            additional_seconds: Additional seconds to add to timeout (optional)
        
        Returns:
            Boolean indicating if session was successfully extended
        """
        if not session_id or not session_id.strip():
            return False
        
        session_id = session_id.strip()
        
        with self.lock:
            if session_id not in self.sessions:
                logger.warning(f"Cannot extend non-existent session: {session_id}")
                return False
            
            session_info = self.sessions[session_id]
            session_info.last_accessed = datetime.now()
            
            if additional_seconds > 0:
                session_info.timeout_seconds += additional_seconds
            
            logger.debug(f"Extended session: {session_id}")
            return True
    
    def invalidate_session(self, session_id: str) -> bool:
        """
        Invalidate and remove a session.
        
        Args:
            session_id: Session identifier to invalidate
        
        Returns:
            Boolean indicating if session was successfully invalidated
        """
        if not session_id or not session_id.strip():
            return False
        
        session_id = session_id.strip()
        
        with self.lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info(f"Invalidated session: {session_id}")
                return True
            else:
                logger.debug(f"Session not found for invalidation: {session_id}")
                return False
    
    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """
        Get session information without updating access time.
        
        Args:
            session_id: Session identifier to query
        
        Returns:
            SessionInfo object if session exists, None otherwise
        """
        if not session_id or not session_id.strip():
            return None
        
        session_id = session_id.strip()
        
        with self.lock:
            return self.sessions.get(session_id)
    
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
    
    def get_active_session_count(self) -> int:
        """
        Get count of active sessions.
        
        Returns:
            Number of active sessions
        """
        with self.lock:
            return len(self.sessions)
    
    def get_session_statistics(self) -> Dict:
        """
        Get session statistics for monitoring.
        
        Returns:
            Dictionary containing session statistics
        """
        now = datetime.now()
        stats = {
            'total_sessions': 0,
            'sessions_by_operation': {},
            'sessions_by_age': {
                'under_5_minutes': 0,
                'under_30_minutes': 0,
                'over_30_minutes': 0
            },
            'average_age_seconds': 0,
            'oldest_session_age_seconds': 0
        }
        
        with self.lock:
            if not self.sessions:
                return stats
            
            stats['total_sessions'] = len(self.sessions)
            total_age = 0
            max_age = 0
            
            for session_info in self.sessions.values():
                # Age statistics
                age_seconds = (now - session_info.created_at).total_seconds()
                total_age += age_seconds
                max_age = max(max_age, age_seconds)
                
                # Age buckets
                if age_seconds < 300:  # 5 minutes
                    stats['sessions_by_age']['under_5_minutes'] += 1
                elif age_seconds < 1800:  # 30 minutes
                    stats['sessions_by_age']['under_30_minutes'] += 1
                else:
                    stats['sessions_by_age']['over_30_minutes'] += 1
                
                # Operation type statistics
                operation_type = session_info.operation_type or 'unknown'
                stats['sessions_by_operation'][operation_type] = (
                    stats['sessions_by_operation'].get(operation_type, 0) + 1
                )
            
            stats['average_age_seconds'] = total_age / len(self.sessions)
            stats['oldest_session_age_seconds'] = max_age
        
        return stats
    
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