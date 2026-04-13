"""
Parameter Schema: Defines all known parameters with metadata for the
structured settings UI.

Reference: .kiro/specs/parameter-driven-config/frontend-tasks.md - F9
"""

PARAMETER_SCHEMA = {
    'storage': {
        'label': 'Storage Settings',
        'label_nl': 'Opslaginstellingen',
        'params': {
            'invoice_provider': {
                'label': 'Storage Provider',
                'label_nl': 'Opslagprovider',
                'type': 'string',
                'required': True,
                'default': 's3_shared',
                'options': [
                    {'value': 'google_drive', 'label': 'Google Drive'},
                    {'value': 's3_shared', 'label': 'S3 Shared Bucket'},
                    {'value': 's3_tenant', 'label': 'S3 Tenant Bucket'},
                ],
                'description': 'Where invoices and documents are stored',
            },
            'google_drive_folder_id': {
                'label': 'Google Drive Folder ID',
                'label_nl': 'Google Drive Map ID',
                'type': 'string',
                'required': True,
                'visible_when': {'invoice_provider': 'google_drive'},
                'description': 'Root folder ID for invoice storage',
            },
            'google_drive_root_folder_id': {
                'label': 'Google Drive Root Folder',
                'label_nl': 'Google Drive Hoofdmap',
                'type': 'string',
                'visible_when': {'invoice_provider': 'google_drive'},
                'description': 'Root folder ID for tenant file structure',
            },
            'google_drive_templates_folder_id': {
                'label': 'Templates Folder ID',
                'label_nl': 'Sjablonen Map ID',
                'type': 'string',
                'visible_when': {'invoice_provider': 'google_drive'},
                'description': 'Folder ID for document templates',
            },
            'google_drive_invoices_folder_id': {
                'label': 'Invoices Folder ID',
                'label_nl': 'Facturen Map ID',
                'type': 'string',
                'visible_when': {'invoice_provider': 'google_drive'},
                'description': 'Folder ID for invoice storage',
            },
            's3_shared_bucket': {
                'label': 'S3 Shared Bucket Name',
                'label_nl': 'S3 Gedeelde Bucket',
                'type': 'string',
                'required': True,
                'visible_when': {'invoice_provider': 's3_shared'},
            },
            's3_tenant_bucket': {
                'label': 'S3 Tenant Bucket Name',
                'label_nl': 'S3 Tenant Bucket',
                'type': 'string',
                'required': True,
                'visible_when': {'invoice_provider': 's3_tenant'},
            },
            'report_output_path': {
                'label': 'Report Output Path',
                'label_nl': 'Rapport Uitvoerpad',
                'type': 'string',
                'required': False,
                'description': 'Path for generated reports (server-side)',
            },
        },
    },
    'branding': {
        'label': 'Branding',
        'label_nl': 'Huisstijl',
        'params': {
            'company_logo_file_id': {
                'label': 'Company Logo (Google Drive File ID)',
                'label_nl': 'Bedrijfslogo (Google Drive Bestands-ID)',
                'type': 'string',
                'description': 'Google Drive file ID for company logo',
            },
        },
    },
    'fin': {
        'label': 'Financial Settings',
        'label_nl': 'Financiele Instellingen',
        'module': 'FIN',
        'params': {
            'default_currency': {
                'label': 'Default Currency',
                'label_nl': 'Standaard Valuta',
                'type': 'string',
                'default': 'EUR',
                'options': [
                    {'value': 'EUR', 'label': 'Euro (EUR)'},
                    {'value': 'USD', 'label': 'US Dollar (USD)'},
                    {'value': 'GBP', 'label': 'British Pound (GBP)'},
                ],
            },
            'fiscal_year_start_month': {
                'label': 'Fiscal Year Start Month',
                'label_nl': 'Boekjaar Startmaand',
                'type': 'number',
                'default': 1,
                'min': 1,
                'max': 12,
            },
            'locale': {
                'label': 'Locale',
                'label_nl': 'Taal',
                'type': 'string',
                'default': 'nl',
                'options': [
                    {'value': 'nl', 'label': 'Nederlands'},
                    {'value': 'en', 'label': 'English'},
                ],
            },
        },
    },
    'str': {
        'label': 'Short-Term Rental Settings',
        'label_nl': 'Korte Termijn Verhuur Instellingen',
        'module': 'STR',
        'params': {
            'aantal_kamers': {
                'label': 'Number of Rooms',
                'label_nl': 'Aantal Kamers',
                'type': 'number',
                'required': True,
            },
            'aantal_slaapplaatsen': {
                'label': 'Number of Beds',
                'label_nl': 'Aantal Slaapplaatsen',
                'type': 'number',
                'required': True,
            },
            'platforms': {
                'label': 'Active Platforms',
                'label_nl': 'Actieve Platformen',
                'type': 'json',
                'default': ['airbnb', 'booking'],
                'description': 'List of active booking platforms',
            },
        },
    },
}


def get_schema_for_tenant(tenant_modules):
    """Return schema filtered by active modules."""
    result = {}
    for ns, section in PARAMETER_SCHEMA.items():
        module = section.get('module')
        if module and module not in tenant_modules:
            continue
        result[ns] = section
    return result
