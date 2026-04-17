"""
TimeTrackingService: Time entry CRUD, summaries, and billing integration.

Standalone optional feature — invoices never require time entries.
Enabled/disabled per tenant via zzp.time_tracking_enabled parameter.

Reference: .kiro/specs/zzp-module/design.md §5.8
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional

from services.field_config_mixin import FieldConfigMixin

logger = logging.getLogger(__name__)


class TimeTrackingService(FieldConfigMixin):
    """Time entry CRUD scoped by tenant."""

    FIELD_CONFIG_KEY = 'time_entry_field_config'
    ALWAYS_REQUIRED = ['contact_id', 'entry_date', 'hours', 'hourly_rate']

    def __init__(self, db, parameter_service=None):
        self.db = db
        self.parameter_service = parameter_service

    def is_enabled(self, tenant: str) -> bool:
        """Check if time tracking is enabled for this tenant."""
        if self.parameter_service:
            val = self.parameter_service.get_param(
                'zzp', 'time_tracking_enabled', tenant=tenant)
            if val is not None:
                return bool(val)
        return True  # default enabled

    def create_entry(self, tenant: str, data: dict, created_by: str) -> dict:
        """Create a time entry."""
        self.validate_fields(tenant, data)
        self._validate_contact(tenant, data['contact_id'])
        if data.get('product_id'):
            self._validate_product(tenant, data['product_id'])

        entry_id = self.db.execute_query(
            """INSERT INTO time_entries
               (administration, contact_id, product_id, project_name,
                entry_date, hours, hourly_rate, description,
                is_billable, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (tenant, data['contact_id'], data.get('product_id'),
             data.get('project_name'), data['entry_date'],
             data['hours'], data['hourly_rate'],
             data.get('description'),
             data.get('is_billable', True), created_by),
            fetch=False, commit=True)
        return self.get_entry(tenant, entry_id)

    def update_entry(self, tenant: str, entry_id: int, data: dict) -> dict:
        """Update a time entry. Only allowed if not yet billed."""
        existing = self.get_entry(tenant, entry_id)
        if not existing:
            raise ValueError(f"Time entry {entry_id} not found")
        if existing.get('is_billed'):
            raise ValueError("Cannot edit a billed time entry")

        if 'contact_id' in data:
            self._validate_contact(tenant, data['contact_id'])
        if 'product_id' in data and data['product_id']:
            self._validate_product(tenant, data['product_id'])

        fields = ['contact_id', 'product_id', 'project_name', 'entry_date',
                  'hours', 'hourly_rate', 'description', 'is_billable']
        sets, params = [], []
        for f in fields:
            if f in data:
                sets.append(f"{f} = %s")
                params.append(data[f])
        if sets:
            params.extend([entry_id, tenant])
            self.db.execute_query(
                f"UPDATE time_entries SET {', '.join(sets)} "
                f"WHERE id = %s AND administration = %s",
                tuple(params), fetch=False, commit=True)
        return self.get_entry(tenant, entry_id)

    def delete_entry(self, tenant: str, entry_id: int) -> bool:
        """Delete a time entry. Only allowed if not yet billed."""
        existing = self.get_entry(tenant, entry_id)
        if not existing:
            raise ValueError(f"Time entry {entry_id} not found")
        if existing.get('is_billed'):
            raise ValueError("Cannot delete a billed time entry")
        self.db.execute_query(
            "DELETE FROM time_entries WHERE id = %s AND administration = %s",
            (entry_id, tenant), fetch=False, commit=True)
        return True

    def get_entry(self, tenant: str, entry_id: int) -> Optional[dict]:
        rows = self.db.execute_query(
            "SELECT * FROM time_entries WHERE id = %s AND administration = %s",
            (entry_id, tenant))
        return self._format_entry(rows[0]) if rows else None

    def list_entries(self, tenant: str, filters: dict = None) -> list:
        filters = filters or {}
        query = "SELECT * FROM time_entries WHERE administration = %s"
        params: list = [tenant]
        if filters.get('contact_id'):
            query += " AND contact_id = %s"
            params.append(filters['contact_id'])
        if filters.get('project_name'):
            query += " AND project_name = %s"
            params.append(filters['project_name'])
        if filters.get('date_from'):
            query += " AND entry_date >= %s"
            params.append(filters['date_from'])
        if filters.get('date_to'):
            query += " AND entry_date <= %s"
            params.append(filters['date_to'])
        if 'is_billable' in filters:
            query += " AND is_billable = %s"
            params.append(filters['is_billable'])
        if 'is_billed' in filters:
            query += " AND is_billed = %s"
            params.append(filters['is_billed'])
        query += " ORDER BY entry_date DESC"
        limit = filters.get('limit', 50)
        offset = filters.get('offset', 0)
        query += " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        rows = self.db.execute_query(query, tuple(params)) or []
        return [self._format_entry(r) for r in rows]

    def get_unbilled_entries(self, tenant: str, contact_id: int) -> list:
        rows = self.db.execute_query(
            """SELECT * FROM time_entries
               WHERE administration = %s AND contact_id = %s
                 AND is_billable = TRUE AND is_billed = FALSE
               ORDER BY entry_date""",
            (tenant, contact_id)) or []
        return [self._format_entry(r) for r in rows]

    def mark_as_billed(self, tenant: str, entry_ids: list,
                       invoice_id: int) -> int:
        if not entry_ids:
            return 0
        placeholders = ','.join(['%s'] * len(entry_ids))
        result = self.db.execute_query(
            f"""UPDATE time_entries
                SET is_billed = TRUE, invoice_id = %s
                WHERE administration = %s AND id IN ({placeholders})
                  AND is_billed = FALSE""",
            (invoice_id, tenant, *entry_ids),
            fetch=False, commit=True)
        return result if isinstance(result, int) else 0

    def get_summary(self, tenant: str, group_by: str = 'contact',
                    period: str = None) -> list:
        if group_by == 'contact':
            query = """SELECT contact_id, SUM(hours) as total_hours,
                              SUM(hours * hourly_rate) as total_amount
                       FROM time_entries WHERE administration = %s
                       GROUP BY contact_id"""
        elif group_by == 'project':
            query = """SELECT project_name, SUM(hours) as total_hours,
                              SUM(hours * hourly_rate) as total_amount
                       FROM time_entries WHERE administration = %s
                       GROUP BY project_name"""
        else:
            # period grouping (week/month/quarter/year)
            date_fmt = {'week': '%x-%v', 'month': '%Y-%m',
                        'quarter': "CONCAT(YEAR(entry_date),'-Q',QUARTER(entry_date))",
                        'year': '%Y'}.get(period or 'month', '%Y-%m')
            if period == 'quarter':
                query = f"""SELECT {date_fmt} as period,
                                   SUM(hours) as total_hours,
                                   SUM(hours * hourly_rate) as total_amount
                            FROM time_entries WHERE administration = %s
                            GROUP BY period"""
            else:
                query = f"""SELECT DATE_FORMAT(entry_date, '{date_fmt}') as period,
                                   SUM(hours) as total_hours,
                                   SUM(hours * hourly_rate) as total_amount
                            FROM time_entries WHERE administration = %s
                            GROUP BY period"""
        return self.db.execute_query(query, (tenant,)) or []

    # ── Private helpers ─────────────────────────────────────

    @staticmethod
    def _format_entry(row: dict) -> dict:
        """Convert date/datetime objects to ISO strings and Decimal to float."""
        row = dict(row)
        for key in ('entry_date', 'created_at', 'updated_at'):
            val = row.get(key)
            if val is not None and hasattr(val, 'isoformat') and not isinstance(val, str):
                row[key] = val.isoformat()
        for key in ('hours', 'hourly_rate'):
            if isinstance(row.get(key), Decimal):
                row[key] = float(row[key])
        return row

    def enrich_with_contacts(self, tenant: str, entries: list) -> list:
        """Add contact info (id, client_id, company_name) to each entry."""
        if not entries:
            return entries
        contact_ids = list({e['contact_id'] for e in entries})
        placeholders = ','.join(['%s'] * len(contact_ids))
        rows = self.db.execute_query(
            f"""SELECT id, client_id, company_name FROM contacts
                WHERE administration = %s AND id IN ({placeholders})""",
            (tenant, *contact_ids),
        ) or []
        contact_map = {r['id']: {'id': r['id'], 'client_id': r['client_id'],
                                  'company_name': r['company_name']} for r in rows}
        for entry in entries:
            entry['contact'] = contact_map.get(entry['contact_id'])
        return entries

    def _validate_contact(self, tenant, contact_id):
        rows = self.db.execute_query(
            "SELECT id FROM contacts WHERE id = %s AND administration = %s",
            (contact_id, tenant))
        if not rows:
            raise ValueError(f"Contact {contact_id} not found")

    def _validate_product(self, tenant, product_id):
        rows = self.db.execute_query(
            "SELECT id FROM products WHERE id = %s AND administration = %s",
            (product_id, tenant))
        if not rows:
            raise ValueError(f"Product {product_id} not found")
