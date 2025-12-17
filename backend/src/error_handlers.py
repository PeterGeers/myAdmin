"""
Error Handlers Module

This module provides comprehensive error handling utilities for the duplicate detection system,
including user-friendly error messages, error categorization, and recovery suggestions.
"""

import logging
import traceback
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

# Configure logger for error handling
logger = logging.getLogger(__name__)

class ErrorSeverity(Enum):
    """Error severity levels for categorization and alerting."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ErrorCategory(Enum):
    """Error categories for classification and handling."""
    VALIDATION = "validation"
    DATABASE = "database"
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    BUSINESS_LOGIC = "business_logic"
    SYSTEM = "system"
    EXTERNAL_SERVICE = "external_service"

class DuplicateDetectionErrorHandler:
    """
    Comprehensive error handler for duplicate detection operations.
    
    This class provides centralized error handling, user-friendly message generation,
    and recovery suggestion functionality for all duplicate detection errors.
    """
    
    def __init__(self):
        """Initialize the error handler with error mappings."""
        self.error_mappings = self._initialize_error_mappings()
        self.recovery_suggestions = self._initialize_recovery_suggestions()
    
    def handle_duplicate_detection_error(
        self,
        error: Exception,
        operation_context: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle duplicate detection errors with comprehensive error processing.
        
        Args:
            error: The exception that occurred
            operation_context: Context information about the operation
            user_id: Optional user identifier for personalized messages
        
        Returns:
            Dictionary containing processed error information
        """
        error_info = self._analyze_error(error, operation_context)
        
        # Log the error with full context
        self._log_error_with_context(error_info, operation_context, user_id)
        
        # Generate user-friendly message
        user_message = self._generate_user_friendly_message(error_info, user_id)
        
        # Get recovery suggestions
        recovery_suggestions = self._get_recovery_suggestions(error_info)
        
        # Determine if graceful degradation is possible
        can_continue = self._can_gracefully_degrade(error_info)
        
        return {
            'error_code': error_info['error_code'],
            'error_category': error_info['category'].value,
            'severity': error_info['severity'].value,
            'user_message': user_message,
            'technical_message': error_info['technical_message'],
            'recovery_suggestions': recovery_suggestions,
            'can_continue': can_continue,
            'timestamp': datetime.now().isoformat(),
            'operation_id': operation_context.get('operation_id', 'unknown'),
            'retry_recommended': error_info.get('retry_recommended', False),
            'contact_support': error_info['severity'] in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]
        }
    
    def _analyze_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze error and categorize it for appropriate handling.
        
        Args:
            error: The exception to analyze
            context: Operation context information
        
        Returns:
            Dictionary containing error analysis results
        """
        error_type = type(error).__name__
        error_message = str(error)
        
        # Check for specific error patterns
        if 'connection' in error_message.lower():
            return {
                'error_code': 'DATABASE_CONNECTION_ERROR',
                'category': ErrorCategory.DATABASE,
                'severity': ErrorSeverity.HIGH,
                'technical_message': error_message,
                'retry_recommended': True,
                'graceful_degradation': True
            }
        elif 'timeout' in error_message.lower():
            return {
                'error_code': 'OPERATION_TIMEOUT',
                'category': ErrorCategory.NETWORK,
                'severity': ErrorSeverity.MEDIUM,
                'technical_message': error_message,
                'retry_recommended': True,
                'graceful_degradation': False
            }
        elif 'permission' in error_message.lower() or 'access' in error_message.lower():
            return {
                'error_code': 'PERMISSION_DENIED',
                'category': ErrorCategory.AUTHORIZATION,
                'severity': ErrorSeverity.HIGH,
                'technical_message': error_message,
                'retry_recommended': False,
                'graceful_degradation': False
            }
        elif 'file' in error_message.lower() and ('not found' in error_message.lower() or 'no such file' in error_message.lower()):
            return {
                'error_code': 'FILE_NOT_FOUND',
                'category': ErrorCategory.FILESYSTEM,
                'severity': ErrorSeverity.MEDIUM,
                'technical_message': error_message,
                'retry_recommended': False,
                'graceful_degradation': True
            }
        elif 'validation' in error_message.lower() or 'invalid' in error_message.lower():
            return {
                'error_code': 'VALIDATION_ERROR',
                'category': ErrorCategory.VALIDATION,
                'severity': ErrorSeverity.LOW,
                'technical_message': error_message,
                'retry_recommended': False,
                'graceful_degradation': False
            }
        elif 'session' in error_message.lower():
            return {
                'error_code': 'SESSION_ERROR',
                'category': ErrorCategory.AUTHENTICATION,
                'severity': ErrorSeverity.MEDIUM,
                'technical_message': error_message,
                'retry_recommended': True,
                'graceful_degradation': False
            }
        else:
            # Generic error handling
            return {
                'error_code': 'UNKNOWN_ERROR',
                'category': ErrorCategory.SYSTEM,
                'severity': ErrorSeverity.HIGH,
                'technical_message': error_message,
                'retry_recommended': True,
                'graceful_degradation': True
            }
    
    def _generate_user_friendly_message(
        self,
        error_info: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> str:
        """
        Generate user-friendly error message based on error information.
        
        Args:
            error_info: Error analysis results
            user_id: Optional user identifier for personalization
        
        Returns:
            User-friendly error message
        """
        error_code = error_info['error_code']
        severity = error_info['severity']
        
        # Base messages for different error codes
        base_messages = {
            'DATABASE_CONNECTION_ERROR': "We're having trouble connecting to our database. This is usually temporary.",
            'OPERATION_TIMEOUT': "The operation took longer than expected to complete.",
            'PERMISSION_DENIED': "You don't have permission to perform this action.",
            'FILE_NOT_FOUND': "The file you're trying to process could not be found.",
            'VALIDATION_ERROR': "The information provided is not valid. Please check your input and try again.",
            'SESSION_ERROR': "Your session has expired or is invalid. Please refresh the page and try again.",
            'UNKNOWN_ERROR': "An unexpected error occurred. Our team has been notified."
        }
        
        base_message = base_messages.get(error_code, "An error occurred while processing your request.")
        
        # Add severity-specific guidance
        if severity == ErrorSeverity.LOW:
            guidance = " Please correct the issue and try again."
        elif severity == ErrorSeverity.MEDIUM:
            guidance = " Please try again in a few moments. If the problem persists, contact support."
        elif severity == ErrorSeverity.HIGH:
            guidance = " Please contact support if this problem continues."
        else:  # CRITICAL
            guidance = " Please contact support immediately."
        
        # Add retry guidance if recommended
        if error_info.get('retry_recommended', False):
            guidance += " You may try the operation again."
        
        return base_message + guidance
    
    def _get_recovery_suggestions(self, error_info: Dict[str, Any]) -> List[str]:
        """
        Get recovery suggestions based on error type.
        
        Args:
            error_info: Error analysis results
        
        Returns:
            List of recovery suggestions
        """
        error_code = error_info['error_code']
        
        suggestions_map = {
            'DATABASE_CONNECTION_ERROR': [
                "Wait a few moments and try again",
                "Check your internet connection",
                "Contact support if the problem persists"
            ],
            'OPERATION_TIMEOUT': [
                "Try the operation again",
                "Check your internet connection",
                "Try during off-peak hours if possible"
            ],
            'PERMISSION_DENIED': [
                "Contact your administrator for access",
                "Verify you're logged in with the correct account",
                "Check if your account has the necessary permissions"
            ],
            'FILE_NOT_FOUND': [
                "Verify the file still exists",
                "Try uploading the file again",
                "Check if the file was moved or deleted"
            ],
            'VALIDATION_ERROR': [
                "Review the information you entered",
                "Check for required fields",
                "Ensure data is in the correct format"
            ],
            'SESSION_ERROR': [
                "Refresh the page and log in again",
                "Clear your browser cache and cookies",
                "Try using a different browser"
            ],
            'UNKNOWN_ERROR': [
                "Try the operation again",
                "Refresh the page",
                "Contact support with the error details"
            ]
        }
        
        return suggestions_map.get(error_code, ["Try again later", "Contact support if the problem persists"])
    
    def _can_gracefully_degrade(self, error_info: Dict[str, Any]) -> bool:
        """
        Determine if the system can gracefully degrade for this error.
        
        Args:
            error_info: Error analysis results
        
        Returns:
            Boolean indicating if graceful degradation is possible
        """
        return error_info.get('graceful_degradation', False)
    
    def _log_error_with_context(
        self,
        error_info: Dict[str, Any],
        context: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> None:
        """
        Log error with full context information.
        
        Args:
            error_info: Error analysis results
            context: Operation context
            user_id: Optional user identifier
        """
        log_data = {
            'error_code': error_info['error_code'],
            'category': error_info['category'].value,
            'severity': error_info['severity'].value,
            'technical_message': error_info['technical_message'],
            'operation_id': context.get('operation_id', 'unknown'),
            'operation_type': context.get('operation_type', 'unknown'),
            'user_id': user_id,
            'timestamp': datetime.now().isoformat(),
            'context': context
        }
        
        # Log at appropriate level based on severity
        if error_info['severity'] == ErrorSeverity.CRITICAL:
            logger.critical(f"Critical error in duplicate detection: {log_data}")
        elif error_info['severity'] == ErrorSeverity.HIGH:
            logger.error(f"High severity error in duplicate detection: {log_data}")
        elif error_info['severity'] == ErrorSeverity.MEDIUM:
            logger.warning(f"Medium severity error in duplicate detection: {log_data}")
        else:
            logger.info(f"Low severity error in duplicate detection: {log_data}")
    
    def _initialize_error_mappings(self) -> Dict[str, Dict[str, Any]]:
        """Initialize error code mappings."""
        return {
            # Database errors
            'mysql.connector.errors.DatabaseError': {
                'category': ErrorCategory.DATABASE,
                'severity': ErrorSeverity.HIGH,
                'retry_recommended': True
            },
            'mysql.connector.errors.InterfaceError': {
                'category': ErrorCategory.DATABASE,
                'severity': ErrorSeverity.HIGH,
                'retry_recommended': True
            },
            
            # File system errors
            'FileNotFoundError': {
                'category': ErrorCategory.FILESYSTEM,
                'severity': ErrorSeverity.MEDIUM,
                'retry_recommended': False
            },
            'PermissionError': {
                'category': ErrorCategory.FILESYSTEM,
                'severity': ErrorSeverity.HIGH,
                'retry_recommended': False
            },
            
            # Network errors
            'requests.exceptions.ConnectionError': {
                'category': ErrorCategory.NETWORK,
                'severity': ErrorSeverity.MEDIUM,
                'retry_recommended': True
            },
            'requests.exceptions.Timeout': {
                'category': ErrorCategory.NETWORK,
                'severity': ErrorSeverity.MEDIUM,
                'retry_recommended': True
            },
            
            # Validation errors
            'ValueError': {
                'category': ErrorCategory.VALIDATION,
                'severity': ErrorSeverity.LOW,
                'retry_recommended': False
            },
            'TypeError': {
                'category': ErrorCategory.VALIDATION,
                'severity': ErrorSeverity.LOW,
                'retry_recommended': False
            }
        }
    
    def _initialize_recovery_suggestions(self) -> Dict[ErrorCategory, List[str]]:
        """Initialize recovery suggestions by category."""
        return {
            ErrorCategory.DATABASE: [
                "Check database connection",
                "Verify database credentials",
                "Contact database administrator"
            ],
            ErrorCategory.FILESYSTEM: [
                "Check file permissions",
                "Verify file exists",
                "Check disk space"
            ],
            ErrorCategory.NETWORK: [
                "Check internet connection",
                "Verify network settings",
                "Try again later"
            ],
            ErrorCategory.VALIDATION: [
                "Check input format",
                "Verify required fields",
                "Review data constraints"
            ],
            ErrorCategory.AUTHENTICATION: [
                "Re-login to the system",
                "Check credentials",
                "Contact administrator"
            ],
            ErrorCategory.AUTHORIZATION: [
                "Check user permissions",
                "Contact administrator",
                "Verify account access"
            ]
        }


# Global error handler instance
error_handler = DuplicateDetectionErrorHandler()

def handle_duplicate_detection_error(
    error: Exception,
    operation_context: Dict[str, Any],
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function for handling duplicate detection errors.
    
    Args:
        error: The exception that occurred
        operation_context: Context information about the operation
        user_id: Optional user identifier
    
    Returns:
        Dictionary containing processed error information
    """
    return error_handler.handle_duplicate_detection_error(error, operation_context, user_id)

def user_friendly_error(error_code: str, **kwargs) -> str:
    """
    Generate user-friendly error message for a given error code.
    
    Args:
        error_code: Error code to generate message for
        **kwargs: Additional context for message generation
    
    Returns:
        User-friendly error message
    """
    error_info = {'error_code': error_code, 'severity': ErrorSeverity.MEDIUM}
    return error_handler._generate_user_friendly_message(error_info, kwargs.get('user_id'))


def configure_logging(app):
    """
    Configure logging for the Flask application.
    
    Args:
        app: Flask application instance
    
    Returns:
        Configured logger instance
    """
    import logging
    from logging.handlers import RotatingFileHandler
    import os
    
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Configure file handler
    file_handler = RotatingFileHandler(
        'logs/app.log',
        maxBytes=10240000,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    
    # Configure app logger
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Application startup')
    
    return app.logger


def register_error_handlers(app):
    """
    Register error handlers for the Flask application.
    
    Args:
        app: Flask application instance
    """
    from flask import jsonify
    
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({'error': 'Bad request', 'message': str(error)}), 400
    
    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({'error': 'Unauthorized', 'message': str(error)}), 401
    
    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({'error': 'Forbidden', 'message': str(error)}), 403
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found', 'message': str(error)}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f'Internal server error: {error}')
        return jsonify({'error': 'Internal server error', 'message': str(error)}), 500


def error_response(message: str, status_code: int = 400, **kwargs):
    """
    Generate a standardized error response.
    
    Args:
        message: Error message
        status_code: HTTP status code
        **kwargs: Additional error context
    
    Returns:
        Tuple of (response dict, status code)
    """
    from flask import jsonify
    
    response = {
        'success': False,
        'error': message,
        'status_code': status_code
    }
    response.update(kwargs)
    
    return jsonify(response), status_code