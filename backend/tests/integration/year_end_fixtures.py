"""
Test Data Fixtures for Year-End Integration Tests

Provides reusable SQL setup/teardown scripts and fixture functions
for testing the year-end closure process against a test database.

Usage:
    from tests.integration.year_end_fixtures import (
        ADMIN, FISCAL_YEAR, setup_year_end_test_data, teardown_year_end_test_data
    )

Task 60 of Phase 8: Create test data fixtures for year-end integration tests
"""

# Test constants
ADMIN = 'TestYearEnd'
FISCAL_YEAR = 2025


# ── Chart of Accounts (rekeningschema) ─────────────────────────────────────

CHART_OF_ACCOUNTS = [
    # Balance sheet accounts (VW='N')
    {'Account': '1300', 'AccountName': 'Rabobank', 'Parent': '1000', 'VW': 'N'},
    {'Account': '1400', 'AccountName': 'Debiteuren', 'Parent': '1000', 'VW': 'N'},
    {'Account': '2000', 'AccountName': 'Crediteuren', 'Parent': '2000', 'VW': 'N'},
    {'Account': '3000', 'AccountName': 'Eigen Vermogen', 'Parent': '3000', 'VW': 'N'},
    {'Account': '3080', 'AccountName': 'Resultaat Lopend Jaar', 'Parent': '3000', 'VW': 'N'},
    # P&L accounts (VW='Y')
    {'Account': '4000', 'AccountName': 'Omzet', 'Parent': '4000', 'VW': 'Y'},
    {'Account': '4100', 'AccountName': 'Omzet Airbnb', 'Parent': '4000', 'VW': 'Y'},
    {'Account': '7000', 'AccountName': 'Kosten', 'Parent': '7000', 'VW': 'Y'},
    {'Account': '7100', 'AccountName': 'Kantoorkosten', 'Parent': '7000', 'VW': 'Y'},
    {'Account': '8099', 'AccountName': 'Resultaatbestemming', 'Parent': '8000', 'VW': 'Y'},
]

# Account purpose configuration (stored in parameters JSON column)
ACCOUNT_PURPOSES = {
    '3080': 'equity_result',   # Where net P&L result is recorded
    '8099': 'pl_closing',      # Used in year-end closure transaction
}


# ── Sample Transactions ────────────────────────────────────────────────────

SAMPLE_TRANSACTIONS = [
    # Revenue transactions (P&L - credit side)
    {
        'TransactionDate': f'{FISCAL_YEAR}-03-15',
        'TransactionDescription': 'Airbnb payout March',
        'TransactionAmount': 2500.00,
        'Debet': '1300',
        'Credit': '4100',
        'ReferenceNumber': 'ABN-MAR-001',
        'administration': ADMIN,
    },
    {
        'TransactionDate': f'{FISCAL_YEAR}-06-20',
        'TransactionDescription': 'Airbnb payout June',
        'TransactionAmount': 3200.00,
        'Debet': '1300',
        'Credit': '4100',
        'ReferenceNumber': 'ABN-JUN-001',
        'administration': ADMIN,
    },
    {
        'TransactionDate': f'{FISCAL_YEAR}-09-10',
        'TransactionDescription': 'Airbnb payout September',
        'TransactionAmount': 2800.00,
        'Debet': '1300',
        'Credit': '4100',
        'ReferenceNumber': 'ABN-SEP-001',
        'administration': ADMIN,
    },
    # Expense transactions (P&L - debit side)
    {
        'TransactionDate': f'{FISCAL_YEAR}-04-01',
        'TransactionDescription': 'Office supplies',
        'TransactionAmount': 150.00,
        'Debet': '7100',
        'Credit': '1300',
        'ReferenceNumber': 'EXP-APR-001',
        'administration': ADMIN,
    },
    {
        'TransactionDate': f'{FISCAL_YEAR}-07-15',
        'TransactionDescription': 'Internet subscription',
        'TransactionAmount': 45.00,
        'Debet': '7100',
        'Credit': '1300',
        'ReferenceNumber': 'EXP-JUL-001',
        'administration': ADMIN,
    },
    {
        'TransactionDate': f'{FISCAL_YEAR}-11-30',
        'TransactionDescription': 'Cleaning supplies',
        'TransactionAmount': 85.00,
        'Debet': '7100',
        'Credit': '1300',
        'ReferenceNumber': 'EXP-NOV-001',
        'administration': ADMIN,
    },
    # Balance sheet transaction (should NOT be closed)
    {
        'TransactionDate': f'{FISCAL_YEAR}-01-05',
        'TransactionDescription': 'Customer payment received',
        'TransactionAmount': 500.00,
        'Debet': '1300',
        'Credit': '1400',
        'ReferenceNumber': 'BAL-JAN-001',
        'administration': ADMIN,
    },
]

# Expected net result: Revenue(2500+3200+2800) - Expenses(150+45+85) = 8220.00
EXPECTED_NET_PL_RESULT = 8220.00


# ── Setup / Teardown SQL ───────────────────────────────────────────────────


def setup_year_end_test_data(db):
    """
    Insert test chart of accounts and transactions into test database.

    Args:
        db: DatabaseManager instance (test_mode=True)

    Returns:
        dict with summary of created data
    """
    created = {'accounts': 0, 'transactions': 0, 'purposes': 0}

    # 1. Insert chart of accounts
    for acct in CHART_OF_ACCOUNTS:
        db.execute_query(
            """INSERT INTO rekeningschema (Account, AccountName, Parent, VW, administration)
               VALUES (%s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE AccountName = VALUES(AccountName), VW = VALUES(VW)""",
            [acct['Account'], acct['AccountName'], acct['Parent'], acct['VW'], ADMIN],
            fetch=False, commit=True
        )
        created['accounts'] += 1

    # 2. Set account purposes via parameters JSON
    for account_code, purpose in ACCOUNT_PURPOSES.items():
        import json
        params_json = json.dumps({'purpose': purpose})
        db.execute_query(
            """UPDATE rekeningschema SET parameters = %s
               WHERE Account = %s AND administration = %s""",
            [params_json, account_code, ADMIN],
            fetch=False, commit=True
        )
        created['purposes'] += 1

    # 3. Insert sample transactions
    for tx in SAMPLE_TRANSACTIONS:
        db.execute_query(
            """INSERT INTO mutaties
               (TransactionDate, TransactionDescription, TransactionAmount,
                Debet, Credit, ReferenceNumber, administration)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            [
                tx['TransactionDate'], tx['TransactionDescription'],
                tx['TransactionAmount'], tx['Debet'], tx['Credit'],
                tx['ReferenceNumber'], tx['administration']
            ],
            fetch=False, commit=True
        )
        created['transactions'] += 1

    return created


def teardown_year_end_test_data(db):
    """
    Remove test data created by setup_year_end_test_data.

    Args:
        db: DatabaseManager instance (test_mode=True)
    """
    # Remove transactions
    db.execute_query(
        "DELETE FROM mutaties WHERE administration = %s",
        [ADMIN], fetch=False, commit=True
    )

    # Remove year_closure_status entries
    db.execute_query(
        "DELETE FROM year_closure_status WHERE administration = %s",
        [ADMIN], fetch=False, commit=True
    )

    # Remove chart of accounts
    db.execute_query(
        "DELETE FROM rekeningschema WHERE administration = %s",
        [ADMIN], fetch=False, commit=True
    )


def verify_closure_result(db, year=FISCAL_YEAR):
    """
    Verify year-end closure produced correct results.

    Args:
        db: DatabaseManager instance
        year: Fiscal year to verify

    Returns:
        dict with verification results
    """
    results = {}

    # Check closure status was recorded
    status = db.execute_query(
        "SELECT * FROM year_closure_status WHERE administration = %s AND year = %s",
        [ADMIN, year]
    )
    results['closure_recorded'] = len(status) > 0 if status else False

    # Check closure transaction exists (P&L accounts zeroed)
    closure_txs = db.execute_query(
        """SELECT * FROM mutaties
           WHERE administration = %s
           AND TransactionDescription LIKE %s
           AND YEAR(TransactionDate) = %s""",
        [ADMIN, '%Jaarafsluiting%', year]
    )
    results['closure_transactions'] = len(closure_txs) if closure_txs else 0

    # Check opening balance transactions exist for next year
    opening_txs = db.execute_query(
        """SELECT * FROM mutaties
           WHERE administration = %s
           AND TransactionDescription LIKE %s
           AND YEAR(TransactionDate) = %s""",
        [ADMIN, '%Opening%', year + 1]
    )
    results['opening_transactions'] = len(opening_txs) if opening_txs else 0

    # Verify net P&L amount matches expected
    pl_sum = db.execute_query(
        """SELECT SUM(CASE WHEN Credit IN ('4000','4100') THEN TransactionAmount ELSE 0 END) as revenue,
                  SUM(CASE WHEN Debet IN ('7000','7100') THEN TransactionAmount ELSE 0 END) as expenses
           FROM mutaties
           WHERE administration = %s AND YEAR(TransactionDate) = %s
           AND TransactionDescription NOT LIKE %s""",
        [ADMIN, year, '%Jaarafsluiting%']
    )
    if pl_sum and pl_sum[0]:
        revenue = float(pl_sum[0].get('revenue', 0) or 0)
        expenses = float(pl_sum[0].get('expenses', 0) or 0)
        results['net_pl'] = revenue - expenses
    else:
        results['net_pl'] = 0.0

    return results
