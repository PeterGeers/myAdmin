"""
FunctionRegistry: In-code Python dictionary defining all optional functions
that can be toggled per tenant within active modules.

Each function belongs to a parent module (from MODULE_REGISTRY) and has a
default enabled state. The validate_function_registry() function ensures
registry integrity at application startup.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
Reference: .kiro/specs/tenant-optional-functions/design.md
"""

import logging
import re
from typing import Dict, TypedDict

from services.module_registry import MODULE_REGISTRY

logger = logging.getLogger(__name__)

IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,49}$")


class FunctionDefinition(TypedDict):
    parent_module: str
    label: str
    default_enabled: bool


FUNCTION_REGISTRY: Dict[str, FunctionDefinition] = {
    "assets": {
        "parent_module": "FIN",
        "label": "Activa beheer",
        "default_enabled": True,
    },
    "str_channel_revenue": {
        "parent_module": "STR",
        "label": "STR Kanaal omzet",
        "default_enabled": True,
    },
    "generate_invoice": {
        "parent_module": "FIN",
        "label": "Generate Invoice",
        "default_enabled": True,
    },
    "budget": {
        "parent_module": "FIN",
        "label": "Budget Management",
        "default_enabled": True,
    },
}


def validate_function_registry() -> None:
    """
    Validate the FUNCTION_REGISTRY at application startup.

    Checks:
    - Each function identifier matches the required format (1-50 chars, snake_case)
    - Each function's parent_module exists in MODULE_REGISTRY
    - Labels are non-empty and ≤ 100 characters

    Raises:
        ValueError: If any validation check fails, with a descriptive message.
    """
    seen_identifiers: set = set()

    for identifier, definition in FUNCTION_REGISTRY.items():
        # Validate identifier format
        if not IDENTIFIER_PATTERN.match(identifier):
            raise ValueError(
                f"Invalid function identifier '{identifier}': "
                f"must match pattern ^[a-z][a-z0-9_]{{0,49}}$ "
                f"(1-50 characters, lowercase snake_case)"
            )

        # Check for duplicate identifiers (defensive — dicts prevent true duplicates,
        # but validates the identifier set is consistent)
        if identifier in seen_identifiers:
            raise ValueError(
                f"Duplicate function identifier '{identifier}' in FUNCTION_REGISTRY"
            )
        seen_identifiers.add(identifier)

        # Validate parent_module exists in MODULE_REGISTRY
        parent_module = definition.get("parent_module", "")
        if parent_module not in MODULE_REGISTRY:
            raise ValueError(
                f"Function '{identifier}' references invalid parent module "
                f"'{parent_module}': module not found in MODULE_REGISTRY"
            )

        # Validate label is non-empty and ≤ 100 characters
        label = definition.get("label", "")
        if not label:
            raise ValueError(
                f"Function '{identifier}' has an empty label: label must be non-empty"
            )
        if len(label) > 100:
            raise ValueError(
                f"Function '{identifier}' has a label exceeding 100 characters: "
                f"'{label[:50]}...' ({len(label)} chars)"
            )

    logger.info(
        "Function registry validated: %d functions registered", len(FUNCTION_REGISTRY)
    )
