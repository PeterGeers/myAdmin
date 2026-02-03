-- ============================================================================
-- Fix Template Field Mappings
-- ============================================================================
-- This script:
-- 1. Deletes STR templates from PeterPrive (no STR function)
-- 2. Updates all field_mappings to proper format with type specifications
-- ============================================================================

USE finance;

-- ============================================================================
-- STEP 1: Delete STR templates from PeterPrive
-- ============================================================================

DELETE FROM tenant_template_config 
WHERE administration = 'PeterPrive' 
  AND template_type IN ('str_invoice_nl', 'str_invoice_en', 'toeristenbelasting_html');

-- ============================================================================
-- STEP 2: Update field_mappings for GoodwinSolutions STR Invoice NL
-- ============================================================================

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
            'format', 'number'
        ),
        'guests', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.guests',
            'format', 'number'
        ),
        'listing', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.listing',
            'format', 'text'
        ),
        'channel', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.channel',
            'format', 'text'
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
            'default', 'Reservering'
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
)
WHERE administration = 'GoodwinSolutions' 
  AND template_type = 'str_invoice_nl';

-- ============================================================================
-- STEP 3: Update field_mappings for GoodwinSolutions STR Invoice EN
-- ============================================================================

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
            'format', 'number'
        ),
        'guests', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.guests',
            'format', 'number'
        ),
        'listing', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.listing',
            'format', 'text'
        ),
        'channel', JSON_OBJECT(
            'source', 'database',
            'path', 'booking.channel',
            'format', 'text'
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
            'default', 'Reservation'
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
)
WHERE administration = 'GoodwinSolutions' 
  AND template_type = 'str_invoice_en';

-- ============================================================================
-- STEP 4: Update field_mappings for Toeristenbelasting (GoodwinSolutions only)
-- ============================================================================

UPDATE tenant_template_config
SET field_mappings = JSON_OBJECT(
    'fields', JSON_OBJECT(
        'year', JSON_OBJECT(
            'source', 'database',
            'path', 'report.year',
            'format', 'number',
            'required', true
        ),
        'totaal_verhuurde_nachten', JSON_OBJECT(
            'source', 'calculation',
            'path', 'report.totaal_verhuurde_nachten',
            'format', 'number',
            'required', true
        ),
        'totaal_belastbare_nachten', JSON_OBJECT(
            'source', 'calculation',
            'path', 'report.totaal_belastbare_nachten',
            'format', 'number',
            'required', true
        ),
        'saldo_toeristenbelasting', JSON_OBJECT(
            'source', 'calculation',
            'path', 'report.saldo_toeristenbelasting',
            'format', 'currency',
            'transform', 'abs'
        ),
        'belastbare_omzet_logies', JSON_OBJECT(
            'source', 'calculation',
            'path', 'report.belastbare_omzet_logies',
            'format', 'currency',
            'required', true
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
)
WHERE administration = 'GoodwinSolutions' 
  AND template_type = 'toeristenbelasting_html';

-- ============================================================================
-- Verification Query
-- ============================================================================

SELECT 
    id,
    administration,
    template_type,
    is_active,
    JSON_PRETTY(field_mappings) as field_mappings
FROM tenant_template_config
WHERE administration IN ('GoodwinSolutions', 'PeterPrive')
ORDER BY administration, template_type;
