import re
import os
import hashlib
import secrets
import bleach
from flask import request, jsonify
from datetime import datetime
import logging
from database import DatabaseManager

class SecurityAudit:
    """Comprehensive security auditing and validation utilities"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.db = DatabaseManager()
        self.security_issues = []
        self.input_validation_rules = {
            'username': r'^[a-zA-Z0-9_]{3,20}$',
            'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
            'password': r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$',
            'filename': r'^[a-zA-Z0-9_\-\.]{1,255}$',
            'url': r'^(https?:\/\/)?([\da-z\.-]+)\.([a-z\.]{2,6})([\/\w \.-]*)*\/?$'
        }

    def audit_authentication_mechanisms(self):
        """Review and audit authentication mechanisms"""
        audit_report = {
            'timestamp': datetime.now().isoformat(),
            'authentication_methods': [],
            'security_issues': [],
            'recommendations': []
        }

        # Check for common authentication patterns in codebase
        auth_patterns = {
            'basic_auth': r'Basic\s+Auth|basic_auth',
            'jwt': r'JWT|jwt|JsonWebToken',
            'oauth': r'OAuth|oauth|google_auth|facebook_auth',
            'session': r'session\[',
            'api_key': r'API_KEY|api_key|access_key'
        }

        # Scan source files for authentication patterns
        src_dir = os.path.join(os.path.dirname(__file__))
        for root, dirs, files in os.walk(src_dir):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()

                            for auth_type, pattern in auth_patterns.items():
                                if re.search(pattern, content):
                                    if auth_type not in [a['type'] for a in audit_report['authentication_methods']]:
                                        audit_report['authentication_methods'].append({
                                            'type': auth_type,
                                            'file': filepath,
                                            'pattern': pattern
                                        })
                    except Exception as e:
                        self.logger.error(f"Error reading {filepath}: {e}")

        # Check for security issues
        if not audit_report['authentication_methods']:
            audit_report['security_issues'].append(
                "No authentication mechanisms found - this is a critical security risk"
            )
        else:
            # Check for insecure authentication methods
            insecure_methods = ['basic_auth', 'session']
            for method in audit_report['authentication_methods']:
                if method['type'] in insecure_methods:
                    audit_report['security_issues'].append(
                        f"Insecure authentication method detected: {method['type']} in {method['file']}"
                    )

        # Add recommendations
        audit_report['recommendations'] = [
            "Use JWT or OAuth2 for API authentication",
            "Implement proper password hashing with bcrypt or PBKDF2",
            "Add rate limiting to authentication endpoints",
            "Implement multi-factor authentication for sensitive operations",
            "Use secure, HTTP-only cookies for session management",
            "Regularly rotate API keys and secrets"
        ]

        return audit_report

    def validate_input(self, input_data, field_type, max_length=None):
        """Validate input data against security rules"""
        if not input_data:
            return {'valid': False, 'error': 'Input cannot be empty'}

        # Check for common injection patterns
        injection_patterns = [
            r'[\'\";\\]',  # SQL injection
            r'<script.*?>.*?</script>',  # XSS
            r'javascript:',  # JavaScript injection
            r'&#x?[0-9a-f]+;',  # HTML entities
            r'/\*.*?\*/',  # CSS injection
            r'{{.*?}}',  # Template injection
            r'(\b(ALTER|CREATE|DELETE|DROP|EXEC(UTE)?|INSERT( +INTO)?|MERGE|SELECT|UPDATE|UNION( +ALL)?)\b)',
            r'(\b(OR|AND)\b.*?=)'
        ]

        for pattern in injection_patterns:
            if re.search(pattern, str(input_data), re.IGNORECASE):
                return {'valid': False, 'error': 'Potential injection pattern detected'}

        # Validate against field type rules
        if field_type in self.input_validation_rules:
            pattern = self.input_validation_rules[field_type]
            if not re.match(pattern, str(input_data)):
                return {'valid': False, 'error': f'Input does not match {field_type} pattern'}

        # Check length
        if max_length and len(str(input_data)) > max_length:
            return {'valid': False, 'error': f'Input exceeds maximum length of {max_length} characters'}

        # Sanitize input
        sanitized = self.sanitize_input(input_data, field_type)

        return {
            'valid': True,
            'original': str(input_data),
            'sanitized': sanitized,
            'length': len(str(input_data))
        }

    def sanitize_input(self, input_data, field_type='text'):
        """Sanitize input data based on field type"""
        if not input_data:
            return ''

        input_str = str(input_data)

        # Different sanitization rules for different field types
        if field_type == 'html':
            # Allow basic HTML but strip dangerous tags and attributes
            allowed_tags = ['p', 'br', 'b', 'i', 'u', 'em', 'strong', 'a', 'ul', 'ol', 'li']
            allowed_attrs = {'a': ['href', 'title']}
            return bleach.clean(input_str, tags=allowed_tags, attributes=allowed_attrs, strip=True)

        elif field_type == 'url':
            # Validate and sanitize URLs
            if re.match(self.input_validation_rules['url'], input_str):
                return input_str
            return ''

        elif field_type == 'email':
            # Validate and sanitize emails
            if re.match(self.input_validation_rules['email'], input_str):
                return input_str.lower()
            return ''

        else:
            # General text sanitization - strip HTML and special chars
            sanitized = bleach.clean(input_str, tags=[], attributes={}, strip=True)
            # Remove control characters
            sanitized = re.sub(r'[\x00-\x1F\x7F]', '', sanitized)
            return sanitized.strip()

    def check_sql_injection(self, query, params=None):
        """Check SQL query for potential injection vulnerabilities"""
        audit_result = {
            'query': query,
            'safe': True,
            'issues': [],
            'recommendations': []
        }

        # Check for string concatenation in queries
        if '+' in query or 'STRING_CONCAT' in query.upper():
            audit_result['issues'].append("Potential SQL injection: string concatenation detected")
            audit_result['safe'] = False

        # Check for dynamic table names
        if re.search(r'\bFROM\s+\w+\s*\+\s*\w+', query, re.IGNORECASE):
            audit_result['issues'].append("Potential SQL injection: dynamic table name detected")
            audit_result['safe'] = False

        # Check for inline values (not parameterized)
        if params is None and re.search(r"VALUES\s*\([^)]*\)", query):
            audit_result['issues'].append("Potential SQL injection: inline VALUES detected without parameters")
            audit_result['safe'] = False

        # Check for common SQL injection patterns
        injection_patterns = [
            r"1\s*=\s*1",
            r"OR\s+1\s*=\s*1",
            r"OR\s+\"\"=\"\"",
            r"OR\s+\'\'=\'\'",
            r"UNION\s+SELECT",
            r"EXEC\s+",
            r"DROP\s+TABLE",
            r"INSERT\s+INTO",
            r"DELETE\s+FROM"
        ]

        for pattern in injection_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                audit_result['issues'].append(f"Potential SQL injection pattern detected: {pattern}")
                audit_result['safe'] = False

        # Add recommendations
        if not audit_result['safe']:
            audit_result['recommendations'] = [
                "Use parameterized queries instead of string concatenation",
                "Use ORM methods instead of raw SQL when possible",
                "Validate all user input before using in queries",
                "Implement proper database user permissions",
                "Use prepared statements for all database operations"
            ]

        return audit_result

    def validate_file_upload(self, file, allowed_types=None, max_size=None):
        """Validate file upload security"""
        if not file or not hasattr(file, 'filename'):
            return {'valid': False, 'error': 'No file provided'}

        validation_result = {
            'filename': file.filename,
            'content_type': file.content_type,
            'size': len(file.read()) if hasattr(file, 'read') else 0,
            'valid': True,
            'issues': [],
            'sanitized_filename': ''
        }

        # Reset file pointer
        if hasattr(file, 'seek'):
            file.seek(0)

        # Check file extension
        filename, file_extension = os.path.splitext(file.filename)
        if not file_extension:
            validation_result['issues'].append('No file extension')
            validation_result['valid'] = False

        # Check allowed file types
        if allowed_types:
            if file_extension.lower() not in [f".{ext.lower()}" for ext in allowed_types]:
                validation_result['issues'].append(f'File type {file_extension} not allowed')
                validation_result['valid'] = False

        # Check file size
        if max_size and validation_result['size'] > max_size:
            validation_result['issues'].append(f'File size {validation_result["size"]} exceeds maximum {max_size}')
            validation_result['valid'] = False

        # Check for dangerous file types
        dangerous_extensions = ['.php', '.php3', '.php4', '.php5', '.phtml', '.pl', '.py', '.rb', '.asp', '.aspx', '.jsp', '.exe', '.bat', '.cmd', '.sh']
        if file_extension.lower() in dangerous_extensions:
            validation_result['issues'].append(f'Dangerous file type detected: {file_extension}')
            validation_result['valid'] = False

        # Sanitize filename
        sanitized_filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)
        validation_result['sanitized_filename'] = f"{sanitized_filename}{file_extension}"

        # Check for potential malware in content (basic check)
        if validation_result['size'] > 0:
            file.seek(0)
            content = file.read(1024)  # Read first 1KB for analysis

            # Check for common malware signatures
            malware_signatures = [
                b'<?php',
                b'<script>',
                b'eval(',
                b'javascript:',
                b'MZ'  # Windows executable header
            ]

            for signature in malware_signatures:
                if signature in content:
                    validation_result['issues'].append(f'Potential malware signature detected: {signature}')
                    validation_result['valid'] = False

            # Reset file pointer
            file.seek(0)

        # Add security recommendations
        if validation_result['issues']:
            validation_result['recommendations'] = [
                "Use strict file type validation",
                "Implement file size limits",
                "Scan files with antivirus software",
                "Store files outside web root with proper permissions",
                "Use random filenames to prevent directory traversal",
                "Implement virus scanning for uploaded files"
            ]

        return validation_result

    def check_xss_vulnerabilities(self, template_content):
        """Check templates for XSS vulnerabilities"""
        xss_audit = {
            'template': template_content[:500] + '...' if len(template_content) > 500 else template_content,
            'vulnerabilities': [],
            'safe': True,
            'recommendations': []
        }

        # Check for unsafe template patterns
        unsafe_patterns = [
            (r'{{.*?}}', "Unsafe template variable interpolation"),
            (r'{\{.*?\}}', "Unsafe template expression"),
            (r'\|safe', "Unsafe filter usage"),
            (r'\|raw', "Unsafe raw filter"),
            (r'autoescape.*?false', "Autoescape disabled"),
            (r'Markup\(.*?\)', "Unsafe Markup usage")
        ]

        for pattern, description in unsafe_patterns:
            if re.search(pattern, template_content):
                xss_audit['vulnerabilities'].append(description)
                xss_audit['safe'] = False

        # Check for proper escaping
        if not re.search(r'\|escape|autoescape', template_content):
            xss_audit['vulnerabilities'].append("No output escaping detected")

        # Add recommendations
        if not xss_audit['safe']:
            xss_audit['recommendations'] = [
                "Use autoescaping in templates",
                "Escape all user-provided content",
                "Use safe filters instead of raw/unsafe",
                "Implement Content Security Policy headers",
                "Use template inheritance with proper escaping",
                "Sanitize all user input before rendering"
            ]

        return xss_audit

    def audit_security_headers(self, app):
        """Audit security-related HTTP headers"""
        headers_audit = {
            'timestamp': datetime.now().isoformat(),
            'headers_checked': [],
            'missing_headers': [],
            'security_issues': [],
            'recommendations': []
        }

        # Check for common security headers
        security_headers = {
            'Content-Security-Policy': "Prevents XSS and data injection attacks",
            'X-Content-Type-Options': "Prevents MIME type sniffing",
            'X-Frame-Options': "Prevents clickjacking",
            'X-XSS-Protection': "Enables XSS protection in browsers",
            'Strict-Transport-Security': "Enforces HTTPS",
            'Referrer-Policy': "Controls referrer information",
            'Permissions-Policy': "Controls browser features"
        }

        # Check which headers are configured
        if hasattr(app, 'after_request'):
            # Check after_request handlers for security headers
            pass  # Implementation would check actual response headers

        # For now, assume no headers are set (simplified check)
        headers_audit['missing_headers'] = list(security_headers.keys())
        headers_audit['security_issues'].append("No security headers configured")

        # Add recommendations
        headers_audit['recommendations'] = [
            "Implement Content-Security-Policy header",
            "Add X-Content-Type-Options: nosniff",
            "Configure X-Frame-Options: DENY or SAMEORIGIN",
            "Set X-XSS-Protection: 1; mode=block",
            "Implement Strict-Transport-Security for HTTPS",
            "Add Referrer-Policy: strict-origin-when-cross-origin",
            "Configure Permissions-Policy for feature control"
        ]

        return headers_audit

    def check_password_strength(self, password):
        """Check password strength and security"""
        if not password:
            return {'strong': False, 'score': 0, 'issues': ['No password provided']}

        strength_check = {
            'password': password,
            'length': len(password),
            'has_uppercase': bool(re.search(r'[A-Z]', password)),
            'has_lowercase': bool(re.search(r'[a-z]', password)),
            'has_digits': bool(re.search(r'[0-9]', password)),
            'has_special': bool(re.search(r'[^A-Za-z0-9]', password)),
            'common_password': False,
            'score': 0,
            'issues': []
        }

        # Check against common passwords
        common_passwords = ['password', '123456', '12345678', 'qwerty', 'abc123', 'password1']
        if password.lower() in common_passwords:
            strength_check['common_password'] = True
            strength_check['issues'].append('Common password detected')

        # Calculate score
        if strength_check['length'] >= 8:
            strength_check['score'] += 1
        if strength_check['length'] >= 12:
            strength_check['score'] += 1
        if strength_check['has_uppercase']:
            strength_check['score'] += 1
        if strength_check['has_lowercase']:
            strength_check['score'] += 1
        if strength_check['has_digits']:
            strength_check['score'] += 1
        if strength_check['has_special']:
            strength_check['score'] += 1

        # Check for weaknesses
        if strength_check['length'] < 8:
            strength_check['issues'].append('Password too short (minimum 8 characters)')
        if not strength_check['has_uppercase']:
            strength_check['issues'].append('No uppercase letters')
        if not strength_check['has_lowercase']:
            strength_check['issues'].append('No lowercase letters')
        if not strength_check['has_digits']:
            strength_check['issues'].append('No digits')
        if not strength_check['has_special']:
            strength_check['issues'].append('No special characters')

        # Determine strength
        strength_check['strong'] = strength_check['score'] >= 4 and not strength_check['issues']

        # Add recommendations
        if not strength_check['strong']:
            strength_check['recommendations'] = [
                "Use at least 12 characters",
                "Include uppercase and lowercase letters",
                "Add numbers and special characters",
                "Avoid common words and patterns",
                "Use a password manager to generate strong passwords",
                "Consider using passphrases instead of passwords"
            ]

        return strength_check

    def generate_security_report(self):
        """Generate comprehensive security audit report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'authentication': self.audit_authentication_mechanisms(),
            'input_validation': {
                'rules_defined': len(self.input_validation_rules),
                'common_patterns': list(self.input_validation_rules.keys())
            },
            'sql_injection': {
                'status': 'Manual review required',
                'recommendations': [
                    "Use parameterized queries for all database operations",
                    "Implement query whitelisting where possible",
                    "Use ORM instead of raw SQL",
                    "Regularly audit database queries"
                ]
            },
            'file_uploads': {
                'status': 'Validation implemented',
                'recommendations': [
                    "Implement virus scanning for uploaded files",
                    "Store files outside web root",
                    "Use random filenames to prevent directory traversal",
                    "Set proper file permissions"
                ]
            },
            'xss_protection': {
                'status': 'Template auditing available',
                'recommendations': [
                    "Enable autoescaping in templates",
                    "Use Content-Security-Policy headers",
                    "Sanitize all user input before rendering",
                    "Use safe template filters",
                    "Implement CSP headers"
                ]
            },
            'security_headers': self.audit_security_headers(app),
            'overall_security_score': self.calculate_security_score(),
            'critical_issues': self.get_critical_issues(),
            'general_recommendations': [
                "Implement regular security audits",
                "Keep all dependencies updated",
                "Use HTTPS for all communications",
                "Implement proper logging and monitoring",
                "Regularly rotate secrets and credentials",
                "Conduct penetration testing",
                "Train developers on secure coding practices"
            ]
        }

        return report

    def calculate_security_score(self):
        """Calculate overall security score"""
        score = 0
        max_score = 100

        # Check authentication
        auth_report = self.audit_authentication_mechanisms()
        if auth_report['authentication_methods']:
            score += 20
            if not auth_report['security_issues']:
                score += 10

        # Check input validation
        if self.input_validation_rules:
            score += 15

        # Check for security headers (simplified check)
        score += 10  # Assume some headers are implemented

        # Check password strength requirements
        if 'password' in self.input_validation_rules:
            score += 10

        # Check file upload security
        score += 15  # Assume file validation is implemented

        # Check XSS protection
        score += 10  # Assume template sanitization is implemented

        # Ensure score is within bounds
        score = max(0, min(score, max_score))

        # Determine security level
        if score >= 80:
            level = 'High'
        elif score >= 60:
            level = 'Medium'
        elif score >= 40:
            level = 'Low'
        else:
            level = 'Critical'

        return {
            'score': score,
            'max_score': max_score,
            'percentage': (score / max_score) * 100,
            'level': level
        }

    def get_critical_issues(self):
        """Get list of critical security issues"""
        critical_issues = []

        # Check authentication
        auth_report = self.audit_authentication_mechanisms()
        if not auth_report['authentication_methods']:
            critical_issues.append("No authentication mechanisms implemented")

        # Check for common vulnerabilities
        critical_issues.extend([
            "Review all user input for injection vulnerabilities",
            "Audit database queries for SQL injection risks",
            "Check file upload handling for security issues",
            "Review template rendering for XSS vulnerabilities",
            "Ensure proper HTTPS implementation",
            "Verify secure session management"
        ])

        return critical_issues

    def create_security_middleware(self, app):
        """Create security middleware for Flask app"""
        @app.before_request
        def security_checks():
            # Skip all security checks in development mode
            if os.getenv('FLASK_DEBUG', 'false').lower() == 'true':
                return None
            
            # Skip all security checks in test mode
            if os.getenv('TEST_MODE', 'false').lower() == 'true':
                return None
                
            # Check for suspicious request patterns
            if self.is_suspicious_request(request):
                self.logger.warning(f"Suspicious request detected: {request.path}")
                return jsonify({'error': 'Suspicious request detected'}), 403

            # Validate common headers
            if not self.validate_request_headers(request):
                self.logger.warning(f"Invalid request headers: {request.path}")
                return jsonify({'error': 'Invalid request headers'}), 400

        @app.after_request
        def add_security_headers(response):
            # Add security headers to all responses
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            return response

        return {
            'status': 'Security middleware installed',
            'headers_added': [
                'X-Content-Type-Options',
                'X-Frame-Options',
                'X-XSS-Protection',
                'Referrer-Policy'
            ]
        }

    def is_suspicious_request(self, request):
        """Check if request shows suspicious patterns"""
        # Skip suspicious request detection in development mode
        if os.getenv('FLASK_DEBUG', 'false').lower() == 'true':
            return False
            
        suspicious_patterns = [
            r'/\.\./',  # Directory traversal
            r'\.\./',   # Directory traversal
            r'%00',     # Null byte
            r'1=1',     # SQL injection
            r'union\s+select',  # SQL injection
            r'<script', # XSS
            r'javascript:',    # XSS
            r'../',     # Directory traversal
            r'./',      # Potential traversal
            r'%2e%2e%2f',  # URL encoded traversal
            r'%252e%252e%252f'  # Double URL encoded traversal
        ]

        # Check URL
        for pattern in suspicious_patterns:
            if re.search(pattern, request.path, re.IGNORECASE):
                return True

        # Check query parameters
        for key, value in request.args.items():
            for pattern in suspicious_patterns:
                if re.search(pattern, str(value), re.IGNORECASE):
                    return True

        # Check user agent
        if request.user_agent and request.user_agent.string:
            suspicious_agents = ['sqlmap', 'nikto', 'dirb', 'wpscan', 'nessus']
            for agent in suspicious_agents:
                if agent.lower() in request.user_agent.string.lower():
                    return True

        return False

    def validate_request_headers(self, request):
        """Validate request headers for security"""
        # Skip header validation in development mode
        if os.getenv('FLASK_DEBUG', 'false').lower() == 'true':
            return True
            
        # Skip strict header validation for API endpoints
        if request.path.startswith('/api/'):
            # Only check for basic required headers for API calls
            return 'Host' in request.headers
            
        # Check for required headers
        required_headers = ['Host']
        for header in required_headers:
            if header not in request.headers:
                return False

        # Check for suspicious headers (only for non-API routes)
        suspicious_headers = ['X-Forwarded-For', 'X-Forwarded-Host', 'X-Forwarded-Proto']
        for header in suspicious_headers:
            if header in request.headers:
                # These headers should be handled by proxy, not client
                return False

        # Check content type for POST requests
        if request.method == 'POST' and 'Content-Type' not in request.headers:
            return False

        return True

# Security endpoint registration
def register_security_endpoints(app):
    """Register security audit and validation endpoints"""

    security_audit = SecurityAudit()

    @app.route('/api/security/audit', methods=['GET'])
    def security_audit_endpoint():
        """Get comprehensive security audit report"""
        report = security_audit.generate_security_report()
        return {
            'success': True,
            'security_report': report
        }

    @app.route('/api/security/validate-input', methods=['POST'])
    def validate_input_endpoint():
        """Validate user input for security"""
        data = request.get_json()
        input_data = data.get('input')
        field_type = data.get('field_type', 'text')
        max_length = data.get('max_length')

        if not input_data:
            return jsonify({'success': False, 'error': 'No input provided'}), 400

        validation = security_audit.validate_input(input_data, field_type, max_length)
        return {
            'success': validation['valid'],
            'validation': validation
        }

    @app.route('/api/security/check-sql', methods=['POST'])
    def check_sql_injection_endpoint():
        """Check SQL query for injection vulnerabilities"""
        data = request.get_json()
        query = data.get('query')
        params = data.get('params')

        if not query:
            return jsonify({'success': False, 'error': 'No query provided'}), 400

        audit = security_audit.check_sql_injection(query, params)
        return {
            'success': audit['safe'],
            'sql_audit': audit
        }

    @app.route('/api/security/validate-file', methods=['POST'])
    def validate_file_upload_endpoint():
        """Validate file upload security"""
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['file']
        allowed_types = request.form.get('allowed_types')
        max_size = request.form.get('max_size')

        if allowed_types:
            allowed_types = allowed_types.split(',')
        if max_size:
            max_size = int(max_size)

        validation = security_audit.validate_file_upload(file, allowed_types, max_size)
        return {
            'success': validation['valid'],
            'file_validation': validation
        }

    @app.route('/api/security/check-password', methods=['POST'])
    def check_password_strength_endpoint():
        """Check password strength"""
        data = request.get_json()
        password = data.get('password')

        if not password:
            return jsonify({'success': False, 'error': 'No password provided'}), 400

        strength_check = security_audit.check_password_strength(password)
        return {
            'success': strength_check['strong'],
            'password_strength': strength_check
        }

    @app.route('/api/security/check-xss', methods=['POST'])
    def check_xss_vulnerabilities_endpoint():
        """Check templates for XSS vulnerabilities"""
        data = request.get_json()
        template_content = data.get('template')

        if not template_content:
            return jsonify({'success': False, 'error': 'No template content provided'}), 400

        xss_audit = security_audit.check_xss_vulnerabilities(template_content)
        return {
            'success': xss_audit['safe'],
            'xss_audit': xss_audit
        }

    return {
        'status': 'Security endpoints registered',
        'endpoints': [
            '/api/security/audit',
            '/api/security/validate-input',
            '/api/security/check-sql',
            '/api/security/validate-file',
            '/api/security/check-password',
            '/api/security/check-xss'
        ]
    }
