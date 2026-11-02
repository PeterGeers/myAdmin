"""Application-form slug **format** validation (spec 12 Task 1.1; R4.2, design §Data Models).

The application form stored on the SAM ``config#fields`` row carries its OWN public slug
(``slug`` attribute), independent of the tenant's landing-page slug and free to differ from the
tenant NAME (R4.4). This module is the single SAM-plane home of the slug **format** contract.

Why the rules are REPLICATED, not imported (plane boundary)
-----------------------------------------------------------
R4.2 requires the form slug to be validated with the SAME rules the landing slug uses. The
landing authority is ``backend/src/services/tenant_slug_service.py`` (``SLUG_PATTERN`` +
``SLUG_MIN_LENGTH`` / ``SLUG_MAX_LENGTH`` + ``RESERVED_SLUGS``). That module is a FLASK-plane
service: importing it drags in ``boto3`` / ``database`` / ``mysql`` dependencies that the SAM
plane must not take (35-sam-module-architecture-sam). So the format rules are replicated here
VERBATIM — same regex, same length bounds, same reserved set — with the landing module cited as
the source of truth. Keep the two in lock-step: a change to the landing format contract must be
mirrored here (and vice-versa) in the same change.

SCOPE — format + prefix-ownership; uniqueness is separate (Task 1.2)
-------------------------------------------------------------------
This module answers two orthogonal questions about a slug STRING, both pure (no I/O):

1. :func:`validate_slug_format` — "is this a well-formed, non-reserved slug string?" (R4.2). It
   performs NO uniqueness / collision check — within-tenant uniqueness is the ``_slugs/{slug}``
   bucket-marker conditional ``put_object`` (OQ4, Task 1.2), and the form-vs-landing backstop is
   the publish-time S3 check (Task 2.2). A blank / malformed / reserved slug is rejected fail-loud
   so garbage never reaches the publish path (R8 unchanged).

2. :func:`validate_slug_prefix_ownership` — **SEC-4** (spec 14 R2.3/R2.5/R10.4): "does this NEW
   slug belong under the AUTHENTICATED tenant's public prefix?". This is a SEPARATE, additive
   layer on top of format: the uniqueness gate (Task 1) is tenant-AGNOSTIC — it stops two tenants
   claiming the SAME slug but does NOT stop tenant B squatting on tenant A's prefix
   (``tenantA-apply``). The prefix rule closes that squatting hole on EVERY claim path. It stays a
   PURE string check: the caller resolves the tenant's own prefix from its projected ``tenant``
   row (``MembersProjectionReader.get_public_prefix`` — SAM reads its own projection, never calls
   Flask, ADR 0005) and supplies a grandfathering predicate for live/legacy slugs; this module
   never touches S3 / DynamoDB / MySQL.

Ordering on a claim path: format/reserved (1) runs FIRST, then the prefix rule (2), then the
atomic uniqueness claim (Task 1). A malformed slug never reaches the prefix check.
"""

from __future__ import annotations

import re

__all__ = [
    "RESERVED_SLUGS",
    "SLUG_MAX_LENGTH",
    "SLUG_MIN_LENGTH",
    "SLUG_PATTERN",
    "validate_slug_format",
    "validate_slug_prefix_ownership",
]

#: Slugs reserved for system use — cannot be claimed as a form slug. Replicated VERBATIM from the
#: landing authority ``tenant_slug_service.RESERVED_SLUGS`` (keep in lock-step).
RESERVED_SLUGS = frozenset(
    {
        "admin",
        "api",
        "www",
        "app",
        "test",
        "staging",
        "landing",
        "public",
        "static",
        "assets",
    }
)

#: Slug format: lowercase alphanumeric with single hyphens, no leading/trailing hyphens, no
#: consecutive hyphens. Replicated VERBATIM from the landing authority
#: ``tenant_slug_service.SLUG_PATTERN`` (R4.2 — "the SAME rules the landing slug uses").
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

#: Length bounds — replicated VERBATIM from the landing authority (3–100 chars).
SLUG_MIN_LENGTH = 3
SLUG_MAX_LENGTH = 100


def validate_slug_format(slug: object) -> str | None:
    """Return a caller-safe error string for a malformed form slug, or ``None`` when it is valid.

    Applies the landing ``SLUG_PATTERN`` rules (R4.2): the slug must be a non-blank string, 3–100
    characters, lowercase letters/numbers/hyphens only, with no leading/trailing hyphen and no
    consecutive hyphens, and must not be a reserved slug. A ``NAME`` that differs from the tenant
    NAME is allowed (this checks SHAPE only, not identity). Uniqueness is NOT checked here — that
    is the Task-1.2 ``_slugs/{slug}`` marker claim.

    The returned message is deliberately caller-safe (no internals) so the edge can surface it on
    the standard 400 envelope; ``None`` means the slug is well-formed.
    """
    if not isinstance(slug, str):
        return "slug must be a string"

    if len(slug) < SLUG_MIN_LENGTH:
        return f"slug must be at least {SLUG_MIN_LENGTH} characters"

    if len(slug) > SLUG_MAX_LENGTH:
        return f"slug must be at most {SLUG_MAX_LENGTH} characters"

    # One format check covers lowercase, allowed chars, no leading/trailing hyphen, and no
    # consecutive hyphens (the landing contract).
    if not SLUG_PATTERN.match(slug):
        return (
            "slug must be lowercase, contain only letters, numbers, and hyphens, "
            "and cannot start/end with a hyphen or contain consecutive hyphens"
        )

    if slug in RESERVED_SLUGS:
        return f"'{slug}' is a reserved name and cannot be used as a form slug"

    return None


def validate_slug_prefix_ownership(
    slug: object,
    tenant_prefix: object,
    *,
    is_grandfathered: bool = False,
) -> str | None:
    """SEC-4 prefix-ownership check: return a caller-safe error, or ``None`` when the claim is OK.

    The tenant-SCOPED squatting guard (spec 14 R2.3/R2.5, R10.4 / SEC-4). A NEW page slug must be
    EXACTLY the authenticated tenant's ``public_prefix`` or ``{prefix}-{suffix}`` — i.e. it must
    start with the tenant's OWN prefix as a whole prefix segment. A slug that does not (including
    one that sits under ANOTHER tenant's prefix) is REJECTED so no claim is performed. This closes
    the squatting hole the Task-1 uniqueness gate alone cannot: that gate is tenant-AGNOSTIC (it
    only stops two tenants claiming the SAME slug), so without this check tenant B could claim
    ``tenantA-apply`` under tenant A's trusted ``*.jabaki.nl`` namespace (a phishing vector).

    This is a PURE string rule — no I/O. The caller resolves ``tenant_prefix`` from the
    AUTHENTICATED tenant's OWN projected ``tenant`` row
    (:meth:`sam.members.repository.projection_config_reader.MembersProjectionReader.get_public_prefix`
    — SAM reads its own projection, never calls Flask, ADR 0005) and decides ``is_grandfathered``
    (see below). It is enforced on EVERY claim path (publish/claim), AFTER
    :func:`validate_slug_format` (format/reserved runs first) and BEFORE the atomic uniqueness
    claim.

    Grandfathering (R2.5): the prefix rule applies to NEW claims only. Already-live / legacy slugs
    — INCLUDING uppercase legacy slugs like ``GoodwinSolutions`` that predate this rule and would
    fail even ``SLUG_PATTERN`` — must NOT be broken or force-renamed. When the caller determines
    the slug is already live for THIS owner (e.g. an existing same-owner marker for the slug, so a
    same-owner idempotent re-publish, Task 1.3), it passes ``is_grandfathered=True`` and this check
    PASSES unconditionally (``None``) — it never re-validates an established slug's shape or prefix.

    Prefix-less tenants (back-compat, task 6.2 omits a NULL prefix): a tenant with NO projected
    prefix (``tenant_prefix`` is ``None`` / blank) cannot assert ownership of a fresh prefixed
    namespace. The SAFE decision (documented) is:

    - a grandfathered (already-live, same-owner) slug is STILL allowed — a prefix-less tenant's
      established slugs keep working (``is_grandfathered`` short-circuits before the prefix lookup);
    - a NEW claim by a prefix-less tenant is REJECTED with a caller-safe message asking that a
      public prefix be configured first. This neither hard-breaks a prefix-less tenant's existing
      slugs (they grandfather) NOR lets a prefix-less tenant squat a new prefixed slug (it cannot
      prove ownership of any prefix) — matching the spec's grandfathering intent.

    Args:
        slug: The NEW slug being claimed. Expected to already be a well-formed string (the caller
            runs :func:`validate_slug_format` first); a non-string is rejected defensively.
        tenant_prefix: The authenticated tenant's ``public_prefix`` (from its projected ``tenant``
            row), or ``None``/blank when the tenant has no prefix projected yet.
        is_grandfathered: ``True`` when the caller has determined this slug is already live for the
            SAME owner (idempotent re-publish / legacy slug) and must be let through unchanged.

    Returns:
        A caller-safe error string (no internals) when the claim violates the prefix rule, or
        ``None`` when the slug is owned by (or grandfathered for) the tenant.
    """
    # Grandfathered live/legacy slug (incl. uppercase legacy, same-owner re-publish): never
    # re-validate shape or prefix — an established slug must not be broken or force-renamed (R2.5).
    if is_grandfathered:
        return None

    if not isinstance(slug, str) or not slug:
        return "slug must be a string"

    # A prefix-less tenant (NULL/absent projected prefix — back-compat, task 6.2) cannot prove
    # ownership of any prefixed namespace, so a NEW claim is refused (a prefix-less tenant's
    # existing slugs are handled by the grandfather short-circuit above, never reaching here).
    if not isinstance(tenant_prefix, str) or not tenant_prefix.strip():
        return (
            "this tenant has no public prefix configured yet; a public prefix must be set "
            "before a new page slug can be claimed"
        )

    prefix = tenant_prefix.strip()

    # The slug must be EXACTLY the prefix, or the prefix followed by a hyphen + suffix — so the
    # prefix is matched as a WHOLE leading segment. A bare ``startswith(prefix)`` would be wrong:
    # it would let ``h-dcn2`` borrow the ``h-dcn`` prefix. Requiring ``prefix`` or ``prefix-…``
    # pins it to the tenant's own sub-namespace and rejects another tenant's prefix.
    if slug == prefix or slug.startswith(f"{prefix}-"):
        return None

    return (
        f"slug must start with this tenant's public prefix '{prefix}' "
        f"(either '{prefix}' or '{prefix}-<suffix>')"
    )
