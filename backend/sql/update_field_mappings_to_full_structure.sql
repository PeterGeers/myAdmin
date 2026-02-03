-- ============================================================================
-- Update Field Mappings to Full Structure
-- ============================================================================
-- This script updates the field_mappings column in tenant_template_config
-- from simple name mappings to the full structure with format specifications
-- ============================================================================

-- STR Invoice NL
UPDATE tenant_template_config
SET field_mappings = JSON_OBJECT(
    'fields', JSON_OBJECT(
        'reservationCode', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.reservationCode',
            'format', 'text',
            'required', true
        ),
        'guestName', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.guestName',
            'format', 'text',
            'required', true
        ),
        'checkinDate', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.checkinDate',
            'format', 'date',
            'required', true
        ),
        'checkoutDate', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.checkoutDate',
            'format', 'date',
            'required', true
        ),
        'nights', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.nights',
            'format', 'number',
            'default', 1
        ),
        'guests', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.guests',
            'format', 'number',
            'default', 1
        ),
        'listing', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.listing',
            'format', 'text',
            'required', true
        ),
        'channel', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.channel',
            'format', 'text',
            'required', true
        ),
        'net_amount', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.amountNett',
            'format', 'currency',
            'required', true
        ),
        'tourist_tax', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.amountTouristTax',
            'format', 'currency',
            'default', 0
        ),
        'amountGross', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.amountGross',
            'format', 'currency',
            'required', true
        ),
        'invoice_date', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.checkinDate',
            'format', 'date',
            'required', true
        ),
        'due_date', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.checkinDate',
            'format', 'date',
            'required', true
        ),
        'billing_name', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.guestName',
            'format', 'text',
            'default', 'Guest'
        ),
        'billing_address', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.channel',
            'format', 'text',
            'default', 'Via booking platform'
        ),
        'billing_city', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.reservationCode',
            'format', 'text',
            'default', ''
        )
    ),
    'formatting', JSON_OBJECT(
        'currency', 'EUR',
        'date_format', 'DD-MM-YYYY',
        'number_decimals', 2,
        'locale', 'nl-NL'
    ),
    'metadata', JSON_OBJECT(
        'version', '1.0.0',
        'last_updated', CURDATE()
    )
),
updated_at = NOW()
WHERE template_type = 'str_invoice_nl';

-- STR Invoice EN
UPDATE tenant_template_config
SET field_mappings = JSON_OBJECT(
    'fields', JSON_OBJECT(
        'reservationCode', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.reservationCode',
            'format', 'text',
            'required', true
        ),
        'guestName', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.guestName',
            'format', 'text',
            'required', true
        ),
        'checkinDate', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.checkinDate',
            'format', 'date',
            'required', true
        ),
        'checkoutDate', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.checkoutDate',
            'format', 'date',
            'required', true
        ),
        'nights', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.nights',
            'format', 'number',
            'default', 1
        ),
        'guests', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.guests',
            'format', 'number',
            'default', 1
        ),
        'listing', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.listing',
            'format', 'text',
            'required', true
        ),
        'channel', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.channel',
            'format', 'text',
            'required', true
        ),
        'net_amount', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.amountNett',
            'format', 'currency',
            'required', true
        ),
        'tourist_tax', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.amountTouristTax',
            'format', 'currency',
            'default', 0
        ),
        'amountGross', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.amountGross',
            'format', 'currency',
            'required', true
        ),
        'invoice_date', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.checkinDate',
            'format', 'date',
            'required', true
        ),
        'due_date', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.checkinDate',
            'format', 'date',
            'required', true
        ),
        'billing_name', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.guestName',
            'format', 'text',
            'default', 'Guest'
        ),
        'billing_address', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.channel',
            'format', 'text',
            'default', 'Via booking platform'
        ),
        'billing_city', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.reservationCode',
            'format', 'text',
            'default', ''
        )
    ),
    'formatting', JSON_OBJECT(
        'currency', 'EUR',
        'date_format', 'DD-MM-YYYY',
        'number_decimals', 2,
        'locale', 'en-US'
    ),
    'metadata', JSON_OBJECT(
        'version', '1.0.0',
        'last_updated', CURDATE()
    )
),
updated_at = NOW()
WHERE template_type = 'str_invoice_en';

-- BTW Aangifte
UPDATE tenant_template_config
SET field_mappings = JSON_OBJECT(
    'fields', JSON_OBJECT(
        'administration', JSON_OBJECT(
            'source', 'database',
            'path', 'report.administration',
            'format', 'text',
            'required', true
        ),
        'year', JSON_OBJECT(
            'source', 'database',
            'path', 'report.year',
            'format', 'number',
            'required', true
        ),
        'quarter', JSON_OBJECT(
            'source', 'database',
            'path', 'report.quarter',
            'format', 'number',
            'required', true
        ),
        'end_date', JSON_OBJECT(
            'source', 'database',
            'path', 'report.quarter_end_date',
            'format', 'date',
            'required', true
        ),
        'total_balance', JSON_OBJECT(
            'source', 'calculation',
            'path', 'calculations.total_balance',
            'format', 'currency',
            'required', true
        ),
        'received_btw', JSON_OBJECT(
            'source', 'calculation',
            'path', 'calculations.received_btw',
            'format', 'currency',
            'transform', 'abs'
        ),
        'prepaid_btw', JSON_OBJECT(
            'source', 'calculation',
            'path', 'calculations.prepaid_btw',
            'format', 'currency'
        ),
        'payment_instruction', JSON_OBJECT(
            'source', 'calculation',
            'path', 'calculations.payment_instruction',
            'format', 'text',
            'required', true
        ),
        'balance_rows', JSON_OBJECT(
            'source', 'database',
            'path', 'report.balance_data',
            'format', 'table'
        ),
        'quarter_rows', JSON_OBJECT(
            'source', 'database',
            'path', 'report.quarter_data',
            'format', 'table'
        )
    ),
    'formatting', JSON_OBJECT(
        'currency', 'EUR',
        'date_format', 'YYYY-MM-DD',
        'number_decimals', 2,
        'locale', 'nl-NL'
    ),
    'metadata', JSON_OBJECT(
        'version', '1.0.0',
        'last_updated', CURDATE()
    )
),
updated_at = NOW()
WHERE template_type = 'btw_aangifte';

-- Aangifte IB
UPDATE tenant_template_config
SET field_mappings = JSON_OBJECT(
    'fields', JSON_OBJECT(
        'year', JSON_OBJECT(
            'source', 'database',
            'path', 'report.year',
            'format', 'number',
            'required', true
        ),
        'administration', JSON_OBJECT(
            'source', 'database',
            'path', 'report.administration',
            'format', 'text',
            'required', true
        ),
        'table_rows', JSON_OBJECT(
            'source', 'database',
            'path', 'report.table_data',
            'format', 'table',
            'required', true
        ),
        'generated_date', JSON_OBJECT(
            'source', 'calculation',
            'path', 'report.generated_date',
            'format', 'date',
            'required', true
        ),
        'total_income', JSON_OBJECT(
            'source', 'calculation',
            'path', 'report.total_income',
            'format', 'currency'
        ),
        'total_expenses', JSON_OBJECT(
            'source', 'calculation',
            'path', 'report.total_expenses',
            'format', 'currency'
        )
    ),
    'formatting', JSON_OBJECT(
        'currency', 'EUR',
        'date_format', 'DD-MM-YYYY',
        'number_decimals', 2,
        'locale', 'nl-NL'
    ),
    'metadata', JSON_OBJECT(
        'version', '1.0.0',
        'last_updated', CURDATE()
    )
),
updated_at = NOW()
WHERE template_type = 'aangifte_ib';

-- Toeristenbelasting
UPDATE tenant_template_config
SET field_mappings = JSON_OBJECT(
    'fields', JSON_OBJECT(
        'year', JSON_OBJECT(
            'source', 'database',
            'path', 'report.year',
            'format', 'number',
            'required', true
        ),
        'contact_name', JSON_OBJECT(
            'source', 'static',
            'path', 'report.contact_name',
            'format', 'text',
            'required', true
        ),
        'contact_email', JSON_OBJECT(
            'source', 'static',
            'path', 'report.contact_email',
            'format', 'text',
            'required', true
        ),
        'nights_total', JSON_OBJECT(
            'source', 'calculation',
            'path', 'report.totaal_verhuurde_nachten',
            'format', 'number',
            'required', true
        ),
        'revenue_total', JSON_OBJECT(
            'source', 'calculation',
            'path', 'report.belastbare_omzet_logies',
            'format', 'currency',
            'required', true
        ),
        'tourist_tax_total', JSON_OBJECT(
            'source', 'calculation',
            'path', 'report.saldo_toeristenbelasting',
            'format', 'currency',
            'transform', 'abs'
        )
    ),
    'formatting', JSON_OBJECT(
        'currency', 'EUR',
        'date_format', 'DD-MM-YYYY',
        'number_decimals', 2,
        'locale', 'nl-NL'
    ),
    'metadata', JSON_OBJECT(
        'version', '1.0.0',
        'last_updated', CURDATE()
    )
),
updated_at = NOW()
WHERE template_type = 'toeristenbelasting';

-- Financial Report
UPDATE tenant_template_config
SET field_mappings = JSON_OBJECT(
    'fields', JSON_OBJECT(
        'date_from', JSON_OBJECT(
            'source', 'database',
            'path', 'report.date_from',
            'format', 'date',
            'required', true
        ),
        'date_to', JSON_OBJECT(
            'source', 'database',
            'path', 'report.date_to',
            'format', 'date',
            'required', true
        ),
        'administration', JSON_OBJECT(
            'source', 'database',
            'path', 'report.administration',
            'format', 'text',
            'required', true
        ),
        'summary_data', JSON_OBJECT(
            'source', 'database',
            'path', 'report.summary_data',
            'format', 'table'
        ),
        'total_revenue', JSON_OBJECT(
            'source', 'calculation',
            'path', 'report.total_revenue',
            'format', 'currency'
        ),
        'total_expenses', JSON_OBJECT(
            'source', 'calculation',
            'path', 'report.total_expenses',
            'format', 'currency'
        ),
        'net_profit', JSON_OBJECT(
            'source', 'calculation',
            'path', 'report.net_profit',
            'format', 'currency'
        )
    ),
    'formatting', JSON_OBJECT(
        'currency', 'EUR',
        'date_format', 'DD-MM-YYYY',
        'number_decimals', 2,
        'locale', 'nl-NL'
    ),
    'metadata', JSON_OBJECT(
        'version', '1.0.0',
        'last_updated', CURDATE()
    )
),
updated_at = NOW()
WHERE template_type = 'financial_report';

-- Verify updates
SELECT 
    template_type,
    JSON_PRETTY(field_mappings) as field_mappings,
    updated_at
FROM tenant_template_config
WHERE template_type IN ('str_invoice_nl', 'str_invoice_en', 'btw_aangifte', 'aangifte_ib', 'toeristenbelasting', 'financial_report')
ORDER BY template_type;
