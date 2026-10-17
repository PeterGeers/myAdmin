"""Applicant **locale** normalization + the record-persistence contract (R6b, D12; design seam — Phase 5).

The public application form offers the applicant a locale selection (``nl`` / ``en``) that drives
all **applicant-facing** copy — the form labels/choices (via the public field-config, R5.3) and the
applicant's confirmation email (R8a.2) — and is **persisted on the member record** so a later staff
reply, re-send, or confirmation re-render uses the same language (R6b.4). The STAFF notification's
language is deliberately NOT this value — it follows the recipient/tenant locale (R6b.5) and is a
separate concern handled by the notification path (Phase 6).

This module is the **single authority** for turning a client-supplied locale into a stored value.
It is kept PURE (no I/O, no globals) and module-neutral so every consumer calls the same function:

- :func:`normalize_locale` — coerce ANY client value (missing / blank / wrong-case / unsupported /
  non-string) to one of the supported locales, **defaulting AND falling back to ``nl``** and NEVER
  raising (R6b.1/R6b.2). ``create_application`` (task 2.2) calls this on the submitted ``locale``
  before persisting; the public field-config read (Phase 4) and the applicant confirmation render
  (Phase 6) call it on the stored value so a record written before this field existed still
  resolves to ``nl``.

Record-persistence contract (R6b.4, D12)
----------------------------------------
The normalized locale is stored as a **top-level string attribute** on the application member
record under the key :data:`LOCALE_RECORD_KEY` (``"locale"``) — a flat sibling of ``status`` /
``member_id``, NOT buried in a nested group, so the notification worker and any re-render read it
with a single top-level lookup. :func:`locale_record_patch` is the one place that produces that
``{"locale": <normalized>}`` fragment; ``create_application`` merges it into the record it writes
(this module intentionally does NOT open its own write path — it owns the value + its record key,
the create spine owns the single write, keeping the write in one place, steering 35). Reading the
stored value back (re-send / confirmation re-render) goes through :func:`locale_of_record`, which
re-normalizes so a missing / legacy / corrupted stored value still resolves to ``nl``.

Why normalize on read as well as write
--------------------------------------
Write-time normalization guarantees a freshly created record carries a supported value. Re-running
the same normalization on read makes the contract robust to records that predate this field (no
``locale`` key → ``nl``) and to any value that slipped in out-of-band — the applicant-facing copy
is NEVER driven by an unsupported locale, consistent with the fall-back-to-``nl`` guarantee.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "DEFAULT_LOCALE",
    "LOCALE_RECORD_KEY",
    "SUPPORTED_LOCALES",
    "locale_of_record",
    "locale_record_patch",
    "normalize_locale",
]

#: The supported applicant locales (R6b.1). ``nl`` first — it is the default/fallback.
SUPPORTED_LOCALES: tuple[str, ...] = ("nl", "en")

#: The default AND fallback locale: any missing / blank / unsupported value becomes ``nl`` (R6b.2).
DEFAULT_LOCALE = "nl"

#: The top-level member-record attribute the normalized locale is stored under (R6b.4, D12).
#: A flat sibling of ``status`` / ``member_id`` — read with one top-level lookup, never nested.
LOCALE_RECORD_KEY = "locale"


def normalize_locale(value: Any) -> str:
    """Return a supported applicant locale, defaulting AND falling back to ``nl`` (R6b.1/R6b.2).

    This is the SINGLE authority for coercing a client-supplied locale into a stored value. It is
    total and never raises: a missing, blank, non-string, wrong-case, or unsupported value all
    resolve to :data:`DEFAULT_LOCALE` (``nl``) — a fallback, not an error (R6b.2). A supported
    value is matched case- and whitespace-insensitively (``"EN"`` / ``" en "`` → ``"en"``) and
    returned in its canonical lower-case form.

    Pure: safe to call on submit (``create_application``, write side) and on read (public
    field-config + confirmation render), so the applicant-facing copy is never driven by an
    unsupported locale.
    """
    if not isinstance(value, str):
        return DEFAULT_LOCALE
    candidate = value.strip().lower()
    if candidate in SUPPORTED_LOCALES:
        return candidate
    return DEFAULT_LOCALE


def locale_record_patch(value: Any) -> dict[str, str]:
    """The ``{"locale": <normalized>}`` fragment to persist on the application record (R6b.4).

    The one place that produces the record's locale attribute: ``create_application`` merges this
    into the record it writes rather than stamping the key by hand, so the record key and its
    normalization stay single-sourced here. Always carries a supported value (normalized via
    :func:`normalize_locale`), so the stored record always holds ``nl`` or ``en``.
    """
    return {LOCALE_RECORD_KEY: normalize_locale(value)}


def locale_of_record(record: Mapping[str, Any] | None) -> str:
    """Read the persisted applicant locale back off a member record, defaulting to ``nl``.

    Re-normalizes the stored value (:func:`normalize_locale`) so a record with NO ``locale`` key
    (predates this field), or any out-of-band value, still resolves to a supported locale —
    the applicant confirmation re-render / staff-reply language is never an unsupported value
    (R6b.4). A ``None`` record (not found) resolves to the default.
    """
    if not isinstance(record, Mapping):
        return DEFAULT_LOCALE
    return normalize_locale(record.get(LOCALE_RECORD_KEY))
