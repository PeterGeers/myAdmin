"""
pivot-output-actions Task 1.3 (R0 / R1, design §6.3) — the mail-enabled flag SURFACES on
``GET /members/field-config`` so the SPA offers the mail output actions only when the
tenant is cleared to send.

Task 0.4 shipped the READ half: ``MembersProjectionReader.is_mail_enabled`` resolves the
per-tenant "mail-enabled / SES-certified" flag from the projected ``config#mail`` row,
fail-closed (covered in ``test_members_projection_reader.py``). Task 1.3 wires that flag
THROUGH the Members edge so the frontend can gate the Mail action on it. These tests pin
the two server halves 1.3 adds:

1. **Domain** — :meth:`MembershipService.get_field_config` surfaces a top-level
   ``mail_enabled`` boolean sourced from the injected
   :class:`~sam.members.domain.mail_gate.MailGateProvider`, keyed by the verified
   ``tenant_id``. FAIL-CLOSED (R0): a service built with NO provider reports ``False``; a
   static provider that says a tenant is enabled surfaces ``True`` only for that tenant.
   The config stays JSON-serializable.

2. **Edge provider seam** — the module edge's :class:`_ProjectionMailGateProvider` reads a
   fresh projection reader (or the ``_MAIL_GATE_PROVIDER_OVERRIDE`` test seam), mirroring
   the view-contexts / scope seams, so a re-projected ``config#mail`` edit reflects without
   rebuilding the service.

A tiny in-memory fake repository (reused from the sibling field-config test) + a
:class:`~sam.members.domain.mail_gate.StaticMailGateProvider` back the service — no boto3,
no AWS, no MySQL (R0: the flag is read from the projection, never a live cross-plane call).

Validates: Requirements R0, R1
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.field_resolver import StaticOverlayProvider
from sam.members.domain.mail_gate import StaticMailGateProvider
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
# (1) Domain — MembershipService.get_field_config surfaces mail_enabled
# ---------------------------------------------------------------------------


class TestGetFieldConfigSurfacesMailEnabled:
    def test_mail_enabled_true_when_provider_reports_tenant_enabled(self, repo):
        """An explicitly mail-enabled tenant surfaces mail_enabled=True (R1)."""
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            mail_gate_provider=StaticMailGateProvider({"h-dcn": True}),
        )
        config = service.get_field_config("h-dcn")

        assert config["mail_enabled"] is True

    def test_mail_enabled_false_when_provider_reports_tenant_disabled(self, repo):
        """A present-but-disabled tenant surfaces mail_enabled=False (gate closed)."""
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            mail_gate_provider=StaticMailGateProvider({"h-dcn": False}),
        )
        config = service.get_field_config("h-dcn")

        assert config["mail_enabled"] is False

    def test_mail_enabled_defaults_false_with_no_provider_wired(self, repo):
        """Fail-closed (R0): a service built with NO mail-gate provider reports False."""
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")

        assert config["mail_enabled"] is False

    def test_mail_enabled_is_per_tenant(self, repo):
        """The flag is resolved per the verified tenant_id — no cross-tenant bleed (R0)."""
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            mail_gate_provider=StaticMailGateProvider({"h-dcn": True}),
        )

        assert service.get_field_config("h-dcn")["mail_enabled"] is True
        # 'other' has no entry → fail-closed False even though h-dcn is enabled.
        assert service.get_field_config("other")["mail_enabled"] is False

    def test_mail_enabled_absent_entry_fails_closed(self, repo):
        """A tenant the provider has never heard of → False (fail-closed, R0)."""
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            mail_gate_provider=StaticMailGateProvider({"someone-else": True}),
        )
        config = service.get_field_config("h-dcn")

        assert config["mail_enabled"] is False

    def test_field_config_with_mail_flag_is_json_serializable(self, repo):
        """The surfaced flag keeps the payload pure-JSON (the edge json.dumps it)."""
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            mail_gate_provider=StaticMailGateProvider({"h-dcn": True}),
        )
        # Must not raise, and the serialized form carries the boolean.
        dumped = json.dumps(service.get_field_config("h-dcn"))
        assert '"mail_enabled": true' in dumped


# ---------------------------------------------------------------------------
# (2) Edge provider seam — _ProjectionMailGateProvider + the test override
# ---------------------------------------------------------------------------


class TestEdgeMailGateProviderSeam:
    def test_provider_delegates_to_the_test_override_when_set(self, monkeypatch):
        """The edge provider honours the _MAIL_GATE_PROVIDER_OVERRIDE seam (no AWS)."""
        monkeypatch.setattr(
            app,
            "_MAIL_GATE_PROVIDER_OVERRIDE",
            StaticMailGateProvider({"h-dcn": True}),
        )
        provider = app._ProjectionMailGateProvider()

        assert provider.is_mail_enabled("h-dcn") is True
        # A tenant the override does not enable → fail-closed False.
        assert provider.is_mail_enabled("other") is False

    def test_default_edge_provider_is_wired_into_the_service(self):
        """The module-level mail-gate provider satisfies the MailGateProvider seam."""
        # The stable indirection the service is constructed with (app._MAIL_GATE_PROVIDER).
        assert hasattr(app._MAIL_GATE_PROVIDER, "is_mail_enabled")
        # With no override set, it answers without raising (reads a fresh projection; here
        # it simply must expose the duck-typed method — no AWS round-trip is forced).
        assert callable(app._MAIL_GATE_PROVIDER.is_mail_enabled)
