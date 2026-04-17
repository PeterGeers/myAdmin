"""
ContactService: Shared contact registry CRUD with multi-tenant isolation.

Reusable by future modules (Webshop, Logistics). No ZZP route dependency.
Uses FieldConfigMixin for parameter-driven field validation.

Reference: .kiro/specs/zzp-module/design.md §5.1
"""

import logging
import re
from typing import Dict, List, Optional

from services.field_config_mixin import FieldConfigMixin

logger = logging.getLogger(__name__)

# client_id: alphanumeric + hyphen/underscore, max 20 chars
CLIENT_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,20}$')


class ContactService(FieldConfigMixin):
    """Shared contact CRUD scoped by tenant."""

    FIELD_CONFIG_KEY = 'contact_field_config'
    ALWAYS_REQUIRED = ['client_id', 'company_name']

    def __init__(self, db, parameter_service=None):
        self.db = db
        self.parameter_service = parameter_service

    # ── Read ────────────────────────────────────────────────

    def list_contacts(self, tenant: str, contact_type: str = None,
                      include_inactive: bool = False) -> List[dict]:
        """List contacts for tenant, optionally filtered by type."""
        query = "SELECT * FROM contacts WHERE administration = %s"
        params: list = [tenant]

        if not include_inactive:
            query += " AND is_active = TRUE"
        if contact_type:
            query += " AND contact_type = %s"
            params.append(contact_type)

        query += " ORDER BY company_name"
        contacts = self.db.execute_query(query, tuple(params)) or []

        for c in contacts:
            c['emails'] = self._get_emails(c['id'])

        return [self.strip_hidden_fields(tenant, c) for c in contacts]

    def get_contact(self, tenant: str, contact_id: int) -> Optional[dict]:
        """Get single contact by id."""
        rows = self.db.execute_query(
            "SELECT * FROM contacts WHERE id = %s AND administration = %s",
            (contact_id, tenant),
        )
        if not rows:
            return None
        contact = rows[0]
        contact['emails'] = self._get_emails(contact['id'])
        return self.strip_hidden_fields(tenant, contact)

    def get_contact_by_client_id(self, tenant: str, client_id: str) -> Optional[dict]:
        """Get contact by short client_id reference."""
        rows = self.db.execute_query(
            "SELECT * FROM contacts WHERE client_id = %s AND administration = %s",
            (client_id, tenant),
        )
        if not rows:
            return None
        contact = rows[0]
        contact['emails'] = self._get_emails(contact['id'])
        return self.strip_hidden_fields(tenant, contact)

    # ── Write ───────────────────────────────────────────────

    def create_contact(self, tenant: str, data: dict, created_by: str) -> dict:
        """Create a new contact with optional emails."""
        self._sanitize_client_id(data.get('client_id', ''))
        self.validate_fields(tenant, data)
        self._validate_contact_type(tenant, data.get('contact_type', 'client'))
        self._check_client_id_unique(tenant, data['client_id'])

        emails = data.pop('emails', [])

        contact_id = self.db.execute_query(
            """INSERT INTO contacts
               (administration, client_id, contact_type, company_name,
                contact_person, street_address, postal_code, city, country,
                vat_number, kvk_number, phone, iban, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                tenant,
                data['client_id'],
                data.get('contact_type', 'client'),
                data['company_name'],
                data.get('contact_person'),
                data.get('street_address'),
                data.get('postal_code'),
                data.get('city'),
                data.get('country', 'NL'),
                data.get('vat_number'),
                data.get('kvk_number'),
                data.get('phone'),
                data.get('iban'),
                created_by,
            ),
            fetch=False, commit=True,
        )

        if emails:
            self._save_emails(contact_id, emails)

        return self.get_contact(tenant, contact_id)

    def update_contact(self, tenant: str, contact_id: int, data: dict) -> dict:
        """Update an existing contact."""
        existing = self.get_contact(tenant, contact_id)
        if not existing:
            raise ValueError(f"Contact {contact_id} not found")

        if 'client_id' in data and data['client_id'] != existing['client_id']:
            self._sanitize_client_id(data['client_id'])
            self._check_client_id_unique(tenant, data['client_id'], exclude_id=contact_id)

        if 'contact_type' in data:
            self._validate_contact_type(tenant, data['contact_type'])

        emails = data.pop('emails', None)

        fields = [
            'client_id', 'contact_type', 'company_name', 'contact_person',
            'street_address', 'postal_code', 'city', 'country',
            'vat_number', 'kvk_number', 'phone', 'iban',
        ]
        sets = []
        params = []
        for f in fields:
            if f in data:
                sets.append(f"{f} = %s")
                params.append(data[f])

        if sets:
            params.extend([contact_id, tenant])
            self.db.execute_query(
                f"UPDATE contacts SET {', '.join(sets)} WHERE id = %s AND administration = %s",
                tuple(params), fetch=False, commit=True,
            )

        if emails is not None:
            self._replace_emails(contact_id, emails)

        return self.get_contact(tenant, contact_id)

    def soft_delete_contact(self, tenant: str, contact_id: int) -> bool:
        """Soft-delete (deactivate) a contact if not referenced by invoices."""
        existing = self.get_contact(tenant, contact_id)
        if not existing:
            raise ValueError(f"Contact {contact_id} not found")

        if self._check_contact_in_use(contact_id):
            raise ValueError(
                "Cannot delete contact: referenced by existing invoices"
            )

        self.db.execute_query(
            "UPDATE contacts SET is_active = FALSE WHERE id = %s AND administration = %s",
            (contact_id, tenant), fetch=False, commit=True,
        )
        return True

    # ── Email helpers ───────────────────────────────────────

    def get_invoice_email(self, tenant: str, contact_id: int) -> Optional[str]:
        """Return invoice email, falling back to primary email."""
        rows = self.db.execute_query(
            """SELECT email, email_type, is_primary FROM contact_emails
               WHERE contact_id = %s ORDER BY FIELD(email_type,'invoice','general','other')""",
            (contact_id,),
        )
        if not rows:
            return None

        # Prefer invoice type
        for r in rows:
            if r['email_type'] == 'invoice':
                return r['email']
        # Fallback to primary
        for r in rows:
            if r['is_primary']:
                return r['email']
        # Last resort: first email
        return rows[0]['email']

    # ── Parameter lookups ───────────────────────────────────

    def get_contact_types(self, tenant: str) -> List[str]:
        """Return configurable contact types from ParameterService."""
        if self.parameter_service:
            types = self.parameter_service.get_param('zzp', 'contact_types', tenant=tenant)
            if types:
                return types
        from services.module_registry import MODULE_REGISTRY
        return list(MODULE_REGISTRY['ZZP']['required_params']['zzp.contact_types']['default'])

    # ── Private helpers ─────────────────────────────────────

    def _validate_contact_type(self, tenant: str, contact_type: str) -> None:
        valid = self.get_contact_types(tenant)
        if contact_type not in valid:
            raise ValueError(
                f"Invalid contact_type '{contact_type}'. Must be one of: {', '.join(valid)}"
            )

    @staticmethod
    def _sanitize_client_id(client_id: str) -> None:
        if not client_id or not CLIENT_ID_PATTERN.match(client_id):
            raise ValueError(
                "client_id must be 1-20 alphanumeric characters, hyphens, or underscores"
            )

    def _check_client_id_unique(self, tenant: str, client_id: str,
                                exclude_id: int = None) -> None:
        query = ("SELECT id FROM contacts "
                 "WHERE administration = %s AND client_id = %s")
        params: list = [tenant, client_id]
        if exclude_id:
            query += " AND id != %s"
            params.append(exclude_id)
        rows = self.db.execute_query(query, tuple(params))
        if rows:
            raise ValueError(f"client_id '{client_id}' already exists for this tenant")

    def _check_contact_in_use(self, contact_id: int) -> bool:
        rows = self.db.execute_query(
            "SELECT 1 FROM invoices WHERE contact_id = %s LIMIT 1",
            (contact_id,),
        )
        return bool(rows)

    def _get_emails(self, contact_id: int) -> List[dict]:
        rows = self.db.execute_query(
            "SELECT id, email, email_type, is_primary FROM contact_emails WHERE contact_id = %s",
            (contact_id,),
        )
        return rows or []

    def _save_emails(self, contact_id: int, emails: List[dict]) -> None:
        for em in emails:
            self.db.execute_query(
                """INSERT INTO contact_emails (contact_id, email, email_type, is_primary)
                   VALUES (%s, %s, %s, %s)""",
                (contact_id, em['email'], em.get('email_type', 'general'),
                 em.get('is_primary', False)),
                fetch=False, commit=True,
            )

    def _replace_emails(self, contact_id: int, emails: List[dict]) -> None:
        """Delete existing emails and re-insert."""
        self.db.execute_query(
            "DELETE FROM contact_emails WHERE contact_id = %s",
            (contact_id,), fetch=False, commit=True,
        )
        self._save_emails(contact_id, emails)
