from flask import Blueprint, request, jsonify
from database import DatabaseManager
from datetime import datetime

reporting_bp = Blueprint('reporting', __name__)

class ReportingService:
    def __init__(self, test_mode=False):
        self.db = DatabaseManager(test_mode=test_mode)
        self.table_name = 'mutaties_test' if test_mode else 'mutaties'
    
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
        date_from = request.args.get('dateFrom', datetime.now().strftime('%Y-01-01'))
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        
        service = ReportingService(test_mode=test_mode)
        connection = service.db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        query = f"""
            SELECT 
                Debet as account,
                SUM(TransactionAmount) as debet_total,
                COUNT(*) as debet_count
            FROM vw_mutaties
            WHERE TransactionDate BETWEEN %s AND %s 
                AND Debet IS NOT NULL AND Debet != ''
            GROUP BY Debet
            
            UNION ALL
            
            SELECT 
                Credit as account,
                -SUM(TransactionAmount) as credit_total,
                COUNT(*) as credit_count
            FROM vw_mutaties
            WHERE TransactionDate BETWEEN %s AND %s 
                AND Credit IS NOT NULL AND Credit != ''
            GROUP BY Credit
            
            ORDER BY ABS(debet_total) DESC
        """
        
        cursor.execute(query, [date_from, date_to, date_from, date_to])
        results = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@reporting_bp.route('/mutaties-table', methods=['GET'])
def get_mutaties_table():
    """Get mutaties table data with PowerBI-style filters"""
    try:
        print(f"Mutaties table request received", flush=True)
        date_from = request.args.get('dateFrom', datetime.now().strftime('%Y-01-01'))
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        administration = request.args.get('administration', 'all')
        profit_loss = request.args.get('profitLoss', 'all')
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        
        service = ReportingService(test_mode=test_mode)
        connection = service.db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        where_conditions = ["TransactionDate BETWEEN %s AND %s"]
        params = [date_from, date_to]
        
        if administration != 'all':
            where_conditions.append("Administration = %s")
            params.append(administration)
        
        if profit_loss == 'Y':
            where_conditions.append("VW = 'Y'")
        elif profit_loss == 'N':
            where_conditions.append("VW = 'N'")
        
        where_clause = " AND ".join(where_conditions)
        
        query = """
            SELECT 
                TransactionDate,
                TransactionDescription,
                Amount,
                Reknum,
                AccountName,
                Administration,
                ReferenceNumber,
                VW
            FROM vw_mutaties
            WHERE """ + where_clause + """
            ORDER BY TransactionDate DESC
            LIMIT 1000
        """
        
        print(f"WHERE conditions: {where_conditions}", flush=True)
        print(f"WHERE clause: {where_clause}", flush=True)
        print(f"BNB Final query: {query}", flush=True)
        print(f"With params: {params}", flush=True)
        
        try:
            cursor.execute(query, tuple(params))
            results = cursor.fetchall()
            print(f"Query executed successfully, found {len(results)} records", flush=True)
            if results:
                print(f"Sample record: {results[0]}", flush=True)
        except Exception as db_error:
            print(f"Database error: {str(db_error)}", flush=True)
            cursor.close()
            connection.close()
            raise db_error
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@reporting_bp.route('/bnb-fields', methods=['GET'])
def get_bnb_fields():
    """Get field names of bnbtotal table"""
    try:
        service = ReportingService()
        connection = service.db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        cursor.execute("SHOW COLUMNS FROM bnbtotal")
        fields = cursor.fetchall()
        
        # Just return field names
        field_names = [str(row['Field']) for row in fields]
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'fields': field_names
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@reporting_bp.route('/mutaties-fields', methods=['GET'])
def get_mutaties_fields():
    """Get field names of vw_mutaties view"""
    try:
        service = ReportingService()
        connection = service.db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        cursor.execute("SHOW COLUMNS FROM vw_mutaties")
        fields = cursor.fetchall()
        
        # Just return field names
        field_names = [str(row['Field']) for row in fields]
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'fields': field_names
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@reporting_bp.route('/balance-data', methods=['GET'])
def get_balance_data():
    """Get balance data grouped by Parent and ledger"""
    try:
        date_from = request.args.get('dateFrom')
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        administration = request.args.get('administration', 'all')
        profit_loss = request.args.get('profitLoss', 'all')
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        
        service = ReportingService(test_mode=test_mode)
        connection = service.db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        where_conditions = []
        params = []
        
        # Add date range filtering
        if date_from:
            where_conditions.append("TransactionDate BETWEEN %s AND %s")
            params.extend([date_from, date_to])
        else:
            where_conditions.append("TransactionDate <= %s")
            params.append(date_to)
        
        if administration != 'all':
            where_conditions.append("Administration = %s")
            params.append(administration)
        
        if profit_loss == 'Y':
            where_conditions.append("VW = 'Y'")
        elif profit_loss == 'N':
            where_conditions.append("VW = 'N'")
        
        where_clause = " AND ".join(where_conditions)
        
        query = f"""
            SELECT 
                Parent,
                ledger,
                SUM(Amount) as total_amount
            FROM vw_mutaties
            WHERE {where_clause}
            GROUP BY Parent, ledger
            ORDER BY Parent, ledger
        """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@reporting_bp.route('/bnb-table', methods=['GET'])
def get_bnb_table():
    """Get BNB table data with PowerBI-style filters"""
    try:
        date_from = request.args.get('dateFrom', datetime.now().strftime('%Y-01-01'))
        date_to = request.args.get('dateTo', datetime.now().strftime('%Y-%m-%d'))
        channel = request.args.get('channel', 'all')
        listing = request.args.get('listing', 'all')
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        
        service = ReportingService(test_mode=test_mode)
        connection = service.db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        where_conditions = ["checkinDate BETWEEN %s AND %s"]
        params = [date_from, date_to]
        
        if channel != 'all':
            where_conditions.append("channel = %s")
            params.append(channel)
        
        if listing != 'all':
            where_conditions.append("listing = %s")
            params.append(listing)
        
        where_clause = " AND ".join(where_conditions)
        
        query = f"""
            SELECT 
                checkinDate,
                checkoutDate,
                channel,
                listing,
                nights,
                guests,
                amountGross,
                amountNett,
                guestName,
                reservationCode
            FROM bnbtotal
            WHERE {where_clause}
            ORDER BY checkinDate DESC
            LIMIT 1000
        """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        print(f"BNB query executed, found {len(results)} records", flush=True)
        if results:
            print(f"Sample BNB record keys: {list(results[0].keys())}", flush=True)
            print(f"Sample BNB record: {results[0]}", flush=True)
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@reporting_bp.route('/trends-data', methods=['GET'])
def get_trends_data():
    """Get P&L trends data by year"""
    try:
        years = request.args.get('years', str(datetime.now().year)).split(',')
        administration = request.args.get('administration', 'all')
        profit_loss = request.args.get('profitLoss', 'Y')
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        
        service = ReportingService(test_mode=test_mode)
        connection = service.db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        where_conditions = []
        params = []
        
        # Add year filtering
        year_conditions = []
        for year in years:
            year_conditions.append("YEAR(TransactionDate) = %s")
            params.append(int(year))
        
        if year_conditions:
            where_conditions.append(f"({' OR '.join(year_conditions)})")
        
        if administration != 'all':
            where_conditions.append("Administration = %s")
            params.append(administration)
        
        if profit_loss == 'Y':
            where_conditions.append("VW = 'Y'")
        elif profit_loss == 'N':
            where_conditions.append("VW = 'N'")
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        query = f"""
            SELECT 
                Parent,
                ledger,
                YEAR(TransactionDate) as year,
                SUM(Amount) as total_amount
            FROM vw_mutaties
            WHERE {where_clause}
            GROUP BY Parent, ledger, YEAR(TransactionDate)
            ORDER BY Parent, ledger, year
        """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@reporting_bp.route('/filter-options', methods=['GET'])
def get_filter_options():
    """Get all distinct combinations for filter dropdowns"""
    try:
        service = ReportingService()
        connection = service.db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        query = """
            SELECT DISTINCT Administration, ledger, ReferenceNumber
            FROM vw_mutaties
            WHERE Administration IS NOT NULL AND Administration != ''
                AND ledger IS NOT NULL AND ledger != ''
                AND ReferenceNumber IS NOT NULL AND ReferenceNumber != ''
            ORDER BY Administration, ledger, ReferenceNumber
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'combinations': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@reporting_bp.route('/check-reference', methods=['GET'])
def get_check_reference():
    """Get check reference data with transactions and summary"""
    try:
        reference_number = request.args.get('referenceNumber', 'all')
        ledger = request.args.get('ledger', 'all')
        administration = request.args.get('administration', 'all')
        test_mode = request.args.get('testMode', 'false').lower() == 'true'
        
        service = ReportingService(test_mode=test_mode)
        connection = service.db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        where_conditions = []
        params = []
        
        if administration != 'all':
            where_conditions.append("Administration = %s")
            params.append(administration)
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        # Get transactions
        transactions_query = f"""
            SELECT 
                TransactionDate,
                TransactionNumber,
                ReferenceNumber,
                Amount,
                TransactionDescription,
                ledger
            FROM vw_mutaties
            WHERE {where_clause}
            ORDER BY TransactionDate DESC
        """
        
        cursor.execute(transactions_query, params)
        transactions = cursor.fetchall()
        
        # Get reference summary
        summary_query = f"""
            SELECT 
                ReferenceNumber,
                ledger,
                SUM(Amount) as total_amount
            FROM vw_mutaties
            WHERE {where_clause}
            GROUP BY ReferenceNumber, ledger
            HAVING SUM(Amount) != 0
            ORDER BY ABS(SUM(Amount)) DESC
        """
        
        cursor.execute(summary_query, params)
        summary = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'transactions': transactions,
            'summary': summary
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500