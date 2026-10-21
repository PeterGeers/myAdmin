"""
spec 02 task 7.1 fix — the full ``config#mail`` body SURFACES on ``GET /members/field-config``
as ``mail_config`` so the typed Mail authoring form (``MembersMailConfigEditor``) LOADS its
initial values from the AUTHORITATIVE SAM source (the ``config#mail`` row) rather than the
retired MySQL ``members.*`` params.

Background: ``mail_enabled`` already surfaces on the field-config read for the pivot output-
actions gate (``test_field_config_mail_enabled.py``). But the typed Mail FORM also needs the
rest of the mail scalars to populate its fields — and reading them from MySQL is the wrong
source: ``mail_reply_to_default`` is SAM-only net-new (no MySQL row), so a saved value reads
back blank. This test pins the two server halves the fix adds, mirroring the ``mail_enabled``
seam exactly:

1. **Domain** — :meth:`MembershipService.get_field_config` surfaces a top-level ``mail_config``
   dict sourced from the injected :class:`~sam.members.domain.mail_config.MailConfigProvider`,
   keyed by the verified ``tenant_id``. FAIL-CLOSED: a service with NO provider reports the
   safe minimal body. JSON-serializable.
2. **Edge provider seam** — :class:`_ProjectionMailConfigProvider` reads a fresh projection
   reader (or the ``_MAIL_CONFIG_PROVIDER_OVERRIDE`` test seam), mirroring the mail-gate seam.

Validates: spec 02 R9 / R14.4 / R20 (the authoring read-back path).
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
from sam.members.domain.mail_config import StaticMailConfigProvider, fail_closed_mail_config
from sam.members.domain.membership_service import MembershipService
from sam.members.handler import app

# Reuse the field-config test's in-memory fake catalog repo + entry helper.
from sam.tests.test_field_config_endpoint import FakeCatalogRepository, _entry

_FULL_BODY = {
    "mail_enabled": True,
    "mail_local_part": "info",
    "mail_certified": True,
    "mail_domain": "h-dcn.nl",
    "mail_reply_to_default": "webmaster@h-dcn.nl",
    "consent_notice": {"version": "2026-01", "text": {"nl": "Tekst", "en": "Body"}},
}


@pytest.fixture()
def repo() -> FakeCatalogRepository:
    r = FakeCatalogRepository()
    r.add_type("h-dcn", _entry("h-dcn", "gewoon", order=10))
    r.add_type("other", _entry("other", "member", order=10))
    return r


# ---------------------------------------------------------------------------
# (1) Domain — MembershipService.get_field_config surfaces mail_config
# ---------------------------------------------------------------------------


class TestGetFieldConfigSurfacesMailConfig:
    def test_full_body_surfaces_when_provider_has_it(self, repo):
        """The authored config#mail body surfaces verbatim as `mail_config`."""
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            mail_config_provider=StaticMailConfigProvider({"h-dcn": _FULL_BODY}),
        )
        config = service.get_field_config("h-dcn")

        assert config["mail_config"] == _FULL_BODY
        # Critically, the SAM-only reply-to round-trips (the reported bug's field).
        assert config["mail_config"]["mail_reply_to_default"] == "webmaster@h-dcn.nl"

    def test_defaults_to_fail_closed_body_with_no_provider_wired(self, repo):
        """Fail-closed: a service built with NO mail-config provider reports the minimal body."""
        service = MembershipService(repo, overlay_provider=StaticOverlayProvider({}))
        config = service.get_field_config("h-dcn")

        assert config["mail_config"] == fail_closed_mail_config()
        assert config["mail_config"]["mail_enabled"] is False
        assert config["mail_config"]["mail_local_part"] == "noreply"
        assert "mail_reply_to_default" not in config["mail_config"]

    def test_mail_config_is_per_tenant(self, repo):
        """Resolved per verified tenant_id — no cross-tenant bleed."""
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            mail_config_provider=StaticMailConfigProvider({"h-dcn": _FULL_BODY}),
        )

        assert service.get_field_config("h-dcn")["mail_config"] == _FULL_BODY
        # 'other' has no entry → fail-closed minimal body.
        assert service.get_field_config("other")["mail_config"] == fail_closed_mail_config()

    def test_field_config_with_mail_config_is_json_serializable(self, repo):
        """The surfaced body keeps the payload pure-JSON (the edge json.dumps it)."""
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            mail_config_provider=StaticMailConfigProvider({"h-dcn": _FULL_BODY}),
        )
        dumped = json.dumps(service.get_field_config("h-dcn"))
        assert '"mail_reply_to_default": "webmaster@h-dcn.nl"' in dumped

    def test_mail_config_and_mail_enabled_both_surface_independently(self, repo):
        """`mail_enabled` (pivot gate) and `mail_config` (authoring read) coexist."""
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({}),
            mail_config_provider=StaticMailConfigProvider({"h-dcn": _FULL_BODY}),
        )
        config = service.get_field_config("h-dcn")
        # The dedicated gate flag is still present (its own provider, default fail-closed here).
        assert "mail_enabled" in config
        # The authoring body is present and carries its own mail_enabled.
        assert config["mail_config"]["mail_enabled"] is True


# ---------------------------------------------------------------------------
# (2) Edge provider seam — _ProjectionMailConfigProvider + the test override
# ---------------------------------------------------------------------------


class TestEdgeMailConfigProviderSeam:
    def test_provider_delegates_to_the_test_override_when_set(self, monkeypatch):
        """The edge provider honours the _MAIL_CONFIG_PROVIDER_OVERRIDE seam (no AWS)."""
        monkeypatch.setattr(
            app,
            "_MAIL_CONFIG_PROVIDER_OVERRIDE",
            StaticMailConfigProvider({"h-dcn": _FULL_BODY}),
        )
        provider = app._ProjectionMailConfigProvider()

        assert provider.get_mail_config("h-dcn") == _FULL_BODY
        # A tenant the override does not know → fail-closed minimal body.
        assert provider.get_mail_config("other") == fail_closed_mail_config()

    def test_default_edge_provider_is_wired_into_the_service(self):
        """The module-level mail-config provider satisfies the MailConfigProvider seam."""
        assert hasattr(app._MAIL_CONFIG_PROVIDER, "get_mail_config")
        assert callable(app._MAIL_CONFIG_PROVIDER.get_mail_config)
