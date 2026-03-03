"""Check NULL closure_transaction_number records"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager

db = DatabaseManager(test_mode=False)

# Summary by tenant
query = """
SELECT 
    administration,
    COUNT(*) as total_years,
    SUM(CASE WHEN closure_transaction_number IS NULL THEN 1 ELSE 0 END) as null_closure,
    SUM(CASE WHEN closure_transaction_number IS NOT NULL THEN 1 ELSE 0 END) as has_closure
FROM year_closure_status
GROUP BY administration
ORDER BY administration
"""

results = db.execute_query(query)

print('Year Closure Status Summary by Tenant:')
print('=' * 80)
for row in results:
    admin = row['administration']
    total = row['total_years']
    has = row['has_closure']
    null = row['null_closure']
    print(f'{admin:20} | Total: {total:2} | With Closure: {has:2} | NULL Closure: {null:2}')

print('\n' + '=' * 80)
print('Records with NULL closure_transaction_number:')
print('=' * 80)

query_null = """
SELECT administration, year, opening_balance_transaction_number
FROM year_closure_status
WHERE closure_transaction_number IS NULL
ORDER BY administration, year
"""

null_records = db.execute_query(query_null)
for row in null_records:
    admin = row['administration']
    year = row['year']
    opening = row['opening_balance_transaction_number']
    print(f'{admin:20} | Year: {year} | Opening: {opening}')

print(f'\nTotal records with NULL closure_transaction_number: {len(null_records)}')
