#!/usr/bin/env python3
"""Seed branding parameters for tenants that currently have hardcoded company info."""

import sys
from pathlib import Path

backend_src = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager
from services.parameter_service import ParameterService


def seed_branding(tenant: str, params: dict):
    db = DatabaseManager(test_mode=False)
    ps = ParameterService(db)

    for key, value in params.items():
        existing = ps.get_param('branding', key, tenant=tenant)
        if existing is not None:
            print(f"  ⏭  branding.{key} already set: {existing}")
            continue
        ps.set_param('tenant', tenant, 'branding', key, value,
                      value_type='string', created_by='seed_branding')
        print(f"  ✅ branding.{key} = {value}")


if __name__ == '__main__':
    print("Seeding branding parameters for GoodwinSolutions...")
    seed_branding('GoodwinSolutions', {
        'company_name': 'Jabaki a Goodwin Solutions Company',
        'company_address': 'Beemsterstraat 3',
        'company_postal_city': '2131 ZA Hoofddorp',
        'company_country': 'Nederland',
        'company_vat': 'NL812613764B02',
        'company_coc': '24352408',
        'contact_email': 'peter@jabaki.nl',
        'company_logo_file_id': '1EJ1wo3qCWUzdUOoW5AYhZM1Fhz0vGJyW',
    })
    print("\nDone.")
