"""Unit tests for the APP_ENV selector (fail-fast, no defaults)."""

import pytest

from environment.app_env import AppEnv, EnvironmentConfigError, parse_app_env


class TestAppEnvEnum:
    """Test the AppEnv enum members and behavior."""

    def test_enum_members_exist(self) -> None:
        """The enum must have exactly two members: PRODUCTION and TEST."""
        members = list(AppEnv)
        assert len(members) == 2
        assert AppEnv.PRODUCTION in members
        assert AppEnv.TEST in members

    def test_enum_values_are_correct(self) -> None:
        """The string values must be 'production' and 'test' (lowercase)."""
        assert AppEnv.PRODUCTION.value == "production"
        assert AppEnv.TEST.value == "test"

    def test_enum_case_sensitive(self) -> None:
        """Enum lookup is case-sensitive; 'Production' or 'TEST' (uppercase) fails."""
        with pytest.raises(ValueError):
            AppEnv("Production")
        with pytest.raises(ValueError):
            AppEnv("TEST")
        with pytest.raises(ValueError):
            AppEnv("Prod")

    def test_enum_from_valid_strings(self) -> None:
        """Valid lowercase strings produce the corresponding enum member."""
        assert AppEnv("production") is AppEnv.PRODUCTION
        assert AppEnv("test") is AppEnv.TEST


class TestParseAppEnv:
    """Test the parse_app_env function (fail-fast, no defaults)."""

    def test_valid_production(self) -> None:
        """Parsing 'production' returns AppEnv.PRODUCTION."""
        result = parse_app_env("production")
        assert result is AppEnv.PRODUCTION

    def test_valid_test(self) -> None:
        """Parsing 'test' returns AppEnv.TEST."""
        result = parse_app_env("test")
        assert result is AppEnv.TEST

    def test_strips_whitespace(self) -> None:
        """Leading/trailing whitespace is stripped before parsing."""
        assert parse_app_env("  production  ") is AppEnv.PRODUCTION
        assert parse_app_env("\ttest\n") is AppEnv.TEST

    def test_none_raises_error(self) -> None:
        """A None input raises EnvironmentConfigError."""
        with pytest.raises(EnvironmentConfigError) as exc_info:
            parse_app_env(None)
        assert "APP_ENV is unset" in str(exc_info.value)
        assert "must be one of: 'production', 'test'" in str(exc_info.value)
        assert "no default" in str(exc_info.value).lower()

    def test_empty_string_raises_error(self) -> None:
        """An empty string raises EnvironmentConfigError."""
        with pytest.raises(EnvironmentConfigError) as exc_info:
            parse_app_env("")
        assert "APP_ENV is unset" in str(exc_info.value)

    def test_whitespace_only_raises_error(self) -> None:
        """A whitespace-only string raises EnvironmentConfigError."""
        with pytest.raises(EnvironmentConfigError) as exc_info:
            parse_app_env("   ")
        assert "APP_ENV is unset" in str(exc_info.value)

    def test_unrecognized_value_raises_error(self) -> None:
        """An unrecognized value raises EnvironmentConfigError naming the bad value."""
        for bad in ("dev", "local", "PROD", "staging", "development", "prod"):
            with pytest.raises(EnvironmentConfigError) as exc_info:
                parse_app_env(bad)
            assert f"APP_ENV='{bad}' is not recognized" in str(exc_info.value)
            assert "'production', 'test'" in str(exc_info.value)

    def test_mixed_case_unrecognized(self) -> None:
        """Mixed-case values like 'Production' or 'Test' are unrecognized."""
        with pytest.raises(EnvironmentConfigError) as exc_info:
            parse_app_env("Production")
        assert "APP_ENV='Production' is not recognized" in str(exc_info.value)

        with pytest.raises(EnvironmentConfigError) as exc_info:
            parse_app_env("Test")
        assert "APP_ENV='Test' is not recognized" in str(exc_info.value)

    def test_error_messages_mention_recognized_values(self) -> None:
        """All error messages must mention the recognized values 'production', 'test'."""
        # Test unset case
        with pytest.raises(EnvironmentConfigError) as exc_info:
            parse_app_env(None)
        assert "'production', 'test'" in str(exc_info.value)

        # Test unrecognized case
        with pytest.raises(EnvironmentConfigError) as exc_info:
            parse_app_env("staging")
        assert "'production', 'test'" in str(exc_info.value)


class TestEnvironmentConfigError:
    """Test the EnvironmentConfigError exception."""

    def test_is_runtime_error_subclass(self) -> None:
        """EnvironmentConfigError must be a RuntimeError subclass."""
        assert issubclass(EnvironmentConfigError, RuntimeError)

    def test_instantiable_with_message(self) -> None:
        """Can be instantiated with a message like a normal exception."""
        exc = EnvironmentConfigError("Test error")
        assert str(exc) == "Test error"

    def test_used_by_parse_app_env(self) -> None:
        """parse_app_env raises EnvironmentConfigError, not a generic ValueError."""
        with pytest.raises(EnvironmentConfigError):
            parse_app_env(None)
        with pytest.raises(EnvironmentConfigError):
            parse_app_env("invalid")