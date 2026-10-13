"""s5c Phase-2 task 2.7 — Property 8 (save-once → single enqueue_sync) for the composite
``members.*`` params, on the Flask/MySQL plane.

Property 8 (design C-EDITOR / R3.5): each ``members.*`` sub-editor commits its WHOLE param
object in ONE save (POST create or PUT update), and that single save triggers EXACTLY ONE
``enqueue_sync(scope_id)`` re-projection for the write's own tenant — no per-field writes, no
extra syncs.

The generic tenant-scope trigger contract (create/update/delete → one enqueue; system scope →
none) is already covered in ``test_projection_sync_trigger_s5b.py`` with a scalar
``members.enabled`` param. This file adds the s5c-specific Property-8 assertion for the real
COMPOSITE payloads the typed editor commits:

- ``members.field_overlay`` — the whole ``map<field_def>`` object (functional_groups catalog +
  fields + fixed_overrides) saved once → one enqueue_sync;

and it exercises the REAL save-time fold + validation (``_prepare_members_config`` is NOT mocked),
so a
valid composite object saves once and an invalid one (dangling functional_group, Property 7) is
rejected 400 with ZERO enqueue_sync — proving the fail-fast guard runs before the write and before
the sync.

Mirrors the auth-mock + injected-trigger setup of the passing s5b trigger tests. No real DB, no
real AWS: the ParameterService is mocked (its ``set_param`` is a no-op) and the projection trigger
is an in-memory ``FakeSync`` injected via ``set_default_trigger``.

Feature: s5c-members-runnable-in-spa
Validates: Requirements R3, R3.5, R4.9 (Property 7, Property 8)
"""

from unittest.mock import MagicMock, patch

import pytest

from routes.parameter_admin_routes import parameter_admin_bp
from services.projection_sync_trigger import (
    ProjectionSyncTrigger,
    set_default_trigger,
)


# --- in-memory projection-sync fake (records enqueued administrations) ------


class FakeSync:
    """Records ``sync_administration`` calls; does no I/O (mirrors the s5b fake)."""

    def __init__(self):
        self.admin_calls: list[str] = []

    def sync_administration(self, administration):
        self.admin_calls.append(administration)
        return {"administration": administration}

    def sync_all(self):  # pragma: no cover - not exercised here
        return {"sync_all": True}


@pytest.fixture
def injected_trigger():
    """Inject an in-memory trigger and restore the default afterwards.

    The in-process default queue drains synchronously on enqueue, so a test can assert
    exactly which administrations were synced (and how many times).
    """
    sync = FakeSync()
    set_default_trigger(ProjectionSyncTrigger(sync=sync))
    try:
        yield sync
    finally:
        set_default_trigger(None)


# --- Flask app / client -----------------------------------------------------


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
    """Authenticated Tenant_Admin on tenant 'TestTenant' (mirrors the green s5b setup)."""
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


_AUTH_HEADERS = {"Authorization": "Bearer fake-jwt", "X-Tenant": "TestTenant"}


# --- composite payload fixtures (what the typed editor commits per save) ----

#: A whole, VALID members.field_overlay map object: functional_groups catalog + one
#: variable field assigned to a catalog group + a fixed override reassigning a group.
VALID_FIELD_OVERLAY = {
    "functional_groups": [
        {"key": "personal", "label_en": "Personal", "order": 1},
        {"key": "motor", "label_en": "Motorcycle", "order": 2},
    ],
    "fields": {
        "motor_brand": {
            "type": "string",
            "label_en": "Motor brand",
            "functional_group": "motor",
            "visible": True,
        }
    },
    "fixed_overrides": {
        "personal.street": {"functional_group": "personal"},
    },
}

# ===========================================================================
# Property 8 — one composite save → exactly one enqueue_sync
# ===========================================================================


class TestMembersCompositeSaveOnceEnqueuesSyncOnce:
    """A single save of a WHOLE members.* composite object fires enqueue_sync exactly once."""

    def test_create_field_overlay_composite_enqueues_sync_exactly_once(
        self, param_client, injected_trigger
    ):
        """POST the whole members.field_overlay map object → one enqueue_sync for own tenant."""
        mocks = _admin_auth_mocks() + [
            patch("routes.parameter_admin_routes.DatabaseManager"),
            patch("routes.parameter_admin_routes._get_service", return_value=MagicMock()),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
            resp = param_client.post(
                "/api/tenant-admin/parameters",
                json={
                    "scope": "tenant",
                    "namespace": "members",
                    "key": "field_overlay",
                    "value": VALID_FIELD_OVERLAY,
                    "value_type": "json",
                },
                headers=_AUTH_HEADERS,
            )

        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        # Property 8: the whole-object save fired EXACTLY ONE re-projection, for own tenant.
        assert injected_trigger.admin_calls == ["TestTenant"]

    def test_update_field_overlay_composite_enqueues_sync_exactly_once(
        self, param_client, injected_trigger
    ):
        """PUT the whole members.field_overlay map object → one enqueue_sync for own tenant."""
        mock_db = MagicMock()
        # The PUT handler reads the existing row to learn scope/scope_id.
        mock_db.execute_query.return_value = [
            {
                "scope": "tenant",
                "scope_id": "TestTenant",
                "namespace": "members",
                "key": "field_overlay",
                "value_type": "json",
                "is_secret": False,
            }
        ]
        mock_svc = MagicMock()
        mock_svc.get_param.return_value = None
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
            resp = param_client.put(
                "/api/tenant-admin/parameters/55",
                json={"value": VALID_FIELD_OVERLAY, "value_type": "json"},
                headers=_AUTH_HEADERS,
            )

        assert resp.status_code == 200
        # Property 8: exactly one re-projection for the row's own tenant, once.
        assert injected_trigger.admin_calls == ["TestTenant"]

    def test_create_field_overlay_saves_whole_object_in_one_set_param(
        self, param_client, injected_trigger
    ):
        """The single save commits the WHOLE composite object (one set_param, whole value)."""
        mock_svc = MagicMock()
        mocks = _admin_auth_mocks() + [
            patch("routes.parameter_admin_routes.DatabaseManager"),
            patch("routes.parameter_admin_routes._get_service", return_value=mock_svc),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
            resp = param_client.post(
                "/api/tenant-admin/parameters",
                json={
                    "scope": "tenant",
                    "namespace": "members",
                    "key": "field_overlay",
                    "value": VALID_FIELD_OVERLAY,
                    "value_type": "json",
                },
                headers=_AUTH_HEADERS,
            )

        assert resp.status_code == 200
        # Exactly one write of the WHOLE object (not one write per field/group).
        assert mock_svc.set_param.call_count == 1
        saved_value = mock_svc.set_param.call_args.args[4]
        # Phase-1 R3.2: the save FOLDS the editor's per-locale ``label_<locale>`` inputs into
        # the stored inline ``{nl,en,…}`` label dict — so the persisted value is the WHOLE
        # object with labels folded (not the raw per-locale editor inputs). Every other key is
        # carried through unchanged (one write, whole composite).
        assert saved_value["functional_groups"] == [
            {"key": "personal", "order": 1, "label": {"en": "Personal"}},
            {"key": "motor", "order": 2, "label": {"en": "Motorcycle"}},
        ]
        assert saved_value["fields"]["motor_brand"] == {
            "type": "string",
            "functional_group": "motor",
            "visible": True,
            "label": {"en": "Motor brand"},
        }
        # A fixed override with no label input is carried through untouched (no empty label).
        assert saved_value["fixed_overrides"] == {
            "personal.street": {"functional_group": "personal"},
        }
        # No raw per-locale editor input survives the fold.
        assert "label_en" not in saved_value["functional_groups"][0]
        assert "label_en" not in saved_value["fields"]["motor_brand"]
        assert injected_trigger.admin_calls == ["TestTenant"]


# ===========================================================================
# Property 7 — an invalid composite save is rejected BEFORE any enqueue_sync
# ===========================================================================


class TestInvalidCompositeSaveRejectedBeforeSync:
    """The fail-fast save-time guard rejects a bad composite (400) with ZERO enqueue_sync."""

    def test_create_field_overlay_dangling_group_rejected_no_enqueue_sync(
        self, param_client, injected_trigger
    ):
        """A field_overlay with a dangling functional_group → 400, NO sync (Property 7)."""
        bad_overlay = {
            "functional_groups": [{"key": "motor", "label_en": "Motor", "order": 1}],
            "fields": {
                "motor_brand": {"type": "string", "functional_group": "does_not_exist"}
            },
        }
        mocks = _admin_auth_mocks() + [
            patch("routes.parameter_admin_routes.DatabaseManager"),
            patch("routes.parameter_admin_routes._get_service", return_value=MagicMock()),
        ]
        with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
            resp = param_client.post(
                "/api/tenant-admin/parameters",
                json={
                    "scope": "tenant",
                    "namespace": "members",
                    "key": "field_overlay",
                    "value": bad_overlay,
                    "value_type": "json",
                },
                headers=_AUTH_HEADERS,
            )

        assert resp.status_code == 400
        # Rejected before the write → no projection sync fired at all.
        assert injected_trigger.admin_calls == []
