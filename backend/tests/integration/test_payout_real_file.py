"""
Test script to process the real Payout CSV file
"""
from src.str_processor import STRProcessor

# Path to the real Payout CSV file (from root directory)
payout_file = "../.kiro/specs/BDC-Algoritm-import-str_processor.py/Payout_from_2025-01-01_until_2025-12-31.csv"

# Create processor
processor = STRProcessor(test_mode=True)

# Process the file
print("=" * 80)
print("Processing real Payout CSV file...")
print("=" * 80)

results = processor._process_booking_payout(payout_file)

# Display results
print("\n" + "=" * 80)
print("RESULTS SUMMARY")
print("=" * 80)
print(f"Total rows in CSV: {results['summary']['total_rows']}")
print(f"Reservation rows: {results['summary']['reservation_rows']}")
print(f"Updates prepared: {results['summary']['updated_count']}")
print(f"Errors: {results['summary']['error_count']}")

if results.get('updates'):
    print("\n" + "=" * 80)
    print("SAMPLE UPDATES (first 5)")
    print("=" * 80)
    for i, update in enumerate(results['updates'][:5]):
        print(f"\n{i+1}. Reservation: {update['reservationCode']}")
        print(f"   Check-in: {update['checkinDate']}, Nights: {update['nights']}")
        print(f"   Gross: €{update['amountGross']:.2f}")
        print(f"   Channel Fee: €{update['amountChannelFee']:.2f}")
        print(f"   VAT: €{update['amountVat']:.2f}")
        print(f"   Tourist Tax: €{update['amountTouristTax']:.2f}")
        print(f"   Net: €{update['amountNett']:.2f}")
        print(f"   Price/Night: €{update['pricePerNight']:.2f}")

if results['errors']:
    print("\n" + "=" * 80)
    print("ERRORS")
    print("=" * 80)
    for error in results['errors']:
        print(f"  - {error}")

print("\n" + "=" * 80)
print("DONE")
print("=" * 80)
