"""
S3-backed **slug-marker store** — the ``_slugs/{slug}`` claim + reverse-lookup adapter (spec 12
Tasks 1.2/1.3; OQ4; design §Reverse-lookup / D6).

OQ4 resolved the slug→``tenant_id`` reverse lookup to a control-plane MARKER OBJECT in the shared
public-pages bucket, rather than a slug-keyed row on the ``tenant_id``-PK governance-projection
table (which would break that table's structural-isolation invariant — ``template.yaml``). This
module is the sole S3 touch-point for that marker; it does two things and nothing else:

- **Claim (Task 1.2):** a CONDITIONAL ``put_object`` on ``_slugs/{slug}`` using an *if-none-match*
  precondition that writes the owning ``tenant_id`` into the object body + metadata. The condition
  gives TENANT-scoped slug uniqueness (within-tenant only — there is NO global registry, OQ2) AND
  the slug→tenant mapping in ONE atomic step. A collision (the marker already exists) surfaces as a
  caller-safe :class:`SlugClaimConflict`, never a raw 500.
- **Resolve (Task 1.3):** a ``get_object`` on ``_slugs/{slug}`` → ``tenant_id``, scan-free. A miss
  (absent object, or an unreachable-as-empty read) returns ``None`` — never raises, never guesses a
  tenant (fail-safe, empty-is-valid; verify-before-trust, Property 2). The consuming
  :class:`~sam.members.domain.tenant_directory.TenantDirectory` maps that ``None`` to the uniform,
  non-probeable 404.

Reserved prefix (design D6)
---------------------------
``_slugs/`` is RESERVED: a real page slug may never be ``_slugs`` or begin ``_slugs/``, and the
marker objects deliberately live OUTSIDE any served ``{slug}/`` prefix — they are control plane,
never CloudFront-served. :func:`is_reserved_slug` is the single home of that rule; the write path
rejects a reserved slug fail-loud BEFORE any S3 call so a reserved name can never be claimed.

Account-agnostic CODE (design D2, migration-first)
--------------------------------------------------
The live-write path is dormant until the owner-run hosting migration (task 0.1) moves the
public-pages bucket to nonprofit. This module is account-agnostic: the bucket resolves lazily +
fail-fast from ``LANDING_PAGES_BUCKET`` (mirroring the landing publish path) and the boto3 S3 client
is injectable, so it is built + unit-tested now with a faked S3 client — no real AWS.

Layering (steering 35)
----------------------
SAM-plane **repository adapter**: it depends on boto3 + the fail-fast env helper and produces the
plain ``tenant_id`` string / raises a domain-shaped conflict. The domain never imports it; the
publish/edge wiring injects it. The format-validation authority stays
:mod:`sam.members.domain.form_slug` (reused, not duplicated) — this module adds only the
reserved-prefix rule and the S3 claim/resolve mechanism.
"""

from __future__ import annotations

from typing import Any

from services.dynamodb_client import REGION_ENV_VAR, require_env

__all__ = [
    "LANDING_PAGES_BUCKET_ENV_VAR",
    "SLUG_MARKER_PREFIX",
    "SlugClaimConflict",
    "S3SlugMarkerStore",
    "is_reserved_slug",
    "resolve_public_pages_bucket_name",
]

#: The env var carrying the shared public-pages bucket name (``myadmin-public-pages-<env>``),
#: mirroring the landing publish path (design C4 / §Data Models). No default is synthesized — a
#: missing/blank var fails fast via the one ``require_env`` helper (steering 23, no dangerous
#: fallback).
LANDING_PAGES_BUCKET_ENV_VAR = "LANDING_PAGES_BUCKET"

#: The RESERVED marker prefix (design D6). Marker objects are written at ``_slugs/{slug}`` —
#: OUTSIDE any served ``{slug}/`` prefix, so they are control plane and never CloudFront-served.
SLUG_MARKER_PREFIX = "_slugs/"


class SlugClaimConflict(Exception):
    """A caller-safe conflict: the slug is already claimed (the marker exists).

    Raised by :meth:`S3SlugMarkerStore.claim_slug` when the conditional ``put_object``'s
    *if-none-match* precondition fails — i.e. another claim already owns ``_slugs/{slug}``. The
    publish/write edge maps this to the standard caller-safe conflict envelope (never a raw 500 /
    stack trace). The message names only the slug, no internals.
    """

    def __init__(self, slug: str):
        self.slug = slug
        super().__init__(f"slug '{slug}' is already claimed")


def is_reserved_slug(slug: object) -> bool:
    """Return ``True`` when ``slug`` collides with the reserved ``_slugs/`` control-plane prefix.

    A real page slug may never be exactly ``_slugs`` nor begin with ``_slugs/`` (design D6) — those
    names would alias the marker control plane. Non-string / blank input is treated as reserved
    (``True``) so it is rejected fail-loud rather than silently claimed; genuine format validation
    (length, charset) stays with :func:`sam.members.domain.form_slug.validate_slug_format`.
    """
    if not isinstance(slug, str) or not slug:
        return True
    # Compare case-insensitively: the marker prefix is a fixed control-plane token, and slugs are
    # case-folded at the resolver, so ``_SLUGS`` must not sneak past as a distinct name.
    normalized = slug.strip().lower()
    marker = SLUG_MARKER_PREFIX.rstrip("/")  # "_slugs"
    return normalized == marker or normalized.startswith(SLUG_MARKER_PREFIX)


def resolve_public_pages_bucket_name() -> str:
    """Return the public-pages bucket name from ``LANDING_PAGES_BUCKET``, or fail fast.

    Reuses the T0 fail-fast client (:func:`services.dynamodb_client.require_env`) so the
    no-dangerous-fallback discipline lives in one place (steering 23).

    Raises:
        services.dynamodb_client.DynamoDBConfigError: ``LANDING_PAGES_BUCKET`` is missing/blank.
    """
    return require_env(LANDING_PAGES_BUCKET_ENV_VAR)


def _marker_key(slug: str) -> str:
    """Return the control-plane marker key ``_slugs/{slug}`` for a (reserved-checked) slug."""
    return f"{SLUG_MARKER_PREFIX}{slug}"


class S3SlugMarkerStore:
    """The S3-backed ``_slugs/{slug}`` claim + reverse-lookup store (OQ4 / design §Reverse-lookup).

    The S3 client + bucket name resolve LAZILY + fail-fast on first use so import touches no AWS;
    the client is injectable (dependency inversion) for tests. All I/O is confined to the reserved
    ``_slugs/`` prefix in the one public-pages bucket.

    Args:
        client: An optional boto3 S3 client (or a compatible fake). If omitted, resolved lazily on
            first use against the resolved region.
        bucket: An optional bucket name override. If omitted, resolved lazily + fail-fast from
            ``LANDING_PAGES_BUCKET`` on first use.
    """

    def __init__(self, *, client: Any = None, bucket: str | None = None):
        self._client = client
        self._bucket = bucket

    # ── lazy, fail-fast resource resolution ───────────────────────────────────────────

    @property
    def client(self):
        """The boto3 S3 client, resolved lazily + fail-fast on first use."""
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=require_env(REGION_ENV_VAR))
        return self._client

    @property
    def bucket(self) -> str:
        """The public-pages bucket name, resolved lazily + fail-fast from the env on first use."""
        if self._bucket is None:
            self._bucket = resolve_public_pages_bucket_name()
        return self._bucket

    # ── claim (Task 1.2) ───────────────────────────────────────────────────────────────

    def claim_slug(self, slug: str, tenant_id: str) -> None:
        """Claim ``_slugs/{slug}`` for ``tenant_id`` with a conditional (if-none-match) put.

        Writes the owning ``tenant_id`` into both the object body and ``x-amz-meta-tenant-id`` so
        the mapping survives whichever read path a later resolve takes, and uses the S3
        *if-none-match* precondition (``IfNoneMatch="*"``) so the write SUCCEEDS only when no marker
        exists yet — giving within-tenant uniqueness AND the mapping atomically (OQ4).

        Reserved-prefix guard (design D6): a slug that is ``_slugs`` or begins ``_slugs/`` (or a
        blank/non-string value) is rejected fail-loud with :class:`ValueError` BEFORE any S3 call,
        so a reserved name can never alias the marker control plane. ``tenant_id`` must be a
        non-blank string (the owner recorded in the marker).

        Raises:
            ValueError: the slug is reserved/blank, or ``tenant_id`` is blank.
            SlugClaimConflict: the marker already exists (if-none-match precondition failed) — a
                caller-safe conflict, NOT a 500.
        """
        if is_reserved_slug(slug):
            raise ValueError(
                f"'{slug}' is reserved (the '{SLUG_MARKER_PREFIX}' prefix is control-plane only) "
                "and cannot be claimed as a form slug"
            )
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-blank string to claim a slug")

        owner = tenant_id.strip()
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=_marker_key(slug),
                Body=owner.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
                Metadata={"tenant-id": owner},
                # Conditional write: succeed ONLY when the marker does not already exist. S3
                # returns a 412 PreconditionFailed (ClientError) when something is already there.
                IfNoneMatch="*",
            )
        except Exception as exc:  # noqa: BLE001 - narrow to precondition-failed below, re-raise rest
            if _is_precondition_failed(exc):
                raise SlugClaimConflict(slug) from exc
            raise

    # ── resolve (Task 1.3) ─────────────────────────────────────────────────────────────

    def resolve_slug(self, slug: str) -> str | None:
        """Return the owning ``tenant_id`` for ``_slugs/{slug}``, or ``None`` (fail-safe).

        Satisfies the :class:`sam.members.domain.tenant_directory.TenantSlugReader` Protocol by
        duck-typing so it drops straight into :class:`TenantDirectory`. A scan-free ``get_object``
        on the marker key; the ``tenant_id`` is read from the object body (falling back to the
        ``x-amz-meta-tenant-id`` metadata). Empty-is-valid / fail-safe throughout (design
        §Reverse-lookup, Property 2):

        - a reserved/blank/non-string slug → ``None`` WITHOUT touching S3 (a reserved name can
          never resolve to a tenant);
        - a MISSING marker (``NoSuchKey`` / ``404``) → ``None``;
        - a present-but-empty / whitespace body with no usable metadata → ``None``;

        so the resolver maps every miss to the ONE non-probeable 404 and never guesses a tenant. Any
        OTHER S3 error (a genuine fault, not a miss) propagates — the resolver's own seam contract
        treats that as no-match, keeping the public surface non-probeable even when the store is
        unreachable-as-empty.
        """
        if not isinstance(slug, str) or not slug or is_reserved_slug(slug):
            return None
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=_marker_key(slug))
        except Exception as exc:  # noqa: BLE001 - a missing marker is "no match", not an error
            if _is_not_found(exc):
                return None
            raise

        tenant_id = _read_body_tenant(response) or _read_metadata_tenant(response)
        return tenant_id or None


# ── structural S3-error classifiers (duck-typed; no botocore import at module scope) ──────


def _is_precondition_failed(exc: Exception) -> bool:
    """True when an S3 exception means the if-none-match precondition failed (slug already claimed).

    boto3 raises ``botocore.exceptions.ClientError`` carrying an ``Error.Code`` of
    ``PreconditionFailed`` (HTTP ``412``) when an ``IfNoneMatch="*"`` put hits an existing object.
    Read structurally (no botocore import at module scope) so a fake client in tests can raise a
    lookalike and this stays import-light — mirroring ``template_body_store._is_not_found``.
    """
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error", {}) if isinstance(response.get("Error"), dict) else {}
    if str(error.get("Code")) in {
        "PreconditionFailed",
        "412",
        "ConditionalRequestConflict",
    }:
        return True
    status = (
        response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if isinstance(response.get("ResponseMetadata"), dict)
        else None
    )
    return status == 412


def _is_not_found(exc: Exception) -> bool:
    """True when an S3 exception means "the marker does not exist" (vs a real failure).

    Mirrors :func:`sam.members.repository.template_body_store._is_not_found`: ``NoSuchKey`` /
    ``NotFound`` / HTTP ``404``, read structurally so a fake client's exception shapes work too.
    """
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error", {}) if isinstance(response.get("Error"), dict) else {}
    if str(error.get("Code")) in {"NoSuchKey", "404", "NotFound"}:
        return True
    status = (
        response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if isinstance(response.get("ResponseMetadata"), dict)
        else None
    )
    return status == 404


def _read_body_tenant(response: Any) -> str | None:
    """Read the ``tenant_id`` from a ``get_object`` response body, or ``None`` (empty-is-valid)."""
    if not isinstance(response, dict):
        return None
    body = response.get("Body")
    if body is None:
        return None
    raw = body.read() if hasattr(body, "read") else body
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    text = text.strip()
    return text or None


def _read_metadata_tenant(response: Any) -> str | None:
    """Read the ``tenant_id`` from the ``x-amz-meta-tenant-id`` metadata, or ``None``."""
    if not isinstance(response, dict):
        return None
    metadata = response.get("Metadata")
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("tenant-id") or metadata.get("tenant_id")
    value = value.strip() if isinstance(value, str) else None
    return value or None
