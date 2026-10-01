#!/usr/bin/env python3
"""members_mapping_loader.py — the SINGLE loader for h-dcn's authored source→target MAPPING.

Companion to ``members_config_loader.py`` (which loads the field/scope CONFIG). Reads
``scripts/aws/h-dcn/members_source_mapping.csv`` — the ONE authored, human- and Kiro-editable
mapping contract (spec s5m R0.1, design D0) — and parses it into the in-memory structures the
h-dcn backfill transform (:func:`sam.members.migration.hdcn_backfill.map_hdcn_row`) consumes:

- ``fixed`` — source column (BASE header, lower-cased) → ``{target: <dotted key>, rule}`` for
  every row whose ``target`` is a fixed ``personal.*`` / ``membership.*`` key;
- ``overlay`` — source column → ``{targets: (<canonical overlay key>, ...), rule}`` for every
  row whose ``target`` is an ``overlay.*`` key (a ``conditional split`` row names TWO targets
  joined with ``+``, e.g. ``overlay.iban+overlay.payment_method``);
- disposition SETS of source columns: ``calculated`` / ``excluded`` / ``additional_info``.

The CSV is a CONTRACT, not just data — the loader VALIDATES it on load (spec R0.4, design D0):
1. every ``target`` is a known fixed key, a declared overlay key, or a disposition token;
2. every ``rule`` is a known combination/conversion strategy;
3. every ``overlay.*`` target is an overlay field DECLARED in ``members_config.json`` — the
   drift guard that stops the mapping from inventing keys the tenant config does not carry.

The fixed-key vocabulary comes from the SAM fixed-field registry
(:data:`sam.members.domain.fixed_fields.FIXED_FIELDS`); the overlay-key vocabulary comes from
``members_config.json`` (via ``members_config_loader``). This module carries NO tenant
vocabulary of its own — it only READS the CSV + the two registries.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from typing import Any, Mapping

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
#: Default mapping-contract CSV (this tenant's single source of truth for the import mapping).
DEFAULT_MAPPING_PATH = os.path.join(_THIS_DIR, "members_source_mapping.csv")

#: Disposition tokens a ``target`` cell may carry instead of a real field key (spec R2.6).
DISPOSITION_CALCULATED = "(calculated)"
DISPOSITION_EXCLUDED = "(excluded)"
DISPOSITION_ADDITIONAL_INFO = "(additional_info)"
DISPOSITION_TOKENS = frozenset(
    {DISPOSITION_CALCULATED, DISPOSITION_EXCLUDED, DISPOSITION_ADDITIONAL_INFO}
)

#: The combination/conversion strategies a ``rule`` cell may name (spec R0.2/R0.3, design D0b).
#: An empty ``rule`` is allowed ONLY on a disposition row (validated below); a real target
#: with a blank rule defaults to ``single``.
KNOWN_RULES = frozenset(
    {
        "single",
        "coalesce",
        "concat",
        "date",
        "member_number",
        "membership_type",
        "region",
        "gender",
        "magazine",
        "iban_or_payment",
    }
)

#: Separator joining the two targets of a ``conditional split`` row (``iban_or_payment``).
_TARGET_SPLIT_SEP = "+"
#: Overlay dotted-key prefix.
_OVERLAY_PREFIX = "overlay."
#: Fixed dotted-key prefixes.
_FIXED_PREFIXES = ("personal.", "membership.")


class MappingContractError(ValueError):
    """Raised when the authored mapping CSV fails to load or violates the contract (R0.4).

    Carries ``errors`` (an ordered list of human-readable problems) so the caller can surface
    every violation at once rather than only the first.
    """

    def __init__(self, errors: list[str], *, path: str):
        self.errors = list(errors)
        self.path = path
        detail = "\n  - ".join(errors)
        super().__init__(f"invalid mapping contract {path!r}:\n  - {detail}")


@dataclass(frozen=True)
class FixedMapping:
    """A source column that feeds a FIXED ``personal.*`` / ``membership.*`` target."""

    source_column: str
    col_index: int
    target: str
    rule: str
    note: str = ""


@dataclass(frozen=True)
class OverlayMapping:
    """A source column that feeds one or more CANONICAL ``overlay.*`` targets.

    ``targets`` is a tuple of canonical overlay KEYS (bare, no ``overlay.`` prefix). A plain
    ``single`` / ``coalesce`` row names one; the ``iban_or_payment`` conditional split names two.
    """

    source_column: str
    col_index: int
    targets: tuple[str, ...]
    rule: str
    note: str = ""


@dataclass(frozen=True)
class MappingContract:
    """The parsed, validated mapping contract (spec R0, design D0).

    Attributes mirror the structures the transform uses:

    - ``fixed`` — BASE source header (lower-cased) → :class:`FixedMapping`;
    - ``overlay`` — BASE source header (lower-cased) → :class:`OverlayMapping`;
    - ``calculated`` / ``excluded`` / ``additional_info`` — frozensets of BASE source headers
      (lower-cased) in each non-mapped disposition (spec R2.6/R2.7).

    ``rows`` keeps every parsed row in file order for reporting / round-tripping.
    """

    fixed: Mapping[str, FixedMapping]
    overlay: Mapping[str, OverlayMapping]
    calculated: frozenset[str]
    excluded: frozenset[str]
    additional_info: frozenset[str]
    rows: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def fixed_source_columns(self) -> dict[str, str]:
        """``{source header → dotted fixed key}`` (the ``FIXED_SOURCE_COLUMNS`` shape)."""
        return {src: m.target for src, m in self.fixed.items()}

    def overlay_source_columns(self) -> dict[str, tuple[str, ...]]:
        """``{source header → (canonical overlay key, ...)}`` (the ``OVERLAY_SOURCE_COLUMNS`` shape)."""
        return {src: m.targets for src, m in self.overlay.items()}


def _base_header(column: str) -> str:
    """Strip a trailing ``#<colindex>`` position suffix back to the BASE header (spec R1.3).

    ``E-mailadres#34`` → ``e-mailadres``; the result is lower-cased so it matches the way the
    transform consults the tables (``col.strip().lower()``). A blank-named column stays ``""``.
    """
    base = column
    if "#" in column:
        head, _, tail = column.rpartition("#")
        if tail.isdigit():
            base = head
    return base.strip().lower()


def _known_fixed_keys() -> frozenset[str]:
    """The valid fixed dotted keys, from the SAM fixed-field registry (single source of truth)."""
    from sam.members.domain.fixed_fields import FIXED_FIELDS

    return frozenset(f.dotted_key() for f in FIXED_FIELDS)


def _declared_overlay_keys(config: Mapping[str, Any] | None) -> frozenset[str]:
    """The overlay field keys DECLARED in ``members_config.json`` (the drift-guard vocabulary)."""
    if config is None:
        from members_config_loader import load_members_config

        config = load_members_config()
    fields = (config.get("field_overlay", {}) or {}).get("fields", {}) or {}
    return frozenset(fields.keys())


def load_mapping_contract(
    path: str = DEFAULT_MAPPING_PATH,
    *,
    config: Mapping[str, Any] | None = None,
) -> MappingContract:
    """Load + VALIDATE the authored mapping CSV into a :class:`MappingContract` (R0.1/R0.4).

    ``#``-prefixed lines are comments and skipped. The header row
    (``source_column,col_index,target,rule,note``) is required. ``config`` is the parsed
    ``members_config.json`` (loaded on demand if omitted) — its declared overlay fields are the
    drift guard for ``overlay.*`` targets.

    Raises :class:`MappingContractError` (collecting ALL violations) on any contract breach:
    unknown target, unknown rule, an ``overlay.*`` target not declared in the config, a
    disposition row carrying a real rule, or a malformed row.
    """
    known_fixed = _known_fixed_keys()
    declared_overlay = _declared_overlay_keys(config)

    errors: list[str] = []
    fixed: dict[str, FixedMapping] = {}
    overlay: dict[str, OverlayMapping] = {}
    calculated: set[str] = set()
    excluded: set[str] = set()
    additional_info: set[str] = set()
    parsed_rows: list[dict[str, Any]] = []

    with open(path, "r", encoding="utf-8", newline="") as fh:
        # Drop full-line comments BEFORE csv parsing so a '#' note inside a quoted field is safe.
        data_lines = [ln for ln in fh if not ln.lstrip().startswith("#")]

    reader = csv.DictReader(data_lines)
    required_cols = {"source_column", "col_index", "target", "rule"}
    header = set(reader.fieldnames or ())
    if not required_cols.issubset(header):
        missing = ", ".join(sorted(required_cols - header))
        raise MappingContractError(
            [f"CSV header missing required column(s): {missing}"], path=path
        )

    for lineno, row in enumerate(reader, start=2):
        source_column = (row.get("source_column") or "").strip()
        target = (row.get("target") or "").strip()
        rule = (row.get("rule") or "").strip()
        note = (row.get("note") or "").strip()
        raw_index = (row.get("col_index") or "").strip()

        if not source_column and not target:
            continue  # a wholly blank spacer line

        try:
            col_index = int(raw_index)
        except (TypeError, ValueError):
            errors.append(
                f"row {lineno} ({source_column!r}): col_index {raw_index!r} is not an integer"
            )
            col_index = -1

        base = _base_header(source_column)
        parsed_rows.append(
            {
                "source_column": source_column,
                "col_index": col_index,
                "target": target,
                "rule": rule,
                "note": note,
                "base": base,
            }
        )

        # --- validate + classify the target ------------------------------------------------
        if target in DISPOSITION_TOKENS:
            if rule and rule not in ("concat",):
                # A disposition row is either blank-ruled or (additional_info) with `concat`.
                errors.append(
                    f"row {lineno} ({source_column!r}): disposition {target} must have a blank "
                    f"rule (or 'concat' for (additional_info)), got {rule!r}"
                )
            if target == DISPOSITION_CALCULATED:
                calculated.add(base)
            elif target == DISPOSITION_EXCLUDED:
                excluded.add(base)
            else:  # (additional_info)
                additional_info.add(base)
            continue

        # A real target must carry a KNOWN rule (blank defaults to single).
        effective_rule = rule or "single"
        if effective_rule not in KNOWN_RULES:
            errors.append(
                f"row {lineno} ({source_column!r}): unknown rule {rule!r} "
                f"(known: {', '.join(sorted(KNOWN_RULES))})"
            )

        if target.startswith(_OVERLAY_PREFIX) or _TARGET_SPLIT_SEP in target:
            # One or (conditional split) two overlay targets.
            raw_targets = target.split(_TARGET_SPLIT_SEP)
            overlay_keys: list[str] = []
            for rt in raw_targets:
                rt = rt.strip()
                if not rt.startswith(_OVERLAY_PREFIX):
                    errors.append(
                        f"row {lineno} ({source_column!r}): target {rt!r} is not a fixed key, "
                        f"an overlay.* key, or a disposition token"
                    )
                    continue
                key = rt[len(_OVERLAY_PREFIX):]
                overlay_keys.append(key)
                if key not in declared_overlay:
                    errors.append(
                        f"row {lineno} ({source_column!r}): overlay target {rt!r} is not a "
                        f"declared overlay field in members_config.json (drift guard)"
                    )
            overlay[base] = OverlayMapping(
                source_column=source_column,
                col_index=col_index,
                targets=tuple(overlay_keys),
                rule=effective_rule,
                note=note,
            )
        elif any(target.startswith(p) for p in _FIXED_PREFIXES):
            if target not in known_fixed:
                errors.append(
                    f"row {lineno} ({source_column!r}): fixed target {target!r} is not a known "
                    f"fixed field key (registry: sam.members.domain.fixed_fields.FIXED_FIELDS)"
                )
            fixed[base] = FixedMapping(
                source_column=source_column,
                col_index=col_index,
                target=target,
                rule=effective_rule,
                note=note,
            )
        else:
            errors.append(
                f"row {lineno} ({source_column!r}): target {target!r} is not a fixed key "
                f"(personal.*/membership.*), an overlay.* key, or a disposition token"
            )

    # --- orphan-field guard (R2.5): every DECLARED overlay field must have a mapping backing ---
    # Mirror of the per-row drift guard above, in the OPPOSITE direction: that guard rejects a
    # mapping target NOT declared in the config; this one rejects a config overlay field with NO
    # mapping backing. ``additional_info`` is excluded because it is populated by the
    # ``(additional_info)`` disposition, NOT a mapping TARGET, so it is legitimately absent from
    # ``overlay`` targets (``region``/``iban``/``payment_method`` DO appear as overlay targets).
    mapped_overlay_keys = {key for m in overlay.values() for key in m.targets}
    orphans = declared_overlay - mapped_overlay_keys
    orphans = orphans - {"additional_info"}
    for key in sorted(orphans):
        errors.append(
            f"config overlay field {key!r} is declared in members_config.json but has NO "
            f"mapping backing in the contract (orphan-field guard, R2.5)"
        )

    if errors:
        raise MappingContractError(errors, path=path)

    return MappingContract(
        fixed=fixed,
        overlay=overlay,
        calculated=frozenset(calculated),
        excluded=frozenset(excluded),
        additional_info=frozenset(additional_info),
        rows=tuple(parsed_rows),
    )
