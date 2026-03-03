"""Compare Opening Balance 2025 vs 2026"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from database import DatabaseManager

db = DatabaseManager(test_mode=False)

print('=' * 100)
print('OPENING BALANCE 2025 (Historical)')
print('=' * 100)

query_2025 = """
SELECT 
    Reknum,
    Description,
    Debet,
    Credit,
    TransactionAmount,
    TransactionDate,
    Reference
FROM mutaties
WHERE TransactionNumber LIKE 'OpeningBalance 2025%'
AND administration = 'GoodwinSolutions'
ORDER BY Reknum
"""

results_2025 = db.execute_query(query_2025)
print(f'Total records: {len(results_2025)}')
print()
for i, row in enumerate(results_2025[:15]):
    acc = row['Reknum']
    desc = row['Description'][:30]
    deb = row['Debet']
    cred = row['Credit']
    amt = row['TransactionAmount']
    ref = row['Reference'] or ''
    print(f'{i+1:2}. {acc:10} | {desc:30} | D:{deb:10} | C:{cred:10} | Amt:{amt:10.2f} | {ref}')

print('\n' + '=' * 100)
print('OPENING BALANCE 2026 (Just Created)')
print('=' * 100)

query_2026 = """
SELECT 
    Reknum,
    Description,
    Debet,
    Credit,
    TransactionAmount,
    TransactionDate,
    Reference
FROM mutaties
WHERE TransactionNumber LIKE 'OpeningBalance 2026%'
AND administration = 'GoodwinSolutions'
ORDER BY Reknum
"""

results_2026 = db.execute_query(query_2026)
print(f'Total records: {len(results_2026)}')
print()
for i, row in enumerate(results_2026[:15]):
    acc = row['Reknum']
    desc = row['Description'][:30]
    deb = row['Debet']
    cred = row['Credit']
    amt = row['TransactionAmount']
    ref = row['Reference'] or ''
    print(f'{i+1:2}. {acc:10} | {desc:30} | D:{deb:10} | C:{cred:10} | Amt:{amt:10.2f} | {ref}')

print('\n' + '=' * 100)
print('COMPARISON SUMMARY')
print('=' * 100)
print(f'2025 records: {len(results_2025)}')
print(f'2026 records: {len(results_2026)}')

# Check for balance
total_2025_debet = sum(r['TransactionAmount'] for r in results_2025 if r['Debet'])
total_2025_credit = sum(r['TransactionAmount'] for r in results_2025 if r['Credit'])
total_2026_debet = sum(r['TransactionAmount'] for r in results_2026 if r['Debet'])
total_2026_credit = sum(r['TransactionAmount'] for r in results_2026 if r['Credit'])

print(f'\n2025 Totals: Debet={total_2025_debet:,.2f} | Credit={total_2025_credit:,.2f} | Balance={total_2025_debet - total_2025_credit:,.2f}')
print(f'2026 Totals: Debet={total_2026_debet:,.2f} | Credit={total_2026_credit:,.2f} | Balance={total_2026_debet - total_2026_credit:,.2f}')

# Check interim account
print('\n' + '=' * 100)
print('INTERIM ACCOUNT CHECK (2026)')
print('=' * 100)

query_interim = """
SELECT 
    Reknum,
    Description,
    Debet,
    Credit,
    TransactionAmount,
    Reference
FROM mutaties
WHERE TransactionNumber LIKE 'OpeningBalance 2026%'
AND administration = 'GoodwinSolutions'
AND Reknum = '0999'
"""

interim = db.execute_query(query_interim)
if interim:
    for row in interim:
        print(f'Account: {row["Reknum"]}')
        print(f'Description: {row["Description"]}')
        print(f'Debet: {row["Debet"]}')
        print(f'Credit: {row["Credit"]}')
        print(f'Amount: {row["TransactionAmount"]:,.2f}')
        print(f'Reference: {row["Reference"]}')
else:
    print('No interim account (0999) found in 2026 opening balance')
