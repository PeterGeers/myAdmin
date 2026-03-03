"""Show mutaties table columns"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager

db = DatabaseManager(test_mode=False)
result = db.execute_query('DESCRIBE mutaties')

print('Mutaties Table Columns:')
print('=' * 80)
for r in result:
    print(f'{r["Field"]:30} | {r["Type"]:20} | Null:{r["Null"]:5} | Key:{r["Key"]:5}')
