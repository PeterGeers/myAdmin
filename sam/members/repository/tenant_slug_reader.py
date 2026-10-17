"""
Members application (public intake) — the concrete **slug → ``tenant_id`` reader** (application-app
Task 1.3; D19/R2.1–R2.3; design §1/§2 step 2, §11a "Slug→tenant resolver" row).

The SAM-plane concrete that satisfies the storage-agnostic
:class:`sam.members.domain.tenant_directory.TenantSlugReader` Protocol the Task-1.2 resolver
depends on. It answers ONE question — *what canonical ``tenant_id`` does this already-normalized
public path slug map to, if any?* — and nothing else. The :class:`TenantDirectory` resolver owns
normalization (trim + case-fold) and the uniform non-probeable not-found; this reader is the thin,
fail-safe lookup behind that seam.

The slug truth source — D19 (reuse the landing-page slug mechanism, NO new directory store)
--------------------------------------------------------------------------------------------
The public slug is the SAME slug the landing pages already use — ``<slug>.jabaki.nl`` (host-based,
slug == tenant slug) plus the custom-domain→slug CloudFront KeyValueStore
``myadmin-domain-slug-mapping`` (``infrastructure/landing-pages.tf``). There is **NO new
``tenant-directory`` store**. The public SAM edge reads slug→``tenant_id`` from a thin SAM-plane
PROJECTION of that landing mapping, kept behind this seam so the resolver stays storage-agnostic
and the Flask⇄SAM boundary stays clean (the edge never calls Flask, never reads the landing KVS
directly from the request path).

Why an env-backed allow-list is the thin projection (task-1.3 scope)
--------------------------------------------------------------------
Task 1.3 is the ROUTE / API / CORS wiring — it needs a concrete reader to CLOSE the resolver seam,
not the full landing-KVS integration (that is the deploy-side seeding in Phase 7/10, see §11a "+ a
thin slug→tenant_id projection seeded from the landing mapping"). So the concrete here reads the
projection as a comma / mapping env var (:data:`SLUG_MAP_ENV`, ``<slug>:<tenant_id>`` pairs) the
public function's stack supplies — the smallest honest projection of the landing mapping that keeps
the boundary clean and the wiring complete and testable without boto3 or the CloudFront KVS. The
backing store is intentionally hidden behind :meth:`resolve_slug`: swapping this env projection for
a DynamoDB-row / direct-KVS read later is a localized change to THIS file, never a ripple through
the resolver (:class:`TenantDirectory`) or the edge (``handler/public_app.py``).

Fail-safe / empty-is-valid (R2.3 / R1a.4)
-----------------------------------------
Mirrors the read discipline of :class:`~sam.members.repository.projection_config_reader.MembersProjectionReader`:
an unknown slug, a missing / blank / malformed mapping, or an unreadable env all resolve to
``None`` (no match) — NEVER a raise and NEVER a guessed tenant. The resolver maps every such miss
to the ONE uniform non-probeable 404, so the allow-list cannot be used as an enumeration oracle.
The map is resolved at call time (not import time) so a stack param / a test ``monkeypatch.setenv``
is honoured without reloading the module — the same late-binding the public edge's CORS allow-list
uses.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

__all__ = ["SLUG_MAP_ENV", "EnvTenantSlugReader"]

#: The env var the public API's stack (task 1.3 / samconfig) sets with the thin slug→``tenant_id``
#: projection of the landing mapping (D19). Format: comma-separated ``<slug>:<tenant_id>`` pairs,
#: e.g. ``"hdcn:h-dcn,zktk:zktk-tenant"``. Unset / empty → an EMPTY allow-list (fail-safe: every
#: slug is not-found), never a guessed tenant. Resolved at call time so a redeploy is not needed
#: to re-seed it and a test can ``monkeypatch.setenv`` it.
SLUG_MAP_ENV = "PUBLIC_TENANT_SLUG_MAP"


class EnvTenantSlugReader:
    """Concrete :class:`TenantSlugReader` backed by the thin env-projection of the landing slug map.

    Satisfies the :class:`sam.members.domain.tenant_directory.TenantSlugReader` Protocol by
    duck-typing (one method, :meth:`resolve_slug`). It is injected into :class:`TenantDirectory`
    at the public edge (``handler/public_app.py``, task 1.3). Storage detail — reading the
    projection as the :data:`SLUG_MAP_ENV` env var — lives ENTIRELY here; the resolver and the
    edge never know where the mapping comes from.

    The reader trusts the resolver to have already normalized the slug (trim + case-fold). It
    still normalizes BOTH sides of its own parsed map defensively (lower-cased keys) so a mapping
    authored with stray case/whitespace still matches the resolver's normalized lookup — the two
    cannot drift. Empty-is-valid throughout: a blank / malformed pair is skipped, a blank value is
    not a match.
    """

    def resolve_slug(self, slug: str) -> str | None:
        """Return the canonical ``tenant_id`` for an allow-listed ``slug``, else ``None`` (D19).

        Args:
            slug: the ALREADY-normalized (trimmed + lower-cased by :class:`TenantDirectory`)
                public path slug.

        Returns:
            The canonical ``tenant_id`` the thin projection maps ``slug`` to, or ``None`` when the
            slug is not on the allow-list (unknown / forged) OR the projection is empty /
            unreadable. ``None`` is the ONLY not-found signal — the reader never raises and never
            invents a tenant, so the resolver inherits its non-probeable, verify-before-trust
            behaviour (R2.3 / R1a.4).
        """
        if not isinstance(slug, str) or not slug:
            return None
        return self._slug_map().get(slug)

    @staticmethod
    def _slug_map() -> dict[str, str]:
        """Parse :data:`SLUG_MAP_ENV` into a ``{normalized_slug: tenant_id}`` allow-list.

        Resolved at call time (not import) so a stack param / a test ``monkeypatch.setenv`` is
        honoured without reloading. Each entry is a ``<slug>:<tenant_id>`` pair; only the FIRST
        ``:`` splits (a ``tenant_id`` never carries one, but this is defensive). A pair missing a
        slug or a tenant is SKIPPED (empty-is-valid) rather than raising — a malformed projection
        degrades to a smaller allow-list, never a crash on a public request. Keys are lower-cased
        to match the resolver's case-folded lookup; a later duplicate slug wins (last-write).
        """
        raw = os.environ.get(SLUG_MAP_ENV, "") or ""
        allow_list: dict[str, str] = {}
        for pair in raw.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            slug_part, _, tenant_part = pair.partition(":")
            slug_key = slug_part.strip().lower()
            tenant_id = tenant_part.strip()
            if slug_key and tenant_id:
                allow_list[slug_key] = tenant_id
        return allow_list
