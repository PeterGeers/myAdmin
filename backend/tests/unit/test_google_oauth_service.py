"""Unit tests for google_oauth_service (auth).

Covers the two public helpers:
- ``test_google_drive_connectivity`` — the credential-shape dispatch, with a strong
  emphasis on the rejection branches (client-secrets file, missing refresh_token,
  missing client id/secret, unknown shape, non-dict, refresh failure) rather than
  only the happy path.
- ``exchange_google_code_for_tokens`` — success mapping plus the non-200 / exception
  failure branches.

The google client libraries are imported lazily inside the functions, so we patch
the real import targets (``build`` / ``Credentials`` / ``service_account``) and
``requests.post`` at their source modules.
"""

from unittest.mock import MagicMock, patch

import pytest

from services import google_oauth_service as svc


# ---------------------------------------------------------------------------
# test_google_drive_connectivity
# ---------------------------------------------------------------------------

class TestGoogleDriveConnectivity:
    def test_non_dict_credentials_rejected(self):
        result = svc.test_google_drive_connectivity("not-a-dict")
        assert result["success"] is False
        assert result["accessible"] is False
        assert "not a dictionary" in result["message"].lower()

    def test_client_secrets_file_rejected(self):
        """An 'installed'/'web' client-secrets file is not usable tokens."""
        result = svc.test_google_drive_connectivity({"installed": {"client_id": "x"}})
        assert result["success"] is False
        assert "client secrets file" in result["message"].lower()

    def test_oauth_token_missing_refresh_token_rejected(self):
        creds = {"token": "abc"}  # no refresh_token
        result = svc.test_google_drive_connectivity(creds, client_id="c", client_secret="s")
        assert result["success"] is False
        assert "refresh_token" in result["message"]

    def test_oauth_token_missing_client_credentials_rejected(self):
        creds = {"token": "abc", "refresh_token": "r"}
        result = svc.test_google_drive_connectivity(creds, client_id=None, client_secret=None)
        assert result["success"] is False
        assert "client_id" in result["message"] or "client_secret" in result["message"]

    def test_unknown_credential_shape_rejected(self):
        result = svc.test_google_drive_connectivity({"something_else": 1})
        assert result["success"] is False
        assert "unknown credential format" in result["message"].lower()

    def test_service_account_happy_path(self):
        """A service_account credential builds a Drive client and lists files."""
        creds = {"type": "service_account", "client_email": "svc@x.iam"}
        fake_service = MagicMock()
        fake_service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "1", "name": "f"}]
        }
        with patch(
            "google.oauth2.service_account.Credentials.from_service_account_info",
            return_value=MagicMock(),
        ), patch("googleapiclient.discovery.build", return_value=fake_service):
            result = svc.test_google_drive_connectivity(creds)

        assert result["success"] is True
        assert result["accessible"] is True

    def test_oauth_token_happy_path_not_expired(self):
        """A valid, non-expired OAuth token lists files successfully."""
        creds = {"token": "abc", "refresh_token": "r"}
        fake_creds = MagicMock()
        fake_creds.expired = False
        fake_service = MagicMock()
        fake_service.files.return_value.list.return_value.execute.return_value = {"files": []}
        with patch(
            "google.oauth2.credentials.Credentials.from_authorized_user_info",
            return_value=fake_creds,
        ), patch("googleapiclient.discovery.build", return_value=fake_service):
            result = svc.test_google_drive_connectivity(creds, client_id="c", client_secret="s")

        assert result["success"] is True
        assert result["accessible"] is True

    def test_oauth_token_refresh_failure_rejected(self):
        """When the token is expired and refresh raises, we fail closed."""
        creds = {"token": "abc", "refresh_token": "r"}
        fake_creds = MagicMock()
        fake_creds.expired = True
        fake_creds.refresh_token = "r"
        fake_creds.refresh.side_effect = RuntimeError("refresh boom")
        with patch(
            "google.oauth2.credentials.Credentials.from_authorized_user_info",
            return_value=fake_creds,
        ), patch("google.auth.transport.requests.Request", return_value=MagicMock()):
            result = svc.test_google_drive_connectivity(creds, client_id="c", client_secret="s")

        assert result["success"] is False
        assert "refresh failed" in result["message"].lower()

    def test_refreshed_token_is_persisted(self):
        """A successful refresh persists the new token via credential_service."""
        creds = {"token": "old", "refresh_token": "r"}
        fake_creds = MagicMock()
        fake_creds.expired = True
        fake_creds.refresh_token = "r"
        fake_creds.refresh.return_value = None
        fake_creds.token = "new"
        fake_creds.token_uri = "https://oauth2.googleapis.com/token"
        fake_creds.client_id = "c"
        fake_creds.client_secret = "s"
        fake_creds.scopes = ["https://www.googleapis.com/auth/drive"]
        fake_creds.expiry = None
        fake_service = MagicMock()
        fake_service.files.return_value.list.return_value.execute.return_value = {"files": []}
        cred_service = MagicMock()

        with patch(
            "google.oauth2.credentials.Credentials.from_authorized_user_info",
            return_value=fake_creds,
        ), patch("google.auth.transport.requests.Request", return_value=MagicMock()), patch(
            "googleapiclient.discovery.build", return_value=fake_service
        ):
            result = svc.test_google_drive_connectivity(
                creds,
                client_id="c",
                client_secret="s",
                tenant="TenantA",
                credential_service=cred_service,
            )

        assert result["success"] is True
        cred_service.store_credential.assert_called_once()
        args = cred_service.store_credential.call_args[0]
        assert args[0] == "TenantA"
        assert args[1] == "google_drive_token"

    def test_build_failure_maps_to_connection_failed(self):
        """An unexpected error during build is caught and reported as failure."""
        creds = {"type": "service_account"}
        with patch(
            "google.oauth2.service_account.Credentials.from_service_account_info",
            side_effect=RuntimeError("bad key"),
        ):
            result = svc.test_google_drive_connectivity(creds)

        assert result["success"] is False
        assert "connection failed" in result["message"].lower()


# ---------------------------------------------------------------------------
# exchange_google_code_for_tokens
# ---------------------------------------------------------------------------

class TestExchangeGoogleCodeForTokens:
    def test_success_builds_complete_token(self):
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
        }
        with patch("requests.post", return_value=fake_response):
            token = svc.exchange_google_code_for_tokens("code123", "cid", "csecret")

        assert token is not None
        assert token["token"] == "at"
        assert token["refresh_token"] == "rt"
        assert token["client_id"] == "cid"
        assert token["token_uri"] == "https://oauth2.googleapis.com/token"
        assert token["expiry"].endswith("Z")
        assert token["scopes"] == ["https://www.googleapis.com/auth/drive"]

    def test_non_200_returns_none(self):
        fake_response = MagicMock()
        fake_response.status_code = 400
        fake_response.text = "invalid_grant"
        with patch("requests.post", return_value=fake_response):
            token = svc.exchange_google_code_for_tokens("bad", "cid", "csecret")

        assert token is None

    def test_request_exception_returns_none(self):
        with patch("requests.post", side_effect=RuntimeError("network down")):
            token = svc.exchange_google_code_for_tokens("code", "cid", "csecret")

        assert token is None

    def test_default_expires_in_when_missing(self):
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"access_token": "at", "refresh_token": "rt"}
        with patch("requests.post", return_value=fake_response):
            token = svc.exchange_google_code_for_tokens("code", "cid", "csecret")

        assert token is not None
        assert token["expiry"].endswith("Z")
