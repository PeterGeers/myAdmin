"""
API Routes for Audit Logging System

Provides REST API endpoints for accessing audit logs, generating reports,
and managing audit data retention.

Requirements: 6.4, 6.5
"""

from flask import Blueprint, request, jsonify, send_file
from audit_logger import AuditLogger
from database import DatabaseManager
import logging
from datetime import datetime
import os
import tempfile
from auth.cognito_utils import cognito_required

# Configure logger
logger = logging.getLogger(__name__)

# Create Blueprint
audit_bp = Blueprint('audit', __name__, url_prefix='/api/audit')


def get_audit_logger():
    """Get an AuditLogger instance"""
    db = DatabaseManager()
    return AuditLogger(db)


@audit_bp.route('/logs', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def get_audit_logs(user_email, user_roles):
    """
    Get audit logs with optional filtering.
    
    Query Parameters:
        - reference_number: Filter by reference number (supports wildcards)
        - start_date: Filter by start date (YYYY-MM-DD)
        - end_date: Filter by end date (YYYY-MM-DD)
        - decision: Filter by decision type ('continue' or 'cancel')
        - user_id: Filter by user ID
        - limit: Maximum number of records (default: 100)
        - offset: Number of records to skip (default: 0)
    
    Returns:
        JSON response with audit log entries
    
    Requirements: 6.4, 6.5
    """
    try:
        # Get query parameters
        reference_number = request.args.get('reference_number')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        decision = request.args.get('decision')
        user_id = request.args.get('user_id')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        # Validate limit
        if limit > 1000:
            limit = 1000  # Cap at 1000 for performance
        
        # Get audit logger and query logs
        audit_logger = get_audit_logger()
        logs = audit_logger.query_logs(
            reference_number=reference_number,
            start_date=start_date,
            end_date=end_date,
            decision=decision,
            user_id=user_id,
            limit=limit,
            offset=offset
        )
        
        # Get total count for pagination
        total_count = audit_logger.get_decision_count(
            start_date=start_date,
            end_date=end_date,
            decision=decision
        )
        
        return jsonify({
            'success': True,
            'logs': logs,
            'pagination': {
                'limit': limit,
                'offset': offset,
                'total_count': total_count,
                'has_more': (offset + len(logs)) < total_count
            }
        }), 200
        
    except ValueError as e:
        logger.error(f"Invalid parameter in audit logs request: {e}")
        return jsonify({
            'success': False,
            'error': 'Invalid parameter value',
            'message': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Error retrieving audit logs: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve audit logs',
            'message': str(e)
        }), 500


@audit_bp.route('/logs/count', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def get_audit_log_count(user_email, user_roles):
    """
    Get count of audit log entries.
    
    Query Parameters:
        - start_date: Filter by start date (YYYY-MM-DD)
        - end_date: Filter by end date (YYYY-MM-DD)
        - decision: Filter by decision type ('continue' or 'cancel')
    
    Returns:
        JSON response with count
    
    Requirements: 6.4, 6.5
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        decision = request.args.get('decision')
        
        audit_logger = get_audit_logger()
        count = audit_logger.get_decision_count(
            start_date=start_date,
            end_date=end_date,
            decision=decision
        )
        
        return jsonify({
            'success': True,
            'count': count,
            'filters': {
                'start_date': start_date,
                'end_date': end_date,
                'decision': decision
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting audit log count: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get count',
            'message': str(e)
        }), 500


@audit_bp.route('/reports/compliance', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def generate_compliance_report(user_email, user_roles):
    """
    Generate a compliance report for audit purposes.
    
    Query Parameters:
        - start_date: Report start date (YYYY-MM-DD) - required
        - end_date: Report end date (YYYY-MM-DD) - required
        - include_details: Include detailed transaction info (true/false, default: false)
    
    Returns:
        JSON response with compliance report
    
    Requirements: 6.4, 6.5
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        include_details = request.args.get('include_details', 'false').lower() == 'true'
        
        # Validate required parameters
        if not start_date or not end_date:
            return jsonify({
                'success': False,
                'error': 'Missing required parameters',
                'message': 'start_date and end_date are required'
            }), 400
        
        # Generate report
        audit_logger = get_audit_logger()
        report = audit_logger.generate_compliance_report(
            start_date=start_date,
            end_date=end_date,
            include_details=include_details
        )
        
        return jsonify({
            'success': True,
            'report': report
        }), 200
        
    except Exception as e:
        logger.error(f"Error generating compliance report: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to generate report',
            'message': str(e)
        }), 500


@audit_bp.route('/reports/user/<user_id>', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def get_user_activity_report(user_id, user_email, user_roles):
    """
    Generate a user activity report.
    
    Path Parameters:
        - user_id: User identifier
    
    Query Parameters:
        - start_date: Optional start date filter (YYYY-MM-DD)
        - end_date: Optional end date filter (YYYY-MM-DD)
    
    Returns:
        JSON response with user activity report
    
    Requirements: 6.4, 6.5
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        audit_logger = get_audit_logger()
        report = audit_logger.get_user_activity_report(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )
        
        return jsonify({
            'success': True,
            'report': report
        }), 200
        
    except Exception as e:
        logger.error(f"Error generating user activity report: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to generate user report',
            'message': str(e)
        }), 500


@audit_bp.route('/transaction-trail', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def get_transaction_audit_trail(user_email, user_roles):
    """
    Get complete audit trail for a specific transaction.
    
    Query Parameters:
        - reference_number: Transaction reference number - required
        - transaction_date: Transaction date (YYYY-MM-DD) - required
        - transaction_amount: Transaction amount - required
    
    Returns:
        JSON response with audit trail
    
    Requirements: 6.4, 6.5
    """
    try:
        reference_number = request.args.get('reference_number')
        transaction_date = request.args.get('transaction_date')
        transaction_amount = request.args.get('transaction_amount')
        
        # Validate required parameters
        if not all([reference_number, transaction_date, transaction_amount]):
            return jsonify({
                'success': False,
                'error': 'Missing required parameters',
                'message': 'reference_number, transaction_date, and transaction_amount are required'
            }), 400
        
        # Convert amount to float
        try:
            transaction_amount = float(transaction_amount)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid transaction_amount',
                'message': 'transaction_amount must be a valid number'
            }), 400
        
        # Get audit trail
        audit_logger = get_audit_logger()
        trail = audit_logger.get_audit_trail_for_transaction(
            reference_number=reference_number,
            transaction_date=transaction_date,
            transaction_amount=transaction_amount
        )
        
        return jsonify({
            'success': True,
            'trail': trail,
            'transaction': {
                'reference_number': reference_number,
                'transaction_date': transaction_date,
                'transaction_amount': transaction_amount
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting transaction audit trail: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get audit trail',
            'message': str(e)
        }), 500


@audit_bp.route('/export/csv', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def export_logs_to_csv(user_email, user_roles):
    """
    Export audit logs to CSV file.
    
    Query Parameters:
        - start_date: Optional start date filter (YYYY-MM-DD)
        - end_date: Optional end date filter (YYYY-MM-DD)
    
    Returns:
        CSV file download
    
    Requirements: 6.4, 6.5
    """
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Create temporary file for export
        temp_file = tempfile.NamedTemporaryFile(
            mode='w',
            delete=False,
            suffix='.csv',
            prefix='audit_logs_'
        )
        temp_file.close()
        
        # Export logs
        audit_logger = get_audit_logger()
        success = audit_logger.export_logs_to_csv(
            output_file=temp_file.name,
            start_date=start_date,
            end_date=end_date
        )
        
        if not success:
            os.unlink(temp_file.name)
            return jsonify({
                'success': False,
                'error': 'Failed to export logs',
                'message': 'No logs found or export failed'
            }), 500
        
        # Generate filename with date range
        filename = f"audit_logs_{start_date or 'all'}_{end_date or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Send file
        response = send_file(
            temp_file.name,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
        # Schedule file deletion after sending
        @response.call_on_close
        def cleanup():
            try:
                os.unlink(temp_file.name)
            except Exception as e:
                logger.error(f"Failed to delete temporary file: {e}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error exporting audit logs to CSV: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to export logs',
            'message': str(e)
        }), 500


@audit_bp.route('/cleanup', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def cleanup_old_logs(user_email, user_roles):
    """
    Clean up old audit logs based on retention policy.
    
    Request Body:
        - retention_days: Number of days to retain logs (default: 730)
    
    Returns:
        JSON response with cleanup results
    
    Requirements: 6.5
    """
    try:
        data = request.get_json() or {}
        retention_days = data.get('retention_days', 730)
        
        # Validate retention days
        if not isinstance(retention_days, int) or retention_days < 1:
            return jsonify({
                'success': False,
                'error': 'Invalid retention_days',
                'message': 'retention_days must be a positive integer'
            }), 400
        
        # Perform cleanup
        audit_logger = get_audit_logger()
        success, deleted_count = audit_logger.cleanup_old_logs(
            retention_days=retention_days
        )
        
        return jsonify({
            'success': success,
            'deleted_count': deleted_count,
            'retention_days': retention_days,
            'message': f'Cleaned up {deleted_count} audit log entries older than {retention_days} days'
        }), 200
        
    except Exception as e:
        logger.error(f"Error cleaning up audit logs: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to cleanup logs',
            'message': str(e)
        }), 500


@audit_bp.route('/health', methods=['GET'])
@cognito_required(required_permissions=[])
def audit_health_check(user_email, user_roles):
    """
    Health check endpoint for audit logging system.
    
    Returns:
        JSON response with system health status
    """
    try:
        audit_logger = get_audit_logger()
        
        # Try to get a count to verify database connectivity
        count = audit_logger.get_decision_count()
        
        return jsonify({
            'success': True,
            'status': 'healthy',
            'total_logs': count,
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Audit system health check failed: {e}")
        return jsonify({
            'success': False,
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# Error handlers
@audit_bp.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'success': False,
        'error': 'Endpoint not found',
        'message': str(error)
    }), 404


@audit_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error in audit routes: {error}")
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'message': 'An unexpected error occurred'
    }), 500
