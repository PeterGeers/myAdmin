"""
STR Channel Revenue Routes
Handles monthly STR channel revenue calculations based on account 1600 transactions
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import calendar
from database import DatabaseManager
import logging
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required

str_channel_bp = Blueprint('str_channel', __name__)

@str_channel_bp.route('/calculate', methods=['POST'])
@cognito_required(required_permissions=['str_read'])
@tenant_required()
def calculate_str_channel_revenue(user_email, user_roles, tenant, user_tenants):
    """Calculate STR channel revenue for a specific month and year"""
    try:
        data = request.get_json()
        year = data.get('year', datetime.now().year)
        month = data.get('month', datetime.now().month)
        administration = data.get('administration', tenant)  # Default to current tenant
        test_mode = data.get('test_mode', True)
        
        # Validate user has access to requested administration
        if administration not in user_tenants:
            return jsonify({'success': False, 'error': 'Access denied to administration'}), 403
        
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
        
        # Query to get channel revenue data - EXACT match on administration
        query = """
        SELECT 
            administration,
            CASE 
                WHEN ReferenceNumber LIKE '%AIRBNB%' THEN 'AirBnB'
                ELSE ReferenceNumber
            END as ReferenceNumber,
            Reknum,
            SUM(Amount) as TransactionAmount
        FROM vw_mutaties 
        WHERE TransactionDate <= %s
        AND administration = %s
        AND Reknum LIKE '1600%'
        AND (ReferenceNumber REGEXP %s)
        GROUP BY administration, 
                 CASE 
                     WHEN ReferenceNumber LIKE '%AIRBNB%' THEN 'AirBnB'
                     ELSE ReferenceNumber
                 END,
                 Reknum
        HAVING ABS(SUM(Amount)) > 0.01
        """
        
        cursor.execute(query, (end_date, administration, pattern))
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
                'administration': row['administration']
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
                'administration': row['administration']
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
@cognito_required(required_permissions=['bookings_create'])
def save_str_channel_transactions(user_email, user_roles):
    """Save STR channel revenue transactions to database"""
    try:
        data = request.get_json()
        transactions = data.get('transactions', [])
        test_mode = data.get('test_mode', True)
        
        if not transactions:
            return jsonify({'success': False, 'error': 'No transactions to save'}), 400
        
        # Get database connection and determine correct table
        db = DatabaseManager(test_mode=test_mode)
        
        # Use mutaties table in both test and production databases
        # Test mode uses testfinance.mutaties, production uses finance.mutaties
        table_name = 'mutaties'
        
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
@cognito_required(required_permissions=['str_read'])
@tenant_required()
def preview_str_channel_data(user_email, user_roles, tenant, user_tenants):
    """Preview STR channel data for a specific month"""
    try:
        year = int(request.args.get('year', datetime.now().year))
        month = int(request.args.get('month', datetime.now().month))
        administration = request.args.get('administration', tenant)  # Default to current tenant
        test_mode = request.args.get('test_mode', 'true').lower() == 'true'
        
        # Validate user has access to requested administration
        if administration not in user_tenants:
            return jsonify({'success': False, 'error': 'Access denied to administration'}), 403
        
        # Calculate last day of month
        last_day = calendar.monthrange(year, month)[1]
        end_date = f"{year}-{month:02d}-{last_day}"
        
        # Pattern for STR channels
        pattern = "AirBnB|Booking.com|dfDirect|Stripe|VRBO"
        
        # Get database connection
        db = DatabaseManager(test_mode=test_mode)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Query to get raw channel data - EXACT match on administration
        query = """
        SELECT 
            administration,
            ReferenceNumber,
            Reknum,
            COUNT(*) as transaction_count,
            SUM(Amount) as total_amount,
            MIN(TransactionDate) as first_date,
            MAX(TransactionDate) as last_date
        FROM vw_mutaties 
        WHERE TransactionDate <= %s
        AND administration = %s
        AND Reknum LIKE '1600%'
        AND (ReferenceNumber REGEXP %s)
        GROUP BY administration, ReferenceNumber, Reknum
        HAVING ABS(SUM(Amount)) > 0.01
        ORDER BY administration, ReferenceNumber
        """
        
        cursor.execute(query, (end_date, administration, pattern))
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