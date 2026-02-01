"""
Test script to verify tourist tax rates for different dates
"""
from src.str_processor import STRProcessor
from datetime import date

processor = STRProcessor(test_mode=True)

print("=" * 80)
print("TOURIST TAX RATE VERIFICATION")
print("=" * 80)

# Test dates
test_dates = [
    "2025-12-31",  # Last day of 2025 (should be 6.02%)
    "2026-01-01",  # First day of 2026 (should be 6.9%)
    "2026-01-15",  # Mid January 2026 (should be 6.9%)
    "2025-03-08",  # March 2025 (should be 6.02%)
]

for test_date in test_dates:
    rates = processor.get_tax_rates(test_date)
    print(f"\nDate: {test_date}")
    print(f"  VAT Rate: {rates['vat_rate']}%")
    print(f"  VAT Base: {rates['vat_base']}")
    print(f"  Tourist Tax Rate: {rates['tourist_tax_rate']}%")
    print(f"  Tourist Tax Base: {rates['tourist_tax_base']}")

print("\n" + "=" * 80)
print("CALCULATION EXAMPLE")
print("=" * 80)

# Example calculation for 2026
gross_amount = 112.50
checkin_date = "2026-01-15"

tax_calc = processor.calculate_str_taxes(gross_amount, checkin_date, channel_fee=14.25)

print(f"\nGross Amount: €{gross_amount}")
print(f"Check-in Date: {checkin_date}")
print(f"Channel Fee: €14.25")
print(f"\nCalculated:")
print(f"  VAT (21%): €{tax_calc['amount_vat']}")
print(f"  Tourist Tax (6.9%): €{tax_calc['amount_tourist_tax']}")
print(f"  Net Amount: €{tax_calc['amount_nett']}")
print(f"\nTax rates used:")
print(f"  VAT: {tax_calc['tax_rates_used']['vat_rate']}%")
print(f"  Tourist Tax: {tax_calc['tax_rates_used']['tourist_tax_rate']}%")

print("\n" + "=" * 80)
