"""
Signup Routes Blueprint

Public endpoints for trial signup flow:
- POST /api/signup          — Create new trial signup
- POST /api/signup/verify   — Verify email with confirmation code
- POST /api/signup/resend   — Resend verification code

No JWT auth required. Protected by rate limiting, honeypot, and CSRF.
"""

from flask import Blueprint, jsonify, request, current_app
import logging

from shared_limiter import limiter
from services.signup_service import (
    SignupService,
    UsernameExistsError,
    SignupNotFoundError,
    AlreadyVerifiedError,
    InvalidCodeError,
    ResendRateLimitError
)

logger = logging.getLogger(__name__)

signup_bp = Blueprint('signup', __name__)

# Lazy-initialized service instance
_signup_service = None


def _get_service() -> SignupService:
    """Get or create the signup service singleton"""
    global _signup_service
    if _signup_service is None:
        _signup_service = SignupService()
    return _signup_service


@signup_bp.route('/api/signup', methods=['POST', 'OPTIONS'])
@limiter.limit("5 per hour", methods=["POST"])
def create_signup():
    """Create a new trial signup"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'})

    service = _get_service()
    data = request.get_json(silent=True) or {}

    # Honeypot check — return fake success to not tip off bots
    if service.is_honeypot_filled(data):
        logger.info("Honeypot triggered — bot detected")
        return jsonify({'success': True, 'userId': 'ok', 'message': 'Verification email sent'}), 200


    # CSRF validation
    csrf_token = request.headers.get('X-CSRF-Token') or data.get('csrfToken', '')
    if not service.validate_csrf_token(csrf_token):
        return jsonify({'error': 'Invalid CSRF token'}), 403

    # Input validation
    is_valid, errors = service.validate_signup_input(data)
    if not is_valid:
        return jsonify({'error': 'Validation failed', 'errors': errors}), 422

    try:
        result = service.create_signup(
            data,
            ip_address=request.remote_addr,
            user_agent=str(request.user_agent)[:500]
        )
        return jsonify({
            'success': True,
            'userId': result['userId'],
            'message': 'Verification email sent'
        }), 201

    except UsernameExistsError:
        return jsonify({'error': 'Email already registered'}), 409
    except Exception as e:
        logger.error(f"Signup failed: {e}")
        return jsonify({'error': 'Signup failed. Please try again.'}), 500


@signup_bp.route('/api/signup/verify', methods=['POST', 'OPTIONS'])
@limiter.limit("10 per hour", methods=["POST"])
def verify_signup():
    """Verify email with Cognito confirmation code"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'})

    service = _get_service()
    data = request.get_json(silent=True) or {}

    email = data.get('email', '').strip()
    code = data.get('code', '').strip()

    if not email or not code:
        return jsonify({'error': 'Email and code are required'}), 422

    try:
        result = service.verify_signup(email, code)
        return jsonify({
            'success': True,
            'redirectUrl': result['redirectUrl']
        }), 200

    except SignupNotFoundError:
        return jsonify({'error': 'Signup not found'}), 404
    except AlreadyVerifiedError:
        return jsonify({'error': 'Already verified'}), 410
    except InvalidCodeError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return jsonify({'error': 'Verification failed. Please try again.'}), 500


@signup_bp.route('/api/signup/resend', methods=['POST', 'OPTIONS'])
@limiter.limit("1 per minute", methods=["POST"])
def resend_verification():
    """Resend verification code"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'})

    service = _get_service()
    data = request.get_json(silent=True) or {}

    email = data.get('email', '').strip()
    if not email:
        return jsonify({'error': 'Email is required'}), 422

    try:
        result = service.resend_verification(email)
        return jsonify({
            'success': True,
            'message': result['message']
        }), 200

    except SignupNotFoundError:
        return jsonify({'error': 'Signup not found'}), 404
    except AlreadyVerifiedError:
        return jsonify({'error': 'Already verified'}), 410
    except ResendRateLimitError as e:
        return jsonify({'error': str(e)}), 429
    except Exception as e:
        logger.error(f"Resend failed: {e}")
        return jsonify({'error': 'Resend failed. Please try again.'}), 500
