"""
Members module **handler layer** — the thin HTTP edge of the single Members Lambda.

Per ``.kiro/steering/35-sam-module-architecture-sam.md`` the handler is an **adapter, not
the logic**: it parses the request, authenticates + establishes tenant context, authorizes
(entitlement + scope), routes internally, delegates to the domain service, and shapes the
HTTP response. It holds **no business logic** and **no DynamoDB access** — those live in
the domain and repository layers respectively (dependencies point downward only).

Contents:
- ``routes`` — the internal route map (union of h-dcn's ~18 handler behaviours).
- ``router`` — resolves ``(method, path)`` → a route spec + path params.
- ``app``    — the Lambda entry point: parse → auth → tenant → authorize → route → respond.
"""

from sam.members.handler.app import handler

__all__ = ["handler"]
