from database import DatabaseManager
from google_drive_service import GoogleDriveService
from mutaties_cache import get_cache
import os
from datetime import datetime
import tempfile
import html

class BTWProcessor:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        self.db = DatabaseManager(test_mode=test_mode)
    
    def generate_btw_report(self, administration, year, quarter):
        """Generate BTW declaration report based on R script logic"""
        try:
            # Calculate quarter end date
            quarter_month = int(quarter) * 3
            quarter_end_date = f"{year}-{quarter_month:02d}-31"
            if quarter_month == 6:
                quarter_end_date = f"{year}-06-30"
            elif quarter_month == 9:
                quarter_end_date = f"{year}-09-30"
            elif quarter_month == 12:
                quarter_end_date = f"{year}-12-31"
            elif quarter_month == 3:
                quarter_end_date = f"{year}-03-31"
            
            # Get balance data (BTW accounts 2010, 2020, 2021)
            balance_data = self._get_balance_data(administration, quarter_end_date)
            
            # Get quarter data (BTW accounts + revenue accounts 8001, 8002, 8003)
            quarter_data = self._get_quarter_data(administration, year, quarter)
            
            # Calculate BTW amounts
            calculations = self._calculate_btw_amounts(balance_data, quarter_data)
            
            # Generate HTML report
            html_report = self._generate_html_report(
                administration, year, quarter, quarter_end_date,
                balance_data, quarter_data, calculations
            )
            
            # Prepare transaction for saving
            transaction = self._prepare_btw_transaction(
                administration, year, quarter, calculations
            )
            
            return {
                'success': True,
                'html_report': html_report,
                'transaction': transaction,
                'calculations': calculations,
                'quarter_end_date': quarter_end_date
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_balance_data(self, administration, end_date):
        """Get balance data for BTW accounts up to end date using cache"""
        try:
            # Get cache instance
            cache = get_cache()
            df = cache.get_data(self.db)
            
            # Filter by date
            df_filtered = df[df['TransactionDate'] <= end_date].copy()
            
            # Filter by administration (LIKE pattern) - lowercase column name
            df_filtered = df_filtered[df_filtered['administration'].str.startswith(administration)]
            
            # Filter by BTW accounts
            df_filtered = df_filtered[df_filtered['Reknum'].isin(['2010', '2020', '2021'])]
            
            # Group by account
            grouped = df_filtered.groupby(['Reknum', 'AccountName'], as_index=False).agg({
                'Amount': 'sum'
            })
            
            # Rename Amount to amount (lowercase for consistency)
            grouped = grouped.rename(columns={'Amount': 'amount'})
            
            # Convert to list of dicts
            results = grouped.to_dict('records')
            
            return results
        except Exception as e:
            print(f"Error getting balance data: {e}", flush=True)
            return []
    
    def _get_quarter_data(self, administration, year, quarter):
        """Get quarter data for BTW and revenue accounts using cache"""
        try:
            # Get cache instance
            cache = get_cache()
            df = cache.get_data(self.db)
            
            # Filter by year and quarter
            df_filtered = df[(df['jaar'] == int(year)) & (df['kwartaal'] == int(quarter))].copy()
            
            # Filter by administration (LIKE pattern) - lowercase column name
            df_filtered = df_filtered[df_filtered['administration'].str.startswith(administration)]
            
            # Filter by BTW and revenue accounts
            df_filtered = df_filtered[df_filtered['Reknum'].isin(['2010', '2020', '2021', '8001', '8002', '8003'])]
            
            # Group by account
            grouped = df_filtered.groupby(['Reknum', 'AccountName'], as_index=False).agg({
                'Amount': 'sum'
            })
            
            # Rename Amount to amount (lowercase for consistency)
            grouped = grouped.rename(columns={'Amount': 'amount'})
            
            # Convert to list of dicts
            results = grouped.to_dict('records')
            
            return results
        except Exception as e:
            print(f"Error getting quarter data: {e}", flush=True)
            return []
    
    def _calculate_btw_amounts(self, balance_data, quarter_data):
        """Calculate BTW amounts based on R script logic"""
        try:
            # Calculate total balance (te betalen/ontvangen)
            total_balance = sum(row['amount'] for row in balance_data)
            
            # Calculate received BTW (accounts 2020, 2021)
            received_btw = sum(
                row['amount'] for row in quarter_data 
                if row['Reknum'] in ['2020', '2021']
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
            print(f"Error calculating BTW amounts: {e}", flush=True)
            return {
                'total_balance': 0,
                'received_btw': 0,
                'prepaid_btw': 0,
                'payment_instruction': '€0 te betalen'
            }
    
    def _generate_html_report(self, administration, year, quarter, end_date, 
                            balance_data, quarter_data, calculations):
        """Generate HTML report similar to R markdown output"""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>BTW aangifte</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1, h2, h3 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .summary {{ background-color: #e8f4fd; padding: 15px; border-radius: 5px; }}
                .amount {{ text-align: right; }}
            </style>
        </head>
        <body>
            <h1>BTW aangifte</h1>
            <p><strong>Auteur:</strong> Peter Geers</p>
            
            <p>Dit overzicht laat de gegevens zien voor de BTW aangifte van <strong>{administration}</strong> 
            Boekjaar <strong>{year}</strong> en kwartaal <strong>{quarter}</strong> en opmaakdatum <strong>{end_date}</strong></p>
            
            <h3>Eindbalans t/m {end_date}</h3>
            <table>
                <thead>
                    <tr>
                        <th>Reknum</th>
                        <th>AccountName</th>
                        <th class="amount">Amount</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for row in balance_data:
            html_content += f"""
                    <tr>
                        <td>{html.escape(str(row['Reknum']))}</td>
                        <td>{html.escape(str(row['AccountName']))}</td>
                        <td class="amount">€{row['amount']:,.2f}</td>
                    </tr>
            """
        
        html_content += f"""
                </tbody>
            </table>
            
            <h3>Gegevens kwartaal {year} - {quarter}</h3>
            <table>
                <thead>
                    <tr>
                        <th>Reknum</th>
                        <th>AccountName</th>
                        <th class="amount">Amount</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for row in quarter_data:
            html_content += f"""
                    <tr>
                        <td>{html.escape(str(row['Reknum']))}</td>
                        <td>{html.escape(str(row['AccountName']))}</td>
                        <td class="amount">€{row['amount']:,.2f}</td>
                    </tr>
            """
        
        html_content += f"""
                </tbody>
            </table>
            
            <div class="summary">
                <h3>Samenvatting</h3>
                <ul>
                    <li><strong>Netto:</strong> {calculations['payment_instruction']}</li>
                    <li><strong>Ontvangen BTW:</strong> €{round(abs(calculations['received_btw']))}</li>
                    <li><strong>Vooruitbetaalde BTW:</strong> €{round(calculations['prepaid_btw'])}</li>
                </ul>
                
                <p><a href="https://mijnzakelijk.belastingdienst.nl/GTService/#/inloggen" target="_blank">
                Inloggen belastingdienst</a></p>
            </div>
            
            <p><em>Gegenereerd op: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</em></p>
        </body>
        </html>
        """
        
        return html_content
    
    def _prepare_btw_transaction(self, administration, year, quarter, calculations):
        """Prepare BTW transaction for saving to mutaties table"""
        # Get last BTW transaction for reference
        last_btw = self._get_last_btw_transaction(administration)
        
        total_balance = calculations['total_balance']
        transaction_date = datetime.now().strftime('%Y-%m-%d')
        
        # Determine debet/credit based on amount
        if total_balance < 0:  # Te betalen
            debet = '2010'
            credit = '1300'
        else:  # Te ontvangen
            debet = '1300'
            credit = '2010'
        
        transaction = {
            'TransactionNumber': 'BTW',
            'TransactionDate': transaction_date,
            'TransactionDescription': f'BTW aangifte {year} Q{quarter}',
            'TransactionAmount': round(abs(total_balance)),
            'Debet': debet,
            'Credit': credit,
            'ReferenceNumber': 'BTW',
            'Ref1': f'BTW aangifte {administration}',
            'Ref2': f'{year}-Q{quarter}',
            'Ref3': calculations['payment_instruction'],
            'Ref4': f'Generated {transaction_date}',
            'Administration': administration
        }
        
        return transaction
    
    def _get_last_btw_transaction(self, administration):
        """Get last BTW transaction for reference"""
        conn = None
        cursor = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            table_name = 'mutaties_test' if self.test_mode else 'mutaties'
            
            query = f"""
                SELECT * FROM {table_name}
                WHERE TransactionNumber = 'BTW'
                AND administration = %s
                ORDER BY TransactionDate DESC, ID DESC
                LIMIT 1
            """
            
            cursor.execute(query, (administration,))
            result = cursor.fetchone()
            
            return result
        except Exception as e:
            print(f"Error getting last BTW transaction: {e}", flush=True)
            return None
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    def save_btw_transaction(self, transaction):
        """Save BTW transaction to database"""
        conn = None
        cursor = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            table_name = 'mutaties_test' if self.test_mode else 'mutaties'
            
            insert_query = f"""
                INSERT INTO {table_name} (
                    TransactionNumber, TransactionDate, TransactionDescription,
                    TransactionAmount, Debet, Credit, ReferenceNumber,
                    Ref1, Ref2, Ref3, Ref4, Administration
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            cursor.execute(insert_query, (
                transaction['TransactionNumber'],
                transaction['TransactionDate'],
                transaction['TransactionDescription'],
                transaction['TransactionAmount'],
                transaction['Debet'],
                transaction['Credit'],
                transaction['ReferenceNumber'],
                transaction['Ref1'],
                transaction['Ref2'],
                transaction['Ref3'],
                transaction['Ref4'],
                transaction['Administration']
            ))
            
            conn.commit()
            transaction_id = cursor.lastrowid
            
            return {'success': True, 'transaction_id': transaction_id}
            
        except Exception as e:
            if conn:
                conn.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    
    def upload_report_to_drive(self, html_content, filename):
        """Upload HTML report to Google Drive BTW folder"""
        try:
            if self.test_mode:
                # In test mode, save locally
                safe_filename = os.path.basename(filename)
                local_path = os.path.join('uploads', safe_filename)
                with open(local_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                return {
                    'success': True,
                    'url': f'http://localhost:5000/uploads/{safe_filename}',
                    'location': 'local'
                }
            else:
                # Production mode - upload to Google Drive
                drive_service = GoogleDriveService()
                
                # Find BTW folder
                folders = drive_service.list_subfolders()
                btw_folder_id = None
                
                for folder in folders:
                    if folder['name'].lower() == 'btw':
                        btw_folder_id = folder['id']
                        break
                
                if not btw_folder_id:
                    return {'success': False, 'error': 'BTW folder not found in Google Drive'}
                
                # Create temporary file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_file:
                    temp_file.write(html_content)
                    temp_path = temp_file.name
                
                try:
                    # Upload to Google Drive
                    result = drive_service.upload_file(temp_path, filename, btw_folder_id)
                    return {
                        'success': True,
                        'url': result['url'],
                        'location': 'google_drive'
                    }
                finally:
                    # Clean up temp file
                    os.unlink(temp_path)
                    
        except Exception as e:
            return {'success': False, 'error': str(e)}