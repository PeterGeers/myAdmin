"""
API tests for storage.py

Tests storage endpoints including presigned URL generation and logo upload,
covering auth enforcement, tenant isolation, S3 configuration, and validation.

Requirements: 7.1–7.7, 9.1–9.3
Reference: .kiro/specs/code-quality-fixes-2026-06/tasks.md
"""
import io
import json
import pytest
from unittest.mock import patch, MagicMock


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


@pytest.mark.api
class TestStorageAuthEnforcement:
    """Verify 401/403 for unauthenticated requests."""

    def test_presigned_url_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to presigned URL should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            response = client.get('/api/storage/presigned-url?key=test-tenant/doc.pdf')
        assert response.status_code in (401, 403)

    def test_upload_logo_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to upload logo should be rejected."""
        auth_error = {
            'statusCode': 401,
            'body': '{"error": "Unauthorized", "message": "Missing or invalid token"}'
        }
        with patch('auth.cognito_utils.extract_user_credentials',
                   return_value=(None, None, auth_error)):
            data = {'file': (io.BytesIO(b'fake'), 'logo.png')}
            response = client.post(
                '/api/storage/upload-logo',
                content_type='multipart/form-data',
                data=data,
            )
        assert response.status_code in (401, 403)


# ============================================================================
# Presigned URL Tests
# ============================================================================


@pytest.mark.api
class TestPresignedUrl:
    """Tests for GET /api/storage/presigned-url."""

    def test_cross_tenant_key_returns_403(self, client, mock_auth):
        """Key not starting with tenant prefix returns 403."""
        response = client.get(
            '/api/storage/presigned-url?key=other-tenant/secret.pdf',
            headers=mock_auth,
        )
        assert response.status_code == 403
        data = json.loads(response.data)
        assert data['error'] == 'Access denied'

    def test_empty_key_returns_403(self, client, mock_auth):
        """Empty key returns 403 (doesn't start with tenant prefix)."""
        response = client.get(
            '/api/storage/presigned-url?key=',
            headers=mock_auth,
        )
        assert response.status_code == 403

    def test_missing_key_param_returns_403(self, client, mock_auth):
        """Missing key query param defaults to empty string, returns 403."""
        response = client.get(
            '/api/storage/presigned-url',
            headers=mock_auth,
        )
        assert response.status_code == 403

    @patch.dict('os.environ', {'S3_SHARED_BUCKET': ''}, clear=False)
    def test_s3_not_configured_returns_503(self, client, mock_auth):
        """Returns 503 when S3_SHARED_BUCKET is not set."""
        with patch('os.getenv', side_effect=lambda k, d='': '' if k == 'S3_SHARED_BUCKET' else d):
            response = client.get(
                '/api/storage/presigned-url?key=test-tenant/doc.pdf',
                headers=mock_auth,
            )
        assert response.status_code == 503
        data = json.loads(response.data)
        assert 'not configured' in data['error']

    @patch('boto3.client')
    def test_presigned_url_success(self, mock_boto_client, client, mock_auth):
        """Happy path: returns presigned URL with 300s expiry."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = 'https://s3.example.com/signed'

        with patch('os.getenv', side_effect=lambda k, d='': 'my-bucket' if k == 'S3_SHARED_BUCKET' else d):
            response = client.get(
                '/api/storage/presigned-url?key=test-tenant/invoices/doc.pdf',
                headers=mock_auth,
            )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['url'] == 'https://s3.example.com/signed'
        assert data['expires_in'] == 300

    @patch('boto3.client')
    def test_presigned_url_calls_s3_with_correct_params(self, mock_boto_client, client, mock_auth):
        """Verifies S3 is called with correct bucket, key, and content params."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = 'https://signed.url'

        with patch('os.getenv', side_effect=lambda k, d='': 'test-bucket' if k == 'S3_SHARED_BUCKET' else d):
            client.get(
                '/api/storage/presigned-url?key=test-tenant/report.pdf',
                headers=mock_auth,
            )

        mock_s3.generate_presigned_url.assert_called_once()
        call_args = mock_s3.generate_presigned_url.call_args
        assert call_args[0][0] == 'get_object'
        params = call_args[1]['Params'] if 'Params' in call_args[1] else call_args[0][1]
        assert params['Bucket'] == 'test-bucket'
        assert params['Key'] == 'test-tenant/report.pdf'


# ============================================================================
# Upload Logo Tests
# ============================================================================


@pytest.mark.api
class TestUploadLogo:
    """Tests for POST /api/storage/upload-logo."""

    def test_no_file_returns_400(self, client, mock_auth):
        """Request without file part returns 400."""
        response = client.post(
            '/api/storage/upload-logo',
            headers=mock_auth,
            content_type='multipart/form-data',
            data={},
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'No file' in data['error']

    def test_empty_filename_returns_400(self, client, mock_auth):
        """File with empty filename returns 400."""
        data = {'file': (io.BytesIO(b'content'), '')}
        response = client.post(
            '/api/storage/upload-logo',
            headers=mock_auth,
            content_type='multipart/form-data',
            data=data,
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'No file' in data['error'] or 'selected' in data['error']

    def test_invalid_mime_type_returns_400(self, client, mock_auth):
        """Non-image MIME type returns 400."""
        data = {
            'file': (io.BytesIO(b'not an image'), 'file.txt'),
        }
        response = client.post(
            '/api/storage/upload-logo',
            headers={**mock_auth, 'Content-Type': 'multipart/form-data'},
            data=data,
        )
        assert response.status_code == 400
        resp_data = json.loads(response.data)
        assert 'Invalid file type' in resp_data['error']

    def test_file_too_large_returns_400(self, client, mock_auth):
        """File exceeding 2MB returns 400."""
        large_content = b'x' * (2 * 1024 * 1024 + 1)  # Just over 2MB
        data = {
            'file': (io.BytesIO(large_content), 'logo.png'),
        }
        response = client.post(
            '/api/storage/upload-logo',
            headers=mock_auth,
            content_type='multipart/form-data',
            data=data,
        )
        assert response.status_code == 400
        resp_data = json.loads(response.data)
        assert 'too large' in resp_data['error'] or 'Maximum' in resp_data['error']

    @patch('boto3.client')
    @patch('services.parameter_service.ParameterService')
    @patch('database.DatabaseManager')
    def test_s3_not_configured_returns_503(self, mock_db, mock_ps, mock_boto,
                                           client, mock_auth):
        """Returns 503 when S3_SHARED_BUCKET not configured."""
        png_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100  # Minimal PNG-like data
        data = {
            'file': (io.BytesIO(png_data), 'logo.png'),
        }
        with patch('os.getenv', side_effect=lambda k, d='': '' if k == 'S3_SHARED_BUCKET' else d):
            response = client.post(
                '/api/storage/upload-logo',
                headers=mock_auth,
                content_type='multipart/form-data',
                data=data,
            )
        assert response.status_code == 503
        resp_data = json.loads(response.data)
        assert 'not configured' in resp_data['error']

    @patch('routes.storage.ParameterService')
    @patch('routes.storage.DatabaseManager')
    @patch('boto3.client')
    def test_upload_logo_png_success(self, mock_boto_client, mock_db_class,
                                     mock_ps_class, client, mock_auth):
        """Happy path: PNG upload succeeds and returns S3 key."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_db_class.return_value = MagicMock()
        mock_ps_instance = MagicMock()
        mock_ps_class.return_value = mock_ps_instance

        png_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        data = {
            'file': (io.BytesIO(png_data), 'logo.png'),
        }

        with patch('os.getenv', side_effect=lambda k, d='': {
            'S3_SHARED_BUCKET': 'my-bucket',
            'TEST_MODE': 'true',
        }.get(k, d)):
            response = client.post(
                '/api/storage/upload-logo',
                headers=mock_auth,
                content_type='multipart/form-data',
                data=data,
            )

        assert response.status_code == 200
        resp_data = json.loads(response.data)
        assert resp_data['success'] is True
        assert resp_data['key'] == 'test-tenant/branding/company_logo.png'

    @patch('routes.storage.ParameterService')
    @patch('routes.storage.DatabaseManager')
    @patch('boto3.client')
    def test_upload_logo_jpg_success(self, mock_boto_client, mock_db_class,
                                     mock_ps_class, client, mock_auth):
        """JPEG upload uses .jpg extension."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_db_class.return_value = MagicMock()
        mock_ps_class.return_value = MagicMock()

        jpg_data = b'\xff\xd8\xff\xe0' + b'\x00' * 100
        data = {
            'file': (io.BytesIO(jpg_data), 'photo.jpg'),
        }

        with patch('os.getenv', side_effect=lambda k, d='': {
            'S3_SHARED_BUCKET': 'my-bucket',
            'TEST_MODE': 'true',
        }.get(k, d)):
            response = client.post(
                '/api/storage/upload-logo',
                headers=mock_auth,
                content_type='multipart/form-data',
                data=data,
            )

        assert response.status_code == 200
        resp_data = json.loads(response.data)
        assert resp_data['key'] == 'test-tenant/branding/company_logo.jpg'

    @patch('routes.storage.ParameterService')
    @patch('routes.storage.DatabaseManager')
    @patch('boto3.client')
    def test_upload_logo_calls_s3_put_object(self, mock_boto_client,
                                             mock_db_class, mock_ps_class,
                                             client, mock_auth):
        """Verifies S3 put_object is called with correct params."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_db_class.return_value = MagicMock()
        mock_ps_class.return_value = MagicMock()

        png_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 50
        data = {
            'file': (io.BytesIO(png_data), 'logo.png'),
        }

        with patch('os.getenv', side_effect=lambda k, d='': {
            'S3_SHARED_BUCKET': 'test-bucket',
            'TEST_MODE': 'true',
        }.get(k, d)):
            client.post(
                '/api/storage/upload-logo',
                headers=mock_auth,
                content_type='multipart/form-data',
                data=data,
            )

        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs['Bucket'] == 'test-bucket'
        assert call_kwargs['Key'] == 'test-tenant/branding/company_logo.png'
        assert call_kwargs['ContentType'] == 'image/png'

    @patch('routes.storage.ParameterService')
    @patch('routes.storage.DatabaseManager')
    @patch('boto3.client')
    def test_upload_logo_updates_parameter_service(self, mock_boto_client,
                                                    mock_db_class,
                                                    mock_ps_class,
                                                    client, mock_auth):
        """Verifies ParameterService is called to store the S3 key."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_db_class.return_value = MagicMock()
        mock_ps_instance = MagicMock()
        mock_ps_class.return_value = mock_ps_instance

        png_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 50
        data = {
            'file': (io.BytesIO(png_data), 'logo.png'),
        }

        with patch('os.getenv', side_effect=lambda k, d='': {
            'S3_SHARED_BUCKET': 'my-bucket',
            'TEST_MODE': 'true',
        }.get(k, d)):
            client.post(
                '/api/storage/upload-logo',
                headers=mock_auth,
                content_type='multipart/form-data',
                data=data,
            )

        mock_ps_instance.set_param.assert_called_once_with(
            'tenant', 'test-tenant', 'branding', 'company_logo_s3_key',
            'test-tenant/branding/company_logo.png',
            value_type='string', created_by='test@example.com'
        )
