"""
Email Template Service

Handles rendering of email templates with variable substitution.
Supports both local file templates (defaults) and Google Drive templates (tenant-specific).
"""

import os
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class EmailTemplateService:
    """Service for rendering email templates"""
    
    def __init__(self, administration: Optional[str] = None):
        """
        Initialize the email template service
        
        Args:
            administration: Tenant name (for loading tenant-specific templates from Google Drive)
        """
        # Templates are in backend/templates/email/, not backend/src/templates/email/
        src_dir = os.path.dirname(os.path.dirname(__file__))  # backend/src
        backend_dir = os.path.dirname(src_dir)  # backend
        self.template_dir = os.path.join(backend_dir, 'templates', 'email')
        self.administration = administration
    
    def _load_from_google_drive(
        self,
        template_name: str,
        format: str = 'html'
    ) -> Optional[str]:
        """
        Load template from Google Drive (tenant-specific)
        
        Args:
            template_name: Name of the template (e.g., 'user_invitation')
            format: 'html' or 'txt'
        
        Returns:
            Template content from Google Drive or None if not found
        """
        if not self.administration:
            return None
        
        try:
            from database import DatabaseManager
            from google_drive_service import GoogleDriveService
            
            # Get active template from database
            db = DatabaseManager()
            query = """
                SELECT template_file_id, template_content
                FROM tenant_template_config
                WHERE administration = %s 
                  AND template_type = %s 
                  AND is_active = TRUE
                ORDER BY version DESC
                LIMIT 1
            """
            
            # Template type in DB is just the name (e.g., 'user_invitation')
            result = db.execute_query(query, [self.administration, template_name], fetch=True)
            
            if result and len(result) > 0:
                template_data = result[0]
                
                # If template_content is stored in DB, use it
                if template_data.get('template_content'):
                    logger.info(f"Loaded {template_name} template from database for {self.administration}")
                    return template_data['template_content']
                
                # Otherwise, load from Google Drive
                file_id = template_data.get('template_file_id')
                if file_id:
                    drive_service = GoogleDriveService(administration=self.administration)
                    content = drive_service.download_file_content(file_id)
                    
                    if content:
                        logger.info(f"Loaded {template_name} template from Google Drive for {self.administration}")
                        return content
            
            logger.debug(f"No custom {template_name} template found for {self.administration}")
            return None
            
        except Exception as e:
            logger.error(f"Error loading template from Google Drive: {e}")
            return None
    
    def render_template(
        self,
        template_name: str,
        variables: Dict[str, str],
        format: str = 'html',
        language: Optional[str] = None
    ) -> Optional[str]:
        """
        Render an email template with variable substitution
        
        Tries to load from Google Drive first (if administration is set),
        then falls back to local file templates.
        
        Args:
            template_name: Name of the template (without extension)
            variables: Dictionary of variables to substitute
            format: 'html' or 'txt'
            language: Language code ('nl' or 'en'). If None, defaults to 'nl'
        
        Returns:
            Rendered template content or None if template not found
        """
        try:
            template_content = None
            
            # Default to Dutch if no language specified
            if language is None:
                language = 'nl'
            
            # Try to load from Google Drive first (tenant-specific)
            if self.administration:
                template_content = self._load_from_google_drive(template_name, format)
            
            # Fall back to local file template
            if not template_content:
                extension = 'html' if format == 'html' else 'txt'
                
                # Try language-specific template first (e.g., user_invitation_nl.html)
                if language != 'en':
                    localized_template_path = os.path.join(
                        self.template_dir,
                        f"{template_name}_{language}.{extension}"
                    )
                    
                    if os.path.exists(localized_template_path):
                        with open(localized_template_path, 'r', encoding='utf-8') as f:
                            template_content = f.read()
                        logger.debug(f"Loaded {template_name} template ({language}) from local file")
                
                # Fall back to English template
                if not template_content:
                    template_path = os.path.join(
                        self.template_dir,
                        f"{template_name}.{extension}"
                    )
                    
                    if os.path.exists(template_path):
                        with open(template_path, 'r', encoding='utf-8') as f:
                            template_content = f.read()
                        logger.debug(f"Loaded {template_name} template (en) from local file")
                    else:
                        logger.error(f"Template not found: {template_path}")
                        return None
            
            # Substitute variables
            rendered_content = template_content
            for key, value in variables.items():
                placeholder = f"{{{{{key}}}}}"  # {{variable}}
                rendered_content = rendered_content.replace(placeholder, str(value))
            
            return rendered_content
            
        except Exception as e:
            logger.error(f"Error rendering template {template_name}: {e}")
            return None
    
    def render_user_invitation(
        self,
        email: str,
        temporary_password: str,
        tenant: str,
        login_url: Optional[str] = None,
        format: str = 'html',
        language: Optional[str] = None
    ) -> Optional[str]:
        """
        Render user invitation email template
        
        Args:
            email: User's email address
            temporary_password: Temporary password
            tenant: Tenant name
            login_url: Login URL (defaults to FRONTEND_URL env var)
            format: 'html' or 'txt'
            language: Language code ('nl' or 'en'). If None, detects from user/tenant
        
        Returns:
            Rendered email content
        """
        if login_url is None:
            login_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
        
        # Detect language if not provided
        if language is None:
            language = self._detect_user_language(email, tenant)
        
        variables = {
            'email': email,
            'temporary_password': temporary_password,
            'tenant': tenant,
            'login_url': login_url
        }
        
        return self.render_template('user_invitation', variables, format, language)
    
    def _detect_user_language(self, email: str, tenant: str) -> str:
        """
        Detect user's preferred language
        
        Priority:
        1. User's preferred language from Cognito custom attribute
        2. Tenant's default language
        3. Default to 'nl'
        
        Args:
            email: User's email address
            tenant: Tenant name
        
        Returns:
            Language code ('nl' or 'en')
        """
        try:
            # Try to get user's preferred language from Cognito
            from services.user_language_service import get_user_language
            user_lang = get_user_language(email)
            if user_lang and user_lang in ['nl', 'en']:
                logger.debug(f"Using user language: {user_lang}")
                return user_lang
        except Exception as e:
            logger.debug(f"Could not get user language: {e}")
        
        try:
            # Fall back to tenant's default language
            from services.tenant_language_service import get_tenant_language
            tenant_lang = get_tenant_language(tenant)
            if tenant_lang and tenant_lang in ['nl', 'en']:
                logger.debug(f"Using tenant language: {tenant_lang}")
                return tenant_lang
        except Exception as e:
            logger.debug(f"Could not get tenant language: {e}")
        
        # Default to Dutch
        logger.debug("Using default language: nl")
        return 'nl'
    
    def get_invitation_subject(self, tenant: str, language: Optional[str] = None) -> str:
        """
        Get subject line for invitation email
        
        Args:
            tenant: Tenant name
            language: Language code ('nl' or 'en')
        
        Returns:
            Email subject line
        """
        if language == 'nl':
            return f"Welkom bij myAdmin - {tenant} Uitnodiging"
        else:
            return f"Welcome to myAdmin - {tenant} Invitation"
