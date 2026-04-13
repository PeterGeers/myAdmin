-- Seed GoodwinSolutions STR-specific tax rates
-- Run in: finance, testfinance, and Railway
-- Idempotent: uses INSERT IGNORE
--
-- btw_accommodation: which system BTW rate applies to STR
--   low (9%) until 2025-12-31, high (21%) from 2026-01-01
-- tourist_tax: municipality-specific
--   6.02% until 2025-12-31, 6.9% from 2026-01-01
INSERT IGNORE INTO tax_rates (
        administration,
        tax_type,
        tax_code,
        rate,
        ledger_account,
        effective_from,
        effective_to,
        description,
        calc_method
    )
VALUES (
        'GoodwinSolutions',
        'btw_accommodation',
        'low',
        9.000,
        '2021',
        '2000-01-01',
        '2025-12-31',
        'BTW Logies laag tarief (verwijst naar btw low)',
        'percentage'
    ),
    (
        'GoodwinSolutions',
        'btw_accommodation',
        'high',
        21.000,
        '2020',
        '2026-01-01',
        '9999-12-31',
        'BTW Logies hoog tarief (verwijst naar btw high)',
        'percentage'
    ),
    (
        'GoodwinSolutions',
        'tourist_tax',
        'standard',
        6.020,
        NULL,
        '2000-01-01',
        '2025-12-31',
        'Toeristenbelasting 6.02%',
        'percentage'
    ),
    (
        'GoodwinSolutions',
        'tourist_tax',
        'standard',
        6.900,
        NULL,
        '2026-01-01',
        '9999-12-31',
        'Toeristenbelasting 6.9%',
        'percentage'
    );