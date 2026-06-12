"""
Property-based tests for Function Registry validation.

Uses hypothesis to verify correctness properties from the design document.
Feature: tenant-optional-functions

Requirements: 1.4
Reference: .kiro/specs/tenant-optional-functions/design.md
"""

import sys
import os
import re
import pytest
from unittest.mock import patch
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.function_registry import (
    FUNCTION_REGISTRY,
    FunctionDefinition,
    validate_function_registry,
    IDENTIFIER_PATTERN,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid snake_case identifiers (1-50 chars, starts with lowercase letter)
valid_identifier_st = st.from_regex(r'^[a-z][a-z0-9_]{0,49}$', fullmatch=True)

# Valid labels (non-empty, max 100 characters)
valid_label_st = st.text(min_size=1, max_size=100)

# Module names that are NOT in the real MODULE_REGISTRY
# We generate arbitrary uppercase strings that won't collide with real modules
invalid_module_st = st.text(
    alphabet=st.characters(whitelist_categories=('Lu',), whitelist_characters='_'),
    min_size=1, max_size=10,
).filter(lambda m: m not in ('FIN', 'STR', 'TENADMIN', 'ZZP'))


# ---------------------------------------------------------------------------
# Property 1: Registry validation rejects invalid parent modules
# Feature: tenant-optional-functions, Property 1: Registry validation rejects invalid parent modules
# Validates: Requirements 1.4
# ---------------------------------------------------------------------------

class TestRegistryValidationRejectsInvalidModules:
    """For any function definition with a parent_module not in MODULE_REGISTRY,
    validate_function_registry() SHALL raise a ValueError."""

    @settings(max_examples=100)
    @given(
        func_id=valid_identifier_st,
        invalid_module=invalid_module_st,
        label=valid_label_st,
        default_enabled=st.booleans(),
    )
    def test_invalid_parent_module_raises_value_error(
        self, func_id, invalid_module, label, default_enabled
    ):
        """Validation rejects any registry entry whose parent_module is not in MODULE_REGISTRY."""
        # Build a registry with one entry containing an invalid parent module
        test_registry = {
            func_id: {
                'parent_module': invalid_module,
                'label': label,
                'default_enabled': default_enabled,
            }
        }

        # Mock MODULE_REGISTRY with a known set of valid modules
        valid_modules = {
            'FIN': {'description': 'Financial Administration'},
            'STR': {'description': 'Short-Term Rental Management'},
        }

        with patch('services.function_registry.MODULE_REGISTRY', valid_modules), \
             patch('services.function_registry.FUNCTION_REGISTRY', test_registry):
            # The invalid_module should not be in valid_modules
            assume(invalid_module not in valid_modules)

            with pytest.raises(ValueError, match=r"invalid parent module"):
                validate_function_registry()

    @settings(max_examples=100)
    @given(
        func_id=valid_identifier_st,
        label=valid_label_st,
        default_enabled=st.booleans(),
        module=st.sampled_from(['FIN', 'STR']),
    )
    def test_valid_parent_module_passes_validation(
        self, func_id, label, default_enabled, module
    ):
        """Validation passes when all parent_modules exist in MODULE_REGISTRY."""
        test_registry = {
            func_id: {
                'parent_module': module,
                'label': label,
                'default_enabled': default_enabled,
            }
        }

        valid_modules = {
            'FIN': {'description': 'Financial Administration'},
            'STR': {'description': 'Short-Term Rental Management'},
        }

        with patch('services.function_registry.MODULE_REGISTRY', valid_modules), \
             patch('services.function_registry.FUNCTION_REGISTRY', test_registry):
            # Should NOT raise — valid parent module
            validate_function_registry()
