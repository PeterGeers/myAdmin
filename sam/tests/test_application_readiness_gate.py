"""
application-app task 4.2 — tests for the tenant-READINESS GATE (D15/R5.4/R9.4, seam a/c).

A tenant may accept applications ONLY when it is mail-send-ready: its projected ``config#mail``
row must be ``mail_certified`` AND carry a ``mail_domain``. The application form triggers emails,
so an un-ready tenant must NOT expose the form and must NOT be able to land a record. The gate
lives on :class:`~sam.members.domain.application_service.ApplicationService` (the public-intake
facade) and wraps BOTH public operations via the ONE shared
:func:`~sam.members.domain.application_readiness.is_send_ready` predicate, so the form read and
the submit can never disagree:

1. **Form read gated (R5.4).** ``get_public_field_config`` on an un-ready tenant raises the
   NEUTRAL :class:`~sam.members.domain.application_readiness.ApplicationNotAvailable` (the edge's
   409) instead of returning a schema — the form does not open.
2. **Submit re-checks (R9.4 defense-in-depth).** ``create_application`` on an un-ready tenant is
   REFUSED with the SAME neutral error and NO record is written / nothing enqueued — even though a
   direct POST never loaded the form.
3. **Neutral — no mail-config leak (D15).** The refusal carries ONLY the stable
   ``errors.application.notAvailable`` code; it never names ``mail_domain`` / ``mail_certified``,
   never distinguishes not-certified from no-domain, and is distinct from the 404 (unknown slug)
   and 422 (validation).
4. **A send-ready tenant passes** both the read (returns a schema) and the submit (lands a
   ``status=application`` record).

The readiness facts are supplied via a
:class:`~sam.members.domain.application_readiness.StaticMailReadinessProvider` (the in-memory
reference seam, fail-closed like the DynamoDB reader). The wrapped engine + overlay + fake repo
are reused from the task-2.2 / task-4.1 tests so these assert ONLY the gate behaviour.

5. **A send-ready schema still carries the full contract (R14.16-partial).** The attrs + enum
   subset + ``format`` token survive the gate on the PUBLIC read path the frontend consumes.

Validates: Requirements R5.4, R9.4, R14.16, R14.17
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.application_readiness import (
    ApplicationNotAvailable,
    StaticMailReadinessProvider,
    is_send_ready,
)
from sam.members.domain.application_service import ApplicationService
from sam.members.domain.error_codes import APPLICATION_NOT_AVAILABLE
from sam.members.domain.field_resolver import StaticOverlayProvider
from sam.members.domain.membership_service import MembershipService

# Reuse the task-2.2 fake repo (member store + first-wins session claim + catalog surface), its
# overlay (fields on the public form), the flat-submission + affirmative-consent helpers, and the
# shared catalog-entry factory.
from sam.tests.test_create_application import (
    _AFFIRMATIVE_CONSENT,
    _ApplicationRepo,
    _flat_submission,
    _overlay_public_form,
)
from sam.tests.test_field_config_endpoint import _entry

TENANT = "h-dcn"

#: A send-ready config#mail: certified AND a projected domain.
_READY = {TENANT: (True, "h-dcn.nl")}
#: Not-ready variants: uncertified (with a domain), certified-but-no-domain, and wholly absent.
_UNCERTIFIED = {TENANT: (False, "h-dcn.nl")}
_NO_DOMAIN = {TENANT: (True, None)}
_NO_DOMAIN_BLANK = {TENANT: (True, "   ")}


def _engine() -> MembershipService:
    """The wrapped authoritative engine (catalog + overlay), as the task-2.2/4.1 tests build it."""
    repo = _ApplicationRepo()
    repo.add_type(TENANT, _entry(TENANT, "gewoon", order=10))
    repo.add_type(TENANT, _entry(TENANT, "erelid", order=20))
    return MembershipService(
        repo, overlay_provider=StaticOverlayProvider({TENANT: _overlay_public_form()})
    )


def _facade(readiness_map) -> ApplicationService:
    """An :class:`ApplicationService` over a fresh engine with the given readiness config."""
    return ApplicationService(
        _engine(),
        mail_readiness_provider=StaticMailReadinessProvider(readiness_map),
    )


# ── 0. the predicate itself (certified AND domain present) ────────────────────────────


class TestIsSendReadyPredicate:
    def test_ready_only_when_certified_and_domain_present(self):
        assert is_send_ready(StaticMailReadinessProvider(_READY), TENANT) is True

    @pytest.mark.parametrize(
        "cfg", [_UNCERTIFIED, _NO_DOMAIN, _NO_DOMAIN_BLANK, {}], ids=
        ["uncertified", "no-domain", "blank-domain", "absent-row"],
    )
    def test_not_ready_when_a_fact_is_missing(self, cfg):
        # Fail-closed: any missing fact (uncertified / no-domain / blank-domain / absent) → False.
        assert is_send_ready(StaticMailReadinessProvider(cfg), TENANT) is False


# ── 1. form read is gated (R5.4) ──────────────────────────────────────────────────────


class TestFormReadGated:
    def test_uncertified_tenant_read_refuses_with_not_available(self):
        facade = _facade(_UNCERTIFIED)
        with pytest.raises(ApplicationNotAvailable):
            facade.get_public_field_config(TENANT)

    def test_no_domain_tenant_read_refuses(self):
        facade = _facade(_NO_DOMAIN)
        with pytest.raises(ApplicationNotAvailable):
            facade.get_public_field_config(TENANT)

    def test_absent_config_fails_closed(self):
        # No config#mail projected at all → not ready (the default fail-closed provider).
        facade = ApplicationService(_engine())  # no provider → empty, fail-closed
        with pytest.raises(ApplicationNotAvailable):
            facade.get_public_field_config(TENANT)

    def test_send_ready_tenant_read_returns_the_schema(self):
        facade = _facade(_READY)
        schema = facade.get_public_field_config(TENANT)
        assert schema["tenant_id"] == TENANT
        assert isinstance(schema["fields"], list) and schema["fields"]


# ── 2. submit RE-CHECKS readiness — refuse, NO record (R9.4 defense-in-depth) ─────────


class TestSubmitReChecks:
    def test_uncertified_submit_is_refused_and_writes_no_record(self):
        engine = _engine()
        facade = ApplicationService(
            engine, mail_readiness_provider=StaticMailReadinessProvider(_UNCERTIFIED)
        )
        with pytest.raises(ApplicationNotAvailable):
            facade.create_application(
                TENANT, _flat_submission(), session_key="s1", consent=_AFFIRMATIVE_CONSENT
            )
        # NO record written and NO session claimed — the write path was never reached (R9.4).
        assert engine._repo.members == {}
        assert engine._repo._sessions == {}

    def test_no_domain_submit_is_refused_and_writes_no_record(self):
        engine = _engine()
        facade = ApplicationService(
            engine, mail_readiness_provider=StaticMailReadinessProvider(_NO_DOMAIN)
        )
        with pytest.raises(ApplicationNotAvailable):
            facade.create_application(
                TENANT, _flat_submission(), session_key="s1", consent=_AFFIRMATIVE_CONSENT
            )
        assert engine._repo.members == {}

    def test_send_ready_submit_lands_a_status_application_record(self):
        engine = _engine()
        facade = ApplicationService(
            engine, mail_readiness_provider=StaticMailReadinessProvider(_READY)
        )
        rec = facade.create_application(
            TENANT, _flat_submission(), session_key="s1", consent=_AFFIRMATIVE_CONSENT
        )
        assert rec["membership"]["status"] == "application"
        # the record actually persisted on the ready path.
        assert len(engine._repo.members) == 1


# ── 3. the refusal is NEUTRAL — no mail-config leak (D15) ─────────────────────────────


class TestNeutralNoLeak:
    def test_code_is_the_stable_neutral_signal(self):
        facade = _facade(_UNCERTIFIED)
        with pytest.raises(ApplicationNotAvailable) as exc:
            facade.get_public_field_config(TENANT)
        # A stable request-level code (distinct from 404 unknown-slug / 422 validation).
        assert exc.value.code == APPLICATION_NOT_AVAILABLE == "errors.application.notAvailable"

    @pytest.mark.parametrize("cfg", [_UNCERTIFIED, _NO_DOMAIN], ids=["uncertified", "no-domain"])
    def test_message_and_code_leak_no_mail_config(self, cfg):
        # The neutral error never names the mail config nor WHICH fact is missing — a tenant's
        # mail posture must not be probeable from the public surface (D15).
        facade = _facade(cfg)
        with pytest.raises(ApplicationNotAvailable) as exc:
            facade.get_public_field_config(TENANT)
        blob = f"{exc.value.code} {exc.value}".lower()
        for leaked in ("mail_domain", "mail_certified", "domain", "certif", "ses", "sender"):
            assert leaked not in blob

    def test_uncertified_and_no_domain_are_indistinguishable(self):
        # The two not-ready reasons must surface the IDENTICAL neutral signal (no oracle).
        a = _facade(_UNCERTIFIED)
        b = _facade(_NO_DOMAIN)
        with pytest.raises(ApplicationNotAvailable) as exc_a:
            a.get_public_field_config(TENANT)
        with pytest.raises(ApplicationNotAvailable) as exc_b:
            b.get_public_field_config(TENANT)
        assert exc_a.value.code == exc_b.value.code
        assert str(exc_a.value) == str(exc_b.value)


# ── 4. send-ready schema still CARRIES the application attrs + subset + format ─────────


class TestSendReadySchemaCarriesContract:
    """The gated PUBLIC read path (what the frontend actually consumes) carries the full renderer
    contract on a send-ready tenant (R14.16-partial / R5.3).

    The per-field contract assertions in ``test_public_field_config.py`` (TestFieldContract /
    TestApplicationSubset) pin the RAW engine read. These pin the SAME application attrs + enum
    SUBSET + ``format`` token survive the readiness gate — i.e. the schema the public edge/Phase-9
    Yup generator reads through ``ApplicationService.get_public_field_config`` on a send-ready
    tenant is the full contract, not a gate-narrowed shape. Uses the richer task-4.1 overlay
    (required/subset/format carriers), which the task-2.2 gate overlay deliberately lacks.
    """

    def _ready_facade(self) -> ApplicationService:
        # The task-4.1 overlay carries application_required + application_choices + format; the
        # task-2.2 _overlay_public_form (imported above for the submit tests) does NOT, so build a
        # dedicated engine here with the field-config contract overlay.
        from sam.tests.test_public_field_config import _overlay_public_form as _contract_overlay

        repo = _ApplicationRepo()
        repo.add_type(TENANT, _entry(TENANT, "gewoon", order=10))
        repo.add_type(TENANT, _entry(TENANT, "erelid", order=20))
        engine = MembershipService(
            repo, overlay_provider=StaticOverlayProvider({TENANT: _contract_overlay()})
        )
        return ApplicationService(
            engine, mail_readiness_provider=StaticMailReadinessProvider(_READY)
        )

    def test_gated_schema_carries_application_required_flag(self):
        fields = {f["key"]: f for f in self._ready_facade().get_public_field_config(TENANT)["fields"]}
        # application-required survives the gate as `required` (R4b.6), NOT the staff flag.
        assert fields["first_name"]["required"] is True
        assert fields["nickname"]["required"] is False

    def test_gated_schema_carries_the_enum_subset(self):
        fields = {f["key"]: f for f in self._ready_facade().get_public_field_config(TENANT)["fields"]}
        # the application SUBSET survives the gate (R4a.2): shirt_size exposes only m/l.
        assert fields["shirt_size"]["options"] == ["m", "l"]
        membership_values = [o["value"] for o in fields["membership_type"]["options"]]
        assert membership_values == ["gewoon"]

    def test_gated_schema_carries_the_format_token(self):
        fields = {f["key"]: f for f in self._ready_facade().get_public_field_config(TENANT)["fields"]}
        # the FieldFormat token survives the gate (R7.1) so the Yup generator can bind it.
        assert fields["email"]["format"] == {"checker": "EMAIL", "params": {}}
        assert "format" not in fields["nickname"]
