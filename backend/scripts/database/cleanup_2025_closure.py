"""
Cleanup incorrect 2025 year closure

This script removes the incorrect year closure for 2025 so it can be re-done
with the fixed logic.

Steps:
1. Delete OpeningBalance 2026 transactions
2. Delete YearClose 2025 transaction (if exists)
3. Delete year_closure_status record for 2025
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager

db = DatabaseManager(test_mode=False)

print('=' * 80)
print('CLEANUP 2025 YEAR CLOSURE')
print('=' * 80)

administration = 'GoodwinSolutions'

# Step 1: Delete OpeningBalance 2026
print('\n1. Deleting OpeningBalance 2026 transactions...')
delete_opening = """
DELETE FROM mutaties
WHERE administration = %s
AND TransactionNumber LIKE 'OpeningBalance 2026%'
"""

result = db.execute_query(delete_opening, [administration], fetch=False, commit=True)
print(f'   ✅ Deleted OpeningBalance 2026 transactions')

# Step 2: Delete YearClose 2025 (if exists)
print('\n2. Deleting YearClose 2025 transaction...')
delete_closure = """
DELETE FROM mutaties
WHERE administration = %s
AND TransactionNumber LIKE 'YearClose 2025%'
"""

result = db.execute_query(delete_closure, [administration], fetch=False, commit=True)
print(f'   ✅ Deleted YearClose 2025 transaction')

# Step 3: Delete year_closure_status record
print('\n3. Deleting year_closure_status record for 2025...')
delete_status = """
DELETE FROM year_closure_status
WHERE administration = %s
AND year = 2025
"""

result = db.execute_query(delete_status, [administration], fetch=False, commit=True)
print(f'   ✅ Deleted year_closure_status record')

# Verify cleanup
print('\n' + '=' * 80)
print('VERIFICATION')
print('=' * 80)

# Check mutaties
check_mutaties = """
SELECT COUNT(*) as count
FROM mutaties
WHERE administration = %s
AND (TransactionNumber LIKE 'OpeningBalance 2026%' OR TransactionNumber LIKE 'YearClose 2025%')
"""

result = db.execute_query(check_mutaties, [administration])
count = result[0]['count']
print(f'\nMutaties records remaining: {count} (should be 0)')

# Check year_closure_status
check_status = """
SELECT COUNT(*) as count
FROM year_closure_status
WHERE administration = %s
AND year = 2025
"""

result = db.execute_query(check_status, [administration])
count = result[0]['count']
print(f'Year closure status records: {count} (should be 0)')

print('\n' + '=' * 80)
print('CLEANUP COMPLETE')
print('=' * 80)
print('\nNext steps:')
print('1. Restart backend: docker-compose restart backend')
print('2. Go to FIN Reports → Year-End Closure')
print('3. Close year 2025 again')
print('=' * 80)
