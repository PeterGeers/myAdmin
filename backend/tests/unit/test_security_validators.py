"""Unit tests for security_validators (auth/security).

Covers the reusable input-validation / sanitization / detection utilities, with a
deliberate emphasis on the rejection branches (injection detection, dangerous file
types, weak passwords, XSS patterns) rather than just the accept path.
"""

import io

import pytest

from security_validators import (
    check_password_strength,
    check_sql_injection,
    check_xss_vulnerabilities,
    sanitize_input,
    validate_file_upload,
    validate_input,
)


# ---------------------------------------------------------------------------
# validate_input
# ---------------------------------------------------------------------------

class TestValidateInput:
    def test_valid_username_passes(self):
        result = validate_input("good_user1", "username")
        assert result["valid"] is True
        assert result["sanitized"] == "good_user1"

    def test_empty_input_rejected(self):
        result = validate_input("", "username")
        assert result["valid"] is False
        assert "empty" in result["error"].lower()

    def test_injection_pattern_rejected(self):
        """A SQL-ish payload trips the injection-pattern guard."""
        result = validate_input("admin' OR 1=1", "username")
        assert result["valid"] is False
        assert "injection" in result["error"].lower()

    def test_script_tag_rejected(self):
        result = validate_input("<script>alert(1)</script>", "text")
        assert result["valid"] is False
        assert "injection" in result["error"].lower()

    def test_field_pattern_mismatch_rejected(self):
        """A value that clears injection checks but fails the field regex."""
        result = validate_input("ab", "username")  # too short for username rule
        assert result["valid"] is False
        assert "username" in result["error"].lower()

    def test_max_length_enforced(self):
        result = validate_input("averylongemailprefix@example.com", "email", max_length=5)
        assert result["valid"] is False
        assert "length" in result["error"].lower()


# ---------------------------------------------------------------------------
# sanitize_input
# ---------------------------------------------------------------------------

class TestSanitizeInput:
    def test_empty_returns_empty(self):
        assert sanitize_input("") == ""

    def test_html_field_keeps_allowed_tags_strips_others(self):
        out = sanitize_input("<p>hi</p><script>x()</script>", "html")
        assert "<p>" in out
        assert "<script>" not in out

    def test_email_field_lowercases_valid_email(self):
        assert sanitize_input("User@Example.COM", "email") == "user@example.com"

    def test_email_field_rejects_invalid(self):
        assert sanitize_input("not-an-email", "email") == ""

    def test_url_field_passes_valid_url(self):
        assert sanitize_input("https://example.com/path", "url") == "https://example.com/path"

    def test_text_field_strips_control_chars_and_tags(self):
        out = sanitize_input("hello\x00<b>there</b>", "text")
        assert "\x00" not in out
        assert "<b>" not in out
        assert "hello" in out


# ---------------------------------------------------------------------------
# check_sql_injection
# ---------------------------------------------------------------------------

class TestCheckSqlInjection:
    def test_parameterized_query_is_safe(self):
        result = check_sql_injection("SELECT * FROM users WHERE id = %s", params=("1",))
        assert result["safe"] is True
        assert result["issues"] == []

    def test_string_concatenation_flagged(self):
        result = check_sql_injection("SELECT * FROM t WHERE name = 'a' + userinput")
        assert result["safe"] is False
        assert any("concatenation" in i.lower() for i in result["issues"])

    def test_classic_or_1_equals_1_flagged(self):
        result = check_sql_injection("SELECT * FROM users WHERE 1=1")
        assert result["safe"] is False
        assert result["recommendations"]

    def test_union_select_flagged(self):
        result = check_sql_injection("SELECT a FROM t UNION SELECT password FROM users")
        assert result["safe"] is False

    def test_inline_values_without_params_flagged(self):
        result = check_sql_injection("INSERT INTO t VALUES (1, 'x')", params=None)
        assert result["safe"] is False


# ---------------------------------------------------------------------------
# validate_file_upload
# ---------------------------------------------------------------------------

class _FakeUpload:
    """Minimal stand-in for a Werkzeug FileStorage."""

    def __init__(self, filename, content=b"", content_type="application/octet-stream"):
        self.filename = filename
        self.content_type = content_type
        self._buf = io.BytesIO(content)

    def read(self, size=-1):
        return self._buf.read(size)

    def seek(self, pos, whence=0):
        return self._buf.seek(pos, whence)


class TestValidateFileUpload:
    def test_no_file_rejected(self):
        result = validate_file_upload(None)
        assert result["valid"] is False

    def test_allowed_type_accepted(self):
        upload = _FakeUpload("statement.pdf", content=b"%PDF-1.4 clean content")
        result = validate_file_upload(upload, allowed_types=["pdf", "csv"])
        assert result["valid"] is True
        assert result["sanitized_filename"].endswith(".pdf")

    def test_disallowed_type_rejected(self):
        upload = _FakeUpload("data.txt", content=b"hello")
        result = validate_file_upload(upload, allowed_types=["pdf"])
        assert result["valid"] is False
        assert any("not allowed" in i.lower() for i in result["issues"])

    def test_dangerous_extension_rejected(self):
        upload = _FakeUpload("shell.php", content=b"<?php echo 1; ?>")
        result = validate_file_upload(upload)
        assert result["valid"] is False
        assert any("dangerous" in i.lower() for i in result["issues"])

    def test_oversize_file_rejected(self):
        upload = _FakeUpload("big.pdf", content=b"x" * 100)
        result = validate_file_upload(upload, allowed_types=["pdf"], max_size=10)
        assert result["valid"] is False
        assert any("exceeds" in i.lower() for i in result["issues"])

    def test_malware_signature_detected(self):
        upload = _FakeUpload("inv.pdf", content=b"<?php system($_GET[0]); ?>")
        result = validate_file_upload(upload, allowed_types=["pdf"])
        assert result["valid"] is False
        assert any("malware" in i.lower() for i in result["issues"])

    def test_filename_is_sanitized(self):
        upload = _FakeUpload("../../etc/pa ss.pdf", content=b"ok")
        result = validate_file_upload(upload, allowed_types=["pdf"])
        assert "/" not in result["sanitized_filename"]
        assert " " not in result["sanitized_filename"]


# ---------------------------------------------------------------------------
# check_xss_vulnerabilities
# ---------------------------------------------------------------------------

class TestCheckXssVulnerabilities:
    def test_static_template_without_interpolation_is_safe(self):
        """A template with no {{ }} interpolation and explicit escaping is safe."""
        result = check_xss_vulnerabilities("<div>{% autoescape true %}static{% endautoescape %}</div>")
        assert result["safe"] is True

    def test_any_interpolation_is_flagged_unsafe(self):
        """The validator conservatively flags all {{ }} interpolation."""
        result = check_xss_vulnerabilities("<div>{{ value|escape }}</div>")
        assert result["safe"] is False

    def test_safe_filter_flagged_unsafe(self):
        result = check_xss_vulnerabilities("<div>{{ value|safe }}</div>")
        assert result["safe"] is False
        assert result["recommendations"]

    def test_autoescape_false_flagged(self):
        result = check_xss_vulnerabilities("{% autoescape false %}{{ x }}{% endautoescape %}")
        assert result["safe"] is False

    def test_long_template_is_truncated_in_report(self):
        content = "{{ x|escape }}" + "a" * 1000
        result = check_xss_vulnerabilities(content)
        assert result["template"].endswith("...")


# ---------------------------------------------------------------------------
# check_password_strength
# ---------------------------------------------------------------------------

class TestCheckPasswordStrength:
    def test_strong_password(self):
        result = check_password_strength("Str0ng!Passphrase")
        assert result["strong"] is True
        assert result["score"] >= 4

    def test_empty_password_rejected(self):
        result = check_password_strength("")
        assert result["strong"] is False
        assert result["score"] == 0

    def test_common_password_rejected(self):
        result = check_password_strength("password")
        assert result["strong"] is False
        assert result["common_password"] is True

    def test_short_password_flagged(self):
        result = check_password_strength("Ab1!")
        assert result["strong"] is False
        assert any("short" in i.lower() for i in result["issues"])

    @pytest.mark.parametrize(
        "pw,missing",
        [
            ("lowercase1!", "uppercase"),
            ("UPPERCASE1!", "lowercase"),
            ("NoDigits!!", "digits"),
            ("NoSpecial11", "special"),
        ],
    )
    def test_missing_character_class_reported(self, pw, missing):
        result = check_password_strength(pw)
        assert result["strong"] is False
        assert any(missing in i.lower() for i in result["issues"])
