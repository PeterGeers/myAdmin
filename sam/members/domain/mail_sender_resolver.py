"""
Members mail — the **pre-send certification resolver** (mail spec Task 1.1; R4, R5, R8.1;
design "Pre-send certification resolver").

ONE storage-agnostic Members-domain component that answers a single question, synchronously,
at the SAM edge BEFORE any mail is enqueued (design §Components / Error Handling):

    *For the active tenant, is there a usable verified From — and if not, exactly why not?*

It resolves From = ``<mail_local_part|noreply>@<mail_domain>`` from the projected ``config#mail``
row and runs the §5c "allowed to send" gate, returning EITHER a usable-From value OR a TYPED
not-certified / not-enabled reason (a structured result + enum, never a raw English string the
caller has to sniff). Reply-To is NOT this resolver's concern: the resolver resolves From; the
Reply-To is the triggering user's verified email, passed by the caller (R4.3, design §Overview).

Where it sits (steering 35)
---------------------------
Thin edge handler → THIS resolver (business logic, storage-agnostic) → the projection-reader
seam. It is NOT the handler (the handler calls it and maps the typed reason to a bilingual 4xx)
and NOT the worker (the worker sends; this gates BEFORE enqueue). It names no boto3, no DynamoDB,
no SES — only the :class:`MailConfigReader` Protocol. ``tenant_id`` is AUTHORITATIVE on every call
(never a body value — verify-before-trust, Property 3).

The certification truth source — DECIDED = Option B (design "Resolved implementation choices")
----------------------------------------------------------------------------------------------
The "is this tenant certified to send" truth is the **PROJECTED** ``mail_certified`` flag on the
``config#mail`` row (``MailConfigReader.is_mail_certified``), authored at onboarding and projected
on the existing ``config#*`` rails. There is **NO live SES call on the send path** — the resolver
reads the projected flag exactly as the mail-enabled gate reads ``mail_enabled``.

    **Option A (the NOTED future alternative, NOT built):** a LIVE SES ``GetEmailIdentity`` at
    pre-send — the address-OR-domain §5c check performed against SES in real time
    (``VerifiedForSendingStatus`` on the address, else on the domain) plus an account
    ``GetAccount`` ``SendingEnabled`` check. Switch to Option A if the projected flag's STALENESS
    (a certification lapses in SES after the row was projected, so the projection says certified
    when SES no longer is — or vice versa) becomes a real problem. The OBSERVABLE BEHAVIOUR is
    identical either way: a not-certified tenant gets the same typed not-certified reason and no
    send; only the truth-source differs. The :class:`SesIdentityPort` Protocol below is the SEAM
    kept open for that switch — a live-SES adapter would satisfy it, and
    :class:`MailSenderResolver` would consult it INSTEAD of the projected flag — so moving to
    Option A is a localized change here, not a ripple through the callers.

Fail-closed (Property 4, R4.2 / R5.2)
-------------------------------------
The gate opens ONLY on explicit, projected verified truth. Every absence refuses:

- ``mail_enabled`` not projected ``True`` → :data:`NotCertifiedReason.MAIL_DISABLED`.
- ``mail_certified`` not projected ``True`` → :data:`NotCertifiedReason.NOT_CERTIFIED`.
- ``mail_domain`` absent/blank → :data:`NotCertifiedReason.NO_DOMAIN` — NO From is composable, and
  the resolver NEVER guesses or substitutes a host (R4.2 — the ``jabaki.nl`` foreign-sender
  regression must stay dead). There is no platform-branded fallback sender anywhere.

A blank ``tenant_id`` is a programming/authz fault (the edge resolves it from the verified JWT +
X-Tenant), not projected data; it refuses as :data:`NotCertifiedReason.MAIL_DISABLED` rather than
composing a hostless address.

Pure / injectable (design "Pure/injectable")
--------------------------------------------
The resolver depends only on the injected :class:`MailConfigReader` seam (the SAM-plane concrete is
``MembersProjectionReader``, which satisfies it by duck-typing) and the OPTIONAL
:class:`SesIdentityPort` seam (``None`` today — Option B needs no live check). No I/O of its own; a
unit test drives it with a static reader and no AWS.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

__all__ = [
    "DEFAULT_MAIL_LOCAL_PART",
    "MailConfigReader",
    "SesIdentityPort",
    "NotCertifiedReason",
    "SenderResolution",
    "MailSenderResolver",
]

#: The default From local-part when a tenant has not authored ``mail_local_part`` — mirrors the
#: projection reader's default so the resolver and the reader agree (design Data Models).
DEFAULT_MAIL_LOCAL_PART = "noreply"


# ── Seams (the storage-agnostic ports this resolver depends on) ─────────────────────────


@runtime_checkable
class MailConfigReader(Protocol):
    """Read-only provider of a tenant's projected mail config (the resolver's only required seam).

    The SAM-plane concrete is
    :class:`sam.members.repository.projection_config_reader.MembersProjectionReader` (whose
    ``get_mail_domain`` / ``get_mail_local_part`` / ``is_mail_certified`` / ``is_mail_enabled``
    satisfy this Protocol by duck-typing); tests pass a static one. Every method is fail-closed /
    empty-is-valid on missing data (a missing ``config#mail`` row → ``None`` domain / default
    local-part / ``False`` flags), so the resolver inherits the fail-closed discipline for free.
    """

    def get_mail_domain(self, tenant_id: str) -> str | None:
        """Return the tenant's projected ``mail_domain``, or ``None`` when absent/unusable."""
        ...

    def get_mail_local_part(self, tenant_id: str) -> str:
        """Return the tenant's projected ``mail_local_part`` (default ``"noreply"``)."""
        ...

    def is_mail_certified(self, tenant_id: str) -> bool:
        """Return the projected ``mail_certified`` gate (fail-closed → ``False``)."""
        ...

    def is_mail_enabled(self, tenant_id: str) -> bool:
        """Return the projected ``mail_enabled`` gate (fail-closed → ``False``)."""
        ...


@runtime_checkable
class SesIdentityPort(Protocol):
    """The OPTIONAL live-SES check seam — kept open for the future **Option A** switch (unused today).

    Option B (the decided truth source) needs no live SES call, so :class:`MailSenderResolver` is
    constructed with ``ses=None`` in production and this Protocol has no concrete implementation
    yet. It exists so that moving to Option A (a live ``GetEmailIdentity`` address-OR-domain §5c
    check + account ``SendingEnabled``) is a localized change: a live-SES adapter would satisfy
    this Protocol, and the resolver would consult it INSTEAD of the projected ``mail_certified``
    flag. The not-certified BEHAVIOUR is identical either way — only the truth-source differs.
    """

    def is_identity_usable(self, from_address: str, domain: str) -> bool:
        """Return whether ``from_address`` OR its ``domain`` is a usable SES identity (§5c)."""
        ...


# ── Typed result (a structured value + enum, never a raw string) ────────────────────────


class NotCertifiedReason(Enum):
    """WHY a tenant cannot send — a MACHINE reason the edge maps to a bilingual message + action.

    A typed enum (design: "a structured result/enum, not a raw string") so the handler switches on
    the reason to pick the i18n message/action rather than string-sniffing. Each is a distinct
    fail-closed branch (Property 4):

    - :attr:`MAIL_DISABLED` — the tenant's ``mail_enabled`` gate is not projected ``True`` (mail is
      not turned on for this tenant at all). Action: contact your administrator.
    - :attr:`NOT_CERTIFIED` — mail is enabled but ``mail_certified`` is not projected ``True`` (the
      SES-verified onboarding flag is not set / lapsed). Action: certify the tenant mail domain.
    - :attr:`NO_DOMAIN` — no ``mail_domain`` is projected, so no From can be composed at all
      (NEVER a guessed/foreign host — R4.2). Action: set the tenant mail domain at onboarding.
    """

    MAIL_DISABLED = "mail_disabled"
    NOT_CERTIFIED = "not_certified"
    NO_DOMAIN = "no_domain"


@dataclass(frozen=True)
class SenderResolution:
    """The resolver's outcome: EITHER a usable From OR a typed not-certified reason — never both.

    Frozen (an immutable answer). Exactly one of the two states holds, enforced at construction:

    - **usable** — :attr:`from_address` is a composed ``<local_part>@<domain>`` the caller may send
      from; :attr:`reason` is ``None`` and :attr:`ok` is ``True``.
    - **refused** — :attr:`reason` is a :class:`NotCertifiedReason`; :attr:`from_address` is
      ``None`` and :attr:`ok` is ``False``. The caller refuses the send BEFORE enqueue and surfaces
      the reason (Property 6 — never a silent drop, never a substitute sender).

    Construct via the :meth:`usable` / :meth:`refused` factories rather than directly, so the
    "exactly one of" invariant can never be violated by a caller.
    """

    from_address: str | None
    reason: NotCertifiedReason | None

    def __post_init__(self) -> None:
        has_from = self.from_address is not None
        has_reason = self.reason is not None
        if has_from == has_reason:
            raise ValueError(
                "SenderResolution carries EXACTLY one of from_address / reason "
                f"(got from_address={self.from_address!r}, reason={self.reason!r})"
            )

    @property
    def ok(self) -> bool:
        """``True`` iff a usable From was resolved (the send may proceed to enqueue)."""
        return self.from_address is not None

    @classmethod
    def usable(cls, from_address: str) -> "SenderResolution":
        """Build a usable resolution carrying the composed From address."""
        return cls(from_address=from_address, reason=None)

    @classmethod
    def refused(cls, reason: NotCertifiedReason) -> "SenderResolution":
        """Build a refused resolution carrying the typed not-certified reason."""
        return cls(from_address=None, reason=reason)


class MailSenderResolver:
    """Resolve the active tenant's usable From, or a typed refusal — the pre-send gate (R4/R5/R8.1).

    Storage-agnostic: depends only on the injected :class:`MailConfigReader` seam (the sole
    projection touch-point) and the OPTIONAL :class:`SesIdentityPort` (``None`` under Option B).
    ``tenant_id`` is authoritative. The resolution order is fail-closed and short-circuits on the
    first refusal (design Error Handling / Property 4):

    1. ``mail_enabled`` must be projected ``True`` → else :attr:`NotCertifiedReason.MAIL_DISABLED`.
    2. ``mail_certified`` must be projected ``True`` (Option B) → else
       :attr:`NotCertifiedReason.NOT_CERTIFIED`. (Option A would consult :class:`SesIdentityPort`
       here instead — see the module docstring.)
    3. ``mail_domain`` must be projected (non-blank) → else :attr:`NotCertifiedReason.NO_DOMAIN`
       (no From composable; never a guessed host — R4.2).
    4. Compose From = ``<mail_local_part|noreply>@<mail_domain>`` and return it as usable.
    """

    def __init__(
        self,
        reader: MailConfigReader,
        ses: SesIdentityPort | None = None,
    ) -> None:
        self._reader = reader
        # Option B: no live SES check on the send path. Held only so an Option-A adapter can be
        # injected later WITHOUT changing the resolver's callers (see the module docstring).
        self._ses = ses

    def resolve(self, tenant_id: str) -> SenderResolution:
        """Resolve the usable From for ``tenant_id``, or a typed not-certified/not-enabled reason.

        Args:
            tenant_id: the AUTHORITATIVE active tenant (resolved by the edge from the verified
                JWT + X-Tenant — never a body value, Property 3). A blank value is treated as
                mail-not-enabled (fail-closed) rather than composing a hostless address.

        Returns:
            A :class:`SenderResolution`: ``usable`` with a composed
            ``<local_part>@<domain>`` From, or ``refused`` with a :class:`NotCertifiedReason`.
            The resolver NEVER returns a guessed/foreign/substitute sender (R4.2).
        """
        # A blank tenant can carry no projected config; refuse fail-closed (never a hostless From).
        if not tenant_id:
            return SenderResolution.refused(NotCertifiedReason.MAIL_DISABLED)

        # 1. Mail must be turned on for the tenant at all (R5.2 / Property 4).
        if not self._reader.is_mail_enabled(tenant_id):
            return SenderResolution.refused(NotCertifiedReason.MAIL_DISABLED)

        # 2. The tenant must be certified. Option B: the projected flag is the truth source; no
        #    live SES call on the send path. (Option A would consult self._ses here instead.)
        if not self._reader.is_mail_certified(tenant_id):
            return SenderResolution.refused(NotCertifiedReason.NOT_CERTIFIED)

        # 3. A domain must be projected — else no From is composable, and we NEVER guess a host
        #    (R4.2, the jabaki.nl foreign-sender regression guard).
        domain = self._reader.get_mail_domain(tenant_id)
        if not domain:
            return SenderResolution.refused(NotCertifiedReason.NO_DOMAIN)

        # 4. Compose From = <mail_local_part|noreply>@<mail_domain>. The reader already defaults a
        #    blank/absent local-part to "noreply"; belt-and-suspenders here too so a seam that
        #    returned an empty string can never yield a hostless/`@`-leading address.
        local_part = self._reader.get_mail_local_part(tenant_id) or DEFAULT_MAIL_LOCAL_PART
        return SenderResolution.usable(f"{local_part}@{domain}")
