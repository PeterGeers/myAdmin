"""
Diagnostic script: Find the gap between calculated balance (SUM from vw_mutaties)
and the Ref3 running balance (from bank statement) for account 1002, GoodwinSolutions.

Approach:
- Get all transactions for account 1002 since opening balance date (2026-01-01)
- The opening balance has no Ref3 (it's an internal booking)
- Bank transactions have Ref3 = running balance from the bank statement
- Walk through all transactions, compute running balance two ways:
  A) From the mutaties records (debet 1002 = +, credit 1002 = -)
  B) From Ref3 values (bank's view)
- Find where they diverge
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from database import DatabaseManager
from decimal import Decimal, ROUND_HALF_UP


def parse_ref3(ref3_value):
    """Parse Ref3 which is in Dutch number format: +7751,65 or -123,45"""
    if not ref3_value:
        return None
    try:
        cleaned = ref3_value.replace('+', '').replace('.', '').replace(',', '.')
        return Decimal(cleaned)
    except Exception:
        return None


def run_diagnosis():
    db = DatabaseManager()
    administration = "GoodwinSolutions"
    opening_date = "2026-01-01"

    print(f"=== Balance Gap Diagnosis for {administration}, account 1002 ===")
    print(f"Opening balance date: {opening_date}\n")

    # Get ALL transactions for account 1002 since opening date, ordered by Ref2
    query = """
        SELECT id, TransactionDate, TransactionDescription, TransactionAmount,
               Debet, Credit, Ref2, Ref3
        FROM mutaties
        WHERE administration = %s
        AND (Debet = '1002' OR Credit = '1002')
        AND TransactionDate >= %s
        ORDER BY CAST(COALESCE(NULLIF(Ref2, ''), '0') AS UNSIGNED) ASC, id ASC
    """
    all_txs = db.execute_query(query, [administration, opening_date])

    print(f"Total transactions: {len(all_txs)}\n")

    # Walk through and compute running balance
    running_balance = Decimal('0')
    first_ref3_seen = False
    gap_introduced_at = None

    print("--- First 5 transactions ---")
    for i, tx in enumerate(all_txs[:5]):
        amount = Decimal(str(tx['TransactionAmount']))
        if tx['Debet'] == '1002':
            running_balance += amount
            direction = "DEBET (+)"
        else:
            running_balance -= amount
            direction = "CREDIT (-)"

        ref3 = parse_ref3(tx['Ref3'])
        ref3_display = tx['Ref3'] if tx['Ref3'] else "(none)"

        print(f"  #{i} ID={tx['id']} Ref2={tx['Ref2']}")
        print(f"     Date={tx['TransactionDate']} | Amount={amount} | {direction}")
        print(f"     Running balance: {running_balance} | Ref3: {ref3_display}")
        if ref3 is not None:
            diff = running_balance - ref3
            print(f"     DIFF (calculated - Ref3): {diff}")
        print()

    # Now full scan to find where gap starts
    print("--- Full scan for discrepancies ---")
    running_balance = Decimal('0')
    prev_diff = Decimal('0')

    for i, tx in enumerate(all_txs):
        amount = Decimal(str(tx['TransactionAmount']))
        if tx['Debet'] == '1002':
            running_balance += amount
        else:
            running_balance -= amount

        ref3 = parse_ref3(tx['Ref3'])
        if ref3 is not None:
            diff = running_balance - ref3
            # Report whenever the diff changes
            if diff != prev_diff:
                print(f"  Gap CHANGES at #{i} ID={tx['id']} Ref2={tx['Ref2']}")
                print(f"     Date={tx['TransactionDate']}")
                print(f"     Desc: {tx['TransactionDescription'][:70]}")
                print(f"     Amount={amount} | Debet={tx['Debet']} | Credit={tx['Credit']}")
                print(f"     Running balance: {running_balance}")
                print(f"     Ref3 (bank):     {ref3} (raw: {tx['Ref3']})")
                print(f"     Previous diff:   {prev_diff}")
                print(f"     New diff:        {diff}")
                print()
                prev_diff = diff

    print(f"--- Final state ---")
    print(f"  Final running balance (from mutaties): {running_balance}")
    print(f"  Final diff vs last Ref3:               {prev_diff}")

    # Detailed: show all transactions BEFORE first Ref3 to find where gap comes from
    print(f"\n--- Transactions before first Ref3 (gap must be in here) ---")
    print(f"  Opening balance (ID=63533): 6972.69 DEBET")
    print(f"  First Ref3 appears at Ref2=5008 showing 4529.04")
    print(f"  Our calculated balance at that point: 4529.06")
    print(f"  So 2 cents extra in our records vs bank")
    print()

    # Get bank's starting point: what was bank balance BEFORE Ref2=4956?
    # We can check: opening balance 6972.69 is what we booked.
    # The bank's balance at start of 2026 might differ.
    # Let's check the last Ref3 from 2025 for this account
    last_2025_query = """
        SELECT id, TransactionDate, TransactionAmount, Debet, Credit, Ref2, Ref3
        FROM mutaties
        WHERE administration = %s
        AND (Debet = '1002' OR Credit = '1002')
        AND TransactionDate < '2026-01-01'
        AND Ref3 IS NOT NULL AND Ref3 != ''
        ORDER BY CAST(COALESCE(NULLIF(Ref2, ''), '0') AS UNSIGNED) DESC
        LIMIT 3
    """
    last_2025 = db.execute_query(last_2025_query, [administration])
    print("  Last transactions from 2025 with Ref3:")
    for tx in last_2025:
        ref3_parsed = parse_ref3(tx['Ref3'])
        print(f"    ID={tx['id']} Ref2={tx['Ref2']} Date={tx['TransactionDate']} "
              f"Amount={tx['TransactionAmount']} Ref3={tx['Ref3']} (={ref3_parsed})")

    # Now compare: opening balance of 6972.69 vs what the bank says the balance was
    # The bank balance at end of 2025 should = start of 2026
    # If last 2025 Ref3 = X, then opening balance should = X
    # But we booked 6972.69. If X != 6972.69, that's our gap source.

    # Also check: sum of all 2025 transactions for account 1002
    sum_2025_query = """
        SELECT
            SUM(CASE WHEN Debet = '1002' THEN TransactionAmount ELSE 0 END) as sum_d,
            SUM(CASE WHEN Credit = '1002' THEN TransactionAmount ELSE 0 END) as sum_c
        FROM mutaties
        WHERE administration = %s
        AND (Debet = '1002' OR Credit = '1002')
        AND TransactionDate < '2026-01-01'
    """
    sum_2025 = db.execute_query(sum_2025_query, [administration])
    if sum_2025 and sum_2025[0]['sum_d'] is not None:
        s_d = Decimal(str(sum_2025[0]['sum_d']))
        s_c = Decimal(str(sum_2025[0]['sum_c']))
        print(f"\n  All-time balance before 2026 (from mutaties): {s_d - s_c}")
        print(f"  Opening balance booked for 2026:               6972.69")
        print(f"  Difference:                                    {(s_d - s_c) - Decimal('6972.69')}")

    # Also check: sum of transactions between opening date and first Ref3
    pre_ref3_query = """
        SELECT id, TransactionDate, TransactionDescription, TransactionAmount,
               Debet, Credit, Ref2, Ref3
        FROM mutaties
        WHERE administration = %s
        AND (Debet = '1002' OR Credit = '1002')
        AND TransactionDate >= '2026-01-01'
        AND (Ref3 IS NULL OR Ref3 = '')
        ORDER BY CAST(COALESCE(NULLIF(Ref2, ''), '0') AS UNSIGNED) ASC
    """
    pre_ref3 = db.execute_query(pre_ref3_query, [administration])
    print(f"\n  Transactions in 2026 WITHOUT Ref3: {len(pre_ref3)}")
    running = Decimal('0')
    for tx in pre_ref3:
        amount = Decimal(str(tx['TransactionAmount']))
        if tx['Debet'] == '1002':
            running += amount
        else:
            running -= amount
    print(f"  Sum of those (net): {running}")
    print(f"  Opening balance (6972.69) + net of no-Ref3 txs = {Decimal('6972.69') + running}")
    print(f"  First Ref3 value after these = 4529.04")
    print(f"  Gap = {Decimal('6972.69') + running - Decimal('4529.04')}")

    # Detailed: show all transactions between last 2025 Ref3 and first 2026 Ref3
    # The last 2025 Ref3 = 6972.69 (matching our opening balance)
    # First 2026 Ref3 at Ref2=5008 = 4529.04
    # Expected: 6972.69 + net(transactions 4956..5007) should = 4529.04
    # But we get 4529.06 (2 cents too high)
    # So we need to find which of those transactions has a 2 cent error

    print(f"\n--- All transactions from Ref2=4956 to Ref2=5007 (gap must be here) ---")
    gap_query = """
        SELECT id, TransactionDate, TransactionDescription, TransactionAmount,
               Debet, Credit, Ref2, Ref3, Ref1
        FROM mutaties
        WHERE administration = %s
        AND (Debet = '1002' OR Credit = '1002')
        AND TransactionDate >= '2026-01-01'
        AND CAST(COALESCE(NULLIF(Ref2, ''), '0') AS UNSIGNED) BETWEEN 4956 AND 5007
        ORDER BY CAST(Ref2 AS UNSIGNED) ASC
    """
    gap_txs = db.execute_query(gap_query, [administration])
    print(f"  Transactions with Ref2 between 4956 and 5007: {len(gap_txs)}")

    running_from_ob = Decimal('6972.69')  # opening balance
    for tx in gap_txs:
        amount = Decimal(str(tx['TransactionAmount']))
        if tx['Debet'] == '1002':
            running_from_ob += amount
            direction = "+"
        else:
            running_from_ob -= amount
            direction = "-"
        print(f"  Ref2={tx['Ref2']} | {direction}{amount} | bal={running_from_ob} | "
              f"D={tx['Debet']} C={tx['Credit']} | {tx['TransactionDescription'][:50]}")

    print(f"\n  Balance after Ref2=4956..5007: {running_from_ob}")
    print(f"  Expected (first Ref3):         4529.04")
    print(f"  Difference:                    {running_from_ob - Decimal('4529.04')}")

    # Now also include transactions without Ref2 (internal bookings like opening balance)
    print(f"\n--- Transactions in 2026 before Ref2=5008 WITHOUT a Ref2 (internal) ---")
    internal_query = """
        SELECT id, TransactionDate, TransactionDescription, TransactionAmount,
               Debet, Credit, Ref2
        FROM mutaties
        WHERE administration = %s
        AND (Debet = '1002' OR Credit = '1002')
        AND TransactionDate >= '2026-01-01'
        AND (Ref2 IS NULL OR Ref2 = '' OR CAST(Ref2 AS UNSIGNED) = 0)
        ORDER BY id ASC
    """
    internals = db.execute_query(internal_query, [administration])
    print(f"  Count: {len(internals)}")
    for tx in internals:
        amount = Decimal(str(tx['TransactionAmount']))
        direction = "DEBET" if tx['Debet'] == '1002' else "CREDIT"
        print(f"    ID={tx['id']} | {direction} {amount} | D={tx['Debet']} C={tx['Credit']} | "
              f"{tx['TransactionDescription'][:60]}")

    # KEY INSIGHT: 
    # Opening balance = 6972.69 (matches last 2025 Ref3)
    # After 52 bank transactions (Ref2=4956..5007): our balance = 4541.04
    # Then Ref2=5008 is -11.98, giving us 4529.06
    # But bank says Ref3=4529.04 at Ref2=5008
    # So the bank says balance before 5008 was 4541.02, we say 4541.04
    # Gap: 0.02 cents somewhere in Ref2=4956..5007
    # 
    # Let's get the BANK's expected balance at each step by working backward from first Ref3
    # Bank says: after Ref2=5008, balance = 4529.04
    # Ref2=5008 is amount=11.98, Credit=1002 (money out) 
    # So bank before 5008 = 4529.04 + 11.98 = 4541.02
    # Our calc before 5008 = 6972.69 + net(4956..5007) = 4541.04
    # Difference: 0.02

    print(f"\n--- Backward reconstruction from Ref3 ---")
    print(f"  Bank balance after Ref2=5008 (Ref3): 4529.04")
    print(f"  Ref2=5008 amount: 11.98, Credit 1002 (outgoing)")
    print(f"  Bank balance before Ref2=5008: 4529.04 + 11.98 = {Decimal('4529.04') + Decimal('11.98')}")
    print(f"  Our balance before Ref2=5008:  6972.69 + net(4956..5007)")
    
    # Recompute step by step from opening balance, show where cumulative sum drifts
    # from what the bank would expect
    # Bank expects final-before-5008 = 4541.02
    # We get 4541.04
    # Somewhere we have 0.02 too much (or bank has 0.02 too little)
    
    # Check if any transactions in that range have amounts that could cause rounding
    # when summed. This could happen if amounts were imported with slight errors.
    
    # Let's find: given bank start=6972.69 and bank end=4541.02,
    # the net should be 6972.69 - 4541.02 = 2431.67
    # Our net from those 52 txs = 6972.69 - 4541.04 = 2431.65... wait that's wrong
    # Our net = final - opening = 4541.04 - 6972.69 = -2431.65
    # Bank net = 4541.02 - 6972.69 = -2431.67
    # So we have 0.02 less outflow than the bank expects
    
    # The transactions are in the range 4956..5007. Let's check if any have amounts
    # that differ from what we'd expect. Most likely candidate: a transaction was 
    # imported with wrong amount.
    
    # Let's look for the gap by computing what the bank balance SHOULD be at each point
    # We know: bank start = 6972.69, bank end before 5008 = 4541.02
    # If we walk forward with our amounts, we should end at 4541.02 if correct
    # We end at 4541.04 instead — 0.02 too high
    # That means somewhere a credit is 0.02 too low or a debit is 0.02 too high
    
    print(f"\n--- Looking for the 0.02 cent source ---")
    print(f"  Total debit (in) for Ref2 4956-5007:")
    total_in = Decimal('0')
    total_out = Decimal('0')
    for tx in gap_txs:
        amount = Decimal(str(tx['TransactionAmount']))
        if tx['Debet'] == '1002':
            total_in += amount
        else:
            total_out += amount
    print(f"    Money IN (debet 1002):  {total_in}")
    print(f"    Money OUT (credit 1002): {total_out}")
    print(f"    Net: {total_in - total_out}")
    print(f"    Expected net (bank): {Decimal('4541.02') - Decimal('6972.69')}")
    print(f"    Difference: {(total_in - total_out) - (Decimal('4541.02') - Decimal('6972.69'))}")

    # Check: are there any transactions where the bank CSV original line might
    # have had a different amount? Look for amounts ending in specific patterns
    print(f"\n  Transactions with amounts that have odd sub-cent patterns:")
    for tx in gap_txs:
        # Check if any original amount could have been rounded
        # For bank transactions, Ref1 contains the IBAN. But we can check if
        # the amount * 100 is not a whole number (shouldn't be possible with DECIMAL(10,2))
        amount = Decimal(str(tx['TransactionAmount']))
        cents = amount * 100
        if cents != int(cents):
            print(f"    Ref2={tx['Ref2']} Amount={amount} (fractional cents!)")

    # Also check: what does vw_mutaties SUM say?
    vw_query = """
        SELECT ROUND(SUM(Amount), 2) as vw_balance
        FROM vw_mutaties
        WHERE Administration = %s
        AND Reknum = '1002'
        AND TransactionDate >= %s
    """
    vw_result = db.execute_query(vw_query, [administration, opening_date])
    if vw_result:
        print(f"  vw_mutaties SUM(Amount):               {vw_result[0]['vw_balance']}")

    # Check if there's a rounding difference between mutaties direct calc and vw_mutaties
    print(f"\n--- Verify: direct SUM vs vw_mutaties SUM ---")
    direct_query = """
        SELECT
            SUM(CASE WHEN Debet = '1002' THEN TransactionAmount ELSE 0 END) as sum_debet,
            SUM(CASE WHEN Credit = '1002' THEN TransactionAmount ELSE 0 END) as sum_credit
        FROM mutaties
        WHERE administration = %s
        AND (Debet = '1002' OR Credit = '1002')
        AND TransactionDate >= %s
    """
    direct = db.execute_query(direct_query, [administration, opening_date])
    if direct:
        sum_d = Decimal(str(direct[0]['sum_debet']))
        sum_c = Decimal(str(direct[0]['sum_credit']))
        print(f"  SUM(debet amounts):  {sum_d}")
        print(f"  SUM(credit amounts): {sum_c}")
        print(f"  Net (D - C):         {sum_d - sum_c}")


if __name__ == "__main__":
    run_diagnosis()
