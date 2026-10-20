"""
SAM config-write **version model** (spec: Members config — SAM-owned write path, Task 1.3).

The three SAM-owned ``config#*`` rows (``config#fields`` / ``config#scope`` / ``config#mail``)
carry their OWN row-level version model, DISTINCT from the retired Flask one. This module owns
exactly one concern: minting the row-level ``version`` write stamp the config-write domain
service (Task 1.5) stamps on every ``config#*`` put before delegating to
:class:`sam.members.repository.projection_config_write_repository.MembersConfigWriteRepository`.

Why its own model — the Flask ``_config_row_version`` is NOT ported (R6.3)
--------------------------------------------------------------------------
The Flask ProjectionSync builder computed a row version as the *max-of-params* across the MySQL
params that fed a row (``_config_row_version`` in ``_projection_config_builders.py``, the old
"version-bump-trap" fix). Once the SAM plane writes the row ATOMICALLY from a single authoring
door there is no second param to take the max of, so that logic is **dead code** — it is
deliberately NOT ported here (Requirement 6.3). The SAM stamp is a plain monotonic ISO-8601 UTC
marker instead.

What the stamp IS (and is NOT)
------------------------------
- **Ordering / when-last-written marker only** (R6.6/R6.7). ISO-8601 UTC sorts lexicographically
  in chronological order, so a later write yields a lexicographically-greater stamp than an
  earlier one (R6.2) — matching the live ``config#scope`` convention. It records WHEN the row was
  last written, for ordering.
- It does **NOT** gate what :class:`MembersProjectionReader` can read — a read never depends on
  the stamp (R6.6).
- It does **NOT** encode a config schema / shape / release version. Production runs a single
  codebase whose one reader interprets only the latest shape, so there is no per-row schema
  version to carry (R6.7, Requirement 24).
- It is **last-writer-wins** for Phase 1: the write path applies no conditional stale-write guard
  and the stamp stays an ordering marker, never a write gate (R6.8).

Separation from the consent-notice version (R6.5)
-------------------------------------------------
This row-level ``version`` (the ``VERSION_ATTR`` attribute on the DynamoDB item) is kept STRICTLY
SEPARATE from the domain-level ``application_consent_notice.version`` carried INSIDE the
``config#mail`` row body. They answer different questions — "when was this row last written"
(row stamp) vs. "which bilingual consent notice revision does a stamped application record pin"
(consent-notice version) — and neither is derived from the other. This helper mints only the
former; the consent-notice version lives entirely within the ``config#mail`` attributes
(see :mod:`sam.members.domain.consent_notice`).

Layering
--------
Pure domain helper: no ``boto3``, no DynamoDB, no table resolution — just the standard-library
clock. The repository (infrastructure) and the write service (domain) depend on it; it depends on
nothing in the plane. This keeps the version model trivially testable (Task 1.4) and lets the
write service compute the stamp without touching the storage layer.
"""

from __future__ import annotations

from datetime import datetime, timezone

__all__ = ["next_write_stamp"]


def next_write_stamp() -> str:
    """Return a monotonic ISO-8601 (UTC) write stamp for a SAM ``config#*`` put.

    The row-level ``version`` the config-write service stamps on every ``config#fields`` /
    ``config#scope`` / ``config#mail`` put (Requirement 6.1).

    Properties:
      - **Ordering-only / monotonic (R6.2, R6.6):** records when the row was last written; a
        later call produces a lexicographically-greater string (ISO-8601 UTC sorts
        chronologically). It does NOT gate what the Members reader reads.
      - **No schema version (R6.7):** it is NOT a config schema/shape/release version — the
        single production reader interprets only the latest shape.
      - **Last-writer-wins (R6.8):** Phase 1 applies no conditional stale-write guard; the stamp
        is purely an ordering marker, never a write gate.
      - **Separate from the consent notice (R6.5):** independent of the ``config#mail``
        ``application_consent_notice.version`` carried in the row body.

    Returns:
        A timezone-aware ISO-8601 UTC timestamp string (e.g. ``"2026-10-12T14:03:27.914233+00:00"``).
    """
    return datetime.now(timezone.utc).isoformat()
