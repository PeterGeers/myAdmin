"""
Property-based tests for rate limiter sliding window enforcement and IP extraction.

Uses Hypothesis to verify correctness properties from the design document.
Feature: security-hardening, Properties 13–14: Rate Limiter

Requirements: 7.1, 7.3, 7.4, 7.5
Reference: .kiro/specs/security-hardening/design.md
"""

import os
import sys
import pytest
from unittest.mock import MagicMock
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from auth.rate_limiter import RateLimiter, RateLimitResult


# --- Strategies ---

# Generate valid email addresses
emails = st.from_regex(r'[a-z]{3,10}@[a-z]{3,8}\.(com|nl|org)', fullmatch=True)

# Generate valid IPv4 addresses
ipv4_addresses = st.tuples(
    st.integers(min_value=1, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=1, max_value=255),
).map(lambda t: f"{t[0]}.{t[1]}.{t[2]}.{t[3]}")

# Generate request counts for email limit testing (1-20 requests)
email_request_counts = st.integers(min_value=1, max_value=20)

# Generate request counts for IP limit testing (1-20 requests)
ip_request_counts = st.integers(min_value=1, max_value=20)

# Generate lists of IPs for X-Forwarded-For header (1-5 IPs)
ip_lists = st.lists(ipv4_addresses, min_size=1, max_size=5)


# ---------------------------------------------------------------------------
# Property 13: Rate Limiter Sliding Window Enforcement
# Feature: security-hardening, Property 13: Sliding Window Enforcement
# Validates: Requirements 7.1, 7.3, 7.4
# ---------------------------------------------------------------------------

class TestSlidingWindowEnforcement:
    """
    Property 13: Rate Limiter Sliding Window Enforcement

    For any sequence of password reset requests where more than 5 requests
    share the same email address within a 900-second window, OR more than 10
    requests share the same client IP within a 900-second window, the
    Rate_Limiter SHALL reject subsequent requests. Both limits are tracked
    independently.

    Feature: security-hardening, Property 13: Sliding Window Enforcement
    **Validates: Requirements 7.1, 7.3, 7.4**
    """

    @settings(max_examples=100)
    @given(
        num_requests=email_request_counts,
        email=emails,
        ip=ipv4_addresses,
    )
    def test_email_limit_enforcement(self, num_requests, email, ip):
        """
        Feature: security-hardening, Property 13: Sliding Window Enforcement

        After recording N requests with the same email, the rate limiter SHALL
        reject the (N+1)th request when N >= 5 (max_per_email), and allow it
        when N < 5.

        **Validates: Requirements 7.1, 7.3, 7.4**
        """
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)

        # Record num_requests requests
        for _ in range(num_requests):
            limiter.record_request(email, ip)

        # Check if the next request would be allowed
        result = limiter.check_rate_limit(email, ip)

        if num_requests >= 5:
            # Should be rejected due to email limit
            assert not result.allowed, (
                f"Request should be rejected after {num_requests} same-email requests "
                f"(limit is 5), but was allowed"
            )
            assert result.limit_type == "email", (
                f"Expected limit_type='email' but got '{result.limit_type}'"
            )
            assert result.retry_after_seconds > 0, (
                f"retry_after_seconds should be positive but got {result.retry_after_seconds}"
            )
        else:
            # Should be allowed (email count is below limit)
            assert result.allowed, (
                f"Request should be allowed after {num_requests} same-email requests "
                f"(limit is 5), but was rejected with limit_type={result.limit_type}"
            )

    @settings(max_examples=100)
    @given(
        num_requests=ip_request_counts,
        ip=ipv4_addresses,
    )
    def test_ip_limit_enforcement(self, num_requests, ip):
        """
        Feature: security-hardening, Property 13: Sliding Window Enforcement

        After recording N requests with the same IP (but different emails to
        avoid triggering email limit), the rate limiter SHALL reject the (N+1)th
        request when N >= 10 (max_per_ip), and allow it when N < 10.

        **Validates: Requirements 7.1, 7.3, 7.4**
        """
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)

        # Record requests with different emails to avoid email limit
        for i in range(num_requests):
            unique_email = f"user{i}@example.com"
            limiter.record_request(unique_email, ip)

        # Check with a fresh email that hasn't been used
        fresh_email = f"fresh_user_{num_requests}@example.com"
        result = limiter.check_rate_limit(fresh_email, ip)

        if num_requests >= 10:
            # Should be rejected due to IP limit
            assert not result.allowed, (
                f"Request should be rejected after {num_requests} same-IP requests "
                f"(limit is 10), but was allowed"
            )
            assert result.limit_type == "ip", (
                f"Expected limit_type='ip' but got '{result.limit_type}'"
            )
            assert result.retry_after_seconds > 0, (
                f"retry_after_seconds should be positive but got {result.retry_after_seconds}"
            )
        else:
            # Should be allowed (IP count is below limit)
            assert result.allowed, (
                f"Request should be allowed after {num_requests} same-IP requests "
                f"(limit is 10), but was rejected with limit_type={result.limit_type}"
            )

    @settings(max_examples=100)
    @given(
        email_count=st.integers(min_value=1, max_value=10),
        ip_count=st.integers(min_value=1, max_value=15),
        email=emails,
        ip=ipv4_addresses,
    )
    def test_limits_tracked_independently(self, email_count, ip_count, email, ip):
        """
        Feature: security-hardening, Property 13: Sliding Window Enforcement

        Email and IP limits are tracked independently. An email can be rate-limited
        while the IP is fine, and vice versa.

        **Validates: Requirements 7.1, 7.3, 7.4**
        """
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)

        # Record email_count requests for a specific email with different IPs
        for i in range(email_count):
            limiter.record_request(email, f"10.0.0.{i + 1}")

        # Record ip_count requests for a specific IP with different emails
        for i in range(ip_count):
            limiter.record_request(f"user{i}@other.com", ip)

        # Check: email limit is independent of IP limit
        # Check email with a fresh IP
        email_result = limiter.check_rate_limit(email, "99.99.99.99")
        if email_count >= 5:
            assert not email_result.allowed, (
                f"Email should be rate-limited after {email_count} requests"
            )
            assert email_result.limit_type == "email"
        else:
            assert email_result.allowed, (
                f"Email should be allowed after {email_count} requests (limit is 5)"
            )

        # Check IP with a fresh email
        ip_result = limiter.check_rate_limit("fresh@brand-new.com", ip)
        if ip_count >= 10:
            assert not ip_result.allowed, (
                f"IP should be rate-limited after {ip_count} requests"
            )
            assert ip_result.limit_type == "ip"
        else:
            assert ip_result.allowed, (
                f"IP should be allowed after {ip_count} requests (limit is 10)"
            )


# ---------------------------------------------------------------------------
# Property 14: Rate Limiter IP Extraction
# Feature: security-hardening, Property 14: IP Extraction
# Validates: Requirements 7.5
# ---------------------------------------------------------------------------

class TestIPExtraction:
    """
    Property 14: Rate Limiter IP Extraction

    For any HTTP request containing an X-Forwarded-For header with one or more
    comma-separated IP addresses, the Rate_Limiter SHALL extract and use the
    leftmost (first) IP address as the client identifier.

    Feature: security-hardening, Property 14: IP Extraction
    **Validates: Requirements 7.5**
    """

    @settings(max_examples=100)
    @given(ip_list=ip_lists)
    def test_leftmost_ip_extracted_from_x_forwarded_for(self, ip_list):
        """
        Feature: security-hardening, Property 14: IP Extraction

        Given a list of IPs joined with ", " as X-Forwarded-For header value,
        get_client_ip SHALL return the leftmost (first) IP address.

        **Validates: Requirements 7.5**
        """
        # Build X-Forwarded-For header value
        forwarded_for_value = ", ".join(ip_list)

        # Create a mock request with X-Forwarded-For header
        mock_request = MagicMock()
        mock_request.headers = {"X-Forwarded-For": forwarded_for_value}
        mock_request.remote_addr = "192.168.1.1"

        # Extract client IP
        extracted_ip = RateLimiter.get_client_ip(mock_request)

        # The leftmost IP should be extracted
        expected_ip = ip_list[0]
        assert extracted_ip == expected_ip, (
            f"Expected leftmost IP '{expected_ip}' from X-Forwarded-For "
            f"'{forwarded_for_value}', but got '{extracted_ip}'"
        )

    @settings(max_examples=100, derandomize=True)
    @given(ip=ipv4_addresses)
    def test_remote_addr_fallback_when_no_forwarded_for(self, ip):
        """
        Feature: security-hardening, Property 14: IP Extraction

        When no X-Forwarded-For header is present, get_client_ip SHALL
        fall back to the request's remote_addr.

        **Validates: Requirements 7.5**
        """
        # Create a mock request without X-Forwarded-For
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.remote_addr = ip

        # Extract client IP
        extracted_ip = RateLimiter.get_client_ip(mock_request)

        assert extracted_ip == ip, (
            f"Expected remote_addr '{ip}' as fallback, but got '{extracted_ip}'"
        )

    @settings(max_examples=100)
    @given(ip_list=ip_lists)
    def test_whitespace_handling_in_forwarded_for(self, ip_list):
        """
        Feature: security-hardening, Property 14: IP Extraction

        IP addresses in X-Forwarded-For may have surrounding whitespace.
        The extracted IP should be stripped of whitespace.

        **Validates: Requirements 7.5**
        """
        # Build X-Forwarded-For with extra whitespace
        forwarded_for_value = " , ".join(f"  {ip}  " for ip in ip_list)

        mock_request = MagicMock()
        mock_request.headers = {"X-Forwarded-For": forwarded_for_value}
        mock_request.remote_addr = "192.168.1.1"

        extracted_ip = RateLimiter.get_client_ip(mock_request)

        # Should be the first IP, stripped of whitespace
        expected_ip = ip_list[0]
        assert extracted_ip == expected_ip, (
            f"Expected stripped leftmost IP '{expected_ip}' from "
            f"X-Forwarded-For '{forwarded_for_value}', but got '{extracted_ip}'"
        )
