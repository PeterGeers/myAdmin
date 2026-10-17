"""
Member Application Form — the **bilingual notification bodies** for the two offloaded jobs
(application-app task 6.3; R8.6/R8.6a/R8a, design §6 / seam e).

The public-intake notification sends TWO feature emails whose COPY is platform-owned, not a
tenant-authored mail template (unlike the pivot/analytics ``per_recipient`` sends, which merge a
tenant ``config#templates`` row). So this module is the single, PURE authority that renders them:

- the **STAFF** "new application" body (``member_application_staff``): a deep-link to the
  authenticated member detail (``/members/{member_id}``, R8b.1) + a neutral one-line ``DUP`` triage
  marker when the record was flagged a possible duplicate (R8.6a) — and **NO applicant PII** beyond
  a display name (R8.6). The applicant's data stays behind the deep-link / authentication. Rendered
  in the **recipient/tenant locale** (R6b.5), NOT the applicant's choice.
- the **APPLICANT** "application received" confirmation (``member_application_ack``): a copy of the
  applicant's OWN submitted data (their own data is not a leak, R8a.4), rendered in the
  **applicant's chosen locale** (R6b/R8a.2).

Both are authored **bilingual (nl/en)** here (R8/R8a) and selected by the resolved ``lang``. The
module is pure (no I/O, no globals) and module-neutral — it takes the job envelope the worker
already holds and returns ``(subject, body_html)``; the worker owns the SES send. Keeping the copy
here (rather than threading tenant template CRUD) matches the design's "render bilingual template"
seam and keeps the rendering unit-testable with no AWS.

Safety invariants this module enforces (so a mis-built envelope can never leak PII):
- the STAFF body NEVER embeds the applicant's email / address / submitted field values — only the
  deep-link, the display name, and the neutral duplicate marker (R8.6/R8.6a/R12.4);
- the STAFF duplicate marker is a NEUTRAL one-liner — it never names the matched member (R8.6a);
- the APPLICANT body embeds only the applicant's OWN ``submitted`` groups (R8a.4).
"""

from __future__ import annotations

from collections.abc import Mapping
from html import escape
from typing import Any

from sam.members.domain.application_notification import (
    JOB_KIND_APPLICANT,
    JOB_KIND_STAFF,
)
from sam.members.domain.applicant_locale import DEFAULT_LOCALE, normalize_locale

__all__ = [
    "MEMBER_DEEP_LINK_TEMPLATE",
    "render_application_message",
    "render_staff_message",
    "render_applicant_message",
]

#: The deep-link to the authenticated member detail the staff email targets (R8.6/R8b.1). A
#: relative path — the mail client resolves it against the app origin; it is a destination, not a
#: grant (opening it still requires Cognito sign-in + the capability check, R8b.2).
MEMBER_DEEP_LINK_TEMPLATE = "/members/{member_id}"

# ── bilingual copy (R8/R8a — authored nl/en, selected by the resolved lang) ───────────────

_STAFF_COPY: dict[str, dict[str, str]] = {
    "nl": {
        "subject": "Nieuwe aanmelding ontvangen",
        "subject_named": "Nieuwe aanmelding: {name}",
        "intro": "Er is een nieuwe aanmelding ontvangen ter beoordeling.",
        "review": "Bekijk en beoordeel de aanmelding:",
        "duplicate": "Let op: mogelijk bestaand lid — controleer voor goedkeuring.",
    },
    "en": {
        "subject": "New application received",
        "subject_named": "New application: {name}",
        "intro": "A new application has been received for review.",
        "review": "Review and approve the application:",
        "duplicate": "Note: possible existing member — review before approving.",
    },
}

_APPLICANT_COPY: dict[str, dict[str, str]] = {
    "nl": {
        "subject": "Bevestiging van je aanmelding",
        "intro": "Bedankt voor je aanmelding. We hebben de volgende gegevens ontvangen:",
        "closing": "We nemen je aanmelding in behandeling en nemen zo nodig contact met je op.",
    },
    "en": {
        "subject": "Confirmation of your application",
        "intro": "Thank you for your application. We received the following details:",
        "closing": "We will review your application and contact you if needed.",
    },
}


def render_application_message(
    kind: str, lang: str, envelope: Mapping[str, Any]
) -> tuple[str, str]:
    """Render ``(subject, body_html)`` for an application job of ``kind`` in ``lang`` (R8.6/R8a).

    Dispatches on the job ``kind`` (``member_application_staff`` / ``member_application_ack``) to
    the staff vs applicant renderer. ``lang`` is already resolved by the caller (the staff/tenant
    locale for staff, the applicant's chosen locale for the ack); it is re-normalized here so an
    unsupported value still yields a well-formed body (fallback ``nl``). An unknown ``kind`` is a
    programming fault — raise so the worker dead-letters it rather than sending blank copy.
    """
    normalized = normalize_locale(lang)
    if kind == JOB_KIND_STAFF:
        return render_staff_message(normalized, envelope)
    if kind == JOB_KIND_APPLICANT:
        return render_applicant_message(normalized, envelope)
    raise ValueError(f"unknown application message kind {kind!r}")


def render_staff_message(
    lang: str, envelope: Mapping[str, Any]
) -> tuple[str, str]:
    """The STAFF "new application" body — deep-link + neutral DUP marker, NO applicant PII (R8.6).

    Carries ONLY: a display name (the one applicant-identifying string, R8.6), the deep-link to
    ``/members/{member_id}`` (the full record is behind auth, R8b.1), and — when
    ``duplicate_suspected`` — a neutral one-line triage marker that NEVER names the matched member
    (R8.6a/R12.4). No email, no address, no submitted field values ever reach this body.
    """
    copy = _STAFF_COPY.get(lang, _STAFF_COPY[DEFAULT_LOCALE])
    display_name = _clean_str(envelope.get("applicant_display_name"))
    member_id = _clean_str(envelope.get("member_id"))

    subject = (
        copy["subject_named"].format(name=display_name) if display_name else copy["subject"]
    )

    parts: list[str] = [f"<p>{escape(copy['intro'])}</p>"]
    if display_name:
        parts.append(f"<p>{escape(display_name)}</p>")
    if bool(envelope.get("duplicate_suspected")):
        parts.append(f"<p><strong>{escape(copy['duplicate'])}</strong></p>")
    if member_id:
        link = escape(MEMBER_DEEP_LINK_TEMPLATE.format(member_id=member_id))
        parts.append(f'<p>{escape(copy["review"])} <a href="{link}">{link}</a></p>')
    return subject, "\n".join(parts)


def render_applicant_message(
    lang: str, envelope: Mapping[str, Any]
) -> tuple[str, str]:
    """The APPLICANT "application received" confirmation — embeds their OWN submitted data (R8a).

    Rendered in the applicant's chosen locale (R6b/R8a.2). Embeds a copy of the applicant's OWN
    ``submitted`` field groups (R8a.4 — their own data, not a leak) as a simple key/value list so
    the applicant has a record of what they sent. No deep-link (they have no account, R8a.6).
    """
    copy = _APPLICANT_COPY.get(lang, _APPLICANT_COPY[DEFAULT_LOCALE])
    submitted = envelope.get("submitted")

    parts: list[str] = [f"<p>{escape(copy['intro'])}</p>"]
    rows = _flatten_submitted(submitted) if isinstance(submitted, Mapping) else []
    if rows:
        parts.append("<ul>")
        parts.extend(
            f"<li>{escape(label)}: {escape(value)}</li>" for label, value in rows
        )
        parts.append("</ul>")
    parts.append(f"<p>{escape(copy['closing'])}</p>")
    return copy["subject"], "\n".join(parts)


def _flatten_submitted(submitted: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Flatten the applicant's submitted groups to ``[(dotted_key, value_str), …]`` for display.

    One level of nesting (``personal.first_name``) is enough for the field groups the record
    carries; a scalar top-level value is emitted under its own key. Values are stringified for a
    plain key/value confirmation list. Blank values are skipped so the confirmation stays tidy.
    Order follows the record's insertion order (groups, then fields) for a stable body.
    """
    rows: list[tuple[str, str]] = []
    for group_key, group_value in submitted.items():
        if isinstance(group_value, Mapping):
            for field_key, field_value in group_value.items():
                text = _value_str(field_value)
                if text:
                    rows.append((f"{group_key}.{field_key}", text))
        else:
            text = _value_str(group_value)
            if text:
                rows.append((str(group_key), text))
    return rows


def _value_str(value: Any) -> str:
    """Stringify a submitted value for the confirmation list (``""`` for None/blank/empty)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(_value_str(v) for v in value if _value_str(v))
    text = str(value).strip()
    return text


def _clean_str(value: Any) -> str:
    """Return a trimmed string, or ``""`` when absent / non-string / blank."""
    return value.strip() if isinstance(value, str) and value.strip() else ""
