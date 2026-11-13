"""Shared constants for the dispatch service container.
Part of _dispatch_services (task 9).
"""

from __future__ import annotations

from typing import Any

from services import projection_schema as schema

UNHANDLED: Any = object()
_WRITABLE_CONFIG_IDS = frozenset({schema.CONFIG_ID_SCOPE, schema.CONFIG_ID_MAIL})
_FIXED_PAGE_SIZES = frozenset({50, 100, 250, 500})
_PAGE_SIZE_MAX = "max"
_FIELDS_OP_METHODS = frozenset(
    {
        "set_field",
        "set_field_application",
        "reset_field",
        "delete_field",
        "set_group",
        "delete_group",
    }
)
_FIELD_IDENTITY_OPS = frozenset(
    {"set_field", "set_field_application", "reset_field", "delete_field"}
)
_ATTR_OPS = frozenset({"set_field", "set_field_application", "set_group"})
_WHOLE_OVERLAY_BODY_KEYS = frozenset(
    {"fields", "overrides", "fixed_overrides", "functional_groups", "field_overlay"}
)
