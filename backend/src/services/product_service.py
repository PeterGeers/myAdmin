"""
ProductService: Shared product/service registry CRUD with multi-tenant isolation.

Validates vat_code via TaxRateService (high/low/zero only) and product_type
via ParameterService. Reusable by future modules.

Reference: .kiro/specs/zzp-module/design.md §5.2
"""

import logging
from datetime import date
from typing import Dict, List, Optional

from services.field_config_mixin import FieldConfigMixin

logger = logging.getLogger(__name__)

ALLOWED_VAT_CODES = {'high', 'low', 'zero'}


class ProductService(FieldConfigMixin):
    """Shared product/service CRUD scoped by tenant."""

    FIELD_CONFIG_KEY = 'product_field_config'
    ALWAYS_REQUIRED = ['product_code', 'name']

    def __init__(self, db, tax_rate_service=None, parameter_service=None):
        """Initialise with database handle and optional collaborators."""
        self.db = db
        self.tax_rate_service = tax_rate_service
        self.parameter_service = parameter_service

    # ── Read ────────────────────────────────────────────────

    def list_products(self, tenant: str, include_inactive: bool = False) -> List[dict]:
        query = "SELECT * FROM products WHERE administration = %s"
        params: list = [tenant]
        if not include_inactive:
            query += " AND is_active = TRUE"
        query += " ORDER BY name"
        rows = self.db.execute_query(query, tuple(params)) or []
        return [self.strip_hidden_fields(tenant, r) for r in rows]

    def get_product(self, tenant: str, product_id: int) -> Optional[dict]:
        rows = self.db.execute_query(
            "SELECT * FROM products WHERE id = %s AND administration = %s",
            (product_id, tenant),
        )
        if not rows:
            return None
        return self.strip_hidden_fields(tenant, rows[0])

    def get_product_by_code(self, tenant: str, product_code: str) -> Optional[dict]:
        rows = self.db.execute_query(
            "SELECT * FROM products WHERE product_code = %s AND administration = %s",
            (product_code, tenant),
        )
        if not rows:
            return None
        return self.strip_hidden_fields(tenant, rows[0])

    # ── Write ───────────────────────────────────────────────

    def create_product(self, tenant: str, data: dict, created_by: str) -> dict:
        """Create a new product after validating fields, VAT code, type, and uniqueness."""
        self.validate_fields(tenant, data)
        self._validate_vat_code(tenant, data['vat_code'])
        self._validate_product_type(tenant, data['product_type'])
        self._check_product_code_unique(tenant, data['product_code'])

        product_id = self.db.execute_query(
            """INSERT INTO products
               (administration, product_code, external_reference, name, description,
                product_type, unit_price, vat_code, unit_of_measure, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                tenant,
                data['product_code'],
                data.get('external_reference'),
                data['name'],
                data.get('description'),
                data['product_type'],
                data.get('unit_price', 0.00),
                data['vat_code'],
                data.get('unit_of_measure', 'uur'),
                created_by,
            ),
            fetch=False, commit=True,
        )
        return self.get_product(tenant, product_id)

    def update_product(self, tenant: str, product_id: int, data: dict) -> dict:
        """Update an existing product. Re-validates changed fields."""
        existing = self.get_product(tenant, product_id)
        if not existing:
            raise ValueError(f"Product {product_id} not found")

        if 'product_code' in data and data['product_code'] != existing['product_code']:
            self._check_product_code_unique(tenant, data['product_code'], exclude_id=product_id)

        if 'vat_code' in data:
            self._validate_vat_code(tenant, data['vat_code'])

        if 'product_type' in data:
            self._validate_product_type(tenant, data['product_type'])

        fields = [
            'product_code', 'external_reference', 'name', 'description',
            'product_type', 'unit_price', 'vat_code', 'unit_of_measure',
        ]
        sets = []
        params = []
        for f in fields:
            if f in data:
                sets.append(f"{f} = %s")
                params.append(data[f])

        if sets:
            params.extend([product_id, tenant])
            self.db.execute_query(
                f"UPDATE products SET {', '.join(sets)} WHERE id = %s AND administration = %s",
                tuple(params), fetch=False, commit=True,
            )

        return self.get_product(tenant, product_id)

    def soft_delete_product(self, tenant: str, product_id: int) -> bool:
        """Deactivate a product if it is not referenced by any invoice line."""
        existing = self.get_product(tenant, product_id)
        if not existing:
            raise ValueError(f"Product {product_id} not found")

        if self._check_product_in_use(tenant, product_id):
            raise ValueError("Cannot delete product: referenced by existing invoice lines")

        self.db.execute_query(
            "UPDATE products SET is_active = FALSE WHERE id = %s AND administration = %s",
            (product_id, tenant), fetch=False, commit=True,
        )
        return True

    # ── Parameter lookups ───────────────────────────────────

    def get_product_types(self, tenant: str) -> List[str]:
        """Return allowed product types from tenant parameters or module defaults."""
        if self.parameter_service:
            types = self.parameter_service.get_param('zzp', 'product_types', tenant=tenant)
            if types:
                return types
        from services.module_registry import MODULE_REGISTRY
        return list(MODULE_REGISTRY['ZZP']['required_params']['zzp.product_types']['default'])

    # ── Private helpers ─────────────────────────────────────

    def _validate_vat_code(self, tenant: str, vat_code: str) -> None:
        if vat_code not in ALLOWED_VAT_CODES:
            raise ValueError(
                f"Invalid vat_code '{vat_code}'. Must be one of: {', '.join(sorted(ALLOWED_VAT_CODES))}"
            )
        if self.tax_rate_service:
            rate = self.tax_rate_service.get_tax_rate(tenant, 'btw', vat_code, date.today())
            if rate is None:
                raise ValueError(
                    f"No BTW rate found for code '{vat_code}' in tenant's tax configuration"
                )

    def _validate_product_type(self, tenant: str, product_type: str) -> None:
        valid = self.get_product_types(tenant)
        if product_type not in valid:
            raise ValueError(
                f"Invalid product_type '{product_type}'. Must be one of: {', '.join(valid)}"
            )

    def _check_product_code_unique(self, tenant: str, product_code: str,
                                   exclude_id: Optional[int] = None) -> None:
        query = "SELECT id FROM products WHERE administration = %s AND product_code = %s"
        params: list = [tenant, product_code]
        if exclude_id:
            query += " AND id != %s"
            params.append(exclude_id)
        rows = self.db.execute_query(query, tuple(params))
        if rows:
            raise ValueError(f"product_code '{product_code}' already exists for this tenant")

    def _check_product_in_use(self, tenant: str, product_id: int) -> bool:
        rows = self.db.execute_query(
            "SELECT 1 FROM invoice_lines il JOIN invoices i ON il.invoice_id = i.id "
            "WHERE il.product_id = %s AND i.administration = %s LIMIT 1",
            (product_id, tenant),
        )
        return bool(rows)
