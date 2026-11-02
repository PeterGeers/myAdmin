"""
S3 + CloudFront **public-page artifact store** — the SERVED ``{slug}/`` publish adapter.

This is the repository adapter spec 14 Task 9.1 lifts the DORMANT live write onto: it owns the
actual publish of a producer's SERVED artifacts (``{slug}/index.html`` + ``{slug}/form.json``)
to the shared public-pages bucket, plus the (best-effort) CloudFront invalidation for the slug
path. It sits AFTER the control-plane slug claim (:class:`S3SlugMarkerStore`) in the publish
flow; the two touch DIFFERENT key spaces and must never be conflated:

- the **slug marker** store writes ``_slugs/{slug}`` — the control-plane owner marker, NEVER
  CloudFront-served (design D6);
- THIS store writes ``{slug}/index.html`` + ``{slug}/form.json`` under the served ``{slug}/``
  prefix — the public content CloudFront maps ``{slug}.jabaki.nl`` to.

Why a repository (steering 35/39)
---------------------------------
No ``boto3`` in the domain service. The publish domain
(:class:`sam.members.domain.application_publish.ApplicationPublishService`) depends only on the
small :class:`sam.members.domain.application_publish.PublicPageArtifactWriter` Protocol; this
adapter is the SAM-plane concrete that satisfies it. The S3 + CloudFront clients are lazy +
injectable (dependency inversion), so the publish flow builds + unit-tests NOW against an
in-memory fake client — no real AWS (mirroring :class:`S3SlugMarkerStore`'s pattern).

Bucket / distribution resolution (MIRRORS the landing publish path)
-------------------------------------------------------------------
The bucket resolves from ``LANDING_PAGES_BUCKET`` and the CloudFront distribution from
``CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID`` — the EXACT env vars
``backend/src/services/landing_page_publish_service.py`` already uses — so the SAM publish and
the Flask landing publish resolve the SAME nonprofit bucket/distribution (the hosting migration
owns both; D7 reconciliation — never a parallel/new resource). The bucket is fail-fast
(``require_env``, no dangerous fallback, steering 23); the distribution id is OPTIONAL — a blank
value means "no invalidation configured" and the publish still succeeds (see below).

CloudFront invalidation is BEST-EFFORT / NON-FATAL (known-deferred — Task 9.2)
------------------------------------------------------------------------------
The ``put_object`` writes ARE the authoritative publish: once the artifact bytes are in the
bucket, the page IS published. The CloudFront invalidation is a cache-freshness optimisation
layered on top, and it is CURRENTLY EXPECTED TO FAIL: the Railway publish identity
(``myadmin-railway-backend``) lacks ``cloudfront:CreateInvalidation`` and the invalidation ARN
is built for the PERSONAL account while the ``*.jabaki.nl`` distribution lives in NONPROFIT
(hosting-migration finding). So this adapter treats ANY invalidation error as non-fatal — it is
LOGGED (caller-safe, no stack to the client) and SWALLOWED; the publish returns success because
the artifact is already written. Consequence (documented, accepted short-term): a NEW page
appears immediately; an UPDATE to an existing page appears after the CloudFront TTL (≤ 1h).
Task 9.2 (SEC-8 IAM) grants the permission + fixes the ARN so the invalidation SUCCEEDS — and it
can do so WITHOUT touching this flow, because the put-succeeds-then-invalidate-best-effort
structure here does not change.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from services.dynamodb_client import REGION_ENV_VAR, require_env

from sam.members.repository.slug_marker_store import (
    LANDING_PAGES_BUCKET_ENV_VAR,
    is_reserved_slug,
    resolve_public_pages_bucket_name,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CLOUDFRONT_DISTRIBUTION_ENV_VAR",
    "INDEX_ARTIFACT_NAME",
    "FORM_JSON_ARTIFACT_NAME",
    "S3PublicPageArtifactStore",
]

#: The env var carrying the CloudFront distribution id for the public-pages (``*.jabaki.nl``)
#: distribution — the SAME var ``landing_page_publish_service`` reads, so the SAM publish and the
#: landing publish invalidate the SAME distribution. OPTIONAL: a blank/absent value means "no
#: invalidation configured" (the publish still succeeds; the artifact write is authoritative).
CLOUDFRONT_DISTRIBUTION_ENV_VAR = "CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID"

#: The served rendered-page artifact name under the ``{slug}/`` prefix.
INDEX_ARTIFACT_NAME = "index.html"

#: The served form-data artifact name under the ``{slug}/`` prefix (the schema/config the
#: published shell fetches).
FORM_JSON_ARTIFACT_NAME = "form.json"


class S3PublicPageArtifactStore:
    """Write a producer's SERVED ``{slug}/`` artifacts + best-effort invalidate (Task 9.1).

    The S3 + CloudFront clients and the bucket name resolve LAZILY + fail-fast on first use so
    import touches no AWS; all three are injectable for tests. Writes are confined to the served
    ``{slug}/`` prefix — NEVER the reserved ``_slugs/`` control-plane prefix (a reserved slug is
    rejected fail-loud before any S3 call).

    Args:
        s3_client: An optional boto3 S3 client (or a compatible fake). Resolved lazily on first
            use if omitted.
        cloudfront_client: An optional boto3 CloudFront client (or a compatible fake). Resolved
            lazily on first use if omitted.
        bucket: An optional bucket-name override. Resolved lazily + fail-fast from
            ``LANDING_PAGES_BUCKET`` on first use if omitted.
        distribution_id: An optional CloudFront distribution-id override. Resolved lazily from
            ``CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID`` on first use if omitted; a blank value
            means "no invalidation configured".
    """

    def __init__(
        self,
        *,
        s3_client: Any = None,
        cloudfront_client: Any = None,
        bucket: str | None = None,
        distribution_id: str | None = None,
    ):
        self._s3 = s3_client
        self._cloudfront = cloudfront_client
        self._bucket = bucket
        self._distribution_id = distribution_id

    # ── lazy, fail-fast resource resolution ───────────────────────────────────────────

    @property
    def s3(self):
        """The boto3 S3 client, resolved lazily + fail-fast on first use."""
        if self._s3 is None:
            import boto3

            self._s3 = boto3.client("s3", region_name=require_env(REGION_ENV_VAR))
        return self._s3

    @property
    def cloudfront(self):
        """The boto3 CloudFront client, resolved lazily + fail-fast on first use."""
        if self._cloudfront is None:
            import boto3

            self._cloudfront = boto3.client(
                "cloudfront", region_name=require_env(REGION_ENV_VAR)
            )
        return self._cloudfront

    @property
    def bucket(self) -> str:
        """The public-pages bucket name, resolved lazily + fail-fast from the env on first use."""
        if self._bucket is None:
            self._bucket = resolve_public_pages_bucket_name()
        return self._bucket

    @property
    def distribution_id(self) -> str:
        """The CloudFront distribution id (``""`` when not configured — invalidation skipped)."""
        if self._distribution_id is None:
            import os

            self._distribution_id = os.environ.get(
                CLOUDFRONT_DISTRIBUTION_ENV_VAR, ""
            ).strip()
        return self._distribution_id

    # ── publish (Task 9.1 — the lifted live write) ─────────────────────────────────────

    def publish_artifacts(
        self, slug: str, *, index_html: str, form_json: bytes
    ) -> None:
        """Write ``{slug}/index.html`` + ``{slug}/form.json`` then best-effort invalidate.

        The two ``put_object`` calls are the AUTHORITATIVE publish (once the bytes are in the
        bucket the page is live); the CloudFront invalidation is layered on top and is
        BEST-EFFORT / NON-FATAL (see module docstring — a denied/failed invalidation is logged and
        swallowed, Task 9.2 fixes the IAM/ARN without touching this flow). Both artifacts live
        under the SERVED ``{slug}/`` prefix — distinct from the ``_slugs/{slug}`` control-plane
        marker.

        Args:
            slug: The (format-/ownership-validated upstream) page slug. Rejected fail-loud here
                only if it is reserved/blank (it must never alias the ``_slugs/`` control plane).
            index_html: The rendered page HTML (the shared ``page_shell`` artifact).
            form_json: The serialized form-data artifact bytes the published shell fetches.

        Raises:
            ValueError: the slug is reserved/blank (never a served prefix).
        """
        if is_reserved_slug(slug):
            raise ValueError(
                f"'{slug}' is reserved (the '_slugs/' prefix is control-plane only) "
                "and cannot be used as a served page prefix"
            )

        html_bytes = (
            index_html.encode("utf-8") if isinstance(index_html, str) else index_html
        )
        # 1. index.html — the rendered page (shared page_shell artifact).
        self.s3.put_object(
            Bucket=self.bucket,
            Key=f"{slug}/{INDEX_ARTIFACT_NAME}",
            Body=html_bytes,
            ContentType="text/html; charset=utf-8",
            CacheControl="public, max-age=300",
        )
        # 2. form.json — the form schema/config the published shell fetches.
        self.s3.put_object(
            Bucket=self.bucket,
            Key=f"{slug}/{FORM_JSON_ARTIFACT_NAME}",
            Body=form_json,
            ContentType="application/json",
            CacheControl="public, max-age=300",
        )
        logger.info(
            "Published served artifacts to s3://%s/%s/ (index.html + form.json)",
            self.bucket,
            slug,
        )

        # 3. CloudFront invalidation — BEST-EFFORT / NON-FATAL (Task 9.2 fixes the IAM/ARN).
        self._invalidate(slug)

    def _invalidate(self, slug: str) -> None:
        """Invalidate the slug's CloudFront paths — best-effort, NON-FATAL (Task 9.2 deferral).

        A missing distribution id (not configured) or ANY CloudFront error (notably the currently
        KNOWN-DEFERRED permission-denied / wrong-account-ARN failure — the Railway publish identity
        lacks ``cloudfront:CreateInvalidation`` and the ARN targets personal, not nonprofit) is
        LOGGED (caller-safe) and SWALLOWED. The artifact ``put_object``s above are the authoritative
        publish, so the publish MUST succeed even when this raises. Task 9.2 (SEC-8 IAM) grants the
        permission + corrects the ARN so the invalidation succeeds — WITHOUT touching this flow.
        """
        if not self.distribution_id:
            logger.warning(
                "%s not set — skipping CloudFront invalidation for slug=%s "
                "(artifact already written; update visible after cache TTL)",
                CLOUDFRONT_DISTRIBUTION_ENV_VAR,
                slug,
            )
            return
        try:
            self.cloudfront.create_invalidation(
                DistributionId=self.distribution_id,
                InvalidationBatch={
                    "Paths": {"Quantity": 2, "Items": [f"/{slug}/*", f"/{slug}"]},
                    "CallerReference": (
                        f"{slug}-{datetime.now(timezone.utc).isoformat()}"
                    ),
                },
            )
            logger.info("CloudFront invalidation created for slug=%s", slug)
        except Exception as exc:  # noqa: BLE001 - best-effort: a denied/failed invalidation
            # is NON-FATAL (known-deferred to Task 9.2). The artifact is already written, so the
            # publish still succeeds; we only lose immediate cache-freshness on an UPDATE.
            logger.warning(
                "CloudFront invalidation failed for slug=%s (non-fatal, deferred to Task 9.2 "
                "SEC-8 IAM): %s",
                slug,
                exc,
            )


# Re-export the bucket env var name for callers that resolve/mirror it alongside the distribution.
_ = LANDING_PAGES_BUCKET_ENV_VAR
