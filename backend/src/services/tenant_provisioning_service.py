"""
Tenant Provisioning Service

Shared logic for creating a new tenant, used by both:
- SysAdmin UI (sysadmin_tenants.py)
- Provisioning script (scripts/provision_tenant.py)
- SysAdmin provisioning API (sysadmin_provisioning.py)

Handles:
1. Insert tenant record (idempotent)
2. Insert tenant modules (idempotent — skips existing, inserts missing)
3. Load chart of accounts from JSON template (idempotent — skips if rows exist)
4. Create initial admin user (idempotent — skips if user_tenant_roles row exists)

Returns a results dict with created/skipped status per step so callers
can report exactly what happened.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from services.parameter_service import ParameterService

logger = logging.getLogger(__name__)

# Path to chart of accounts JSON templates
_TEMPLATE_DIR = Path(__file__).parent.parent / 'templates' / 'chart_of_accounts'


class TenantProvisioningService:
    """Shared tenant provisioning logic."""

    def __init__(self, db_manager):
        self.db = db_manager

    def create_and_provision_tenant(
        self,
        administration: str,
        display_name: str,
        contact_email: str,
        modules: list,
        created_by: str,
        locale: str = 'nl',
        phone_number: Optional[str] = None,
        street: Optional[str] = None,
        city: Optional[str] = None,
        zipcode: Optional[str] = None,
        country: str = 'Netherlands',
        initial_admin_email: Optional[str] = None,
    ) -> dict:
        """
        Create and provision a new tenant.

        Idempotent — safe to rerun if a previous attempt partially completed.
        Each step checks before acting and skips if already done.

        Args:
            administration: Unique tenant identifier (PascalCase, alphanumeric)
            display_name:   Human-readable tenant name
            contact_email:  Primary contact email
            modules:        List of module names (e.g. ['FIN', 'STR', 'TENADMIN'])
            created_by:     Email of the user performing the action
            locale:         'nl' or 'en' — determines chart of accounts language
            phone_number:   Optional contact phone
            street:         Optional street address
            city:           Optional city
            zipcode:        Optional zipcode
            country:        Country (default: Netherlands)
            initial_admin_email: Optional email for the initial Tenant_Admin user.
                                 When provided, creates the admin user after
                                 infrastructure provisioning.  When None or empty,
                                 the admin-user step is skipped entirely.

        Returns:
            {
                'tenant':  'created' | 'skipped',
                'modules': [{'name': 'FIN', 'status': 'created' | 'skipped'}, ...],
                'chart':   'created' | 'skipped' | 'failed',
                'chart_rows': int,
                'warnings': [],
                'initial_admin': {              # only present when initial_admin_email provided
                    'status': 'created' | 'existing_user' | 'skipped' | 'failed',
                    'warning': optional str
                }
            }
        """
        results = {
            'tenant': None,
            'modules': [],
            'chart': None,
            'chart_rows': 0,
            'warnings': [],
        }

        # Ensure TENADMIN is always included
        if 'TENADMIN' not in modules:
            modules = list(modules) + ['TENADMIN']

        # Step 1: Insert tenant record
        results['tenant'] = self._insert_tenant(
            administration, display_name, contact_email,
            created_by, phone_number, street, city, zipcode, country
        )

        # Step 2: Insert modules
        results['modules'] = self._insert_modules(administration, modules)

        # Step 2b: Seed module parameters
        param_service = ParameterService(self.db)
        params_seeded = 0
        for module in modules:
            params_seeded += param_service.seed_module_params(administration, module)

        # Seed storage params (only when S3_SHARED_BUCKET is configured)
        s3_bucket = os.getenv('S3_SHARED_BUCKET')
        if s3_bucket:
            param_service.set_param(
                'tenant', administration, 'storage', 'invoice_provider',
                's3_shared', value_type='string', created_by='provisioning'
            )
            param_service.set_param(
                'tenant', administration, 'storage', 's3_shared_bucket',
                s3_bucket,
                value_type='string', created_by='provisioning'
            )
            params_seeded += 2
        results['params_seeded'] = params_seeded

        # Step 3: Load chart of accounts from JSON template
        chart_result = self._load_chart_of_accounts(administration, locale, results['warnings'])
        results['chart'] = chart_result['status']
        results['chart_rows'] = chart_result['rows']

        # Step 4: Create initial admin user (optional)
        if initial_admin_email and initial_admin_email.strip():
            try:
                admin_result = self.create_initial_admin_user(
                    administration=administration,
                    email=initial_admin_email.strip(),
                    created_by=created_by,
                    locale=locale,
                )
                results['initial_admin'] = admin_result
            except Exception as e:
                logger.warning(
                    f"Initial admin user creation failed for '{administration}': {e}"
                )
                results['initial_admin'] = {
                    'status': 'failed',
                    'warning': str(e),
                }
                results['warnings'].append(
                    f"Initial admin user creation failed: {e}"
                )

        admin_status = (
            f", initial_admin={results['initial_admin']['status']}"
            if 'initial_admin' in results
            else ''
        )
        logger.info(
            f"Provisioning complete for '{administration}': "
            f"tenant={results['tenant']}, "
            f"chart={results['chart']} ({results['chart_rows']} rows)"
            f"{admin_status}"
        )
        return results

    def create_initial_admin_user(
        self,
        administration: str,
        email: str,
        created_by: str,
        locale: str = 'nl',
    ) -> Dict[str, Any]:
        """
        Create an initial admin user for a newly provisioned tenant.

        Idempotent — skips if a Tenant_Admin role already exists for this
        email + administration pair.  Handles both brand-new Cognito users
        and users that already exist (e.g. from the promo signup flow).

        For NEW users:
          - Creates Cognito user with custom:tenants
          - Sets permanent password so status is CONFIRMED (not FORCE_CHANGE_PASSWORD)
          - Creates invitation record with temporary password
          - Inserts user_tenant_roles with Tenant_Admin
          - Sends invitation email

        For EXISTING users:
          - Adds tenant to Cognito custom:tenants
          - Inserts user_tenant_roles with Tenant_Admin
          - Sends tenant-added notification email

        Failures are logged as warnings — they never fail the overall
        provisioning operation (matches the chart-of-accounts pattern).

        Args:
            administration: Tenant identifier
            email:          Admin user email
            created_by:     Email of the user performing the action
            locale:         'nl' or 'en' — used for email language

        Returns:
            {'status': 'created'|'existing_user'|'skipped'|'failed',
             'warning': <optional str>}
        """
        email = email.strip().lower()

        try:
            # ── Idempotent guard ────────────────────────────────────
            existing_role = self.db.execute_query(
                """
                SELECT id FROM user_tenant_roles
                WHERE email = %s AND administration = %s AND role = 'Tenant_Admin'
                """,
                (email, administration),
                fetch=True,
            )
            if existing_role:
                logger.info(
                    f"Tenant_Admin role already exists for {email} "
                    f"in '{administration}' — skipping"
                )
                return {'status': 'skipped'}

            # ── Service instances ───────────────────────────────────
            from services.cognito_service import CognitoService
            from services.invitation_service import InvitationService
            from services.email_template_service import EmailTemplateService
            from services.ses_email_service import SESEmailService
            from utils.frontend_url import get_frontend_url

            test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
            cognito = CognitoService()
            invitation_service = InvitationService(test_mode=test_mode)
            email_template = EmailTemplateService(administration=administration)
            ses = SESEmailService()
            login_url = get_frontend_url()

            # ── Check if Cognito user exists ────────────────────────
            cognito_user = cognito.get_user(email)

            if cognito_user is None:
                # ── NEW user path ───────────────────────────────────
                return self._create_new_admin_user(
                    administration, email, created_by, locale,
                    cognito, invitation_service, email_template, ses, login_url,
                )
            else:
                # ── EXISTING user path ──────────────────────────────
                return self._add_admin_role_existing_user(
                    administration, email, created_by, locale,
                    cognito, cognito_user, email_template, ses, login_url,
                )

        except Exception as exc:
            msg = (
                f"Failed to create initial admin user {email} "
                f"for '{administration}': {exc}"
            )
            logger.error(msg)
            return {'status': 'failed', 'warning': msg}

    # -------------------------------------------------------------------------
    # Initial-admin helpers
    # -------------------------------------------------------------------------

    def _create_new_admin_user(
        self,
        administration: str,
        email: str,
        created_by: str,
        locale: str,
        cognito,
        invitation_service,
        email_template,
        ses,
        login_url: str,
    ) -> Dict[str, Any]:
        """Create a brand-new Cognito user and grant Tenant_Admin."""

        # 1. Create invitation record (generates temp password)
        invitation = invitation_service.create_invitation(
            administration=administration,
            email=email,
            created_by=created_by,
            template_type='user_invitation',
        )
        if not invitation.get('success'):
            return {
                'status': 'failed',
                'warning': f"Invitation creation failed: {invitation.get('error')}",
            }

        temp_password = invitation['temporary_password']

        # 2. Create Cognito user (suppresses default welcome email)
        cognito.create_user(
            email=email,
            tenant=administration,
            password=temp_password,
            suppress_email=True,
        )

        # 3. Set permanent password → moves status to CONFIRMED
        cognito.client.admin_set_user_password(
            UserPoolId=cognito.user_pool_id,
            Username=email,
            Password=temp_password,
            Permanent=True,
        )

        # 4. Update invitation with Cognito username
        invitation_service.create_invitation(
            administration=administration,
            email=email,
            username=email,
            created_by=created_by,
            template_type='user_invitation',
        )

        # 5. Insert user_tenant_roles row
        self.db.execute_query(
            """
            INSERT INTO user_tenant_roles (email, administration, role, created_by)
            VALUES (%s, %s, 'Tenant_Admin', %s)
            """,
            (email, administration, created_by),
            fetch=False,
            commit=True,
        )

        # 6. Send invitation email
        self._send_invitation_email(
            email, administration, temp_password, locale,
            email_template, ses, login_url, created_by, invitation_service,
        )

        logger.info(
            f"Initial admin user {email} created for '{administration}'"
        )
        return {'status': 'created'}

    def _add_admin_role_existing_user(
        self,
        administration: str,
        email: str,
        created_by: str,
        locale: str,
        cognito,
        cognito_user: dict,
        email_template,
        ses,
        login_url: str,
    ) -> Dict[str, Any]:
        """Grant Tenant_Admin to an existing Cognito user."""

        # 1. Add tenant to Cognito custom:tenants
        cognito.add_tenant_to_user(email, administration)

        # 2. Insert user_tenant_roles row
        self.db.execute_query(
            """
            INSERT INTO user_tenant_roles (email, administration, role, created_by)
            VALUES (%s, %s, 'Tenant_Admin', %s)
            """,
            (email, administration, created_by),
            fetch=False,
            commit=True,
        )

        # 3. Send tenant-added notification email
        self._send_tenant_added_email(
            email, administration, cognito_user, locale,
            email_template, ses, login_url, created_by,
        )

        logger.info(
            f"Existing user {email} granted Tenant_Admin for '{administration}'"
        )
        return {'status': 'existing_user'}

    def _send_invitation_email(
        self,
        email: str,
        administration: str,
        temp_password: str,
        locale: str,
        email_template,
        ses,
        login_url: str,
        created_by: str,
        invitation_service,
    ) -> None:
        """Send invitation email to a new admin user."""
        try:
            html_body = email_template.render_user_invitation(
                email=email,
                temporary_password=temp_password,
                tenant=administration,
                login_url=login_url,
                format='html',
                language=locale,
            )
            text_body = email_template.render_user_invitation(
                email=email,
                temporary_password=temp_password,
                tenant=administration,
                login_url=login_url,
                format='txt',
                language=locale,
            )
            subject = email_template.get_invitation_subject(
                administration, language=locale,
            )

            result = ses.send_invitation(
                to_email=email,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
                administration=administration,
                sent_by=created_by,
            )

            if result.get('success'):
                invitation_service.mark_invitation_sent(
                    administration=administration, email=email,
                )
                logger.info(f"Invitation email sent to {email}")
            else:
                logger.warning(
                    f"SES failed to send invitation to {email}: "
                    f"{result.get('error')}"
                )
                invitation_service.mark_invitation_failed(
                    administration=administration,
                    email=email,
                    error_message=f"SES send failed: {result.get('error')}",
                )
        except Exception as exc:
            logger.warning(f"Failed to send invitation email to {email}: {exc}")
            invitation_service.mark_invitation_failed(
                administration=administration,
                email=email,
                error_message=f"Email send failed: {exc}",
            )

    def _send_tenant_added_email(
        self,
        email: str,
        administration: str,
        cognito_user: dict,
        locale: str,
        email_template,
        ses,
        login_url: str,
        created_by: str,
    ) -> None:
        """Send tenant-added notification to an existing user."""
        try:
            # Resolve display name from Cognito attributes
            user_name = email.split('@')[0]
            for attr in cognito_user.get('UserAttributes', []):
                if attr['Name'] == 'name':
                    user_name = attr['Value']
                    break

            html_body = email_template.render_template(
                template_name='tenant_added',
                variables={
                    'email': email,
                    'tenant': administration,
                    'name': user_name,
                    'login_url': login_url,
                },
                format='html',
                language=locale,
            )
            text_body = (
                f"Hi {user_name},\n\n"
                f"You have been added to the {administration} tenant "
                f"in myAdmin.\n\n"
                f"You can log in with your existing credentials at: "
                f"{login_url}\n\n"
                f"Regards,\nmyAdmin"
            )

            if locale == 'nl':
                subject = (
                    f"U bent toegevoegd aan {administration} in myAdmin"
                )
            else:
                subject = (
                    f"You've been added to {administration} in myAdmin"
                )

            result = ses.send_invitation(
                to_email=email,
                subject=subject,
                html_body=html_body or text_body,
                text_body=text_body,
                administration=administration,
                sent_by=created_by,
            )

            if result.get('success'):
                logger.info(
                    f"Tenant-added notification sent to {email} "
                    f"for '{administration}'"
                )
            else:
                logger.warning(
                    f"Failed to send tenant-added notification to {email}: "
                    f"{result.get('error')}"
                )
        except Exception as exc:
            logger.warning(
                f"Failed to send tenant-added notification to {email}: {exc}"
            )

    def _insert_tenant(
        self, administration, display_name, contact_email,
        created_by, phone_number, street, city, zipcode, country
    ) -> str:
        """Insert tenant record. Returns 'created' or 'skipped'."""
        existing = self.db.execute_query(
            "SELECT administration FROM tenants WHERE administration = %s",
            (administration,),
            fetch=True
        )
        if existing:
            logger.info(f"Tenant '{administration}' already exists — skipping insert")
            return 'skipped'

        self.db.execute_query(
            """
            INSERT INTO tenants (
                administration, display_name, status, contact_email,
                phone_number, street, city, zipcode, country,
                created_at, updated_at, updated_by
            ) VALUES (%s, %s, 'active', %s, %s, %s, %s, %s, %s, NOW(), NOW(), %s)
            """,
            (
                administration, display_name, contact_email,
                phone_number, street, city, zipcode, country, created_by
            ),
            commit=True
        )
        logger.info(f"Tenant '{administration}' inserted")
        return 'created'

    def _insert_modules(self, administration: str, modules: list) -> list:
        """Insert modules, skipping any that already exist."""
        results = []
        for module in modules:
            existing = self.db.execute_query(
                """
                SELECT id FROM tenant_modules
                WHERE administration = %s AND module_name = %s
                """,
                (administration, module),
                fetch=True
            )
            if existing:
                logger.info(f"Module '{module}' already exists for '{administration}' — skipping")
                results.append({'name': module, 'status': 'skipped'})
            else:
                self.db.execute_query(
                    """
                    INSERT INTO tenant_modules (administration, module_name, is_active, created_at)
                    VALUES (%s, %s, TRUE, NOW())
                    """,
                    (administration, module),
                    commit=True
                )
                logger.info(f"Module '{module}' inserted for '{administration}'")
                results.append({'name': module, 'status': 'created'})
        return results

    def _load_chart_of_accounts(
        self, administration: str, locale: str, warnings: list
    ) -> dict:
        """
        Load chart of accounts from JSON template and insert for tenant.
        Skips if the tenant already has chart rows.
        Falls back to 'nl' if the requested locale template doesn't exist.

        Returns {'status': 'created'|'skipped'|'failed', 'rows': int}
        """
        # Check if chart already exists for this tenant
        count_result = self.db.execute_query(
            "SELECT COUNT(*) as cnt FROM rekeningschema WHERE administration = %s",
            (administration,),
            fetch=True
        )
        existing_count = count_result[0]['cnt'] if count_result else 0
        if existing_count > 0:
            logger.info(
                f"Chart of accounts already exists for '{administration}' "
                f"({existing_count} rows) — skipping"
            )
            return {'status': 'skipped', 'rows': existing_count}

        # Resolve template path with locale fallback
        template_path = _TEMPLATE_DIR / f'{locale}.json'
        if not template_path.exists():
            fallback = _TEMPLATE_DIR / 'nl.json'
            if fallback.exists():
                msg = (
                    f"Chart template for locale '{locale}' not found, "
                    f"falling back to 'nl'"
                )
                logger.warning(msg)
                warnings.append(msg)
                template_path = fallback
            else:
                msg = (
                    f"Chart of accounts template not found at {template_path}. "
                    f"Tenant '{administration}' has no chart — add manually."
                )
                logger.error(msg)
                warnings.append(msg)
                return {'status': 'failed', 'rows': 0}

        # Load and insert
        try:
            with open(template_path, encoding='utf-8') as f:
                accounts = json.load(f)

            inserted = 0
            for account in accounts:
                self.db.execute_query(
                    """
                    INSERT INTO rekeningschema
                        (Account, AccountLookup, AccountName, SubParent, Parent,
                         VW, Belastingaangifte, administration, Pattern, parameters)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        account['Account'],
                        account.get('AccountLookup'),
                        account['AccountName'],
                        account['SubParent'],
                        account['Parent'],
                        account['VW'],
                        account.get('Belastingaangifte'),
                        administration,
                        account.get('Pattern', False),
                        json.dumps(account['parameters']) if account.get('parameters') else None,
                    ),
                    commit=True
                )
                inserted += 1

            logger.info(
                f"Chart of accounts loaded for '{administration}': "
                f"{inserted} rows from {template_path.name}"
            )
            return {'status': 'created', 'rows': inserted}

        except Exception as e:
            msg = (
                f"Failed to load chart of accounts for '{administration}': {e}. "
                f"Add chart manually."
            )
            logger.error(msg)
            warnings.append(msg)
            return {'status': 'failed', 'rows': 0}
