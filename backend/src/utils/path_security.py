"""
Path-containment security helper.

Single source of truth for "is this resolved path contained inside an allowed
base directory?" — used at every filesystem sink that touches an
attacker-influenceable path (CodeQL ``py/path-injection``).

Containment is made explicit so both a reviewer and the scanner can see it:

1. Canonicalize the candidate path AND the allowed base dir(s) with
   ``os.path.realpath`` — this resolves ``..`` traversal segments and symlinks
   to an absolute, real path.
2. Accept only when the real candidate equals an allowed base, or sits strictly
   beneath it using a trailing ``os.sep`` boundary. The separator boundary stops
   a sibling that merely shares a name prefix (e.g. ``/storage_evil`` must NOT
   satisfy a ``/storage`` base).

Any resolution error is treated as "not contained" (fail closed).

Usage::

    from utils.path_security import is_within_base

    if not is_within_base(candidate, allowed_base):
        raise SomeSecurityError(...)
"""

import os

__all__ = ["is_within_base"]


def is_within_base(candidate_path: str, *allowed_bases: str) -> bool:
    """Return True iff ``candidate_path`` resolves inside one of ``allowed_bases``.

    Args:
        candidate_path: The (possibly attacker-influenceable) path to check.
        *allowed_bases: One or more base directories the path must stay within.

    Returns:
        True when the canonicalized candidate equals, or is strictly contained
        beneath, one of the canonicalized base dirs. False on any traversal
        escape, sibling-prefix near-miss, or resolution error (fail closed).
    """
    if not candidate_path or not allowed_bases:
        return False

    try:
        real_candidate = os.path.realpath(candidate_path)
        for base in allowed_bases:
            if not base:
                continue
            real_base = os.path.realpath(base)
            if real_candidate == real_base or real_candidate.startswith(
                real_base + os.sep
            ):
                return True
        return False
    except Exception:
        return False
