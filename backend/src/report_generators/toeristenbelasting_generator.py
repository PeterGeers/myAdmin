"""
Toeristenbelasting (Tourist Tax) Report Generator

This module generates structured data for Toeristenbelasting (Tourist Tax) declaration reports.
It transforms raw financial and booking data into formatted output ready for template rendering.

The report includes:
1. Contact information and period details
2. Accommodation details (rooms, beds)
3. Rental statistics (nights, occupancy rates)
4. Financial calculations (tourist tax, revenue, deductions)
5. Taxable revenue calculation

Usage:
    from report_generators.toeristenbelasting_generator import generate_toeristenbelasting_report
    
    report_data = generate_toeristenbelasting_report(
        cache=cache_instance,
        bnb_cache=bnb_cache_instance,
        db=db_instance,
        year=2025
    )
"""

import logging
from typing import Dict, Any, List
from datetime import datetime
from report_generators.common_formatters import (
    format_currency,
    format_amount,
    safe_float,
    escape_html
)

logger = logging.getLogger(__name__)


def generate_toeristenbelasting_report(
    cache: Any,
    bnb_cache: Any,
    db: Any,
    year: int
) -> Dict[str, Any]:
    """
    Generate Toeristenbelasting (Tourist Tax) declaration report data.
    
    This function retrieves booking and financial data, performs tourist tax
    calculations, and formats the data for template rendering.
    
    Args:
        cache: Cache instance for querying financial data (mutaties_cache)
        bnb_cache: BNB cache instance for querying booking data
        db: Database instance
        year: Report year (e.g., 2025)
    
    Returns:
        Dictionary containing structured report data:
        {
            'success': bool,
            'template_data': {
                'year': str,
                'next_year': str,
                'functie': str,
                'telefoonnummer': str,
                'email': str,
                'periode_van': str,
                'periode_tm': str,
                'aantal_kamers': str,
                'aantal_slaapplaatsen': str,
                'totaal_verhuurde_nachten': str,
                'cancelled_nachten': str,
                'verhuurde_kamers_inwoners': str,
                'totaal_belastbare_nachten': str,
                'kamerbezettingsgraad': str,
                'bedbezettingsgraad': str,
                'saldo_toeristenbelasting': str,
                'ontvangsten_excl_btw_excl_toeristenbelasting': str,
                'ontvangsten_logies_inwoners': str,
                'kortingen_provisie_commissie': str,
                'no_show_omzet': str,
                'totaal_2_3_4': str,
                'belastbare_omzet_logies': str,
                'verwachte_belastbare_omzet_volgend_jaar': str,
                'naam': str,
                'plaats': str,
                'datum': str
            },
            'raw_data': {
                # Raw numeric values for calculations
            }
        }
    
    Example:
        >>> report = generate_toeristenbelasting_report(
        ...     cache=cache,
        ...     bnb_cache=bnb_cache,
        ...     db=db,
        ...     year=2025
        ... )
        >>> report['template_data']['saldo_toeristenbelasting']
        '€1,234.56'
    """
    try:
        # Step 1: Get fixed configuration values
        config = _get_configuration()
        
        # Step 2: Calculate period
        periode_van = f"1-1-{year}"
        periode_tm = f"31-12-{year}"
        
        # Step 3: Get BNB booking data
        bnb_data = _get_bnb_data(bnb_cache, db, year)
        
        # Step 4: Calculate rental statistics
        rental_stats = _calculate_rental_statistics(
            bnb_data=bnb_data,
            aantal_kamers=config['aantal_kamers']
        )
        
        # Step 5: Get financial data
        financial_data = _get_financial_data(cache, db, year, bnb_data)
        
        # Step 6: Calculate taxable revenue
        taxable_revenue = _calculate_taxable_revenue(financial_data)
        
        # Step 7: Prepare template data
        template_data = _prepare_template_data(
            year=year,
            config=config,
            periode_van=periode_van,
            periode_tm=periode_tm,
            rental_stats=rental_stats,
            financial_data=financial_data,
            taxable_revenue=taxable_revenue
        )
        
        # Step 8: Prepare raw data for reference
        raw_data = {
            'year': year,
            **config,
            **rental_stats,
            **financial_data,
            **taxable_revenue
        }
        
        logger.info(f"Generated Toeristenbelasting report for year {year}")
        
        return {
            'success': True,
            'template_data': template_data,
            'raw_data': raw_data
        }
        
    except Exception as e:
        logger.error(f"Failed to generate Toeristenbelasting report: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def _get_configuration() -> Dict[str, Any]:
    """
    Get fixed configuration values for the report.
    
    Returns:
        Dictionary with configuration values
    """
    return {
        'functie': 'DGA',
        'telefoonnummer': '06921893861',
        'email': 'peter@pgeers.nl',
        'aantal_kamers': 3,
        'aantal_slaapplaatsen': 8,
        'naam': 'Peter Geers',
        'plaats': 'Hoofddorp'
    }


def _get_bnb_data(bnb_cache: Any, db: Any, year: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get BNB booking data for the year.
    
    Args:
        bnb_cache: BNB cache instance
        db: Database instance
        year: Report year
    
    Returns:
        Dictionary with booking lists:
        {
            'all_bookings': List of all bookings,
            'cancelled_bookings': List of cancelled bookings,
            'realised_bookings': List of realised bookings
        }
    """
    try:
        # Get all bookings for the year
        all_bookings = bnb_cache.query_by_year(db, year)
        
        # Get cancelled bookings
        cancelled_bookings = bnb_cache.query_cancelled_by_year(db, year)
        
        # Get realised bookings
        realised_bookings = bnb_cache.query_realised_by_year(db, year)
        
        logger.info(
            f"BNB data for {year}: {len(all_bookings)} total, "
            f"{len(cancelled_bookings)} cancelled, {len(realised_bookings)} realised"
        )
        
        return {
            'all_bookings': all_bookings,
            'cancelled_bookings': cancelled_bookings,
            'realised_bookings': realised_bookings
        }
        
    except Exception as e:
        logger.error(f"Error getting BNB data: {e}")
        return {
            'all_bookings': [],
            'cancelled_bookings': [],
            'realised_bookings': []
        }


def _calculate_rental_statistics(
    bnb_data: Dict[str, List[Dict[str, Any]]],
    aantal_kamers: int
) -> Dict[str, float]:
    """
    Calculate rental statistics from booking data.
    
    Args:
        bnb_data: Dictionary with booking lists
        aantal_kamers: Number of rooms
    
    Returns:
        Dictionary with rental statistics:
        {
            'totaal_verhuurde_nachten': Total rented nights,
            'cancelled_nachten': Cancelled nights,
            'verhuurde_kamers_inwoners': Nights rented to residents (always 0),
            'totaal_belastbare_nachten': Total taxable nights,
            'kamerbezettingsgraad': Room occupancy rate (%),
            'bedbezettingsgraad': Bed occupancy rate (%)
        }
    """
    # Calculate totals based on nights (not bookings)
    totaal_verhuurde_nachten = sum(
        b.get('nights', 0) for b in bnb_data['all_bookings']
    )
    
    cancelled_nachten = sum(
        b.get('nights', 0) for b in bnb_data['cancelled_bookings']
    )
    
    # Always 0 per requirements
    verhuurde_kamers_inwoners = 0
    
    # Total taxable nights
    totaal_belastbare_nachten = totaal_verhuurde_nachten - cancelled_nachten
    
    # Calculate occupancy rates based on nights
    total_realised_nights = sum(
        b.get('nights', 0) for b in bnb_data['realised_bookings']
    )
    
    max_nights = aantal_kamers * 365
    
    if max_nights > 0:
        kamerbezettingsgraad = (total_realised_nights / max_nights) * 100
    else:
        kamerbezettingsgraad = 0
    
    # Bed occupancy is 90% of room occupancy
    bedbezettingsgraad = kamerbezettingsgraad * 0.90
    
    return {
        'totaal_verhuurde_nachten': totaal_verhuurde_nachten,
        'cancelled_nachten': cancelled_nachten,
        'verhuurde_kamers_inwoners': verhuurde_kamers_inwoners,
        'totaal_belastbare_nachten': totaal_belastbare_nachten,
        'kamerbezettingsgraad': kamerbezettingsgraad,
        'bedbezettingsgraad': bedbezettingsgraad
    }


def _get_financial_data(
    cache: Any,
    db: Any,
    year: int,
    bnb_data: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, float]:
    """
    Get financial data for the report.
    
    Args:
        cache: Cache instance for financial data
        db: Database instance
        year: Report year
        bnb_data: BNB booking data
    
    Returns:
        Dictionary with financial data:
        {
            'saldo_toeristenbelasting': Tourist tax amount,
            'total_revenue_8003': Total revenue from account 8003,
            'ontvangsten_excl_btw_excl_toeristenbelasting': Revenue excl. VAT and tourist tax,
            'ontvangsten_logies_inwoners': Revenue from residents (always 0),
            'kortingen_provisie_commissie': Service fees,
            'no_show_omzet': No-show revenue
        }
    """
    # Get tourist tax from account 8003: (sum / 106.2) * 6.2
    saldo_toeristenbelasting = abs(_get_tourist_tax_from_account(cache, db, year))
    
    # Get total revenue from account 8003
    total_revenue_8003 = abs(_get_total_revenue_8003(cache, db, year))
    
    # Calculate revenue excluding VAT and tourist tax
    ontvangsten_excl_btw_excl_toeristenbelasting = (
        total_revenue_8003 - saldo_toeristenbelasting
    )
    
    # Always 0 per requirements
    ontvangsten_logies_inwoners = 0
    
    # Get service fees from account 4007 (make positive)
    kortingen_provisie_commissie = abs(_get_service_fees(cache, db, year))
    
    # Calculate no-show revenue: amountGross - amountVat for cancelled bookings
    no_show_omzet = sum(
        b.get('amountGross', 0) - b.get('amountVat', 0)
        for b in bnb_data['cancelled_bookings']
    )
    
    return {
        'saldo_toeristenbelasting': saldo_toeristenbelasting,
        'total_revenue_8003': total_revenue_8003,
        'ontvangsten_excl_btw_excl_toeristenbelasting': ontvangsten_excl_btw_excl_toeristenbelasting,
        'ontvangsten_logies_inwoners': ontvangsten_logies_inwoners,
        'kortingen_provisie_commissie': kortingen_provisie_commissie,
        'no_show_omzet': no_show_omzet
    }


def _get_tourist_tax_from_account(cache: Any, db: Any, year: int) -> float:
    """
    Calculate tourist tax from account 8003: (sum / 106.2) * 6.2
    
    Args:
        cache: Cache instance
        db: Database instance
        year: Report year
    
    Returns:
        Tourist tax amount
    """
    try:
        df = cache.get_data(db)
        
        # Filter by year and account 8003
        df_filtered = df[
            (df['jaar'] == int(year)) & (df['Reknum'] == '8003')
        ].copy()
        
        total_8003 = df_filtered['Amount'].sum()
        
        # Calculate tourist tax: (sum / 106.2) * 6.2
        tourist_tax = (total_8003 / 106.2) * 6.2
        
        return tourist_tax
        
    except Exception as e:
        logger.error(f"Error calculating tourist tax: {e}")
        return 0


def _get_total_revenue_8003(cache: Any, db: Any, year: int) -> float:
    """
    Get total revenue from account 8003.
    
    Args:
        cache: Cache instance
        db: Database instance
        year: Report year
    
    Returns:
        Total revenue amount
    """
    try:
        df = cache.get_data(db)
        
        # Filter by year and account 8003
        df_filtered = df[
            (df['jaar'] == int(year)) & (df['Reknum'] == '8003')
        ].copy()
        
        return df_filtered['Amount'].sum()
        
    except Exception as e:
        logger.error(f"Error getting total revenue 8003: {e}")
        return 0


def _get_service_fees(cache: Any, db: Any, year: int) -> float:
    """
    Get service fees from account 4007 (Service Fee bookingssites).
    
    Args:
        cache: Cache instance
        db: Database instance
        year: Report year
    
    Returns:
        Service fees amount
    """
    try:
        df = cache.get_data(db)
        
        # Filter by year and account 4007
        df_filtered = df[
            (df['jaar'] == int(year)) & (df['Reknum'] == '4007')
        ].copy()
        
        return df_filtered['Amount'].sum()
        
    except Exception as e:
        logger.error(f"Error getting service fees 4007: {e}")
        return 0


def _calculate_taxable_revenue(financial_data: Dict[str, float]) -> Dict[str, float]:
    """
    Calculate taxable revenue components.
    
    Args:
        financial_data: Dictionary with financial data
    
    Returns:
        Dictionary with taxable revenue calculations:
        {
            'totaal_2_3_4': Sum of items 2, 3, 4,
            'belastbare_omzet_logies': Taxable accommodation revenue,
            'verwachte_belastbare_omzet_volgend_jaar': Expected next year revenue
        }
    """
    # Calculate total of items 2, 3, 4
    totaal_2_3_4 = (
        financial_data['ontvangsten_logies_inwoners'] +
        financial_data['kortingen_provisie_commissie'] +
        financial_data['no_show_omzet']
    )
    
    # Calculate taxable accommodation revenue: [1] - [5]
    belastbare_omzet_logies = (
        financial_data['ontvangsten_excl_btw_excl_toeristenbelasting'] -
        totaal_2_3_4
    )
    
    # Calculate expected next year revenue: [6] * 1.05
    verwachte_belastbare_omzet_volgend_jaar = belastbare_omzet_logies * 1.05
    
    return {
        'totaal_2_3_4': totaal_2_3_4,
        'belastbare_omzet_logies': belastbare_omzet_logies,
        'verwachte_belastbare_omzet_volgend_jaar': verwachte_belastbare_omzet_volgend_jaar
    }


def _prepare_template_data(
    year: int,
    config: Dict[str, Any],
    periode_van: str,
    periode_tm: str,
    rental_stats: Dict[str, float],
    financial_data: Dict[str, float],
    taxable_revenue: Dict[str, float]
) -> Dict[str, str]:
    """
    Prepare data for template rendering.
    
    Converts all numeric values to formatted strings suitable for
    template placeholder replacement.
    
    Args:
        year: Report year
        config: Configuration dictionary
        periode_van: Period start date
        periode_tm: Period end date
        rental_stats: Rental statistics dictionary
        financial_data: Financial data dictionary
        taxable_revenue: Taxable revenue dictionary
    
    Returns:
        Dictionary with template placeholders as keys and formatted values
    """
    next_year = int(year) + 1
    datum = datetime.now().strftime('%d-%m-%Y')
    
    return {
        'year': str(year),
        'next_year': str(next_year),
        'functie': escape_html(config['functie']),
        'telefoonnummer': escape_html(config['telefoonnummer']),
        'email': escape_html(config['email']),
        'periode_van': escape_html(periode_van),
        'periode_tm': escape_html(periode_tm),
        'aantal_kamers': str(config['aantal_kamers']),
        'aantal_slaapplaatsen': str(config['aantal_slaapplaatsen']),
        'totaal_verhuurde_nachten': str(int(rental_stats['totaal_verhuurde_nachten'])),
        'cancelled_nachten': str(int(rental_stats['cancelled_nachten'])),
        'verhuurde_kamers_inwoners': str(int(rental_stats['verhuurde_kamers_inwoners'])),
        'totaal_belastbare_nachten': str(int(rental_stats['totaal_belastbare_nachten'])),
        'kamerbezettingsgraad': f"{rental_stats['kamerbezettingsgraad']:.2f}",
        'bedbezettingsgraad': f"{rental_stats['bedbezettingsgraad']:.2f}",
        'saldo_toeristenbelasting': format_currency(
            financial_data['saldo_toeristenbelasting'],
            currency='EUR'
        ),
        'ontvangsten_excl_btw_excl_toeristenbelasting': format_amount(
            financial_data['ontvangsten_excl_btw_excl_toeristenbelasting']
        ),
        'ontvangsten_logies_inwoners': format_amount(
            financial_data['ontvangsten_logies_inwoners']
        ),
        'kortingen_provisie_commissie': format_amount(
            financial_data['kortingen_provisie_commissie']
        ),
        'no_show_omzet': format_amount(
            financial_data['no_show_omzet']
        ),
        'totaal_2_3_4': format_amount(
            taxable_revenue['totaal_2_3_4']
        ),
        'belastbare_omzet_logies': format_amount(
            taxable_revenue['belastbare_omzet_logies']
        ),
        'verwachte_belastbare_omzet_volgend_jaar': format_amount(
            taxable_revenue['verwachte_belastbare_omzet_volgend_jaar']
        ),
        'naam': escape_html(config['naam']),
        'plaats': escape_html(config['plaats']),
        'datum': datum
    }
