"""
FieldConfigMixin: Shared mixin providing parameter-driven field validation
and visibility control for ZZP entities (contacts, products, invoices, time entries).

Each entity service subclasses this mixin and defines:
    FIELD_CONFIG_KEY  — parameter key, e.g. 'contact_field_config'
    ALWAYS_REQUIRED   — DB NOT NULL fields that cannot be hidden

Field levels: required | optional | hidden

Reference: .kiro/specs/zzp-module/design.md §2 (Field Visibility & Validation)
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class FieldConfigMixin:
    """Mixin providing parameter-driven field validation."""

    # Subclasses must define these
    FIELD_CONFIG_KEY: str = ''
    ALWAYS_REQUIRED: List[str] = []

    def get_field_config(self, tenant: str) -> Dict[str, str]:
        """Get field config for tenant, merging defaults with overrides.

        Resolution: ParameterService tenant override → MODULE_REGISTRY default.
        ALWAYS_REQUIRED fields are forced to 'required' regardless of config.
        """
        config = None
        if hasattr(self, 'parameter_service') and self.parameter_service:
            config = self.parameter_service.get_param(
                'zzp', self.FIELD_CONFIG_KEY, tenant=tenant
            )

        if not config:
            from services.module_registry import MODULE_REGISTRY
            param_key = f'zzp.{self.FIELD_CONFIG_KEY}'
            param_def = MODULE_REGISTRY['ZZP']['required_params'].get(param_key, {})
            config = dict(param_def.get('default', {}))
        else:
            config = dict(config)

        # Enforce minimum required fields
        for field in self.ALWAYS_REQUIRED:
            config[field] = 'required'

        return config

    def validate_fields(self, tenant: str, data: Dict[str, Any]) -> None:
        """Validate data against field config.

        Raises ValueError listing all missing required fields.
        """
        config = self.get_field_config(tenant)
        missing = [
            f for f, level in config.items()
            if level == 'required' and not data.get(f)
        ]
        if missing:
            raise ValueError(f"Required fields missing: {', '.join(missing)}")

    def strip_hidden_fields(self, tenant: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove hidden fields from response data."""
        config = self.get_field_config(tenant)
        hidden = {f for f, level in config.items() if level == 'hidden'}
        return {k: v for k, v in data.items() if k not in hidden}
