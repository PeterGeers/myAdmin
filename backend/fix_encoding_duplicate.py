import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)

cursor = conn.cursor(dictionary=True)

# Check both records
cursor.execute("SELECT ID, Omschrijving, Bedrag, Datum FROM mutaties WHERE ID IN (61679, 61901)")
records = cursor.fetchall()

print("Current records:")
for r in records:
    print(f"ID {r['ID']}: {r['Omschrijving']} | {r['Bedrag']} | {r['Datum']}")

# Delete the one with encoding issue (Ã¸)
cursor.execute("DELETE FROM mutaties WHERE ID = 61901 AND Omschrijving LIKE '%Ã¸%'")
conn.commit()

print(f"\nDeleted record 61901 with encoding issue")
print(f"Kept record 61679 with correct UTF-8: Søstrene Grene")

cursor.close()
conn.close()
