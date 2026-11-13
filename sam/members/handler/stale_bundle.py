"""STALE-SPA-BUNDLE rejection policy for ``config#fields`` writes.

Extracted from :mod:`sam.members.handler.app` (code-quality-fixes-2026-11-12 task 5); the edge
keeps the response-shaping call while this module owns the status/code policy.

A ``PUT /members/config/fields`` write that arrives in the RETIRED whole-overlay shape (a whole
record keyed by ``overrides``, no ``ops`` list) comes from a CACHED OLD SPA bundle that has not
reloaded since the Change-Op switch. NO write was attempted (the guard fires at the edge before
any op is derived). The caller-safe response is a 409 with a DISTINCT, stable machine code
``errors.api.staleClient`` — intentionally NOT the generic validation 400 and NOT the
data-conflict ``errors.api.conflict`` — so the SPA can tell this apart and render a dedicated
"a newer version is available — reload the app" prompt. The message is the actionable remedy
and carries NO raw internals (steering 39). 409 fits the existing error envelope (same
"reload" family as the StaleVersionError 409).
"""

from __future__ import annotations

__all__ = [
    "STALE_CLIENT_BUNDLE_CODE",
    "STALE_CLIENT_BUNDLE_STATUS",
    "stale_client_bundle_rejection",
]

#: HTTP status for a retired-shape write from a stale client bundle.
STALE_CLIENT_BUNDLE_STATUS = 409

#: Stable machine code the SPA matches to render its "reload the app" prompt.
STALE_CLIENT_BUNDLE_CODE = "errors.api.staleClient"


def stale_client_bundle_rejection(exc: BaseException) -> tuple[int, str, str]:
    """Map a :class:`StaleClientBundleError` to ``(status, message, code)`` for the edge.

    Args:
        exc: The guard's exception; its message is the caller-safe remedy text.

    Returns:
        ``(409, str(exc), "errors.api.staleClient")``.
    """
    return STALE_CLIENT_BUNDLE_STATUS, str(exc), STALE_CLIENT_BUNDLE_CODE
