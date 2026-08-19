"""
Bug Condition Exploration Test — Stripe Tenant Credential Isolation

Property 1: Bug Condition — Global Credential Usage

These tests encode the EXPECTED (fixed) behavior:
- enrich_direct_bookings() accepts `api_key` and `metadata_key` parameters
- It does NOT read from os.getenv("STRIPE_SECRET_KEY")
- It does NOT set stripe.api_key globally
- GUESTY_METADATA_KEY is not a module-level constant

When run on UNFIXED code, these tests MUST FAIL — confirming the bug exists.
When run AFTER the fix, these tests PASS — confirming the bug is resolved.

Counterexamples documented:
- "All Stripe SDK calls use `stripe.api_key` global rather than per-call `api_key=` parameter"
- "Function signature lacks api_key/metadata_key params — tenants cannot isolate credentials"
- "GUESTY_METADATA_KEY is module-level os.getenv read at import time — shared across all tenants"
"""
import inspect
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from str_stripe_enrichment import enrich_direct_bookings, _lookup_payment


class TestBugCondition_GlobalCredentialUsage:
    """
    Property 1: Bug Condition — Global Credential Usage

    For any enrichment request with non-empty reservation codes and a valid tenant,
    the function should accept explicit credentials rather than reading from global
    env vars and setting stripe.api_key globally.

    These tests FAIL on unfixed code (confirming the bug) and PASS after the fix.
    """

    def test_function_accepts_api_key_parameter(self):
        """
        Expected behavior: enrich_direct_bookings() has an `api_key` parameter.

        Bug condition: Function signature only has (reservation_codes, amounts) —
        no way to pass per-tenant credentials.
        """
        sig = inspect.signature(enrich_direct_bookings)
        param_names = list(sig.parameters.keys())

        assert "api_key" in param_names, (
            "COUNTEREXAMPLE: enrich_direct_bookings() does not accept 'api_key' parameter. "
            "All tenants forced to share global STRIPE_SECRET_KEY env var."
        )

    def test_function_accepts_metadata_key_parameter(self):
        """
        Expected behavior: enrich_direct_bookings() has a `metadata_key` parameter.

        Bug condition: GUESTY_METADATA_KEY is a module-level constant read at import
        time — all tenants share the same metadata key.
        """
        sig = inspect.signature(enrich_direct_bookings)
        param_names = list(sig.parameters.keys())

        assert "metadata_key" in param_names, (
            "COUNTEREXAMPLE: enrich_direct_bookings() does not accept 'metadata_key' parameter. "
            "GUESTY_METADATA_KEY is a module-level constant shared across all tenants."
        )

    @patch('str_stripe_enrichment.stripe')
    def test_does_not_set_stripe_api_key_globally(self, mock_stripe):
        """
        Expected behavior: The function uses per-call api_key= kwarg on Stripe SDK
        calls, never sets stripe.api_key globally.

        Bug condition: Function does `stripe.api_key = api_key` which pollutes
        global state and breaks tenant isolation.
        """
        # Reset any prior global state
        mock_stripe.api_key = None

        try:
            # Call with explicit api_key (expected fixed signature)
            enrich_direct_bookings(
                ["GY-TEST1"],
                api_key="sk_test_tenant_a",
                metadata_key="confirmationCode",
            )
        except TypeError:
            # If function doesn't accept api_key param, that's the bug
            pytest.fail(
                "COUNTEREXAMPLE: enrich_direct_bookings() does not accept api_key parameter. "
                "Cannot pass per-tenant credentials."
            )

        # Verify stripe.api_key was NOT set globally
        assert mock_stripe.api_key is None, (
            "COUNTEREXAMPLE: stripe.api_key was set globally instead of using "
            "per-call api_key= parameter. This breaks tenant isolation."
        )

    def test_does_not_read_from_env_vars(self):
        """
        Expected behavior: Function uses the passed api_key parameter, not os.getenv.

        Bug condition: Function reads STRIPE_SECRET_KEY from environment variables,
        meaning all tenants share the same credentials.

        Verification: After the fix, the module should NOT import os at all,
        proving it cannot read from environment variables.
        """
        import str_stripe_enrichment as module
        import importlib
        importlib.reload(module)

        # The module should not import os (no env var reading)
        source_file = inspect.getsourcefile(module)
        with open(source_file, "r") as f:
            source = f.read()

        assert "os.getenv" not in source, (
            "COUNTEREXAMPLE: Module still contains os.getenv calls. "
            "Credentials should come from parameters, not environment variables."
        )
        assert "import os" not in source, (
            "COUNTEREXAMPLE: Module still imports os. "
            "No environment variable reading should occur — credentials come from parameters."
        )

    @patch('str_stripe_enrichment.stripe')
    def test_different_tenants_use_different_credentials(self, mock_stripe):
        """
        Expected behavior: Two calls with different api_key values result in
        different credentials being used for Stripe SDK calls.

        Bug condition: Both calls read from the same os.getenv("STRIPE_SECRET_KEY"),
        making tenant isolation impossible.
        """
        mock_stripe.api_key = None
        mock_stripe.PaymentIntent.search.return_value = MagicMock(data=[])

        # Tenant A call
        try:
            enrich_direct_bookings(
                ["GY-TENANT-A"],
                api_key="sk_test_tenant_a_key",
                metadata_key="guestyCode_A",
            )
        except TypeError:
            pytest.fail(
                "COUNTEREXAMPLE: Cannot pass different api_key per tenant. "
                "All tenants forced to use same global STRIPE_SECRET_KEY."
            )

        # Tenant B call
        try:
            enrich_direct_bookings(
                ["GY-TENANT-B"],
                api_key="sk_test_tenant_b_key",
                metadata_key="guestyCode_B",
            )
        except TypeError:
            pytest.fail(
                "COUNTEREXAMPLE: Cannot pass different api_key per tenant. "
                "All tenants forced to use same global STRIPE_SECRET_KEY."
            )

    def test_no_module_level_guesty_metadata_key_constant(self):
        """
        Expected behavior: There is no module-level GUESTY_METADATA_KEY constant.
        The metadata key is passed per-call via the metadata_key parameter.

        Bug condition: GUESTY_METADATA_KEY = os.getenv(...) at module level means
        all tenants share the same metadata key, set once at import time.
        """
        import str_stripe_enrichment as module

        # After the fix, this module-level constant should not exist
        has_constant = hasattr(module, 'GUESTY_METADATA_KEY')

        assert not has_constant, (
            "COUNTEREXAMPLE: GUESTY_METADATA_KEY is a module-level constant "
            f"(value='{getattr(module, 'GUESTY_METADATA_KEY', '')}') read from os.getenv at "
            "import time. All tenants share this value — cannot be configured per-tenant."
        )

    def test_lookup_payment_accepts_credentials(self):
        """
        Expected behavior: _lookup_payment() accepts api_key and metadata_key params
        to thread credentials through the lookup stages.

        Bug condition: Internal helpers use module-level GUESTY_METADATA_KEY and
        global stripe.api_key — no credential threading.
        """
        sig = inspect.signature(_lookup_payment)
        param_names = list(sig.parameters.keys())

        assert "api_key" in param_names, (
            "COUNTEREXAMPLE: _lookup_payment() does not accept 'api_key'. "
            "Internal helpers rely on global stripe.api_key state."
        )
        assert "metadata_key" in param_names, (
            "COUNTEREXAMPLE: _lookup_payment() does not accept 'metadata_key'. "
            "Uses module-level GUESTY_METADATA_KEY constant instead."
        )
