"""
S4 / T14 — drift guard for the VENDORED entitlement decoder.

``sam/shared/entitlement_claim.py`` is a vendored mirror of the *decode* half of the
single-source codec ``backend/src/auth/entitlement_claim_codec.py`` (T4). The
``sam/shared`` layer must stay standalone (no ``backend/src`` import in production),
so the decoder is copied — and a copy can drift.

This test is the ONE place that reaches into ``backend/src`` (guarded, and only for the
test) to decode a shared set of claim vectors through BOTH the vendored decoder and the
backend source codec, asserting they produce identical results field-for-field. It also
pins the shared constants (``CLAIM_NAME`` / ``CLAIM_VERSION``). If the format ever
changes in the single source, this test fails until the vendored copy is re-synced.

If ``backend/src`` is not importable in this environment the drift comparison is
skipped (the vendored decoder is still exercised directly by test_entitlement_reader.py
and the standalone assertions below).
"""

import json
import os
import sys

import pytest

from sam.shared import entitlement_claim as vendored

# --- Guarded import of the single-source backend codec (test-only) ---------- #
# The sam/shared PRODUCTION code never imports backend/src; this DRIFT TEST is the sole
# exception and localises the sys.path tweak here, not in the shipped module.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

try:
    from auth import entitlement_claim_codec as source  # type: ignore
except Exception:  # pragma: no cover - environment without backend/src
    source = None


# A representative set of claim vectors covering every decode branch.
def _vectors():
    return [
        # normal, single tenant
        json.dumps({"v": 1, "t": {"GoodwinSolutions": ["finance_read"]}}),
        # normal, multi-tenant + empty caps list
        json.dumps(
            {"v": 1, "t": {"A": ["x", "y"], "B": [], "Unicödé": ["z"]}},
            separators=(",", ":"),
        ),
        # overflow signal
        json.dumps({"v": 1, "overflow": True, "t_keys": ["B", "A"]}),
        # unknown version -> fallback
        json.dumps({"v": 999, "t": {"A": ["x"]}}),
        # missing version -> fallback
        json.dumps({"t": {"A": ["x"]}}),
        # malformed t (not a mapping) at a recognised version -> fallback
        json.dumps({"v": 1, "t": ["not", "a", "map"]}),
        # malformed cap list (a string, not a list) -> fallback
        json.dumps({"v": 1, "t": {"A": "finance_read"}}),
        # invalid JSON string -> fallback
        "not-json",
        # a dict passed straight through (readers/tests convenience)
        {"v": 1, "t": {"A": ["x"]}},
        # non-decodable scalar -> fallback
        None,
        12345,
        ["a", "list"],
    ]


def _as_tuple(decoded):
    """Field-for-field snapshot of a DecodedEntitlements for equality comparison."""
    return (
        decoded.version,
        {k: list(v) for k, v in decoded.tenants.items()},
        list(decoded.tenant_keys),
        decoded.is_overflow,
        decoded.fallback_required,
    )


def test_vendored_constants_match_source_or_pinned_values():
    """CLAIM_NAME / CLAIM_VERSION are pinned; when the source is present they match it."""
    assert vendored.CLAIM_NAME == "custom:entitlements"
    assert vendored.CLAIM_VERSION == 1
    if source is not None:
        assert vendored.CLAIM_NAME == source.CLAIM_NAME
        assert vendored.CLAIM_VERSION == source.CLAIM_VERSION


@pytest.mark.skipif(
    "source is None", reason="backend/src not importable in this environment"
)
@pytest.mark.parametrize("vector", _vectors())
def test_vendored_decoder_matches_source_codec(vector):
    """The vendored decoder must decode identically to the single-source codec."""
    assert _as_tuple(vendored.decode_entitlements(vector)) == _as_tuple(
        source.decode_entitlements(vector)
    )


def test_vendored_decoder_capabilities_for_matches_source():
    """capabilities_for() also agrees between the vendored copy and the source."""
    if source is None:
        pytest.skip("backend/src not importable")
    claim = json.dumps({"v": 1, "t": {"A": ["x", "y"], "B": []}})
    v = vendored.decode_entitlements(claim)
    s = source.decode_entitlements(claim)
    for tenant in ("A", "B", "MISSING"):
        assert v.capabilities_for(tenant) == s.capabilities_for(tenant)
    # overflow / fallback both yield None from capabilities_for on both impls.
    for bad in (
        json.dumps({"v": 1, "overflow": True, "t_keys": ["A"]}),
        json.dumps({"v": 999}),
    ):
        assert (
            vendored.decode_entitlements(bad).capabilities_for("A")
            == source.decode_entitlements(bad).capabilities_for("A")
        )
