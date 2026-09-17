"""
Unit tests for the S4 D3 entitlement claim codec.

Covers R3.1 (versioned, documented shape + unknown-version safe fallback),
R3.2 (compact encoding within a bounded byte budget), and R3.3 (over-budget ->
overflow signal, never silent truncation). Property-based coverage is T10.

The codec is pure: these tests pass plain dict/str values — no DB, no mocks.

Reference: .kiro/specs/multi-tenant/s4-token-entitlement-projection/
"""

import json
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from auth.entitlement_claim_codec import (
    CLAIM_NAME,
    CLAIM_VERSION,
    DEFAULT_BUDGET_BYTES,
    DecodedEntitlements,
    decode_entitlements,
    encode_entitlements,
)


def _byte_len(value: str) -> int:
    return len(value.encode("utf-8"))


class TestConstants:
    """R3.1/R3.2 — the claim name, version, and byte budget are named constants."""

    def test_claim_name_is_custom_entitlements(self):
        assert CLAIM_NAME == "custom:entitlements"

    def test_claim_version_is_a_positive_int(self):
        assert isinstance(CLAIM_VERSION, int)
        assert CLAIM_VERSION >= 1

    def test_budget_is_bounded_and_well_under_token_limits(self):
        # 3 KiB — documented rationale: leaves headroom for the rest of the token.
        assert DEFAULT_BUDGET_BYTES == 3072


class TestRoundTripIdentity:
    """R3.1/R3.2 — encode -> decode reproduces the resolver's per-tenant map."""

    def test_round_trip_single_tenant(self):
        original = {"ExampleTenant": ["finance_read", "finance_create"]}
        decoded = decode_entitlements(encode_entitlements(original))

        assert decoded.fallback_required is False
        assert decoded.is_overflow is False
        assert decoded.version == CLAIM_VERSION
        # Normalised to sorted-unique on encode; decode preserves that.
        assert decoded.tenants == {"ExampleTenant": ["finance_create", "finance_read"]}
        assert decoded.tenant_keys == ["ExampleTenant"]

    def test_round_trip_multi_tenant(self):
        original = {
            "TenantA": ["finance_read"],
            "TenantB": ["str_read", "str_list"],
            "TenantC": [],  # belongs but no capabilities
        }
        decoded = decode_entitlements(encode_entitlements(original))

        assert decoded.tenants == {
            "TenantA": ["finance_read"],
            "TenantB": ["str_list", "str_read"],
            "TenantC": [],
        }
        assert decoded.tenant_keys == ["TenantA", "TenantB", "TenantC"]

    def test_round_trip_deduplicates_and_sorts(self):
        original = {"ExampleTenant": ["finance_read", "finance_read", "finance_create"]}
        decoded = decode_entitlements(encode_entitlements(original))
        assert decoded.tenants == {"ExampleTenant": ["finance_create", "finance_read"]}

    def test_capabilities_for_returns_list_for_present_tenant(self):
        decoded = decode_entitlements(
            encode_entitlements({"ExampleTenant": ["finance_read"]})
        )
        assert decoded.capabilities_for("ExampleTenant") == ["finance_read"]

    def test_capabilities_for_absent_tenant_returns_none(self):
        decoded = decode_entitlements(
            encode_entitlements({"ExampleTenant": ["finance_read"]})
        )
        # None => "token does not answer this tenant", not "no capabilities".
        assert decoded.capabilities_for("OtherTenant") is None


class TestEmptyMap:
    """R3.1 — an empty entitlement map round-trips to an empty (usable) claim."""

    def test_empty_map_encodes_and_decodes(self):
        decoded = decode_entitlements(encode_entitlements({}))
        assert decoded.fallback_required is False
        assert decoded.is_overflow is False
        assert decoded.tenants == {}
        assert decoded.tenant_keys == []


class TestCompactEncoding:
    """R3.2 — the encoding is compact (no whitespace) and versioned."""

    def test_encoding_has_no_whitespace(self):
        encoded = encode_entitlements({"ExampleTenant": ["finance_read"]})
        assert " " not in encoded
        assert "\n" not in encoded

    def test_encoding_contains_version_marker(self):
        encoded = encode_entitlements({"ExampleTenant": ["finance_read"]})
        parsed = json.loads(encoded)
        assert parsed["v"] == CLAIM_VERSION
        assert "t" in parsed

    def test_realistic_multi_tenant_user_fits_budget(self):
        # ~10 tenants x ~8 caps — a realistic multi-tenant admin stays in budget.
        caps = [f"module{n}_action" for n in range(8)]
        entitlement = {f"Tenant{i:02d}": list(caps) for i in range(10)}
        encoded = encode_entitlements(entitlement)
        assert _byte_len(encoded) <= DEFAULT_BUDGET_BYTES
        decoded = decode_entitlements(encoded)
        assert decoded.is_overflow is False
        assert len(decoded.tenants) == 10


class TestOverBudgetOverflowSignal:
    """R3.3 — over budget emits an overflow signal, never a truncated map."""

    def test_over_budget_sets_overflow_not_truncation(self):
        # Force overflow with a tiny budget so we don't need a huge input.
        entitlement = {
            "TenantA": ["finance_read", "finance_create"],
            "TenantB": ["str_read"],
        }
        encoded = encode_entitlements(entitlement, budget=20)
        parsed = json.loads(encoded)

        # Overflow signal present; capability map ("t") absent (not truncated).
        assert parsed.get("overflow") is True
        assert "t" not in parsed
        assert parsed["v"] == CLAIM_VERSION
        # The tenant list is preserved so the reader knows what to resolve.
        assert sorted(parsed["t_keys"]) == ["TenantA", "TenantB"]

    def test_decode_of_overflow_signals_reader_to_consult_server(self):
        entitlement = {"TenantA": ["finance_read"], "TenantB": ["str_read"]}
        decoded = decode_entitlements(encode_entitlements(entitlement, budget=20))

        assert decoded.is_overflow is True
        assert decoded.fallback_required is False
        # No per-user answer in the token; the tenant list drives the S3 lookup.
        assert decoded.tenants == {}
        assert decoded.tenant_keys == ["TenantA", "TenantB"]
        # capabilities_for must NOT return an answer for an overflow claim.
        assert decoded.capabilities_for("TenantA") is None

    def test_large_multi_tenant_map_near_budget_boundary(self):
        # A genuinely large user with the default budget goes overflow rather
        # than silently dropping tenants/capabilities.
        caps = [f"capability_token_{n:03d}" for n in range(40)]
        entitlement = {f"TenantNumber{i:03d}": list(caps) for i in range(60)}

        encoded = encode_entitlements(entitlement)  # default 3 KiB budget
        parsed = json.loads(encoded)

        assert parsed.get("overflow") is True
        assert "t" not in parsed
        # Every tenant the user belongs to is still enumerated for the fallback
        # (the overflow signal keeps the tenant list, drops only the caps).
        assert set(parsed["t_keys"]) == set(entitlement.keys())

    def test_at_budget_boundary_fits(self):
        # Construct an input whose normal encoding is exactly within budget.
        entitlement = {"T": ["read"]}
        encoded = encode_entitlements(entitlement)
        # Use the exact encoded length as the budget: must still be the normal form.
        exact = _byte_len(encoded)
        again = encode_entitlements(entitlement, budget=exact)
        assert json.loads(again).get("overflow") is None
        assert "t" in json.loads(again)

    def test_one_byte_over_budget_overflows(self):
        entitlement = {"T": ["read"]}
        encoded = encode_entitlements(entitlement)
        just_under = _byte_len(encoded) - 1
        result = encode_entitlements(entitlement, budget=just_under)
        assert json.loads(result).get("overflow") is True


class TestUnknownVersionSafeFallback:
    """R3.1 — a decoder on an unknown/missing version falls back, never crashes."""

    def test_unknown_version_returns_fallback(self):
        future = json.dumps({"v": 999, "t": {"TenantA": ["finance_read"]}})
        decoded = decode_entitlements(future)

        assert decoded.fallback_required is True
        assert decoded.is_overflow is False
        assert decoded.tenants == {}
        assert decoded.tenant_keys == []
        assert decoded.version == 999
        # A reader must not treat an unknown-version claim as an answer.
        assert decoded.capabilities_for("TenantA") is None

    def test_missing_version_returns_fallback(self):
        decoded = decode_entitlements(json.dumps({"t": {"TenantA": ["finance_read"]}}))
        assert decoded.fallback_required is True
        assert decoded.version is None

    def test_invalid_json_returns_fallback(self):
        decoded = decode_entitlements("{not valid json")
        assert decoded.fallback_required is True
        assert decoded.tenants == {}

    def test_non_string_non_mapping_returns_fallback(self):
        for value in (None, 42, ["a", "b"], 3.14):
            decoded = decode_entitlements(value)
            assert decoded.fallback_required is True, value

    def test_json_scalar_or_list_returns_fallback(self):
        assert decode_entitlements("123").fallback_required is True
        assert decode_entitlements('["a","b"]').fallback_required is True

    def test_recognised_version_but_malformed_map_returns_fallback(self):
        # v matches but "t" is not a mapping -> untrustworthy, fall back.
        bad = json.dumps({"v": CLAIM_VERSION, "t": ["not", "a", "map"]})
        decoded = decode_entitlements(bad)
        assert decoded.fallback_required is True

    def test_recognised_version_but_malformed_caps_returns_fallback(self):
        # A tenant's caps is a string, not a list -> untrustworthy, fall back.
        bad = json.dumps({"v": CLAIM_VERSION, "t": {"TenantA": "finance_read"}})
        decoded = decode_entitlements(bad)
        assert decoded.fallback_required is True


class TestDecodeAcceptsParsedDict:
    """Convenience: decode accepts an already-parsed dict as well as a string."""

    def test_decode_accepts_dict(self):
        claim = {"v": CLAIM_VERSION, "t": {"TenantA": ["finance_read"]}}
        decoded = decode_entitlements(claim)
        assert decoded.fallback_required is False
        assert decoded.tenants == {"TenantA": ["finance_read"]}
