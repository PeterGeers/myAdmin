"""
Aangifte IB (Income Tax) Report Generator

This module generates structured data for Aangifte IB (Inkomstenbelasting) reports.
It transforms raw financial data into a hierarchical structure ready for template rendering.

The report follows a three-level hierarchy:
1. Parent level: Top-level categories (e.g., 1000, 2000, 3000)
2. Aangifte level: Sub-categories within each parent (e.g., "Liquide middelen", "BTW")
3. Account level: Individual accounts with details (e.g., bank accounts, expense accounts)

Usage:
    from report_generators.aangifte_ib_generator import generate_table_rows
    
    rows = generate_table_rows(
        report_data=summary_data,
        cache=cache_instance,
        year=2025,
        administration='GoodwinSolutions',
        user_tenants=['GoodwinSolutions', 'PeterPrive']
    )
"""

import logging
from typing import List, Dict, Any, Optional
from report_generators.common_formatters import (
    format_currency,
    format_amount,
    safe_float,
    get_css_class_for_amount,
    escape_html
)

logger = logging.getLogger(__name__)


def generate_table_rows(
    report_data: List[Dict[str, Any]],
    cache: Any,
    year: int,
    administration: str,
    user_tenants: List[str]
) -> List[Dict[str, Any]]:
    """
    Generate hierarchical table rows for Aangifte IB report.
    
    This function transforms raw report data into a structured list of table rows
    with proper hierarchy (parent → aangifte → accounts), formatting, and CSS classes.
    
    Args:
        report_data: List of dictionaries containing Parent, Aangifte, and Amount
                    Example: [{'Parent': '1000', 'Aangifte': 'Liquide middelen', 'Amount': 88262.80}, ...]
        cache: Cache instance for querying account details (must have query_aangifte_ib_details method)
        year: Report year (e.g., 2025)
        administration: Administration/tenant identifier (e.g., 'GoodwinSolutions')
        user_tenants: List of tenants user has access to (for security filtering)
    
    Returns:
        List of dictionaries representing table rows, each containing:
        {
            'row_type': 'parent' | 'aangifte' | 'account' | 'resultaat' | 'grand_total',
            'parent': Parent code or label,
            'aangifte': Aangifte name or account number,
            'description': Account description,
            'amount': Formatted amount string,
            'amount_raw': Raw numeric amount,
            'css_class': CSS class for styling,
            'indent_level': 0 | 1 | 2 (for indentation)
        }
    
    Example:
        >>> rows = generate_table_rows(
        ...     report_data=[{'Parent': '1000', 'Aangifte': 'Liquide middelen', 'Amount': 88262.80}],
        ...     cache=cache,
        ...     year=2025,
        ...     administration='GoodwinSolutions',
        ...     user_tenants=['GoodwinSolutions']
        ... )
        >>> rows[0]
        {
            'row_type': 'parent',
            'parent': '1000',
            'aangifte': '',
            'description': '',
            'amount': '88,130.07',
            'amount_raw': 88130.07,
            'css_class': 'parent-row',
            'indent_level': 0
        }
    """
    if not report_data:
        logger.warning("No report data provided to generate_table_rows")
        return []
    
    if not user_tenants:
        logger.warning("No user_tenants provided - security filtering may be compromised")
    
    rows = []
    
    # Step 1: Group data by parent
    grouped = _group_by_parent(report_data)
    
    # Step 2: Calculate totals for resultaat and grand total
    # RESULTAAT = Only P&L accounts (Parents 4000+)
    # Balance sheet accounts (1000-3000) are excluded from resultaat
    resultaat = sum(
        safe_float(item.get('Amount', 0)) 
        for item in report_data 
        if item.get('Parent', '').startswith(('4', '5', '6', '7', '8', '9'))
    )
    grand_total = 0.0  # Should be close to zero for balanced accounts
    
    # Step 3: Generate hierarchical rows
    for parent, items in sorted(grouped.items()):
        # Calculate parent total
        parent_total = sum(safe_float(item.get('Amount', 0)) for item in items)
        
        # Skip parent groups with zero total
        if abs(parent_total) < 0.01:
            continue
        
        # Add parent row
        parent_row = _create_parent_row(parent, parent_total)
        rows.append(parent_row)
        
        # Process each aangifte within this parent
        for item in items:
            amount = safe_float(item.get('Amount', 0))
            
            # Skip items with zero amounts
            if abs(amount) < 0.01:
                continue
            
            aangifte = item.get('Aangifte', '')
            
            # Add aangifte row
            aangifte_row = _create_aangifte_row(aangifte, amount)
            rows.append(aangifte_row)
            
            # Get and add account detail rows
            account_rows = _fetch_and_create_account_rows(
                cache=cache,
                year=year,
                administration=administration,
                parent=parent,
                aangifte=aangifte,
                user_tenants=user_tenants
            )
            rows.extend(account_rows)
    
    # Step 4: Add resultaat row
    if abs(resultaat) >= 0.01:
        resultaat_row = _create_resultaat_row(resultaat)
        rows.append(resultaat_row)
    
    # Step 5: Add grand total row
    grand_total_row = _create_grand_total_row(grand_total)
    rows.append(grand_total_row)
    
    logger.info(f"Generated {len(rows)} table rows for {administration} year {year}")
    
    return rows


def _group_by_parent(report_data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group report data by Parent code.
    
    Args:
        report_data: List of report items
    
    Returns:
        Dictionary mapping parent codes to lists of items
    """
    grouped = {}
    for row in report_data:
        parent = row.get('Parent', '')
        if parent not in grouped:
            grouped[parent] = []
        grouped[parent].append(row)
    return grouped


def _create_parent_row(parent: str, amount: float) -> Dict[str, Any]:
    """
    Create a parent-level row.
    
    Args:
        parent: Parent code (e.g., '1000')
        amount: Total amount for this parent
    
    Returns:
        Dictionary representing a parent row
    """
    return {
        'row_type': 'parent',
        'parent': escape_html(str(parent)),
        'aangifte': '',
        'description': '',
        'amount': format_amount(amount),
        'amount_raw': amount,
        'css_class': 'parent-row',
        'indent_level': 0
    }


def _create_aangifte_row(aangifte: str, amount: float) -> Dict[str, Any]:
    """
    Create an aangifte-level row.
    
    Args:
        aangifte: Aangifte name (e.g., 'Liquide middelen')
        amount: Total amount for this aangifte
    
    Returns:
        Dictionary representing an aangifte row
    """
    return {
        'row_type': 'aangifte',
        'parent': '',
        'aangifte': escape_html(str(aangifte)),
        'description': '',
        'amount': format_amount(amount),
        'amount_raw': amount,
        'css_class': 'aangifte-row',
        'indent_level': 1
    }


def _create_account_row(reknum: str, account_name: str, amount: float) -> Dict[str, Any]:
    """
    Create an account-level row.
    
    Args:
        reknum: Account number (e.g., '1002')
        account_name: Account description (e.g., 'NL80RABO0107936917 RCRT')
        amount: Account amount
    
    Returns:
        Dictionary representing an account row
    """
    return {
        'row_type': 'account',
        'parent': '',
        'aangifte': escape_html(str(reknum)),
        'description': escape_html(str(account_name)),
        'amount': format_amount(amount),
        'amount_raw': amount,
        'css_class': 'account-row',
        'indent_level': 2
    }


def _create_resultaat_row(amount: float) -> Dict[str, Any]:
    """
    Create the resultaat (result) row.
    
    Args:
        amount: Resultaat amount
    
    Returns:
        Dictionary representing the resultaat row
    """
    css_class = 'resultaat-positive' if amount >= 0 else 'resultaat-negative'
    
    return {
        'row_type': 'resultaat',
        'parent': 'RESULTAAT',
        'aangifte': '',
        'description': '',
        'amount': format_amount(amount),
        'amount_raw': amount,
        'css_class': css_class,
        'indent_level': 0
    }


def _create_grand_total_row(amount: float) -> Dict[str, Any]:
    """
    Create the grand total row.
    
    Args:
        amount: Grand total amount (should be close to zero)
    
    Returns:
        Dictionary representing the grand total row
    """
    return {
        'row_type': 'grand_total',
        'parent': 'GRAND TOTAL',
        'aangifte': '',
        'description': '',
        'amount': format_amount(amount),
        'amount_raw': amount,
        'css_class': 'grand-total',
        'indent_level': 0
    }


def _fetch_and_create_account_rows(
    cache: Any,
    year: int,
    administration: str,
    parent: str,
    aangifte: str,
    user_tenants: List[str]
) -> List[Dict[str, Any]]:
    """
    Fetch account details from cache and create account rows.
    
    Args:
        cache: Cache instance with query_aangifte_ib_details method
        year: Report year
        administration: Administration identifier
        parent: Parent code
        aangifte: Aangifte name
        user_tenants: List of accessible tenants (for security)
    
    Returns:
        List of account row dictionaries
    """
    account_rows = []
    
    try:
        # SECURITY: Pass user_tenants to filter cached data
        details = cache.query_aangifte_ib_details(
            year=year,
            administration=administration,
            parent=parent,
            aangifte=aangifte,
            user_tenants=user_tenants
        )
        
        # Filter out zero amounts
        non_zero_details = [
            d for d in details
            if abs(safe_float(d.get('Amount', 0))) >= 0.01
        ]
        
        # Create account rows
        for detail in non_zero_details:
            reknum = detail.get('Reknum', '')
            account_name = detail.get('AccountName', '')
            detail_amount = safe_float(detail.get('Amount', 0))
            
            account_row = _create_account_row(reknum, account_name, detail_amount)
            account_rows.append(account_row)
    
    except Exception as e:
        logger.error(f"Error fetching details for {parent}-{aangifte}: {e}")
        # Continue processing - don't fail the entire report for one error
    
    return account_rows
