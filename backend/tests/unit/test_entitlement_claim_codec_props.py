"""
S4 T10 — property-based proof of the entitlement claim codec.

Feature: s4-token-entitlement-projection, Property 5: Compact claim round-trips
and respects the budget.

This is the D3 codec's correctness guarantee. For any resolved per-tenant
entitlement map, the codec must:

  (a) Round-trip — encode→decode is identity for maps that fit the budget: the
      decoded claim is usable (``fallback_required=False``, ``is_overflow=False``)
      and its ``tenants`` equal the normalized (sorted-unique) input map.

  (b) Budget / overflow — for ANY map and ANY budget, the encoded value's UTF-8
      byte length is within budget OR the decoded claim is flagged overflow
      (never a silently truncated capability map). On overflow the decoded
      ``tenants`` is empty and ``tenant_keys`` lists exactly the input tenants,
      so the reader can consult the S3 projection for those tenants.

  (c) Unknown version — a claim re-encoded with a bumped/unknown ``v`` decodes
      to ``fallback_required=True``; the decoder never mis-parses a future
      format as an answer.

The codec is pure (no I/O, no clock, no env), so Hypothesis can drive it
directly with no DB, no mocks.

Validates: Requirements R3.1, R3.2, R3.3

Reference: .kiro/specs/multi-tenant/s4-token-entitlement-projection/
  design.md "Correctness Properties → Property 5"; requirements R3.1 (versioned,
  documented shape + unknown-version fallback), R3.2 (compact, bounded budget),
  R3.3 (over-budget → overflow signal, never silent truncation).
"""

import json
import os
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from auth.entitlement_claim_codec import (
    CLAIM_VERSION,
    DEFAULT_BUDGET_BYTES,
    DecodedEntitlements,
    decode_entitlements,
    encode_entitlements,
)


# ---------------------------------------------------------------------------
# Generators — resolver-output-shaped per-tenant entitlement maps.
#
# Shape mirrors resolve_entitlement's output: {tenant -> [capability, ...]}.
# Strings deliberately include unicode so the UTF-8 byte-budget path is exercised
# (a capability/tenant may be multi-byte). Capability lists may be empty (the
# tenant belongs but grants nothing) and may contain duplicates (the codec
# normalizes to sorted-unique), matching the resolver's contract.
# ---------------------------------------------------------------------------

# Non-empty text incl. unicode; the codec drops falsy caps, so keep caps truthy.
_TENANT_ST = st.text(min_size=1, max_size=12)
_CAP_ST = st.text(min_size=1, max_size=12)


def _normalise(entitlement_map):
    """Reference normalization: {tenant -> sorted(unique truthy caps)}.

    Mirrors the codec's internal ``_normalise_map`` so the round-trip assertion
    compares against the same canonical form the codec commits to.
    """
    return {
        tenant: sorted({c for c in (caps or []) if c})
        for tenant, caps in entitlement_map.items()
    }


# A per-tenant entitlement map of varying size (0..8 tenants, 0..8 caps each).
entitlement_map_st = st.dictionaries(
    keys=_TENANT_ST,
    values=st.lists(_CAP_ST, min_size=0, max_size=8),
    min_size=0,
    max_size=8,
)


class TestClaimRoundTripAndBudget:
    """Feature: s4-token-entitlement-projection, Property 5: Compact claim
    round-trips and respects the budget.

    Validates: Requirements R3.1, R3.2, R3.3
    """

    # (a) Round-trip identity for maps that fit the budget --------------------
    @settings(max_examples=200)
    @given(entitlement_map=entitlement_map_st)
    def test_round_trip_is_identity_within_budget(self, entitlement_map):
        """(a) A map that fits the default budget round-trips to itself.

        encode→decode yields a usable claim whose ``tenants`` equal the
        normalized (sorted-unique) input. Realistic maps generated here are far
        below the 3 KiB budget, so this exercises the normal (non-overflow) form.
        """
        encoded = encode_entitlements(entitlement_map)

        # Precondition for the identity claim: it actually fit the budget (the
        # normal form was emitted, not the overflow signal).
        assert len(encoded.encode("utf-8")) <= DEFAULT_BUDGET_BYTES
        assert json.loads(encoded).get("overflow") is None

        decoded = decode_entitlements(encoded)

        assert isinstance(decoded, DecodedEntitlements)
        assert decoded.fallback_required is False
        assert decoded.is_overflow is False
        assert decoded.version == CLAIM_VERSION
        # Identity: decoded map equals the normalized input map.
        assert decoded.tenants == _normalise(entitlement_map)
        assert sorted(decoded.tenant_keys) == sorted(entitlement_map.keys())

    # (b) Budget / overflow invariant for ANY map + ANY budget ----------------
    @settings(max_examples=200)
    @given(
        entitlement_map=entitlement_map_st,
        # Mix tiny budgets (force overflow on small maps) with the default and
        # larger budgets, so both branches are driven.
        budget=st.integers(min_value=1, max_value=4096),
    )
    def test_fits_budget_or_signals_overflow_never_truncates(
        self, entitlement_map, budget
    ):
        """(b) For any map + any budget: within budget OR flagged overflow.

        The encoded value's UTF-8 byte length is ≤ budget, or the decoded claim
        is overflow — never a silently truncated capability map. On overflow the
        decoded ``tenants`` is empty and ``tenant_keys`` lists exactly the input
        tenants (so the reader can consult S3).
        """
        encoded = encode_entitlements(entitlement_map, budget=budget)
        decoded = decode_entitlements(encoded)
        encoded_len = len(encoded.encode("utf-8"))

        # The core invariant: fits the budget, or is explicitly overflow.
        assert encoded_len <= budget or decoded.is_overflow is True

        normalised = _normalise(entitlement_map)

        if decoded.is_overflow:
            # Overflow is never a partial answer: no capability map at all,
            # and the tenant list is preserved exactly for the S3 fallback.
            assert decoded.fallback_required is False
            assert decoded.tenants == {}
            assert sorted(decoded.tenant_keys) == sorted(normalised.keys())
        else:
            # Non-overflow => it fit, and is a faithful (non-truncated) map.
            assert encoded_len <= budget
            assert decoded.fallback_required is False
            assert decoded.tenants == normalised

    @settings(max_examples=100)
    @given(entitlement_map=entitlement_map_st)
    def test_tiny_budget_forces_overflow_signal(self, entitlement_map):
        """(b) A 1-byte budget forces the overflow signal on any map.

        Even the empty normal form ``{"v":1,"t":{}}`` exceeds 1 byte, so the
        codec must emit the overflow signal (never truncate) and the reader must
        see it flagged. tenant_keys still enumerates every input tenant.
        """
        encoded = encode_entitlements(entitlement_map, budget=1)
        decoded = decode_entitlements(encoded)

        assert decoded.is_overflow is True
        assert decoded.fallback_required is False
        assert decoded.tenants == {}
        assert sorted(decoded.tenant_keys) == sorted(entitlement_map.keys())

    @settings(max_examples=100)
    @given(
        # Many tenants x many long unicode caps => exceeds the default 3 KiB.
        n_tenants=st.integers(min_value=40, max_value=80),
    )
    def test_default_budget_overflows_on_large_maps(self, n_tenants):
        """(b) A large realistic map exceeds the DEFAULT budget → overflow.

        Drives the default-budget overflow branch (not just tiny budgets): a
        user large enough to blow the 3 KiB budget yields the overflow signal
        with the full tenant list preserved, never a truncated capability map.
        """
        caps = [f"capability_token_{n:03d}" for n in range(20)]
        entitlement_map = {f"TenantNumber{i:04d}": list(caps) for i in range(n_tenants)}

        encoded = encode_entitlements(entitlement_map)  # default 3 KiB budget
        assert len(encoded.encode("utf-8")) > 0
        decoded = decode_entitlements(encoded)

        assert decoded.is_overflow is True
        assert decoded.tenants == {}
        assert sorted(decoded.tenant_keys) == sorted(entitlement_map.keys())

    # (c) Unknown version → fallback (never mis-parse a future format) --------
    @settings(max_examples=100)
    @given(
        entitlement_map=entitlement_map_st,
        # Any version marker that is not the current one (below or above).
        bumped_version=st.integers(min_value=CLAIM_VERSION + 1, max_value=10_000),
    )
    def test_unknown_version_decodes_to_fallback(
        self, entitlement_map, bumped_version
    ):
        """(c) A claim with a bumped/unknown ``v`` decodes to fallback.

        We construct a well-formed claim payload but stamp it with an unknown
        version; the decoder must set ``fallback_required=True`` and NOT surface
        the map — a reader must never mistake a future format for an answer.
        """
        normalised = _normalise(entitlement_map)
        unknown_claim = json.dumps(
            {"v": bumped_version, "t": normalised},
            separators=(",", ":"),
            ensure_ascii=False,
        )

        decoded = decode_entitlements(unknown_claim)

        assert decoded.fallback_required is True
        # Never mis-parses the future payload as a usable answer.
        assert decoded.is_overflow is False
        assert decoded.tenants == {}
