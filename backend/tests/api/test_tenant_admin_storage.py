"""
API tests for tenant_admin_storage.py

Tests storage configuration, folder listing, and usage endpoints,
including authentication enforcement and input validation.

Requirements: 6.1, 6.2, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""

import pytest
import json
from unittest.mock import patch, MagicMock

from db_exceptions import DatabaseError


@pytest.fixture
def tenant_admin_auth():
    """
    Mock authentication with Tenant_Admin role for tenant admin endpoints.
    """
    with (
        patch("auth.cognito_utils.extract_user_credentials") as mock_creds,
        patch("auth.tenant_context.validate_tenant_access", return_value=(True, None)),
        patch("auth.tenant_context.get_user_tenants", return_value=["test-tenant"]),
        patch("auth.role_cache.get_tenant_roles", return_value=["Tenant_Admin"]),
    ):
        mock_creds.return_value = ("admin@example.com", ["Tenant_Admin"], None)
        yield {
            "Authorization": "Bearer test-token",
            "X-Tenant": "test-tenant",
        }


# ============================================================================
# Authentication Enforcement Tests
# ============================================================================


class TestTenantAdminStorageAuthEnforcement:
    """Verify 401/403 for unauthenticated/unauthorized requests."""

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
            response = client.get("/api/tenant-admin/storage/folders")
        assert response.status_code in (401, 403)

    def test_get_storage_config_unauthenticated_returns_401_or_403(self, client):
        """Unauthenticated request to get storage config should be rejected."""
        auth_error = {
            "statusCode": 401,
            "body": '{"error": "Unauthorized", "message": "Missing or invalid token"}',
        }
        with patch(
            "auth.cognito_utils.extract_user_credentials",
            return_value=(None, None, auth_error),
        ):
            response = client.get("/api/tenant-admin/storage/config")
        assert response.status_code in (401, 403)


# ============================================================================
# List Folders Tests
# ============================================================================


class TestTenantAdminStorageFolders:
    """Tests for GET /api/tenant-admin/storage/folders."""

    @patch("routes.tenant_admin_storage.get_current_tenant", return_value="test-tenant")
    @patch("routes.tenant_admin_storage.GoogleDriveService")
    def test_list_folders_returns_data(
        self, mock_drive_class, mock_tenant, client, tenant_admin_auth
    ):
        """Authenticated request should return folder list."""
        mock_drive = MagicMock()
        mock_drive_class.return_value = mock_drive
        mock_drive.list_subfolders.return_value = [
            {"id": "folder-1", "name": "Invoices"},
            {"id": "folder-2", "name": "Reports"},
        ]

        response = client.get(
            "/api/tenant-admin/storage/folders", headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["count"] == 2
        assert data["folders"][0]["name"] == "Invoices"

    @patch("routes.tenant_admin_storage.get_current_tenant", return_value="test-tenant")
    @patch("routes.tenant_admin_storage.GoogleDriveService")
    def test_list_folders_drive_error_returns_500(
        self, mock_drive_class, mock_tenant, client, tenant_admin_auth
    ):
        """Google Drive error should return 500."""
        mock_drive_class.side_effect = Exception("Drive service unavailable")

        response = client.get(
            "/api/tenant-admin/storage/folders", headers=tenant_admin_auth
        )
        assert response.status_code == 500
        data = json.loads(response.data)
        assert "error" in data


# ============================================================================
# Get Storage Config Tests
# ============================================================================


def _ns_param(key, value, scope_origin="tenant"):
    """
    Build a storage-namespace parameter row shaped like
    ParameterService.get_params_by_namespace(...) returns, i.e.
    {"id", "namespace", "key", "value", "value_type", "scope_origin",
     "is_secret", "has_code_default"}. Only the keys the route reads
    (key / value) matter for these tests; the rest mirror the real shape.
    """
    return {
        "id": 1,
        "namespace": "storage",
        "key": key,
        "value": value,
        "value_type": "string",
        "scope_origin": scope_origin,
        "is_secret": False,
        "has_code_default": False,
    }


class TestTenantAdminStorageConfig:
    """Tests for GET /api/tenant-admin/storage/config."""

    # ------------------------------------------------------------------
    # Preservation (Task 5, Property 4) — happy-path read returns the
    # folder-id map as 200 with keys as-is.
    #
    # change-with-tests contract: Task 6 moves the GET /config read OFF the
    # superseded `tenant_config` table and ONTO the `parameters` store via
    # ParameterService.get_params_by_namespace("storage", tenant). This test
    # is therefore UPDATED to mock the NEW source — it patches
    # routes.tenant_admin_storage.ParameterService and returns storage-
    # namespace params (incl. folder-id keys). It no longer asserts the
    # removed `tenant_config` / DatabaseManager.execute_query behavior.
    #
    # NO CONTRADICTION with the Task 4 reproduce test
    # (test_get_config_source_unavailable_returns_500_generic): that test
    # makes DatabaseManager.execute_query raise and asserts the masked 500.
    # After Task 6 the fixed handler no longer calls DatabaseManager for this
    # read at all, so the two tests exercise disjoint code paths — one the
    # pre-fix stale-source error, one the post-fix parameters read.
    #
    # STATUS: FIX-VALIDATING. On UNFIXED code the route does not import
    # ParameterService, so patching routes.tenant_admin_storage.ParameterService
    # raises AttributeError and this test is EXPECTED TO FAIL until Task 6 lands.
    # ------------------------------------------------------------------
    @patch("routes.tenant_admin_storage.get_current_tenant", return_value="test-tenant")
    @patch("routes.tenant_admin_storage.ParameterService")
    def test_get_config_returns_data(
        self, mock_param_service_class, mock_tenant, client, tenant_admin_auth
    ):
        """Authenticated request returns storage config read from parameters (NEW source)."""
        mock_ps = MagicMock()
        mock_param_service_class.return_value = mock_ps
        mock_ps.get_params_by_namespace.return_value = [
            _ns_param("google_drive_invoices_folder_id", "folder-abc"),
            _ns_param("google_drive_reports_folder_id", "folder-def"),
            # a non-folder-id param in the same namespace is ignored by the filter
            _ns_param("storage_provider", "s3_shared"),
        ]

        response = client.get(
            "/api/tenant-admin/storage/config", headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        # Keys returned as-is (6.2); values as-is.
        assert "google_drive_invoices_folder_id" in data["config"]
        assert data["config"]["google_drive_invoices_folder_id"] == "folder-abc"
        assert data["config"]["google_drive_reports_folder_id"] == "folder-def"
        # Non-folder-id namespace key excluded.
        assert "storage_provider" not in data["config"]
        # Read came from the storage namespace via the service layer.
        mock_ps.get_params_by_namespace.assert_called_once_with(
            "storage", "test-tenant"
        )

    # ------------------------------------------------------------------
    # Preservation (Task 5, 6.3) — a tenant with no folder-id params gets a
    # 200 with an empty `config` object, never a 500.
    #
    # STATUS: FIX-VALIDATING — targets the post-fix parameters read path;
    # EXPECTED TO FAIL on unfixed code (ParameterService not yet patchable
    # on the route module) until Task 6 lands.
    # ------------------------------------------------------------------
    @patch("routes.tenant_admin_storage.get_current_tenant", return_value="test-tenant")
    @patch("routes.tenant_admin_storage.ParameterService")
    def test_get_config_empty_returns_200_empty_config(
        self, mock_param_service_class, mock_tenant, client, tenant_admin_auth
    ):
        """No folder-id params -> 200 with an empty config object (never 500)."""
        mock_ps = MagicMock()
        mock_param_service_class.return_value = mock_ps
        # Namespace has params, but NONE are folder-id keys.
        mock_ps.get_params_by_namespace.return_value = [
            _ns_param("storage_provider", "s3_shared"),
            _ns_param("google_drive_root", "root-xyz"),
        ]

        response = client.get(
            "/api/tenant-admin/storage/config", headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["config"] == {}

    # ------------------------------------------------------------------
    # Preservation (Task 5, 5.3 / 4.3) — the literal `_folder_id` suffix
    # filter must exclude a wildcard over-match key. The old SQL predicate
    # `config_key LIKE '%_folder_id'` treats `_` as a single-char wildcard,
    # so it would WRONGLY match "xfolder_id". The fixed handler uses
    # str.endswith("_folder_id"), so only genuine `_folder_id`-suffixed keys
    # survive.
    #
    # STATUS: FIX-VALIDATING — EXPECTED TO FAIL on unfixed code until Task 6.
    # ------------------------------------------------------------------
    @patch("routes.tenant_admin_storage.get_current_tenant", return_value="test-tenant")
    @patch("routes.tenant_admin_storage.ParameterService")
    def test_get_config_excludes_wildcard_overmatch_key(
        self, mock_param_service_class, mock_tenant, client, tenant_admin_auth
    ):
        """Only literal `_folder_id` keys are returned; `xfolder_id` is excluded."""
        mock_ps = MagicMock()
        mock_param_service_class.return_value = mock_ps
        mock_ps.get_params_by_namespace.return_value = [
            # Over-match: the SQL `_` wildcard would match this, the literal
            # endswith("_folder_id") must NOT.
            _ns_param("xfolder_id", "should-be-excluded"),
            # Genuine folder-id key.
            _ns_param("google_drive_invoices_folder_id", "folder-abc"),
        ]

        response = client.get(
            "/api/tenant-admin/storage/config", headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "google_drive_invoices_folder_id" in data["config"]
        assert data["config"]["google_drive_invoices_folder_id"] == "folder-abc"
        # The wildcard over-match key is excluded by the literal-suffix filter.
        assert "xfolder_id" not in data["config"]

    # ------------------------------------------------------------------
    # Bug 2 exploration (Task 4) — reproduce the masked 500 on the stale
    # tenant_config read. On UNFIXED code get_storage_config issues a raw
    # SELECT against the superseded `tenant_config` table / `is_secret`
    # column. In the resolved DB target that table/column is gone, so the
    # read raises a DatabaseError which the route masks as a generic 500
    # with include_success=False.
    #
    # This asserts the CURRENT (unfixed) behavior as the reproduction. Per
    # the design it also validates the fix when it passes later — the fix
    # moves the read to the `parameters` source so this stale-source error
    # path no longer triggers; the post-fix 200 behavior is covered by the
    # Task 5/6 tests.
    # ------------------------------------------------------------------
    @patch("routes.tenant_admin_storage.get_current_tenant", return_value="test-tenant")
    @patch("routes.tenant_admin_storage.DatabaseManager")
    def test_get_config_source_unavailable_returns_500_generic(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """
        An authenticated Tenant_Admin hits GET /config, but the raw read against
        the superseded tenant_config table/is_secret column raises a
        DatabaseError (missing table/column in the resolved DB target). The
        unfixed handler masks this as HTTP 500 with the include_success=False
        shape: bare {"error": <generic>, "error_id": <uuid>} and NO "success"
        key — and must never echo the raw exception text (str(e)).
        """
        # Distinctive raw exception text we assert is NOT leaked to the client.
        raw_exc_text = "Table 'finance.tenant_config' doesn't exist"

        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.side_effect = DatabaseError(raw_exc_text)

        response = client.get(
            "/api/tenant-admin/storage/config", headers=tenant_admin_auth
        )

        # Masked 500 on a plain read by an authenticated Tenant_Admin.
        assert response.status_code == 500
        data = json.loads(response.data)

        # include_success=False shape: generic message + error_id, NO success key.
        assert data["error"] == "Tenant storage request failed"
        assert "error_id" in data
        assert data["error_id"]  # present / non-empty (a uuid hex)
        assert "success" not in data

        # The raw exception text (table/column detail) must never reach the client.
        body_text = response.data.decode("utf-8")
        assert raw_exc_text not in body_text
        assert "tenant_config" not in body_text


# ============================================================================
# Update Storage Config Tests
# ============================================================================


class TestTenantAdminStorageConfigUpdate:
    """Tests for PUT /api/tenant-admin/storage/config."""

    @patch("routes.tenant_admin_storage.get_current_tenant", return_value="test-tenant")
    @patch("routes.tenant_admin_storage.DatabaseManager")
    def test_update_config_no_data_returns_400(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Update with empty data should return 400."""
        response = client.put(
            "/api/tenant-admin/storage/config", headers=tenant_admin_auth, json={}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert (
            "no configuration" in data["error"].lower()
            or "no data" in data["error"].lower()
        )

    @patch("routes.tenant_admin_storage.get_current_tenant", return_value="test-tenant")
    @patch("routes.tenant_admin_storage.DatabaseManager")
    def test_update_config_success(
        self, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """Valid config update should return 200."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = [
            {
                "config_key": "storage_invoices_folder_id",
                "config_value": "new-folder-id",
            }
        ]

        response = client.put(
            "/api/tenant-admin/storage/config",
            headers=tenant_admin_auth,
            json={"invoices_folder_id": "new-folder-id"},
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "updated successfully" in data["message"].lower()


# ============================================================================
# Test Folder Access Tests
# ============================================================================


class TestTenantAdminStorageTestFolder:
    """Tests for POST /api/tenant-admin/storage/test."""

    @patch("routes.tenant_admin_storage.get_current_tenant", return_value="test-tenant")
    @patch("routes.tenant_admin_storage.GoogleDriveService")
    def test_test_folder_missing_folder_id_returns_400(
        self, mock_drive_class, mock_tenant, client, tenant_admin_auth
    ):
        """Test folder without folder_id should return 400."""
        response = client.post(
            "/api/tenant-admin/storage/test", headers=tenant_admin_auth, json={}
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "folder_id" in data["error"].lower()

    @patch("routes.tenant_admin_storage.get_current_tenant", return_value="test-tenant")
    @patch("routes.tenant_admin_storage.GoogleDriveService")
    def test_test_folder_success(
        self, mock_drive_class, mock_tenant, client, tenant_admin_auth
    ):
        """Valid folder test should return test results."""
        mock_drive = MagicMock()
        mock_drive_class.return_value = mock_drive

        # Mock files().list().execute()
        mock_files_list = MagicMock()
        mock_files_list.execute.return_value = {
            "files": [{"id": "f1", "name": "test.pdf"}]
        }
        mock_drive.service.files.return_value.list.return_value = mock_files_list

        # Mock upload_text_file
        mock_drive.upload_text_file.return_value = {"id": "test-file-id"}

        # Mock files().delete().execute()
        mock_drive.service.files.return_value.delete.return_value.execute.return_value = None

        response = client.post(
            "/api/tenant-admin/storage/test",
            headers=tenant_admin_auth,
            json={"folder_id": "test-folder-123"},
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["test_result"]["read_access"] is True


# ============================================================================
# Storage Usage Tests
# ============================================================================


class TestTenantAdminStorageUsage:
    """Tests for GET /api/tenant-admin/storage/usage."""

    @patch("routes.tenant_admin_storage.get_current_tenant", return_value="test-tenant")
    @patch("routes.tenant_admin_storage.DatabaseManager")
    @patch("routes.tenant_admin_storage.GoogleDriveService")
    def test_get_usage_no_folders_configured(
        self, mock_drive_class, mock_db_class, mock_tenant, client, tenant_admin_auth
    ):
        """No configured folders should return empty usage."""
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.execute_query.return_value = []

        response = client.get(
            "/api/tenant-admin/storage/usage", headers=tenant_admin_auth
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert data["usage"] == {}
        assert "no storage folders" in data["message"].lower()
