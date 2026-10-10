"""
API tests for members_analytics_audit.py (member-analytics task 10.1, Design C7).

Covers the POST /api/members/analytics-audit route (the client-side CSV / PDF-label
audit signal):
  - happy path: records a metadata-only audit entry through the shared helper, with
    the tenant resolved from the auth context;
  - capability denied: a caller without members:export is rejected (403);
  - validation: an unknown / server-only output_kind is rejected (400);
  - tenant isolation: a client-supplied tenant in the body is ignored;
  - PII guard: a PII-named filter key is never logged (R8.3).

(The former server-side Members SES mail route + its test were retired to the SAM
plane per the mail spec, task 4.1; this client-side export-audit route remains.)

Validates: Requirements R8.1, R8.3
"""
import json
from unittest.mock import patch

import pytest


@pytest.fixture
def export_auth():
    """Auth with a Members role that grants members:export."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['Members_Export']):
        mock_creds.return_value = ('exporter@example.com', ['Members_Export'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


@pytest.fixture
def no_export_auth():
    """Auth with a read-only role that does NOT grant members:export."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['Members_Read']):
        mock_creds.return_value = ('reader@example.com', ['Members_Read'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


class TestAnalyticsAuditCapabilityGate:
    """members:export capability enforcement (R4.12 / C7)."""

    def test_audit_without_export_capability_returns_403(self, client, no_export_auth):
        response = client.post(
            '/api/members/analytics-audit',
            headers=no_export_auth,
            json={'output_kind': 'csv_export'},
        )
        assert response.status_code == 403


class TestAnalyticsAuditValidation:
    """Request validation + accepted output kinds."""

    @patch('routes.members_analytics_audit.get_current_tenant', return_value='test-tenant')
    def test_audit_no_data_returns_400(self, mock_tenant, client, export_auth):
        response = client.post(
            '/api/members/analytics-audit', headers=export_auth, json={}
        )
        assert response.status_code == 400

    @patch('routes.members_analytics_audit.get_current_tenant', return_value='test-tenant')
    def test_audit_unknown_output_kind_returns_400(
        self, mock_tenant, client, export_auth
    ):
        response = client.post(
            '/api/members/analytics-audit',
            headers=export_auth,
            json={'output_kind': 'delete_all'},
        )
        assert response.status_code == 400

    @patch('routes.members_analytics_audit.get_current_tenant', return_value='test-tenant')
    def test_audit_rejects_server_only_mail_kind(
        self, mock_tenant, client, export_auth
    ):
        """A client cannot forge a 'mail sent' audit through this route (C7)."""
        response = client.post(
            '/api/members/analytics-audit',
            headers=export_auth,
            json={'output_kind': 'ses_mail'},
        )
        assert response.status_code == 400


class TestAnalyticsAuditHappyPath:
    """Successful recording through the shared audit helper."""

    @patch('routes.members_analytics_audit.get_current_tenant', return_value='test-tenant')
    def test_audit_csv_export_records_metadata_only(
        self, mock_tenant, client, export_auth
    ):
        with patch(
            'services.analytics_audit.log_successful_access'
        ) as mock_access_log:
            response = client.post(
                '/api/members/analytics-audit',
                headers=export_auth,
                json={
                    'output_kind': 'csv_export',
                    'set_key': 'members-per-type',
                    'record_count': 128,
                    'filter_summary': {'membership_type': 'gold'},
                },
            )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        audit = data['audit']
        assert audit['output_kind'] == 'csv_export'
        assert audit['set_key'] == 'members-per-type'
        assert audit['record_count'] == 128
        # Tenant comes from the auth context, actor from the verified identity.
        assert audit['tenant'] == 'test-tenant'
        assert audit['actor'] == 'exporter@example.com'

        # The structured audit log was written once with the C7 record.
        mock_access_log.assert_called_once()
        _, kwargs = mock_access_log.call_args
        assert kwargs['operation'] == 'member_analytics_output'
        assert kwargs['details']['output_kind'] == 'csv_export'

    @patch('routes.members_analytics_audit.get_current_tenant', return_value='test-tenant')
    def test_audit_pdf_labels_pii_filter_key_is_not_logged(
        self, mock_tenant, client, export_auth
    ):
        """A PII-named filter key never reaches the audit record (R8.3)."""
        with patch(
            'services.analytics_audit.log_successful_access'
        ) as mock_access_log:
            response = client.post(
                '/api/members/analytics-audit',
                headers=export_auth,
                json={
                    'output_kind': 'pdf_labels',
                    'set_key': 'clubblad-paper',
                    'record_count': 40,
                    'filter_summary': {
                        'email': 'leak@example.com',
                        'clubblad': 'Papier',
                    },
                },
            )

        assert response.status_code == 200
        _, kwargs = mock_access_log.call_args
        details = kwargs['details']
        assert 'email' not in details['filter_summary']
        assert 'leak@example.com' not in json.dumps(details)
        assert details['filter_summary']['clubblad'] == {'present': True, 'type': 'str'}


class TestAnalyticsAuditTenantIsolation:
    """The record is scoped to the auth-resolved tenant, never a client-supplied one."""

    def test_audit_ignores_client_supplied_tenant(self, client, export_auth):
        with patch(
            'services.analytics_audit.log_successful_access'
        ) as mock_access_log:
            response = client.post(
                '/api/members/analytics-audit',
                headers=export_auth,  # X-Tenant: test-tenant
                json={
                    'tenant': 'victim-tenant',
                    'administration': 'victim-tenant',
                    'output_kind': 'csv_export',
                    'record_count': 1,
                },
            )

        assert response.status_code == 200
        _, kwargs = mock_access_log.call_args
        assert kwargs['details']['tenant'] == 'test-tenant'
