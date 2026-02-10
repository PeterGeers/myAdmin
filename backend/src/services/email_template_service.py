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
        format: str = 'html'
    ) -> Optional[str]:
        """
        Render an email template with variable substitution
        
        Tries to load from Google Drive first (if administration is set),
        then falls back to local file templates.
        
        Args:
            template_name: Name of the template (without extension)
            variables: Dictionary of variables to substitute
            format: 'html' or 'txt'
        
        Returns:
            Rendered template content or None if template not found
        """
        try:
            template_content = None
            
            # Try to load from Google Drive first (tenant-specific)
            if self.administration:
                template_content = self._load_from_google_drive(template_name, format)
            
            # Fall back to local file template
            if not template_content:
                extension = 'html' if format == 'html' else 'txt'
                template_path = os.path.join(
                    self.template_dir,
                    f"{template_name}.{extension}"
                )
                
                if os.path.exists(template_path):
                    with open(template_path, 'r', encoding='utf-8') as f:
                        template_content = f.read()
                    logger.debug(f"Loaded {template_name} template from local file")
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
        format: str = 'html'
    ) -> Optional[str]:
        """
        Render user invitation email template
        
        Args:
            email: User's email address
            temporary_password: Temporary password
            tenant: Tenant name
            login_url: Login URL (defaults to FRONTEND_URL env var)
            format: 'html' or 'txt'
        
        Returns:
            Rendered email content
        """
        if login_url is None:
            login_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
        
        variables = {
            'email': email,
            'temporary_password': temporary_password,
            'tenant': tenant,
            'login_url': login_url
        }
        
        return self.render_template('user_invitation', variables, format)
    
    def get_invitation_subject(self, tenant: str) -> str:
        """
        Get subject line for invitation email
        
        Args:
            tenant: Tenant name
        
        Returns:
            Email subject line
        """
        return f"Welcome to myAdmin - {tenant} Invitation"
