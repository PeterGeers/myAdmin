from flask import Blueprint, request, jsonify
from database import DatabaseManager
import numpy as np
from collections import defaultdict

bnb_bp = Blueprint('bnb', __name__)

@bnb_bp.route('/bnb-listing-data', methods=['GET'])
def get_bnb_listing_data():
    """Get BNB data summarized by listing"""
    try:
        years = request.args.get('years', '').split(',')
        listings = request.args.get('listings', 'all')
        channels = request.args.get('channels', 'all')
        period = request.args.get('period', 'year')  # year, q, m
        
        db = DatabaseManager(test_mode=False)
        connection = db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
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
        
        # Always include q and m fields for frontend expandable functionality
        group_fields = ["listing", "year", "q", "m"]
        select_fields = ["listing", "year", "q", "m"]
        
        query = f"""
        SELECT {', '.join(select_fields)},
               SUM(amountGross) as amountGross,
               SUM(amountNett) as amountNett,
               SUM(amountChannelFee) as amountChannelFee,
               SUM(amountTouristTax) as amountTouristTax,
               SUM(amountVat) as amountVat
        FROM bnb 
        {where_clause}
        GROUP BY {', '.join(group_fields)}
        ORDER BY year, q, m, listing
        """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({'success': True, 'data': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bnb_bp.route('/bnb-channel-data', methods=['GET'])
def get_bnb_channel_data():
    """Get BNB data summarized by channel"""
    try:
        years = request.args.get('years', '').split(',')
        listings = request.args.get('listings', 'all')
        channels = request.args.get('channels', 'all')
        period = request.args.get('period', 'year')  # year, q, m
        
        db = DatabaseManager(test_mode=False)
        connection = db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
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
        
        # Always include q and m fields for frontend expandable functionality
        group_fields = ["channel", "year", "q", "m"]
        select_fields = ["channel", "year", "q", "m"]
        
        query = f"""
        SELECT {', '.join(select_fields)},
               SUM(amountGross) as amountGross,
               SUM(amountNett) as amountNett,
               SUM(amountChannelFee) as amountChannelFee,
               SUM(amountTouristTax) as amountTouristTax,
               SUM(amountVat) as amountVat
        FROM bnb 
        {where_clause}
        GROUP BY {', '.join(group_fields)}
        ORDER BY year, q, m, channel
        """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({'success': True, 'data': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bnb_bp.route('/bnb-actuals', methods=['GET'])
def get_bnb_actuals():
    """Get BNB actuals data"""
    try:
        years = request.args.get('years', '').split(',')
        administration = request.args.get('administration', 'all')
        
        db = DatabaseManager(test_mode=False)
        connection = db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        where_conditions = []
        params = []
        
        if years and years != ['']:
            placeholders = ','.join(['%s'] * len(years))
            where_conditions.append(f"year IN ({placeholders})")
            params.extend(years)
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        query = f"""
            SELECT year, SUM(amountNett) as total_amount
            FROM bnb 
            {where_clause}
            GROUP BY year
            ORDER BY year
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
        return jsonify({'success': False, 'error': str(e)}), 500

@bnb_bp.route('/bnb-filter-options', methods=['GET'])
def get_bnb_filter_options():
    """Get available filter options for BNB data"""
    try:
        db = DatabaseManager(test_mode=False)
        connection = db.get_connection()
        cursor = connection.cursor()
        
        # Get distinct years
        cursor.execute("SELECT DISTINCT year FROM bnb WHERE year IS NOT NULL ORDER BY year DESC")
        years = [str(row[0]) for row in cursor.fetchall()]
        
        # Get distinct listings
        cursor.execute("SELECT DISTINCT listing FROM bnb WHERE listing IS NOT NULL ORDER BY listing")
        listings = [row[0] for row in cursor.fetchall()]
        
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
        channels = [row[0] for row in cursor.fetchall()]
        
        cursor.close()
        connection.close()
        
        return jsonify({
            'success': True,
            'years': years,
            'listings': listings,
            'channels': channels
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bnb_bp.route('/bnb-violin-data', methods=['GET'])
def get_bnb_violin_data():
    """Get BNB data for violin plots"""
    try:
        years = request.args.get('years', '').split(',')
        listings = request.args.get('listings', 'all')
        channels = request.args.get('channels', 'all')
        metric = request.args.get('metric', 'pricePerNight')  # 'pricePerNight' or 'nightsPerStay'
        
        db = DatabaseManager(test_mode=False)
        connection = db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
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
        
        # Select appropriate metric with normalized channel names
        if metric == 'pricePerNight':
            # Calculate price per night (amountGross / nights)
            query = f"""
            SELECT listing, 
                   CASE 
                       WHEN LOWER(channel) = 'booking.com' THEN 'Booking.com'
                       WHEN LOWER(channel) = 'airbnb' THEN 'Airbnb'
                       ELSE channel 
                   END as channel, 
                   year,
                   CASE WHEN nights > 0 THEN amountGross / nights ELSE 0 END as value
            FROM bnb 
            {where_clause} AND nights > 0
            ORDER BY listing, channel, year
            """
        else:  # nightsPerStay
            query = f"""
            SELECT listing, 
                   CASE 
                       WHEN LOWER(channel) = 'booking.com' THEN 'Booking.com'
                       WHEN LOWER(channel) = 'airbnb' THEN 'Airbnb'
                       ELSE channel 
                   END as channel, 
                   year, 
                   nights as value
            FROM bnb 
            {where_clause} AND nights > 0
            ORDER BY listing, channel, year
            """
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({'success': True, 'data': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bnb_bp.route('/bnb-returning-guests', methods=['GET'])
def get_bnb_returning_guests():
    """Get returning guests summary"""
    try:
        db = DatabaseManager(test_mode=False)
        connection = db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Get guest summary with booking count > 1
        query = """
            SELECT guestName, COUNT(*) as aantal
            FROM bnb 
            WHERE guestName IS NOT NULL AND guestName != ''
            GROUP BY guestName
            HAVING COUNT(*) > 1
            ORDER BY aantal DESC, guestName ASC
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({'success': True, 'data': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bnb_bp.route('/bnb-guest-bookings', methods=['GET'])
def get_bnb_guest_bookings():
    """Get all bookings for a specific guest"""
    try:
        guest_name = request.args.get('guestName')
        if not guest_name:
            return jsonify({'success': False, 'error': 'Guest name required'}), 400
        
        db = DatabaseManager(test_mode=False)
        connection = db.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        query = """
            SELECT checkinDate, checkoutDate, channel, listing, nights, 
                   amountGross, amountNett, reservationCode
            FROM bnb 
            WHERE guestName = %s
            ORDER BY checkinDate DESC
        """
        
        cursor.execute(query, [guest_name])
        results = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        return jsonify({'success': True, 'data': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500