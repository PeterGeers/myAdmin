"""
spec 02 Task 5.3 — **Property 6: Invoice-SES-untouched invariant** (Requirements 15.4, 15.5).

The Members ``config#mail`` cutover (SAM-owned write path + the per-tenant sender fields +
``mail_reply_to_default``) is a SEPARATE concern from the INVOICE sender SES verification path
(``SenderSettingsTab`` → ``verificationApi`` → the Flask ``email_verification_service`` / SES
``VerifyEmailIdentity`` flow). The two share no dataset and no code path:

- Members mail config is authored through ``PUT /members/config/mail`` → the SAM
  ``ConfigWriteService`` → ``MembersConfigWriteRepository`` → the ``config#mail`` DynamoDB row,
  and read through ``MembersProjectionReader`` + resolved by ``MailSenderResolver``.
- Invoice SES verification is the Flask-plane ``email_verification_service`` (a DIFFERENT service,
  a DIFFERENT table, a DIFFERENT API surface ``/api/.../verification``), surfaced by the frontend
  ``SenderSettingsTab`` via ``verificationApi`` — entirely on the Flask plane.

This test pins the structural isolation on the SAM side: the Members mail write/read/resolve
modules name NOTHING from the invoice SES verification path (no import, no symbol reference). The
planes are physically disjoint (SAM package vs Flask ``services``), so the cutover cannot alter
the invoice SES behaviour — the invariant is enforced by construction, and this test guards it
against a future accidental coupling. The frontend leg (``SenderSettingsTab`` keeps using
``verificationApi``, never ``membersConfigService``) is pinned in the frontend suite once the mail
save is repointed (Task 5.6/5.7).

Validates: Requirements 15.4, 15.5
"""

from __future__ import annotations

import inspect

from sam.members.domain import (
    config_write_service,
    execute_and_deliver,
    mail_sender_resolver,
)
from sam.members.repository import (
    projection_config_reader,
    projection_config_write_repository,
)

# Tokens that would betray a coupling to the INVOICE sender-SES verification path. If any Members
# mail module ever imported or referenced these, the "untouched" invariant would be at risk.
_INVOICE_SES_TOKENS = (
    "email_verification_service",
    "EmailVerificationService",
    "verificationApi",
    "verify_email_identity",
    "VerifyEmailIdentity",
    "get_verified_sender",
    "resend_verification",
    "update_sender_email",
    "sender-settings",
    "SenderSettingsTab",
)

#: Every SAM Members module that participates in the config#mail write/read/resolve/send path.
_MEMBERS_MAIL_MODULES = (
    config_write_service,
    execute_and_deliver,
    mail_sender_resolver,
    projection_config_reader,
    projection_config_write_repository,
)


def test_members_mail_modules_name_nothing_from_the_invoice_ses_path():
    """No Members mail module references any invoice-SES-verification symbol (Property 6).

    A pure source scan: the config#mail write service, the write repository, the reader, the
    sender resolver, and the execute-and-deliver send path must contain NONE of the invoice SES
    verification tokens. (The Members sender is resolved purely from the projected ``config#mail``
    row — there is no live SES identity call and no reach into the invoice verification service.)
    """
    offenders: list[str] = []
    for module in _MEMBERS_MAIL_MODULES:
        src = inspect.getsource(module)
        for token in _INVOICE_SES_TOKENS:
            if token in src:
                offenders.append(f"{module.__name__} references {token!r}")
    assert not offenders, (
        "Invoice-SES-untouched invariant VIOLATED (Property 6, R15.4/15.5) — a Members mail "
        "module now couples to the invoice SES verification path: "
        + "; ".join(offenders)
    )


def test_members_mail_modules_do_not_import_flask_email_verification():
    """Belt-and-suspenders: none of the Members mail modules imports the Flask invoice-SES service
    module object (an import would surface it in the module namespace)."""
    for module in _MEMBERS_MAIL_MODULES:
        names = set(vars(module))
        assert "email_verification_service" not in names, (
            f"{module.__name__} imported the Flask invoice-SES service — the Members mail cutover "
            "must not touch the invoice SES path (R15.4/15.5)."
        )
        assert "EmailVerificationService" not in names, (
            f"{module.__name__} imported EmailVerificationService — invoice-SES coupling (R15.4)."
        )
