import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv('DB_HOST'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cursor = conn.cursor(dictionary=True)

cursor.execute("""
    SELECT ID, TransactionNumber, Ref2
    FROM mutaties
    WHERE TransactionNumber LIKE 'Revolut%'
    LIMIT 10
""")

records = cursor.fetchall()
print(f"Found {len(records)} Revolut records:")
for r in records:
    parts = r['Ref2'].split('_') if r['Ref2'] else []
    print(f"ID {r['ID']}: {r['TransactionNumber']} | Ref2 parts: {len(parts)} | {r['Ref2'][:80] if r['Ref2'] else 'NULL'}")

cursor.close()
conn.close()
