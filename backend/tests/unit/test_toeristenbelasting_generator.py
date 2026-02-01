"""
Unit tests for Toeristenbelasting (Tourist Tax) Report Generator

Tests the toeristenbelasting_generator module which generates structured data
for tourist tax declaration reports.
"""

import pytest
from unittest.mock import Mock, MagicMock
import pandas as pd
from report_generators import toeristenbelasting_generator


class TestToeristenbelastingGenerator:
    """Test suite for toeristenbelasting_generator module"""
    
    def test_get_configuration(self):
        """Test configuration retrieval"""
        config = toeristenbelasting_generator._get_configuration()
        
        assert config['functie'] == 'DGA'
        assert config['telefoonnummer'] == '06921893861'
        assert config['email'] == 'peter@pgeers.nl'
        assert config['aantal_kamers'] == 3
        assert config['aantal_slaapplaatsen'] == 8
        assert config['naam'] == 'Peter Geers'
        assert config['plaats'] == 'Hoofddorp'
    
    def test_calculate_rental_statistics_basic(self):
        """Test rental statistics calculation with basic data"""
        bnb_data = {
            'all_bookings': [
                {'nights': 5},
                {'nights': 3},
                {'nights': 7}
            ],
            'cancelled_bookings': [
                {'nights': 2}
            ],
            'realised_bookings': [
                {'nights': 5},
                {'nights': 3},
                {'nights': 7}
            ]
        }
        
        stats = toeristenbelasting_generator._calculate_rental_statistics(
            bnb_data=bnb_data,
            aantal_kamers=3
        )
        
        assert stats['totaal_verhuurde_nachten'] == 15  # 5 + 3 + 7
        assert stats['cancelled_nachten'] == 2
        assert stats['verhuurde_kamers_inwoners'] == 0  # Always 0
        assert stats['totaal_belastbare_nachten'] == 13  # 15 - 2
        
        # Occupancy: 15 realised nights / (3 rooms * 365 days) * 100
        expected_room_occupancy = (15 / (3 * 365)) * 100
        assert abs(stats['kamerbezettingsgraad'] - expected_room_occupancy) < 0.01
        
        # Bed occupancy is 90% of room occupancy
        expected_bed_occupancy = expected_room_occupancy * 0.90
        assert abs(stats['bedbezettingsgraad'] - expected_bed_occupancy) < 0.01
    
    def test_calculate_rental_statistics_no_bookings(self):
        """Test rental statistics with no bookings"""
        bnb_data = {
            'all_bookings': [],
            'cancelled_bookings': [],
            'realised_bookings': []
        }
        
        stats = toeristenbelasting_generator._calculate_rental_statistics(
            bnb_data=bnb_data,
            aantal_kamers=3
        )
        
        assert stats['totaal_verhuurde_nachten'] == 0
        assert stats['cancelled_nachten'] == 0
        assert stats['totaal_belastbare_nachten'] == 0
        assert stats['kamerbezettingsgraad'] == 0
        assert stats['bedbezettingsgraad'] == 0
    
    def test_get_tourist_tax_from_account(self):
        """Test tourist tax calculation from account 8003"""
        # Mock cache
        cache = Mock()
        db = Mock()
        
        # Create mock dataframe
        df = pd.DataFrame({
            'jaar': [2025, 2025, 2025],
            'Reknum': ['8003', '8003', '4007'],
            'Amount': [-10620.0, -5310.0, 100.0]  # Negative for revenue
        })
        cache.get_data.return_value = df
        
        result = toeristenbelasting_generator._get_tourist_tax_from_account(
            cache=cache,
            db=db,
            year=2025
        )
        
        # Total 8003 = -10620 + -5310 = -15930
        # Tourist tax = (-15930 / 106.2) * 6.2 = -930
        expected = (-15930 / 106.2) * 6.2
        assert abs(result - expected) < 0.01
    
    def test_get_total_revenue_8003(self):
        """Test total revenue retrieval from account 8003"""
        cache = Mock()
        db = Mock()
        
        df = pd.DataFrame({
            'jaar': [2025, 2025, 2025],
            'Reknum': ['8003', '8003', '4007'],
            'Amount': [-10620.0, -5310.0, 100.0]
        })
        cache.get_data.return_value = df
        
        result = toeristenbelasting_generator._get_total_revenue_8003(
            cache=cache,
            db=db,
            year=2025
        )
        
        # Total 8003 = -10620 + -5310 = -15930
        assert result == -15930.0
    
    def test_get_service_fees(self):
        """Test service fees retrieval from account 4007"""
        cache = Mock()
        db = Mock()
        
        df = pd.DataFrame({
            'jaar': [2025, 2025, 2025],
            'Reknum': ['4007', '4007', '8003'],
            'Amount': [-100.0, -50.0, 1000.0]
        })
        cache.get_data.return_value = df
        
        result = toeristenbelasting_generator._get_service_fees(
            cache=cache,
            db=db,
            year=2025
        )
        
        # Total 4007 = -100 + -50 = -150
        assert result == -150.0
    
    def test_calculate_taxable_revenue(self):
        """Test taxable revenue calculation"""
        financial_data = {
            'saldo_toeristenbelasting': 930.0,
            'total_revenue_8003': 15930.0,
            'ontvangsten_excl_btw_excl_toeristenbelasting': 15000.0,
            'ontvangsten_logies_inwoners': 0.0,
            'kortingen_provisie_commissie': 150.0,
            'no_show_omzet': 100.0
        }
        
        result = toeristenbelasting_generator._calculate_taxable_revenue(
            financial_data=financial_data
        )
        
        # Totaal 2+3+4 = 0 + 150 + 100 = 250
        assert result['totaal_2_3_4'] == 250.0
        
        # Belastbare omzet = 15000 - 250 = 14750
        assert result['belastbare_omzet_logies'] == 14750.0
        
        # Expected next year = 14750 * 1.05 = 15487.5
        assert abs(result['verwachte_belastbare_omzet_volgend_jaar'] - 15487.5) < 0.01
    
    def test_get_financial_data(self):
        """Test financial data retrieval"""
        cache = Mock()
        db = Mock()
        
        # Mock dataframe
        df = pd.DataFrame({
            'jaar': [2025, 2025, 2025, 2025],
            'Reknum': ['8003', '8003', '4007', '4007'],
            'Amount': [-10620.0, -5310.0, -100.0, -50.0]
        })
        cache.get_data.return_value = df
        
        bnb_data = {
            'all_bookings': [],
            'cancelled_bookings': [
                {'amountGross': 520.0, 'amountVat': 88.0},
                {'amountGross': 300.0, 'amountVat': 50.0}
            ],
            'realised_bookings': []
        }
        
        result = toeristenbelasting_generator._get_financial_data(
            cache=cache,
            db=db,
            year=2025,
            bnb_data=bnb_data
        )
        
        # Tourist tax = (15930 / 106.2) * 6.2 = 930
        expected_tax = abs(((-15930) / 106.2) * 6.2)
        assert abs(result['saldo_toeristenbelasting'] - expected_tax) < 0.01
        
        # Total revenue 8003
        assert result['total_revenue_8003'] == 15930.0
        
        # Revenue excl. VAT and tourist tax
        assert abs(result['ontvangsten_excl_btw_excl_toeristenbelasting'] - (15930.0 - expected_tax)) < 0.01
        
        # Residents revenue (always 0)
        assert result['ontvangsten_logies_inwoners'] == 0
        
        # Service fees (absolute value)
        assert result['kortingen_provisie_commissie'] == 150.0
        
        # No-show revenue: (520-88) + (300-50) = 432 + 250 = 682
        assert result['no_show_omzet'] == 682.0
    
    def test_prepare_template_data(self):
        """Test template data preparation"""
        config = {
            'functie': 'DGA',
            'telefoonnummer': '06921893861',
            'email': 'peter@pgeers.nl',
            'aantal_kamers': 3,
            'aantal_slaapplaatsen': 8,
            'naam': 'Peter Geers',
            'plaats': 'Hoofddorp'
        }
        
        rental_stats = {
            'totaal_verhuurde_nachten': 365,
            'cancelled_nachten': 12,
            'verhuurde_kamers_inwoners': 0,
            'totaal_belastbare_nachten': 353,
            'kamerbezettingsgraad': 85.50,
            'bedbezettingsgraad': 76.95
        }
        
        financial_data = {
            'saldo_toeristenbelasting': 930.0,
            'total_revenue_8003': 15930.0,
            'ontvangsten_excl_btw_excl_toeristenbelasting': 15000.0,
            'ontvangsten_logies_inwoners': 0.0,
            'kortingen_provisie_commissie': 150.0,
            'no_show_omzet': 100.0
        }
        
        taxable_revenue = {
            'totaal_2_3_4': 250.0,
            'belastbare_omzet_logies': 14750.0,
            'verwachte_belastbare_omzet_volgend_jaar': 15487.5
        }
        
        result = toeristenbelasting_generator._prepare_template_data(
            year=2025,
            config=config,
            periode_van='1-1-2025',
            periode_tm='31-12-2025',
            rental_stats=rental_stats,
            financial_data=financial_data,
            taxable_revenue=taxable_revenue
        )
        
        # Check basic fields
        assert result['year'] == '2025'
        assert result['next_year'] == '2026'
        assert result['functie'] == 'DGA'
        assert result['email'] == 'peter@pgeers.nl'
        
        # Check formatted numbers
        assert result['totaal_verhuurde_nachten'] == '365'
        assert result['cancelled_nachten'] == '12'
        assert result['kamerbezettingsgraad'] == '85.50'
        
        # Check currency formatting
        assert '€' in result['saldo_toeristenbelasting']
        assert '930' in result['saldo_toeristenbelasting']
        
        # Check date is present
        assert 'datum' in result
        assert '-' in result['datum']  # DD-MM-YYYY format
    
    def test_generate_toeristenbelasting_report_success(self):
        """Test full report generation with success"""
        # Mock cache
        cache = Mock()
        db = Mock()
        
        df = pd.DataFrame({
            'jaar': [2025, 2025],
            'Reknum': ['8003', '4007'],
            'Amount': [-10620.0, -100.0]
        })
        cache.get_data.return_value = df
        
        # Mock BNB cache
        bnb_cache = Mock()
        bnb_cache.query_by_year.return_value = [
            {'nights': 5, 'amountGross': 520.0, 'amountVat': 88.0}
        ]
        bnb_cache.query_cancelled_by_year.return_value = [
            {'nights': 1, 'amountGross': 100.0, 'amountVat': 20.0}
        ]
        bnb_cache.query_realised_by_year.return_value = [
            {'nights': 5, 'amountGross': 520.0, 'amountVat': 88.0}
        ]
        
        result = toeristenbelasting_generator.generate_toeristenbelasting_report(
            cache=cache,
            bnb_cache=bnb_cache,
            db=db,
            year=2025
        )
        
        assert result['success'] is True
        assert 'template_data' in result
        assert 'raw_data' in result
        
        # Check template data structure
        template_data = result['template_data']
        assert 'year' in template_data
        assert 'saldo_toeristenbelasting' in template_data
        assert 'totaal_verhuurde_nachten' in template_data
        
        # Check raw data structure
        raw_data = result['raw_data']
        assert raw_data['year'] == 2025
        assert 'aantal_kamers' in raw_data
        assert 'totaal_verhuurde_nachten' in raw_data
    
    def test_generate_toeristenbelasting_report_error_handling(self):
        """Test report generation with error in BNB cache"""
        cache = Mock()
        db = Mock()
        
        # Mock dataframe for cache
        df = pd.DataFrame({
            'jaar': [2025],
            'Reknum': ['8003'],
            'Amount': [-10620.0]
        })
        cache.get_data.return_value = df
        
        # Mock BNB cache that raises exception
        bnb_cache = Mock()
        bnb_cache.query_by_year.side_effect = Exception("BNB cache error")
        
        result = toeristenbelasting_generator.generate_toeristenbelasting_report(
            cache=cache,
            bnb_cache=bnb_cache,
            db=db,
            year=2025
        )
        
        # The function should still succeed but with empty booking data
        # This is by design - it handles errors gracefully
        assert result['success'] is True
        assert 'template_data' in result
        
        # Verify that booking-related fields are zero
        raw_data = result['raw_data']
        assert raw_data['totaal_verhuurde_nachten'] == 0
        assert raw_data['cancelled_nachten'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
