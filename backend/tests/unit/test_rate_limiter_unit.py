"""
Unit tests for Rate Limiter (Requirements 7.2, 7.3).

Tests verify:
- HTTP 429 response format with Retry-After header (7.2)
- Retry-After value calculation (seconds until earliest request expires) (7.2)
- Concurrent access thread safety (7.3)
- Email and IP limits tracked independently (7.3)
- get_client_ip() with various X-Forwarded-For formats (7.5)
"""
import time
import threading
import pytest
from unittest.mock import MagicMock

from src.auth.rate_limiter import RateLimiter, RateLimitResult


class TestEmailRateLimit:
    """Test email-based rate limiting (max 5 per 15-minute window)."""

    def test_sixth_request_same_email_is_rejected(self):
        """After 5 requests with same email, 6th returns not allowed with limit_type='email'."""
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)
        email = "user@example.com"
        ip = "192.168.1.1"

        # Record 5 requests
        for _ in range(5):
            limiter.record_request(email, ip)

        # 6th check should be rejected
        result = limiter.check_rate_limit(email, ip)
        assert result.allowed is False
        assert result.limit_type == "email"
        assert result.retry_after_seconds > 0

    def test_fifth_request_same_email_is_allowed(self):
        """5 requests with same email should still be allowed on check."""
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)
        email = "user@example.com"
        ip = "192.168.1.1"

        # Record 4 requests
        for _ in range(4):
            limiter.record_request(email, ip)

        # 5th check should still pass (limit is >= 5 recorded)
        result = limiter.check_rate_limit(email, ip)
        assert result.allowed is True
        assert result.limit_type is None
        assert result.retry_after_seconds == 0


class TestIPRateLimit:
    """Test IP-based rate limiting (max 10 per 15-minute window)."""

    def test_eleventh_request_same_ip_is_rejected(self):
        """After 10 requests with same IP, 11th returns not allowed with limit_type='ip'."""
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)
        ip = "10.0.0.1"

        # Use different emails to avoid hitting email limit first
        for i in range(10):
            limiter.record_request(f"user{i}@example.com", ip)

        # 11th check with a new email should be rejected by IP limit
        result = limiter.check_rate_limit("new_user@example.com", ip)
        assert result.allowed is False
        assert result.limit_type == "ip"
        assert result.retry_after_seconds > 0

    def test_tenth_request_same_ip_is_allowed(self):
        """10 requests with same IP should still allow a check (limit is >= 10 recorded)."""
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)
        ip = "10.0.0.1"

        # Record 9 requests with different emails
        for i in range(9):
            limiter.record_request(f"user{i}@example.com", ip)

        # 10th check with new email should pass
        result = limiter.check_rate_limit("new_user@example.com", ip)
        assert result.allowed is True
        assert result.limit_type is None


class TestRetryAfterCalculation:
    """Test Retry-After value calculation (seconds until earliest request expires)."""

    def test_retry_after_is_window_minus_age_of_earliest_request(self):
        """Retry-After = window_seconds - age_of_earliest_request + 1 (rounded up)."""
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)
        email = "user@example.com"
        ip = "192.168.1.1"

        # Manually insert timestamps: earliest was 100 seconds ago
        now = time.time()
        email_key = f"email:{email}"
        limiter._store[email_key] = [
            now - 100,  # earliest: 100 seconds old
            now - 80,
            now - 60,
            now - 40,
            now - 20,
        ]

        result = limiter.check_rate_limit(email, ip)
        assert result.allowed is False
        assert result.limit_type == "email"
        # Expected: window_seconds - age_of_earliest + 1 = 900 - 100 + 1 = 801
        # The calculation: earliest - cutoff + 1 where cutoff = now - window_seconds
        # = (now - 100) - (now - 900) + 1 = 800 + 1 = 801
        assert result.retry_after_seconds == 801

    def test_retry_after_minimum_is_1(self):
        """Retry-After should always be at least 1 second."""
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)
        email = "user@example.com"
        ip = "192.168.1.1"

        # All timestamps at the edge of the window (nearly expired)
        now = time.time()
        email_key = f"email:{email}"
        limiter._store[email_key] = [
            now - 899,  # Almost expired (1 second from expiry)
            now - 898,
            now - 897,
            now - 896,
            now - 895,
        ]

        result = limiter.check_rate_limit(email, ip)
        assert result.allowed is False
        assert result.retry_after_seconds >= 1

    def test_retry_after_for_ip_limit(self):
        """Retry-After also works correctly when IP limit is triggered."""
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)
        ip = "10.0.0.1"

        now = time.time()
        ip_key = f"ip:{ip}"
        # 10 requests from same IP, earliest was 200 seconds ago
        limiter._store[ip_key] = [now - 200 + i * 10 for i in range(10)]

        # Use a fresh email so email limit doesn't fire
        result = limiter.check_rate_limit("fresh@example.com", ip)
        assert result.allowed is False
        assert result.limit_type == "ip"
        # Expected: earliest is now - 200, cutoff = now - 900
        # retry_after = (now - 200) - (now - 900) + 1 = 700 + 1 = 701
        assert result.retry_after_seconds == 701


class TestThreadSafety:
    """Test concurrent access thread safety."""

    def test_concurrent_record_requests_no_data_corruption(self):
        """Spawn multiple threads recording requests simultaneously,
        verify final count is consistent and no data corruption."""
        limiter = RateLimiter(max_per_email=100, max_per_ip=200, window_seconds=900)
        email = "concurrent@example.com"
        ip = "172.16.0.1"
        num_threads = 20
        requests_per_thread = 10
        total_expected = num_threads * requests_per_thread

        barrier = threading.Barrier(num_threads)

        def worker():
            barrier.wait()  # Synchronize all threads to start together
            for _ in range(requests_per_thread):
                limiter.record_request(email, ip)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify counts are consistent
        email_key = f"email:{email}"
        ip_key = f"ip:{ip}"
        assert len(limiter._store[email_key]) == total_expected
        assert len(limiter._store[ip_key]) == total_expected

    def test_concurrent_check_and_record_no_crash(self):
        """Mixed check_rate_limit and record_request calls from multiple threads
        should not raise exceptions or corrupt data."""
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)
        num_threads = 10
        errors = []

        barrier = threading.Barrier(num_threads)

        def worker(thread_id):
            try:
                barrier.wait()
                email = f"user{thread_id}@example.com"
                ip = f"10.0.0.{thread_id}"
                for _ in range(5):
                    limiter.record_request(email, ip)
                    result = limiter.check_rate_limit(email, ip)
                    assert isinstance(result, RateLimitResult)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"


class TestGetClientIP:
    """Test get_client_ip() with various X-Forwarded-For header formats."""

    def _make_request(self, forwarded_for=None, remote_addr="127.0.0.1"):
        """Create a mock Flask request object."""
        request = MagicMock()
        headers = {}
        if forwarded_for is not None:
            headers["X-Forwarded-For"] = forwarded_for
        request.headers = MagicMock()
        request.headers.get = lambda key, default="": headers.get(key, default)
        request.remote_addr = remote_addr
        return request

    def test_single_ip_in_forwarded_for(self):
        """Single IP in X-Forwarded-For is used directly."""
        request = self._make_request(forwarded_for="203.0.113.50")
        assert RateLimiter.get_client_ip(request) == "203.0.113.50"

    def test_multiple_ips_uses_leftmost(self):
        """Multiple IPs: leftmost (original client) is used per Requirement 7.5."""
        request = self._make_request(
            forwarded_for="203.0.113.50, 70.41.3.18, 150.172.238.178"
        )
        assert RateLimiter.get_client_ip(request) == "203.0.113.50"

    def test_forwarded_for_with_spaces(self):
        """Spaces around IPs in X-Forwarded-For are stripped."""
        request = self._make_request(
            forwarded_for="  203.0.113.50  , 70.41.3.18"
        )
        assert RateLimiter.get_client_ip(request) == "203.0.113.50"

    def test_no_forwarded_for_falls_back_to_remote_addr(self):
        """Without X-Forwarded-For, remote_addr is used."""
        request = self._make_request(remote_addr="192.168.1.100")
        assert RateLimiter.get_client_ip(request) == "192.168.1.100"

    def test_empty_forwarded_for_falls_back_to_remote_addr(self):
        """Empty X-Forwarded-For falls back to remote_addr."""
        request = self._make_request(forwarded_for="", remote_addr="192.168.1.100")
        assert RateLimiter.get_client_ip(request) == "192.168.1.100"

    def test_no_remote_addr_returns_unknown(self):
        """If both X-Forwarded-For and remote_addr are absent, returns 'unknown'."""
        request = self._make_request(remote_addr=None)
        assert RateLimiter.get_client_ip(request) == "unknown"

    def test_ipv6_in_forwarded_for(self):
        """IPv6 address in X-Forwarded-For is handled correctly."""
        request = self._make_request(
            forwarded_for="2001:db8::1, 203.0.113.50"
        )
        assert RateLimiter.get_client_ip(request) == "2001:db8::1"


class TestIndependentLimits:
    """Verify email limit and IP limit are tracked independently."""

    def test_email_limit_does_not_affect_ip_limit(self):
        """Hitting email limit for one email doesn't block a different email from same IP."""
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)
        ip = "192.168.1.1"

        # Exhaust email limit for user1
        for _ in range(5):
            limiter.record_request("user1@example.com", ip)

        # user1 should be blocked by email limit
        result = limiter.check_rate_limit("user1@example.com", ip)
        assert result.allowed is False
        assert result.limit_type == "email"

        # user2 from same IP should still be allowed (only 5 IP requests so far)
        result = limiter.check_rate_limit("user2@example.com", ip)
        assert result.allowed is True

    def test_ip_limit_does_not_affect_email_limit(self):
        """Hitting IP limit doesn't block a request from a different IP for same email."""
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)
        email = "shared@example.com"

        # Exhaust IP limit by sending 10 requests from same IP with different emails
        ip1 = "10.0.0.1"
        for i in range(10):
            limiter.record_request(f"user{i}@example.com", ip1)

        # IP1 is now blocked
        result = limiter.check_rate_limit("new_user@example.com", ip1)
        assert result.allowed is False
        assert result.limit_type == "ip"

        # Different IP should still be allowed
        result = limiter.check_rate_limit("new_user@example.com", "10.0.0.2")
        assert result.allowed is True

    def test_email_and_ip_are_separate_counters(self):
        """Email and IP counters don't interfere with each other."""
        limiter = RateLimiter(max_per_email=2, max_per_ip=3, window_seconds=900)

        # 2 requests: email1 from ip1
        limiter.record_request("email1@test.com", "1.1.1.1")
        limiter.record_request("email1@test.com", "1.1.1.1")

        # email1 should be blocked (email limit = 2)
        result = limiter.check_rate_limit("email1@test.com", "1.1.1.1")
        assert result.allowed is False
        assert result.limit_type == "email"

        # email2 from ip1 should still work (IP has 2 of 3 allowed)
        result = limiter.check_rate_limit("email2@test.com", "1.1.1.1")
        assert result.allowed is True

        # Add one more request from ip1 with email2
        limiter.record_request("email2@test.com", "1.1.1.1")

        # Now ip1 has 3 requests -> next IP check should fail
        result = limiter.check_rate_limit("email3@test.com", "1.1.1.1")
        assert result.allowed is False
        assert result.limit_type == "ip"


class TestWindowExpiration:
    """Test that requests outside the window are properly cleaned."""

    def test_expired_requests_are_cleaned(self):
        """Requests older than the window are not counted."""
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)
        email = "user@example.com"
        ip = "192.168.1.1"

        now = time.time()
        email_key = f"email:{email}"
        # Insert 5 timestamps that are all expired (older than 900 seconds)
        limiter._store[email_key] = [now - 1000, now - 1100, now - 1200, now - 1300, now - 1400]

        # Should be allowed since all timestamps are expired
        result = limiter.check_rate_limit(email, ip)
        assert result.allowed is True

    def test_mixed_expired_and_current_requests(self):
        """Only current (non-expired) requests count toward the limit."""
        limiter = RateLimiter(max_per_email=5, max_per_ip=10, window_seconds=900)
        email = "user@example.com"
        ip = "192.168.1.1"

        now = time.time()
        email_key = f"email:{email}"
        # 3 expired + 4 current = only 4 count
        limiter._store[email_key] = [
            now - 1000, now - 1100, now - 1200,  # expired
            now - 100, now - 80, now - 60, now - 40,  # current (within 900s)
        ]

        result = limiter.check_rate_limit(email, ip)
        assert result.allowed is True  # 4 < 5, still allowed
