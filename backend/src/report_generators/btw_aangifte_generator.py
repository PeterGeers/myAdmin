"""
BTW Aangifte (VAT Declaration) Report Generator

This module generates structured data for BTW Aangifte (VAT Declaration) reports.
It transforms raw financial data into formatted output ready for template rendering.

The report includes:
1. Balance data: BTW accounts (2010, 2020, 2021) up to end date
2. Quarter data: BTW and revenue accounts for the specific quarter
3. Calculations: Total balance, received BTW, prepaid BTW, payment instruction

Usage:
    from report_generators.btw_aangifte_generator import generate_btw_report
    
    report_data = generate_btw_report(
        cache=cache_instance,
        db=db_instance,
        administration='GoodwinSolutions',
        year=2025,
        quarter=1
    )
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from report_generators.common_formatters import (
    format_currency,
    format_amount,
    safe_float,
    escape_html
)

logger = logging.getLogger(__name__)


def generate_btw_report(
    cache: Any,
    db: Any,
    administration: str,
    year: int,
    quarter: int
) -> Dict[str, Any]:
    """
    Generate BTW Aangifte report data.
    
    This function retrieves balance and quarter data from cache, performs
    VAT calculations, and formats the data for template rendering.
    
    Args:
        cache: Cache instance for querying financial data
        db: Database instance (for compatibility)
        administration: Administration/tenant identifier (e.g., 'GoodwinSolutions')
        year: Report year (e.g., 2025)
        quarter: Quarter number (1, 2, 3, or 4)
    
    Returns:
        Dictionary containing structured report data:
        {
            'balance_rows': HTML table rows for balance data,
            'quarter_rows': HTML table rows for quarter data,
            'calculations': {
                'total_balance': float,
                'received_btw': float,
                'prepaid_btw': float,
                'payment_instruction': str
            },
            'metadata': {
                'administration': str,
                'year': int,
                'quarter': int,
                'end_date': str,
                'generated_date': str
            }
        }
    
    Example:
        >>> report = generate_btw_report(
        ...     cache=cache,
        ...     db=db,
        ...     administration='GoodwinSolutions',
        ...     year=2025,
        ...     quarter=1
        ... )
        >>> report['calculations']['payment_instruction']
        '€1,234 te betalen'
    """
    try:
        # Step 1: Calculate quarter end date
        end_date = _calculate_quarter_end_date(year, quarter)
        
        # Step 2: Get balance data (BTW accounts up to end date)
        balance_data = _get_balance_data(cache, db, administration, end_date)
        
        # Step 3: Get quarter data (BTW + revenue accounts for quarter)
        quarter_data = _get_quarter_data(cache, db, administration, year, quarter)
        
        # Step 4: Calculate BTW amounts
        calculations = _calculate_btw_amounts(balance_data, quarter_data)
        
        # Step 5: Format data for template
        balance_rows = _format_table_rows(balance_data)
        quarter_rows = _format_table_rows(quarter_data)
        
        # Step 6: Prepare metadata
        metadata = {
            'administration': administration,
            'year': year,
            'quarter': quarter,
            'end_date': end_date,
            'generated_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Step 7: Return structured data
        return {
            'balance_rows': balance_rows,
            'quarter_rows': quarter_rows,
            'calculations': calculations,
            'metadata': metadata,
            'success': True
        }
        
    except Exception as e:
        logger.error(f"Failed to generate BTW report: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def _calculate_quarter_end_date(year: int, quarter: int) -> str:
    """
    Calculate the end date for a given quarter.
    
    Args:
        year: Year (e.g., 2025)
        quarter: Quarter number (1, 2, 3, or 4)
    
    Returns:
        End date string in YYYY-MM-DD format
    
    Examples:
        >>> _calculate_quarter_end_date(2025, 1)
        '2025-03-31'
        >>> _calculate_quarter_end_date(2025, 2)
        '2025-06-30'
    """
    quarter_month = int(quarter) * 3
    
    if quarter_month == 3:
        return f"{year}-03-31"
    elif quarter_month == 6:
        return f"{year}-06-30"
    elif quarter_month == 9:
        return f"{year}-09-30"
    elif quarter_month == 12:
        return f"{year}-12-31"
    else:
        raise ValueError(f"Invalid quarter: {quarter}")


def _get_balance_data(
    cache: Any,
    db: Any,
    administration: str,
    end_date: str
) -> List[Dict[str, Any]]:
    """
    Get balance data for BTW accounts up to end date.
    
    Retrieves data for accounts 2010, 2020, 2021 (BTW accounts) up to the
    specified end date.
    
    Args:
        cache: Cache instance
        db: Database instance
        administration: Administration identifier
        end_date: End date in YYYY-MM-DD format
    
    Returns:
        List of dictionaries with Reknum, AccountName, and amount
    """
    try:
        # Get cache data
        df = cache.get_data(db)
        
        # Filter by date
        df_filtered = df[df['TransactionDate'] <= end_date].copy()
        
        # Filter by administration
        df_filtered = df_filtered[
            df_filtered['administration'].str.startswith(administration)
        ]
        
        # Filter by BTW accounts
        df_filtered = df_filtered[
            df_filtered['Reknum'].isin(['2010', '2020', '2021'])
        ]
        
        # Group by account
        grouped = df_filtered.groupby(
            ['Reknum', 'AccountName'], 
            as_index=False
        ).agg({'Amount': 'sum'})
        
        # Rename Amount to amount
        grouped = grouped.rename(columns={'Amount': 'amount'})
        
        # Convert to list of dicts
        results = grouped.to_dict('records')
        
        logger.info(f"Retrieved {len(results)} balance records for {administration}")
        return results
        
    except Exception as e:
        logger.error(f"Error getting balance data: {e}")
        return []


def _get_quarter_data(
    cache: Any,
    db: Any,
    administration: str,
    year: int,
    quarter: int
) -> List[Dict[str, Any]]:
    """
    Get quarter data for BTW and revenue accounts.
    
    Retrieves data for accounts 2010, 2020, 2021 (BTW) and 8001, 8002, 8003
    (revenue) for the specific quarter.
    
    Args:
        cache: Cache instance
        db: Database instance
        administration: Administration identifier
        year: Year
        quarter: Quarter number
    
    Returns:
        List of dictionaries with Reknum, AccountName, and amount
    """
    try:
        # Get cache data
        df = cache.get_data(db)
        
        # Filter by year and quarter
        df_filtered = df[
            (df['jaar'] == int(year)) & (df['kwartaal'] == int(quarter))
        ].copy()
        
        # Filter by administration
        df_filtered = df_filtered[
            df_filtered['administration'].str.startswith(administration)
        ]
        
        # Filter by BTW and revenue accounts
        df_filtered = df_filtered[
            df_filtered['Reknum'].isin(['2010', '2020', '2021', '8001', '8002', '8003'])
        ]
        
        # Group by account
        grouped = df_filtered.groupby(
            ['Reknum', 'AccountName'], 
            as_index=False
        ).agg({'Amount': 'sum'})
        
        # Rename Amount to amount
        grouped = grouped.rename(columns={'Amount': 'amount'})
        
        # Convert to list of dicts
        results = grouped.to_dict('records')
        
        logger.info(f"Retrieved {len(results)} quarter records for {administration}")
        return results
        
    except Exception as e:
        logger.error(f"Error getting quarter data: {e}")
        return []


def _calculate_btw_amounts(
    balance_data: List[Dict[str, Any]],
    quarter_data: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculate BTW amounts based on balance and quarter data.
    
    Calculations:
    - Total balance: Sum of all balance data (te betalen/ontvangen)
    - Received BTW: Sum of accounts 2020, 2021 from quarter data
    - Prepaid BTW: Received BTW - Total balance
    - Payment instruction: Formatted instruction based on total balance
    
    Args:
        balance_data: List of balance records
        quarter_data: List of quarter records
    
    Returns:
        Dictionary with calculated amounts and payment instruction
    """
    try:
        # Calculate total balance (te betalen/ontvangen)
        total_balance = sum(safe_float(row.get('amount', 0)) for row in balance_data)
        
        # Calculate received BTW (accounts 2020, 2021)
        received_btw = sum(
            safe_float(row.get('amount', 0)) 
            for row in quarter_data 
            if row.get('Reknum') in ['2020', '2021']
        )
        
        # Calculate prepaid BTW
        prepaid_btw = received_btw - total_balance
        
        # Determine payment instruction
        if total_balance >= 0:
            payment_instruction = f"€{abs(total_balance):.0f} te ontvangen"
        else:
            payment_instruction = f"€{abs(total_balance):.0f} te betalen"
        
        return {
            'total_balance': total_balance,
            'received_btw': received_btw,
            'prepaid_btw': prepaid_btw,
            'payment_instruction': payment_instruction
        }
        
    except Exception as e:
        logger.error(f"Error calculating BTW amounts: {e}")
        return {
            'total_balance': 0,
            'received_btw': 0,
            'prepaid_btw': 0,
            'payment_instruction': '€0 te betalen'
        }


def _format_table_rows(data: List[Dict[str, Any]]) -> str:
    """
    Format data into HTML table rows.
    
    Args:
        data: List of dictionaries with Reknum, AccountName, and amount
    
    Returns:
        HTML string with table rows
    """
    if not data:
        return '<tr><td colspan="3">Geen gegevens beschikbaar</td></tr>'
    
    rows_html = []
    
    for row in data:
        reknum = escape_html(str(row.get('Reknum', '')))
        account_name = escape_html(str(row.get('AccountName', '')))
        amount = safe_float(row.get('amount', 0))
        formatted_amount = format_currency(amount, currency='EUR')
        
        row_html = f"""            <tr>
                <td>{reknum}</td>
                <td>{account_name}</td>
                <td class="amount">{formatted_amount}</td>
            </tr>"""
        
        rows_html.append(row_html)
    
    return '\n'.join(rows_html)


def prepare_template_data(report_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Prepare report data for template rendering.
    
    Converts the structured report data into a flat dictionary with
    string values suitable for template placeholder replacement.
    
    Args:
        report_data: Structured report data from generate_btw_report()
    
    Returns:
        Dictionary with template placeholders as keys and formatted values
    
    Example:
        >>> template_data = prepare_template_data(report_data)
        >>> template_data['year']
        '2025'
        >>> template_data['payment_instruction']
        '€1,234 te betalen'
    """
    metadata = report_data.get('metadata', {})
    calculations = report_data.get('calculations', {})
    
    return {
        'administration': str(metadata.get('administration', '')),
        'year': str(metadata.get('year', '')),
        'quarter': str(metadata.get('quarter', '')),
        'end_date': str(metadata.get('end_date', '')),
        'generated_date': str(metadata.get('generated_date', '')),
        'balance_rows': report_data.get('balance_rows', ''),
        'quarter_rows': report_data.get('quarter_rows', ''),
        'payment_instruction': str(calculations.get('payment_instruction', '€0 te betalen')),
        'received_btw': format_currency(
            calculations.get('received_btw', 0), 
            currency='EUR'
        ),
        'prepaid_btw': format_currency(
            calculations.get('prepaid_btw', 0), 
            currency='EUR'
        )
    }
