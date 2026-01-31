"""
Financial Report Generator

This module generates financial reports (XLSX) for the myAdmin application.
It handles data retrieval, formatting, and preparation for Excel export.

The generator follows the pattern:
1. Retrieve ledger data from database
2. Calculate beginning balances
3. Format data for Excel export
4. Return structured data ready for template rendering
"""

import logging
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def make_ledgers(db, year: int, administration: str) -> List[Dict[str, Any]]:
    """
    Calculate starting balance and add all transactions for specific year and administration.
    
    Args:
        db: DatabaseManager instance
        year: Year for the report
        administration: Administration/tenant identifier
        
    Returns:
        List of transaction records including beginning balance
    """
    conn = db.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get balance accounts (VW = N) for years before target year
        balance_query = """
            SELECT Reknum, AccountName, Parent, Administration,
                   SUM(Amount) as Amount
            FROM vw_mutaties 
            WHERE VW = 'N' AND Administration LIKE %s AND jaar < %s
            GROUP BY Reknum, AccountName, Parent, Administration
            HAVING ABS(SUM(Amount)) > 0.01
        """
        cursor.execute(balance_query, [f"{administration}%", year])
        balance_data = cursor.fetchall()
        
        # Create beginning balance records
        beginning_balance = []
        for row in balance_data:
            balance_record = {
                'TransactionNumber': f'Beginbalans {year}',
                'TransactionDate': f'{year}-01-01',
                'TransactionDescription': f'Beginbalans van het jaar {year} van Administratie {administration}',
                'Amount': round(row['Amount'], 2),
                'Reknum': row['Reknum'],
                'AccountName': row['AccountName'],
                'Parent': row['Parent'],
                'Administration': row['Administration'],
                'VW': 'N',
                'jaar': year,
                'kwartaal': 1,
                'maand': 1,
                'week': 1,
                'ReferenceNumber': '',
                'DocUrl': '',
                'Document': ''
            }
            beginning_balance.append(balance_record)
        
        # Get all transactions for the specific year
        transactions_query = """
            SELECT TransactionNumber, TransactionDate, TransactionDescription, Amount, 
                   Reknum, AccountName, Parent, Administration, VW, jaar, kwartaal, 
                   maand, week, ReferenceNumber, Ref3 as DocUrl, Ref4 as Document
            FROM vw_mutaties 
            WHERE Administration LIKE %s AND jaar = %s
            ORDER BY TransactionDate, Reknum
        """
        cursor.execute(transactions_query, [f"{administration}%", year])
        transactions_data = cursor.fetchall()
        
        # Combine beginning balance and transactions
        all_data = beginning_balance + transactions_data
        
        logger.info(
            f"Generated ledger data for {administration} {year}: "
            f"{len(beginning_balance)} balance records, "
            f"{len(transactions_data)} transactions"
        )
        
        return all_data
        
    finally:
        cursor.close()
        conn.close()


def prepare_financial_report_data(
    db,
    administration: str,
    year: int
) -> Dict[str, Any]:
    """
    Prepare financial report data for Excel export.
    
    Args:
        db: DatabaseManager instance
        administration: Administration/tenant identifier
        year: Year for the report
        
    Returns:
        Dictionary containing:
        - ledger_data: List of transaction records
        - metadata: Report metadata (administration, year, generated_date)
    """
    try:
        # Get ledger data
        ledger_data = make_ledgers(db, year, administration)
        
        # Prepare metadata
        metadata = {
            'administration': administration,
            'year': year,
            'generated_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'record_count': len(ledger_data)
        }
        
        logger.info(
            f"Prepared financial report data for {administration} {year}: "
            f"{len(ledger_data)} records"
        )
        
        return {
            'ledger_data': ledger_data,
            'metadata': metadata
        }
        
    except Exception as e:
        logger.error(f"Failed to prepare financial report data: {e}")
        raise Exception(f"Failed to prepare financial report data: {str(e)}")
