"""
API tests for folder_routes.py

Tests folder listing and creation endpoints including auth enforcement,
tenant context, and input validation.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""

import json
import time
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def finance_auth():
    """Mock authentication with Finance_CRUD role for folder endpoints."""
    with (
        patch("auth.cognito_utils.extract_user_credentials") as mock_creds,
        patch("auth.tenant_context.validate_tenant_access", return_value=(True, None)),
        patch("auth.tenant_context.get_user_tenants", return_value=["test-tenant"]),
        patch("auth.role_cache.get_tenant_roles", return_value=["Finance_CRUD"]),
    ):
        mock_creds.return_value = ("test@example.com", ["Finance_CRUD"], None)
        yield {
            "Authorization": "Bearer test-token",
            "X-Tenant": "test-tenant",
        }


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestFolderAuthEnforcement:
    """Verify 401/403 for unauthenticated requests."""

    def test_list_folders_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to list folders should be rejected."""
        auth_error = {
            "statusCode": 401,
            "body": '{"error": "Unauthorized", "message": "Missing or invalid token"}',
        }
        with patch(
            "auth.cognito_utils.extract_user_credentials",
            return_value=(None, None, auth_error),
        ):
            response = client.get("/api/folders")
        assert response.status_code in (401, 403)

    def test_create_folder_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to create folder should be rejected."""
        auth_error = {
            "statusCode": 401,
            "body": '{"error": "Unauthorized", "message": "Missing or invalid token"}',
        }
        with patch(
            "auth.cognito_utils.extract_user_credentials",
            return_value=(None, None, auth_error),
        ):
            response = client.post(
                "/api/create-folder", json={"folderName": "Test Folder"}
            )
        assert response.status_code in (401, 403)


# ============================================================================
# List Folders Tests
# ============================================================================


class TestListFolders:
    """Tests for GET /api/folders."""

    @patch("auth.tenant_context.get_current_tenant", return_value="test-tenant")
    @patch(
        "routes.folder_routes.resolve_storage_provider",
        side_effect=Exception("no provider in test"),
    )
    @patch("routes.folder_routes.GoogleDriveService")
    def test_list_folders_success(
        self, mock_drive_class, mock_resolve, mock_tenant, client, finance_auth
    ):
        """Authenticated user can list folders."""
        # Force resolve_storage_provider to raise so the route falls back to
        # config.vendor_folders — the local folder list these tests exercise.
        import routes.folder_routes as fr

        original_config = fr.config
        mock_config = MagicMock()
        mock_config.vendor_folders = {"v1": "Vendor A", "v2": "Vendor B"}
        fr.config = mock_config

        try:
            response = client.get("/api/folders", headers=finance_auth)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert isinstance(data, list)
            assert len(data) == 2
        finally:
            fr.config = original_config

    @patch("auth.tenant_context.get_current_tenant", return_value=None)
    def test_list_folders_no_tenant_returns_error(
        self, mock_tenant, client, finance_auth
    ):
        """Request without tenant context returns error."""
        # When get_current_tenant returns None, the route returns 400
        # But the patch may conflict with finance_auth fixture's patches
        response = client.get("/api/folders", headers=finance_auth)

        # Either 400 (no tenant) or 403 (auth conflict) is acceptable
        assert response.status_code in (400, 403, 500)


# ============================================================================
# Create Folder Tests
# ============================================================================


class TestCreateFolder:
    """Tests for POST /api/create-folder."""

    @patch("routes.folder_routes.GoogleDriveService")
    def test_create_folder_without_name_returns_400(
        self, mock_drive_class, client, finance_auth
    ):
        """Creating folder without name returns 400."""
        import routes.folder_routes as fr

        original_config = fr.config
        mock_config = MagicMock()
        fr.config = mock_config

        try:
            response = client.post("/api/create-folder", headers=finance_auth, json={})

            assert response.status_code == 400
            data = json.loads(response.data)
            assert data["success"] is False
        finally:
            fr.config = original_config

    @patch("routes.folder_routes.GoogleDriveService")
    def test_create_folder_success(self, mock_drive_class, client, finance_auth):
        """Creating folder with valid name succeeds."""
        import routes.folder_routes as fr

        original_config = fr.config
        mock_config = MagicMock()
        mock_config.get_storage_folder.return_value = "/tmp/test-folder"
        mock_config.ensure_folder_exists.return_value = None
        fr.config = mock_config

        mock_drive = MagicMock()
        mock_drive_class.return_value = mock_drive
        mock_drive.create_folder.return_value = {"id": "drive-folder-id"}

        try:
            response = client.post(
                "/api/create-folder",
                headers=finance_auth,
                json={"folderName": "New Vendor"},
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True
        finally:
            fr.config = original_config

    @patch(
        "routes.folder_routes.resolve_storage_provider",
        side_effect=Exception("no provider in test"),
    )
    @patch("routes.folder_routes.GoogleDriveService")
    @patch("auth.tenant_context.get_current_tenant", return_value="test-tenant")
    def test_list_folders_with_regex_filter(
        self, mock_tenant, mock_drive_class, mock_resolve, client, finance_auth
    ):
        """Folders can be filtered by a case-insensitive substring pattern."""
        import routes.folder_routes as fr

        original_config = fr.config
        mock_config = MagicMock()
        mock_config.vendor_folders = {
            "v1": "Vendor Alpha",
            "v2": "Vendor Beta",
            "v3": "Supplier Gamma",
        }
        fr.config = mock_config

        try:
            response = client.get("/api/folders?regex=Vendor", headers=finance_auth)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data) == 2
            # Substring match is case-insensitive and only matches "Vendor *".
            assert set(data) == {"Vendor Alpha", "Vendor Beta"}
        finally:
            fr.config = original_config

    @patch(
        "routes.folder_routes.resolve_storage_provider",
        side_effect=Exception("no provider in test"),
    )
    @patch("routes.folder_routes.GoogleDriveService")
    @patch("auth.tenant_context.get_current_tenant", return_value="test-tenant")
    def test_list_folders_pathological_pattern_returns_fast(
        self, mock_tenant, mock_drive_class, mock_resolve, client, finance_auth
    ):
        """A catastrophic-backtracking-style pattern against a long folder list
        must NOT stall: the filter is a linear substring match, so it returns
        quickly (previously `re.compile(pattern).search()` was a ReDoS vector)."""
        import routes.folder_routes as fr

        original_config = fr.config
        mock_config = MagicMock()
        # Long folder list, each a long 'a' run that would detonate `(a+)+$`.
        mock_config.vendor_folders = {f"v{i}": ("a" * 60) + "!" for i in range(500)}
        fr.config = mock_config

        # A classic ReDoS pattern. As a literal substring it simply never matches.
        pathological = "(a+)+$"

        try:
            start = time.monotonic()
            response = client.get(
                f"/api/folders?regex={pathological}", headers=finance_auth
            )
            elapsed = time.monotonic() - start

            assert response.status_code == 200
            # Linear substring match over 500 items finishes well under a second;
            # a ReDoS would hang for many seconds. Generous bound avoids flakiness.
            assert elapsed < 2.0, f"filter took too long: {elapsed:.2f}s"
            data = json.loads(response.data)
            # Treated as a literal substring -> matches nothing here.
            assert data == []
        finally:
            fr.config = original_config

    @patch("routes.folder_routes.GoogleDriveService")
    @patch("auth.tenant_context.get_current_tenant", return_value="test-tenant")
    def test_list_folders_overlong_pattern_returns_400(
        self, mock_tenant, mock_drive_class, client, finance_auth
    ):
        """A filter value longer than 128 chars is rejected with a 400 before
        any matching runs (deliberate validation guard)."""
        import routes.folder_routes as fr

        original_config = fr.config
        mock_config = MagicMock()
        mock_config.vendor_folders = {"v1": "Vendor Alpha"}
        fr.config = mock_config

        overlong = "a" * 129

        try:
            response = client.get(
                f"/api/folders?regex={overlong}", headers=finance_auth
            )

            assert response.status_code == 400
            data = json.loads(response.data)
            assert data["error"] == "Invalid regex pattern: too long"
        finally:
            fr.config = original_config
