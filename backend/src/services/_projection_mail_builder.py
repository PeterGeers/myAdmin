"""Governance projection — the ``config#mail`` row builder (R0 + R4/R5; D9a/D26).

INTERNAL helper module of :mod:`services._projection_config_builders` — extracted from it
(code-quality file-length split, 2026-10-28) with **zero behaviour change**. Owns the mail
param-key constants, the consent-notice shaper, and :func:`build_config_mail_row`. Re-exported
from the facade :mod:`services._projection_config_builders` (and the public ``build_config_mail_row``
from :mod:`services.projection_sync`), so the public import surface is unchanged.

One-directional discipline (Property 1): the builder issues **zero** MySQL writes and does
**not** write the projection itself — it only READS via ``ParameterService`` and RETURNS the
item for the sole writer (:class:`services.projection_sync.ProjectionSync`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services import projection_schema as schema
from services._projection_config_common import (
    _MEMBERS_PARAM_NAMESPACE,
    _config_row_version,
)
from services.projection_builder import ProjectionItem

#: The single tenant-scope parameter key that holds the per-tenant "mail-enabled /
#: SES-certified" onboarding gate flag as a boolean (pivot-output-actions R0,
#: task 0.4). Authored by the tenant-admin module (``members.mail_enabled``, same
#: ``/api/tenant-admin/parameters`` surface as ``scope_dimensions`` etc.); read
#: here and shaped into the ``config#mail`` row's ``mail_enabled`` attribute — the
#: shape the SAM-plane projection reader (``projection_config_reader.is_mail_enabled``)
#: consumes. This builder only READS whatever value exists (Property 1,
#: one-directional).
_MAIL_ENABLED_PARAM_KEY = "mail_enabled"

#: The tenant's own mail domain (e.g. ``h-dcn.nl``), authored at onboarding as the
#: ``members.mail_domain`` param (task 0.1 schema) and projected into ``config#mail``.
#: The Members send path composes the envelope From as
#: ``<mail_local_part|noreply>@<mail_domain>`` — the domain is NEVER projected as a
#: literal address. Read-only here (Property 1).
_MAIL_DOMAIN_PARAM_KEY = "mail_domain"

#: The From local-part (e.g. ``info``, ``onderhoud``), authored as the optional
#: ``members.mail_local_part`` param. DEFAULT ``"noreply"`` when unset/blank — the
#: SAME default the SAM reader (``get_mail_local_part``) applies, kept in sync here.
_MAIL_LOCAL_PART_PARAM_KEY = "mail_local_part"

#: The onboarding-recorded SES-verified flag (``members.mail_certified``, design
#: "Option B"). The pre-send certification check reads this projected boolean and
#: fails CLOSED when it is absent/False (R5.2/Property 4) — same discipline as
#: ``mail_enabled``.
_MAIL_CERTIFIED_PARAM_KEY = "mail_certified"

#: The OPTIONAL tenant-authored Reply-To default for SCHEDULED / unattended sends
#: (``members.mail_reply_to_default``, spec 02 Task 5.1). A scheduled send has no invoking
#: user, so its Reply-To is this authored address, falling back to the composed From when it
#: is absent (an interactive send instead uses the invoking user's verified email at runtime).
#: Projected onto ``config#mail`` ONLY when authored as a non-blank string.
_MAIL_REPLY_TO_DEFAULT_PARAM_KEY = "mail_reply_to_default"

#: The default From local-part projected when a tenant has authored no (or a blank)
#: ``members.mail_local_part``. MUST match the SAM reader's ``_DEFAULT_MAIL_LOCAL_PART``
#: so builder and reader agree on the composed-From local-part.
_MAIL_LOCAL_PART_DEFAULT = "noreply"

#: Member Application Form (application-app D9a/R8.3a, task 8.2) — the OPTIONAL,
#: tenant-config-gated "scope-matched copy" toggle, authored as the boolean
#: ``members.application_scope_copy`` param and projected onto the SAME ``config#mail``
#: row the sender config rides (design §7). When True AND the applicant selected a scope
#: value on the form, the staff notification SHALL ALSO copy the ``Members_CRUD`` users
#: scoped to that value (ADDING to the all-scope recipients, never replacing — D9a). The
#: application Reply-To param is DROPPED (D24 — Reply-To is the all-scope ``Members_CRUD``
#: set, not configured). Fail-closed: only an explicit boolean ``True`` enables the copy;
#: any other/absent value projects ``False`` (the D9 all-scope-only default).
_APPLICATION_SCOPE_COPY_PARAM_KEY = "application_scope_copy"

#: Member Application Form (application-app D26/R12.1a/R12.1c, task 8.2) — the per-tenant,
#: bilingual, VERSIONED consent/privacy notice, authored as the
#: ``members.application_consent_notice`` param and projected onto the SAME ``config#mail``
#: row. Each tenant authors its OWN notice text ``{nl, en}`` with a STABLE ``version`` id per
#: revision (D26): the public field-config read (R5) serves the current text + version to the
#: form, and a stored consent references the exact version accepted (a later revision never
#: retroactively changes an existing record's recorded version). Projected ONLY when
#: well-formed (a non-blank ``version`` AND at least one non-blank locale text); otherwise the
#: attribute is OMITTED so an un-authored tenant projects a back-compatible row (the platform
#: MAY seed a default notice elsewhere — R12.1c / steering 38).
_APPLICATION_CONSENT_NOTICE_PARAM_KEY = "application_consent_notice"


def _resolve_application_consent_notice(raw: Any) -> dict[str, Any] | None:
    """Shape an authored ``members.application_consent_notice`` value for ``config#mail``.

    The per-tenant, bilingual, VERSIONED consent notice (application-app D26/R12.1a/R12.1c,
    task 8.2). Returns the projected shape ``{"version": <str>, "text": {<locale>: <str>, …}}``
    when the authored value is well-formed, else ``None`` so the ``config#mail`` row OMITS the
    attribute (an un-authored / malformed notice is simply absent — a back-compatible row for a
    tenant not using the application form; the platform MAY seed a default elsewhere, R12.1c).

    Well-formed (projected) requires BOTH:

    - a STABLE ``version`` id — a non-blank string (the stable per-revision id a stored consent
      references so a later revision never retroactively changes an existing record, R12.1a);
      a non-string version is coerced to its ``str`` only when it is a non-blank scalar id
      (int/str), never fabricated;
    - at least ONE non-blank locale text under ``text`` (the bilingual ``{nl, en}`` body, R12.1c).

    Degrades gracefully on projected config data (never raises): a non-mapping value, a blank /
    absent version, or an empty/blank ``text`` all collapse to ``None``. Only non-blank string
    locale texts survive into the projected ``text`` map (a blank/non-string entry is dropped),
    so the served notice body is always ``{str: str}``. The authoring-plane validator (task 8.3
    companion) rejects a malformed notice at Save; this is the symmetric read-side guard so a
    stray stored value never projects a broken notice.
    """
    if not isinstance(raw, Mapping):
        return None

    raw_version = raw.get("version")
    if isinstance(raw_version, bool):
        return None
    if isinstance(raw_version, str):
        version = raw_version.strip()
    elif isinstance(raw_version, int):
        version = str(raw_version)
    else:
        version = ""
    if not version:
        return None

    raw_text = raw.get("text")
    if not isinstance(raw_text, Mapping):
        return None
    text: dict[str, str] = {}
    for locale, body in raw_text.items():
        if (
            isinstance(locale, str)
            and locale.strip()
            and isinstance(body, str)
            and body.strip()
        ):
            text[locale] = body
    if not text:
        return None

    return {"version": version, "text": text}


def build_config_mail_row(
    tenant: Mapping[str, Any],
    parameter_service: Any,
) -> ProjectionItem | None:
    """Build the tenant-level ``config#mail`` projection item (R0 + R4/R5).

    Reads the tenant's per-tenant mail parameters from the tenant-scope parameter
    system (``ParameterService.get_param`` on the ``members`` namespace) and shapes
    them into the SINGLE ``config#mail`` row — the shape the SAM-plane projection
    reader (``projection_config_reader``: ``is_mail_enabled`` / ``get_mail_domain`` /
    ``get_mail_local_part`` / ``is_mail_certified``) consumes. The Members edge reads
    this projected row at request time to decide whether to offer the mail output
    actions and to resolve the per-tenant sender (R1–R5); it NEVER queries MySQL
    (ADR 0005/0006).

    The four projected attributes (design "Data Models", task 0.2):

    - ``mail_enabled`` (bool) — the onboarding "cleared to send" gate (R0).
    - ``mail_domain`` (str, optional) — the tenant's own mail domain (e.g.
      ``h-dcn.nl``); the send path composes From = ``<local_part>@<domain>``. The
      domain is NEVER projected as a literal address. Projected ONLY when authored as
      a non-empty string; omitted otherwise (there is no safe default for a domain —
      a guessed host would send from a foreign domain, the ``jabaki.nl`` regression,
      R4.2 — so the reader resolves an absent domain to ``None`` and refuses the send).
    - ``mail_local_part`` (str) — the From local-part (e.g. ``info``); DEFAULT
      ``"noreply"`` when unset/blank, matching the SAM reader's default so builder and
      reader compose the SAME From.
    - ``mail_certified`` (bool) — the onboarding-recorded SES-verified flag ("Option
      B"); the pre-send check reads it and fails CLOSED when absent/False (R5.2).

    Two Member Application Form attributes ride this SAME row (application-app task 8.2;
    the application Reply-To param is DROPPED — D24):

    - ``application_scope_copy`` (bool, D9a) — the OPTIONAL tenant-gated "scope-matched
      copy" toggle; fail-closed ``False`` (only an explicit ``True`` enables the copy), so
      an un-authored tenant keeps the D9 all-scope-only recipients.
    - ``consent_notice`` ({version, text:{nl,en}}, D26) — the per-tenant, VERSIONED,
      bilingual consent/privacy notice; OMITTED when un-authored/malformed (a tenant not
      using the application form projects a back-compatible row).

    One-directional discipline (Property 1): this builder issues **zero** MySQL
    writes and does **not** write the projection itself — it only READS via
    ``ParameterService`` (which resolves the tenant-scope rows read-only) and
    RETURNS the item for :class:`ProjectionSync` (the sole writer), mirroring the
    sibling ``config#scope`` / ``config#fields`` builders.

    Fail-closed defaults (R0/R4/R5): a tenant that has authored no parameter — or a
    malformed value — yields a safe, non-permissive row. ``mail_enabled`` and
    ``mail_certified`` collapse to ``False`` for any non-boolean-``True`` value (only
    an explicit ``True`` opens either gate; the absence NEVER opens it);
    ``mail_local_part`` collapses to ``"noreply"``; ``mail_domain`` is omitted when
    absent/blank (no guessed host). Returning the row (rather than ``None``) keeps the
    projection self-describing — a present-but-disabled gate is distinct from "not yet
    projected".

    Args:
        tenant: The tenant row. Must carry ``administration`` (or ``tenant_id``)
            — the partition key / tenancy boundary (R5.4).
        parameter_service: A ``ParameterService`` (or anything exposing
            ``get_param(namespace, key, tenant=...)``). Read-only.

    Returns:
        The ``config#mail`` :class:`ProjectionItem` for this tenant. ``None`` is
        never returned for a present tenant — an un-configured tenant still gets a
        well-formed, fail-closed row.

    Raises:
        ValueError: The tenant is missing its ``administration``/``tenant_id`` key.
    """
    tenant_id = tenant.get("administration") or tenant.get(schema.PARTITION_KEY_ATTR)
    if not tenant_id:
        raise ValueError(
            "tenant is missing its 'administration'/'tenant_id' key — a blank "
            "partition key is a cross-tenant hazard (R5.4)"
        )

    raw_flag = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _MAIL_ENABLED_PARAM_KEY,
        tenant=tenant_id,
    )
    raw_domain = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _MAIL_DOMAIN_PARAM_KEY,
        tenant=tenant_id,
    )
    raw_local_part = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _MAIL_LOCAL_PART_PARAM_KEY,
        tenant=tenant_id,
    )
    raw_certified = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _MAIL_CERTIFIED_PARAM_KEY,
        tenant=tenant_id,
    )
    raw_reply_to_default = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _MAIL_REPLY_TO_DEFAULT_PARAM_KEY,
        tenant=tenant_id,
    )
    raw_scope_copy = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _APPLICATION_SCOPE_COPY_PARAM_KEY,
        tenant=tenant_id,
    )
    raw_consent_notice = parameter_service.get_param(
        _MEMBERS_PARAM_NAMESPACE,
        _APPLICATION_CONSENT_NOTICE_PARAM_KEY,
        tenant=tenant_id,
    )

    # Fail-closed: only an explicit boolean ``True`` opens a gate. Any other value —
    # absent (None), a stray string, a number — collapses to False, so a
    # malformed/absent gate can never silently permit sending (R0/R5.2/Property 4).
    mail_enabled = raw_flag is True
    mail_certified = raw_certified is True

    # D9a scope-copy toggle: fail-closed like the gate flags — only an explicit boolean
    # ``True`` enables the optional scope-matched copy; any other/absent value projects
    # ``False`` (the D9 all-scope-only default), so a malformed value never silently
    # fans the notification out to scope-limited recipients.
    application_scope_copy = raw_scope_copy is True

    # Local-part: optional with a generic default. A non-string/blank value falls back
    # to ``noreply`` so a From is always composable from a usable domain.
    if isinstance(raw_local_part, str) and raw_local_part:
        mail_local_part = raw_local_part
    else:
        mail_local_part = _MAIL_LOCAL_PART_DEFAULT

    attributes: dict[str, Any] = {
        "mail_enabled": mail_enabled,
        "mail_local_part": mail_local_part,
        "mail_certified": mail_certified,
        # Member Application Form (D9a): the scope-copy toggle always rides the row as a
        # fail-closed boolean (present-but-False is distinct from "not projected"), the
        # SAME discipline as the mail gate flags.
        "application_scope_copy": application_scope_copy,
    }

    # Domain: NO safe default (a guessed host = a foreign-sender leak, R4.2). Project
    # it ONLY when authored as a non-empty string; otherwise omit it so the reader
    # resolves ``None`` and the pre-send resolver refuses the send (fail-closed).
    if isinstance(raw_domain, str) and raw_domain:
        attributes["mail_domain"] = raw_domain

    # Reply-To default (Task 5.1): the SCHEDULED/unattended-send Reply-To. Project ONLY when
    # authored as a non-blank string; omit otherwise so the send path falls back to the From
    # address (an interactive send uses the invoking user's verified email at runtime instead).
    if isinstance(raw_reply_to_default, str) and raw_reply_to_default.strip():
        attributes["mail_reply_to_default"] = raw_reply_to_default

    # Member Application Form (D26): the versioned bilingual consent notice is projected
    # ONLY when well-formed (non-blank version + at least one locale text); otherwise it
    # is OMITTED so a tenant that authored none projects a back-compatible row (the public
    # field-config read then serves no tenant notice, falling back to a platform seed if any).
    consent_notice = _resolve_application_consent_notice(raw_consent_notice)
    if consent_notice is not None:
        attributes["consent_notice"] = consent_notice

    return ProjectionItem(
        tenant_id=tenant_id,
        sort_key=schema.build_sort_key(
            schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_MAIL
        ),
        # config#mail is driven by SEVEN params — the four mail params + the NEW
        # mail_reply_to_default (Task 5.1) + the two Member Application Form params (the D9a
        # scope-copy toggle + the D26 consent notice) that ride this row — so an edit to ANY
        # must bump the row (version-bump trap fix): the version is the max of their per-param
        # revisions, falling back to the tenant row only when none is authored.
        version=_config_row_version(
            tenant,
            parameter_service,
            tenant_id,
            (
                _MAIL_ENABLED_PARAM_KEY,
                _MAIL_DOMAIN_PARAM_KEY,
                _MAIL_LOCAL_PART_PARAM_KEY,
                _MAIL_CERTIFIED_PARAM_KEY,
                _MAIL_REPLY_TO_DEFAULT_PARAM_KEY,
                _APPLICATION_SCOPE_COPY_PARAM_KEY,
                _APPLICATION_CONSENT_NOTICE_PARAM_KEY,
            ),
        ),
        attributes=attributes,
    )
