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

SCOPE — format only (R4.2); uniqueness is separate (Task 1.2)
-------------------------------------------------------------
This module answers ONLY "is this slug a well-formed, non-reserved slug string?". It performs NO
uniqueness / collision check — within-tenant uniqueness is the ``_slugs/{slug}`` bucket-marker
conditional ``put_object`` (OQ4, Task 1.2), and the form-vs-landing backstop is the publish-time
S3 check (Task 2.2). A blank / malformed / reserved slug is rejected fail-loud so garbage never
reaches the publish path (R8 unchanged).
"""

from __future__ import annotations

import re

__all__ = [
    "RESERVED_SLUGS",
    "SLUG_MAX_LENGTH",
    "SLUG_MIN_LENGTH",
    "SLUG_PATTERN",
    "validate_slug_format",
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
