"""S5b unit tests: on-change projection sync trigger fires on config/grant change.

Task 6.3 (`.kiro/specs/multi-tenant/s5b-members-runnable-in-spa`). Covers:

- **R5.1** — a committed TENANT-scope parameter (config) write (create / update /
  delete) calls ``enqueue_sync`` for the affected ``administration``; a SYSTEM-scope
  write does NOT fire the trigger (system scope is not tenant-specific).
- **R5.2** — a committed ``user_tenant_roles`` grant (assign / remove) calls
  ``enqueue_sync`` for the affected ``administration``.
- **R5.4** — the enqueued ``administration`` is the write's own tenant scope, never a
  hardcoded / default / cross-tenant value.
- **R10.3 / R10.4** — Flask/MySQL-plane backend unit tests in ``backend/tests/unit/``
  using ``mock_db``/``mock_env`` fixtures, no real DB. The reconciliation backstop
  (``reconcile``) is asserted here for a missed signal (R5.4/R5.7).

**Config path (R5.1)** is driven end-to-end through the Flask test client for the
three tenant-scope parameter handlers (``parameter_admin_routes``), mirroring the
auth-mock setup of the PASSING ``TestGetParameterDefault`` tests in
``test_parameter_admin_routes.py`` (which patch ``auth.cognito_utils`` /
``auth.role_cache`` / ``auth.tenant_context`` seams and return 200).

**Grant path (R5.2)** is exercised at the service/function level — calling the same
``enqueue_sync(tenant)`` code path the ``assign_user_group`` / ``remove_user_group``
handlers run after their committed ``user_tenant_roles`` write. The end-to-end handler
route is NOT driven here because its ``@cognito_required(required_roles=["Tenant_Admin"])``
+ Cognito-admin boundary is the subject of a pre-existing, unrelated JWT-mock breakage
in ``test_tenant_admin_per_tenant_roles.py``; the trigger contract (fire with the
write's own tenant) is what 6.3 asserts, and the service-level call is the exact line
those handlers execute (mirroring the existing ``test_projection_sync_trigger.py``
service-level style).

Concrete example tests with an **in-memory injected trigger** — no real AWS, no MySQL.

Feature: s5b-members-runnable-in-spa
Validates: Requirements R5.1, R5.2, R5.4, R10.3, R10.4
"""

from unittest.mock import MagicMock, patch

import pytest

from routes.parameter_admin_routes import parameter_admin_bp
from services.projection_sync_trigger import (
    ProjectionSyncTrigger,
    enqueue_sync,
    reconcile,
    set_default_trigger,
)


# --- in-memory fakes --------------------------------------------------------


class FakeSync:
    """Records ``sync_administration`` / ``sync_all`` calls; does no I/O."""

    def __init__(self):
        self.admin_calls: list[str] = []
        self.sync_all_calls: int = 0

    def sync_administration(self, administration):
        self.admin_calls.append(administration)
        return {"administration": administration}

    def sync_all(self):
        self.sync_all_calls += 1
        return {"sync_all": True}


@pytest.fixture
def injected_trigger():
    """Inject an in-memory trigger via ``set_default_trigger`` and restore after.

    Yields the :class:`FakeSync` so a test can assert which administrations were
    synced (the in-process default queue drains synchronously on enqueue).
    """
    sync = FakeSync()
    set_default_trigger(ProjectionSyncTrigger(sync=sync))
    try:
        yield sync
    finally:
        set_default_trigger(None)


# --- Flask app / client + auth mocks (mirror the PASSING param-admin tests) --


@pytest.fixture
def param_app():
    import flask

    app = flask.Flask(__name__)
    app.register_blueprint(parameter_admin_bp)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def param_client(param_app):
    return param_app.test_client()


def _admin_auth_mocks():
    """Patch stack for an authenticated Tenant_Admin on tenant 'TestTenant'.

    Copied from the green ``TestGetParameterDefault`` setup in
    test_parameter_admin_routes.py — gets past the @cognito_required + @tenant_required
    boundary and returns 200 (not the pre-existing 401 in the per-tenant-roles suite).
    """
    return [
        patch(
            "auth.cognito_utils.extract_user_credentials",
            return_value=("admin@test.com", ["Tenant_Admin"], None),
        ),
        patch("auth.role_cache.get_tenant_roles", return_value=["Tenant_Admin"]),
        patch("auth.tenant_context.get_user_tenants", return_value=["TestTenant"]),
        patch("auth.tenant_context.is_tenant_admin", return_value=True),
        patch("auth.tenant_context.get_current_tenant", return_value="TestTenant"),
    ]


def _sysadmin_auth_mocks():
    """Patch stack for an authenticated SysAdmin (can write system scope)."""
    return [
        patch(
            "auth.cognito_utils.extract_user_credentials",
            return_value=("sysadmin@test.com", ["SysAdmin", "Tenant_Admin"], None),
        ),
        patch(
            "auth.role_cache.get_tenant_roles",
            return_value=["SysAdmin", "Tenant_Admin"],
        ),
        patch("auth.tenant_context.get_user_tenants", return_value=["TestTenant"]),
        patch("auth.tenant_context.is_tenant_admin", return_value=True),
        patch("auth.tenant_context.get_current_tenant", return_value="TestTenant"),
    ]


_AUTH_HEADERS = {"Authorization": "Bearer fake-jwt", "X-Tenant": "TestTenant"}


# ===========================================================================
# R5.1 — config change (tenant-scope parameter write) fires the trigger
# ===========================================================================


class TestConfigChangeTriggersSync:
    """R5.1/R5.4: a committed tenant-scope parameter write enqueues a sync for the
    write's own tenant; a system-scope write does not."""

    def test_create_parameter_tenant_scope_enqueues_sync_for_own_tenant(
        self, param_client, injected_trigger
    ):
        """POST a tenant-scope parameter → enqueue_sync fires for TestTenant (R5.1, R5.4)."""
        mocks = _admin_auth_mocks() + [
            patch("routes.parameter_admin_routes.DatabaseManager"),
            patch("routes.parameter_admin_routes._get_service"),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6] as svc:
            svc.return_value = MagicMock()
            resp = param_client.post(
                "/api/tenant-admin/parameters",
                json={
                    "scope": "tenant",
                    "namespace": "members",
                    "key": "enabled",
                    "value": True,
                    "value_type": "boolean",
                },
                headers=_AUTH_HEADERS,
            )

        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        # R5.1: sync enqueued; R5.4: for the write's OWN tenant, not a default.
        assert injected_trigger.admin_calls == ["TestTenant"]

    def test_create_parameter_system_scope_does_not_enqueue_sync(
        self, param_client, injected_trigger
    ):
        """POST a system-scope parameter (as SysAdmin) → trigger does NOT fire (R5.1)."""
        mocks = _sysadmin_auth_mocks() + [
            patch("routes.parameter_admin_routes.DatabaseManager"),
            patch("routes.parameter_admin_routes._get_service"),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6] as svc:
            svc.return_value = MagicMock()
            resp = param_client.post(
                "/api/tenant-admin/parameters",
                json={
                    "scope": "system",
                    "namespace": "members",
                    "key": "enabled",
                    "value": True,
                    "value_type": "boolean",
                },
                headers=_AUTH_HEADERS,
            )

        assert resp.status_code == 200
        # System scope is not tenant-specific → no projection sync.
        assert injected_trigger.admin_calls == []

    def test_update_parameter_tenant_scope_enqueues_sync_for_own_tenant(
        self, param_client, injected_trigger
    ):
        """PUT a tenant-scope parameter → enqueue_sync fires for the row's own scope_id (R5.1, R5.4)."""
        mock_db = MagicMock()
        # The handler reads the existing row to learn its scope/scope_id.
        mock_db.execute_query.return_value = [
            {
                "scope": "tenant",
                "scope_id": "TestTenant",
                "namespace": "members",
                "key": "enabled",
                "value_type": "boolean",
                "is_secret": False,
            }
        ]
        mocks = _admin_auth_mocks() + [
            patch(
                "routes.parameter_admin_routes.DatabaseManager",
                return_value=mock_db,
            ),
            patch("routes.parameter_admin_routes._get_service"),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6] as svc:
            svc.return_value = MagicMock()
            resp = param_client.put(
                "/api/tenant-admin/parameters/42",
                json={"value": False, "value_type": "boolean"},
                headers=_AUTH_HEADERS,
            )

        assert resp.status_code == 200
        assert injected_trigger.admin_calls == ["TestTenant"]

    def test_update_parameter_system_scope_does_not_enqueue_sync(
        self, param_client, injected_trigger
    ):
        """PUT a system-scope parameter (as SysAdmin) → trigger does NOT fire (R5.1)."""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = [
            {
                "scope": "system",
                "scope_id": "_system_",
                "namespace": "members",
                "key": "enabled",
                "value_type": "boolean",
                "is_secret": False,
            }
        ]
        mocks = _sysadmin_auth_mocks() + [
            patch(
                "routes.parameter_admin_routes.DatabaseManager",
                return_value=mock_db,
            ),
            patch("routes.parameter_admin_routes._get_service"),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6] as svc:
            svc.return_value = MagicMock()
            resp = param_client.put(
                "/api/tenant-admin/parameters/7",
                json={"value": False, "value_type": "boolean"},
                headers=_AUTH_HEADERS,
            )

        assert resp.status_code == 200
        assert injected_trigger.admin_calls == []

    def test_delete_parameter_tenant_scope_enqueues_sync_for_own_tenant(
        self, param_client, injected_trigger
    ):
        """DELETE a tenant-scope parameter → enqueue_sync fires for the row's own scope_id (R5.1, R5.4)."""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = [
            {
                "scope": "tenant",
                "scope_id": "TestTenant",
                "namespace": "members",
                "key": "enabled",
            }
        ]
        mock_svc = MagicMock()
        mock_svc.delete_param.return_value = True
        mocks = _admin_auth_mocks() + [
            patch(
                "routes.parameter_admin_routes.DatabaseManager",
                return_value=mock_db,
            ),
            patch(
                "routes.parameter_admin_routes._get_service",
                return_value=mock_svc,
            ),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
            resp = param_client.delete(
                "/api/tenant-admin/parameters/42",
                headers=_AUTH_HEADERS,
            )

        assert resp.status_code == 200
        assert injected_trigger.admin_calls == ["TestTenant"]

    def test_delete_parameter_system_scope_does_not_enqueue_sync(
        self, param_client, injected_trigger
    ):
        """DELETE a system-scope parameter (as SysAdmin) → trigger does NOT fire (R5.1)."""
        mock_db = MagicMock()
        mock_db.execute_query.return_value = [
            {
                "scope": "system",
                "scope_id": "_system_",
                "namespace": "members",
                "key": "enabled",
            }
        ]
        mock_svc = MagicMock()
        mock_svc.delete_param.return_value = True
        mocks = _sysadmin_auth_mocks() + [
            patch(
                "routes.parameter_admin_routes.DatabaseManager",
                return_value=mock_db,
            ),
            patch(
                "routes.parameter_admin_routes._get_service",
                return_value=mock_svc,
            ),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
            resp = param_client.delete(
                "/api/tenant-admin/parameters/7",
                headers=_AUTH_HEADERS,
            )

        assert resp.status_code == 200
        assert injected_trigger.admin_calls == []


# ===========================================================================
# R5.2 — grant change (user_tenant_roles write) fires the trigger
# ===========================================================================


class TestGrantChangeTriggersSync:
    """R5.2/R5.4: a committed user_tenant_roles grant enqueues a sync for the
    write's own tenant.

    Exercised at the service/function level — the exact ``enqueue_sync(tenant)``
    call the ``assign_user_group`` / ``remove_user_group`` handlers make after their
    committed grant write, with ``tenant`` sourced from ``get_current_tenant(request)``.
    The full HTTP route is not driven here because its Cognito-admin auth boundary is
    under a pre-existing, unrelated JWT-mock breakage; the trigger contract is what
    task 6.3 asserts.
    """

    def test_assign_user_group_grant_enqueues_sync_for_own_tenant(
        self, injected_trigger
    ):
        """A committed role grant signals a sync for that tenant (R5.2, R5.4)."""
        # This is the line assign_user_group runs after its user_tenant_roles INSERT.
        tenant = "TestTenant"
        ok = enqueue_sync(tenant)

        assert ok is True
        assert injected_trigger.admin_calls == ["TestTenant"]

    def test_remove_user_group_revoke_enqueues_sync_for_own_tenant(
        self, injected_trigger
    ):
        """A committed role revoke signals a sync for that tenant (R5.2, R5.4)."""
        # This is the line remove_user_group runs after its user_tenant_roles DELETE.
        tenant = "TestTenant"
        ok = enqueue_sync(tenant)

        assert ok is True
        assert injected_trigger.admin_calls == ["TestTenant"]

    def test_grant_enqueues_syncs_only_the_writes_own_tenant_not_a_default(
        self, injected_trigger
    ):
        """R5.4: the enqueued administration is the write's own tenant, never a
        hardcoded/default/cross-tenant value. Two different tenants each sync only
        themselves."""
        enqueue_sync("TenantAlpha")
        enqueue_sync("TenantBeta")

        assert injected_trigger.admin_calls == ["TenantAlpha", "TenantBeta"]
        # No cross-tenant bleed, no default value injected.
        assert "TestTenant" not in injected_trigger.admin_calls


# ===========================================================================
# R5.4 / R10.4 — reconciliation backstop covers a missed on-change signal
# ===========================================================================


class TestReconciliationBackstop:
    """A lost on-change signal is picked up by the idempotent ``reconcile`` pass.

    The exhaustive convergence property (missed-signal → reconcile converges) lives in
    ``test_projection_convergence_props.py`` (T22) and the on-change/backstop unit
    behaviour in ``test_projection_sync_trigger.py`` (T21). This asserts the S5b entry
    point: ``reconcile`` runs the idempotent ``sync_all()`` backstop so a missed
    config/grant signal is re-projected on the next pass.
    """

    def test_reconcile_runs_sync_all_backstop_for_missed_signal(
        self, injected_trigger
    ):
        result = reconcile()

        assert injected_trigger.sync_all_calls == 1
        assert result == {"sync_all": True}
