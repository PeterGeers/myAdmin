"""Public (unauthenticated) landing page endpoints: slug resolution + contact form.

Handlers resolve shared helpers through the ``routes.landing_page_routes``
package namespace at call time so the test suite's
``patch('routes.landing_page_routes.<name>')`` calls keep working.
"""

import logging
import os
import re

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from database import DatabaseManager
from routes import landing_page_routes as pkg

logger = logging.getLogger(__name__)

landing_page_bp = pkg.landing_page_bp

# Basic email regex for server-side validation
_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename for safe S3 storage.
    Keeps only alphanumeric characters, hyphens, underscores, and dots.
    """
    import re as re_module

    # Get just the filename (not path)
    name = os.path.basename(filename)
    # Replace spaces with hyphens
    name = name.replace(" ", "-")
    # Remove any character that isn't alphanumeric, hyphen, underscore, or dot
    name = re_module.sub(r"[^a-zA-Z0-9\-_.]", "", name)
    # Collapse multiple hyphens/underscores
    name = re_module.sub(r"[-_]{2,}", "-", name)
    return name.lower()


def _sanitize_input(value: str) -> str:
    """
    Sanitize user input by stripping HTML tags to prevent stored XSS.

    Task 4.11 — Input sanitization on contact form fields.
    Strips all HTML/XML tags from the input, leaving only plain text content.
    Also normalizes excessive whitespace.

    Args:
        value: Raw user input string

    Returns:
        Sanitized string with HTML tags removed.
    """
    import html as html_module

    # Strip HTML tags
    clean = re.sub(r"<[^>]*>", "", value)
    # Unescape any HTML entities that might have been injected (e.g. &lt;script&gt;)
    clean = html_module.unescape(clean)
    # Strip again after unescape (in case entities decoded into tags)
    clean = re.sub(r"<[^>]*>", "", clean)
    # Normalize excessive whitespace (but preserve newlines for message readability)
    clean = re.sub(r"[ \t]+", " ", clean)
    return clean.strip()


def _get_client_ip() -> str | None:
    """Get the client IP address, respecting X-Forwarded-For header."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr


def _check_rate_limit(
    db: DatabaseManager, email: str, ip_address: str | None
) -> str | None:
    """
    Check rate limits for contact form submissions.

    Limits:
        - 5 submissions per email per hour
        - 10 submissions per IP per hour

    Returns:
        None if within limits, or an error message string if rate-limited.
    """
    # Check email rate limit (5 per hour)
    email_count_query = """
        SELECT COUNT(*) AS cnt
        FROM landing_page_submissions
        WHERE visitor_email = %s
          AND created_at > NOW() - INTERVAL 1 HOUR
    """
    result = db.execute_query(email_count_query, (email,), fetch=True)
    if result and result[0].get("cnt", 0) >= 5:
        return "Too many requests. Please try again later."

    # Check IP rate limit (10 per hour)
    if ip_address:
        ip_count_query = """
            SELECT COUNT(*) AS cnt
            FROM landing_page_submissions
            WHERE ip_address = %s
              AND created_at > NOW() - INTERVAL 1 HOUR
        """
        result = db.execute_query(ip_count_query, (ip_address,), fetch=True)
        if result and result[0].get("cnt", 0) >= 10:
            return "Too many requests. Please try again later."

    return None


def _verify_recaptcha(token: str, client_ip: str | None) -> str | None:
    """
    Verify a reCAPTCHA v3 token with Google's API.

    Task 4.9 — Optional CAPTCHA verification. If RECAPTCHA_SECRET_KEY is not
    configured, verification is skipped (graceful degradation).

    Args:
        token: The reCAPTCHA response token from the frontend
        client_ip: Client IP address for additional verification

    Returns:
        None if verification passes (or is skipped), error message string if failed.
    """
    import urllib.parse
    import urllib.request

    secret_key = os.environ.get("RECAPTCHA_SECRET_KEY")
    if not secret_key:
        # CAPTCHA not configured — skip verification (graceful degradation)
        logger.debug("RECAPTCHA_SECRET_KEY not set, skipping CAPTCHA verification")
        return None

    try:
        verify_url = "https://www.google.com/recaptcha/api/siteverify"
        payload = urllib.parse.urlencode(
            {
                "secret": secret_key,
                "response": token,
                **({"remoteip": client_ip} if client_ip else {}),
            }
        ).encode("utf-8")

        req = urllib.request.Request(verify_url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            import json as json_module

            result = json_module.loads(resp.read().decode("utf-8"))

        if not result.get("success"):
            logger.warning(
                "reCAPTCHA verification failed: %s", result.get("error-codes")
            )
            return "CAPTCHA verification failed. Please try again."

        # Check score threshold (reCAPTCHA v3 returns 0.0–1.0)
        score = result.get("score", 0.0)
        min_score = float(os.environ.get("RECAPTCHA_MIN_SCORE", "0.5"))
        if score < min_score:
            logger.warning(
                "reCAPTCHA score too low: %.2f (min: %.2f)", score, min_score
            )
            return "CAPTCHA verification failed. Please try again."

        return None

    except Exception as e:
        # On verification error, allow the submission (graceful degradation)
        logger.error("reCAPTCHA verification error: %s", e)
        return None


@landing_page_bp.route("/api/public/landing/resolve/<slug>", methods=["GET"])
def resolve_slug(slug: str) -> ResponseReturnValue:
    """
    Resolve a slug to its administration identifier.

    This is a public endpoint used by the landing page rendering system
    to look up which tenant a slug belongs to.

    No authentication required.

    Args:
        slug: The URL slug to resolve

    Returns:
        JSON with success and administration, or 404 if not found
    """
    try:
        service = pkg._get_slug_service()
        administration = service.resolve_slug(slug)

        if administration:
            return jsonify(
                {"success": True, "data": {"administration": administration}}
            )
        else:
            return jsonify({"success": False, "error": "Slug not found"}), 404

    except Exception as e:
        logger.error(f"Error resolving slug '{slug}': {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@landing_page_bp.route("/api/public/landing/<slug>/contact", methods=["POST"])
def submit_contact(slug: str) -> ResponseReturnValue:
    """
    Submit a contact form inquiry for a public landing page.

    No authentication required — this is a public endpoint.

    Flow:
        1. Honeypot check (silently reject bots)
        2. Validate required fields + email format
        3. Resolve slug -> administration
        4. Rate limiting (5/email/hour, 10/IP/hour)
        5. Store submission in landing_page_submissions
        6. Send SES notification to tenant (async, non-blocking)

    Args:
        slug: The landing page URL slug

    Returns:
        JSON with success message, or error details
    """
    try:
        data = request.get_json(silent=True)

        if not data:
            return jsonify({"success": False, "error": "Invalid request body"}), 400

        # Honeypot check — if filled, silently return success (don't reveal to bots)
        honeypot = data.get("honeypot", "")
        if honeypot:
            return jsonify({"success": True, "message": "Your message has been sent."})

        # Validate and sanitize required fields (Task 4.11 — strip HTML to prevent stored XSS)
        name = _sanitize_input((data.get("name") or "").strip())
        email = (
            data.get("email") or ""
        ).strip()  # Email validated by regex, no HTML expected
        message = _sanitize_input((data.get("message") or "").strip())

        if not name:
            return jsonify({"success": False, "error": "Name is required"}), 400

        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400

        if not message:
            return jsonify({"success": False, "error": "Message is required"}), 400

        # Validate email format
        if not _EMAIL_PATTERN.match(email):
            return jsonify({"success": False, "error": "Invalid email address"}), 400

        # Validate field lengths
        if len(name) > 200:
            return jsonify(
                {"success": False, "error": "Name is too long (max 200 characters)"}
            ), 400

        if len(email) > 200:
            return jsonify(
                {"success": False, "error": "Email is too long (max 200 characters)"}
            ), 400

        # Resolve slug -> administration
        service = pkg._get_slug_service()
        administration = service.resolve_slug(slug)

        if not administration:
            return jsonify({"success": False, "error": "Page not found"}), 404

        # Rate limiting
        client_ip = _get_client_ip()
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = pkg.DatabaseManager(test_mode=test_mode)

        rate_limit_msg = _check_rate_limit(db, email, client_ip)
        if rate_limit_msg:
            return jsonify({"success": False, "error": rate_limit_msg}), 429

        # CAPTCHA verification (Task 4.9 — optional reCAPTCHA v3)
        captcha_token = data.get("captcha_token")
        if captcha_token:
            captcha_error = _verify_recaptcha(captcha_token, client_ip)
            if captcha_error:
                return jsonify({"success": False, "error": captcha_error}), 400

        # Store submission
        insert_query = """
            INSERT INTO landing_page_submissions
                (administration, visitor_name, visitor_email, message, ip_address)
            VALUES (%s, %s, %s, %s, %s)
        """
        db.execute_query(
            insert_query,
            (administration, name, email, message, client_ip),
            fetch=False,
            commit=True,
        )

        logger.info(
            f"Contact form submission stored for tenant '{administration}' "
            f"from {email} (IP: {client_ip})"
        )

        # Send notification to tenant (non-blocking — errors are logged, not raised)
        pkg._send_contact_notification(administration, name, email, message)

        return jsonify({"success": True, "message": "Your message has been sent."})

    except Exception as e:
        logger.error(f"Error processing contact form for slug '{slug}': {e}")
        return jsonify(
            {
                "success": False,
                "error": "Failed to send message. Please try again later.",
            }
        ), 500
