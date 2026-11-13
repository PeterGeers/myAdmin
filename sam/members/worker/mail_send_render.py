"""Template rendering, attachments and export shaping.

Part of MailSendWorker (task 7).
"""

from __future__ import annotations

import csv
import io
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

from sam.members.domain.analytics_set import (
    DELIVERY_MODE_PER_RECIPIENT,
    DELIVERY_MODE_TO_FIXED,
)
from sam.members.domain.applicant_locale import DEFAULT_LOCALE, normalize_locale
from sam.members.domain.application_messages import render_application_message
from sam.members.domain.application_notification import (
    JOB_KIND_STAFF,
)

logger = logging.getLogger(__name__)

from ._mail_send_shared import (
    DEFAULT_EXPORT_FILENAME,
    DEFAULT_EXPORT_SUBJECT,
    MailSendPermanent,
)


class MailRenderMixin:
    """Template rendering, attachments and export shaping."""

    def _render(
        self, envelope: Mapping[str, Any], mode: str, recipients: Sequence[str]
    ) -> tuple[str, str, list[dict[str, Any]] | None]:
        """Render the subject + body + any attachment for the job's mode.

        - ``per_recipient``: mail-merge the ``template_id`` with the job's ``merge_values`` (one
          recipient). The merge happens on-plane (never an AI prompt) via the template service's
          ``render_for_recipient``.
        - ``to_fixed``: build the attachment (``csv`` / ``pdf_labels``) from the job's ``rows`` +
          an optional covering-template body (merged with no per-recipient values — a static
          covering mail).
        """
        if mode == DELIVERY_MODE_PER_RECIPIENT:
            return self._render_per_recipient(envelope)
        if mode == DELIVERY_MODE_TO_FIXED:
            return self._render_to_fixed(envelope)
        raise MailSendPermanent(
            f"job {envelope.get('job_id')!r} has unknown delivery mode {mode!r}"
        )

    def _render_per_recipient(
        self, envelope: Mapping[str, Any]
    ) -> tuple[str, str, None]:
        template_id = envelope.get("template_id")
        merge_values = envelope.get("merge_values") or {}
        if not isinstance(merge_values, Mapping):
            merge_values = {}
        if not template_id:
            raise MailSendPermanent(
                f"per_recipient job {envelope.get('job_id')!r} carries no template_id"
            )
        if self._templates is None:
            raise MailSendPermanent(
                "per_recipient render requires a template service (none wired)"
            )
        lang = str(envelope.get("lang") or self._default_lang)
        rendered = self._templates.render_for_recipient(
            self._require(envelope, "tenant_id"),
            str(template_id),
            lang,
            dict(merge_values),
        )
        return rendered.subject, rendered.body_html, None

    def _render_to_fixed(
        self, envelope: Mapping[str, Any]
    ) -> tuple[str, str, list[dict[str, Any]] | None]:
        rows = envelope.get("rows") or []
        rows = [dict(r) for r in rows if isinstance(r, Mapping)]
        attachment = envelope.get("attachment")
        tenant_id = self._require(envelope, "tenant_id")

        # Export naming (R5.2/5.3/5.5, task 6.3). The tenant + pivot DISPLAY names ride the
        # envelope (task 6.1 stamped them from the verified context) — opaque `tenant_id` /
        # `set_id` are not human-readable. Compose the attachment filename and the default
        # pivot-export subject from them via the shared PURE helpers (task 6.2), which encode the
        # `{Tenant}-{Pivot}.csv` / `{Tenant} - {Pivot}` rule and already handle the backward-compat
        # fallback (blank/absent names → export.csv / generic subject) for older in-flight jobs.
        tenant_name = envelope.get("tenant_name")
        pivot_name = envelope.get("pivot_name")
        export_name = _export_file_name(tenant_name, pivot_name)

        # Default pivot-export subject = tenant prefix + pivot name. A covering TEMPLATE subject
        # (when a `template_id` is supplied) still takes precedence for the body below — the
        # composed name is only the default when no covering template overrides it.
        subject = _export_subject(tenant_name, pivot_name)
        body_html = ""
        template_id = envelope.get("template_id")
        if template_id and self._templates is not None:
            lang = str(envelope.get("lang") or self._default_lang)
            rendered = self._templates.render_for_recipient(
                tenant_id, str(template_id), lang, {}
            )
            subject, body_html = rendered.subject, rendered.body_html

        attachments: list[dict[str, Any]] | None = None
        if isinstance(attachment, Mapping):
            kind = str(attachment.get("kind") or "")
            built = self._build_attachment(
                kind, rows, attachment.get("label_options"), export_name=export_name
            )
            if built is not None:
                attachments = [built]
        return subject, body_html, attachments

    def _render_application(
        self, envelope: Mapping[str, Any], kind: str
    ) -> tuple[str, str]:
        """Render the bilingual application body for the job's kind (R8.6/R8.6a/R8a).

        The two feature templates are rendered by the pure, on-plane
        :func:`~sam.members.domain.application_messages.render_application_message`:

        - STAFF (``member_application_staff``): a deep-link to ``/members/{member_id}`` + a
          neutral one-line ``DUP`` triage marker when ``duplicate_suspected`` is set, and NO
          applicant PII beyond the display name (R8.6/R8.6a). Rendered in the recipient/tenant
          locale — the STAFF locale is NOT the applicant's choice (R6b.5), defaulting to ``nl``.
        - APPLICANT (``member_application_ack``): a confirmation embedding the applicant's OWN
          submitted data (their own data is not a leak, R8a.4), rendered in the APPLICANT's
          chosen locale (R6b/R8a.2).
        """
        if kind == JOB_KIND_STAFF:
            # Staff locale = recipient/tenant locale (R6b.5), not the applicant's — default nl.
            lang = DEFAULT_LOCALE
        else:
            lang = normalize_locale(envelope.get("locale"))
        return render_application_message(kind, lang, envelope)

    def _build_attachment(
        self,
        kind: str,
        rows: Sequence[Mapping[str, Any]],
        label_options: Any,
        *,
        export_name: str = DEFAULT_EXPORT_FILENAME,
    ) -> dict[str, Any] | None:
        """Build the attachment descriptor (``{filename, content, content_type}``) for the SES port.

        ``csv`` → a UTF-8 CSV of the result rows (header = the union of row keys, stable order),
        named ``export_name`` — the ``{Tenant_Name}-{Pivot_Name}.csv`` name the caller composed
        off the envelope (R5.2/5.5), replacing the old hard-coded ``members.csv``. ``export_name``
        is keyword-only and defaults to the safe generic :data:`DEFAULT_EXPORT_FILENAME` so a
        caller that supplies no name (or an older in-flight job) never emits a malformed filename.
        ``pdf_labels`` → delegated to the shared address-label generator seam when available;
        the worker does not reimplement label layout. An unknown kind is a permanent fault.
        """
        if kind == "csv":
            content = _rows_to_csv_bytes(rows)
            return {
                "filename": export_name,
                "content": content,
                "content_type": "text/csv",
            }
        if kind == "pdf_labels":
            content = self._build_pdf_labels(rows, label_options)
            return {
                "filename": "labels.pdf",
                "content": content,
                "content_type": "application/pdf",
            }
        raise MailSendPermanent(f"unknown attachment kind {kind!r}")

    def _build_pdf_labels(
        self, rows: Sequence[Mapping[str, Any]], label_options: Any
    ) -> bytes:
        """Render address-label PDF bytes from the result rows + shared ``label_options``.

        The label-layout generator is not yet on the SAM plane (it runs frontend-side today, R6),
        so a concrete generator is injected via the edge when available. Until it lands the
        worker refuses a ``pdf_labels`` job as a permanent fault rather than sending a corrupt /
        empty PDF — a loud, dead-lettered signal, never a silent bad send.
        """
        raise MailSendPermanent(
            "pdf_labels rendering is not available on the SAM plane yet "
            "(no label generator wired) — see design §6/R6"
        )

    @staticmethod
    def _clean_single(raw: Any) -> str:
        """Normalize a single optional address/value to a trimmed string (``""`` when absent)."""
        return raw.strip() if isinstance(raw, str) and raw.strip() else ""


_EXPORT_SANITIZE_STRIP = re.compile(
    "[/\\\\"
    "\u0000\u0001\u0002\u0003\u0004\u0005\u0006\u0007\u0008"
    "\u000b\u000c"
    "\u000e\u000f\u0010\u0011\u0012\u0013\u0014\u0015\u0016\u0017"
    "\u0018\u0019\u001a\u001b\u001c\u001d\u001e\u001f"
    "\u007f]"
)
_EXPORT_WHITESPACE_RUN = re.compile(r"\s+")


def _sanitize_export_part(part: Any) -> str:
    """Sanitize one export-name part (a tenant or pivot display name) for a filename/subject.

    The Python mirror of the frontend ``sanitize`` (``csvExport.ts``): strips filesystem-hostile
    characters — path separators and ASCII control chars — and collapses any whitespace run to a
    single space, trimming the edges. The result never contains a path separator, a control char,
    or leading/trailing whitespace, so it can neither escape a directory nor inject a mail header.
    A ``None`` / non-string input sanitizes to an empty string (the caller's fallback then kicks
    in).
    """
    text = part if isinstance(part, str) else ("" if part is None else str(part))
    text = _EXPORT_SANITIZE_STRIP.sub("", text)
    text = _EXPORT_WHITESPACE_RUN.sub(" ", text)
    return text.strip()


def _export_file_name(tenant_name: Any, pivot_name: Any) -> str:
    """Build the pivot-export attachment filename from the tenant + pivot display names (R5.2/5.5).

    Encodes the shared rule ``sanitize(tenant) + "-" + sanitize(pivot) + ".csv"`` — identical to
    the frontend ``exportFileName`` so a downloaded file and an emailed attachment match. Both
    parts are run through :func:`_sanitize_export_part` so the result carries no path separators
    or control characters.

    **Backward-compat fallback (design §"Error Handling").** When EITHER sanitized part is blank
    — an older in-flight job that predates the ``tenant_name`` / ``pivot_name`` envelope stamp
    (task 6.1), or a name that sanitizes to nothing — the helper does NOT raise and does NOT emit
    a malformed ``-.csv``; it degrades to the safe generic :data:`DEFAULT_EXPORT_FILENAME`
    (``export.csv``). A pivot export never regresses to a hard failure over a cosmetic name.
    """
    tenant = _sanitize_export_part(tenant_name)
    pivot = _sanitize_export_part(pivot_name)
    if not tenant or not pivot:
        return DEFAULT_EXPORT_FILENAME
    return f"{tenant}-{pivot}.csv"


def _export_subject(tenant_name: Any, pivot_name: Any) -> str:
    """Compose the pivot-export email subject: the tenant name as a leading prefix + the pivot (R5.3).

    Combines the sanitized tenant name as a LEADING PREFIX with the pivot name as
    ``"{Tenant} - {Pivot}"``, so the subject identifies which tenant and which pivot the emailed
    export belongs to. Parts are sanitized with :func:`_sanitize_export_part` (no control chars,
    so no header injection).

    **Backward-compat fallback (design §"Error Handling").** When EITHER sanitized part is blank
    (an older in-flight job with no stamped names), the helper falls back to the generic
    :data:`DEFAULT_EXPORT_SUBJECT` rather than composing a lopsided ``"Tenant - "`` /
    ``" - Pivot"`` subject or raising — matching the filename fallback so the two degrade
    together.
    """
    tenant = _sanitize_export_part(tenant_name)
    pivot = _sanitize_export_part(pivot_name)
    if not tenant or not pivot:
        return DEFAULT_EXPORT_SUBJECT
    return f"{tenant} - {pivot}"


def _rows_to_csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    """Serialize result rows to UTF-8 CSV bytes (header = the union of row keys, stable order).

    Pure + storage-agnostic. The header is the first-appearance union of every row's keys so a
    ragged result (rows with differing keys) still produces a well-formed CSV; a missing value is
    an empty cell. An empty result yields a zero-row CSV (just no data lines).
    """
    header: list[str] = []
    for row in rows:
        for key in row:
            if key not in header:
                header.append(str(key))

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({str(k): _csv_cell(v) for k, v in row.items()})
    return buffer.getvalue().encode("utf-8")


def _csv_cell(value: Any) -> Any:
    """Flatten a cell value for CSV — nested mapping/sequence → str, scalars pass through."""
    if isinstance(value, (Mapping, list, tuple)):
        return str(value)
    return value


def _dedupe_addresses(raw: Any) -> tuple[str, ...]:
    """De-duplicate an address sequence (case-insensitive key), preserving first-seen order.

    Used for the application Reply-To set (R9a) — the all-scope ``Members_CRUD`` / ``TenantAdmin``
    addresses the 6.1 resolver returns. A non-sequence / empty input yields ``()``.
    """
    if not isinstance(raw, (list, tuple)):
        return ()
    seen: set[str] = set()
    out: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            continue
        addr = entry.strip()
        key = addr.lower()
        if addr and key not in seen:
            seen.add(key)
            out.append(addr)
    return tuple(out)


def _join_reply_to(addresses: Sequence[str]) -> str | None:
    """Join a multi-address Reply-To SET into the single ``reply_to`` the SES port takes (R9a.2).

    The application Reply-To is the all-scope ``Members_CRUD`` recipient SET (D8/D24), so it can be
    more than one address — but the :class:`SesSender` port carries a single ``reply_to`` string.
    SES ``ReplyToAddresses`` is an address LIST, so a comma-separated address list in that one field
    is split back into the multiple header addresses by the adapter (``SesBotoSender`` splits on
    commas). An empty set → ``None`` (no Reply-To header set, R9a.4).
    """
    cleaned = [a for a in (addresses or ()) if a]
    if not cleaned:
        return None
    return ", ".join(cleaned)
