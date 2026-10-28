"""Tenant-label fold: per-locale editor inputs → inline ``{nl,en,…}`` dict (R3.2).

Structural split out of ``members_config_validation.py`` (code-quality 2026-10-28
task 10). Holds the save-path label fold that assembles the editor's per-locale
``label_<locale>`` inputs into the single inline ``label`` dict the SAM resolver and the
projection builders consume. ``members_config_validation`` re-exports
:func:`fold_field_overlay_labels`; the public import surface is unchanged. Behaviour is
identical to the pre-split module.

Phase-1 i18n Option (b), design §3: a tenant-authored field/group/enum-option label is
runtime DATA stored as an inline per-language dict ``{nl, en, …}``. The Flask authoring
editor (``members_parameters.json`` field_def) presents that as ONE text input per
supported locale, keyed ``label_<locale>`` (``label_nl`` / ``label_en`` / … ) — the
former two hardcoded ``label_en``/``label_nl`` inputs, now locale-generic. The SAM-plane
consumers (``field_resolver`` ``OverlayField``/``FixedFieldOverride``/``FunctionalGroup``)
and the governance projection builders (``_projection_config_builders._map_*``) read a
single inline ``label`` dict. This fold is the single bridge point that assembles the
per-locale inputs into that ``label`` dict on save, BEFORE the overlay is stored — so the
stored (and therefore served) shape stays the ``{nl,en,…}`` dict (R2.2, shape unchanged).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

#: An editor per-locale label input key: ``label_<locale>`` (e.g. ``label_nl``, ``label_en``,
#: ``label_de``). Locale-generic by construction — adding a language needs no code change here
#: (R3.6); the locale segment is the trailing token. ``label`` itself (the folded dict) is NOT
#: matched (no trailing ``_<locale>``), so an already-folded overlay passes through untouched.
_LOCALE_INPUT_RE = re.compile(r"^label_([A-Za-z][A-Za-z0-9-]*)$")


def _fold_entry_labels(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Fold a single field-def entry's per-locale ``label_<locale>`` inputs into ``label``.

    Returns a NEW dict (never mutates ``entry``). Any ``label_<locale>`` key with a string
    value is removed and its value placed under ``label[<locale>]``. An existing inline
    ``label`` dict is preserved and MERGED into (a per-locale input WINS for its own locale,
    so re-authoring one language updates just that key). An entry carrying neither a
    per-locale input nor a ``label`` dict is returned unchanged (shape preserved). A
    ``label_<locale>`` whose value is not a string (an authoring quirk) is dropped from the
    output rather than folded, so the stored ``label`` dict stays ``{str: str}``.
    """
    folded: dict[str, Any] = {}
    label: dict[str, str] = {}

    # Seed from an already-present inline label dict (backward-compatible round-trip).
    existing = entry.get("label")
    if isinstance(existing, Mapping):
        for loc, text in existing.items():
            if isinstance(loc, str) and isinstance(text, str):
                label[loc] = text

    saw_locale_input = False
    for key, value in entry.items():
        match = _LOCALE_INPUT_RE.match(key) if isinstance(key, str) else None
        if match:
            saw_locale_input = True
            if isinstance(value, str):
                label[match.group(1)] = value
            # Non-string per-locale input: drop it (don't carry label_<locale> through).
            continue
        if key == "label":
            # Replaced by the merged `label` below; skip the raw copy.
            continue
        folded[key] = value

    # Only (re)attach a `label` dict when there is something to carry, OR the entry already
    # had an inline label dict — so an entry with no label at all stays label-free.
    if label or (isinstance(existing, Mapping) and not saw_locale_input):
        folded["label"] = label
    elif isinstance(existing, Mapping):
        # existing was present but empty and no inputs: preserve the (empty) dict shape.
        folded["label"] = label

    return folded


def _fold_entry_map(raw: Any) -> Any:
    """Fold labels for every value in a ``map<field_def>`` ({key: entry}); copy otherwise."""
    if not isinstance(raw, Mapping):
        return raw
    out: dict[str, Any] = {}
    for name, entry in raw.items():
        out[name] = _fold_entry_labels(entry) if isinstance(entry, Mapping) else entry
    return out


def _fold_entry_list(raw: Any) -> Any:
    """Fold labels for every entry in a ``list<object>``; copy otherwise."""
    if not isinstance(raw, (list, tuple)):
        return raw
    return [
        _fold_entry_labels(entry) if isinstance(entry, Mapping) else entry
        for entry in raw
    ]


def fold_field_overlay_labels(overlay: Any) -> Any:
    """Fold per-locale editor label inputs across a ``members.field_overlay`` object (R3.2).

    Returns a NEW overlay object (never mutates the input) in which every authored
    field-def entry — the ``functional_groups`` catalog (list), the added ``fields`` map,
    and the ``fixed_overrides`` map — has its per-locale ``label_<locale>`` inputs folded
    into a single inline ``label`` ``{nl, en, …}`` dict (design §3). All other keys/shapes
    are carried through unchanged, so the folded overlay is byte-for-byte the same as the
    input except for the label assembly — keeping the stored (and served) shape the inline
    dict the SAM resolver and the projection builders already consume (R2.2).

    Idempotent: an overlay whose labels are ALREADY inline ``{nl,en}`` dicts (no
    ``label_<locale>`` inputs) is returned structurally unchanged — so re-folding a stored
    overlay is a no-op (round-trip stable).
    """
    if not isinstance(overlay, Mapping):
        return overlay

    folded = dict(overlay)
    if "functional_groups" in folded:
        folded["functional_groups"] = _fold_entry_list(folded["functional_groups"])
    if "fields" in folded:
        folded["fields"] = _fold_entry_map(folded["fields"])
    if "fixed_overrides" in folded:
        folded["fixed_overrides"] = _fold_entry_map(folded["fixed_overrides"])
    return folded
