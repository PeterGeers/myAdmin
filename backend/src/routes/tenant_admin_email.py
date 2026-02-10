"""
Tenant Admin Email Routes

Endpoints for Tenant Admins to send emails to users using templates.
"""

from flask import Blueprint, jsonify, request
import os
import logging

from auth.cognito_utils import cognito_required
from auth.tenant_context import get_current_tenant
from services.email_template_service import EmailTemplateService
from services.cognito_service import CognitoService

# Initialize logger
logger = logging.getLogger(__name__)

# Create blueprint
tenant_admin_email_bp = Blueprint('tenant_admin_email', __name__)


@tenant_admin_email_bp.route('/api/tenant-admin/send-email', methods=['POST'])
@cognito_required(required_roles=['Tenant_Admin'])
def send_email_to_user(user_email, user_roles):
    """
    Send email to a user using a template
    
    Authorization: Tenant_Admin role required
    
    Request body:
    {
        "email": "user@example.com",
        "template_type": "user_invitation",
        "user_data": {
            "name": "John Doe",
            "username": "uuid",
            "status": "CONFIRMED"
        }
    }
    
    Returns:
        JSON with success status
    """
    try:
        # Get current tenant
        tenant = get_current_tenant(request)
        
        # Get request data
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        recipient_email = data.get('email')
        template_type = data.get('template_type', 'user_invitation')
        user_data = data.get('user_data', {})
        
        if not recipient_email:
            return jsonify({'error': 'Email is required'}), 400
        
        # Validate template type
        valid_templates = ['user_invitation', 'password_reset', 'account_update']
        if template_type not in valid_templates:
            return jsonify({'error': f'Invalid template type. Must be one of: {", ".join(valid_templates)}'}), 400
        
        # Initialize services
        email_service = EmailTemplateService(administration=tenant)
        cognito_service = CognitoService()
        
        # Get user details if not provided
        if not user_data.get('name'):
            try:
                # Try to get user details from Cognito
                import boto3
                from botocore.exceptions import ClientError
                
                cognito_client = boto3.client('cognito-idp', region_name=os.getenv('AWS_REGION', 'eu-west-1'))
                user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
                
                response = cognito_client.admin_get_user(
                    UserPoolId=user_pool_id,
                    Username=user_data.get('username', recipient_email)
                )
                
                # Extract name from attributes
                for attr in response.get('UserAttributes', []):
                    if attr['Name'] == 'name':
                        user_data['name'] = attr['Value']
                        break
                
            except (ClientError, Exception) as e:
                logger.warning(f"Could not fetch user details: {e}")
                user_data['name'] = recipient_email.split('@')[0]
        
        # Render email template
        html_content = email_service.render_template(
            template_name=template_type,
            variables={
                'email': recipient_email,
                'tenant': tenant,
                'name': user_data.get('name', recipient_email),
                'login_url': os.getenv('FRONTEND_URL', 'http://localhost:3000'),
                'temporary_password': user_data.get('temporary_password', '********')
            },
            format='html'
        )
        
        text_content = email_service.render_template(
            template_name=template_type,
            variables={
                'email': recipient_email,
                'tenant': tenant,
                'name': user_data.get('name', recipient_email),
                'login_url': os.getenv('FRONTEND_URL', 'http://localhost:3000'),
                'temporary_password': user_data.get('temporary_password', '********')
            },
            format='txt'
        )
        
        # Send email via SNS
        sns_topic_arn = os.getenv('SNS_TOPIC_ARN')
        if not sns_topic_arn:
            return jsonify({
                'error': 'SNS not configured',
                'message': 'SNS_TOPIC_ARN environment variable is not set'
            }), 500
        
        import boto3
        sns_client = boto3.client('sns', region_name=os.getenv('AWS_REGION', 'eu-west-1'))
        
        # Get subject line
        subject = email_service.get_invitation_subject(tenant)
        if template_type == 'password_reset':
            subject = f"Password Reset - {tenant}"
        elif template_type == 'account_update':
            subject = f"Account Update - {tenant}"
        
        # Send via SNS (use text content as primary message)
        sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject=subject,
            Message=text_content or f"Email to {recipient_email} from {tenant}"
        )
        
        logger.info(f"Email sent to {recipient_email} by {user_email} for tenant {tenant}, template={template_type}")
        
        return jsonify({
            'success': True,
            'message': f'Email sent successfully to {recipient_email}',
            'template_type': template_type
        })
        
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': 'Failed to send email',
            'message': str(e)
        }), 500


@tenant_admin_email_bp.route('/api/tenant-admin/email-templates', methods=['GET'])
@cognito_required(required_roles=['Tenant_Admin'])
def list_email_templates(user_email, user_roles):
    """
    List available email templates
    
    Authorization: Tenant_Admin role required
    
    Returns:
        JSON with list of available templates
    """
    try:
        templates = [
            {
                'template_type': 'user_invitation',
                'display_name': 'User Invitation',
                'description': 'Welcome email for new users with login credentials'
            },
            {
                'template_type': 'password_reset',
                'display_name': 'Password Reset',
                'description': 'Password reset instructions'
            },
            {
                'template_type': 'account_update',
                'display_name': 'Account Update',
                'description': 'Notification about account changes'
            }
        ]
        
        return jsonify({
            'success': True,
            'templates': templates
        })
        
    except Exception as e:
        logger.error(f"Error listing email templates: {e}")
        return jsonify({
            'error': 'Failed to list templates',
            'message': str(e)
        }), 500
