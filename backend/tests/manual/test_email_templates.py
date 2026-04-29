"""
Test Email Templates

This script tests the email template rendering without sending actual emails.
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from services.email_template_service import EmailTemplateService


def test_email_templates():
    """Test email template rendering"""
    
    print("=" * 80)
    print("Testing Email Template Rendering")
    print("=" * 80)
    print()
    
    # Initialize service
    email_service = EmailTemplateService()
    
    # Test data
    test_data = {
        'email': 'john.doe@example.com',
        'temporary_password': 'TempPass123!',
        'tenant': 'GoodwinSolutions',
        'login_url': 'http://localhost:3000'
    }
    
    # Test HTML template
    print("1. Testing HTML Template")
    print("-" * 80)
    html_content = email_service.render_user_invitation(
        email=test_data['email'],
        temporary_password=test_data['temporary_password'],
        tenant=test_data['tenant'],
        login_url=test_data['login_url'],
        format='html'
    )
    
    if html_content:
        print("✅ HTML template rendered successfully")
        print(f"   Length: {len(html_content)} characters")
        
        # Save to file for inspection
        output_path = os.path.join(os.path.dirname(__file__), 'test_invitation.html')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"   Saved to: {output_path}")
        print(f"   Open in browser to preview")
    else:
        print("❌ HTML template rendering failed")
    
    print()
    
    # Test plain text template
    print("2. Testing Plain Text Template")
    print("-" * 80)
    text_content = email_service.render_user_invitation(
        email=test_data['email'],
        temporary_password=test_data['temporary_password'],
        tenant=test_data['tenant'],
        login_url=test_data['login_url'],
        format='txt'
    )
    
    if text_content:
        print("✅ Plain text template rendered successfully")
        print(f"   Length: {len(text_content)} characters")
        print()
        print("   Preview:")
        print("   " + "-" * 76)
        # Print first 20 lines
        lines = text_content.split('\n')
        for line in lines[:20]:
            print(f"   {line}")
        if len(lines) > 20:
            print(f"   ... ({len(lines) - 20} more lines)")
        print("   " + "-" * 76)
    else:
        print("❌ Plain text template rendering failed")
    
    print()
    
    # Test subject line
    print("3. Testing Subject Line")
    print("-" * 80)
    subject = email_service.get_invitation_subject(test_data['tenant'])
    print(f"✅ Subject: {subject}")
    
    print()
    print("=" * 80)
    print("Template Testing Complete")
    print("=" * 80)
    
    # Return success status
    return html_content is not None and text_content is not None


if __name__ == '__main__':
    success = test_email_templates()
    sys.exit(0 if success else 1)
