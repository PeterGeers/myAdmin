"""Unit tests for AI Model Registry — ProfileResolver class."""

import os
import re
import pytest

from services.ai_model_registry import (
    ModelEntry,
    ModelOverride,
    TaskProfile,
    ResolvedModel,
    RegistryError,
    ProfileResolver,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_models():
    """A small set of model entries for testing."""
    return {
        "provider/model-a": ModelEntry(
            model_id="provider/model-a",
            cost_tier="free",
            max_tokens=4096,
            default_timeout=10,
            supports_vision=False,
        ),
        "provider/model-b": ModelEntry(
            model_id="provider/model-b",
            cost_tier="cheap",
            max_tokens=8000,
            default_timeout=15,
            supports_vision=True,
        ),
        "provider/model-c": ModelEntry(
            model_id="provider/model-c",
            cost_tier="paid",
            max_tokens=2000,
            default_timeout=20,
            supports_vision=False,
        ),
    }


@pytest.fixture
def sample_profiles():
    """A small set of profiles for testing."""
    return {
        "extraction": TaskProfile(
            name="extraction",
            fallback_chain=("provider/model-a", "provider/model-b"),
            overrides={
                "provider/model-a": ModelOverride(max_tokens=500),
            },
        ),
        "vision": TaskProfile(
            name="vision",
            fallback_chain=("provider/model-b",),
            overrides={
                "provider/model-b": ModelOverride(timeout=30, max_tokens=1000),
            },
        ),
        "generation": TaskProfile(
            name="generation",
            fallback_chain=("provider/model-c", "provider/model-a"),
            overrides={},
        ),
    }


@pytest.fixture
def resolver(sample_models, sample_profiles):
    """ProfileResolver instance with sample data."""
    return ProfileResolver(sample_models, sample_profiles)


# ---------------------------------------------------------------------------
# resolve_profile tests
# ---------------------------------------------------------------------------


class TestResolveProfile:
    """Tests for ProfileResolver.resolve_profile()."""

    def test_returns_resolved_models_in_order(self, resolver):
        """Resolved chain preserves fallback_chain order."""
        result = resolver.resolve_profile("extraction")
        assert len(result) == 2
        assert result[0].model_id == "provider/model-a"
        assert result[1].model_id == "provider/model-b"

    def test_applies_max_tokens_override(self, resolver):
        """Override max_tokens replaces model default."""
        result = resolver.resolve_profile("extraction")
        # model-a has override max_tokens=500
        assert result[0].max_tokens == 500
        # model-b has no override, keeps default 8000
        assert result[1].max_tokens == 8000

    def test_applies_timeout_override(self, resolver):
        """Override timeout replaces model default."""
        result = resolver.resolve_profile("vision")
        # model-b has override timeout=30
        assert result[0].timeout == 30

    def test_uses_defaults_when_no_override(self, resolver):
        """Without overrides, uses ModelEntry defaults."""
        result = resolver.resolve_profile("generation")
        assert result[0].timeout == 20  # model-c default
        assert result[0].max_tokens == 2000  # model-c default
        assert result[1].timeout == 10  # model-a default
        assert result[1].max_tokens == 4096  # model-a default

    def test_resolved_model_contains_all_fields(self, resolver):
        """Each ResolvedModel has all expected attributes."""
        result = resolver.resolve_profile("vision")
        model = result[0]
        assert isinstance(model, ResolvedModel)
        assert model.model_id == "provider/model-b"
        assert model.timeout == 30
        assert model.max_tokens == 1000
        assert model.cost_tier == "cheap"
        assert model.supports_vision is True

    def test_raises_error_for_unknown_profile(self, resolver):
        """Unknown profile raises RegistryError with name and available list."""
        with pytest.raises(RegistryError) as exc_info:
            resolver.resolve_profile("nonexistent")
        msg = str(exc_info.value)
        assert "nonexistent" in msg
        assert "extraction" in msg
        assert "vision" in msg
        assert "generation" in msg

    def test_case_sensitive_profile_lookup(self, resolver):
        """Profile lookup is case-sensitive."""
        with pytest.raises(RegistryError):
            resolver.resolve_profile("Extraction")


# ---------------------------------------------------------------------------
# list_models tests
# ---------------------------------------------------------------------------


class TestListModels:
    """Tests for ProfileResolver.list_models()."""

    def test_returns_all_models(self, resolver):
        """list_models returns all registered ModelEntry instances."""
        result = resolver.list_models()
        assert len(result) == 3
        ids = {m.model_id for m in result}
        assert ids == {"provider/model-a", "provider/model-b", "provider/model-c"}

    def test_returns_model_entry_instances(self, resolver):
        """Each element is a ModelEntry."""
        result = resolver.list_models()
        for entry in result:
            assert isinstance(entry, ModelEntry)


# ---------------------------------------------------------------------------
# list_profiles tests
# ---------------------------------------------------------------------------


class TestListProfiles:
    """Tests for ProfileResolver.list_profiles()."""

    def test_returns_all_profile_names(self, resolver):
        """list_profiles returns all registered profile name strings."""
        result = resolver.list_profiles()
        assert set(result) == {"extraction", "vision", "generation"}

    def test_returns_strings(self, resolver):
        """Each element is a string."""
        result = resolver.list_profiles()
        for name in result:
            assert isinstance(name, str)


# ---------------------------------------------------------------------------
# get_profile_detail tests
# ---------------------------------------------------------------------------


class TestGetProfileDetail:
    """Tests for ProfileResolver.get_profile_detail()."""

    def test_returns_detail_with_override_indicators(self, resolver):
        """get_profile_detail includes override boolean flags."""
        result = resolver.get_profile_detail("extraction")
        assert len(result) == 2

        # model-a has max_tokens override
        detail_a = result[0]
        assert detail_a["model_id"] == "provider/model-a"
        assert detail_a["max_tokens"] == 500
        assert detail_a["max_tokens_overridden"] is True
        assert detail_a["timeout"] == 10
        assert detail_a["timeout_overridden"] is False

        # model-b has no overrides
        detail_b = result[1]
        assert detail_b["model_id"] == "provider/model-b"
        assert detail_b["max_tokens_overridden"] is False
        assert detail_b["timeout_overridden"] is False

    def test_both_overrides_flagged(self, resolver):
        """When both timeout and max_tokens are overridden, both flags are True."""
        result = resolver.get_profile_detail("vision")
        detail = result[0]
        assert detail["timeout_overridden"] is True
        assert detail["max_tokens_overridden"] is True
        assert detail["timeout"] == 30
        assert detail["max_tokens"] == 1000

    def test_includes_cost_tier_and_vision(self, resolver):
        """Detail dicts include cost_tier and supports_vision."""
        result = resolver.get_profile_detail("generation")
        assert result[0]["cost_tier"] == "paid"
        assert result[0]["supports_vision"] is False
        assert result[1]["cost_tier"] == "free"

    def test_raises_error_for_unknown_profile(self, resolver):
        """Unknown profile raises RegistryError with name and available list."""
        with pytest.raises(RegistryError) as exc_info:
            resolver.get_profile_detail("unknown")
        msg = str(exc_info.value)
        assert "unknown" in msg
        assert "extraction" in msg


# ---------------------------------------------------------------------------
# Actual Registry Data Tests
# ---------------------------------------------------------------------------
# These tests validate the module-level `resolver` instance with real
# registered data (not test fixtures).
# Validates: Requirements 2.2, 3.1, 3.2, 6.2, 12.1, 12.2


from services.ai_model_registry import resolver as actual_resolver


REQUIRED_PROFILES = [
    "structured_extraction",
    "vision",
    "text_generation",
    "template_assistance",
    "recommendation",
]


class TestActualRegistryProfiles:
    """Tests against the real module-level resolver instance."""

    @pytest.mark.unit
    def test_all_required_profiles_exist(self):
        """Verify resolver.list_profiles() contains all 5 required profiles."""
        profiles = actual_resolver.list_profiles()
        for name in REQUIRED_PROFILES:
            assert name in profiles, f"Missing required profile: {name}"

    @pytest.mark.unit
    def test_all_profiles_resolve_successfully(self):
        """Each of the 5 required profiles resolves to a non-empty list of ResolvedModel."""
        for name in REQUIRED_PROFILES:
            result = actual_resolver.resolve_profile(name)
            assert len(result) > 0, f"Profile '{name}' resolved to empty chain"
            for model in result:
                assert isinstance(model, ResolvedModel)

    @pytest.mark.unit
    def test_vision_profile_all_support_vision(self):
        """All models in the 'vision' profile have supports_vision=True."""
        chain = actual_resolver.resolve_profile("vision")
        for model in chain:
            assert model.supports_vision is True, (
                f"Vision profile model '{model.model_id}' does not support vision"
            )

    @pytest.mark.unit
    def test_structured_extraction_override_merging(self):
        """deepseek/deepseek-chat has max_tokens=500, openai/gpt-3.5-turbo has max_tokens=500."""
        chain = actual_resolver.resolve_profile("structured_extraction")
        models_by_id = {m.model_id: m for m in chain}

        deepseek = models_by_id["deepseek/deepseek-chat"]
        assert deepseek.max_tokens == 500, (
            f"Expected max_tokens=500 for deepseek, got {deepseek.max_tokens}"
        )

        gpt35 = models_by_id["openai/gpt-3.5-turbo"]
        assert gpt35.max_tokens == 500, (
            f"Expected max_tokens=500 for gpt-3.5-turbo, got {gpt35.max_tokens}"
        )

    @pytest.mark.unit
    def test_recommendation_override_merging(self):
        """Both recommendation models have timeout=15 and max_tokens=1500."""
        chain = actual_resolver.resolve_profile("recommendation")
        for model in chain:
            assert model.timeout == 15, (
                f"Expected timeout=15 for '{model.model_id}', got {model.timeout}"
            )
            assert model.max_tokens == 1500, (
                f"Expected max_tokens=1500 for '{model.model_id}', got {model.max_tokens}"
            )

    @pytest.mark.unit
    def test_template_assistance_override_merging(self):
        """deepseek has max_tokens=2000, anthropic/claude-3.5-sonnet has max_tokens=2000 and timeout=20."""
        chain = actual_resolver.resolve_profile("template_assistance")
        models_by_id = {m.model_id: m for m in chain}

        deepseek = models_by_id["deepseek/deepseek-chat"]
        assert deepseek.max_tokens == 2000, (
            f"Expected max_tokens=2000 for deepseek, got {deepseek.max_tokens}"
        )

        claude = models_by_id["anthropic/claude-3.5-sonnet"]
        assert claude.max_tokens == 2000, (
            f"Expected max_tokens=2000 for claude-3.5-sonnet, got {claude.max_tokens}"
        )
        assert claude.timeout == 20, (
            f"Expected timeout=20 for claude-3.5-sonnet, got {claude.timeout}"
        )

    @pytest.mark.unit
    def test_error_message_contains_profile_name(self):
        """Resolving unknown profile → error message contains 'unknown_profile' and lists available."""
        with pytest.raises(RegistryError) as exc_info:
            actual_resolver.resolve_profile("unknown_profile")
        msg = str(exc_info.value)
        assert "unknown_profile" in msg
        # Should list at least some available profiles
        for name in REQUIRED_PROFILES:
            assert name in msg, f"Error message should list available profile '{name}'"

    @pytest.mark.unit
    def test_list_models_returns_all_ten(self):
        """resolver.list_models() returns exactly 10 entries."""
        models = actual_resolver.list_models()
        assert len(models) == 10, f"Expected 10 models, got {len(models)}"

    @pytest.mark.unit
    def test_list_profiles_returns_five(self):
        """resolver.list_profiles() returns exactly 5 names."""
        profiles = actual_resolver.list_profiles()
        assert len(profiles) == 5, f"Expected 5 profiles, got {len(profiles)}"

    @pytest.mark.unit
    def test_structured_extraction_chain_order(self):
        """First model is deepseek/deepseek-chat, last is openai/gpt-3.5-turbo."""
        chain = actual_resolver.resolve_profile("structured_extraction")
        assert chain[0].model_id == "deepseek/deepseek-chat", (
            f"Expected first model to be deepseek/deepseek-chat, got {chain[0].model_id}"
        )
        assert chain[-1].model_id == "openai/gpt-3.5-turbo", (
            f"Expected last model to be openai/gpt-3.5-turbo, got {chain[-1].model_id}"
        )


# ---------------------------------------------------------------------------
# No Hardcoded Model Strings Tests
# ---------------------------------------------------------------------------
# Validates: Requirements 5.6, 10.5
# Static analysis: consumer files must contain zero hardcoded Model_Identifier
# strings. All model references must come exclusively from the registry.


# Known model identifiers registered in the AI Model Registry
KNOWN_MODEL_IDS = [
    "deepseek/deepseek-chat",
    "meta-llama/llama-3.2-3b-instruct:free",
    "moonshotai/kimi-k2:free",
    "google/gemini-flash-1.5",
    "microsoft/phi-3-mini-128k-instruct:free",
    "openai/gpt-3.5-turbo",
    "openai/gpt-4o-mini",
    "google/gemini-2.0-flash-exp:free",
    "anthropic/claude-3-haiku",
    "anthropic/claude-3.5-sonnet",
]

# Consumer files that must not contain hardcoded model strings.
# Paths are relative to the backend/src directory.
CONSUMER_FILES = [
    "ai_extractor.py",
    "image_ai_processor.py",
    "services/ai_template_assistant.py",
    "hybrid_pricing_optimizer.py",
    "services/invoice_test_service.py",
]


def _get_backend_src_dir():
    """Resolve the absolute path to backend/src from this test file location."""
    # This test file is at backend/tests/unit/test_ai_model_registry.py
    tests_unit_dir = os.path.dirname(os.path.abspath(__file__))
    tests_dir = os.path.dirname(tests_unit_dir)
    backend_dir = os.path.dirname(tests_dir)
    return os.path.join(backend_dir, "src")


def _find_hardcoded_models(file_path, model_ids):
    """Scan a file for hardcoded model identifier strings.

    Ignores occurrences that appear in comment lines (lines starting with #
    after stripping whitespace). Only flags model IDs that appear as string
    literals (surrounded by quotes).

    Returns a list of (line_number, model_id, line_text) tuples for violations.
    """
    violations = []
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line_num, line in enumerate(lines, start=1):
        stripped = line.strip()
        # Skip pure comment lines
        if stripped.startswith("#"):
            continue
        # Check each model ID as a quoted string literal
        for model_id in model_ids:
            # Match model_id inside single or double quotes (string literal usage)
            pattern = rf"""(['"]){re.escape(model_id)}\1"""
            if re.search(pattern, line):
                violations.append((line_num, model_id, stripped))

    return violations


class TestNoHardcodedModelStrings:
    """Static analysis: verify consumer files have zero hardcoded model IDs.

    Validates: Requirements 5.6, 10.5
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("consumer_file", CONSUMER_FILES)
    def test_no_hardcoded_model_strings(self, consumer_file):
        """Consumer file must not contain any hardcoded Model_Identifier strings."""
        src_dir = _get_backend_src_dir()
        file_path = os.path.join(src_dir, consumer_file)

        assert os.path.exists(file_path), (
            f"Consumer file not found: {file_path}"
        )

        violations = _find_hardcoded_models(file_path, KNOWN_MODEL_IDS)

        if violations:
            details = "\n".join(
                f"  Line {ln}: {model_id!r} in: {text}"
                for ln, model_id, text in violations
            )
            pytest.fail(
                f"Hardcoded model string(s) found in {consumer_file}:\n{details}\n\n"
                f"All model references must come from the AI Model Registry."
            )
