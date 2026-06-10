"""
Unit tests for error_handlers module — error response formatting.

Tests the DuplicateDetectionErrorHandler class: error analysis/categorization,
user-friendly message generation, recovery suggestions, and structured response formatting.
"""

import pytest
from unittest.mock import patch
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from error_handlers import (
    DuplicateDetectionErrorHandler,
    ErrorSeverity,
    ErrorCategory,
    handle_duplicate_detection_error,
    error_response,
    register_error_handlers,
)


@pytest.fixture
def handler():
    """Fresh error handler instance."""
    return DuplicateDetectionErrorHandler()


@pytest.fixture
def operation_context():
    """Standard operation context for tests."""
    return {
        'operation_id': 'op-123',
        'operation_type': 'duplicate_check',
    }


class TestErrorAnalysis:
    """Tests for _analyze_error — classifying exceptions into error codes."""

    def test_connection_error_detected(self, handler):
        """Error message containing 'connection' maps to DATABASE category."""
        error = Exception("Database connection refused")
        result = handler._analyze_error(error, {})

        assert result['error_code'] == 'DATABASE_CONNECTION_ERROR'
        assert result['category'] == ErrorCategory.DATABASE
        assert result['severity'] == ErrorSeverity.HIGH
        assert result['retry_recommended'] is True

    def test_timeout_error_detected(self, handler):
        """Error message containing 'timeout' maps to NETWORK category."""
        error = Exception("Operation timeout after 30s")
        result = handler._analyze_error(error, {})

        assert result['error_code'] == 'OPERATION_TIMEOUT'
        assert result['category'] == ErrorCategory.NETWORK
        assert result['severity'] == ErrorSeverity.MEDIUM
        assert result['retry_recommended'] is True

    def test_permission_error_detected(self, handler):
        """Error message containing 'permission' maps to AUTHORIZATION."""
        error = Exception("Permission denied for this resource")
        result = handler._analyze_error(error, {})

        assert result['error_code'] == 'PERMISSION_DENIED'
        assert result['category'] == ErrorCategory.AUTHORIZATION
        assert result['severity'] == ErrorSeverity.HIGH
        assert result['retry_recommended'] is False

    def test_access_error_detected(self, handler):
        """Error message containing 'access' maps to AUTHORIZATION."""
        error = Exception("Access denied")
        result = handler._analyze_error(error, {})

        assert result['error_code'] == 'PERMISSION_DENIED'
        assert result['category'] == ErrorCategory.AUTHORIZATION

    def test_file_not_found_error_detected(self, handler):
        """Error about file not found maps to FILESYSTEM category."""
        error = Exception("File not found: /path/to/data.csv")
        result = handler._analyze_error(error, {})

        assert result['error_code'] == 'FILE_NOT_FOUND'
        assert result['category'] == ErrorCategory.FILESYSTEM
        assert result['severity'] == ErrorSeverity.MEDIUM
        assert result['retry_recommended'] is False

    def test_no_such_file_error_detected(self, handler):
        """Error about 'no such file' maps to FILESYSTEM category."""
        error = Exception("No such file or directory")
        result = handler._analyze_error(error, {})

        assert result['error_code'] == 'FILE_NOT_FOUND'
        assert result['category'] == ErrorCategory.FILESYSTEM

    def test_validation_error_detected(self, handler):
        """Error about 'validation' maps to VALIDATION category."""
        error = Exception("Validation failed for input field")
        result = handler._analyze_error(error, {})

        assert result['error_code'] == 'VALIDATION_ERROR'
        assert result['category'] == ErrorCategory.VALIDATION
        assert result['severity'] == ErrorSeverity.LOW
        assert result['retry_recommended'] is False

    def test_invalid_keyword_detected(self, handler):
        """Error containing 'invalid' maps to VALIDATION category."""
        error = Exception("Invalid date format")
        result = handler._analyze_error(error, {})

        assert result['error_code'] == 'VALIDATION_ERROR'
        assert result['category'] == ErrorCategory.VALIDATION

    def test_session_error_detected(self, handler):
        """Error about 'session' maps to AUTHENTICATION category."""
        error = Exception("Session expired")
        result = handler._analyze_error(error, {})

        assert result['error_code'] == 'SESSION_ERROR'
        assert result['category'] == ErrorCategory.AUTHENTICATION
        assert result['severity'] == ErrorSeverity.MEDIUM
        assert result['retry_recommended'] is True

    def test_unknown_error_fallback(self, handler):
        """Unrecognized error maps to UNKNOWN_ERROR / SYSTEM category."""
        error = Exception("Something completely unexpected happened")
        result = handler._analyze_error(error, {})

        assert result['error_code'] == 'UNKNOWN_ERROR'
        assert result['category'] == ErrorCategory.SYSTEM
        assert result['severity'] == ErrorSeverity.HIGH
        assert result['retry_recommended'] is True

    def test_technical_message_preserved(self, handler):
        """Original error message stored in technical_message."""
        msg = "Specific technical detail: errno=42"
        error = Exception(msg)
        result = handler._analyze_error(error, {})

        assert result['technical_message'] == msg


class TestUserFriendlyMessages:
    """Tests for _generate_user_friendly_message — producing end-user messages."""

    def test_database_connection_message(self, handler):
        """DATABASE_CONNECTION_ERROR produces helpful message."""
        error_info = {
            'error_code': 'DATABASE_CONNECTION_ERROR',
            'severity': ErrorSeverity.HIGH,
            'retry_recommended': True,
        }
        msg = handler._generate_user_friendly_message(error_info)

        assert "trouble connecting" in msg.lower()
        assert "try" in msg.lower()

    def test_timeout_message(self, handler):
        """OPERATION_TIMEOUT produces informative message."""
        error_info = {
            'error_code': 'OPERATION_TIMEOUT',
            'severity': ErrorSeverity.MEDIUM,
            'retry_recommended': True,
        }
        msg = handler._generate_user_friendly_message(error_info)

        assert "longer than expected" in msg.lower()

    def test_permission_denied_message(self, handler):
        """PERMISSION_DENIED produces access-related message."""
        error_info = {
            'error_code': 'PERMISSION_DENIED',
            'severity': ErrorSeverity.HIGH,
            'retry_recommended': False,
        }
        msg = handler._generate_user_friendly_message(error_info)

        assert "permission" in msg.lower()

    def test_validation_error_message(self, handler):
        """VALIDATION_ERROR suggests correcting input."""
        error_info = {
            'error_code': 'VALIDATION_ERROR',
            'severity': ErrorSeverity.LOW,
            'retry_recommended': False,
        }
        msg = handler._generate_user_friendly_message(error_info)

        assert "not valid" in msg.lower() or "check" in msg.lower()

    def test_severity_low_adds_correction_guidance(self, handler):
        """LOW severity adds 'correct the issue' guidance."""
        error_info = {
            'error_code': 'VALIDATION_ERROR',
            'severity': ErrorSeverity.LOW,
            'retry_recommended': False,
        }
        msg = handler._generate_user_friendly_message(error_info)

        assert "correct" in msg.lower()

    def test_severity_critical_adds_support_guidance(self, handler):
        """CRITICAL severity adds 'contact support immediately' guidance."""
        error_info = {
            'error_code': 'UNKNOWN_ERROR',
            'severity': ErrorSeverity.CRITICAL,
            'retry_recommended': False,
        }
        msg = handler._generate_user_friendly_message(error_info)

        assert "immediately" in msg.lower()

    def test_retry_recommended_adds_retry_text(self, handler):
        """When retry is recommended, message mentions trying again."""
        error_info = {
            'error_code': 'OPERATION_TIMEOUT',
            'severity': ErrorSeverity.MEDIUM,
            'retry_recommended': True,
        }
        msg = handler._generate_user_friendly_message(error_info)

        assert "try" in msg.lower()


class TestRecoverySuggestions:
    """Tests for _get_recovery_suggestions — actionable recovery steps."""

    def test_database_suggestions(self, handler):
        """DATABASE_CONNECTION_ERROR returns connection-related suggestions."""
        error_info = {'error_code': 'DATABASE_CONNECTION_ERROR'}
        suggestions = handler._get_recovery_suggestions(error_info)

        assert isinstance(suggestions, list)
        assert len(suggestions) >= 2
        assert any("wait" in s.lower() or "try again" in s.lower() for s in suggestions)

    def test_timeout_suggestions(self, handler):
        """OPERATION_TIMEOUT returns retry-oriented suggestions."""
        error_info = {'error_code': 'OPERATION_TIMEOUT'}
        suggestions = handler._get_recovery_suggestions(error_info)

        assert len(suggestions) >= 2
        assert any("try" in s.lower() for s in suggestions)

    def test_permission_suggestions(self, handler):
        """PERMISSION_DENIED returns admin-contact suggestions."""
        error_info = {'error_code': 'PERMISSION_DENIED'}
        suggestions = handler._get_recovery_suggestions(error_info)

        assert any("administrator" in s.lower() or "admin" in s.lower() for s in suggestions)

    def test_file_not_found_suggestions(self, handler):
        """FILE_NOT_FOUND returns file-verification suggestions."""
        error_info = {'error_code': 'FILE_NOT_FOUND'}
        suggestions = handler._get_recovery_suggestions(error_info)

        assert any("file" in s.lower() for s in suggestions)

    def test_unknown_error_has_fallback_suggestions(self, handler):
        """UNKNOWN_ERROR still returns useful fallback suggestions."""
        error_info = {'error_code': 'UNKNOWN_ERROR'}
        suggestions = handler._get_recovery_suggestions(error_info)

        assert len(suggestions) >= 1

    def test_completely_unknown_code_returns_generic(self, handler):
        """Unrecognized error code returns generic fallback list."""
        error_info = {'error_code': 'NEVER_SEEN_BEFORE'}
        suggestions = handler._get_recovery_suggestions(error_info)

        assert isinstance(suggestions, list)
        assert len(suggestions) >= 1


class TestGracefulDegradation:
    """Tests for _can_gracefully_degrade."""

    def test_database_error_can_degrade(self, handler):
        """Database connection errors allow graceful degradation."""
        error_info = {'graceful_degradation': True}
        assert handler._can_gracefully_degrade(error_info) is True

    def test_permission_error_cannot_degrade(self, handler):
        """Permission errors do not allow graceful degradation."""
        error_info = {'graceful_degradation': False}
        assert handler._can_gracefully_degrade(error_info) is False

    def test_missing_flag_defaults_to_false(self, handler):
        """Missing graceful_degradation flag defaults to False."""
        error_info = {}
        assert handler._can_gracefully_degrade(error_info) is False


class TestHandleDuplicateDetectionError:
    """Tests for the full handle_duplicate_detection_error flow — end-to-end response formatting."""

    def test_response_contains_required_fields(self, handler, operation_context):
        """Response dictionary contains all expected keys."""
        error = Exception("Database connection lost")
        result = handler.handle_duplicate_detection_error(error, operation_context)

        assert 'error_code' in result
        assert 'error_category' in result
        assert 'severity' in result
        assert 'user_message' in result
        assert 'technical_message' in result
        assert 'recovery_suggestions' in result
        assert 'can_continue' in result
        assert 'timestamp' in result
        assert 'operation_id' in result
        assert 'retry_recommended' in result
        assert 'contact_support' in result

    def test_operation_id_from_context(self, handler, operation_context):
        """operation_id comes from the operation_context."""
        error = Exception("timeout error")
        result = handler.handle_duplicate_detection_error(error, operation_context)

        assert result['operation_id'] == 'op-123'

    def test_operation_id_defaults_to_unknown(self, handler):
        """Missing operation_id defaults to 'unknown'."""
        error = Exception("some error")
        result = handler.handle_duplicate_detection_error(error, {})

        assert result['operation_id'] == 'unknown'

    def test_timestamp_is_iso_format(self, handler, operation_context):
        """Timestamp is in ISO format."""
        error = Exception("timeout")
        result = handler.handle_duplicate_detection_error(error, operation_context)

        # Should parse without error
        parsed = datetime.fromisoformat(result['timestamp'])
        assert parsed is not None

    def test_contact_support_true_for_high_severity(self, handler, operation_context):
        """contact_support is True for HIGH and CRITICAL severity."""
        error = Exception("Database connection failed")  # -> HIGH
        result = handler.handle_duplicate_detection_error(error, operation_context)

        assert result['contact_support'] is True

    def test_contact_support_false_for_low_severity(self, handler, operation_context):
        """contact_support is False for LOW severity."""
        error = Exception("Validation error: invalid input")  # -> LOW
        result = handler.handle_duplicate_detection_error(error, operation_context)

        assert result['contact_support'] is False

    def test_error_category_is_string_value(self, handler, operation_context):
        """error_category is the string value of the enum."""
        error = Exception("Operation timeout")
        result = handler.handle_duplicate_detection_error(error, operation_context)

        assert result['error_category'] == 'network'

    def test_severity_is_string_value(self, handler, operation_context):
        """severity is the string value of the enum."""
        error = Exception("Validation failed: invalid format")
        result = handler.handle_duplicate_detection_error(error, operation_context)

        assert result['severity'] == 'low'

    def test_recovery_suggestions_is_list(self, handler, operation_context):
        """recovery_suggestions is a non-empty list."""
        error = Exception("file not found: missing.csv")
        result = handler.handle_duplicate_detection_error(error, operation_context)

        assert isinstance(result['recovery_suggestions'], list)
        assert len(result['recovery_suggestions']) >= 1


class TestConvenienceFunction:
    """Tests for the module-level handle_duplicate_detection_error convenience function."""

    def test_convenience_function_returns_same_structure(self):
        """Module-level function returns the same structure as the method."""
        context = {'operation_id': 'test-op', 'operation_type': 'scan'}
        error = Exception("Request timeout after 30 seconds")

        result = handle_duplicate_detection_error(error, context, user_id='user@example.com')

        assert result['error_code'] == 'OPERATION_TIMEOUT'
        assert result['operation_id'] == 'test-op'
        assert 'user_message' in result


class TestErrorResponseFunction:
    """Tests for the error_response helper function."""

    def test_default_status_code_is_400(self):
        """Default status code is 400."""
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            response, code = error_response("Bad input")
            assert code == 400

    def test_custom_status_code(self):
        """Custom status code is returned."""
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            response, code = error_response("Server error", 500)
            assert code == 500

    def test_response_body_structure(self):
        """Response includes success=False, error message, and status_code."""
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            response, _ = error_response("Not authorized", 403)
            data = response.get_json()
            assert data['success'] is False
            assert data['error'] == "Not authorized"
            assert data['status_code'] == 403

    def test_extra_kwargs_included(self):
        """Additional keyword arguments are merged into the response."""
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            response, _ = error_response("Conflict", 409, field="name", detail="already exists")
            data = response.get_json()
            assert data['field'] == "name"
            assert data['detail'] == "already exists"


class TestRegisterErrorHandlers:
    """Tests for register_error_handlers — Flask error handler formatting."""

    @pytest.fixture
    def app(self):
        """Flask app with error handlers registered."""
        from flask import Flask
        app = Flask(__name__)
        app.config['TESTING'] = True
        register_error_handlers(app)
        return app

    def test_400_handler_returns_json(self, app):
        """400 error returns JSON with error key."""
        with app.test_client() as client:
            # Trigger 400 via abort
            @app.route('/test-400')
            def trigger_400():
                from flask import abort
                abort(400)

            resp = client.get('/test-400')
            assert resp.status_code == 400
            data = resp.get_json()
            assert data['error'] == 'Bad request'

    def test_401_handler_returns_json(self, app):
        """401 error returns JSON with Unauthorized."""
        with app.test_client() as client:
            @app.route('/test-401')
            def trigger_401():
                from flask import abort
                abort(401)

            resp = client.get('/test-401')
            assert resp.status_code == 401
            data = resp.get_json()
            assert data['error'] == 'Unauthorized'

    def test_403_handler_returns_json(self, app):
        """403 error returns JSON with Forbidden."""
        with app.test_client() as client:
            @app.route('/test-403')
            def trigger_403():
                from flask import abort
                abort(403)

            resp = client.get('/test-403')
            assert resp.status_code == 403
            data = resp.get_json()
            assert data['error'] == 'Forbidden'

    def test_404_handler_returns_json(self, app):
        """404 error returns JSON with Not found."""
        with app.test_client() as client:
            resp = client.get('/nonexistent-route')
            assert resp.status_code == 404
            data = resp.get_json()
            assert data['error'] == 'Not found'

    def test_500_handler_returns_json(self, app):
        """500 error returns JSON with Internal server error."""
        with app.test_client() as client:
            @app.route('/test-500')
            def trigger_500():
                from flask import abort
                abort(500)

            resp = client.get('/test-500')
            assert resp.status_code == 500
            data = resp.get_json()
            assert data['error'] == 'Internal server error'


class TestErrorSeverityEnum:
    """Tests for ErrorSeverity enum values."""

    def test_all_severity_values(self):
        assert ErrorSeverity.LOW.value == "low"
        assert ErrorSeverity.MEDIUM.value == "medium"
        assert ErrorSeverity.HIGH.value == "high"
        assert ErrorSeverity.CRITICAL.value == "critical"


class TestErrorCategoryEnum:
    """Tests for ErrorCategory enum values."""

    def test_all_category_values(self):
        assert ErrorCategory.VALIDATION.value == "validation"
        assert ErrorCategory.DATABASE.value == "database"
        assert ErrorCategory.FILESYSTEM.value == "filesystem"
        assert ErrorCategory.NETWORK.value == "network"
        assert ErrorCategory.AUTHENTICATION.value == "authentication"
        assert ErrorCategory.AUTHORIZATION.value == "authorization"
        assert ErrorCategory.SYSTEM.value == "system"
