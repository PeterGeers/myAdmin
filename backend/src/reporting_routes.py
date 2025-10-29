from flask import Blueprint, request, jsonify
from database import DatabaseManager
from datetime import datetime
from contextlib import contextmanager

reporting_bp = Blueprint('reporting', __name__)

class ReportingService:
    def __init__(self, test_mode=False):
        self.db = DatabaseManager(test_mode=test_mode)
        self.table_name = 'mutaties_test' if test_mode else 'mutaties'
    
    @contextmanager
    def get_cursor(self):
        """Context manager for database operations"""
        connection = self.db.get_connection()
        cursor = connection.cursor(dictionary=True)
        try:
            yield cursor
        finally:
            cursor.close()
            connection.close()
    
    def build_where_clause(self, conditions):
        """Build WHERE clause from conditions dict"""
        where_parts = []
        params = []
        
        for key, value in conditions.items():
            if value == 'all' or not value:
                continue
            
            if key == 'date_range':
                if value.get('from') and value.get('to'):
                    where_parts.append("TransactionDate BETWEEN %s AND %s")
                    params.extend([value['from'], value['to']])
                elif value.get('to'):
                    where_parts.append("TransactionDate <= %s")
                    params.append(value['to'])
            elif key == 'years':
                if isinstance(value, list) and value:
                    placeholders = ','.join(['%s'] * len(value))
                    where_parts.append(f"jaar IN ({placeholders})")
                    params.extend(value)
            elif key == 'administration':
                where_parts.append("Administration = %s")
                params.append(value)
            elif key == 'profit_loss':
                where_parts.append("VW = %s")
                params.append(value)
            elif key == 'channel':
                where_parts.append("channel = %s")
                params.append(value)
            elif key == 'listing':
                where_parts.append("listing = %s")
                params.append(value)
            elif key == 'reference':
                where_parts.append("ReferenceNumber = %s")
                params.append(value)
            elif key == 'ledger':
                where_parts.append("ledger = %s")
                params.append(value)
        
        return " AND ".join(where_parts) if where_parts else "1=1", params
    
    def get_financial_summary(self, date_from, date_to, category='all', administration='all'):
        """Get financial summary data for reporting"""
        try:
            connection = self.db.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # Base query
            where_conditions = ["TransactionDate BETWEEN %s AND %s"]
            params = [date_from, date_to]
            
            # Add administration filter
            if administration != 'all':
                where_conditions.append("Administration = %s")
                params.append(administration)
            
            # Category-based account filtering
            if category == 'income':
                where_conditions.append("(Credit BETWEEN '4000' AND '4999' OR Credit BETWEEN '8000' AND '8999')")
            elif category == 'expense':
                where_conditions.append("(Debet BETWEEN '6000' AND '6999' OR Debet BETWEEN '7000' AND '7999')")
            elif category == 'vat':
                where_conditions.append("(Debet = '2010' OR Credit = '2010')")
            
            where_clause = " AND ".join(where_conditions)
            
            # Query for account-based summary
            # amazonq-ignore-next-line
            query = f"""
                SELECT 
                    CASE 
                        WHEN Debet BETWEEN '4000' AND '4999' OR Credit BETWEEN '4000' AND '4999' THEN 'Revenue'
                        WHEN Debet BETWEEN '6000' AND '6999' OR Credit BETWEEN '6000' AND '6999' THEN 'Operating Expenses'
                        WHEN Debet BETWEEN '7000' AND '7999' OR Credit BETWEEN '7000' AND '7999' THEN 'Other Expenses'
                        WHEN Debet = '2010' OR Credit = '2010' THEN 'VAT'
                        WHEN Debet BETWEEN '1000' AND '1999' OR Credit BETWEEN '1000' AND '1999' THEN 'Bank/Cash'
                        ELSE 'Other'
                    END as category,
                    SUM(CASE 
                        WHEN Debet BETWEEN '4000' AND '8999' THEN -TransactionAmount
                        WHEN Credit BETWEEN '4000' AND '8999' THEN TransactionAmount
                        ELSE TransactionAmount
                    END) as amount
                FROM vw_mutaties
                WHERE {where_clause}
                GROUP BY category
                HAVING ABS(amount) > 0.01
                ORDER BY ABS(amount) DESC
            """
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            # Format data for frontend
            labels = [row['category'] for row in results]
            values = [float(row['amount']) for row in results]
            total = sum(abs(value) for value in values)
            
            cursor.close()
            connection.close()
            
            return {
                'success': True,
                'data': {
                    'labels': labels,
                    'values': values,
                    'total': total
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_str_revenue_summary(self, date_from, date_to):
        """Get STR revenue summary from bnb table"""
        try:
            connection = self.db.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            query = """
                SELECT 
                    channel,
                    listing,
                    COUNT(*) as bookings,
                    SUM(amountGross) as gross_revenue,
                    SUM(amountNett) as net_revenue,
                    SUM(nights) as total_nights
                FROM bnbtotal
                WHERE checkinDate BETWEEN %s AND %s
                GROUP BY channel, listing
                ORDER BY gross_revenue DESC
            """
            
            cursor.execute(query, [date_from, date_to])
            results = cursor.fetchall()
            
            cursor.close()
            connection.close()
            
            return {
                'success': True,
                'data': results
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

@reporting_bp.route('/financial-summary', methods=['GET'])
def get_financial_summary():
    """Get financial summary report"""
    try:
        # Get query parameters
        date_from = request.args.get('dateFrom', datetime.now().strftime('%Y-01-01'))
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        category = request.args.get('category', 'all')
        administration = request.args.get('administration', 'all')
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        
        # Validate dates
        try:
            datetime.strptime(date_from, '%Y-%m-%d')
            datetime.strptime(date_to, '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid date format. Use YYYY-MM-DD'
            }), 400
        
        # Get report data
        service = ReportingService(test_mode=test_mode)
        result = service.get_financial_summary(date_from, date_to, category, administration)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@reporting_bp.route('/str-revenue', methods=['GET'])
def get_str_revenue():
    """Get STR revenue summary"""
    try:
        date_from = request.args.get('dateFrom', datetime.now().strftime('%Y-01-01'))
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        
        service = ReportingService(test_mode=test_mode)
        result = service.get_str_revenue_summary(date_from, date_to)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@reporting_bp.route('/account-summary', methods=['GET'])
def get_account_summary():
    """Get account-based summary for chart of accounts analysis"""
    try:
        service = ReportingService(request.args.get('testMode', 'false').lower() == 'true')
        date_from = request.args.get('dateFrom', datetime.now().strftime('%Y-01-01'))
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        
        with service.get_cursor() as cursor:
            cursor.execute("""
                SELECT Debet as account, SUM(TransactionAmount) as debet_total, COUNT(*) as debet_count
                FROM vw_mutaties
                WHERE TransactionDate BETWEEN %s AND %s AND Debet IS NOT NULL AND Debet != ''
                GROUP BY Debet
                UNION ALL
                SELECT Credit as account, -SUM(TransactionAmount) as credit_total, COUNT(*) as credit_count
                FROM vw_mutaties
                WHERE TransactionDate BETWEEN %s AND %s AND Credit IS NOT NULL AND Credit != ''
                GROUP BY Credit
                ORDER BY ABS(debet_total) DESC
            """, [date_from, date_to, date_from, date_to])
            results = cursor.fetchall()
        
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/mutaties-table', methods=['GET'])
def get_mutaties_table():
    """Get mutaties table data with PowerBI-style filters"""
    try:
        service = ReportingService(request.args.get('testMode', 'false').lower() == 'true')
        
        conditions = {
            'date_range': {
                'from': request.args.get('dateFrom', datetime.now().strftime('%Y-01-01')),
                'to': request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
            },
            'administration': request.args.get('administration', 'all'),
            'profit_loss': request.args.get('profitLoss', 'all')
        }
        
        where_clause, params = service.build_where_clause(conditions)
        
        with service.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT TransactionDate, TransactionDescription, Amount, Reknum,
                       AccountName, Administration, ReferenceNumber, VW
                FROM vw_mutaties
                WHERE {where_clause}
                ORDER BY TransactionDate DESC
                LIMIT 1000
            """, params)
            results = cursor.fetchall()
        
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/<table>-fields', methods=['GET'])
def get_table_fields(table):
    """Get field names for specified table"""
    table_map = {'bnb': 'bnbtotal', 'mutaties': 'vw_mutaties'}
    if table not in table_map:
        return jsonify({'success': False, 'error': 'Invalid table'}), 400
    
    try:
        service = ReportingService()
        with service.get_cursor() as cursor:
            cursor.execute(f"SHOW COLUMNS FROM {table_map[table]}")
            fields = [row['Field'] for row in cursor.fetchall()]
        
        return jsonify({'success': True, 'fields': fields})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/balance-data', methods=['GET'])
def get_balance_data():
    """Get balance data grouped by Parent and ledger"""
    try:
        service = ReportingService(request.args.get('testMode', 'false').lower() == 'true')
        
        conditions = {
            'date_range': {
                'from': request.args.get('dateFrom'),
                'to': request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
            },
            'administration': request.args.get('administration', 'all'),
            'profit_loss': request.args.get('profitLoss', 'all')
        }
        
        where_clause, params = service.build_where_clause(conditions)
        
        with service.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT Parent, ledger, SUM(Amount) as total_amount
                FROM vw_mutaties
                WHERE {where_clause}
                GROUP BY Parent, ledger
                ORDER BY Parent, ledger
            """, params)
            results = cursor.fetchall()
        
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/bnb-table', methods=['GET'])
def get_bnb_table():
    """Get BNB table data with PowerBI-style filters"""
    try:
        service = ReportingService(request.args.get('testMode', 'false').lower() == 'true')
        
        date_from = request.args.get('dateFrom', datetime.now().strftime('%Y-01-01'))
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        
        conditions = {
            'channel': request.args.get('channel', 'all'),
            'listing': request.args.get('listing', 'all')
        }
        
        where_parts = ["checkinDate BETWEEN %s AND %s"]
        params = [date_from, date_to]
        
        for key, value in conditions.items():
            if value != 'all':
                where_parts.append(f"{key} = %s")
                params.append(value)
        
        where_clause = " AND ".join(where_parts)
        
        with service.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT checkinDate, checkoutDate, channel, listing, nights, guests,
                       amountGross, amountNett, guestName, reservationCode
                FROM bnbtotal
                WHERE {where_clause}
                ORDER BY checkinDate DESC
                LIMIT 1000
            """, params)
            results = cursor.fetchall()
        
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/trends-data', methods=['GET'])
def get_trends_data():
    """Get P&L trends data by year"""
    try:
        service = ReportingService(request.args.get('testMode', 'false').lower() == 'true')
        
        years = [int(y) for y in request.args.get('years', str(datetime.now().year)).split(',') if y]
        
        conditions = {
            'years': years,
            'administration': request.args.get('administration', 'all'),
            'profit_loss': request.args.get('profitLoss', 'Y')
        }
        
        where_clause, params = service.build_where_clause(conditions)
        
        with service.get_cursor() as cursor:
            cursor.execute(f"""
                SELECT Parent, ledger, YEAR(TransactionDate) as year, SUM(Amount) as total_amount
                FROM vw_mutaties
                WHERE {where_clause}
                GROUP BY Parent, ledger, YEAR(TransactionDate)
                ORDER BY Parent, ledger, year
            """, params)
            results = cursor.fetchall()
        
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/filter-options', methods=['GET'])
def get_filter_options():
    """Get distinct values for each filter dropdown with cascading support"""
    try:
        service = ReportingService()
        administration = request.args.get('administration', 'all')
        ledger = request.args.get('ledger', 'all')
        
        with service.get_cursor() as cursor:
            # Get administrations
            cursor.execute("""
                SELECT DISTINCT Administration FROM vw_mutaties
                WHERE Administration IS NOT NULL AND Administration != ''
                ORDER BY Administration
            """)
            administrations = [row['Administration'] for row in cursor.fetchall()]
            
            # Get ledgers with optional administration filter
            ledger_conditions = ["ledger IS NOT NULL AND ledger != ''"]
            ledger_params = []
            if administration != 'all':
                ledger_conditions.append("Administration = %s")
                ledger_params.append(administration)
            
            cursor.execute(f"""
                SELECT DISTINCT ledger FROM vw_mutaties
                WHERE {' AND '.join(ledger_conditions)}
                ORDER BY ledger
            """, ledger_params)
            ledgers = [row['ledger'] for row in cursor.fetchall()]
            
            # Get references with optional filters
            ref_conditions = ["ReferenceNumber IS NOT NULL AND ReferenceNumber != ''"]
            ref_params = []
            if administration != 'all':
                ref_conditions.append("Administration = %s")
                ref_params.append(administration)
            if ledger != 'all':
                ref_conditions.append("ledger = %s")
                ref_params.append(ledger)
            
            cursor.execute(f"""
                SELECT DISTINCT ReferenceNumber FROM vw_mutaties
                WHERE {' AND '.join(ref_conditions)}
                ORDER BY ReferenceNumber
            """, ref_params)
            references = [row['ReferenceNumber'] for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'administrations': administrations,
            'ledgers': ledgers,
            'references': references
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/actuals-profitloss', methods=['GET'])
def get_actuals_profitloss():
    """Get actuals profit/loss data"""
    try:
        service = ReportingService(request.args.get('testMode', 'false').lower() == 'true')
        years = [y for y in request.args.get('years', str(datetime.now().year)).split(',') if y]
        group_by = request.args.get('groupBy', 'year')
        
        conditions = {
            'years': years,
            'administration': request.args.get('administration', 'all'),
            'profit_loss': 'Y'
        }
        
        where_clause, params = service.build_where_clause(conditions)
        
        if group_by == 'year':
            query = f"SELECT jaar as period, SUM(Amount) as total_amount FROM vw_mutaties WHERE {where_clause} GROUP BY jaar ORDER BY jaar"
        else:
            query = f"SELECT Parent, ledger, SUM(Amount) as total_amount FROM vw_mutaties WHERE {where_clause} GROUP BY Parent, ledger ORDER BY Parent, ledger"
        
        with service.get_cursor() as cursor:
            cursor.execute(query, params)
            results = cursor.fetchall()
        
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/available-<data_type>', methods=['GET'])
def get_available_data(data_type):
    """Get available years or references from vw_mutaties"""
    queries = {
        'years': "SELECT DISTINCT jaar as value FROM vw_mutaties WHERE jaar IS NOT NULL ORDER BY jaar DESC",
        'references': "SELECT DISTINCT ReferenceNumber as value FROM vw_mutaties WHERE ReferenceNumber IS NOT NULL AND ReferenceNumber != '' ORDER BY ReferenceNumber"
    }
    
    if data_type not in queries:
        return jsonify({'success': False, 'error': 'Invalid data type'}), 400
    
    try:
        service = ReportingService()
        with service.get_cursor() as cursor:
            cursor.execute(queries[data_type])
            values = [str(row['value']) for row in cursor.fetchall()]
        
        return jsonify({'success': True, data_type: values})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@reporting_bp.route('/check-reference', methods=['GET'])
def get_check_reference():
    """Get check reference data with transactions and summary"""
    try:
        service = ReportingService(request.args.get('testMode', 'false').lower() == 'true')
        reference_number = request.args.get('referenceNumber', 'all')
        administration = request.args.get('administration', 'all')
        ledger = request.args.get('ledger', 'all')
        
        with service.get_cursor() as cursor:
            # Build WHERE conditions manually for better control
            where_conditions = ["ReferenceNumber IS NOT NULL AND ReferenceNumber != ''"]
            params = []
            
            if administration != 'all':
                where_conditions.append("Administration = %s")
                params.append(administration)
            
            if ledger != 'all':
                # Extract just the account number (first part before space)
                account_num = ledger.split(' ')[0] if ' ' in ledger else ledger
                where_conditions.append("Reknum = %s")
                params.append(account_num)
            
            if reference_number != 'all':
                where_conditions.append("ReferenceNumber = %s")
                params.append(reference_number)
            
            where_clause = " AND ".join(where_conditions)
            
            # Get reference summary
            cursor.execute(f"""
                SELECT ReferenceNumber, COUNT(*) as transaction_count, SUM(Amount) as total_amount
                FROM vw_mutaties
                WHERE {where_clause}
                GROUP BY ReferenceNumber
                HAVING ABS(SUM(Amount)) > 0.01
                ORDER BY ABS(SUM(Amount)) DESC
            """, params)
            summary = cursor.fetchall()
            
            # Get detailed transactions if specific reference selected
            transactions = []
            if reference_number != 'all':
                cursor.execute(f"""
                    SELECT TransactionDate, TransactionNumber, TransactionDescription, Amount, Reknum, AccountName, Administration
                    FROM vw_mutaties
                    WHERE {where_clause}
                    ORDER BY TransactionDate DESC
                """, params)
                transactions = cursor.fetchall()
        
        return jsonify({'success': True, 'transactions': transactions, 'summary': summary})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/reference-analysis', methods=['GET'])
def get_reference_analysis():
    """Get reference analysis data with trend and available accounts"""
    try:
        service = ReportingService()
        years = [y for y in request.args.get('years', str(datetime.now().year)).split(',') if y]
        reference_number = request.args.get('reference_number', '')
        accounts = [a for a in request.args.get('accounts', '').split(',') if a]
        
        with service.get_cursor() as cursor:
            # Get available accounts
            account_conditions = {
                'years': years,
                'administration': request.args.get('administration', 'all')
            }
            account_where, account_params = service.build_where_clause(account_conditions)
            
            cursor.execute(f"""
                SELECT DISTINCT Reknum, AccountName FROM vw_mutaties
                WHERE {account_where} AND Reknum IS NOT NULL AND Reknum != ''
                      AND AccountName IS NOT NULL AND AccountName != ''
                ORDER BY Reknum
            """, account_params)
            available_accounts = cursor.fetchall()
            
            transactions = []
            trend_data = []
            
            if reference_number:
                conditions = {
                    'years': years,
                    'administration': request.args.get('administration', 'all')
                }
                where_clause, params = service.build_where_clause(conditions)
                
                # Add reference pattern and accounts
                where_clause += " AND ReferenceNumber REGEXP %s"
                params.append(reference_number)
                
                if accounts:
                    placeholders = ','.join(['%s'] * len(accounts))
                    where_clause += f" AND Reknum IN ({placeholders})"
                    params.extend(accounts)
                
                # Get transactions
                cursor.execute(f"""
                    SELECT TransactionDate, TransactionDescription, Amount, Reknum,
                           AccountName, ReferenceNumber, Administration
                    FROM vw_mutaties
                    WHERE {where_clause}
                    ORDER BY TransactionDate DESC
                """, params)
                transactions = cursor.fetchall()
                
                # Get trend data
                cursor.execute(f"""
                    SELECT jaar, kwartaal, SUM(Amount) as total_amount
                    FROM vw_mutaties
                    WHERE {where_clause}
                    GROUP BY jaar, kwartaal
                    ORDER BY jaar, kwartaal
                """, params)
                trend_data = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'transactions': transactions,
            'trend_data': trend_data,
            'available_accounts': available_accounts
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/bnb-filter-options', methods=['GET'])
def get_bnb_filter_options():
    """Get available filter options for BNB data"""
    try:
        service = ReportingService()
        with service.get_cursor() as cursor:
            # Get distinct years
            cursor.execute("SELECT DISTINCT year FROM bnb WHERE year IS NOT NULL ORDER BY year DESC")
            years = [str(row['year']) for row in cursor.fetchall()]
            
            # Get distinct listings
            cursor.execute("SELECT DISTINCT listing FROM bnb WHERE listing IS NOT NULL ORDER BY listing")
            listings = [row['listing'] for row in cursor.fetchall()]
            
            # Get distinct channels with normalization
            cursor.execute("""
                SELECT DISTINCT 
                    CASE 
                        WHEN LOWER(channel) = 'booking.com' THEN 'Booking.com'
                        WHEN LOWER(channel) = 'airbnb' THEN 'Airbnb'
                        ELSE channel 
                    END as channel 
                FROM bnb 
                WHERE channel IS NOT NULL 
                ORDER BY channel
            """)
            channels = [row['channel'] for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'years': years,
            'listings': listings,
            'channels': channels
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/bnb-listing-data', methods=['GET'])
def get_bnb_listing_data():
    """Get BNB data summarized by listing"""
    try:
        service = ReportingService()
        years = request.args.get('years', '').split(',')
        listings = request.args.get('listings', 'all')
        channels = request.args.get('channels', 'all')
        
        with service.get_cursor() as cursor:
            # Build WHERE clause
            where_conditions = []
            params = []
            
            if years and years != ['']:
                placeholders = ','.join(['%s'] * len(years))
                where_conditions.append(f"year IN ({placeholders})")
                params.extend(years)
            
            if listings != 'all':
                listing_list = listings.split(',')
                placeholders = ','.join(['%s'] * len(listing_list))
                where_conditions.append(f"listing IN ({placeholders})")
                params.extend(listing_list)
                
            if channels != 'all':
                channel_list = channels.split(',')
                placeholders = ','.join(['%s'] * len(channel_list))
                where_conditions.append(f"channel IN ({placeholders})")
                params.extend(channel_list)
            
            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            query = f"""
            SELECT listing, year, q, m,
                   SUM(amountGross) as amountGross,
                   SUM(amountNett) as amountNett,
                   SUM(amountChannelFee) as amountChannelFee,
                   SUM(amountTouristTax) as amountTouristTax,
                   SUM(amountVat) as amountVat
            FROM bnb 
            {where_clause}
            GROUP BY listing, year, q, m
            ORDER BY year, q, m, listing
            """
            
            cursor.execute(query, params)
            results = cursor.fetchall()
        
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@reporting_bp.route('/bnb-channel-data', methods=['GET'])
def get_bnb_channel_data():
    """Get BNB data summarized by channel"""
    try:
        service = ReportingService()
        years = request.args.get('years', '').split(',')
        listings = request.args.get('listings', 'all')
        channels = request.args.get('channels', 'all')
        
        with service.get_cursor() as cursor:
            # Build WHERE clause
            where_conditions = []
            params = []
            
            if years and years != ['']:
                placeholders = ','.join(['%s'] * len(years))
                where_conditions.append(f"year IN ({placeholders})")
                params.extend(years)
            
            if listings != 'all':
                listing_list = listings.split(',')
                placeholders = ','.join(['%s'] * len(listing_list))
                where_conditions.append(f"listing IN ({placeholders})")
                params.extend(listing_list)
                
            if channels != 'all':
                channel_list = channels.split(',')
                placeholders = ','.join(['%s'] * len(channel_list))
                where_conditions.append(f"channel IN ({placeholders})")
                params.extend(channel_list)
            
            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            query = f"""
            SELECT CASE 
                       WHEN LOWER(channel) = 'booking.com' THEN 'Booking.com'
                       WHEN LOWER(channel) = 'airbnb' THEN 'Airbnb'
                       ELSE channel 
                   END as channel, year, q, m,
                   SUM(amountGross) as amountGross,
                   SUM(amountNett) as amountNett,
                   SUM(amountChannelFee) as amountChannelFee,
                   SUM(amountTouristTax) as amountTouristTax,
                   SUM(amountVat) as amountVat
            FROM bnb 
            {where_clause}
            GROUP BY channel, year, q, m
            ORDER BY year, q, m, channel
            """
            
            cursor.execute(query, params)
            results = cursor.fetchall()
        
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500