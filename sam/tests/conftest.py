"""
Shared pytest fixtures for the PreTokenGen Lambda tests (S4 D2).

The handler memoises its :class:`GovernanceReader` on the module for the life of a
warm Lambda container (fail-fast config validated once at cold start, T12). Under
test each case installs its own reader (via the ``patch_reader`` fixture that
patches ``handler._build_reader``), so the process-level cache must be cleared
between tests or the first test's reader would leak into later ones. This autouse
fixture resets that cache around every test — mirroring a fresh cold start.
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.pretokengen import handler as handler_mod


@pytest.fixture(autouse=True)
def _reset_reader_cache():
    """Clear the handler's cold-start reader cache before and after each test."""
    handler_mod._reader_cache = None
    yield
    handler_mod._reader_cache = None
