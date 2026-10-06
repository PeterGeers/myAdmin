"""
API tests for members_mail.py (member-analytics task 9.1, Design C6)

Covers the POST /api/members/mail-set route:
  - happy path: delegates to SESEmailService.send_email_with_attachments with the
    right args (BCC recipients, tenant from auth, attachment bytes decoded)
  - capability denied: a caller without members:export is rejected (403)
  - tenant isolation: the send is scoped to the AUTH-resolved tenant; a
    client-supplied tenant in the body is ignored
  - no-recipients: empty / unresolvable recipient set is rejected (400)
  - SES rate limit: a throttling error maps to a DISTINCT 429 + code
    'rate_limited', while a generic SES failure stays a 502 (task 9.3)
  - transient-artifact cleanup: the decoded CSV/PDF bytes are released after the
    send completes, success OR failure (task 9.3, R8.5)

Mirrors tests/api/test_tenant_admin_email.py.

Validates: Requirements R4.12, R8.5
"""
import base64
import json
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def export_auth():
    """Auth with a Members role that grants the members:export capability.

    The route is gated via cognito_required(required_permissions=['members:export']),
    which expands the caller's tenant roles through ROLE_PERMISSIONS. Members_Export
    grants members:read + members:export.
    """
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
    """Auth with a role that does NOT grant members:export (read-only)."""
    with patch('auth.cognito_utils.extract_user_credentials') as mock_creds, \
         patch('auth.tenant_context.validate_tenant_access', return_value=(True, None)), \
         patch('auth.tenant_context.get_user_tenants', return_value=['test-tenant']), \
         patch('auth.role_cache.get_tenant_roles', return_value=['Members_Read']):
        mock_creds.return_value = ('reader@example.com', ['Members_Read'], None)
        yield {
            'Authorization': 'Bearer test-token',
            'X-Tenant': 'test-tenant',
        }


def _mock_ses(success=True, error=None):
    """Build a mock SESEmailService.

    - success=True  -> a successful send result.
    - success=False -> a failure result; ``error`` sets the error string so a
      test can exercise either a generic failure or an SES throttle (task 9.3).
    """
    mock_ses = MagicMock()
    if success:
        mock_ses.send_email_with_attachments.return_value = {
            'success': True, 'message_id': 'msg-123'
        }
    else:
        mock_ses.send_email_with_attachments.return_value = {
            'success': False,
            'error': error or 'MessageRejected: Email address is not verified',
        }
    mock_ses.sender = 'support@jabaki.nl'
    return mock_ses


class TestMailSetCapabilityGate:
    """members:export capability enforcement (R4.12)."""

    def test_mail_set_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request is rejected before reaching the handler."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.post(
                '/api/members/mail-set',
                json={'recipients': ['a@example.com'], 'subject': 's', 'body': 'b'}
            )
        assert response.status_code in (401, 403)

    def test_mail_set_without_export_capability_returns_403(
        self, client, no_export_auth
    ):
        """A members:read-only caller cannot mail a set."""
        response = client.post(
            '/api/members/mail-set',
            headers=no_export_auth,
            json={'recipients': ['a@example.com'], 'subject': 's', 'body': 'b'}
        )
        assert response.status_code == 403


class TestMailSetValidation:
    """Request validation + no-recipients handling."""

    @patch('routes.members_mail.get_current_tenant', return_value='test-tenant')
    def test_mail_set_no_data_returns_400(self, mock_tenant, client, export_auth):
        response = client.post(
            '/api/members/mail-set', headers=export_auth, json={}
        )
        assert response.status_code == 400

    @patch('routes.members_mail.get_current_tenant', return_value='test-tenant')
    def test_mail_set_missing_subject_returns_400(
        self, mock_tenant, client, export_auth
    ):
        response = client.post(
            '/api/members/mail-set',
            headers=export_auth,
            json={'recipients': ['a@example.com'], 'body': 'b'}
        )
        assert response.status_code == 400
        assert 'subject' in json.loads(response.data)['error'].lower()

    @patch('routes.members_mail.get_current_tenant', return_value='test-tenant')
    def test_mail_set_empty_recipients_returns_400(
        self, mock_tenant, client, export_auth
    ):
        response = client.post(
            '/api/members/mail-set',
            headers=export_auth,
            json={'recipients': [], 'subject': 's', 'body': 'b'}
        )
        assert response.status_code == 400
        assert 'recipient' in json.loads(response.data)['error'].lower()

    @patch('routes.members_mail.get_current_tenant', return_value='test-tenant')
    def test_mail_set_unresolvable_emails_returns_400(
        self, mock_tenant, client, export_auth
    ):
        """Rows with no email key resolve to zero recipients -> 400."""
        response = client.post(
            '/api/members/mail-set',
            headers=export_auth,
            json={
                'recipients': [{'id': '1', 'name': 'No Email'}],
                'subject': 's',
                'body': 'b',
            }
        )
        assert response.status_code == 400
        assert 'email' in json.loads(response.data)['error'].lower()


class TestMailSetHappyPath:
    """Successful delegation to SES with the right args."""

    @patch('routes.members_mail.get_current_tenant', return_value='test-tenant')
    def test_mail_set_delegates_to_ses_with_right_args(
        self, mock_tenant, client, export_auth
    ):
        csv_bytes = b'name,email\nAlice,alice@example.com\n'
        attachment_b64 = base64.b64encode(csv_bytes).decode()

        # Snapshot the attachments AT CALL TIME. The route releases the decoded
        # bytes after the send (R8.5, task 9.3) by emptying the very list it hands
        # to SES, so inspecting `call_args` after the request would see the cleared
        # list; capture a copy inside the side_effect instead.
        sent_attachments = {}

        def _capture_send(*args, **kwargs):
            atts = kwargs['attachments']
            sent_attachments['snapshot'] = [dict(a) for a in atts]
            return {'success': True, 'message_id': 'msg-123'}

        mock_ses = MagicMock()
        mock_ses.sender = 'support@jabaki.nl'
        mock_ses.send_email_with_attachments.side_effect = _capture_send

        import services.ses_email_service
        with patch.object(services.ses_email_service, 'SESEmailService',
                          return_value=mock_ses), \
             patch('services.analytics_audit.log_successful_access') as mock_audit:
            response = client.post(
                '/api/members/mail-set',
                headers=export_auth,
                json={
                    'recipients': [
                        {'id': '1', 'email': 'Alice@Example.com'},
                        {'id': '2', 'email': 'bob@example.com'},
                    ],
                    'subject': 'Hello members',
                    'body': '<p>Newsletter</p>',
                    'attachments': [
                        {'kind': 'csv', 'content_base64': attachment_b64,
                         'filename': 'members.csv'},
                    ],
                    'set_key': 'members-per-type',
                    'filter_summary': {'membership_type': 'gold'},
                }
            )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['recipient_count'] == 2

        mock_ses.send_email_with_attachments.assert_called_once()
        _, kwargs = mock_ses.send_email_with_attachments.call_args
        # Recipients are BCC'd (R8.4), de-duplicated and lowercased.
        assert kwargs['bcc'] == ['alice@example.com', 'bob@example.com']
        # Visible envelope recipient is the SES sender, not a member.
        assert kwargs['to_email'] == mock_ses.sender
        assert kwargs['subject'] == 'Hello members'
        assert kwargs['html_body'] == '<p>Newsletter</p>'
        # Tenant comes from the auth context.
        assert kwargs['administration'] == 'test-tenant'
        assert kwargs['sent_by'] == 'exporter@example.com'
        # Attachment bytes decoded and forwarded (captured at send time, before
        # the route releases them per R8.5).
        snapshot = sent_attachments['snapshot']
        assert len(snapshot) == 1
        att = snapshot[0]
        assert att['filename'] == 'members.csv'
        assert att['content'] == csv_bytes
        assert att['content_type'] == 'text/csv'

        # The send is audit-logged (C7 / R8.1): metadata only — output kind, set,
        # recipient count, PII-free filter summary. NO member PII in the record.
        mock_audit.assert_called_once()
        _, audit_kwargs = mock_audit.call_args
        assert audit_kwargs['operation'] == 'member_analytics_output'
        audit = audit_kwargs['details']
        assert audit['output_kind'] == 'ses_mail'
        assert audit['set_key'] == 'members-per-type'
        assert audit['record_count'] == 2
        assert audit['tenant'] == 'test-tenant'
        assert audit['actor'] == 'exporter@example.com'
        # Filter summary is PII-sanitized (shape only, never values).
        assert audit['filter_summary']['membership_type'] == {
            'present': True, 'type': 'str'
        }

    @patch('routes.members_mail.get_current_tenant', return_value='test-tenant')
    def test_mail_set_ses_error_returns_502(
        self, mock_tenant, client, export_auth
    ):
        mock_ses = _mock_ses(success=False)
        import services.ses_email_service
        with patch.object(services.ses_email_service, 'SESEmailService',
                          return_value=mock_ses):
            response = client.post(
                '/api/members/mail-set',
                headers=export_auth,
                json={
                    'recipients': ['alice@example.com'],
                    'subject': 's',
                    'body': 'b',
                }
            )
        assert response.status_code == 502
        assert 'message' in json.loads(response.data)
        # A generic (non-throttle) failure is NOT flagged as a rate limit.
        assert json.loads(response.data).get('code') != 'rate_limited'


class TestMailSetRateLimit:
    """SES rate-limit / throttling maps to a DISTINCT 429 response (R4.12, ODI-4)."""

    @pytest.mark.parametrize(
        'ses_error',
        [
            'Throttling: Maximum sending rate exceeded',
            'ThrottlingException: Rate exceeded',
            'Throttling: Maximum Throughput exceeded',
            'TooManyRequests: Maximum sending rate exceeded',
        ],
    )
    @patch('routes.members_mail.get_current_tenant', return_value='test-tenant')
    def test_mail_set_ses_throttle_returns_429_with_code(
        self, mock_tenant, ses_error, client, export_auth
    ):
        """A throttling error maps to 429 + code='rate_limited', not the 502 path."""
        mock_ses = _mock_ses(success=False, error=ses_error)
        import services.ses_email_service
        with patch.object(services.ses_email_service, 'SESEmailService',
                          return_value=mock_ses):
            response = client.post(
                '/api/members/mail-set',
                headers=export_auth,
                json={
                    'recipients': ['alice@example.com'],
                    'subject': 's',
                    'body': 'b',
                }
            )
        assert response.status_code == 429
        data = json.loads(response.data)
        # Machine-readable code the client branches on for the dedicated message.
        assert data['code'] == 'rate_limited'
        assert 'message' in data

    @patch('routes.members_mail.get_current_tenant', return_value='test-tenant')
    def test_mail_set_generic_failure_is_not_rate_limited(
        self, mock_tenant, client, export_auth
    ):
        """A non-throttle SES failure stays a generic 502 (regression guard)."""
        mock_ses = _mock_ses(
            success=False, error='MessageRejected: Email address is not verified'
        )
        import services.ses_email_service
        with patch.object(services.ses_email_service, 'SESEmailService',
                          return_value=mock_ses):
            response = client.post(
                '/api/members/mail-set',
                headers=export_auth,
                json={
                    'recipients': ['alice@example.com'],
                    'subject': 's',
                    'body': 'b',
                }
            )
        assert response.status_code == 502
        assert json.loads(response.data).get('code') != 'rate_limited'


class TestMailSetArtifactCleanup:
    """Transient attachment bytes are released after the send (R8.5)."""

    @pytest.mark.parametrize('send_succeeds', [True, False])
    @patch('routes.members_mail.get_current_tenant', return_value='test-tenant')
    def test_mail_set_releases_attachment_bytes_after_send(
        self, mock_tenant, send_succeeds, client, export_auth
    ):
        """The decoded CSV/PDF bytes forwarded to SES are cleared post-send.

        The route holds the decoded attachment content only to forward it to SES;
        afterwards it must drop that content (success OR failure) so member data
        is not retained in process memory. We capture the exact attachment list
        object the route hands to SES and assert the route emptied it once the
        send returned.
        """
        csv_bytes = b'name,email\nAlice,alice@example.com\n'
        attachment_b64 = base64.b64encode(csv_bytes).decode()

        captured = {}

        def _capture(*args, **kwargs):
            # Snapshot the content the route decoded + the list it passed, so we
            # can assert the route released them afterwards.
            attachments = kwargs['attachments']
            captured['list'] = attachments
            captured['had_content'] = bool(attachments) and all(
                att.get('content') for att in attachments
            )
            if send_succeeds:
                return {'success': True, 'message_id': 'msg-123'}
            return {'success': False, 'error': 'MessageRejected: not verified'}

        mock_ses = MagicMock()
        mock_ses.sender = 'support@jabaki.nl'
        mock_ses.send_email_with_attachments.side_effect = _capture

        import services.ses_email_service
        with patch.object(services.ses_email_service, 'SESEmailService',
                          return_value=mock_ses):
            client.post(
                '/api/members/mail-set',
                headers=export_auth,
                json={
                    'recipients': ['alice@example.com'],
                    'subject': 's',
                    'body': 'b',
                    'attachments': [
                        {'kind': 'csv', 'content_base64': attachment_b64,
                         'filename': 'members.csv'},
                    ],
                }
            )

        # SES genuinely received the decoded bytes during the send...
        assert captured['had_content'] is True
        # ...but the route released them afterwards: the list is emptied and no
        # descriptor still carries the decoded content.
        assert captured['list'] == []


class TestMailSetTenantIsolation:
    """The send is scoped to the auth-resolved tenant, never a client-supplied one."""

    def test_mail_set_ignores_client_supplied_tenant(self, client, export_auth):
        """A 'tenant' field in the body must NOT override the auth tenant.

        get_current_tenant resolves from the X-Tenant header / verified token; the
        route passes that to SES as 'administration'. A body-supplied tenant is
        ignored entirely.
        """
        mock_ses = _mock_ses(success=True)
        import services.ses_email_service
        with patch.object(services.ses_email_service, 'SESEmailService',
                          return_value=mock_ses):
            response = client.post(
                '/api/members/mail-set',
                headers=export_auth,  # X-Tenant: test-tenant
                json={
                    'tenant': 'victim-tenant',
                    'administration': 'victim-tenant',
                    'recipients': ['alice@example.com'],
                    'subject': 's',
                    'body': 'b',
                }
            )

        assert response.status_code == 200
        _, kwargs = mock_ses.send_email_with_attachments.call_args
        assert kwargs['administration'] == 'test-tenant'
