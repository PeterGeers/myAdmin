"""
In-memory cache for per-tenant user roles.

Avoids a DB lookup on every request by caching roles with a 5-minute TTL.
The cache is keyed by email:tenant and invalidated when roles change.
"""

import time

CACHE_TTL_SECONDS = 300  # 5 minutes

# Cache structure: { "email:tenant": (roles_list, timestamp) }
_role_cache: dict[str, tuple[list[str], float]] = {}


def get_tenant_roles(email: str, tenant: str, db) -> list[str]:
    """
    Get per-tenant roles for a user, using cache when available.

    Args:
        email: User email address
        tenant: Tenant administration name
        db: DatabaseManager instance

    Returns:
        List of role names for this user in this tenant
    """
    key = f"{email}:{tenant}"
    now = time.time()

    if key in _role_cache:
        roles, ts = _role_cache[key]
        if now - ts < CACHE_TTL_SECONDS:
            return roles

    rows = db.execute_query(
        "SELECT role FROM user_tenant_roles WHERE email = %s AND administration = %s",
        (email, tenant),
        fetch=True,
    )
    roles = [r["role"] for r in (rows or [])]

    # Do NOT cache a negative (empty) result. A user whose roles were assigned
    # out-of-band (direct SQL, seed/provisioning scripts) — i.e. NOT through the
    # tenant-admin role routes that call invalidate_cache — would otherwise be
    # pinned to a stale "no roles" answer for the full TTL, surfacing as spurious
    # "role not assigned" errors that even a fresh login can't clear (this cache
    # is process-global and not tied to the session). Skipping the empty cache
    # write means such a grant is picked up on the very next request. Users with
    # genuinely no roles re-query each request, but those requests are rejected
    # fast and are rare. Populated results are still cached for the full TTL.
    if roles:
        _role_cache[key] = (roles, now)
    return roles


def invalidate_cache(email: str, tenant: str):
    """
    Remove cached roles for a user+tenant after a role change.

    Args:
        email: User email address
        tenant: Tenant administration name
    """
    _role_cache.pop(f"{email}:{tenant}", None)
