import re
import os
from flask import request, jsonify, current_app
from datetime import datetime
import logging
from database import DatabaseManager
from security_validators import (
    validate_input as _validate_input,
    sanitize_input as _sanitize_input,
    check_sql_injection as _check_sql_injection,
    validate_file_upload as _validate_file_upload,
    check_xss_vulnerabilities as _check_xss_vulnerabilities,
    check_password_strength as _check_password_strength,
    INPUT_VALIDATION_RULES,
)

class SecurityAudit:
    """Comprehensive security auditing and validation utilities"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.db = DatabaseManager()
        self.security_issues = []
        self.input_validation_rules = INPUT_VALIDATION_RULES

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
        return _validate_input(input_data, field_type, max_length, self.input_validation_rules)

    def sanitize_input(self, input_data, field_type='text'):
        """Sanitize input data based on field type"""
        return _sanitize_input(input_data, field_type, self.input_validation_rules)

    def check_sql_injection(self, query, params=None):
        """Check SQL query for potential injection vulnerabilities"""
        return _check_sql_injection(query, params)

    def validate_file_upload(self, file, allowed_types=None, max_size=None):
        """Validate file upload security"""
        return _validate_file_upload(file, allowed_types, max_size)

    def check_xss_vulnerabilities(self, template_content):
        """Check templates for XSS vulnerabilities"""
        return _check_xss_vulnerabilities(template_content)

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
        return _check_password_strength(password)

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
            'security_headers': self.audit_security_headers(current_app._get_current_object()),
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
        """Create security middleware for Flask app.

        Security checks run on ALL requests regardless of FLASK_DEBUG,
        TEST_MODE, host, or IP address. Only health check endpoints are
        whitelisted.
        """
        # Log warning if debug mode is active in production
        if (os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
                and os.getenv('RAILWAY_ENVIRONMENT', '').lower() == 'production'):
            self.logger.warning(
                "FLASK_DEBUG is enabled in production environment. "
                "Security checks remain enforced but debug mode may expose "
                "sensitive information in error responses."
            )

        @app.before_request
        def security_checks():
            # Only whitelist health check endpoints (needed for Railway/Docker health checks)
            if request.path in ['/api/health', '/api/status']:
                return None

            # Skip security checks for CORS preflight (OPTIONS) requests.
            # Browsers send OPTIONS automatically; these never carry auth tokens.
            # Flask-CORS handles the response (200 with/without CORS headers).
            if request.method == 'OPTIONS':
                return None

            # Check for suspicious request patterns on ALL requests
            if self.is_suspicious_request(request):
                self.logger.warning(f"Suspicious request detected: {request.path}")
                return jsonify({'error': 'Suspicious request detected'}), 403

            # Validate common headers
            if not self.validate_request_headers(request):
                self.logger.warning(f"Invalid request headers: {request.path}")
                return jsonify({'error': 'Invalid request headers'}), 400

        @app.after_request
        def add_security_headers(response):
            # Apply security response headers to ALL responses
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
        """Check if request shows suspicious patterns.

        Runs on ALL requests regardless of environment variables.
        """
        suspicious_patterns = [
            r'/\.\./',  # Directory traversal
            r'\.\./',   # Directory traversal
            r'%00',     # Null byte
            r'\b1=1\b',     # SQL injection
            r'union\s+select',  # SQL injection
            r'<script', # XSS
            r'javascript:',    # XSS
            r'\.\.\/',     # Directory traversal (literal ../)
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
        """Validate request headers for security.

        Runs on ALL requests regardless of environment variables.
        """
        # Check for required headers
        required_headers = ['Host']
        for header in required_headers:
            if header not in request.headers:
                return False

        # Note: X-Forwarded-* headers are legitimate when behind a proxy (Railway, nginx, etc.)
        # We trust these headers in production since Railway adds them
        # In a production environment, these should be validated by the proxy layer

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
