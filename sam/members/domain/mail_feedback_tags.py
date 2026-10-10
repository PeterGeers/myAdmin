"""
Members mail — the SES-feedback ROUTING-KEY contract (mail-spec task 5.2; R9.5; design
"(Layered) SES feedback ingestion ... routed by run_id/tag").

SES publishes bounce/complaint/delivery events to ONE account-level SNS sink per configuration
set — it has NO module / tenant / run concept (R9.5). So the Members send-path STAMPS two custom
SES MESSAGE TAGS at send time that the configuration set echoes back on every feedback event
(``mail.tags``), and the task-5.2 ingestion handler reads them back to ROUTE the outcome to the
originating Members run:

- :data:`SES_TAG_TENANT_ID` — the AUTHORITATIVE tenant the event belongs to (never guessed from
  the address/domain downstream — tenancy is fail-closed, Property 3).
- :data:`SES_TAG_RUN_ID` — the logical run, so a LATE async bounce/complaint — which has NO
  existing ``mailrecipient#`` sub-record (the recipient SUCCEEDED at send) — can CREATE one AND
  adjust that run's tally (``record_mail_failure(..., adjust_run_tally=True)``).

Why TAGS (not message_id)?
--------------------------
The failure-ONLY status model (design "Resolved implementation choices") stores NO per-recipient
row for a success, so there is no send-time ``message_id → (tenant, run)`` index to match a late
bounce against without adding a write per recipient (which would defeat the failure-only model).
Stamping ``tenant_id`` + ``run_id`` as tags makes the event SELF-ROUTING: the authoritative tenant
and the run both ride ON the event, so a late bounce needs no prior record to be placed correctly.

Encoding (the SES tag charset)
------------------------------
SES restricts tag VALUES to ``[A-Za-z0-9_-]`` — but a Members ``run_id`` is
``deliver:<set>:<who>:<stamp>`` (colons) and a ``tenant_id`` can carry other characters. So the
values are HEX-encoded (lossless, reversible, output only ``[0-9a-f]``) rather than sanitised — a
sanitised id could collide two distinct runs. This module is the SINGLE SOURCE OF TRUTH for the
tag names + the codec, shared by the SENDER (stamps, :mod:`sam.members.repository.mail_send_adapters`)
and the INGESTION handler (reads, :mod:`sam.members.domain.mail_feedback_handler`) so stamp and
read can never disagree. PURE (no boto / no I/O) so the storage-agnostic worker + the ingestion
service import it without pulling in AWS.
"""

from __future__ import annotations

__all__ = [
    "SES_TAG_RUN_ID",
    "SES_TAG_TENANT_ID",
    "build_feedback_tags",
    "decode_ses_tag_value",
    "encode_ses_tag_value",
]

#: The SES message-tag NAME carrying the authoritative tenant_id (hex-encoded value). The NAME is
#: already within the SES-allowed tag charset by construction.
SES_TAG_TENANT_ID = "ms_tenant"

#: The SES message-tag NAME carrying the run_id (hex-encoded value) — locates the run so a late
#: bounce can create a failure sub-record + adjust the tally.
SES_TAG_RUN_ID = "ms_run"


def encode_ses_tag_value(value: str) -> str:
    """Encode an arbitrary string into a VALID SES message-tag value (hex of its UTF-8 bytes).

    SES tag values allow only ``[A-Za-z0-9_-]``; hex output (``"h-dcn"`` → ``"682d64636e"``) is
    always inside that charset, lossless, and reversible — so no id is mangled (a mangled id could
    collide two distinct runs). A blank input encodes to ``""`` (the caller omits a blank tag; SES
    rejects an empty tag value).
    """
    return (value or "").encode("utf-8").hex()


def decode_ses_tag_value(encoded: str) -> str:
    """Reverse :func:`encode_ses_tag_value`; a malformed value yields ``""`` (treated as ABSENT).

    A corrupt / non-hex tag decodes to empty so the ingestion handler treats it as a MISSING tag
    (→ the event is reported unroutable, never mis-routed to a wrong tenant — fail-closed, R9.5).
    """
    try:
        return bytes.fromhex(encoded or "").decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


def build_feedback_tags(tenant_id: str, run_id: str) -> dict[str, str]:
    """Build the ``{tag_name: encoded_value}`` mapping the sender stamps for ONE send (R9.5).

    Encodes ``tenant_id`` + ``run_id`` into the SES tag charset. A blank id yields a blank value;
    the sender drops a blank-valued tag (SES rejects empty values) — in practice ``tenant_id`` is
    always present (the worker refuses a job without it) and ``run_id`` always rides the envelope.
    """
    return {
        SES_TAG_TENANT_ID: encode_ses_tag_value(tenant_id),
        SES_TAG_RUN_ID: encode_ses_tag_value(run_id),
    }
