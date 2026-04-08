"""
SysAdmin Provisioning Endpoints

API endpoints for provisioning verified trial signups into full tenants.
- GET  /api/sysadmin/provisioning/pending   — List verified signups awaiting provisioning
- POST /api/sysadmin/provisioning/provision — Provision a verified signup into a tenant
"""

import os
import json
import logging
import boto3
from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from database import DatabaseManager

logger = logging.getLogger(__name__)

sysadmin_provisioning_bp = Blueprint('sysadmin_provisioning', __name__)


def _get_promo_db():
    """Get DatabaseManager for myadmin_promo database"""
    test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
    db = DatabaseManager(test_mode=test_mode)
    # Override database to promo DB
    promo_db_name = os.getenv('PROMO_DB_NAME', 'myadmin_promo')
    db.config['database'] = promo_db_name
    return db


def _get_finance_db():
    """Get DatabaseManager for finance database"""
    test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
    return DatabaseManager(test_mode=test_mode)


@sysadmin_provisioning_bp.route('/pending', methods=['GET'])
@cognito_required(required_roles=['SysAdmin'])
def list_pending_signups(user_email, user_roles):
    """
    List verified signups awaiting provisioning.

    Returns signups with status='verified' from myadmin_promo.pending_signups.
    """
    try:
        db = _get_promo_db()
        query = """
            SELECT id, email, first_name, last_name, company_name,
                   property_range, locale, status, created_at, verified_at
            FROM pending_signups
            WHERE status = 'verified'
            ORDER BY verified_at DESC
        """
        results = db.execute_query(query, fetch=True)

        signups = []
        for row in (results or []):
            signup = dict(row)
            for date_field in ('created_at', 'verified_at'):
                if signup.get(date_field):
                    signup[date_field] = signup[date_field].isoformat()
            signups.append(signup)

        return jsonify({'success': True, 'signups': signups, 'count': len(signups)})

    except Exception as e:
        logger.error(f"Error listing pending signups: {e}")
        return jsonify({'error': str(e)}), 500


@sysadmin_provisioning_bp.route('/provision', methods=['POST'])
@cognito_required(required_roles=['SysAdmin'])
def provision_signup(user_email, user_roles):
    """
    Provision a verified signup into a full tenant.

    Request body:
    {
        "email": "user@example.com",
        "administration_name": "CompanyName",   (optional — auto-generated if omitted)
        "modules": ["FIN", "STR"],              (optional — default: FIN, STR, TENADMIN)
        "locale": "nl"                          (optional — default from signup record)
    }

    Steps:
    1. Look up pending_signups record (must be 'verified')
    2. Generate administration name if not provided
    3. Create tenant + modules + chart via TenantProvisioningService
    4. Update Cognito user custom:tenants attribute
    5. Mark signup as provisioned
    6. Send admin notification via SNS
    7. Send welcome email to user via SES
    """
    try:
        data = request.get_json()
        if not data or not data.get('email'):
            return jsonify({'error': 'Email is required'}), 400

        email = data['email'].strip()

        # Step 1: Look up signup
        promo_db = _get_promo_db()
        signup_rows = promo_db.execute_query(
            "SELECT * FROM pending_signups WHERE email = %s",
            (email,), fetch=True
        )
        if not signup_rows:
            return jsonify({'error': f'No signup found for {email}'}), 404

        signup = signup_rows[0]
        if signup['status'] == 'provisioned':
            return jsonify({'error': f'{email} is already provisioned'}), 409
        if signup['status'] != 'verified':
            return jsonify({'error': f'Signup status is {signup["status"]}, must be verified'}), 400

        # Step 2: Generate or use provided administration name
        admin_name = data.get('administration_name')
        if not admin_name:
            admin_name = _generate_admin_name(
                signup.get('company_name', ''), email
            )

        # Determine modules and locale
        modules = data.get('modules', ['FIN', 'STR', 'TENADMIN'])
        locale = data.get('locale', signup.get('locale', 'nl'))
        display_name = signup.get('company_name') or f"{signup['first_name']} {signup['last_name']}"

        # Step 3: Create tenant via shared service
        from services.tenant_provisioning_service import TenantProvisioningService
        finance_db = _get_finance_db()
        service = TenantProvisioningService(finance_db)

        prov_results = service.create_and_provision_tenant(
            administration=admin_name,
            display_name=display_name,
            contact_email=email,
            modules=modules,
            created_by=user_email,
            locale=locale,
        )

        # Set plan to trial with 2-month expiry
        finance_db.execute_query(
            """
            UPDATE tenants
            SET plan = 'trial', plan_expires_at = DATE_ADD(NOW(), INTERVAL 2 MONTH)
            WHERE administration = %s
            """,
            (admin_name,), commit=True
        )

        # Step 4: Update Cognito user custom:tenants
        cognito_error = _update_cognito_tenants(email, admin_name)

        # Step 5: Mark provisioned
        promo_db.execute_query(
            "UPDATE pending_signups SET status = 'provisioned', provisioned_at = NOW() WHERE email = %s",
            (email,), commit=True
        )

        # Step 6: Send admin notification (non-critical)
        _send_admin_notification(email, admin_name, signup.get('first_name', ''))

        # Step 7: Send welcome email (non-critical)
        _send_welcome_email(email, admin_name, signup.get('first_name', ''), locale)

        response = {
            'success': True,
            'administration': admin_name,
            'display_name': display_name,
            'provisioning': prov_results,
            'plan': 'trial',
        }
        if cognito_error:
            response['cognito_warning'] = cognito_error
        if prov_results.get('warnings'):
            response['warnings'] = prov_results['warnings']

        logger.info(f"Signup {email} provisioned as '{admin_name}' by {user_email}")
        return jsonify(response), 201

    except Exception as e:
        logger.error(f"Error provisioning signup: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def _generate_admin_name(company_name: str, email: str) -> str:
    """Generate PascalCase administration name from company or email."""
    import re
    source = company_name.strip() if company_name else email.split('@')[0]
    words = re.sub(r'[^a-zA-Z0-9\s]', '', source).split()
    base = ''.join(w.capitalize() for w in words if w) or 'NewTenant'
    return base[:50]


def _update_cognito_tenants(email: str, admin_name: str) -> str:
    """Add admin_name to Cognito user's custom:tenants. Returns error string or None."""
    try:
        region = os.getenv('AWS_REGION', 'eu-west-1')
        pool_id = os.getenv('SIGNUP_COGNITO_USER_POOL_ID', os.getenv('COGNITO_USER_POOL_ID'))
        client = boto3.client('cognito-idp', region_name=region)

        user = client.admin_get_user(UserPoolId=pool_id, Username=email)
        current_tenants = []
        for attr in user.get('UserAttributes', []):
            if attr['Name'] == 'custom:tenants':
                try:
                    current_tenants = json.loads(attr['Value'])
                except (json.JSONDecodeError, TypeError):
                    pass

        if admin_name not in current_tenants:
            current_tenants.append(admin_name)
            client.admin_update_user_attributes(
                UserPoolId=pool_id,
                Username=email,
                UserAttributes=[{
                    'Name': 'custom:tenants',
                    'Value': json.dumps(current_tenants)
                }]
            )
        logger.info(f"Cognito updated for {email}: custom:tenants = {json.dumps(current_tenants)}")
        return None
    except Exception as e:
        logger.warning(f"Cognito update failed for {email}: {e}")
        return str(e)


def _send_admin_notification(email: str, admin_name: str, first_name: str):
    """Send SNS notification to admin (non-critical)."""
    try:
        from aws_notifications import get_notification_service
        service = get_notification_service()
        if service and service.is_enabled():
            service.send_business_notification(
                'Tenant Provisioned',
                f"Tenant '{admin_name}' provisioned for {email}",
                {'email': email, 'administration': admin_name, 'name': first_name}
            )
    except Exception as e:
        logger.warning(f"Admin notification failed (non-critical): {e}")


def _send_welcome_email(email: str, admin_name: str, first_name: str, locale: str):
    """Send welcome email to the new tenant user via SES (non-critical)."""
    try:
        from services.ses_email_service import SESEmailService
        from utils.frontend_url import get_frontend_url

        ses = SESEmailService()
        if not ses.is_enabled():
            return

        login_url = get_frontend_url()
        name = first_name or email.split('@')[0]

        if locale == 'nl':
            subject = f'Welkom bij myAdmin — {admin_name}'
            html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #DD6B20;">Welkom bij myAdmin</h2>
                <p>Hallo {name},</p>
                <p>Uw tenant <strong>{admin_name}</strong> is aangemaakt en klaar voor gebruik.</p>
                <p>U kunt nu inloggen met uw e-mailadres en wachtwoord:</p>
                <p style="text-align: center; margin: 30px 0;">
                    <a href="{login_url}" style="background-color: #DD6B20; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px;">
                        Inloggen op myAdmin
                    </a>
                </p>
                <p>Of bezoek: <a href="{login_url}">{login_url}</a></p>
                <p>Uw proefperiode is 2 maanden geldig.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #888; font-size: 12px;">myAdmin — Financieel beheer en vakantieverhuur</p>
            </div>
            """
        else:
            subject = f'Welcome to myAdmin — {admin_name}'
            html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #DD6B20;">Welcome to myAdmin</h2>
                <p>Hello {name},</p>
                <p>Your tenant <strong>{admin_name}</strong> has been created and is ready to use.</p>
                <p>You can now log in with your email and password:</p>
                <p style="text-align: center; margin: 30px 0;">
                    <a href="{login_url}" style="background-color: #DD6B20; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px;">
                        Log in to myAdmin
                    </a>
                </p>
                <p>Or visit: <a href="{login_url}">{login_url}</a></p>
                <p>Your trial period is valid for 2 months.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                <p style="color: #888; font-size: 12px;">myAdmin — Financial management and short-term rentals</p>
            </div>
            """

        ses.send_email(
            to_email=email, subject=subject, html_body=html,
            email_type='invitation', administration=admin_name,
        )
        logger.info(f"Welcome email sent to {email}")
    except Exception as e:
        logger.warning(f"Welcome email failed (non-critical): {e}")
