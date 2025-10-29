from flask import Blueprint, request, jsonify
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

actuals_bp = Blueprint('actuals', __name__)

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'myadmin')
    )

@actuals_bp.route('/actuals-balance', methods=['GET'])
def get_actuals_balance():
    try:
        years = request.args.get('years', '2024').split(',')
        administration = request.args.get('administration', 'all')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build WHERE clause
        where_conditions = ["VW = 'N'"]
        params = []
        
        if administration != 'all':
            where_conditions.append("Administration = %s")
            params.append(administration)
            
        # Add year filter: from beginning up to max selected year
        max_year = max([int(y) for y in years])
        where_conditions.append("jaar <= %s")
        params.append(max_year)
            
        where_clause = " AND ".join(where_conditions)
        
        query = f"""
        SELECT 
            Parent,
            ledger,
            SUM(Amount) as Amount
        FROM vw_mutaties 
        WHERE {where_clause}
        GROUP BY Parent, ledger
        HAVING SUM(Amount) != 0
        ORDER BY Parent, ledger
        """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@actuals_bp.route('/actuals-profitloss', methods=['GET'])
def get_actuals_profitloss():
    try:
        years = request.args.get('years', '2024').split(',')
        administration = request.args.get('administration', 'all')
        group_by = request.args.get('groupBy', 'year')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build WHERE clause
        where_conditions = ["VW = 'Y'"]
        params = []
        
        if administration != 'all':
            where_conditions.append("Administration = %s")
            params.append(administration)
            
        # Add year filter
        year_placeholders = ','.join(['%s'] * len(years))
        where_conditions.append(f"jaar IN ({year_placeholders})")
        params.extend(years)
        
        # Build query based on groupBy parameter
        if group_by == 'quarter':
            where_conditions.append("kwartaal IS NOT NULL")
            where_clause = " AND ".join(where_conditions)
            query = f"""
            SELECT 
                Parent,
                ledger,
                jaar,
                kwartaal,
                SUM(Amount) as Amount
            FROM vw_mutaties 
            WHERE {where_clause}
            GROUP BY Parent, ledger, jaar, kwartaal
            HAVING SUM(Amount) != 0
            ORDER BY Parent, ledger, jaar, kwartaal
            """
        elif group_by == 'month':
            where_conditions.append("maand IS NOT NULL")
            where_clause = " AND ".join(where_conditions)
            query = f"""
            SELECT 
                Parent,
                ledger,
                jaar,
                maand,
                SUM(Amount) as Amount
            FROM vw_mutaties 
            WHERE {where_clause}
            GROUP BY Parent, ledger, jaar, maand
            HAVING SUM(Amount) != 0
            ORDER BY Parent, ledger, jaar, maand
            """
        else:  # Default to year
            where_clause = " AND ".join(where_conditions)
            query = f"""
            SELECT 
                Parent,
                ledger,
                jaar,
                SUM(Amount) as Amount
            FROM vw_mutaties 
            WHERE {where_clause}
            GROUP BY Parent, ledger, jaar
            HAVING SUM(Amount) != 0
            ORDER BY Parent, ledger, jaar
            """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

