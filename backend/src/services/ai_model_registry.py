"""
AI Model Registry — centralized OpenRouter model configuration.

This module defines all AI model entries, task-based profiles with ordered
fallback chains, per-profile overrides, and a ProfileResolver. It replaces
hardcoded model fallback chains scattered across consumer modules with a
single source of truth validated at import time.
"""

from dataclasses import dataclass, field
from typing import Dict, Literal, Optional

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

CostTier = Literal["free", "cheap", "paid"]

_VALID_COST_TIERS = ("free", "cheap", "paid")


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class RegistryError(Exception):
    """Raised for registry validation or resolution errors."""

    pass


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelEntry:
    """Immutable definition of a single AI model."""

    model_id: str
    cost_tier: CostTier
    max_tokens: int  # 1–16384
    default_timeout: int  # 1–300 seconds
    supports_vision: bool


@dataclass(frozen=True)
class ModelOverride:
    """Per-model parameter overrides within a profile."""

    timeout: Optional[int] = None  # 1–600 if specified
    max_tokens: Optional[int] = None  # 1–16384 if specified


@dataclass(frozen=True)
class TaskProfile:
    """Named profile mapping a task type to an ordered fallback chain."""

    name: str
    fallback_chain: tuple  # Ordered tuple of model_id strings (1–10)
    overrides: Dict[str, ModelOverride] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedModel:
    """Fully resolved model configuration for a consumer to use."""

    model_id: str
    timeout: int
    max_tokens: int
    cost_tier: CostTier
    supports_vision: bool


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------


def _validate_model_entry(entry: ModelEntry) -> None:
    """Validate a single ModelEntry's attributes.

    Raises RegistryError for:
    - cost_tier not in ("free", "cheap", "paid")
    - max_tokens not in [1, 16384]
    - default_timeout not in [1, 300]
    """
    if entry.cost_tier not in _VALID_COST_TIERS:
        raise RegistryError(
            f"Model '{entry.model_id}': cost_tier must be one of "
            f"{_VALID_COST_TIERS}, got '{entry.cost_tier}'"
        )

    if not (1 <= entry.max_tokens <= 16384):
        raise RegistryError(
            f"Model '{entry.model_id}': max_tokens must be in [1, 16384], "
            f"got {entry.max_tokens}"
        )

    if not (1 <= entry.default_timeout <= 300):
        raise RegistryError(
            f"Model '{entry.model_id}': default_timeout must be in [1, 300], "
            f"got {entry.default_timeout}"
        )


def _validate_profile(profile: TaskProfile, models: Dict[str, ModelEntry]) -> None:
    """Validate a TaskProfile against registered models.

    Raises RegistryError for:
    - Empty fallback_chain or len > 10
    - Model_Identifier not in models dict
    - Duplicate model_ids in chain
    - Override referencing model not in chain
    - Override values out of range (timeout: 1-600, max_tokens: 1-16384)
    """
    chain = profile.fallback_chain

    # Chain length validation
    if len(chain) == 0:
        raise RegistryError(
            f"Profile '{profile.name}': fallback_chain must contain at least "
            f"1 model, got 0"
        )

    if len(chain) > 10:
        raise RegistryError(
            f"Profile '{profile.name}': fallback_chain must contain at most "
            f"10 models, got {len(chain)}"
        )

    # Unknown model references
    for model_id in chain:
        if model_id not in models:
            raise RegistryError(
                f"Profile '{profile.name}': model '{model_id}' is not a "
                f"registered model. Available models: "
                f"{sorted(models.keys())}"
            )

    # Duplicate model_ids in chain
    seen = set()
    for model_id in chain:
        if model_id in seen:
            raise RegistryError(
                f"Profile '{profile.name}': duplicate model '{model_id}' "
                f"in fallback_chain"
            )
        seen.add(model_id)

    # Orphaned overrides (override key not in chain)
    chain_set = set(chain)
    for model_id in profile.overrides:
        if model_id not in chain_set:
            raise RegistryError(
                f"Profile '{profile.name}': override for model '{model_id}' "
                f"is not referenced in the profile's fallback_chain"
            )

    # Override value range validation
    for model_id, override in profile.overrides.items():
        if override.timeout is not None and not (1 <= override.timeout <= 600):
            raise RegistryError(
                f"Profile '{profile.name}': override timeout for model "
                f"'{model_id}' must be in [1, 600], got {override.timeout}"
            )

        if override.max_tokens is not None and not (1 <= override.max_tokens <= 16384):
            raise RegistryError(
                f"Profile '{profile.name}': override max_tokens for model "
                f"'{model_id}' must be in [1, 16384], got {override.max_tokens}"
            )


# ---------------------------------------------------------------------------
# ProfileResolver
# ---------------------------------------------------------------------------


class ProfileResolver:
    """Resolves task profiles into ordered lists of fully-configured models."""

    def __init__(self, models: Dict[str, ModelEntry], profiles: Dict[str, TaskProfile]):
        self._models = models
        self._profiles = profiles

    def resolve_profile(self, profile_name: str) -> list:
        """Resolve a profile name to its ordered fallback chain.

        Args:
            profile_name: The task profile to resolve (case-sensitive).

        Returns:
            Ordered list of ResolvedModel instances.

        Raises:
            RegistryError: If profile_name is not registered.
        """
        if profile_name not in self._profiles:
            available = sorted(self._profiles.keys())
            raise RegistryError(
                f"Unknown profile '{profile_name}'. Available profiles: {available}"
            )

        profile = self._profiles[profile_name]
        resolved = []

        for model_id in profile.fallback_chain:
            entry = self._models[model_id]
            override = profile.overrides.get(model_id)

            timeout = entry.default_timeout
            max_tokens = entry.max_tokens

            if override is not None:
                if override.timeout is not None:
                    timeout = override.timeout
                if override.max_tokens is not None:
                    max_tokens = override.max_tokens

            resolved.append(
                ResolvedModel(
                    model_id=model_id,
                    timeout=timeout,
                    max_tokens=max_tokens,
                    cost_tier=entry.cost_tier,
                    supports_vision=entry.supports_vision,
                )
            )

        return resolved

    def list_models(self) -> list:
        """Return all registered ModelEntry instances."""
        return list(self._models.values())

    def list_profiles(self) -> list:
        """Return all registered profile names."""
        return list(self._profiles.keys())

    def get_profile_detail(self, profile_name: str) -> list:
        """Return detailed profile info including override indicators.

        Args:
            profile_name: The task profile to inspect (case-sensitive).

        Returns:
            List of dicts, each with model_id, timeout, max_tokens,
            cost_tier, supports_vision, timeout_overridden, and
            max_tokens_overridden.

        Raises:
            RegistryError: If profile_name is not registered.
        """
        if profile_name not in self._profiles:
            available = sorted(self._profiles.keys())
            raise RegistryError(
                f"Unknown profile '{profile_name}'. Available profiles: {available}"
            )

        profile = self._profiles[profile_name]
        details = []

        for model_id in profile.fallback_chain:
            entry = self._models[model_id]
            override = profile.overrides.get(model_id)

            timeout = entry.default_timeout
            max_tokens = entry.max_tokens
            timeout_overridden = False
            max_tokens_overridden = False

            if override is not None:
                if override.timeout is not None:
                    timeout = override.timeout
                    timeout_overridden = True
                if override.max_tokens is not None:
                    max_tokens = override.max_tokens
                    max_tokens_overridden = True

            details.append(
                {
                    "model_id": model_id,
                    "timeout": timeout,
                    "max_tokens": max_tokens,
                    "cost_tier": entry.cost_tier,
                    "supports_vision": entry.supports_vision,
                    "timeout_overridden": timeout_overridden,
                    "max_tokens_overridden": max_tokens_overridden,
                }
            )

        return details


# ---------------------------------------------------------------------------
# Model Definitions
# ---------------------------------------------------------------------------

MODELS: Dict[str, ModelEntry] = {}


def _register_model(
    model_id: str,
    cost_tier: CostTier,
    max_tokens: int,
    default_timeout: int,
    supports_vision: bool,
) -> None:
    """Register a model entry. Raises RegistryError on duplicate or invalid attributes."""
    if model_id in MODELS:
        raise RegistryError(
            f"Duplicate model registration: '{model_id}' is already registered"
        )
    entry = ModelEntry(
        model_id=model_id,
        cost_tier=cost_tier,
        max_tokens=max_tokens,
        default_timeout=default_timeout,
        supports_vision=supports_vision,
    )
    _validate_model_entry(entry)
    MODELS[model_id] = entry


# Register all models
_register_model("deepseek/deepseek-chat", "cheap", 4096, 10, False)
_register_model("meta-llama/llama-3.2-3b-instruct:free", "free", 4096, 10, False)
_register_model("moonshotai/kimi-k2:free", "free", 4096, 10, False)
_register_model("google/gemini-flash-1.5", "free", 4096, 10, False)
_register_model("microsoft/phi-3-mini-128k-instruct:free", "free", 4096, 10, False)
_register_model("openai/gpt-3.5-turbo", "paid", 4096, 10, False)
_register_model("openai/gpt-4o-mini", "cheap", 4096, 15, True)
_register_model("google/gemini-2.0-flash-exp:free", "free", 4096, 15, True)
_register_model("anthropic/claude-3-haiku", "cheap", 4096, 15, True)
_register_model("anthropic/claude-3.5-sonnet", "paid", 4096, 15, False)

# ---------------------------------------------------------------------------
# Profile Definitions
# ---------------------------------------------------------------------------

PROFILES: Dict[str, TaskProfile] = {}

PROFILES["structured_extraction"] = TaskProfile(
    name="structured_extraction",
    fallback_chain=(
        "deepseek/deepseek-chat",
        "meta-llama/llama-3.2-3b-instruct:free",
        "moonshotai/kimi-k2:free",
        "google/gemini-flash-1.5",
        "microsoft/phi-3-mini-128k-instruct:free",
        "openai/gpt-3.5-turbo",
    ),
    overrides={
        "deepseek/deepseek-chat": ModelOverride(max_tokens=500),
        "openai/gpt-3.5-turbo": ModelOverride(max_tokens=500),
    },
)

PROFILES["vision"] = TaskProfile(
    name="vision",
    fallback_chain=(
        "openai/gpt-4o-mini",
        "google/gemini-2.0-flash-exp:free",
        "anthropic/claude-3-haiku",
    ),
    overrides={
        "openai/gpt-4o-mini": ModelOverride(max_tokens=500, timeout=15),
    },
)

PROFILES["text_generation"] = TaskProfile(
    name="text_generation",
    fallback_chain=(
        "deepseek/deepseek-chat",
        "google/gemini-flash-1.5",
        "openai/gpt-3.5-turbo",
    ),
    overrides={},
)

PROFILES["template_assistance"] = TaskProfile(
    name="template_assistance",
    fallback_chain=(
        "google/gemini-flash-1.5",
        "meta-llama/llama-3.2-3b-instruct:free",
        "deepseek/deepseek-chat",
        "anthropic/claude-3.5-sonnet",
    ),
    overrides={
        "deepseek/deepseek-chat": ModelOverride(max_tokens=2000),
        "anthropic/claude-3.5-sonnet": ModelOverride(max_tokens=2000, timeout=20),
    },
)

PROFILES["recommendation"] = TaskProfile(
    name="recommendation",
    fallback_chain=(
        "openai/gpt-3.5-turbo",
        "moonshotai/kimi-k2:free",
    ),
    overrides={
        "openai/gpt-3.5-turbo": ModelOverride(max_tokens=1500, timeout=15),
        "moonshotai/kimi-k2:free": ModelOverride(max_tokens=1500, timeout=15),
    },
)

# ---------------------------------------------------------------------------
# Import-time validation
# ---------------------------------------------------------------------------

for _model in MODELS.values():
    _validate_model_entry(_model)

for _profile in PROFILES.values():
    _validate_profile(_profile, MODELS)

# ---------------------------------------------------------------------------
# Module-level resolver instance
# ---------------------------------------------------------------------------

resolver = ProfileResolver(MODELS, PROFILES)
