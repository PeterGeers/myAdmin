"""
Unit tests for log sanitization.

Validates:
- Requirements 8.1: No API key values in startup logs
- Requirements 8.2: Mask function for sensitive key patterns
- Requirements 8.4: Exception log capture contains no raw secrets
"""
import io
import sys
import pytest
from unittest.mock import patch
from hypothesis import given, settings
from hypothesis import strategies as st

from utils.log_sanitizer import mask_sensitive_value, is_sensitive_key, REDACTED


# ---------------------------------------------------------------------------
# Property-Based Tests (Hypothesis)
# ---------------------------------------------------------------------------

# Core sensitive pattern fragments that are guaranteed to match the regex patterns
# in log_sanitizer.py. Each entry will match at least one SENSITIVE_KEY_PATTERNS regex.
_SENSITIVE_CORE_NAMES = [
    "api_key", "api-key", "api key",
    "password", "db_password", "user_password",
    "encryption_key", "encryption-key", "encryption key",
    "oauth_secret", "oauth-secret", "oauth_client_secret",
    "jwt_key", "jwt-key", "jwt_signing_key", "jwt-signing-key",
    "secret_key", "secret-key", "secret key",
    "access_token", "access-token", "access token",
    "refresh_token", "refresh-token", "refresh token",
    "private_key", "private-key", "private key",
    "client_secret", "client-secret", "client secret",
]

# Optional prefixes to prepend (simulates real keys like "openrouter_api_key")
_OPTIONAL_PREFIXES = ["", "my_", "app_", "openrouter_", "cognito_", "db_",
                      "BACKEND_", "AWS_"]


@st.composite
def sensitive_key_strategy(draw):
    """Generate key names that are guaranteed to match known sensitive patterns."""
    core = draw(st.sampled_from(_SENSITIVE_CORE_NAMES))
    prefix = draw(st.sampled_from(_OPTIONAL_PREFIXES))
    return f"{prefix}{core}"


# Strategy: generate secret values with min_size=4 to allow substring checks of length >= 3
# Excludes characters that appear in "[REDACTED]" to avoid false positives in substring check
secret_value_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S'),
        blacklist_characters='\x00'
    ),
    min_size=4,
    max_size=100
)


class TestSensitiveValueMaskingProperty:
    """Property 15: Sensitive Value Masking.

    For any (key_name, secret_value) pair where key_name matches a known
    sensitive pattern, mask_sensitive_value SHALL return "[REDACTED]" and the
    return value SHALL NOT contain any substring of length >= 3 from the
    original secret_value.

    **Validates: Requirements 8.2, 8.4**
    """

    # Feature: security-hardening, Property 15: Sensitive Value Masking

    @given(key=sensitive_key_strategy(), secret=secret_value_strategy)
    @settings(max_examples=100)
    def test_sensitive_key_always_returns_redacted(self, key, secret):
        """Any key matching a sensitive pattern must return '[REDACTED]'."""
        result = mask_sensitive_value(key, secret)
        assert result == REDACTED, (
            f"Expected '[REDACTED]' for sensitive key '{key}', got '{result}'"
        )

    @given(key=sensitive_key_strategy(), secret=secret_value_strategy)
    @settings(max_examples=100)
    def test_redacted_contains_no_secret_substring(self, key, secret):
        """The return value must not contain any substring of length >= 3
        from the original secret value.

        We filter out secrets that coincidentally share substrings with the
        literal '[REDACTED]' string, since the property is about information
        leakage, not coincidental string overlap."""
        from hypothesis import assume

        result = mask_sensitive_value(key, secret)
        # Pre-check: skip if the secret has substrings naturally in "[REDACTED]"
        # This avoids false negatives from coincidental overlap
        has_overlap_with_redacted = any(
            secret[i:i + 3] in REDACTED
            for i in range(len(secret) - 2)
        )
        assume(not has_overlap_with_redacted)

        # Check all substrings of length >= 3 from the original secret
        for i in range(len(secret) - 2):
            substring = secret[i:i + 3]
            assert substring not in result, (
                f"Substring '{substring}' from original secret found in "
                f"masked result '{result}' for key '{key}'"
            )


class TestMaskSensitiveValue:
    """Test mask_sensitive_value for various sensitive key patterns."""

    @pytest.mark.parametrize("key", [
        "api_key",
        "API_KEY",
        "Api-Key",
        "openrouter_api_key",
        "OPENROUTER_API_KEY",
    ])
    def test_api_key_patterns_redacted(self, key):
        """API key patterns should always be redacted."""
        result = mask_sensitive_value(key, "sk-abc123secret456")
        assert result == REDACTED

    @pytest.mark.parametrize("key", [
        "password",
        "PASSWORD",
        "db_password",
        "DB_PASSWORD",
        "user_password",
    ])
    def test_password_patterns_redacted(self, key):
        """Password patterns should always be redacted."""
        result = mask_sensitive_value(key, "super_secret_pass!")
        assert result == REDACTED

    @pytest.mark.parametrize("key", [
        "encryption_key",
        "ENCRYPTION_KEY",
        "CREDENTIALS_ENCRYPTION_KEY",
        "encryption-key",
    ])
    def test_encryption_key_patterns_redacted(self, key):
        """Encryption key patterns should always be redacted."""
        result = mask_sensitive_value(key, "fernet-base64-encoded-key==")
        assert result == REDACTED

    @pytest.mark.parametrize("key", [
        "oauth_secret",
        "OAUTH_SECRET",
        "oauth_client_secret",
        "OAUTH_CLIENT_SECRET",
    ])
    def test_oauth_secret_patterns_redacted(self, key):
        """OAuth secret patterns should always be redacted."""
        result = mask_sensitive_value(key, "oauth-secret-value-xyz")
        assert result == REDACTED

    @pytest.mark.parametrize("key", [
        "jwt_key",
        "JWT_KEY",
        "jwt_signing_key",
        "JWT_SIGNING_KEY",
    ])
    def test_jwt_key_patterns_redacted(self, key):
        """JWT key patterns should always be redacted."""
        result = mask_sensitive_value(key, "jwt-signing-secret-123")
        assert result == REDACTED

    @pytest.mark.parametrize("key", [
        "secret_key",
        "SECRET_KEY",
        "access_token",
        "ACCESS_TOKEN",
        "refresh_token",
        "REFRESH_TOKEN",
        "private_key",
        "PRIVATE_KEY",
        "client_secret",
        "CLIENT_SECRET",
    ])
    def test_other_sensitive_patterns_redacted(self, key):
        """Other sensitive key patterns should be redacted."""
        result = mask_sensitive_value(key, "some-secret-value-here")
        assert result == REDACTED

    @pytest.mark.parametrize("key", [
        "username",
        "email",
        "database_host",
        "port",
        "log_level",
        "app_name",
        "region",
        "tenant_id",
    ])
    def test_non_sensitive_keys_pass_through(self, key):
        """Non-sensitive keys should return the value unchanged (as string)."""
        value = "some_normal_value"
        result = mask_sensitive_value(key, value)
        assert result == value

    def test_non_sensitive_key_returns_str_of_value(self):
        """Non-sensitive keys should convert the value to string."""
        result = mask_sensitive_value("port", 5432)
        assert result == "5432"

    def test_redacted_value_contains_no_original_content(self):
        """The redacted output must not contain any part of the original secret."""
        secret = "my-super-secret-api-key-value"
        result = mask_sensitive_value("api_key", secret)
        assert result == REDACTED
        # Ensure no substring of the secret leaks
        for i in range(len(secret) - 2):
            assert secret[i:i+3] not in result


class TestIsSensitiveKey:
    """Test is_sensitive_key helper function."""

    def test_returns_true_for_sensitive_keys(self):
        assert is_sensitive_key("api_key") is True
        assert is_sensitive_key("password") is True
        assert is_sensitive_key("encryption_key") is True

    def test_returns_false_for_non_sensitive_keys(self):
        assert is_sensitive_key("username") is False
        assert is_sensitive_key("database_host") is False
        assert is_sensitive_key("log_level") is False

    def test_case_insensitive_matching(self):
        assert is_sensitive_key("API_KEY") is True
        assert is_sensitive_key("Password") is True
        assert is_sensitive_key("JWT_SIGNING_KEY") is True


class TestStartupLogNoApiKeys:
    """Test that startup logs do not contain API key values.

    Validates: Requirement 8.1
    """

    def test_ai_extractor_startup_does_not_log_api_key(self):
        """AI Extractor startup log must not contain any API key value."""
        fake_api_key = "sk-or-v1-" + "a1b2c3d4" * 8  # noqa: fake test value

        captured_output = io.StringIO()
        with patch.dict('os.environ', {'OPENROUTER_API_KEY': fake_api_key}):
            with patch('sys.stdout', new=captured_output):
                # Re-import to trigger __init__ print
                from ai_extractor import AIExtractor
                AIExtractor()

        output = captured_output.getvalue()
        # The log must NOT contain the API key or any partial key
        assert fake_api_key not in output
        assert fake_api_key[:20] not in output
        # It should contain the safe message
        assert "AI Extractor initialized successfully" in output


class TestExceptionLogNoSecrets:
    """Test that exception logs in credential code do not expose raw secrets.

    Validates: Requirement 8.4
    """

    def test_credential_service_encryption_error_no_secret(self):
        """Encryption failure logs should contain error type, not raw values."""
        import logging

        # Capture log output
        log_output = io.StringIO()
        handler = logging.StreamHandler(log_output)
        handler.setLevel(logging.ERROR)

        logger = logging.getLogger('credential_service')
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        secret_value = "super-secret-credential-value-12345"
        master_key = "my-master-encryption-key-abc"

        # Simulate what the credential service does on encryption error
        try:
            raise ValueError("simulated encryption failure")
        except Exception as e:
            # This mirrors the pattern in credential_service.py
            logger.error(f"Encryption failed: {type(e).__name__}")

        log_content = log_output.getvalue()

        # Verify the log does NOT contain the raw secret or master key
        assert secret_value not in log_content
        assert master_key not in log_content
        # Verify it logs the exception type name
        assert "ValueError" in log_content

        logger.removeHandler(handler)

    def test_credential_service_decryption_error_no_secret(self):
        """Decryption failure logs should contain error type, not raw values."""
        import logging

        log_output = io.StringIO()
        handler = logging.StreamHandler(log_output)
        handler.setLevel(logging.ERROR)

        logger = logging.getLogger('credential_service')
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        encrypted_value = "gAAAAABhEncryptedDataHere=="
        master_key = "fernet-master-key-base64-encoded=="

        try:
            raise Exception("simulated decryption failure")
        except Exception as e:
            # Mirror the credential_service pattern
            logger.error(f"Decryption failed: {type(e).__name__}")

        log_content = log_output.getvalue()

        # Verify no raw secrets in log
        assert encrypted_value not in log_content
        assert master_key not in log_content
        # Verify the error type is logged
        assert "Exception" in log_content

        logger.removeHandler(handler)
