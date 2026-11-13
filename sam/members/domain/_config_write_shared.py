"""Shared constants and error type for ConfigWriteService.
Part of ConfigWriteService (task 9).
"""

from __future__ import annotations

import re

#: The storage bucket variable (overlay) fields live under (mirrors field_resolver.OVERLAY_GROUP /
#: the retired Flask ``members_config_validation.OVERLAY_GROUP``). Used ONLY to build a stable,
#: caller-safe dotted error key for a variable field (``overlay.<key>``) so a rejected write names
#: the offending field the same way across both planes (R8.3/R8.4).
OVERLAY_GROUP = "overlay"

#: SEC-7 (design §10, R6.3): a tenant-authored ``application_embed_origins`` entry becomes a token
#: in the CloudFront CSP ``frame-ancestors`` directive (``'frame-ancestors ' + list.join(' ')``, see
#: ``infrastructure/application-form.tf``). Framing DEFAULTS CLOSED (a host with no list → no header
#: → not embeddable), so the write path is the one place that keeps the allow-list well-formed: every
#: entry MUST be a bare ``https://host[:port]`` serialized origin — NO ``*`` wildcard-all, NO path /
#: query / fragment, and NO whitespace or CSP-delimiter characters (`` `` ``;`` `` `` `` ``'`` ``"``)
#: that could inject an extra ``frame-ancestors`` token or a second directive at the edge. An ``http``
#: origin is rejected too (the form is HTTPS-only). This is deny-by-default's authoring guard — a
#: malformed/dangerous entry is a clickjacking surface, so it is rejected fail-loud, never stored.
_EMBED_ORIGIN_RE = re.compile(
    r"^https://"  # https scheme only (no http, no wildcard scheme)
    r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)"  # first DNS label
    r"(?:\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*"  # further labels
    r"(?::[0-9]{1,5})?"  # optional :port
    r"$"  # nothing after the authority — no path/query/fragment
)

#: Bound the list so a hand-edited / abusive row can neither bloat the stored item nor produce an
#: unreasonably long ``frame-ancestors`` directive at the edge (SEC-7 / defensive).
_EMBED_ORIGINS_MAX_COUNT = 50
_EMBED_ORIGIN_MAX_LEN = 255


class ConfigWriteValidationError(ValueError):
    """A deliberate, caller-safe config-write body validation error (maps to HTTP 400).

    Raised by a per-``configId`` body validator when the request body is malformed. It is a
    DELIBERATE validation error — distinct from an unexpected exception — so the edge may surface
    its message to the caller (SAM-plane error conventions, steering 35). It subclasses
    :class:`ValueError` so existing ``except ValueError`` seams keep working.
    """
