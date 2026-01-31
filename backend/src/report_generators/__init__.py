"""
Report Generators Package

This package contains report generation modules for myAdmin application.
Each generator is responsible for transforming raw data into formatted output
for specific report types (HTML, XBRL, XML, etc.).

Generators follow a consistent pattern:
1. Accept raw data from database/cache
2. Apply business logic and calculations
3. Format data according to report requirements
4. Return structured output ready for template rendering

Available Generators:
- aangifte_ib_generator: Generates Aangifte IB (Income Tax) HTML reports
- btw_aangifte_generator: Generates BTW Aangifte (VAT Declaration) HTML reports
- str_invoice_generator: Generates STR (Short-Term Rental) invoice HTML reports
- toeristenbelasting_generator: Generates Toeristenbelasting (Tourist Tax) HTML reports

Common Utilities:
- common_formatters: Shared formatting utilities for currency, dates, numbers, etc.
"""

# Import generators here as they are created
from .aangifte_ib_generator import generate_table_rows
from . import str_invoice_generator
from . import btw_aangifte_generator
from . import toeristenbelasting_generator

__all__ = [
    # Generators will be exported here as they are implemented
    'generate_table_rows',
    'str_invoice_generator',
    'btw_aangifte_generator',
    'toeristenbelasting_generator',
]


