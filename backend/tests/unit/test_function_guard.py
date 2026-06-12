"""
Unit tests for the function_guard decorator.

Tests the three-step check order:
1. Tenant context present
2. Parent module active
3. Function toggle enabled

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
Reference: .kiro/specs/tenant-optional-functions/design.md
"""

import sys
import os
import pytest
from unittest.mock import Mock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.function_guard import function_guard


class TestFunctionGuardNoTenant:
    """Step 1: Returns 403 when tenant context is missing."""

    def test_returns_403_when_no_tenant_in_kwargs(self):
        import flask
        app = flask.Flask(__name__)

        @function_guard('assets', 'FIN')
        def dummy(**kwargs):
            return 'ok'

        with app.test_request_context():
            result = dummy()
            response, status_code = result
            assert status_code == 403
            data = response.get_json()
            assert data['success'] is False
            assert data['error'] == 'Tenant context required'

    def test_returns_403_when_tenant_is_none(self):
        import flask
        app = flask.Flask(__name__)

        @function_guard('assets', 'FIN')
        def dummy(**kwargs):
            return 'ok'

        with app.test_request_context():
            result = dummy(tenant=None)
            response, status_code = result
            assert status_code == 403
            data = response.get_json()
            assert data['error'] == 'Tenant context required'


class TestFunctionGuardModuleCheck:
    """Step 2: Returns 403 when parent module is inactive."""

    def test_returns_403_when_module_inactive(self):
        import flask
        app = flask.Flask(__name__)

        with app.test_request_context():
            with patch('database.DatabaseManager') as MockDB:
                mock_db = Mock()
                # has_module will query tenant_modules - return empty (inactive)
                mock_db.execute_query = Mock(return_value=[])
                MockDB.return_value = mock_db

                @function_guard('assets', 'FIN')
                def dummy(**kwargs):
                    return 'ok'

                result = dummy(tenant='TestTenant')
                response, status_code = result
                assert status_code == 403
                data = response.get_json()
                assert data['success'] is False
                assert data['error'] == "Module 'FIN' is not active for this tenant"

    def test_error_message_includes_module_name(self):
        import flask
        app = flask.Flask(__name__)

        with app.test_request_context():
            with patch('database.DatabaseManager') as MockDB:
                mock_db = Mock()
                mock_db.execute_query = Mock(return_value=[])
                MockDB.return_value = mock_db

                @function_guard('str_channel_revenue', 'STR')
                def dummy(**kwargs):
                    return 'ok'

                result = dummy(tenant='TestTenant')
                response, status_code = result
                data = response.get_json()
                assert "'STR'" in data['error']


class TestFunctionGuardFunctionCheck:
    """Step 3: Returns 403 when function is disabled."""

    def test_returns_403_when_function_disabled(self):
        import flask
        app = flask.Flask(__name__)

        with app.test_request_context():
            with patch('database.DatabaseManager') as MockDB:
                mock_db = Mock()
                # First call: has_module check - module is active
                # Second call: get_function_state - function is disabled
                mock_db.execute_query = Mock(side_effect=[
                    [{'is_active': True}],   # has_module returns active
                    [{'is_active': False}],   # get_function_state returns disabled
                ])
                MockDB.return_value = mock_db

                @function_guard('assets', 'FIN')
                def dummy(**kwargs):
                    return 'ok'

                result = dummy(tenant='TestTenant')
                response, status_code = result
                assert status_code == 403
                data = response.get_json()
                assert data['success'] is False
                assert data['error'] == "Function 'assets' is disabled for this tenant"

    def test_error_message_includes_function_name(self):
        import flask
        app = flask.Flask(__name__)

        with app.test_request_context():
            with patch('database.DatabaseManager') as MockDB:
                mock_db = Mock()
                mock_db.execute_query = Mock(side_effect=[
                    [{'is_active': True}],   # has_module
                    [{'is_active': False}],   # get_function_state
                ])
                MockDB.return_value = mock_db

                @function_guard('generate_invoice', 'FIN')
                def dummy(**kwargs):
                    return 'ok'

                result = dummy(tenant='TestTenant')
                response, status_code = result
                data = response.get_json()
                assert "'generate_invoice'" in data['error']


class TestFunctionGuardPassThrough:
    """Passes through to route handler when all checks pass."""

    def test_passes_through_when_module_active_and_function_enabled(self):
        import flask
        app = flask.Flask(__name__)

        with app.test_request_context():
            with patch('database.DatabaseManager') as MockDB:
                mock_db = Mock()
                mock_db.execute_query = Mock(side_effect=[
                    [{'is_active': True}],   # has_module - active
                    [{'is_active': True}],   # get_function_state - enabled
                ])
                MockDB.return_value = mock_db

                @function_guard('assets', 'FIN')
                def dummy(**kwargs):
                    return 'ok'

                result = dummy(tenant='TestTenant')
                assert result == 'ok'

    def test_preserves_kwargs_to_handler(self):
        import flask
        app = flask.Flask(__name__)

        with app.test_request_context():
            with patch('database.DatabaseManager') as MockDB:
                mock_db = Mock()
                mock_db.execute_query = Mock(side_effect=[
                    [{'is_active': True}],
                    [{'is_active': True}],
                ])
                MockDB.return_value = mock_db

                @function_guard('assets', 'FIN')
                def dummy(**kwargs):
                    return kwargs

                result = dummy(
                    user_email='test@example.com',
                    user_roles=['admin'],
                    tenant='TestTenant',
                    user_tenants=['TestTenant']
                )
                assert result['user_email'] == 'test@example.com'
                assert result['tenant'] == 'TestTenant'
                assert result['user_roles'] == ['admin']
                assert result['user_tenants'] == ['TestTenant']

    def test_function_enabled_by_registry_default(self):
        """When no DB override exists, registry default (True) allows pass-through."""
        import flask
        app = flask.Flask(__name__)

        with app.test_request_context():
            with patch('database.DatabaseManager') as MockDB:
                mock_db = Mock()
                mock_db.execute_query = Mock(side_effect=[
                    [{'is_active': True}],   # has_module - active
                    [],                       # No override in tenant_functions
                ])
                MockDB.return_value = mock_db

                @function_guard('assets', 'FIN')
                def dummy(**kwargs):
                    return 'ok'

                result = dummy(tenant='TestTenant')
                assert result == 'ok'


class TestFunctionGuardCheckOrder:
    """Verifies the decorator checks in correct order: tenant → module → function."""

    def test_tenant_check_before_module_check(self):
        """If no tenant, should not attempt DB call for module check."""
        import flask
        app = flask.Flask(__name__)

        with app.test_request_context():
            with patch('database.DatabaseManager') as MockDB:
                mock_db = Mock()
                MockDB.return_value = mock_db

                @function_guard('assets', 'FIN')
                def dummy(**kwargs):
                    return 'ok'

                result = dummy()
                response, status_code = result
                assert status_code == 403
                # DatabaseManager should not have been instantiated
                MockDB.assert_not_called()

    def test_module_check_before_function_check(self):
        """If module inactive, should not query for function state."""
        import flask
        app = flask.Flask(__name__)

        with app.test_request_context():
            with patch('database.DatabaseManager') as MockDB:
                mock_db = Mock()
                # Only one call: has_module returns inactive
                mock_db.execute_query = Mock(return_value=[])
                MockDB.return_value = mock_db

                @function_guard('assets', 'FIN')
                def dummy(**kwargs):
                    return 'ok'

                result = dummy(tenant='TestTenant')
                response, status_code = result
                assert status_code == 403
                # Only one execute_query call (for module check)
                assert mock_db.execute_query.call_count == 1
