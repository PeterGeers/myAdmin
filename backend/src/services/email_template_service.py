"""
Email Template Service

Handles rendering of email templates with variable substitution.
"""

import os
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class EmailTemplateService:
    """Service for rendering email templates"""
    
    def __init__(self):
        """Initialize the email template service"""
        # Templates are in backend/templates/email/, not backend/src/templates/email/
        src_dir = os.path.dirname(os.path.dirname(__file__))  # backend/src
        backend_dir = os.path.dirname(src_dir)  # backend
        self.template_dir = os.path.join(backend_dir, 'templates', 'email')
    
    def render_template(
        self,
        template_name: str,
        variables: Dict[str, str],
        format: str = 'html'
    ) -> Optional[str]:
        """
        Render an email template with variable substitution
        
        Args:
            template_name: Name of the template (without extension)
            variables: Dictionary of variables to substitute
            format: 'html' or 'txt'
        
        Returns:
            Rendered template content or None if template not found
        """
        try:
            # Construct template path
            extension = 'html' if format == 'html' else 'txt'
            template_path = os.path.join(
                self.template_dir,
                f"{template_name}.{extension}"
            )
            
            # Check if template exists
            if not os.path.exists(template_path):
                logger.error(f"Template not found: {template_path}")
                return None
            
            # Read template
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
            
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
