"""Wire-key/path Change-Op builders.

Part of ConfigFieldsCrudService (code-quality-fixes-2026-11-12 task 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sam.members.repository.projection_config_write_repository import REMOVE, SET


class ConfigFieldsWireOpsMixin:
    """Wire-key/path Change-Op builders."""

    # ── Op emission (absent = untouched / null = REMOVE that aspect) ────────────────────

    def _attr_ops(
        self, placement: Mapping[str, Any], attrs: Mapping[str, Any]
    ) -> list[dict]:
        """Turn an attrs payload into Change-Ops under the resolved entry path, choosing the VERB
        by ENTRY EXISTENCE (design-review Must-fix #1 — the create-vs-update correction).

        Two cases, decided by ``placement["create"]`` (which the placement read set from the
        consistent record):

        - **CREATE (the entry does NOT yet exist):** emit a SINGLE ``SET <map>.<key> = :whole``
          whose value is the whole entry map (the non-``None`` attrs collected into one object).
          A child path ``SET <map>.<key>.<attr>`` would be rejected by DynamoDB because the parent
          entry does not exist, and ``if_not_exists`` parent-seed + child-set in one expression is
          the "Two document paths overlap" rejection (Must-fix #1). The parent MAP
          (``fields``/``overrides``/``functional_groups``) itself is guaranteed to exist by the row
          skeleton (C6), so a single whole-entry ``SET`` is legal and atomic. An explicit ``None``
          in a CREATE payload is simply absent from the seeded map (there is nothing yet to clear).
        - **UPDATE (the entry EXISTS):** emit ONE op per PRESENT attr addressing
          ``<map>.<key>.<attr>``: a non-``None`` value → ``SET``; an explicit ``None`` → ``REMOVE``
          (clear just that aspect). An attr the payload OMITS yields no op (left untouched).

        In both cases DynamoDB leaves every attribute the ops do not name physically untouched, so
        the write is structurally unable to truncate a sibling entry or slice (R1.3/R4.2).
        """
        entry_path = [placement["map"], placement["key"]]
        if placement.get("create"):
            # Seed the whole entry in one SET. A `None` has nothing to clear on a brand-new entry,
            # so it is dropped from the seed (absent = not-authored); every real value is included.
            whole_entry = {
                attr: value for attr, value in attrs.items() if value is not None
            }
            return [{"action": SET, "path": list(entry_path), "value": whole_entry}]

        ops: list[dict] = []
        for attr, value in attrs.items():
            path = [*entry_path, attr]
            if value is None:
                ops.append({"action": REMOVE, "path": path})
            else:
                ops.append({"action": SET, "path": path, "value": value})
        return ops

    @staticmethod
    def _remove_entry_op(placement: Mapping[str, Any]) -> dict:
        """A single ``REMOVE <map>.<key>`` op removing a whole field/override/group entry."""
        return {"action": REMOVE, "path": [placement["map"], placement["key"]]}
