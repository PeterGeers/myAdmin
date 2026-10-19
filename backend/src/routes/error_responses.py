"""Shared error-response helper for route blueprints.

Centralises the one error-handling pattern every Flask route repeats in its
``except Exception`` block. The old convention returned ``str(e)`` straight to
the client::

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

That leaks internal exception text (table names, file paths, library versions,
stack frames) to the caller — flagged uniformly by CodeQL
``py/stack-trace-exposure`` and revised in steering ``30-backend-api-flask-mysql``.

The replacement logs the **full** exception (with stack) server-side under a
generated correlation ``error_id`` and returns only a **generic** message plus
that id to the client, keeping the same response shape and HTTP status::

    from routes.error_responses import error_response

    except Exception as e:
        return error_response(e, "Failed to save bookings", status=500)

Returns a ``(jsonify(body), status)`` tuple so handlers keep ``return``-ing it
exactly as before. The client sees::

    {"success": False, "error": "Failed to save bookings", "error_id": "<uuid>"}

and the server log carries the full traceback keyed by the same ``error_id`` so
support can tie a user-reported failure to the exact server-side event without
exposing internals.

Two legacy response shapes are supported:

* ``include_success=True`` (default) -> ``{"success": False, "error": ..., "error_id": ...}``
* ``include_success=False`` -> bare ``{"error": ..., "error_id": ...}`` (the shape the
  sysadmin role endpoints historically used).

``error_payload`` returns the plain ``dict`` (no ``jsonify``) for callers that
build the response themselves — e.g. Server-Sent-Events generators that
``json.dumps`` an error frame rather than returning a Flask response.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from flask import jsonify

logger = logging.getLogger(__name__)

# Generic, caller-safe fallback when no specific client message is supplied.
_DEFAULT_CLIENT_MESSAGE = "An internal error occurred. Please try again later."


def _log_and_build(
    exc: BaseException,
    client_message: str,
    *,
    include_success: bool,
    log_context: str | None,
) -> dict[str, Any]:
    """Log ``exc`` with a full stack under a fresh ``error_id`` and build the body."""
    error_id = uuid.uuid4().hex
    context = f"{log_context}: " if log_context else ""
    # exc_info=exc records the full traceback server-side (the exception object is
    # passed explicitly so this is valid even outside an active except block, per
    # ruff LOG014); the client never sees it.
    logger.error(
        "%s[error_id=%s] %s: %s",
        context,
        error_id,
        type(exc).__name__,
        exc,
        exc_info=exc,
    )

    body: dict[str, Any] = {}
    if include_success:
        body["success"] = False
    body["error"] = client_message or _DEFAULT_CLIENT_MESSAGE
    body["error_id"] = error_id
    return body


def error_payload(
    exc: BaseException,
    client_message: str = _DEFAULT_CLIENT_MESSAGE,
    *,
    include_success: bool = True,
    log_context: str | None = None,
) -> dict[str, Any]:
    """Log the exception server-side and return the generic error **dict**.

    Use this when you need the raw body (not a Flask response) — e.g. an SSE
    generator that ``json.dumps`` an error frame.

    Args:
        exc: The caught exception. Logged in full (with stack) server-side.
        client_message: Generic, caller-safe message returned to the client.
            Never include ``str(exc)`` here.
        include_success: When ``True`` (default) prefix the body with
            ``"success": False``; when ``False`` return the bare
            ``{"error": ..., "error_id": ...}`` shape.
        log_context: Optional short label for the server log line (e.g. the
            handler name) to aid triage.

    Returns:
        A dict containing ``error`` (the generic message), ``error_id`` (a fresh
        correlation id, also logged), and — unless ``include_success=False`` —
        ``success: False``.
    """
    return _log_and_build(
        exc,
        client_message,
        include_success=include_success,
        log_context=log_context,
    )


def error_response(
    exc: BaseException,
    client_message: str = _DEFAULT_CLIENT_MESSAGE,
    *,
    status: int = 500,
    include_success: bool = True,
    log_context: str | None = None,
) -> tuple[Any, int]:
    """Log the exception server-side and return a ``(jsonify(body), status)`` tuple.

    Drop-in replacement for::

        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    rewritten as::

        except Exception as e:
            return error_response(e, "Human-readable generic message", status=500)

    Args:
        exc: The caught exception. Logged in full (with stack) server-side.
        client_message: Generic, caller-safe message returned to the client.
            Never include ``str(exc)`` here.
        status: HTTP status code (unchanged from the old convention — typically
            500 for unexpected errors).
        include_success: When ``True`` (default) include ``"success": False`` in
            the body; when ``False`` return the bare ``{"error": ...}`` shape used
            by the sysadmin role endpoints.
        log_context: Optional short label for the server log line.

    Returns:
        ``(flask.Response, status)`` ready to ``return`` from a route handler.
    """
    body = _log_and_build(
        exc,
        client_message,
        include_success=include_success,
        log_context=log_context,
    )
    return jsonify(body), status
