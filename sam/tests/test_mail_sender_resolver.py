"""
SAM pytest for the :class:`MailSenderResolver` (mail spec Task 1.1; R4, R5, R8.1; design
"Pre-send certification resolver") — the storage-agnostic pre-send gate that resolves the active
tenant's usable From = ``<mail_local_part|noreply>@<mail_domain>`` from the projected
``config#mail`` row, OR returns a TYPED not-certified / not-enabled reason.

Phase 1 testing (tasks.md): "SAM pytest — From resolution (domain/local-part/default);
not-certified → typed refusal; fail-closed on absent flags." These drive the resolver through its
one required port — a static :class:`MailConfigReader` fake mirroring the projected
``config#mail`` reads (``get_mail_domain`` / ``get_mail_local_part`` / ``is_mail_certified`` /
``is_mail_enabled``) — with NO AWS/boto3 and NO live SES (Option B: the projected flag is the
truth source). Covered:

- usable-From composition — explicit local-part (``info@h-dcn.nl``) and the default
  (``noreply@...`` when the tenant authored none);
- the three fail-closed refusals, each a distinct typed reason — mail disabled, not certified,
  no domain (no From composable, never a guessed/foreign host — R4.2);
- tenancy — the resolution is bounded to the queried ``tenant_id`` (a second tenant's config
  never leaks into the first's From);
- the resolution-order short-circuit (disabled beats not-certified beats no-domain);
- Property 4 (fail-closed): across arbitrary projected states, a usable From is returned ONLY when
  mail is enabled AND certified AND a domain is projected — every other combination refuses.

Validates: Requirements R4, R5, R8.1
"""

from __future__ import annotations

import os
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.mail_sender_resolver import (
    DEFAULT_MAIL_LOCAL_PART,
    MailSenderResolver,
    NotCertifiedReason,
    SenderResolution,
)

TENANT = "h-dcn"
OTHER = "other-club"


# ── fake config reader (the one injected port) ──────────────────────────────────────────


class FakeMailConfigReader:
    """A tenant-scoped static :class:`MailConfigReader` mirroring the projected ``config#mail`` reads.

    Holds a ``{tenant_id: {domain, local_part, certified, enabled}}`` map and answers each accessor
    from it with the SAME fail-closed / empty-is-valid defaults the real
    :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader` applies: a
    tenant with no entry → ``None`` domain, default ``"noreply"`` local-part, ``False`` gates. So a
    cross-tenant leak is structurally impossible (an unseeded tenant resolves to the fail-closed
    defaults), and no AWS/boto3 is touched. It RECORDS every tenant it was asked for so a test can
    assert the resolver keyed strictly off the authoritative tenant.
    """

    def __init__(self):
        self._by_tenant: dict[str, dict] = {}
        self.seen_tenants: list[str] = []

    def put(
        self,
        tenant_id: str,
        *,
        domain: str | None = None,
        local_part: str | None = None,
        certified: bool = False,
        enabled: bool = False,
    ) -> None:
        self._by_tenant[tenant_id] = {
            "domain": domain,
            "local_part": local_part,
            "certified": certified,
            "enabled": enabled,
        }

    def _cfg(self, tenant_id: str) -> dict:
        self.seen_tenants.append(tenant_id)
        return self._by_tenant.get(tenant_id, {})

    def get_mail_domain(self, tenant_id):
        domain = self._cfg(tenant_id).get("domain")
        return domain if isinstance(domain, str) and domain else None

    def get_mail_local_part(self, tenant_id):
        local_part = self._cfg(tenant_id).get("local_part")
        if not isinstance(local_part, str) or not local_part:
            return DEFAULT_MAIL_LOCAL_PART
        return local_part

    def is_mail_certified(self, tenant_id):
        return self._cfg(tenant_id).get("certified") is True

    def is_mail_enabled(self, tenant_id):
        return self._cfg(tenant_id).get("enabled") is True


@pytest.fixture()
def reader() -> FakeMailConfigReader:
    return FakeMailConfigReader()


@pytest.fixture()
def resolver(reader) -> MailSenderResolver:
    # Option B: no live SES port on the send path (ses=None).
    return MailSenderResolver(reader)


# ── usable-From composition (R4.1) ──────────────────────────────────────────────────────


def test_resolve_certified_tenant_with_local_part_composes_that_from(reader, resolver):
    reader.put(TENANT, domain="h-dcn.nl", local_part="info", certified=True, enabled=True)

    result = resolver.resolve(TENANT)

    assert result.ok is True
    assert result.reason is None
    assert result.from_address == "info@h-dcn.nl"


def test_resolve_certified_tenant_without_local_part_defaults_to_noreply(reader, resolver):
    # No local_part authored → the generic default (design Data Models).
    reader.put(TENANT, domain="h-dcn.nl", local_part=None, certified=True, enabled=True)

    result = resolver.resolve(TENANT)

    assert result.ok is True
    assert result.from_address == "noreply@h-dcn.nl"


def test_resolve_blank_local_part_defaults_to_noreply(reader, resolver):
    # A blank/empty projected local-part must not yield an `@`-leading hostless address.
    reader.put(TENANT, domain="h-dcn.nl", local_part="", certified=True, enabled=True)

    result = resolver.resolve(TENANT)

    assert result.from_address == f"{DEFAULT_MAIL_LOCAL_PART}@h-dcn.nl"


# ── fail-closed refusals, each a distinct typed reason (R4.2 / R5.2 / Property 4) ─────────


def test_resolve_mail_disabled_refuses_with_mail_disabled_reason(reader, resolver):
    # Enabled=False — even though certified+domain are present, mail is off for the tenant.
    reader.put(TENANT, domain="h-dcn.nl", certified=True, enabled=False)

    result = resolver.resolve(TENANT)

    assert result.ok is False
    assert result.from_address is None
    assert result.reason is NotCertifiedReason.MAIL_DISABLED


def test_resolve_not_certified_refuses_with_not_certified_reason(reader, resolver):
    # Enabled but certified=False (the SES-verified onboarding flag is unset / lapsed).
    reader.put(TENANT, domain="h-dcn.nl", certified=False, enabled=True)

    result = resolver.resolve(TENANT)

    assert result.ok is False
    assert result.reason is NotCertifiedReason.NOT_CERTIFIED


def test_resolve_missing_domain_refuses_with_no_domain_reason(reader, resolver):
    # Enabled + certified but NO domain → no From composable; NEVER a guessed/foreign host (R4.2).
    reader.put(TENANT, domain=None, certified=True, enabled=True)

    result = resolver.resolve(TENANT)

    assert result.ok is False
    assert result.from_address is None
    assert result.reason is NotCertifiedReason.NO_DOMAIN


def test_resolve_unseeded_tenant_fails_closed(resolver):
    # A tenant with NO projected config#mail row at all → fail-closed (mail not enabled).
    result = resolver.resolve("never-onboarded")

    assert result.ok is False
    assert result.reason is NotCertifiedReason.MAIL_DISABLED


def test_resolve_blank_tenant_fails_closed_without_composing_hostless_from(resolver):
    # A blank tenant is an authz/programming fault — refuse, never compose a hostless address.
    result = resolver.resolve("")

    assert result.ok is False
    assert result.from_address is None
    assert result.reason is NotCertifiedReason.MAIL_DISABLED


# ── resolution-order short-circuit (disabled → not-certified → no-domain) ────────────────


def test_resolve_disabled_short_circuits_before_certified_and_domain(reader, resolver):
    # Everything wrong at once: the FIRST gate (enabled) wins the reason.
    reader.put(TENANT, domain=None, certified=False, enabled=False)

    assert resolver.resolve(TENANT).reason is NotCertifiedReason.MAIL_DISABLED


def test_resolve_not_certified_short_circuits_before_domain(reader, resolver):
    # Enabled, but not certified AND no domain: not-certified is reported before no-domain.
    reader.put(TENANT, domain=None, certified=False, enabled=True)

    assert resolver.resolve(TENANT).reason is NotCertifiedReason.NOT_CERTIFIED


# ── tenancy — bounded to the queried tenant (Property 3) ─────────────────────────────────


def test_resolve_is_bounded_to_the_queried_tenant(reader, resolver):
    # Two tenants, different domains. Resolving one NEVER uses the other's config.
    reader.put(TENANT, domain="h-dcn.nl", local_part="info", certified=True, enabled=True)
    reader.put(OTHER, domain="other.example", local_part="post", certified=True, enabled=True)

    assert resolver.resolve(TENANT).from_address == "info@h-dcn.nl"
    assert resolver.resolve(OTHER).from_address == "post@other.example"
    # Every read was keyed by a concrete tenant id (never a tenant-less lookup).
    assert set(reader.seen_tenants) <= {TENANT, OTHER}


def test_resolve_other_tenant_certified_does_not_certify_first(reader, resolver):
    # OTHER is fully certified; TENANT is not enabled. TENANT must still refuse (no leak).
    reader.put(OTHER, domain="other.example", certified=True, enabled=True)
    reader.put(TENANT, domain="h-dcn.nl", certified=True, enabled=False)

    assert resolver.resolve(TENANT).reason is NotCertifiedReason.MAIL_DISABLED


# ── SenderResolution invariant (exactly one of from/reason) ──────────────────────────────


def test_sender_resolution_rejects_both_from_and_reason():
    with pytest.raises(ValueError):
        SenderResolution(from_address="x@y.nl", reason=NotCertifiedReason.NO_DOMAIN)


def test_sender_resolution_rejects_neither_from_nor_reason():
    with pytest.raises(ValueError):
        SenderResolution(from_address=None, reason=None)


# ── Property 4: fail-closed across arbitrary projected states ────────────────────────────
#
# **Validates: Requirements 4.2, 5.1, 5.2** (design Property 4)


@given(
    enabled=st.booleans(),
    certified=st.booleans(),
    domain=st.one_of(st.none(), st.sampled_from(["h-dcn.nl", "club.example", "a.co"])),
    local_part=st.one_of(st.none(), st.sampled_from(["noreply", "info", "post", ""])),
)
def test_resolver_opens_only_on_enabled_and_certified_and_domain(
    enabled, certified, domain, local_part
):
    """A usable From is returned IFF enabled AND certified AND a domain is projected; else refused.

    The gate opens only on explicit projected truth across the whole state space — no combination
    of absent/false flags ever yields a sendable From, and a usable From always carries the
    projected domain as its host (never a guessed/foreign one — R4.2).
    """
    reader = FakeMailConfigReader()
    reader.put(
        TENANT, domain=domain, local_part=local_part, certified=certified, enabled=enabled
    )
    result = MailSenderResolver(reader).resolve(TENANT)

    should_send = enabled and certified and bool(domain)
    assert result.ok is should_send

    if should_send:
        expected_local = local_part if local_part else DEFAULT_MAIL_LOCAL_PART
        assert result.from_address == f"{expected_local}@{domain}"
        assert result.reason is None
    else:
        assert result.from_address is None
        assert result.reason is not None
        # The reason reflects the FIRST failed gate (enabled → certified → domain).
        if not enabled:
            assert result.reason is NotCertifiedReason.MAIL_DISABLED
        elif not certified:
            assert result.reason is NotCertifiedReason.NOT_CERTIFIED
        else:
            assert result.reason is NotCertifiedReason.NO_DOMAIN
