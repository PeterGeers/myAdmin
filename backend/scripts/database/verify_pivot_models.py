"""Quick verification that pivot_models table exists in the connected database."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from database import DatabaseManager

db = DatabaseManager()

# Check table exists
tables = db.execute_query("SHOW TABLES LIKE %s", ("pivot_models",))
print(f"Table exists: {len(tables) > 0}")
if tables:
    print(f"  Result: {tables}")

# Describe schema
print("\nSchema:")
for col in db.execute_query("DESCRIBE pivot_models"):
    print(f"  {col['Field']:20s} {col['Type']:20s} Null={col['Null']} Key={col['Key']} Default={col['Default']} Extra={col['Extra']}")

# Show indexes
print("\nIndexes:")
for idx in db.execute_query("SHOW INDEX FROM pivot_models"):
    print(f"  {idx['Key_name']:25s} col={idx['Column_name']} unique={not idx['Non_unique']}")

# Row count
count = db.execute_query("SELECT COUNT(*) as cnt FROM pivot_models")
print(f"\nRow count: {count[0]['cnt']}")
