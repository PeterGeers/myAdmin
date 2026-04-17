#!/usr/bin/env python3
"""Seed branding parameters for tenants that currently have hardcoded company info.

Seeds both str_branding (STR module) and zzp_branding (ZZP module) namespaces.
"""

import sys
from pathlib import Path

backend_src = Path(__file__).parent.parent / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager
from services.parameter_service import ParameterService


def seed_namespace(ps, tenant: str, namespace: str, params: dict):
    """Seed parameters for a given namespace."""
    for key, value in params.items():
        existing = ps.get_param(namespace, key, tenant=tenant)
        if existing is not None:
            print(f"  ⏭  {namespace}.{key} already set: {existing}")
            continue
        ps.set_param('tenant', tenant, namespace, key, value,
                      value_type='string', created_by='seed_branding')
        print(f"  ✅ {namespace}.{key} = {value}")


if __name__ == '__main__':
    db = DatabaseManager(test_mode=False)
    ps = ParameterService(db)

    # Shared company details
    shared_params = {
        'company_name': 'Jabaki a Goodwin Solutions Company',
        'company_address': 'Beemsterstraat 3',
        'company_postal_city': '2131 ZA Hoofddorp',
        'company_country': 'Nederland',
        'company_vat': 'NL812613764B02',
        'company_coc': '24352408',
        'contact_email': 'peter@jabaki.nl',
        'company_logo_file_id': '1EJ1wo3qCWUzdUOoW5AYhZM1Fhz0vGJyW',
    }

    # ZZP-specific keys (company_iban and company_phone are new for ZZP)
    zzp_extra = {
        'company_iban': '',
        'company_phone': '',
    }

    print("Seeding STR branding parameters for GoodwinSolutions...")
    seed_namespace(ps, 'GoodwinSolutions', 'str_branding', shared_params)

    print("\nSeeding ZZP branding parameters for GoodwinSolutions...")
    seed_namespace(ps, 'GoodwinSolutions', 'zzp_branding',
                   {**shared_params, **zzp_extra})

    print("\nDone.")
