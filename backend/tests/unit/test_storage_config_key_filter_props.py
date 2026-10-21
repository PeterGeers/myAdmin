"""
Property-based tests for the storage/config folder-id key filter.

Spec: .kiro/specs/tenant-admin-storage-and-merge-500s
  Bug 2 = GET /api/tenant-admin/storage/config
  Property 4 = Preservation (design.md)

Property under test (5.3 / 4.3 / 6.2): when GET /api/tenant-admin/storage/config
reads the tenant's `storage` namespace via
ParameterService.get_params_by_namespace("storage", tenant), the handler includes
ONLY parameters whose key ends in the LITERAL suffix "_folder_id"
(str.endswith("_folder_id")), returns the keys AS-IS mapped to their values, and
never includes a wildcard over-match key such as "xfolder_id" (which the old SQL
`LIKE '%_folder_id'` predicate would have wrongly matched because `_` is a
single-char LIKE wildcard).

Seam note: in Task 6 the filter is implemented INLINE in
routes.tenant_admin_storage.get_storage_config (there is no importable
pure-function helper, and we deliberately do not invent one). So this property is
asserted against the endpoint's OBSERVABLE behavior with the parameters source
mocked — the genuine seam that exists after the fix.

STATUS: FIX-VALIDATING. On UNFIXED code get_storage_config reads `tenant_config`
via DatabaseManager and routes.tenant_admin_storage does not import
ParameterService, so patching it raises AttributeError. The module-level
`requires_parameters_source` autouse check skips these tests until Task 6 wires
the parameters read path, keeping the UNFIXED run green while still encoding the
intended post-fix contract.

Validates: Requirements 5.3, 4.3, 6.2
"""

import os
import sys
import json

import pytest
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings, HealthCheck

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import routes.tenant_admin_storage as storage_route


# ---------------------------------------------------------------------------
# Gate: these properties target the post-fix parameters read path (Task 6).
# Until the route imports ParameterService and reads the storage namespace, the
# seam these properties exercise does not exist, so skip rather than report a
# misleading failure on unfixed code.
# ---------------------------------------------------------------------------
_HAS_PARAM_SOURCE = hasattr(storage_route, "ParameterService")

requires_parameters_source = pytest.mark.skipif(
    not _HAS_PARAM_SOURCE,
    reason=(
        "FIX-VALIDATING: get_storage_config does not yet read the `parameters` "
        "source (routes.tenant_admin_storage.ParameterService absent) — wired in "
        "Task 6. Property exercises the post-fix folder-id filter seam."
    ),
)


# ---------------------------------------------------------------------------
# Fixtures: a minimal Flask app with the tenant-admin-storage blueprint, plus a
# patched-auth client. Self-contained (the api-level `client` fixture lives under
# tests/api/conftest and is not visible to tests/unit).
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    from flask import Flask

    with (
        patch("auth.cognito_utils.extract_user_credentials") as mock_creds,
        patch("auth.tenant_context.validate_tenant_access", return_value=(True, None)),
        patch("auth.tenant_context.get_user_tenants", return_value=["test-tenant"]),
        patch("auth.role_cache.get_tenant_roles", return_value=["Tenant_Admin"]),
    ):
        mock_creds.return_value = ("admin@example.com", ["Tenant_Admin"], None)

        app = Flask(__name__)
        app.register_blueprint(storage_route.tenant_admin_storage_bp)
        app.config["TESTING"] = True
        with app.test_client() as test_client:
            with app.app_context():
                yield test_client


AUTH_HEADERS = {"Authorization": "Bearer test-token", "X-Tenant": "test-tenant"}


def _ns_param(key, value):
    """A storage-namespace param shaped like get_params_by_namespace returns."""
    return {
        "id": 1,
        "namespace": "storage",
        "key": key,
        "value": value,
        "value_type": "string",
        "scope_origin": "tenant",
        "is_secret": False,
        "has_code_default": False,
    }


# Key generators -------------------------------------------------------------
# Non-folder-id keys (must NOT survive the filter), including the tricky
# over-match "xfolder_id" family (no literal underscore before "folder_id").
_non_folder_id_base = st.sampled_from(
    [
        "storage_provider",
        "google_drive_root",
        "xfolder_id",  # SQL LIKE '%_folder_id' over-match — excluded by endswith
        "afolder_id",  # another over-match variant
        "folder_id_extra",  # suffix in the middle, not at the end
        "invoices_folderid",  # missing underscore entirely
        "random_key",
    ]
)
# Keys that genuinely end in the literal "_folder_id" suffix (MUST survive).
_folder_id_key = st.sampled_from(
    [
        "google_drive_invoices_folder_id",
        "google_drive_reports_folder_id",
        "x_folder_id",  # literal underscore before folder_id — INCLUDED
        "facturen_folder_id",
        "_folder_id",  # degenerate but literal-suffix key
    ]
)

_value = st.text(
    alphabet=st.characters(min_codepoint=48, max_codepoint=122),
    min_size=1,
    max_size=12,
)


@requires_parameters_source
@settings(max_examples=60, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    folder_items=st.lists(st.tuples(_folder_id_key, _value), min_size=0, max_size=5),
    non_folder_items=st.lists(
        st.tuples(_non_folder_id_base, _value), min_size=0, max_size=5
    ),
)
def test_only_literal_folder_id_keys_appear_in_config(
    client, folder_items, non_folder_items
):
    """
    For any mix of storage-namespace params, GET /config returns exactly the
    params whose key ends in the literal "_folder_id" suffix, with keys/values
    as-is, and excludes every non-folder-id key (incl. the `xfolder_id`
    wildcard over-match).
    """
    # De-dup by key; folder-id entries define the expected map (keys as-is).
    all_items = {}
    for k, v in non_folder_items:
        all_items[k] = v
    expected = {}
    for k, v in folder_items:
        all_items[k] = v
        expected[k] = v

    params = [_ns_param(k, v) for k, v in all_items.items()]

    with (
        patch.object(storage_route, "get_current_tenant", return_value="test-tenant"),
        patch.object(storage_route, "ParameterService") as mock_ps_class,
    ):
        mock_ps = MagicMock()
        mock_ps_class.return_value = mock_ps
        mock_ps.get_params_by_namespace.return_value = params

        response = client.get("/api/tenant-admin/storage/config", headers=AUTH_HEADERS)

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True

    returned = data["config"]
    # Exactly the literal-suffix keys, values as-is.
    assert returned == expected
    # Belt-and-suspenders: nothing returned violates the literal-suffix rule.
    for key in returned:
        assert key.endswith("_folder_id")
    # The classic wildcard over-match key never survives.
    assert "xfolder_id" not in returned
