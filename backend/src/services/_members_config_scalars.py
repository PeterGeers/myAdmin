"""Scalar ``members.*`` param validators: mail config, application params, page size.

Structural split out of ``members_config_validation.py`` (code-quality 2026-10-28
task 10). Holds the per-key validators for the non-overlay scalar params — the mail
sender config (``mail_domain`` / ``mail_local_part`` / ``mail_certified``), the Member
Application Form params (``application_scope_copy`` / ``application_consent_notice``), and
the ``default_page_size`` tenant default. ``members_config_validation`` re-exports these,
so the public import surface is unchanged. Behaviour is identical to the pre-split module.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from services._members_config_fields import MembersConfigError

# ── mail config validation (R4 / §5f — per-tenant From + certification gate) ──────────
#
# These three params feed the config#mail projection (design Data Models): the Members send
# path composes the envelope From as "<mail_local_part|noreply>@<mail_domain>" and reads
# mail_certified as the fail-closed pre-send gate. We validate the AUTHORED shape here so a
# malformed domain / local-part never reaches the projection (where it would silently produce
# a broken sender). All three are OPTIONAL params: an unset/empty value is accepted (the From
# simply cannot be composed until a domain is authored; mail_local_part defaults to "noreply"
# in the schema; mail_certified is absent → the pre-send gate fails closed, no send).

#: A bare DNS domain: one or more dot-separated labels, each 1–63 chars of letters/digits/
#: hyphens (not leading/trailing a hyphen), with a final alphabetic TLD label. No scheme, no
#: "@", no path, no whitespace — the From is composed from "<local_part>@<domain>".
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}$"
)

#: An email local-part token: letters/digits and the common unquoted-local-part punctuation,
#: no "@" and no whitespace. Kept conservative on purpose (generic addresses like "noreply",
#: "info", "onderhoud") — not the full RFC 5321 quoted-string grammar.
_LOCAL_PART_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+$")


def _is_blank(value: Any) -> bool:
    """A None or empty/whitespace-only string counts as 'unset' for an optional mail param."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_mail_domain(value: Any) -> None:
    """Fail fast if ``members.mail_domain`` is not a bare DNS domain (R4, §5f).

    Accepts an unset/empty value (optional param). Otherwise the value must be a string that
    is a bare domain (e.g. ``h-dcn.nl``) — no scheme, no ``@``, no path, no whitespace — since
    the send path composes the From as ``<mail_local_part|noreply>@<mail_domain>`` and never
    projects a literal address.

    Raises :class:`MembersConfigError` (``{"mail_domain": reason}``) on any violation.
    """
    if _is_blank(value):
        return
    if not isinstance(value, str):
        raise MembersConfigError({"mail_domain": "must be a string (a bare domain)"})
    domain = value.strip()
    if "@" in domain or "/" in domain or "://" in domain:
        raise MembersConfigError(
            {"mail_domain": "must be a bare domain (no '@', scheme or path)"}
        )
    if not _DOMAIN_RE.match(domain):
        raise MembersConfigError(
            {"mail_domain": f"{value!r} is not a valid domain (e.g. 'h-dcn.nl')"}
        )


def validate_mail_local_part(value: Any) -> None:
    """Fail fast if ``members.mail_local_part`` is not a single local-part token (R4, §5f).

    Accepts an unset/empty value (optional param — the schema default is ``noreply``).
    Otherwise the value must be a string with no ``@`` and no whitespace (e.g. ``info``,
    ``onderhoud``), since it becomes the part before ``@`` in the composed From.

    Raises :class:`MembersConfigError` (``{"mail_local_part": reason}``) on any violation.
    """
    if _is_blank(value):
        return
    if not isinstance(value, str):
        raise MembersConfigError({"mail_local_part": "must be a string"})
    local = value.strip()
    if "@" in local or any(ch.isspace() for ch in local):
        raise MembersConfigError(
            {
                "mail_local_part": "must be a single local-part token (no '@' or whitespace)"
            }
        )
    if not _LOCAL_PART_RE.match(local):
        raise MembersConfigError(
            {"mail_local_part": f"{value!r} is not a valid email local-part"}
        )


def validate_mail_certified(value: Any) -> None:
    """Fail fast if ``members.mail_certified`` is not a boolean (R4, §5f, Option B).

    Accepts an unset/None value (optional param → the pre-send gate fails closed, no send).
    Otherwise the value must be a real ``bool`` — the fail-closed pre-send certification gate
    reads it, so an ambiguous truthy string (``"false"``) must NOT be stored as if it were
    certified.

    Raises :class:`MembersConfigError` (``{"mail_certified": reason}``) on any violation.
    """
    if value is None:
        return
    if not isinstance(value, bool):
        raise MembersConfigError({"mail_certified": "must be a boolean (true/false)"})


# ── Member Application Form params on config#mail (application-app, task 8.2) ───────────
#
# Two per-tenant application params ride the SAME config#mail row as the sender config
# (design §7). We validate the AUTHORED shape here so a malformed value never reaches the
# projection. Both are OPTIONAL: an unset/None value is accepted (the scope-copy toggle
# fails closed to False in the builder; the consent notice is simply omitted from the row).
# The application Reply-To param is DROPPED (D24 — Reply-To is the all-scope Members_CRUD
# set, not configured), so there is no validator for it.


def validate_application_scope_copy(value: Any) -> None:
    """Fail fast if ``members.application_scope_copy`` is not a boolean (D9a, task 8.2).

    The OPTIONAL, tenant-gated "scope-matched copy" toggle (D9a/R8.3a). Accepts an
    unset/None value (optional param → the builder fails closed to ``False``, the D9
    all-scope-only default). Otherwise the value must be a real ``bool`` — the fail-closed
    scope-copy gate reads it, so an ambiguous truthy string (``"false"``) must NOT be stored
    as if it enabled the extra fan-out.

    Raises :class:`MembersConfigError` (``{"application_scope_copy": reason}``) on violation.
    """
    if value is None:
        return
    if not isinstance(value, bool):
        raise MembersConfigError(
            {"application_scope_copy": "must be a boolean (true/false)"}
        )


def validate_application_consent_notice(value: Any) -> None:
    """Fail fast if ``members.application_consent_notice`` is malformed (D26, task 8.2).

    The per-tenant, bilingual, VERSIONED consent/privacy notice (D26/R12.1a/R12.1c). Accepts
    an unset/None value (optional param → the builder omits ``consent_notice`` from the row;
    the platform MAY seed a default elsewhere, R12.1c). When authored, the value must be a
    well-formed notice so a broken one never projects:

    - a mapping (object) with a STABLE ``version`` id — a non-blank string (the per-revision
      id a stored consent references so a later revision never retroactively changes an
      existing record, R12.1a);
    - a ``text`` mapping of ``<locale> → <body>`` carrying at least one non-blank string body
      (the bilingual ``{nl, en}`` notice, R12.1c), every present body being a string.

    Raises :class:`MembersConfigError` (``{"application_consent_notice": reason}``) on any
    violation, surfacing the first structural problem found.
    """
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise MembersConfigError(
            {
                "application_consent_notice": (
                    "must be an object with a 'version' and a 'text' {nl,en} map"
                )
            }
        )

    version = value.get("version")
    if isinstance(version, bool) or not isinstance(version, (str, int)):
        raise MembersConfigError(
            {
                "application_consent_notice": (
                    "'version' must be a stable non-blank id (a string or int)"
                )
            }
        )
    if isinstance(version, str) and not version.strip():
        raise MembersConfigError(
            {"application_consent_notice": "'version' must be a non-blank id"}
        )

    text = value.get("text")
    if not isinstance(text, Mapping):
        raise MembersConfigError(
            {
                "application_consent_notice": (
                    "'text' must be a map of locale → notice body (e.g. {nl, en})"
                )
            }
        )
    non_blank_bodies = 0
    for locale, body in text.items():
        if not isinstance(body, str):
            raise MembersConfigError(
                {
                    "application_consent_notice": (
                        f"notice body for locale {locale!r} must be a string"
                    )
                }
            )
        if body.strip():
            non_blank_bodies += 1
    if non_blank_bodies == 0:
        raise MembersConfigError(
            {
                "application_consent_notice": (
                    "'text' must carry at least one non-blank locale body"
                )
            }
        )


# ── default_page_size validation (R2.1, R2.6 — a positive-int tenant DEFAULT) ──────────
#
# Phase 2 re-homes pagination (`view_contexts[*].page_size`) to ONE tenant-level scalar
# `members.default_page_size` — a DEFAULT, not a stored view object (steering 38 rule 3).
# The resolver's positive-integer guarantee (requirements Property 1) must hold at the
# SOURCE too: a non-positive or non-integer default is rejected here on the authoring
# (Flask writer) path, so an invalid default never reaches the projection. The param is
# OPTIONAL — an unset/None value is accepted (the table toolkit's own default applies).


def validate_default_page_size(value: Any) -> None:
    """Fail fast if ``members.default_page_size`` is not a positive integer (R2.1, R2.6).

    Accepts an unset/None value (optional param → the table toolkit's own default applies).
    Otherwise the value must be a positive ``int`` (> 0): a boolean, a float, a string, or a
    non-positive integer (0 or negative) is rejected, so the served tenant default can only
    ever be a positive rows-per-page — honouring the resolver's positive-integer guarantee at
    the authoring source. This is a tenant/field DEFAULT, not a stored view object
    (``38-sam-module-field-config.md`` rule 3).

    Raises :class:`MembersConfigError` (``{"default_page_size": reason}``) on any violation.
    """
    if value is None:
        return
    # bool is a subclass of int — reject it explicitly so True/False is never stored as 1/0.
    if isinstance(value, bool) or not isinstance(value, int):
        raise MembersConfigError({"default_page_size": "must be a positive integer"})
    if value <= 0:
        raise MembersConfigError(
            {"default_page_size": f"must be a positive integer (got {value})"}
        )
