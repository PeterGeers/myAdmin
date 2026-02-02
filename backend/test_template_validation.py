import re

# Read template content
with open('.kiro/specs/Common/template-preview-validation/str_invoice_en_template.html', 'r', encoding='utf-8') as f:
    template = f.read()

# Check for event handlers
event_handlers = re.findall(
    r'<[^>]*\s(on\w+)\s*=',
    template,
    re.IGNORECASE
)
print(f'Event handlers found: {event_handlers}')

# Check for placeholders
placeholders = re.findall(r'\{\{\s*(\w+)\s*\}\}', template)
print(f'\nPlaceholders found: {sorted(set(placeholders))}')

# Check required ones
required = [
    ['invoice_number', 'reservationCode'],
    ['guest_name', 'billing_name', 'guestName'],
    ['checkin_date', 'checkinDate'],
    ['checkout_date', 'checkoutDate'],
    ['amount_gross', 'amountGross', 'table_rows'],
    ['company_name']
]

found_placeholders = set(placeholders)
print('\nRequired placeholder check:')
for placeholder_options in required:
    found = any(opt in found_placeholders for opt in placeholder_options)
    status = "✓ FOUND" if found else "✗ MISSING"
    print(f'  {status}: {placeholder_options[0]} (alternatives: {placeholder_options[1:]})')
