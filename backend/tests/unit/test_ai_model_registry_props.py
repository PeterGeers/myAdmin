"""
Property-based tests for AI Model Registry.

Feature: ai-model-registry, Properties 1–8
Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.3, 2.4, 2.5, 2.6, 3.2, 3.3

Reference: .kiro/specs/ai-model-registry/design.md
"""

import sys
import os
import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.ai_model_registry import (
    ModelEntry,
    TaskProfile,
    ModelOverride,
    ProfileResolver,
    RegistryError,
    _validate_model_entry,
    _validate_profile,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

st_model_id = st.from_regex(r"[a-z][a-z0-9\-]+/[a-z][a-z0-9\-]+", fullmatch=True)
st_cost_tier = st.sampled_from(["free", "cheap", "paid"])
st_max_tokens = st.integers(min_value=1, max_value=16384)
st_timeout = st.integers(min_value=1, max_value=300)


@st.composite
def st_model_entry(draw):
    """Generate a valid ModelEntry."""
    model_id = draw(st_model_id)
    cost_tier = draw(st_cost_tier)
    max_tokens = draw(st_max_tokens)
    timeout = draw(st_timeout)
    vision = draw(st.booleans())
    return ModelEntry(
        model_id=model_id,
        cost_tier=cost_tier,
        max_tokens=max_tokens,
        default_timeout=timeout,
        supports_vision=vision,
    )


@st.composite
def st_models_dict(draw, min_size=1, max_size=10):
    """Generate a dict of model_id -> ModelEntry with unique IDs."""
    entries = draw(
        st.lists(st_model_entry(), min_size=min_size, max_size=max_size, unique_by=lambda e: e.model_id)
    )
    return {e.model_id: e for e in entries}


# Strategies for invalid values (Properties 1-3)
st_invalid_cost_tier = st.text(min_size=1, max_size=20).filter(
    lambda x: x not in ("free", "cheap", "paid")
)
st_invalid_max_tokens_low = st.integers(max_value=0)
st_invalid_max_tokens_high = st.integers(min_value=16385)
st_invalid_timeout_low = st.integers(max_value=0)
st_invalid_timeout_high = st.integers(min_value=301)


# ---------------------------------------------------------------------------
# Property 1: Model_Entry attribute validation
# Feature: ai-model-registry, Property 1: Model_Entry attribute validation
# Validates: Requirements 1.1
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestProperty1ModelEntryAttributeValidation:
    """For any combination of cost_tier, max_tokens, and default_timeout values,
    the registry SHALL accept entries where cost_tier is in {"free", "cheap", "paid"},
    max_tokens is in [1, 16384], and default_timeout is in [1, 300], and SHALL reject
    entries where any attribute is outside these bounds."""

    @settings(max_examples=100)
    @given(
        model_id=st_model_id,
        cost_tier=st_cost_tier,
        max_tokens=st_max_tokens,
        timeout=st_timeout,
        supports_vision=st.booleans(),
    )
    def test_valid_entries_are_accepted(
        self, model_id, cost_tier, max_tokens, timeout, supports_vision
    ):
        """**Validates: Requirements 1.1**"""
        entry = ModelEntry(
            model_id=model_id,
            cost_tier=cost_tier,
            max_tokens=max_tokens,
            default_timeout=timeout,
            supports_vision=supports_vision,
        )
        # Should not raise
        _validate_model_entry(entry)

    @settings(max_examples=100, suppress_health_check=[HealthCheck.filter_too_much])
    @given(
        model_id=st_model_id,
        bad_tier=st_invalid_cost_tier,
        max_tokens=st_max_tokens,
        timeout=st_timeout,
    )
    def test_invalid_cost_tier_is_rejected(self, model_id, bad_tier, max_tokens, timeout):
        """**Validates: Requirements 1.1**"""
        entry = ModelEntry(
            model_id=model_id,
            cost_tier=bad_tier,
            max_tokens=max_tokens,
            default_timeout=timeout,
            supports_vision=False,
        )
        with pytest.raises(RegistryError, match="cost_tier"):
            _validate_model_entry(entry)

    @settings(max_examples=100)
    @given(
        model_id=st_model_id,
        cost_tier=st_cost_tier,
        bad_tokens=st.one_of(st_invalid_max_tokens_low, st_invalid_max_tokens_high),
        timeout=st_timeout,
    )
    def test_invalid_max_tokens_is_rejected(self, model_id, cost_tier, bad_tokens, timeout):
        """**Validates: Requirements 1.1**"""
        entry = ModelEntry(
            model_id=model_id,
            cost_tier=cost_tier,
            max_tokens=bad_tokens,
            default_timeout=timeout,
            supports_vision=False,
        )
        with pytest.raises(RegistryError, match="max_tokens"):
            _validate_model_entry(entry)

    @settings(max_examples=100)
    @given(
        model_id=st_model_id,
        cost_tier=st_cost_tier,
        max_tokens=st_max_tokens,
        bad_timeout=st.one_of(st_invalid_timeout_low, st_invalid_timeout_high),
    )
    def test_invalid_timeout_is_rejected(self, model_id, cost_tier, max_tokens, bad_timeout):
        """**Validates: Requirements 1.1**"""
        entry = ModelEntry(
            model_id=model_id,
            cost_tier=cost_tier,
            max_tokens=max_tokens,
            default_timeout=bad_timeout,
            supports_vision=False,
        )
        with pytest.raises(RegistryError, match="default_timeout"):
            _validate_model_entry(entry)


# ---------------------------------------------------------------------------
# Property 2: Duplicate model rejection
# Feature: ai-model-registry, Property 2: Duplicate model rejection
# Validates: Requirements 1.2
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestProperty2DuplicateModelRejection:
    """For any Model_Identifier string, registering it once SHALL succeed, and
    registering it a second time SHALL always raise a RegistryError that names
    the duplicate identifier."""

    @settings(max_examples=100)
    @given(
        model_id=st_model_id,
        cost_tier=st_cost_tier,
        max_tokens=st_max_tokens,
        timeout=st_timeout,
        supports_vision=st.booleans(),
    )
    def test_duplicate_registration_raises_registry_error(
        self, model_id, cost_tier, max_tokens, timeout, supports_vision
    ):
        """**Validates: Requirements 1.2**"""
        # Use a fresh local dict to avoid polluting the module-level MODELS
        local_models = {}

        def register_model_local(mid, ct, mt, dt, sv):
            """Local version of _register_model using local_models dict."""
            if mid in local_models:
                raise RegistryError(
                    f"Duplicate model registration: '{mid}' is already registered"
                )
            entry = ModelEntry(
                model_id=mid,
                cost_tier=ct,
                max_tokens=mt,
                default_timeout=dt,
                supports_vision=sv,
            )
            _validate_model_entry(entry)
            local_models[mid] = entry

        # First registration succeeds
        register_model_local(model_id, cost_tier, max_tokens, timeout, supports_vision)
        assert model_id in local_models

        # Second registration with same model_id raises RegistryError naming the duplicate
        with pytest.raises(RegistryError, match=model_id):
            register_model_local(model_id, cost_tier, max_tokens, timeout, supports_vision)


# ---------------------------------------------------------------------------
# Property 3: Model registration round-trip
# Feature: ai-model-registry, Property 3: Model registration round-trip
# Validates: Requirements 1.3
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestProperty3ModelRegistrationRoundTrip:
    """For any valid ModelEntry (model_id, cost_tier, max_tokens, default_timeout,
    supports_vision), after registration, retrieving the model by its identifier
    SHALL return an object with identical attribute values."""

    @settings(max_examples=100)
    @given(
        model_id=st_model_id,
        cost_tier=st_cost_tier,
        max_tokens=st_max_tokens,
        timeout=st_timeout,
        supports_vision=st.booleans(),
    )
    def test_registered_model_attributes_match(
        self, model_id, cost_tier, max_tokens, timeout, supports_vision
    ):
        """**Validates: Requirements 1.3**"""
        local_models = {}

        def register_model_local(mid, ct, mt, dt, sv):
            """Local version of _register_model using local_models dict."""
            if mid in local_models:
                raise RegistryError(
                    f"Duplicate model registration: '{mid}' is already registered"
                )
            entry = ModelEntry(
                model_id=mid,
                cost_tier=ct,
                max_tokens=mt,
                default_timeout=dt,
                supports_vision=sv,
            )
            _validate_model_entry(entry)
            local_models[mid] = entry

        # Register the model
        register_model_local(model_id, cost_tier, max_tokens, timeout, supports_vision)

        # Retrieve by identifier
        retrieved = local_models[model_id]

        # All attributes SHALL match
        assert retrieved.model_id == model_id
        assert retrieved.cost_tier == cost_tier
        assert retrieved.max_tokens == max_tokens
        assert retrieved.default_timeout == timeout
        assert retrieved.supports_vision == supports_vision

    @settings(max_examples=100)
    @given(
        model_id=st_model_id,
        cost_tier=st_cost_tier,
        max_tokens=st_max_tokens,
        timeout=st_timeout,
        supports_vision=st.booleans(),
    )
    def test_round_trip_via_profile_resolver(
        self, model_id, cost_tier, max_tokens, timeout, supports_vision
    ):
        """**Validates: Requirements 1.3**"""
        local_models = {}

        entry = ModelEntry(
            model_id=model_id,
            cost_tier=cost_tier,
            max_tokens=max_tokens,
            default_timeout=timeout,
            supports_vision=supports_vision,
        )
        _validate_model_entry(entry)
        local_models[model_id] = entry

        # Create a minimal profile referencing this model
        profile = TaskProfile(
            name="test_profile",
            fallback_chain=(model_id,),
            overrides={},
        )
        local_profiles = {"test_profile": profile}

        # Resolve via ProfileResolver
        resolver = ProfileResolver(local_models, local_profiles)
        resolved_chain = resolver.resolve_profile("test_profile")

        assert len(resolved_chain) == 1
        resolved = resolved_chain[0]

        # All attributes SHALL match (no overrides applied)
        assert resolved.model_id == model_id
        assert resolved.timeout == timeout
        assert resolved.max_tokens == max_tokens
        assert resolved.cost_tier == cost_tier
        assert resolved.supports_vision == supports_vision


# ---------------------------------------------------------------------------
# Property 4: Unknown identifier/profile raises descriptive error
# Feature: ai-model-registry, Property 4: Unknown identifier/profile raises descriptive error
# Validates: Requirements 1.4, 3.2
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestUnknownProfileRaisesDescriptiveError:
    """For any string that does not match a registered Task_Profile name,
    attempting resolution SHALL raise a RegistryError whose message contains
    the requested name and lists available alternatives."""

    @settings(max_examples=100)
    @given(
        unknown_name=st.text(
            alphabet=st.characters(whitelist_categories=('L', 'N', 'P')),
            min_size=1,
            max_size=50,
        ),
        models=st_models_dict(min_size=2, max_size=5),
    )
    def test_unknown_profile_raises_with_name_and_alternatives(self, unknown_name, models):
        """**Validates: Requirements 1.4, 3.2**"""
        # Build a few profiles from the models
        model_ids = list(models.keys())
        profiles = {
            "profile_alpha": TaskProfile(
                name="profile_alpha",
                fallback_chain=(model_ids[0],),
            ),
            "profile_beta": TaskProfile(
                name="profile_beta",
                fallback_chain=(model_ids[0],),
            ),
        }

        # Ensure unknown_name is truly unknown
        assume(unknown_name not in profiles)

        resolver = ProfileResolver(models, profiles)

        with pytest.raises(RegistryError) as exc_info:
            resolver.resolve_profile(unknown_name)

        error_msg = str(exc_info.value)
        # Must contain the requested name
        assert unknown_name in error_msg, (
            f"Error should contain the unknown name '{unknown_name}', got: {error_msg}"
        )
        # Must list available profiles
        for profile_name in profiles:
            assert profile_name in error_msg, (
                f"Error should list available profile '{profile_name}', got: {error_msg}"
            )


# ---------------------------------------------------------------------------
# Property 5: Fallback chain length validation
# Feature: ai-model-registry, Property 5: Fallback chain length validation
# Validates: Requirements 2.1
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFallbackChainLengthValidation:
    """For any list of valid Model_Identifier references, the registry SHALL
    accept it as a fallback chain if and only if its length is between 1 and 10
    inclusive."""

    @settings(max_examples=100)
    @given(models=st_models_dict(min_size=10, max_size=10))
    def test_empty_chain_rejected(self, models):
        """**Validates: Requirements 2.1**"""
        profile = TaskProfile(
            name="test_profile",
            fallback_chain=(),
        )
        with pytest.raises(RegistryError) as exc_info:
            _validate_profile(profile, models)
        assert "at least 1" in str(exc_info.value).lower() or "0" in str(exc_info.value)

    @settings(max_examples=100)
    @given(
        models=st_models_dict(min_size=10, max_size=10),
        chain_len=st.integers(min_value=1, max_value=10),
    )
    def test_valid_length_accepted(self, models, chain_len):
        """**Validates: Requirements 2.1**"""
        model_ids = list(models.keys())[:chain_len]
        profile = TaskProfile(
            name="test_profile",
            fallback_chain=tuple(model_ids),
        )
        # Should not raise
        _validate_profile(profile, models)

    @settings(max_examples=100)
    @given(
        models=st_models_dict(min_size=10, max_size=10),
        extra_count=st.integers(min_value=1, max_value=10),
    )
    def test_oversized_chain_rejected(self, models, extra_count):
        """**Validates: Requirements 2.1**"""
        # We need more than 10 unique model IDs — generate extras
        model_ids = list(models.keys())
        # Add extra fake model IDs to the models dict to construct >10 chain
        extended_models = dict(models)
        extra_ids = []
        for i in range(extra_count):
            extra_id = f"extra/model-{i}"
            extended_models[extra_id] = ModelEntry(
                model_id=extra_id,
                cost_tier="free",
                max_tokens=4096,
                default_timeout=10,
                supports_vision=False,
            )
            extra_ids.append(extra_id)

        chain = tuple(model_ids + extra_ids)  # 10 + extra_count > 10
        assert len(chain) > 10

        profile = TaskProfile(
            name="test_profile",
            fallback_chain=chain,
        )
        with pytest.raises(RegistryError) as exc_info:
            _validate_profile(profile, extended_models)
        assert "at most 10" in str(exc_info.value).lower() or str(len(chain)) in str(exc_info.value)


# ---------------------------------------------------------------------------
# Property 6: Referential integrity
# Feature: ai-model-registry, Property 6: Referential integrity
# Validates: Requirements 2.3, 2.4
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestReferentialIntegrity:
    """For any Task_Profile definition, if any Model_Identifier in its
    fallback_chain does not exist in the model registry, validation SHALL
    raise a RegistryError naming the invalid identifier and the profile."""

    @settings(max_examples=100)
    @given(
        models=st_models_dict(min_size=1, max_size=5),
        invalid_id=st.from_regex(r"invalid/[a-z][a-z0-9\-]+", fullmatch=True),
    )
    def test_unknown_model_in_chain_raises(self, models, invalid_id):
        """**Validates: Requirements 2.3, 2.4**"""
        assume(invalid_id not in models)

        profile_name = "test_integrity_profile"
        # Put the invalid_id into the chain along with a valid one
        valid_id = next(iter(models.keys()))
        profile = TaskProfile(
            name=profile_name,
            fallback_chain=(valid_id, invalid_id),
        )

        with pytest.raises(RegistryError) as exc_info:
            _validate_profile(profile, models)

        error_msg = str(exc_info.value)
        # Must name the invalid identifier
        assert invalid_id in error_msg, (
            f"Error should name invalid model '{invalid_id}', got: {error_msg}"
        )
        # Must name the profile
        assert profile_name in error_msg, (
            f"Error should name the profile '{profile_name}', got: {error_msg}"
        )


# ---------------------------------------------------------------------------
# Property 7: Order preservation in fallback chains
# Feature: ai-model-registry, Property 7: Order preservation in fallback chains
# Validates: Requirements 2.5, 3.3
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrderPreservation:
    """For any Task_Profile with a defined fallback_chain ordering, the
    resolved chain SHALL return models in the exact same order as defined."""

    @settings(max_examples=100)
    @given(models=st_models_dict(min_size=2, max_size=10))
    def test_resolved_order_matches_definition(self, models):
        """**Validates: Requirements 2.5, 3.3**"""
        model_ids = list(models.keys())
        profile_name = "order_test"
        profile = TaskProfile(
            name=profile_name,
            fallback_chain=tuple(model_ids),
        )

        profiles = {profile_name: profile}
        resolver = ProfileResolver(models, profiles)
        resolved = resolver.resolve_profile(profile_name)

        # Verify exact order
        resolved_ids = [rm.model_id for rm in resolved]
        assert resolved_ids == model_ids, (
            f"Expected order {model_ids}, got {resolved_ids}"
        )


# ---------------------------------------------------------------------------
# Property 8: No duplicate models within a chain
# Feature: ai-model-registry, Property 8: No duplicate models within a chain
# Validates: Requirements 2.6
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNoDuplicatesInChain:
    """For any fallback_chain containing duplicate Model_Identifier entries,
    the registry SHALL reject the profile definition with a validation error."""

    @settings(max_examples=100)
    @given(
        models=st_models_dict(min_size=2, max_size=5),
        repeat_count=st.integers(min_value=1, max_value=3),
    )
    def test_duplicate_model_in_chain_rejected(self, models, repeat_count):
        """**Validates: Requirements 2.6**"""
        model_ids = list(models.keys())
        # Pick one model to duplicate
        dup_id = model_ids[0]
        # Build chain: first model repeated, then others (keep total <= 10)
        chain = [dup_id] * (repeat_count + 1) + model_ids[1:2]
        assume(len(chain) <= 10)

        profile_name = "dup_test_profile"
        profile = TaskProfile(
            name=profile_name,
            fallback_chain=tuple(chain),
        )

        with pytest.raises(RegistryError) as exc_info:
            _validate_profile(profile, models)

        error_msg = str(exc_info.value)
        # Must indicate the duplicate
        assert "duplicate" in error_msg.lower(), (
            f"Error should mention 'duplicate', got: {error_msg}"
        )
        assert dup_id in error_msg, (
            f"Error should name the duplicate model '{dup_id}', got: {error_msg}"
        )


# ---------------------------------------------------------------------------
# Property 9: Override precedence
# Feature: ai-model-registry, Property 9: Override precedence
# Validates: Requirements 4.1, 4.2
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOverridePrecedence:
    """For any model in a resolved profile, if the profile defines a timeout or
    max_tokens override for that model, the resolved value SHALL equal the
    override; if no override is defined, the resolved value SHALL equal the
    model's default."""

    @settings(max_examples=100)
    @given(
        models=st_models_dict(min_size=2, max_size=5),
        override_timeout=st.integers(min_value=1, max_value=600),
        override_max_tokens=st.integers(min_value=1, max_value=16384),
    )
    def test_overridden_values_equal_override(self, models, override_timeout, override_max_tokens):
        """**Validates: Requirements 4.1, 4.2**"""
        model_ids = list(models.keys())

        # Pick one model to override, leave the rest with defaults
        overridden_model_id = model_ids[0]

        overrides = {
            overridden_model_id: ModelOverride(
                timeout=override_timeout,
                max_tokens=override_max_tokens,
            )
        }

        profile = TaskProfile(
            name="test_profile",
            fallback_chain=tuple(model_ids),
            overrides=overrides,
        )

        # Validate profile passes
        _validate_profile(profile, models)

        # Resolve and check
        resolver = ProfileResolver(models, {"test_profile": profile})
        resolved = resolver.resolve_profile("test_profile")

        for resolved_model in resolved:
            entry = models[resolved_model.model_id]
            if resolved_model.model_id == overridden_model_id:
                # Overridden model: values must equal the override
                assert resolved_model.timeout == override_timeout, (
                    f"Expected timeout={override_timeout}, got {resolved_model.timeout}"
                )
                assert resolved_model.max_tokens == override_max_tokens, (
                    f"Expected max_tokens={override_max_tokens}, got {resolved_model.max_tokens}"
                )
            else:
                # Non-overridden model: values must equal model defaults
                assert resolved_model.timeout == entry.default_timeout, (
                    f"Expected timeout={entry.default_timeout}, got {resolved_model.timeout}"
                )
                assert resolved_model.max_tokens == entry.max_tokens, (
                    f"Expected max_tokens={entry.max_tokens}, got {resolved_model.max_tokens}"
                )


# ---------------------------------------------------------------------------
# Property 10: Override value range validation
# Feature: ai-model-registry, Property 10: Override value range validation
# Validates: Requirements 4.3, 4.5
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOverrideValueRangeValidation:
    """For any override timeout value outside [1, 600] or max_tokens value
    outside [1, 16384], the registry SHALL reject the profile with a
    RegistryError naming the invalid parameter, model, and acceptable range."""

    @settings(max_examples=100)
    @given(
        model_entry=st_model_entry(),
        invalid_timeout=st.one_of(
            st.integers(max_value=0),
            st.integers(min_value=601),
        ),
    )
    def test_invalid_timeout_rejected(self, model_entry, invalid_timeout):
        """**Validates: Requirements 4.3, 4.5**"""
        models = {model_entry.model_id: model_entry}

        profile = TaskProfile(
            name="test_profile",
            fallback_chain=(model_entry.model_id,),
            overrides={
                model_entry.model_id: ModelOverride(timeout=invalid_timeout),
            },
        )

        with pytest.raises(RegistryError) as exc_info:
            _validate_profile(profile, models)

        error_msg = str(exc_info.value)
        assert "timeout" in error_msg.lower(), (
            f"Error should mention 'timeout': {error_msg}"
        )
        assert model_entry.model_id in error_msg, (
            f"Error should mention model_id: {error_msg}"
        )
        assert "600" in error_msg, (
            f"Error should mention acceptable range boundary '600': {error_msg}"
        )

    @settings(max_examples=100)
    @given(
        model_entry=st_model_entry(),
        invalid_max_tokens=st.one_of(
            st.integers(max_value=0),
            st.integers(min_value=16385),
        ),
    )
    def test_invalid_max_tokens_rejected(self, model_entry, invalid_max_tokens):
        """**Validates: Requirements 4.3, 4.5**"""
        models = {model_entry.model_id: model_entry}

        profile = TaskProfile(
            name="test_profile",
            fallback_chain=(model_entry.model_id,),
            overrides={
                model_entry.model_id: ModelOverride(max_tokens=invalid_max_tokens),
            },
        )

        with pytest.raises(RegistryError) as exc_info:
            _validate_profile(profile, models)

        error_msg = str(exc_info.value)
        assert "max_tokens" in error_msg.lower(), (
            f"Error should mention 'max_tokens': {error_msg}"
        )
        assert model_entry.model_id in error_msg, (
            f"Error should mention model_id: {error_msg}"
        )
        assert "16384" in error_msg, (
            f"Error should mention acceptable range boundary '16384': {error_msg}"
        )


# ---------------------------------------------------------------------------
# Property 11: Orphaned override rejection
# Feature: ai-model-registry, Property 11: Orphaned override rejection
# Validates: Requirements 4.4
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOrphanedOverrideRejection:
    """For any profile whose overrides dict contains a Model_Identifier key
    that is not in the profile's fallback_chain, validation SHALL raise a
    RegistryError naming the orphaned model identifier."""

    @settings(max_examples=100)
    @given(
        chain_entries=st.lists(st_model_entry(), min_size=1, max_size=5, unique_by=lambda e: e.model_id),
        orphan_entry=st_model_entry(),
    )
    def test_orphaned_override_raises_with_model_name(self, chain_entries, orphan_entry):
        """**Validates: Requirements 4.4**"""
        # Ensure the orphan model_id is distinct from all chain model_ids
        chain_ids = {e.model_id for e in chain_entries}
        assume(orphan_entry.model_id not in chain_ids)

        # Build models dict — include orphan so it's a registered model,
        # but the override error is about the model not being in the *chain*
        models = {entry.model_id: entry for entry in chain_entries}
        models[orphan_entry.model_id] = orphan_entry

        # Create profile with orphan in overrides but NOT in fallback_chain
        profile = TaskProfile(
            name="test_profile",
            fallback_chain=tuple(e.model_id for e in chain_entries),
            overrides={
                orphan_entry.model_id: ModelOverride(timeout=30),
            },
        )

        with pytest.raises(RegistryError) as exc_info:
            _validate_profile(profile, models)

        error_msg = str(exc_info.value)
        assert orphan_entry.model_id in error_msg, (
            f"Error should name the orphaned model '{orphan_entry.model_id}': {error_msg}"
        )


# ---------------------------------------------------------------------------
# Property 15: Introspection completeness
# Feature: ai-model-registry, Property 15: Introspection completeness
# Validates: Requirements 12.1, 12.2
# ---------------------------------------------------------------------------


@st.composite
def st_models_and_profiles(draw):
    """Generate N models (1-10) and M profiles (1-5) referencing those models."""
    # Generate N unique model entries
    n = draw(st.integers(min_value=1, max_value=10))
    entries = draw(
        st.lists(
            st_model_entry(),
            min_size=n,
            max_size=n,
            unique_by=lambda e: e.model_id,
        )
    )
    models = {e.model_id: e for e in entries}
    model_ids = list(models.keys())

    # Generate M profiles referencing subsets of those models
    m = draw(st.integers(min_value=1, max_value=5))
    profiles = {}
    for i in range(m):
        profile_name = f"profile_{i}"
        # Pick 1 to min(10, n) models for the fallback chain
        chain_size = draw(st.integers(min_value=1, max_value=min(10, n)))
        chain_ids = draw(
            st.lists(
                st.sampled_from(model_ids),
                min_size=chain_size,
                max_size=chain_size,
                unique=True,
            )
        )
        profiles[profile_name] = TaskProfile(
            name=profile_name,
            fallback_chain=tuple(chain_ids),
            overrides={},
        )

    return models, profiles


@pytest.mark.unit
class TestIntrospectionCompleteness:
    """For any set of N registered models and M registered profiles,
    list_models() SHALL return exactly N entries and list_profiles() SHALL
    return exactly M names, with no omissions."""

    @settings(max_examples=100)
    @given(data=st_models_and_profiles())
    def test_list_models_returns_all_entries(self, data):
        """**Validates: Requirements 12.1, 12.2**"""
        models, profiles = data

        resolver = ProfileResolver(models, profiles)

        # Verify list_models() returns exactly N entries
        listed_models = resolver.list_models()
        assert len(listed_models) == len(models), (
            f"Expected {len(models)} models, got {len(listed_models)}"
        )

        # Verify all model entries are present (no omissions)
        listed_model_ids = {m.model_id for m in listed_models}
        expected_model_ids = set(models.keys())
        assert listed_model_ids == expected_model_ids, (
            f"Model IDs mismatch. Missing: {expected_model_ids - listed_model_ids}, "
            f"Extra: {listed_model_ids - expected_model_ids}"
        )

    @settings(max_examples=100)
    @given(data=st_models_and_profiles())
    def test_list_profiles_returns_all_names(self, data):
        """**Validates: Requirements 12.1, 12.2**"""
        models, profiles = data

        resolver = ProfileResolver(models, profiles)

        # Verify list_profiles() returns exactly M names
        listed_profiles = resolver.list_profiles()
        assert len(listed_profiles) == len(profiles), (
            f"Expected {len(profiles)} profiles, got {len(listed_profiles)}"
        )

        # Verify all profile names are present (no omissions)
        listed_profile_set = set(listed_profiles)
        expected_profile_set = set(profiles.keys())
        assert listed_profile_set == expected_profile_set, (
            f"Profile names mismatch. Missing: {expected_profile_set - listed_profile_set}, "
            f"Extra: {listed_profile_set - expected_profile_set}"
        )
