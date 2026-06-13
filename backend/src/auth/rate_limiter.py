"""
Rate limiter for authentication endpoints.
Uses a sliding window algorithm with in-memory storage.
Thread-safe via threading.Lock. Suitable for single-instance Railway deployment.
"""

import time
import threading
from dataclasses import dataclass
from typing import Optional


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    retry_after_seconds: int
    limit_type: Optional[str]


class RateLimiter:
    """Sliding window rate limiter using in-memory store.

    Tracks requests by email and IP address independently.
    Both limits must pass for a request to be allowed.
    """

    def __init__(
        self,
        max_per_email: int = 5,
        max_per_ip: int = 10,
        window_seconds: int = 900
    ):
        """Initialize the rate limiter.

        Args:
            max_per_email: Maximum requests per email within the window (default 5).
            max_per_ip: Maximum requests per IP within the window (default 10).
            window_seconds: Sliding window duration in seconds (default 900 = 15 minutes).
        """
        self.max_per_email = max_per_email
        self.max_per_ip = max_per_ip
        self.window_seconds = window_seconds
        self._store: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check_rate_limit(self, email: str, ip: str) -> RateLimitResult:
        """Check if a request is within rate limits.

        Cleans expired timestamps and checks both email and IP limits.
        Email is checked first; if both exceed, email limit is reported.

        Args:
            email: The target email address for the request.
            ip: The client IP address.

        Returns:
            RateLimitResult with allowed status, retry_after_seconds, and limit_type.
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            # Clean and check email limit
            email_key = f"email:{email}"
            self._clean_expired(email_key, cutoff)
            email_timestamps = self._store.get(email_key, [])

            if len(email_timestamps) >= self.max_per_email:
                retry_after = self._calculate_retry_after(email_timestamps, cutoff)
                return RateLimitResult(
                    allowed=False,
                    retry_after_seconds=retry_after,
                    limit_type="email"
                )

            # Clean and check IP limit
            ip_key = f"ip:{ip}"
            self._clean_expired(ip_key, cutoff)
            ip_timestamps = self._store.get(ip_key, [])

            if len(ip_timestamps) >= self.max_per_ip:
                retry_after = self._calculate_retry_after(ip_timestamps, cutoff)
                return RateLimitResult(
                    allowed=False,
                    retry_after_seconds=retry_after,
                    limit_type="ip"
                )

        return RateLimitResult(
            allowed=True,
            retry_after_seconds=0,
            limit_type=None
        )

    def record_request(self, email: str, ip: str) -> None:
        """Record a request against both email and IP windows.

        Args:
            email: The target email address for the request.
            ip: The client IP address.
        """
        now = time.time()

        with self._lock:
            email_key = f"email:{email}"
            if email_key not in self._store:
                self._store[email_key] = []
            self._store[email_key].append(now)

            ip_key = f"ip:{ip}"
            if ip_key not in self._store:
                self._store[ip_key] = []
            self._store[ip_key].append(now)

    @staticmethod
    def get_client_ip(request) -> str:
        """Extract client IP from X-Forwarded-For (leftmost) or remote_addr.

        Args:
            request: Flask request object.

        Returns:
            The client IP address string.
        """
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            # Use the leftmost IP (original client)
            return forwarded_for.split(",")[0].strip()
        return request.remote_addr or "unknown"

    def _clean_expired(self, key: str, cutoff: float) -> None:
        """Remove timestamps older than the cutoff from the store.

        Must be called while holding self._lock.

        Args:
            key: The store key to clean.
            cutoff: Timestamps older than this are removed.
        """
        if key in self._store:
            self._store[key] = [
                ts for ts in self._store[key] if ts > cutoff
            ]
            # Remove empty lists to prevent unbounded memory growth
            if not self._store[key]:
                del self._store[key]

    def _calculate_retry_after(
        self, timestamps: list[float], cutoff: float
    ) -> int:
        """Calculate seconds until the earliest timestamp in the window expires.

        The earliest request in the window will expire at (earliest + window_seconds).
        Retry-after is the time from now until that expiration.
        Since cutoff = now - window_seconds, this simplifies to: earliest - cutoff.

        Args:
            timestamps: List of request timestamps within the window.
            cutoff: The current window cutoff time (now - window_seconds).

        Returns:
            Seconds (rounded up) until the earliest request expires from the window.
        """
        if not timestamps:
            return 0
        earliest = min(timestamps)
        # earliest expires at (earliest + window_seconds)
        # retry_after = (earliest + window_seconds) - now
        # Since cutoff = now - window_seconds: retry_after = earliest - cutoff
        retry_after_seconds = int(earliest - cutoff) + 1  # Round up
        return max(retry_after_seconds, 1)
