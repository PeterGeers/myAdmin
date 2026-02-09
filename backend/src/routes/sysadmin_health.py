"""
SysAdmin Health Check Endpoints

API endpoints for monitoring system health and service status
"""

from flask import Blueprint, jsonify
from auth.cognito_utils import cognito_required
import os
import boto3
import logging
import time
from database import DatabaseManager
from datetime import datetime

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize AWS clients
cognito_client = boto3.client('cognito-idp', region_name=os.getenv('AWS_REGION', 'eu-west-1'))
sns_client = boto3.client('sns', region_name=os.getenv('AWS_REGION', 'eu-west-1'))

# Configuration
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN')

# Create blueprint
sysadmin_health_bp = Blueprint('sysadmin_health', __name__)


def check_database_health():
    """
    Check MySQL database health
    
    Returns:
        dict: Health status with response time and details
    """
    start_time = time.time()
    try:
        db = DatabaseManager()
        
        # Test connection with simple query
        result = db.execute_query("SELECT 1 as test", fetch=True)
        
        # Get database info
        db_info = db.execute_query("SELECT VERSION() as version", fetch=True)
        version = db_info[0]['version'] if db_info else 'Unknown'
        
        # Get connection stats (if available)
        stats = db.execute_query(
            "SHOW STATUS WHERE Variable_name IN ('Threads_connected', 'Max_used_connections')",
            fetch=True
        )
        
        connections = {}
        for stat in stats:
            connections[stat['Variable_name']] = stat['Value']
        
        response_time = int((time.time() - start_time) * 1000)
        
        return {
            'service': 'database',
            'status': 'healthy',
            'responseTime': response_time,
            'message': f'Connected to MySQL {version}',
            'lastChecked': datetime.utcnow().isoformat() + 'Z',
            'details': {
                'host': os.getenv('DB_HOST', 'localhost'),
                'database': os.getenv('DB_NAME', 'finance'),
                'connections': connections
            }
        }
    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        logger.error(f"Database health check failed: {e}")
        return {
            'service': 'database',
            'status': 'unhealthy',
            'responseTime': response_time,
            'message': f'Database connection failed: {str(e)}',
            'lastChecked': datetime.utcnow().isoformat() + 'Z'
        }


def check_cognito_health():
    """
    Check AWS Cognito health
    
    Returns:
        dict: Health status with response time and details
    """
    start_time = time.time()
    try:
        # Test Cognito access by describing user pool
        response = cognito_client.describe_user_pool(
            UserPoolId=USER_POOL_ID
        )
        
        response_time = int((time.time() - start_time) * 1000)
        
        # Determine status based on response time
        status = 'healthy' if response_time < 1000 else 'degraded'
        
        return {
            'service': 'cognito',
            'status': status,
            'responseTime': response_time,
            'message': 'AWS Cognito accessible',
            'lastChecked': datetime.utcnow().isoformat() + 'Z',
            'details': {
                'userPoolId': USER_POOL_ID,
                'userPoolName': response['UserPool'].get('Name', 'Unknown')
            }
        }
    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        logger.error(f"Cognito health check failed: {e}")
        return {
            'service': 'cognito',
            'status': 'unhealthy',
            'responseTime': response_time,
            'message': f'AWS Cognito error: {str(e)}',
            'lastChecked': datetime.utcnow().isoformat() + 'Z'
        }


def check_sns_health():
    """
    Check AWS SNS health
    
    Returns:
        dict: Health status with response time and details
    """
    start_time = time.time()
    
    # Skip if SNS not configured
    if not SNS_TOPIC_ARN:
        return {
            'service': 'sns',
            'status': 'healthy',
            'responseTime': 0,
            'message': 'AWS SNS not configured (optional)',
            'lastChecked': datetime.utcnow().isoformat() + 'Z'
        }
    
    try:
        # Test SNS access by getting topic attributes
        response = sns_client.get_topic_attributes(
            TopicArn=SNS_TOPIC_ARN
        )
        
        response_time = int((time.time() - start_time) * 1000)
        
        # Determine status based on response time
        status = 'healthy' if response_time < 1000 else 'degraded'
        
        return {
            'service': 'sns',
            'status': status,
            'responseTime': response_time,
            'message': 'AWS SNS accessible',
            'lastChecked': datetime.utcnow().isoformat() + 'Z',
            'details': {
                'topicArn': SNS_TOPIC_ARN,
                'subscriptions': response['Attributes'].get('SubscriptionsConfirmed', '0')
            }
        }
    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        logger.error(f"SNS health check failed: {e}")
        return {
            'service': 'sns',
            'status': 'unhealthy',
            'responseTime': response_time,
            'message': f'AWS SNS error: {str(e)}',
            'lastChecked': datetime.utcnow().isoformat() + 'Z'
        }


def check_google_drive_health():
    """
    Check Google Drive API health
    
    Returns:
        dict: Health status with response time and details
    """
    start_time = time.time()
    
    try:
        # Import Google Drive service
        from google_drive_service import get_drive_service
        
        # Get Drive service
        service = get_drive_service()
        
        # Test access by listing files (limit 1)
        results = service.files().list(
            pageSize=1,
            fields="files(id, name)"
        ).execute()
        
        response_time = int((time.time() - start_time) * 1000)
        
        # Determine status based on response time
        if response_time < 1000:
            status = 'healthy'
        elif response_time < 3000:
            status = 'degraded'
        else:
            status = 'unhealthy'
        
        return {
            'service': 'google_drive',
            'status': status,
            'responseTime': response_time,
            'message': 'Google Drive API accessible' if status == 'healthy' else 'Slow response time',
            'lastChecked': datetime.utcnow().isoformat() + 'Z'
        }
    except ImportError:
        return {
            'service': 'google_drive',
            'status': 'healthy',
            'responseTime': 0,
            'message': 'Google Drive not configured (optional)',
            'lastChecked': datetime.utcnow().isoformat() + 'Z'
        }
    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        logger.error(f"Google Drive health check failed: {e}")
        return {
            'service': 'google_drive',
            'status': 'unhealthy',
            'responseTime': response_time,
            'message': f'Google Drive error: {str(e)}',
            'lastChecked': datetime.utcnow().isoformat() + 'Z'
        }


def check_openrouter_health():
    """
    Check OpenRouter API health
    
    Returns:
        dict: Health status with response time and details
    """
    start_time = time.time()
    
    # Skip if OpenRouter not configured
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        return {
            'service': 'openrouter',
            'status': 'healthy',
            'responseTime': 0,
            'message': 'OpenRouter not configured (optional)',
            'lastChecked': datetime.utcnow().isoformat() + 'Z'
        }
    
    try:
        import requests
        
        # Test OpenRouter API with a simple request
        response = requests.get(
            'https://openrouter.ai/api/v1/models',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=5
        )
        
        response_time = int((time.time() - start_time) * 1000)
        
        if response.status_code == 200:
            status = 'healthy' if response_time < 1000 else 'degraded'
            message = 'OpenRouter API accessible'
        else:
            status = 'unhealthy'
            message = f'OpenRouter API error: HTTP {response.status_code}'
        
        return {
            'service': 'openrouter',
            'status': status,
            'responseTime': response_time,
            'message': message,
            'lastChecked': datetime.utcnow().isoformat() + 'Z'
        }
    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        logger.error(f"OpenRouter health check failed: {e}")
        return {
            'service': 'openrouter',
            'status': 'unhealthy',
            'responseTime': response_time,
            'message': f'OpenRouter error: {str(e)}',
            'lastChecked': datetime.utcnow().isoformat() + 'Z'
        }


@sysadmin_health_bp.route('', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def get_system_health(user_email, user_roles):
    """
    Get overall system health status
    
    Authorization: SysAdmin role required
    
    Returns health status for all services:
    - Database (MySQL)
    - AWS Cognito
    - AWS SNS
    - Google Drive (optional)
    - OpenRouter (optional)
    """
    try:
        # Run all health checks
        services = [
            check_database_health(),
            check_cognito_health(),
            check_sns_health(),
            check_google_drive_health(),
            check_openrouter_health()
        ]
        
        # Determine overall status
        unhealthy_count = sum(1 for s in services if s['status'] == 'unhealthy')
        degraded_count = sum(1 for s in services if s['status'] == 'degraded')
        
        if unhealthy_count > 0:
            overall = 'unhealthy'
        elif degraded_count > 0:
            overall = 'degraded'
        else:
            overall = 'healthy'
        
        return jsonify({
            'overall': overall,
            'services': services,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
        
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
