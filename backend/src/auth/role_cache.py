"""
In-memory cache for per-tenant user roles.

Avoids a DB lookup on every request by caching roles with a 5-minute TTL.
The cache is keyed by email:tenant and invalidated when roles change.
"""

import time
from typing import Dict, List, Tuple

CACHE_TTL_SECONDS = 300  # 5 minutes

# Cache structure: { "email:tenant": (roles_list, timestamp) }
_role_cache: Dict[str, Tuple[List[str], float]] = {}


def get_tenant_roles(email: str, tenant: str, db) -> List[str]:
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
        fetch=True
    )
    roles = [r['role'] for r in (rows or [])]
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
