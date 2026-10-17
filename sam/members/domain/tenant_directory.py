"""
Members application (public intake) — the **tenant-directory slug resolver** (application-app
Task 1.2; R2.1–R2.3, R1a.4; design §1/§2/§3, seam a).

ONE storage-agnostic Members-domain component that answers a single question, synchronously,
at the PUBLIC SAM edge BEFORE any tenant-scoped work is done (design §1 "resolve tenant from
slug (allow-list, verify-before-trust)"):

    *Does this public path slug name an allow-listed tenant — and if so, which canonical
    ``tenant_id`` does it resolve to?*

It treats the lookup as an **allow-list** (verify-before-trust, Property 2): a slug resolves
ONLY when it matches an entry the directory actually carries. Every other input — an unknown
slug, a forged/garbage slug, a blank/oversized/malformed one — resolves to the SAME typed
**not-found** outcome, so the edge returns a 404 that is deliberately indistinguishable from
"no such endpoint" (R1a.4): the allow-list cannot be probed for valid tenant slugs (no
enumeration oracle).

Where it sits (steering 35)
---------------------------
Thin public edge handler (``handler/public_app.py``, Task 1.1) → THIS resolver (business logic,
storage-agnostic) → the slug→``tenant_id`` reader seam (``repository/tenant_slug_reader.py``, a
thin SAM-plane projection of the existing landing-page slug mechanism — D19; wired in Task 1.3).
It is NOT the handler (the handler calls it and maps a not-found outcome to the non-probeable
404 envelope via ``_http._error``) and NOT the repository (it names no boto3, no DynamoDB, no
CloudFront KVS — only the :class:`TenantSlugReader` Protocol).

The slug→tenant truth source — DECIDED = D19 (reuse the landing-page slug mechanism)
------------------------------------------------------------------------------------
The slug is the SAME one the landing pages already use — ``<slug>.jabaki.nl`` (host-based) plus
the custom-domain→slug CloudFront KeyValueStore ``myadmin-domain-slug-mapping``
(``infrastructure/landing-pages.tf``). There is **NO new ``tenant-directory`` store**. The API
edge reads slug→``tenant_id`` from a thin SAM-plane projection of that mapping, kept behind the
:class:`TenantSlugReader` seam so this resolver stays storage-agnostic. Swapping the backing
store (projection row vs. a direct KVS read) is a localized change to the seam's concrete
implementation — never a ripple through this resolver or its callers.

Non-probeable by construction (R2.3 / R1a.4)
--------------------------------------------
The resolver NEVER distinguishes "unknown slug" from "malformed slug" from "blank slug" in its
OUTCOME: all collapse to the single :class:`TenantResolution.not_found` state. A caller that
maps every not-found to the same 404 (``code = errors.api.notFound``) therefore cannot be used
to tell a real-but-unknown slug from garbage — the only observable success is a slug that is
actually allow-listed. The reader seam is fail-safe/empty-is-valid (a missing mapping → no
match), so the resolver inherits non-probeable behaviour even when the backing store is empty
or unreachable-as-empty.

Pure / injectable (mirrors :class:`MailSenderResolver`)
-------------------------------------------------------
The resolver depends only on the injected :class:`TenantSlugReader` seam (the SAM-plane concrete
is the slug reader wired in Task 1.3, which satisfies it by duck-typing); a unit test drives it
with a static reader and no AWS. It has no I/O of its own and never raises on bad input — a
malformed slug is simply not-found, not an exception.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

__all__ = [
    "MAX_SLUG_LENGTH",
    "TenantSlugReader",
    "ResolveFailure",
    "TenantResolution",
    "TenantDirectory",
]

#: Upper bound on an acceptable slug length. A DNS label is <= 63 chars (the slug rides as a
#: landing-page host label, ``<slug>.jabaki.nl`` — D19); anything longer cannot be a real slug,
#: so it is rejected BEFORE the reader is consulted (a cheap, non-probeable guard that also caps
#: the key handed to the backing store). An oversized value resolves to the same not-found
#: outcome as any other miss (R1a.4) — never a distinct error.
MAX_SLUG_LENGTH = 63


# ── Seam (the storage-agnostic port this resolver depends on) ───────────────────────────


@runtime_checkable
class TenantSlugReader(Protocol):
    """Read-only provider of the slug→``tenant_id`` allow-list (the resolver's only seam).

    The SAM-plane concrete is the slug reader wired in Task 1.3
    (``repository/tenant_slug_reader.py`` — a thin projection of the landing-page slug mechanism,
    D19), which satisfies this Protocol by duck-typing; tests pass a static one. The method is
    fail-safe / empty-is-valid: an unknown slug, a missing mapping, or an unreachable-as-empty
    backing store all return ``None`` (no match) — NEVER a raise and NEVER a guessed tenant. The
    resolver inherits its non-probeable, verify-before-trust behaviour from that contract.
    """

    def resolve_slug(self, slug: str) -> str | None:
        """Return the canonical ``tenant_id`` for an allow-listed ``slug``, else ``None``.

        ``None`` means "not on the allow-list" (unknown/forged); it is the ONLY not-found
        signal, so the resolver cannot leak why a lookup missed. The ``slug`` passed here is
        already normalized by the resolver (trimmed + case-folded).
        """
        ...


# ── Typed result (a structured value + enum, never a raw string) ────────────────────────


class ResolveFailure(Enum):
    """WHY a slug did not resolve — a single, uniform not-found reason (non-probeable).

    There is intentionally ONE value: the resolver never distinguishes an unknown slug from a
    malformed/blank/oversized one in its outcome, so a caller mapping it to HTTP cannot be used
    as an enumeration oracle (R2.3 / R1a.4). The enum exists for symmetry with the sibling
    resolvers (e.g. :class:`~sam.members.domain.mail_sender_resolver.NotCertifiedReason`) and so
    the handler switches on a typed value rather than string-sniffing — NOT to expose distinct
    failure causes to the client.
    """

    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class TenantResolution:
    """The resolver's outcome: EITHER a resolved ``tenant_id`` OR the uniform not-found reason.

    Frozen (an immutable answer). Exactly one of the two states holds, enforced at construction:

    - **resolved** — :attr:`tenant_id` is the canonical allow-listed tenant the slug names;
      :attr:`failure` is ``None`` and :attr:`ok` is ``True``. The edge proceeds scoped to this
      (and ONLY this) ``tenant_id`` (R2.2/R2.4 — the sole source of the record's tenant).
    - **not-found** — :attr:`failure` is :data:`ResolveFailure.NOT_FOUND`; :attr:`tenant_id` is
      ``None`` and :attr:`ok` is ``False``. The edge returns the non-probeable 404, deliberately
      indistinguishable from "no such endpoint" (R2.3/R1a.4).

    Construct via the :meth:`resolved` / :meth:`not_found` factories rather than directly, so the
    "exactly one of" invariant can never be violated by a caller.
    """

    tenant_id: str | None
    failure: ResolveFailure | None

    def __post_init__(self) -> None:
        has_tenant = self.tenant_id is not None
        has_failure = self.failure is not None
        if has_tenant == has_failure:
            raise ValueError(
                "TenantResolution carries EXACTLY one of tenant_id / failure "
                f"(got tenant_id={self.tenant_id!r}, failure={self.failure!r})"
            )

    @property
    def ok(self) -> bool:
        """``True`` iff the slug resolved to an allow-listed tenant (the edge may proceed)."""
        return self.tenant_id is not None

    @classmethod
    def resolved(cls, tenant_id: str) -> "TenantResolution":
        """Build a resolved outcome carrying the canonical ``tenant_id``."""
        return cls(tenant_id=tenant_id, failure=None)

    @classmethod
    def not_found(cls) -> "TenantResolution":
        """Build the uniform not-found outcome (the ONLY failure state — non-probeable)."""
        return cls(tenant_id=None, failure=ResolveFailure.NOT_FOUND)


class TenantDirectory:
    """Resolve a public path slug to an allow-listed ``tenant_id``, or a uniform not-found (R2/R1a.4).

    Storage-agnostic: depends only on the injected :class:`TenantSlugReader` seam (the sole
    slug→tenant touch-point). The resolution is an **allow-list** (verify-before-trust): a slug
    resolves ONLY when the reader returns a concrete tenant for it. Every rejection — a blank /
    oversized / otherwise-malformed slug, or a well-formed slug the reader does not know — yields
    the SAME :data:`ResolveFailure.NOT_FOUND`, so the outcome carries no signal a caller could
    probe (R2.3 / R1a.4).

    Normalization (fixed here so the resolver and the backing projection agree): a slug is
    trimmed of surrounding whitespace and case-folded to lower-case before the reader is
    consulted — the landing-page slug is a DNS host label, which is case-insensitive, so
    ``HDCN`` and ``hdcn`` name the same tenant. A slug that is empty after trimming, or longer
    than :data:`MAX_SLUG_LENGTH`, is rejected WITHOUT consulting the reader (a cheap guard that
    also caps the key handed to the store); the rejection is the same uniform not-found.
    """

    def __init__(self, reader: TenantSlugReader) -> None:
        self._reader = reader

    @staticmethod
    def _normalize(slug: object) -> str | None:
        """Return the normalized (trimmed + case-folded) slug, or ``None`` if it cannot be one.

        A non-string, a blank/whitespace-only value, or one longer than :data:`MAX_SLUG_LENGTH`
        all return ``None`` — the resolver maps that to the uniform not-found WITHOUT touching
        the reader, so garbage is as non-probeable as an unknown-but-well-formed slug.
        """
        if not isinstance(slug, str):
            return None
        normalized = slug.strip().lower()
        if not normalized or len(normalized) > MAX_SLUG_LENGTH:
            return None
        return normalized

    def resolve(self, slug: str) -> TenantResolution:
        """Resolve ``slug`` to an allow-listed ``tenant_id``, or the uniform not-found (R2/R1a.4).

        Args:
            slug: the public path slug carried on the request (e.g. ``hdcn`` from
                ``POST /public/members/hdcn/applications``). It is trusted for NOTHING — it only
                SELECTS among allow-listed tenants, it never GRANTS one (verify-before-trust,
                Property 2). A non-string / blank / oversized / malformed value is accepted here
                and resolved to not-found rather than raising.

        Returns:
            A :class:`TenantResolution`: ``resolved`` with the canonical ``tenant_id`` when (and
            only when) the slug is on the allow-list, or ``not_found`` for EVERY other input. The
            not-found outcome is uniform by construction so the caller's 404 is non-probeable
            (R2.3 / R1a.4). The resolver NEVER invents or guesses a tenant.
        """
        normalized = self._normalize(slug)
        if normalized is None:
            # Malformed / blank / oversized — not-found WITHOUT consulting the reader.
            return TenantResolution.not_found()

        tenant_id = self._reader.resolve_slug(normalized)
        # Guard the reader's own contract: only a non-blank string is a real tenant. A ``None`` /
        # empty / non-string answer is treated as no-match (fail-safe, never a hostless tenant).
        if not isinstance(tenant_id, str) or not tenant_id:
            return TenantResolution.not_found()

        return TenantResolution.resolved(tenant_id)
