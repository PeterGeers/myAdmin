from database import DatabaseManager
from mutaties_cache import get_cache
from datetime import datetime
import html

class ToeristenbelastingProcessor:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        self.db = DatabaseManager(test_mode=test_mode)
    
    def generate_toeristenbelasting_report(self, year):
        """Generate Toeristenbelasting (Tourist Tax) declaration report"""
        try:
            # Fixed values
            functie = "DGA"
            telefoonnummer = "06921893861"
            email = "peter@pgeers.nl"
            aantal_kamers = 3
            aantal_slaapplaatsen = 8
            naam = "Peter Geers"
            plaats = "Hoofddorp"
            
            # Calculate period
            periode_van = f"1-1-{year}"
            periode_tm = f"31-12-{year}"
            
            # Get BNB data for the year
            bnb_data = self._get_bnb_data(year)
            
            # Calculate totals
            totaal_verhuurde_kamers = len(bnb_data['all_bookings'])
            no_shows = len(bnb_data['cancelled_bookings'])
            verhuurde_kamers_inwoners = 0  # Always 0 per requirements
            totaal_belastbare_kamerverhuren = totaal_verhuurde_kamers - no_shows
            
            # Calculate occupancy rates
            total_nights = sum(b['nights'] for b in bnb_data['realised_bookings'])
            max_nights = aantal_kamers * 365
            kamerbezettingsgraad = (total_nights / max_nights * 100) if max_nights > 0 else 0
            bedbezettingsgraad = kamerbezettingsgraad * 0.90
            
            # Get tourist tax from account 8003
            saldo_toeristenbelasting = self._get_tourist_tax_from_account(year)
            
            # Calculate revenue components
            total_revenue_8003 = self._get_total_revenue_8003(year)
            ontvangsten_excl_btw_excl_toeristenbelasting = total_revenue_8003 - saldo_toeristenbelasting
            
            ontvangsten_logies_inwoners = 0  # Always 0
            kortingen_provisie_commissie = 0  # Always 0
            no_show_omzet = sum(b['amountNett'] for b in bnb_data['cancelled_bookings'])
            
            totaal_2_3_4 = ontvangsten_logies_inwoners + kortingen_provisie_commissie + no_show_omzet
            belastbare_omzet_logies = ontvangsten_excl_btw_excl_toeristenbelasting - totaal_2_3_4
            verwachte_belastbare_omzet_volgend_jaar = belastbare_omzet_logies * 1.05
            
            # Generate HTML report
            html_report = self._generate_html_report(
                year=year,
                functie=functie,
                telefoonnummer=telefoonnummer,
                email=email,
                periode_van=periode_van,
                periode_tm=periode_tm,
                aantal_kamers=aantal_kamers,
                aantal_slaapplaatsen=aantal_slaapplaatsen,
                totaal_verhuurde_kamers=totaal_verhuurde_kamers,
                no_shows=no_shows,
                verhuurde_kamers_inwoners=verhuurde_kamers_inwoners,
                totaal_belastbare_kamerverhuren=totaal_belastbare_kamerverhuren,
                kamerbezettingsgraad=kamerbezettingsgraad,
                bedbezettingsgraad=bedbezettingsgraad,
                saldo_toeristenbelasting=saldo_toeristenbelasting,
                ontvangsten_excl_btw_excl_toeristenbelasting=ontvangsten_excl_btw_excl_toeristenbelasting,
                ontvangsten_logies_inwoners=ontvangsten_logies_inwoners,
                kortingen_provisie_commissie=kortingen_provisie_commissie,
                no_show_omzet=no_show_omzet,
                totaal_2_3_4=totaal_2_3_4,
                belastbare_omzet_logies=belastbare_omzet_logies,
                verwachte_belastbare_omzet_volgend_jaar=verwachte_belastbare_omzet_volgend_jaar,
                naam=naam,
                plaats=plaats
            )
            
            return {
                'success': True,
                'html_report': html_report,
                'data': {
                    'year': year,
                    'functie': functie,
                    'telefoonnummer': telefoonnummer,
                    'email': email,
                    'periode_van': periode_van,
                    'periode_tm': periode_tm,
                    'aantal_kamers': aantal_kamers,
                    'aantal_slaapplaatsen': aantal_slaapplaatsen,
                    'totaal_verhuurde_kamers': totaal_verhuurde_kamers,
                    'no_shows': no_shows,
                    'verhuurde_kamers_inwoners': verhuurde_kamers_inwoners,
                    'totaal_belastbare_kamerverhuren': totaal_belastbare_kamerverhuren,
                    'kamerbezettingsgraad': round(kamerbezettingsgraad, 2),
                    'bedbezettingsgraad': round(bedbezettingsgraad, 2),
                    'saldo_toeristenbelasting': round(saldo_toeristenbelasting, 2),
                    'ontvangsten_excl_btw_excl_toeristenbelasting': round(ontvangsten_excl_btw_excl_toeristenbelasting, 2),
                    'ontvangsten_logies_inwoners': ontvangsten_logies_inwoners,
                    'kortingen_provisie_commissie': kortingen_provisie_commissie,
                    'no_show_omzet': round(no_show_omzet, 2),
                    'totaal_2_3_4': round(totaal_2_3_4, 2),
                    'belastbare_omzet_logies': round(belastbare_omzet_logies, 2),
                    'verwachte_belastbare_omzet_volgend_jaar': round(verwachte_belastbare_omzet_volgend_jaar, 2),
                    'naam': naam,
                    'plaats': plaats
                }
            }
            
        except Exception as e:
            print(f"Error generating toeristenbelasting report: {e}", flush=True)
            return {'success': False, 'error': str(e)}
    
    def _get_bnb_data(self, year):
        """Get BNB booking data for the year"""
        try:
            query = """
            SELECT 
                checkinDate,
                checkoutDate,
                nights,
                amountGross,
                amountNett,
                amountChannelFee,
                amountTouristTax,
                amountVat,
                guestName,
                status
            FROM bnb
            WHERE YEAR(checkinDate) = %s
            """
            
            results = self.db.execute_query(query, (year,))
            
            all_bookings = []
            cancelled_bookings = []
            realised_bookings = []
            
            for row in results:
                booking = {
                    'checkinDate': row[0],
                    'checkoutDate': row[1],
                    'nights': row[2] or 0,
                    'amountGross': float(row[3]) if row[3] else 0,
                    'amountNett': float(row[4]) if row[4] else 0,
                    'amountChannelFee': float(row[5]) if row[5] else 0,
                    'amountTouristTax': float(row[6]) if row[6] else 0,
                    'amountVat': float(row[7]) if row[7] else 0,
                    'guestName': row[8],
                    'status': row[9]
                }
                
                all_bookings.append(booking)
                
                if booking['status'] == 'cancelled':
                    cancelled_bookings.append(booking)
                else:
                    realised_bookings.append(booking)
            
            return {
                'all_bookings': all_bookings,
                'cancelled_bookings': cancelled_bookings,
                'realised_bookings': realised_bookings
            }
            
        except Exception as e:
            print(f"Error getting BNB data: {e}", flush=True)
            return {
                'all_bookings': [],
                'cancelled_bookings': [],
                'realised_bookings': []
            }
    
    def _get_tourist_tax_from_account(self, year):
        """Calculate tourist tax from account 8003: (sum / 106.2) * 6.2"""
        try:
            cache = get_cache()
            df = cache.get_data(self.db)
            
            # Filter by year and account 8003
            df_filtered = df[(df['jaar'] == int(year)) & (df['Reknum'] == '8003')].copy()
            
            total_8003 = df_filtered['Amount'].sum()
            
            # Calculate tourist tax: (sum / 106.2) * 6.2
            tourist_tax = (total_8003 / 106.2) * 6.2
            
            return tourist_tax
            
        except Exception as e:
            print(f"Error calculating tourist tax: {e}", flush=True)
            return 0
    
    def _get_total_revenue_8003(self, year):
        """Get total revenue from account 8003"""
        try:
            cache = get_cache()
            df = cache.get_data(self.db)
            
            # Filter by year and account 8003
            df_filtered = df[(df['jaar'] == int(year)) & (df['Reknum'] == '8003')].copy()
            
            return df_filtered['Amount'].sum()
            
        except Exception as e:
            print(f"Error getting total revenue 8003: {e}", flush=True)
            return 0
