"""
STR Channel Revenue Routes
Handles monthly STR channel revenue calculations based on account 1600 transactions
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import calendar
from database import DatabaseManager
import logging

str_channel_bp = Blueprint('str_channel', __name__)

@str_channel_bp.route('/calculate', methods=['POST'])
def calculate_str_channel_revenue():
    """Calculate STR channel revenue for a specific month and year"""
    try:
        data = request.get_json()
        year = data.get('year', datetime.now().year)
        month = data.get('month', datetime.now().month)
        administration = data.get('administration', 'GoodwinSolutions')
        test_mode = data.get('test_mode', True)
        
        # Calculate last day of month
        last_day = calendar.monthrange(year, month)[1]
        end_date = f"{year}-{month:02d}-{last_day}"
        
        # Reference number for transactions
        ref1 = f"BnB {year}{month:02d}"
        
        # Pattern for STR channels
        pattern = "AirBnB|Booking.com|dfDirect|Stripe|VRBO"
        
        # Get database connection
        db = DatabaseManager(test_mode=test_mode)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Query to get channel revenue data
        query = """
        SELECT 
            Administration,
            CASE 
                WHEN ReferenceNumber LIKE '%AIRBNB%' THEN 'AirBnB'
                ELSE ReferenceNumber
            END as ReferenceNumber,
            Reknum,
            SUM(Amount) as TransactionAmount
        FROM vw_mutaties 
        WHERE TransactionDate <= %s
        AND Administration LIKE %s
        AND Reknum LIKE '1600%'
        AND (ReferenceNumber REGEXP %s)
        GROUP BY Administration, 
                 CASE 
                     WHEN ReferenceNumber LIKE '%AIRBNB%' THEN 'AirBnB'
                     ELSE ReferenceNumber
                 END,
                 Reknum
        HAVING ABS(SUM(Amount)) > 0.01
        """
        
        cursor.execute(query, (end_date, f"%{administration}%", pattern))
        channel_data = cursor.fetchall()
        
        # Process the data to create transactions
        transactions = []
        
        for row in channel_data:
            amount = round(float(row['TransactionAmount']) * -1, 2)  # Reverse sign
            if amount == 0:
                continue
                
            # Main revenue transaction
            revenue_transaction = {
                'TransactionDate': end_date,
                'TransactionNumber': f"{row['ReferenceNumber']} {end_date}",
                'TransactionDescription': f"{row['ReferenceNumber']} omzet {end_date}",
                'TransactionAmount': amount,
                'Debet': row['Reknum'],
                'Credit': '8003',
                'ReferenceNumber': row['ReferenceNumber'],
                'Ref1': ref1,
                'Ref2': '',
                'Ref3': '',
                'Ref4': '',
                'Administration': row['Administration']
            }
            transactions.append(revenue_transaction)
            
            # VAT transaction (9% of revenue / 109 * 9)
            vat_amount = round((amount / 109) * 9, 2)
            vat_transaction = {
                'TransactionDate': end_date,
                'TransactionNumber': f"{row['ReferenceNumber']} {end_date}",
                'TransactionDescription': f"{row['ReferenceNumber']} Btw {end_date}",
                'TransactionAmount': vat_amount,
                'Debet': '8003',
                'Credit': '2021',
                'ReferenceNumber': row['ReferenceNumber'],
                'Ref1': ref1,
                'Ref2': '',
                'Ref3': '',
                'Ref4': '',
                'Administration': row['Administration']
            }
            transactions.append(vat_transaction)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'transactions': transactions,
            'summary': {
                'year': year,
                'month': month,
                'administration': administration,
                'end_date': end_date,
                'ref1': ref1,
                'transaction_count': len(transactions)
            }
        })
        
    except Exception as e:
        logging.error(f"Error calculating STR channel revenue: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@str_channel_bp.route('/save', methods=['POST'])
def save_str_channel_transactions():
    """Save STR channel revenue transactions to database"""
    try:
        data = request.get_json()
        transactions = data.get('transactions', [])
        test_mode = data.get('test_mode', True)
        
        if not transactions:
            return jsonify({'success': False, 'error': 'No transactions to save'}), 400
        
        # Get database connection
        table_name = 'mutaties_test' if test_mode else 'mutaties'
        
        db = DatabaseManager(test_mode=test_mode)
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Insert transactions
        insert_query = f"""
        INSERT INTO {table_name} 
        (TransactionDate, TransactionNumber, TransactionDescription, TransactionAmount,
         Debet, Credit, ReferenceNumber, Ref1, Ref2, Ref3, Ref4, Administration)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        saved_count = 0
        for transaction in transactions:
            cursor.execute(insert_query, (
                transaction['TransactionDate'],
                transaction['TransactionNumber'],
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
            saved_count += 1
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'saved_count': saved_count,
            'table': table_name
        })
        
    except Exception as e:
        logging.error(f"Error saving STR channel transactions: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@str_channel_bp.route('/preview', methods=['GET'])
def preview_str_channel_data():
    """Preview STR channel data for a specific month"""
    try:
        year = int(request.args.get('year', datetime.now().year))
        month = int(request.args.get('month', datetime.now().month))
        administration = request.args.get('administration', 'GoodwinSolutions')
        test_mode = request.args.get('test_mode', 'true').lower() == 'true'
        
        # Calculate last day of month
        last_day = calendar.monthrange(year, month)[1]
        end_date = f"{year}-{month:02d}-{last_day}"
        
        # Pattern for STR channels
        pattern = "AirBnB|Booking.com|dfDirect|Stripe|VRBO"
        
        # Get database connection
        db = DatabaseManager(test_mode=test_mode)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Query to get raw channel data
        query = """
        SELECT 
            Administration,
            ReferenceNumber,
            Reknum,
            COUNT(*) as transaction_count,
            SUM(Amount) as total_amount,
            MIN(TransactionDate) as first_date,
            MAX(TransactionDate) as last_date
        FROM vw_mutaties 
        WHERE TransactionDate <= %s
        AND Administration LIKE %s
        AND Reknum LIKE '1600%'
        AND (ReferenceNumber REGEXP %s)
        GROUP BY Administration, ReferenceNumber, Reknum
        HAVING ABS(SUM(Amount)) > 0.01
        ORDER BY Administration, ReferenceNumber
        """
        
        cursor.execute(query, (end_date, f"%{administration}%", pattern))
        preview_data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'preview_data': preview_data,
            'summary': {
                'year': year,
                'month': month,
                'administration': administration,
                'end_date': end_date,
                'channels_found': len(preview_data)
            }
        })
        
    except Exception as e:
        logging.error(f"Error previewing STR channel data: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500