import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database import DatabaseManager

db = DatabaseManager()

# Check both records
records = db.execute_query(
    "SELECT ID, Omschrijving, Bedrag, Datum FROM mutaties WHERE ID IN (61679, 61901)"
)

print("Current records:")
for r in records:
    print(f"ID {r['ID']}: {r['Omschrijving']} | {r['Bedrag']} | {r['Datum']}")

# Delete the one with encoding issue (Ã¸)
db.execute_query(
    "DELETE FROM mutaties WHERE ID = 61901 AND Omschrijving LIKE %s",
    ('%Ã¸%',),
    fetch=False,
    commit=True
)

print(f"\nDeleted record 61901 with encoding issue")
print(f"Kept record 61679 with correct UTF-8: Søstrene Grene")
