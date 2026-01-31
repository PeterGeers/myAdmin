#!/usr/bin/env python3
"""Check tenant_template_config table schema"""

import sys
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent.parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

from database import DatabaseManager

db = DatabaseManager()
result = db.execute_query('DESCRIBE tenant_template_config')

print("\nTable: tenant_template_config")
print("="*80)
print(f"{'Field':<25} {'Type':<30} {'Null':<8} {'Key':<8} {'Default':<15}")
print("-"*80)

for row in result:
    field = str(row['Field'])
    type_ = str(row['Type'])
    null = str(row['Null'])
    key = str(row['Key'] or '')
    default = str(row['Default'] or 'NULL')
    print(f"{field:<25} {type_:<30} {null:<8} {key:<8} {default:<15}")

print("="*80)

# Also show a sample record
print("\nSample record:")
print("="*80)
sample = db.execute_query(
    'SELECT * FROM tenant_template_config LIMIT 1'
)
if sample:
    for key, value in sample[0].items():
        print(f"{key:<25} {value}")
