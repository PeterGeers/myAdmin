"""Unit tests for the authoritative stdout root-logging configuration.

Verifies that importing ``logging_setup`` attaches a ``StreamHandler`` to the
root logger whose stream is ``sys.stdout`` (not stderr). This is the property
that keeps platforms such as Railway from tagging INFO lines as errors.

No live DB / no network — imports the isolated logging_setup module only.
"""

import logging
import sys


def test_root_logger_streams_to_stdout():
    import logging_setup  # noqa: F401  (import triggers basicConfig at import time)

    root = logging.getLogger()

    stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
    assert stream_handlers, "root logger has no StreamHandler"

    stdout_handlers = [h for h in stream_handlers if h.stream is sys.stdout]
    assert stdout_handlers, "no root StreamHandler is bound to sys.stdout"

    stderr_handlers = [h for h in stream_handlers if h.stream is sys.stderr]
    assert not stderr_handlers, "a root StreamHandler is bound to sys.stderr"
