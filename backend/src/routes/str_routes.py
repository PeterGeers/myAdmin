"""
STR (Short-Term Rental) Routes Blueprint

Handles all STR and pricing endpoints including:
- STR file upload and processing
- Booking data saving (realized/planned)
- Pricing recommendations and generation
- Historical pricing data

Extracted from app.py during refactoring (Phase 4.1)
"""

from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from str_processor import STRProcessor
from str_database import STRDatabase
from database import DatabaseManager
import os

# Create blueprint
str_bp = Blueprint('str', __name__)

# Configuration (will be set by set_config)
UPLOAD_FOLDER = 'uploads'
test_mode = False


def set_config(upload_folder, flag):
    """Set configuration for STR routes"""
    global UPLOAD_FOLDER, test_mode
    UPLOAD_FOLDER = upload_folder
    test_mode = flag


@str_bp.route('/api/str/upload', methods=['POST', 'OPTIONS'])
@cognito_required(required_permissions=['str_create'])
@tenant_required()
def str_upload(user_email, user_roles, tenant, user_tenants):
    """Upload and process single STR file"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'})
        
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        platform = request.form.get('platform', 'airbnb')
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        filename = secure_filename(file.filename)
        temp_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(temp_path)
        
        str_processor = STRProcessor(test_mode=test_mode)
        
        bookings = str_processor.process_str_files([temp_path], platform)
        
        # Add administration (tenant) to all bookings
        if bookings:
            for booking in bookings:
                booking['administration'] = tenant
        
        if bookings:
            separated = str_processor.separate_by_status(bookings)
            summary = str_processor.generate_summary(bookings)
        else:
            separated = {'realised': [], 'planned': []}
            summary = {}
        
        os.remove(temp_path)  # Clean up
        
        # Convert numpy types to native Python types for JSON serialization
        def convert_types(obj):
            if hasattr(obj, 'item'):
                return obj.item()
            elif isinstance(obj, dict):
                return {k: convert_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_types(v) for v in obj]
            return obj
        
        response_data = {
            'success': True,
            'realised': convert_types(separated['realised']),
            'planned': convert_types(separated['planned']),
            'already_loaded': convert_types(separated.get('already_loaded', [])),
            'summary': convert_types(summary),
            'platform': platform,
            'administration': tenant
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@str_bp.route('/api/str/save', methods=['POST'])
@cognito_required(required_permissions=['bookings_create'])
@tenant_required()
def str_save(user_email, user_roles, tenant, user_tenants):
    """Save STR bookings to database like R script"""
    try:
        data = request.get_json()
        realised_bookings = data.get('realised', [])
        planned_bookings = data.get('planned', [])
        
        # Add administration (tenant) to all bookings
        for booking in realised_bookings:
            booking['administration'] = tenant
        for booking in planned_bookings:
            booking['administration'] = tenant
        
        str_db = STRDatabase(test_mode=test_mode)
        str_processor = STRProcessor(test_mode=test_mode)
        
        results = {}
        
        # Save realised bookings to bnb table
        if realised_bookings:
            realised_count = str_db.insert_realised_bookings(realised_bookings)
            results['realised_saved'] = realised_count
        
        # Save planned bookings to bnbplanned table (clears table first)
        planned_count = str_db.insert_planned_bookings(planned_bookings)
        results['planned_saved'] = planned_count
        
        # Generate and save future summary to bnbfuture table
        if planned_bookings:
            future_summary = str_processor.generate_future_summary(planned_bookings)
            future_count = str_db.insert_future_summary(future_summary)
            results['future_summary_saved'] = future_count
        
        return jsonify({
            'success': True,
            'results': results,
            'message': f'Processed {len(realised_bookings)} realised, {len(planned_bookings)} planned bookings for {tenant}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Pricing routes
@str_bp.route('/api/pricing/generate', methods=['POST'])
@cognito_required(required_permissions=['str_update'])
def pricing_generate(user_email, user_roles):
    """Generate pricing recommendations using hybrid optimizer"""
    try:
        from hybrid_pricing_optimizer import HybridPricingOptimizer
        from datetime import datetime
        
        data = request.get_json()
        months = data.get('months', 14)
        listing = data.get('listing')
        
        optimizer = HybridPricingOptimizer(test_mode=test_mode)
        result = optimizer.generate_pricing_strategy(months, listing)
        
        return jsonify({
            'success': True,
            'result': result,
            'listing': listing,
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@str_bp.route('/api/pricing/recommendations', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def pricing_recommendations(user_email, user_roles):
    """Get pricing recommendations with historical comparison"""
    try:
        db = DatabaseManager(test_mode=test_mode)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get all recommendations with historical data and multipliers
        query = """
        SELECT listing_name, price_date, recommended_price, ai_recommended_adr, 
               ai_historical_adr, ai_variance, ai_reasoning, is_weekend, 
               event_uplift, event_name, last_year_adr, generated_at,
               base_rate, historical_mult, occupancy_mult, pace_mult, 
               event_mult, ai_correction, btw_adjustment
        FROM pricing_recommendations 
        WHERE price_date >= CURDATE()
        ORDER BY listing_name, price_date
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        # Convert dates to strings and Decimals to floats
        for result in results:
            result['price_date'] = str(result['price_date'])
            if result['generated_at']:
                result['generated_at'] = str(result['generated_at'])
            # Convert Decimal fields to float
            decimal_fields = ['recommended_price', 'ai_recommended_adr', 'ai_historical_adr', 
                            'ai_variance', 'last_year_adr', 'base_rate', 'historical_mult',
                            'occupancy_mult', 'pace_mult', 'event_mult', 'ai_correction', 'btw_adjustment']
            for field in decimal_fields:
                if result.get(field) is not None:
                    result[field] = float(result[field])
        
        return jsonify({
            'success': True,
            'recommendations': results,
            'count': len(results)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


@str_bp.route('/api/pricing/historical', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def pricing_historical(user_email, user_roles):
    """Get historical ADR data for trend analysis"""
    try:
        db = DatabaseManager(test_mode=test_mode)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get monthly historical ADR data with guest fee adjustment for Child Friendly
        query = """
        SELECT 
            listing,
            YEAR(checkinDate) as year,
            MONTH(checkinDate) as month,
            COUNT(*) as bookings,
            AVG(
                CASE 
                    WHEN listing = 'Child Friendly' AND guests > 2 
                    THEN (amountGross - (guests - 2) * 30) / nights
                    ELSE amountGross / nights
                END
            ) as historical_adr
        FROM bnb 
        WHERE checkinDate >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
        AND nights > 0
        GROUP BY listing, YEAR(checkinDate), MONTH(checkinDate)
        ORDER BY listing, year, month
        """
        
        cursor.execute(query)
        historical_data = cursor.fetchall()
        
        # Convert Decimal to float for historical data
        for row in historical_data:
            if row['historical_adr']:
                row['historical_adr'] = float(row['historical_adr'])
        
        # Get recommended ADR data by month
        rec_query = """
        SELECT 
            listing_name,
            YEAR(price_date) as year,
            MONTH(price_date) as month,
            AVG(recommended_price) as recommended_adr
        FROM pricing_recommendations 
        GROUP BY listing_name, YEAR(price_date), MONTH(price_date)
        ORDER BY listing_name, year, month
        """
        
        cursor.execute(rec_query)
        recommended_data = cursor.fetchall()
        
        # Convert Decimal to float for recommended data
        for row in recommended_data:
            if row['recommended_adr']:
                row['recommended_adr'] = float(row['recommended_adr'])
        
        return jsonify({
            'success': True,
            'historical': historical_data,
            'recommended': recommended_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


@str_bp.route('/api/pricing/listings', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def pricing_listings(user_email, user_roles):
    """Get available listings for pricing"""
    try:
        db = DatabaseManager(test_mode=test_mode)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT listing_name, active FROM listings WHERE active = TRUE ORDER BY listing_name"
        cursor.execute(query)
        listings = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'listings': [listing['listing_name'] for listing in listings]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


@str_bp.route('/api/pricing/multipliers', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def pricing_multipliers(user_email, user_roles):
    """Get pricing multipliers breakdown"""
    try:
        db = DatabaseManager(test_mode=test_mode)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        listing = request.args.get('listing')
        
        if not listing:
            return jsonify({'success': False, 'error': 'Listing parameter required'}), 400
        
        query = """
        SELECT price_date, listing_name, recommended_price,
               base_rate, historical_mult, occupancy_mult, pace_mult,
               event_mult, ai_correction, btw_adjustment,
               is_weekend, event_name
        FROM pricing_recommendations
        WHERE listing_name = %s
        AND price_date >= CURDATE()
        ORDER BY price_date
        """
        
        cursor.execute(query, (listing,))
        results = cursor.fetchall()
        
        # Convert dates and decimals
        for result in results:
            result['price_date'] = str(result['price_date'])
            decimal_fields = ['recommended_price', 'base_rate', 'historical_mult',
                            'occupancy_mult', 'pace_mult', 'event_mult', 
                            'ai_correction', 'btw_adjustment']
            for field in decimal_fields:
                if result.get(field) is not None:
                    result[field] = float(result[field])
        
        return jsonify({
            'success': True,
            'multipliers': results,
            'listing': listing
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


@str_bp.route('/api/str/write-future', methods=['POST'])
@cognito_required(required_permissions=['bookings_create'])
def str_write_future(user_email, user_roles):
    """Write current BNB planned data to bnbfuture table"""
    try:
        str_db = STRDatabase(test_mode=test_mode)
        result = str_db.write_bnb_future_summary()
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f"Written {result['inserted']} future records for {result['date']}",
                'summary': result['summary']
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', result.get('message', 'Unknown error'))
            }), 400
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@str_bp.route('/api/str/import-payout', methods=['POST', 'OPTIONS'])
@cognito_required(required_permissions=['str_create'])
def str_import_payout(user_email, user_roles):
    """
    Import Booking.com Payout CSV to update financial figures
    
    This endpoint processes monthly Payout CSV files from Booking.com
    and updates existing bookings with actual settlement data.
    """
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'})
    
    try:
        print("=== PAYOUT CSV IMPORT START ===", flush=True)
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        # Validate filename pattern (Payout_from_*.csv)
        if not file.filename.lower().startswith('payout_from') or not file.filename.lower().endswith('.csv'):
            return jsonify({
                'success': False, 
                'error': 'Invalid file format. Expected: Payout_from_YYYY-MM-DD_until_YYYY-MM-DD.csv'
            }), 400
        
        filename = secure_filename(file.filename)
        temp_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(temp_path)
        
        print(f"Processing Payout CSV: {filename}", flush=True)
        
        # Process the Payout CSV file
        str_processor = STRProcessor(test_mode=test_mode)
        payout_result = str_processor._process_booking_payout(temp_path)
        
        if payout_result.get('errors'):
            print(f"Payout processing errors: {payout_result['errors']}", flush=True)
        
        # Update database with payout data
        str_db = STRDatabase(test_mode=test_mode)
        update_result = str_db.update_from_payout(payout_result.get('updates', []))
        
        # Clean up temp file
        os.remove(temp_path)
        
        # Combine results
        response = {
            'success': True,
            'message': f"Payout CSV processed successfully",
            'processing': {
                'total_rows': payout_result['summary']['total_rows'],
                'reservation_rows': payout_result['summary']['reservation_rows'],
                'updates_prepared': payout_result['summary']['updated_count'],
                'processing_errors': payout_result['summary']['error_count']
            },
            'database': {
                'updated': update_result['updated'],
                'not_found': update_result['not_found'],
                'errors': update_result.get('errors', [])
            },
            'summary': {
                'total_updated': update_result['updated'],
                'total_not_found': len(update_result['not_found']),
                'total_errors': len(update_result.get('errors', []))
            }
        }
        
        print(f"Payout import completed: {update_result['updated']} bookings updated", flush=True)
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in Payout import: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@str_bp.route('/api/str/summary', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def str_summary(user_email, user_roles):
    """Get STR performance summary"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        str_db = STRDatabase(test_mode=test_mode)
        summary = str_db.get_str_summary(start_date, end_date)
        
        return jsonify({
            'success': True,
            'summary': summary
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@str_bp.route('/api/str/future-trend', methods=['GET'])
@cognito_required(required_permissions=['str_read'])
def str_future_trend(user_email, user_roles):
    """Get BNB future revenue trend data"""
    try:
        db = DatabaseManager(test_mode=test_mode)
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
        SELECT date, channel, listing, amount, items
        FROM bnbfuture
        ORDER BY date, listing, channel
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        # Convert dates and decimals
        for row in results:
            if row['date']:
                row['date'] = str(row['date'])
            if row['amount']:
                row['amount'] = float(row['amount'])
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
