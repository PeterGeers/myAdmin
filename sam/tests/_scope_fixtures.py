"""Shared test fixtures for the scope-dimension model.

Phase 2 (Members config redesign) §6.2 / R7: the synthetic ``SAMPLE_SCOPE_CONFIG``
scope-dimension fixture lives HERE, in the test tree — not in the storage-agnostic
``sam.members.domain.scope_dimensions`` module (steering 35: "fixtures live with
tests"; Decision D16/D17: no tenant/synthetic vocabulary in the domain). The scope
MODEL (``ScopeDimension`` / ``ScopeConfig`` / ``WILDCARD`` / the providers) stays in the
domain; only this sample DATA moves into tests.

This is a TEST FIXTURE ONLY — never a runtime source and never a runtime fallback
(Decision D16): a missing/failed projection is a system error, not a silent substitution
to this constant. A tenant's real region vocabulary lives ONLY in its
``members.scope_dimensions`` parameter (MySQL, authored at onboarding) → projected to
``config#scope`` → read by the SAM edge via the ``ScopeConfigProvider``.

The values are ABSTRACT synthetic values (``North/South/East/West``) that are obviously
NOT a real Dutch region set — just enough to exercise the scope MECHANISM in unit tests.
"""

from __future__ import annotations

from sam.members.domain.scope_dimensions import ScopeDimension

__all__ = ["SAMPLE_SCOPE_CONFIG"]

#: REFERENCE / TEST FIXTURE ONLY — **not** any tenant's config and **not** a runtime source.
#: ABSTRACT synthetic region dimension (``North/South/East/West``). Setting ``enabled=False``
#: (or an empty list) collapses to tenant-wide with no code path change (R3.2).
SAMPLE_SCOPE_CONFIG: tuple[ScopeDimension, ...] = (
    ScopeDimension(
        key="region",
        # field defaults to key ("region") — binds to the member's `region` field.
        label={"en": "Region"},
        enabled=True,
        # ABSTRACT synthetic values ONLY (D17) — deliberately NOT a real region set, so no
        # tenant's vocabulary lives in a shared/core fixture. A tenant's real regions are
        # authored in its `members.scope_dimensions` param / the onboarding data file.
        values=(
            "North",
            "South",
            "East",
            "West",
        ),
        required_for=("Members_CRUD",),
    ),
)
