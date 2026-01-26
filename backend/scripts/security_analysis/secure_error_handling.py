#!/usr/bin/env python3
"""
Secure Error Handling Implementation
Provides secure error handling patterns for STR Reports
"""

import logging
import re
from typing import Tuple, Dict, Any

# Configure logging for security analysis
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SecureErrorHandler:
    """Handles errors securely without leaking sensitive information"""
    
    # Generic error messages for different categories
    ERROR_MESSAGES = {
        'database': 'Database operation failed',
        'validation': 'Invalid input provided',
        'authentication': 'Authentication failed',
        'authorization': 'Access denied',
        'not_found': 'Resource not found',
        'internal': 'Internal server error',
        'network': 'Network connection error'
    }
    
    @staticmethod
    def categorize_error(exception: Exception) -> str:
        """Categorize exception to determine appropriate user message"""
        error_str = str(exception).lower()
        
        # Database-related errors
        if any(keyword in error_str for keyword in ['mysql', 'connection', 'database', 'cursor', 'sql']):
            return 'database'
        
        # Network-related errors
        if any(keyword in error_str for keyword in ['timeout', 'network', 'connection refused']):
            return 'network'
        
        # Validation errors
        if any(keyword in error_str for keyword in ['invalid', 'required', 'missing']):
            return 'validation'
        
        # Default to internal error
        return 'internal'
    
    @staticmethod
    def handle_error(exception: Exception, context: str = "", log_details: bool = True) -> Tuple[Dict[str, Any], int]:
        """
        Handle exception securely
        
        Args:
            exception: The exception that occurred
            context: Context information for logging
            log_details: Whether to log detailed error information
            
        Returns:
            Tuple of (response_dict, status_code)
        """
        if log_details:
            logger.error(f"Error in {context}: {str(exception)}", exc_info=True)
        
        error_category = SecureErrorHandler.categorize_error(exception)
        user_message = SecureErrorHandler.ERROR_MESSAGES.get(error_category, 'Internal server error')
        
        return {
            'success': False,
            'error': user_message
        }, 500
    
    @staticmethod
    def handle_validation_error(message: str) -> Tuple[Dict[str, Any], int]:
        """Handle validation errors with specific message"""
        return {
            'success': False,
            'error': message
        }, 400
    
    @staticmethod
    def handle_authorization_error(message: str = None) -> Tuple[Dict[str, Any], int]:
        """Handle authorization errors"""
        return {
            'success': False,
            'error': message or SecureErrorHandler.ERROR_MESSAGES['authorization']
        }, 403
    
    @staticmethod
    def handle_not_found_error(resource: str = "Resource") -> Tuple[Dict[str, Any], int]:
        """Handle not found errors"""
        return {
            'success': False,
            'error': f"{resource} not found"
        }, 404

def apply_secure_error_handling():
    """Apply secure error handling to route files"""
    
    files_to_fix = [
        'backend/src/bnb_routes.py',
        'backend/src/str_channel_routes.py',
        'backend/src/str_invoice_routes.py'
    ]
    
    print("=" * 80)
    print("APPLYING SECURE ERROR HANDLING FIXES")
    print("=" * 80)
    print()
    
    for filepath in files_to_fix:
        print(f"📁 Processing: {filepath}")
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Add logging import if not present
            if 'import logging' not in content and 'from logging import' not in content:
                # Find the first import line and add logging import after it
                lines = content.split('\n')
                import_line_found = False
                for i, line in enumerate(lines):
                    if line.startswith('from ') or line.startswith('import '):
                        if not import_line_found:
                            lines.insert(i + 1, 'import logging')
                            import_line_found = True
                            break
                
                if not import_line_found:
                    # Add at the beginning if no imports found
                    lines.insert(0, 'import logging')
                
                content = '\n'.join(lines)
            
            # Add logger configuration if not present
            if 'logger = logging.getLogger' not in content:
                # Add after imports
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if line.strip() and not (line.startswith('from ') or line.startswith('import ') or line.startswith('#')):
                        lines.insert(i, 'logger = logging.getLogger(__name__)')
                        lines.insert(i + 1, '')
                        break
                content = '\n'.join(lines)
            
            # Replace dangerous error patterns
            patterns_to_replace = [
                # Pattern 1: return jsonify({'success': False, 'error': str(e)}), 500
                (
                    r"return jsonify\(\{'success': False, 'error': str\(e\)\}\), 500",
                    "logger.error(f'Error in endpoint: {str(e)}')\n        return jsonify({'success': False, 'error': 'Internal server error'}), 500"
                ),
                # Pattern 2: return jsonify({"success": False, "error": str(e)}), 500
                (
                    r'return jsonify\(\{"success": False, "error": str\(e\)\}\), 500',
                    'logger.error(f\'Error in endpoint: {str(e)}\')\n        return jsonify({"success": False, "error": "Internal server error"}), 500'
                ),
                # Pattern 3: 'error': str(e) in dictionaries
                (
                    r"'error': str\(e\)",
                    "'error': 'Internal server error'"
                ),
                # Pattern 4: "error": str(e) in dictionaries
                (
                    r'"error": str\(e\)',
                    '"error": "Internal server error"'
                )
            ]
            
            original_content = content
            replacements_made = 0
            
            for pattern, replacement in patterns_to_replace:
                new_content = re.sub(pattern, replacement, content)
                if new_content != content:
                    replacements_made += len(re.findall(pattern, content))
                    content = new_content
            
            if content != original_content:
                # Create backup
                backup_path = filepath + '.backup'
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(original_content)
                
                # Write fixed content
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                print(f"  ✅ Fixed {replacements_made} error handling issues")
                print(f"  📄 Backup created: {backup_path}")
            else:
                print(f"  ℹ️  No changes needed")
            
        except Exception as e:
            print(f"  ❌ Error processing file: {str(e)}")
        
        print()
    
    print("🎯 SECURE ERROR HANDLING IMPLEMENTATION COMPLETE")
    print()
    print("📋 SUMMARY OF CHANGES:")
    print("- Added logging imports where missing")
    print("- Added logger configuration")
    print("- Replaced str(e) with generic error messages")
    print("- Added proper error logging for debugging")
    print("- Created backups of original files")
    print()
    print("⚠️  IMPORTANT NOTES:")
    print("- Review the changes before deploying")
    print("- Test all endpoints to ensure functionality")
    print("- Monitor logs for detailed error information")
    print("- Consider implementing error categorization for better UX")

if __name__ == '__main__':
    apply_secure_error_handling()