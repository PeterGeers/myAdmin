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

    
    def _generate_html_report(self, **kwargs):
        """Generate HTML report for Toeristenbelasting declaration"""
        
        year = kwargs['year']
        next_year = int(year) + 1
        datum = datetime.now().strftime('%d-%m-%Y')
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Aangifte Toeristenbelasting {year}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 40px;
            line-height: 1.6;
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #333;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
            border-bottom: 1px solid #999;
            padding-bottom: 5px;
        }}
        .section {{
            margin: 20px 0;
        }}
        .field {{
            margin: 10px 0;
            padding: 5px 0;
        }}
        .label {{
            font-weight: bold;
            display: inline-block;
            width: 400px;
        }}
        .value {{
            display: inline-block;
        }}
        .amount {{
            text-align: right;
            font-family: 'Courier New', monospace;
        }}
        .signature {{
            margin-top: 50px;
            border-top: 1px solid #999;
            padding-top: 20px;
        }}
        .signature-line {{
            margin: 30px 0;
            border-bottom: 1px solid #333;
            width: 300px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background-color: #f2f2f2;
        }}
        .number {{
            text-align: right;
        }}
    </style>
</head>
<body>
    <h1>Aangifte Toeristenbelasting {year}</h1>
    
    <div class="section">
        <h2>Contactgegevens</h2>
        <div class="field">
            <span class="label">Functie:</span>
            <span class="value">{html.escape(kwargs['functie'])}</span>
        </div>
        <div class="field">
            <span class="label">Telefoonnummer:</span>
            <span class="value">{html.escape(kwargs['telefoonnummer'])}</span>
        </div>
        <div class="field">
            <span class="label">E-mailadres:</span>
            <span class="value">{html.escape(kwargs['email'])}</span>
        </div>
    </div>
    
    <div class="section">
        <h2>Periode en Accommodatie</h2>
        <div class="field">
            <span class="label">Periode waarop aangifte betrekking heeft:</span>
            <span class="value">{html.escape(kwargs['periode_van'])} t/m {html.escape(kwargs['periode_tm'])}</span>
        </div>
        <div class="field">
            <span class="label">Aantal kamers in {year}:</span>
            <span class="value">{kwargs['aantal_kamers']}</span>
        </div>
        <div class="field">
            <span class="label">Aantal beschikbare slaapplaatsen:</span>
            <span class="value">{kwargs['aantal_slaapplaatsen']}</span>
        </div>
    </div>
    
    <div class="section">
        <h2>Verhuurgegevens</h2>
        <div class="field">
            <span class="label">Totaal verhuurde kamers:</span>
            <span class="value">{kwargs['totaal_verhuurde_kamers']}</span>
        </div>
        <div class="field">
            <span class="label">No-shows:</span>
            <span class="value">{kwargs['no_shows']}</span>
        </div>
        <div class="field">
            <span class="label">Verhuurde kamers aan inwoners:</span>
            <span class="value">{kwargs['verhuurde_kamers_inwoners']}</span>
        </div>
        <div class="field">
            <span class="label">Totaal belastbare kamerverhuren:</span>
            <span class="value">{kwargs['totaal_belastbare_kamerverhuren']}</span>
        </div>
        <div class="field">
            <span class="label">Kamerbezettingsgraad (%):</span>
            <span class="value">{kwargs['kamerbezettingsgraad']:.2f}%</span>
        </div>
        <div class="field">
            <span class="label">Bedbezettingsgraad (%):</span>
            <span class="value">{kwargs['bedbezettingsgraad']:.2f}%</span>
        </div>
    </div>
    
    <div class="section">
        <h2>Financiële Gegevens</h2>
        <div class="field">
            <span class="label">Saldo totaal ingehouden toeristenbelasting:</span>
            <span class="value amount">€ {kwargs['saldo_toeristenbelasting']:,.2f}</span>
        </div>
        <div class="field">
            <span class="label">Logiesomzet incl./excl. BTW:</span>
            <span class="value">excl. BTW</span>
        </div>
        <div class="field">
            <span class="label">Logiesomzet incl./excl. toeristenbelasting:</span>
            <span class="value">incl. toeristenbelasting</span>
        </div>
    </div>
    
    <div class="section">
        <h2>Berekening Belastbare Omzet</h2>
        <table>
            <tr>
                <th>Omschrijving</th>
                <th class="number">Bedrag (€)</th>
            </tr>
            <tr>
                <td>[1] Ontvangsten excl. BTW en excl. Toeristenbelasting</td>
                <td class="number">{kwargs['ontvangsten_excl_btw_excl_toeristenbelasting']:,.2f}</td>
            </tr>
            <tr>
                <td>[2] Ontvangsten logies inwoners excl. BTW</td>
                <td class="number">{kwargs['ontvangsten_logies_inwoners']:,.2f}</td>
            </tr>
            <tr>
                <td>[3] Kortingen / provisie / commissie</td>
                <td class="number">{kwargs['kortingen_provisie_commissie']:,.2f}</td>
            </tr>
            <tr>
                <td>[4] No-show omzet</td>
                <td class="number">{kwargs['no_show_omzet']:,.2f}</td>
            </tr>
            <tr style="background-color: #f9f9f9;">
                <td><strong>[5] Totaal 2 + 3 + 4</strong></td>
                <td class="number"><strong>{kwargs['totaal_2_3_4']:,.2f}</strong></td>
            </tr>
            <tr style="background-color: #e6f3ff;">
                <td><strong>[6] Belastbare omzet logies ([1] - [5])</strong></td>
                <td class="number"><strong>{kwargs['belastbare_omzet_logies']:,.2f}</strong></td>
            </tr>
            <tr style="background-color: #fff3cd;">
                <td><strong>Verwachte belastbare omzet {next_year} ([6] * 1.05)</strong></td>
                <td class="number"><strong>{kwargs['verwachte_belastbare_omzet_volgend_jaar']:,.2f}</strong></td>
            </tr>
        </table>
    </div>
    
    <div class="signature">
        <h2>Ondertekening</h2>
        <div class="field">
            <span class="label">Naam:</span>
            <span class="value">{html.escape(kwargs['naam'])}</span>
        </div>
        <div class="field">
            <span class="label">Plaats:</span>
            <span class="value">{html.escape(kwargs['plaats'])}</span>
        </div>
        <div class="field">
            <span class="label">Datum:</span>
            <span class="value">{datum}</span>
        </div>
        <div class="field">
            <span class="label">Aantal bijlagen:</span>
            <span class="value">0</span>
        </div>
        <div class="signature-line">
            <p style="margin-top: 50px; font-size: 12px; color: #666;">Handtekening</p>
        </div>
    </div>
</body>
</html>
"""
        
        return html_content
