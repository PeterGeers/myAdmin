"""
Members domain layer — the generic membership engine.

Storage-agnostic and tenant-agnostic: it calls the repository through an interface,
builds no HTTP responses, writes no DynamoDB queries. This is where the reused h-dcn
business logic (fixed/variable fields, membership workflow, scope access) lands.
"""

from .applicant_locale import (
    DEFAULT_LOCALE,
    LOCALE_RECORD_KEY,
    SUPPORTED_LOCALES,
    locale_of_record,
    locale_record_patch,
    normalize_locale,
)
from .field_resolver import (
    OVERLAY_GROUP,
    FieldConfig,
    FieldOrigin,
    FieldResolver,
    FixedFieldOverride,
    OverlayError,
    OverlayField,
    ResolvedField,
    StaticOverlayProvider,
    TenantOverlay,
    TenantOverlayProvider,
)
from .membership_type_catalog import (
    CATALOG_LOCALES,
    MembershipTypeEntry,
    MembershipTypeValidationError,
)

__all__ = [
    "CATALOG_LOCALES",
    "DEFAULT_LOCALE",
    "LOCALE_RECORD_KEY",
    "OVERLAY_GROUP",
    "SUPPORTED_LOCALES",
    "FieldConfig",
    "FieldOrigin",
    "FieldResolver",
    "FixedFieldOverride",
    "MembershipTypeEntry",
    "MembershipTypeValidationError",
    "OverlayError",
    "locale_of_record",
    "locale_record_patch",
    "normalize_locale",
    "OverlayField",
    "ResolvedField",
    "StaticOverlayProvider",
    "TenantOverlay",
    "TenantOverlayProvider",
]
