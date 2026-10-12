"""
Members config redesign — Phase 0 step 3 (impact-analysis §2 / risk #6): the projected-config
DELIVERED/LOADED status SURFACES on ``GET /members/field-config`` so the authoring UI can show
whether a ``members.*`` edit has been projected (delivered) and is what the module reads
(loaded).

The READ half ships in ``MembersProjectionReader.get_config_status`` — it resolves each
projected ``config#*`` row's monotonic ``version`` (or ``None`` when never delivered), covered
in ``test_members_projection_reader.py``. These tests pin the two server halves that wire it
THROUGH the Members edge, mirroring the sibling ``mail_enabled`` wiring 1:1:

1. **Domain** — :meth:`MembershipService.get_field_config` surfaces a top-level
   ``config_status`` map sourced from the injected
   :class:`~sam.members.domain.config_status.ConfigStatusProvider`, keyed by the verified
   ``tenant_id``. Empty-is-valid: a service built with NO provider reports every config id as
   ``None`` (not yet delivered). The config stays JSON-serializable.

2. **Edge provider seam** — the module edge's :class:`_ProjectionConfigStatusProvider` reads a
   fresh projection reader (or the ``_CONFIG_STATUS_PROVIDER_OVERRIDE`` test seam), mirroring
   the mail-gate / view-contexts seams, so a re-projected ``config#*`` edit reflects without
   rebuilding the service.

A tiny in-memory fake repository (reused from the sibling field-config test) + a
:class:`~sam.members.domain.config_status.StaticConfigStatusProvider` back the service — no
boto3, no AWS, no MySQL (the status is read from the projection, never a live cross-plane call).
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.config_status import StaticConfigStatusProvider
from sam.members.domain.field_resolver import StaticOverlayProvider
from sam.members.domain.membership_service import MembershipService
from sam.members.handler import app

# Reuse the field-config test's in-memory fake catalog repo + entry helper.
from sam.tests.test_field_config_endpoint import FakeCatalogRepository, _entry


@pytest.fixture()
def repo() -> FakeCatalogRepository:
    r = FakeCatalogRepository()
    r.add_type("h-dcn", _entry("h-dcn", "gewoon", order=10))
    r.add_type("other", _entry("other", "member", order=10))
    return r


# ---------------------------------------------------------------------------
# (1) Domain — MembershipService.get_field_config surfaces config_status
# ---------------------------------------------------------------------------


class TestGetFieldConfigSurfacesConfigStatus:
    def test_config_status_reflects_delivered_versions(self, repo):
        """A tenant with projected rows surfaces each config id's delivered version."""
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            config_status_provider=StaticConfigStatusProvider(
                {
                    "h-dcn": {
                        "scope": 5,
                        "fields": "2026-10-12T09:00:00",
                        # views + mail intentionally absent → not yet delivered.
                    }
                }
            ),
        )
        status = service.get_field_config("h-dcn")["config_status"]

        assert status["scope"] == 5
        assert status["fields"] == "2026-10-12T09:00:00"
        assert status["views"] is None
        assert status["mail"] is None

    def test_config_status_defaults_all_none_with_no_provider_wired(self, repo):
        """Empty-is-valid: a service built with NO provider reports every id un-delivered."""
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        status = service.get_field_config("h-dcn")["config_status"]

        assert status == {"scope": None, "fields": None, "views": None, "mail": None}

    def test_config_status_is_per_tenant(self, repo):
        """Status is resolved per the verified tenant_id — no cross-tenant bleed."""
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            config_status_provider=StaticConfigStatusProvider(
                {"h-dcn": {"scope": 9}}
            ),
        )

        assert service.get_field_config("h-dcn")["config_status"]["scope"] == 9
        # 'other' has no entry → all-None even though h-dcn is delivered.
        assert service.get_field_config("other")["config_status"]["scope"] is None

    def test_field_config_with_status_is_json_serializable(self, repo):
        """The surfaced status keeps the payload pure-JSON (the edge json.dumps it)."""
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            config_status_provider=StaticConfigStatusProvider(
                {"h-dcn": {"scope": 1, "fields": 2, "views": 3, "mail": 4}}
            ),
        )
        dumped = json.dumps(service.get_field_config("h-dcn"))
        assert '"config_status"' in dumped


# ---------------------------------------------------------------------------
# (2) Edge provider seam — _ProjectionConfigStatusProvider + the test override
# ---------------------------------------------------------------------------


class TestEdgeConfigStatusProviderSeam:
    def test_provider_delegates_to_the_test_override_when_set(self, monkeypatch):
        """The edge provider honours the _CONFIG_STATUS_PROVIDER_OVERRIDE seam (no AWS)."""
        monkeypatch.setattr(
            app,
            "_CONFIG_STATUS_PROVIDER_OVERRIDE",
            StaticConfigStatusProvider({"h-dcn": {"scope": 7}}),
        )
        provider = app._ProjectionConfigStatusProvider()

        assert provider.get_config_status("h-dcn")["scope"] == 7
        # A tenant the override does not know → all-None (empty-is-valid).
        assert provider.get_config_status("other")["scope"] is None

    def test_default_edge_provider_is_wired_into_the_service(self):
        """The module-level config-status provider satisfies the ConfigStatusProvider seam."""
        assert hasattr(app._CONFIG_STATUS_PROVIDER, "get_config_status")
        assert callable(app._CONFIG_STATUS_PROVIDER.get_config_status)
