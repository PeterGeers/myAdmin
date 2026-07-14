"""Performance test for trip CSV import with 1000+ rows.

Tests parse_file() and validate_import() performance with a large dataset.
Target: total processing time under 30 seconds.

Usage:
    cd backend && source .venv/bin/activate && python scripts/test_import_performance.py
"""
import io
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.zzp_trip_import_service import TripImportService
from unittest.mock import MagicMock


def generate_csv(num_rows=1000):
    """Generate a large CSV with realistic trip data."""
    lines = ["Datum;Vertrekadres;Bestemming;Begin KM;Eind KM;Categorie;Doel;Klant;Notities"]
    odometer = 45000
    for i in range(num_rows):
        day = (i % 28) + 1
        month = ((i // 28) % 12) + 1
        distance = 20 + (i % 80)  # 20-100 km per trip
        lines.append(
            f"{day:02d}-{month:02d}-2026;Amsterdam;Utrecht;{odometer};{odometer + distance};Zakelijk;Klantbezoek;Acme BV;Trip {i+1}"
        )
        odometer += distance
    return "\n".join(lines)


def main():
    # Setup
    mock_db = MagicMock()
    mock_db.execute_query.return_value = []
    service = TripImportService(db=mock_db)

    csv_content = generate_csv(1000)
    print(f"Generated CSV: {len(csv_content)} bytes, ~1000 rows")

    # Test parse_file
    stream = io.BytesIO(csv_content.encode("utf-8"))
    start = time.time()
    result = service.parse_file(stream, "large_import.csv")
    parse_time = time.time() - start
    print(f"parse_file: {result['total_rows']} rows in {parse_time:.2f}s")

    if not result["success"]:
        print(f"  ERROR: {result.get('error')}")
        return

    # Test validate_import
    start = time.time()
    validation = service.validate_import("tenant1", 1, result["rows"])
    validate_time = time.time() - start
    print(f"validate_import: {validation['total_rows']} rows in {validate_time:.2f}s")
    print(f"  Valid: {validation['valid']}, Warnings: {validation['warnings']}, Errors: {validation['errors']}")

    total = parse_time + validate_time
    print(f"\nTotal: {total:.2f}s {'✓ PASS' if total < 30 else '✗ FAIL'} (target: <30s)")


if __name__ == "__main__":
    main()
