"""Authoritative root-logging configuration.

Import this module FIRST — before any module that calls ``logging.basicConfig()``
at import time (e.g. ``database``, ``scalability_manager``, ``pattern_cache``,
``scalability_routes``). Those modules call ``basicConfig`` without a ``stream=``
argument, which defaults to ``sys.stderr`` and only takes effect if the root logger
has no handlers yet (first call wins). As a result their ``INFO:`` lines land on
stderr, and platforms such as Railway then tag every stderr line as
``severity: error``.

Configuring the root logger to ``sys.stdout`` here, before those imports run,
ensures application logs go to stdout. ``force=True`` (Python 3.8+) removes any
handlers already attached to the root logger and reconfigures it, reclaiming the
root even if some other import already ran ``basicConfig`` first.
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(levelname)s:%(name)s:%(message)s",
    force=True,
)
